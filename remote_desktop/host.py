from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Any, Callable, Optional

from . import PROTOCOL_VERSION
from .capture import ScreenCapturer
from .config import HostConfig, StreamConfig
from .devices import detect_os_label, remote_username
from .input_io import InputInjector
from .net import Connection, password_matches, serve_forever
from .pointer_sync import PointerAuthority
from .protocol import MsgType, ProtocolError, decode_json, pack_frame_message
from .terminal_pty import FEATURE_TERMINAL, HostTerminalBridge

log = logging.getLogger(__name__)

_HOST_OS = detect_os_label()


class RemoteHost:
    def __init__(self, config: HostConfig) -> None:
        self.config = config
        self._stop = threading.Event()
        self.stream = config.stream.clamp()
        self._capturer = ScreenCapturer(self.stream)
        self._session_lock = threading.Lock()
        self.session_live = threading.Event()
        self._os_label = _HOST_OS
        # GUI/main-thread clipboard bridge exchanges packed CLIPBOARD payloads here.
        self.clipboard_out: queue.Queue = queue.Queue(maxsize=128)
        self.clipboard_in: queue.Queue = queue.Queue(maxsize=128)
        # Dedicated file transfer queues (do not block recv on apply).
        self.file_out: queue.Queue = queue.Queue(maxsize=256)
        self.file_in: queue.Queue = queue.Queue(maxsize=256)
        # Remote terminal (PTY) packets — flushed on the send thread.
        self.term_out: queue.Queue = queue.Queue(maxsize=256)
        self._term: Optional[HostTerminalBridge] = None
        # GUI sets this after applying a clipboard packet on the Qt thread.
        self.clipboard_applied = threading.Event()
        # Optional wakeup for GUI (e.g. Qt Signal.emit) — called from recv thread.
        self.clipboard_notify: Optional[Callable[[], None]] = None
        self.file_notify: Optional[Callable[[], None]] = None
        self._pointer = PointerAuthority()

    def stop(self) -> None:
        self._stop.set()
        self.session_live.clear()
        self._capturer.stop()

    def run(self) -> None:
        if self.config.bind_require_password and self.config.net.host in {"0.0.0.0", "::"}:
            if not self.config.net.password:
                raise ValueError("password is required when binding on all interfaces")

        self._capturer.start()
        for _ in range(50):
            if self._capturer.src_width > 0:
                break
            time.sleep(0.05)

        try:
            serve_forever(
                self.config.net.host,
                self.config.net.port,
                handler=self._handle_client,
                should_stop=self._stop.is_set,
                recv_buffer=self.config.net.recv_buffer,
            )
        finally:
            self.stop()

    def _clear_session_queues(self) -> None:
        for q in (
            self.clipboard_out,
            self.clipboard_in,
            self.file_out,
            self.file_in,
            self.term_out,
        ):
            while True:
                try:
                    q.get_nowait()
                except queue.Empty:
                    break

    def _enqueue_term(self, packet: bytes) -> None:
        self.term_out.put(packet, timeout=30.0)

    def _hello_ack(self, conn: Connection, payload: dict[str, Any]) -> None:
        data = dict(payload)
        data.setdefault("os", self._os_label)
        data.setdefault("username", remote_username())
        conn.send_json(MsgType.HELLO_ACK, data)

    def _handle_client(self, conn: Connection, addr: tuple) -> None:
        try:
            hello = self._recv_hello(conn)
        except (ConnectionError, OSError, ProtocolError) as exc:
            log.warning("hello failed %s: %s", addr, exc)
            conn.close()
            return
        if hello is None:
            conn.close()
            return

        role = str(hello.get("role") or "client")
        if role == "terminal":
            self._handle_terminal_client(conn, addr)
            return

        # Desktop session remains exclusive.
        if not self._session_lock.acquire(blocking=False):
            log.warning("reject %s: desktop session busy", addr)
            try:
                self._hello_ack(conn, {"ok": False, "reason": "busy"})
            except OSError:
                pass
            conn.close()
            return

        self._handle_desktop_client(conn, addr, hello)

    def _recv_hello(self, conn: Connection) -> Optional[dict[str, Any]]:
        frame = conn.recv_frame()
        if frame.type != MsgType.HELLO:
            self._hello_ack(conn, {"ok": False, "reason": "expected_hello"})
            return None
        hello = decode_json(frame.payload)
        client_ver = int(hello.get("version", -1))
        if client_ver != PROTOCOL_VERSION:
            self._hello_ack(conn, {"ok": False, "reason": "version_mismatch"})
            return None
        role = str(hello.get("role") or "client")
        # Probes use role=probe and intentionally send an empty password; still
        # advertise OS so the device list can show Windows / macOS / Ubuntu.
        if role == "probe":
            self._hello_ack(conn, {"ok": False, "reason": "probe"})
            return None
        if not password_matches(self.config.net.password, str(hello.get("password", ""))):
            self._hello_ack(conn, {"ok": False, "reason": "auth_failed"})
            log.warning("auth failed")
            return None
        return hello

    def _handle_terminal_client(self, conn: Connection, addr: tuple) -> None:
        """SSH-like terminal session: independent of desktop lock / screen capture."""
        log.info("terminal client connected %s", addr)
        session_stop = threading.Event()
        term_out: queue.Queue = queue.Queue(maxsize=256)
        term = HostTerminalBridge(lambda packet: term_out.put(packet, timeout=30.0))
        sender: threading.Thread | None = None
        watchdog: threading.Thread | None = None
        try:
            self._hello_ack(
                conn,
                {
                    "ok": True,
                    "mode": "terminal",
                    "version": PROTOCOL_VERSION,
                    "features": [FEATURE_TERMINAL],
                },
            )
            sender = threading.Thread(
                target=self._term_send_loop,
                args=(conn, session_stop, term_out),
                name="host-term-send",
                daemon=True,
            )
            watchdog = threading.Thread(
                target=self._watchdog_loop,
                args=(conn, session_stop),
                name="host-term-watchdog",
                daemon=True,
            )
            sender.start()
            watchdog.start()
            self._term_recv_loop(conn, session_stop, term)
        except (ConnectionError, OSError, ProtocolError) as exc:
            log.warning("terminal session ended (%s): %s", addr, exc)
        except Exception:
            log.exception("terminal session crashed %s", addr)
        finally:
            session_stop.set()
            term.close(send_closed=False)
            try:
                conn.send_json(MsgType.BYE, {"reason": "host_close"})
            except Exception:
                pass
            conn.close()
            if sender:
                sender.join(timeout=2.0)
            if watchdog:
                watchdog.join(timeout=2.0)
            log.info("terminal client disconnected %s", addr)

    def _handle_desktop_client(
        self, conn: Connection, addr: tuple, hello: dict[str, Any]
    ) -> None:
        log.info("desktop client connected %s", addr)
        sender: threading.Thread | None = None
        watchdog: threading.Thread | None = None
        injector: InputInjector | None = None
        session_stop = threading.Event()
        mouse_listener: Any = None
        self._clear_session_queues()
        self._term = HostTerminalBridge(self._enqueue_term)

        try:
            q = hello.get("quality")
            if isinstance(q, dict):
                self._apply_quality(q)

            self._hello_ack(
                conn,
                {
                    "ok": True,
                    "mode": "desktop",
                    "screen_w": self._capturer.src_width,
                    "screen_h": self._capturer.src_height,
                    "version": PROTOCOL_VERSION,
                    "features": ["clipboard", "file_transfer", FEATURE_TERMINAL],
                },
            )

            self.session_live.set()
            injector = InputInjector(
                self._capturer.src_width,
                self._capturer.src_height,
                pointer=self._pointer,
            )
            try:
                from pynput import mouse as pynput_mouse

                ptr = self._pointer

                def _on_local_pointer_move(x: float, y: float) -> None:
                    if injector is None:
                        return
                    ptr.note_local_move(
                        int(x),
                        int(y),
                        injector.screen_w,
                        injector.screen_h,
                    )

                mouse_listener = pynput_mouse.Listener(on_move=_on_local_pointer_move)
                mouse_listener.start()
            except Exception:
                log.warning("local pointer listener unavailable", exc_info=True)
                mouse_listener = None
            sender = threading.Thread(
                target=self._send_loop,
                args=(conn, session_stop),
                name="host-send",
                daemon=True,
            )
            watchdog = threading.Thread(
                target=self._watchdog_loop,
                args=(conn, session_stop),
                name="host-watchdog",
                daemon=True,
            )
            sender.start()
            watchdog.start()
            self._recv_loop(conn, injector, session_stop)
        except (ConnectionError, OSError, ProtocolError) as exc:
            log.warning("session ended (%s): %s", addr, exc)
        except Exception:
            log.exception("session crashed %s", addr)
        finally:
            session_stop.set()
            self.session_live.clear()
            if mouse_listener is not None:
                try:
                    mouse_listener.stop()
                except Exception:
                    pass
            if injector is not None:
                injector.release_all()
            if self._term is not None:
                self._term.close(send_closed=False)
                self._term = None
            self._clear_session_queues()
            try:
                conn.send_json(MsgType.BYE, {"reason": "host_close"})
            except Exception:
                pass
            conn.close()
            if sender:
                sender.join(timeout=2.0)
            if watchdog:
                watchdog.join(timeout=2.0)
            self._session_lock.release()
            log.info("desktop client disconnected %s", addr)

    def _apply_quality(self, data: dict[str, Any]) -> None:
        stream = StreamConfig(
            max_fps=float(data.get("max_fps", self.stream.max_fps)),
            jpeg_quality=int(data.get("jpeg_quality", self.stream.jpeg_quality)),
            scale=float(data.get("scale", self.stream.scale)),
            min_jpeg_quality=self.stream.min_jpeg_quality,
            max_jpeg_quality=self.stream.max_jpeg_quality,
            min_scale=self.stream.min_scale,
            max_scale=self.stream.max_scale,
        ).clamp()
        self.stream = stream
        self._capturer.update_stream(stream)
        log.info(
            "quality updated fps=%s q=%s scale=%s",
            stream.max_fps,
            stream.jpeg_quality,
            stream.scale,
        )

    def _flush_reliable_out(
        self,
        conn: Connection,
        session_stop: threading.Event,
        out_q: queue.Queue,
    ) -> bool:
        """Send pending reliable packets. False if connection died."""
        while not session_stop.is_set():
            try:
                packet = out_q.get_nowait()
            except queue.Empty:
                return True
            try:
                conn.send_raw(packet)
            except (ConnectionError, OSError):
                return False
        return True

    def _term_send_loop(
        self,
        conn: Connection,
        session_stop: threading.Event,
        term_out: queue.Queue,
    ) -> None:
        """Terminal-only session: TERM packets + heartbeat (no desktop frames)."""
        while not session_stop.is_set() and not self._stop.is_set():
            if not self._flush_reliable_out(conn, session_stop, term_out):
                session_stop.set()
                break
            now = time.monotonic()
            if (now - conn.last_tx) >= self.config.net.heartbeat_interval_s:
                try:
                    conn.send_heartbeat()
                except (ConnectionError, OSError):
                    session_stop.set()
                    break
            session_stop.wait(0.01)

    def _term_recv_loop(
        self,
        conn: Connection,
        session_stop: threading.Event,
        term: HostTerminalBridge,
    ) -> None:
        while not session_stop.is_set() and not self._stop.is_set():
            try:
                frame = conn.recv_frame(stop_event=session_stop)
            except ConnectionError:
                session_stop.set()
                break
            if frame.type == MsgType.TERM:
                try:
                    term.handle_payload(frame.payload)
                except Exception:
                    log.exception("terminal handle failed")
            elif frame.type == MsgType.HEARTBEAT:
                continue
            elif frame.type == MsgType.BYE:
                session_stop.set()
                break
            else:
                log.debug("ignore msg %s in terminal session", frame.type)

    def _send_loop(self, conn: Connection, session_stop: threading.Event) -> None:
        last_adapt = time.monotonic()
        send_failures = 0
        ok_streak = 0
        while not session_stop.is_set() and not self._stop.is_set():
            if not self._flush_reliable_out(conn, session_stop, self.clipboard_out):
                session_stop.set()
                break
            if not self._flush_reliable_out(conn, session_stop, self.file_out):
                session_stop.set()
                break
            if not self._flush_reliable_out(conn, session_stop, self.term_out):
                session_stop.set()
                break

            now = time.monotonic()
            if (now - conn.last_tx) >= self.config.net.heartbeat_interval_s:
                try:
                    conn.send_heartbeat()
                except (ConnectionError, OSError):
                    session_stop.set()
                    break

            frame = self._capturer.pop_latest()
            if frame is None:
                session_stop.wait(0.002)
                continue
            cx, cy, host_ptr = self._pointer.snapshot()
            packet = pack_frame_message(
                frame.jpeg,
                width=frame.width,
                height=frame.height,
                seq=self._capturer.sequence,
                quality=frame.quality,
                scale=frame.scale,
                cursor_x=cx,
                cursor_y=cy,
                host_pointer=host_ptr,
            )
            if not conn.try_send_raw(packet):
                send_failures += 1
                ok_streak = 0
                if conn.closed or send_failures >= 8:
                    session_stop.set()
                    break
                # Only degrade when the socket is actually back-pressured.
                # Do NOT use frame byte size: LAN HD JPEGs are often >1MB and
                # size-based adapt was crushing sharpness on gigabit links.
                self._apply_quality(
                    {
                        "max_fps": max(10.0, self.stream.max_fps - 5),
                        "jpeg_quality": max(
                            self.stream.min_jpeg_quality, self.stream.jpeg_quality - 8
                        ),
                        "scale": max(self.stream.min_scale, self.stream.scale - 0.1),
                    }
                )
                session_stop.wait(0.01)
                continue
            send_failures = 0
            ok_streak += 1

            # Recover toward the client's requested quality after a healthy streak.
            now = time.monotonic()
            if now - last_adapt > 1.2 and ok_streak >= 8:
                last_adapt = now
                target_q = self.config.stream.jpeg_quality
                target_scale = self.config.stream.scale
                target_fps = self.config.stream.max_fps
                next_q = min(target_q, self.stream.jpeg_quality + 4)
                next_scale = min(target_scale, self.stream.scale + 0.05)
                next_fps = min(target_fps, self.stream.max_fps + 5)
                if (
                    next_q != self.stream.jpeg_quality
                    or next_scale != self.stream.scale
                    or next_fps != self.stream.max_fps
                ):
                    self._apply_quality(
                        {
                            "max_fps": next_fps,
                            "jpeg_quality": next_q,
                            "scale": next_scale,
                        }
                    )

    def _watchdog_loop(self, conn: Connection, session_stop: threading.Event) -> None:
        timeout = self.config.net.heartbeat_timeout_s
        while not session_stop.is_set() and not self._stop.is_set():
            if conn.is_heartbeat_expired(timeout):
                log.warning("heartbeat timeout (%.1fs idle)", timeout)
                session_stop.set()
                conn.close()
                break
            session_stop.wait(0.5)

    def _recv_loop(
        self,
        conn: Connection,
        injector: InputInjector,
        session_stop: threading.Event,
    ) -> None:
        while not session_stop.is_set() and not self._stop.is_set():
            try:
                frame = conn.recv_frame(stop_event=session_stop)
            except ConnectionError:
                session_stop.set()
                break
            if frame.type == MsgType.MOUSE:
                injector.handle_mouse(decode_json(frame.payload))
            elif frame.type == MsgType.KEY:
                injector.handle_key(decode_json(frame.payload))
            elif frame.type == MsgType.BYE:
                injector.release_all()
                session_stop.set()
                break
            elif frame.type == MsgType.QUALITY:
                self._apply_quality(decode_json(frame.payload))
            elif frame.type == MsgType.CLIPBOARD:
                try:
                    self.clipboard_in.put_nowait(frame.payload)
                except queue.Full:
                    log.warning("clipboard_in full, drop packet")
                    continue
                # Wait until GUI applies clipboard BEFORE injecting later keys
                # (otherwise remote Ctrl+V pastes the old clipboard).
                notify = self.clipboard_notify
                if notify is not None:
                    self.clipboard_applied.clear()
                    try:
                        notify()
                    except Exception:
                        log.exception("clipboard_notify failed")
                    if not self.clipboard_applied.wait(timeout=1.0):
                        log.warning("clipboard apply timeout")
            elif frame.type == MsgType.FILE:
                try:
                    self.file_in.put_nowait(frame.payload)
                except queue.Full:
                    log.warning("file_in full, drop packet")
                    continue
                notify = self.file_notify
                if notify is not None:
                    try:
                        notify()
                    except Exception:
                        log.exception("file_notify failed")
            elif frame.type == MsgType.TERM:
                term = self._term
                if term is not None:
                    try:
                        term.handle_payload(frame.payload)
                    except Exception:
                        log.exception("terminal handle failed")
            elif frame.type == MsgType.HEARTBEAT:
                continue
            else:
                log.debug("ignore msg %s", frame.type)
