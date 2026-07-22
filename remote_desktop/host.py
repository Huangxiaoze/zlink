from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Any, Callable, Optional

from . import PROTOCOL_VERSION
from .capture import ScreenCapturer
from .config import HostConfig, StreamConfig
from .input_io import InputInjector
from .net import Connection, password_matches, serve_forever
from .protocol import MsgType, ProtocolError, decode_json, pack_frame_message

log = logging.getLogger(__name__)


class RemoteHost:
    def __init__(self, config: HostConfig) -> None:
        self.config = config
        self._stop = threading.Event()
        self.stream = config.stream.clamp()
        self._capturer = ScreenCapturer(self.stream)
        self._session_lock = threading.Lock()
        self.session_live = threading.Event()
        # GUI/main-thread clipboard bridge exchanges packed CLIPBOARD payloads here.
        self.clipboard_out: queue.Queue = queue.Queue(maxsize=128)
        self.clipboard_in: queue.Queue = queue.Queue(maxsize=128)
        # GUI sets this after applying a clipboard packet on the Qt thread.
        self.clipboard_applied = threading.Event()
        # Optional wakeup for GUI (e.g. Qt Signal.emit) — called from recv thread.
        self.clipboard_notify: Optional[Callable[[], None]] = None

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

    def _clear_clipboard_queues(self) -> None:
        for q in (self.clipboard_out, self.clipboard_in):
            while True:
                try:
                    q.get_nowait()
                except queue.Empty:
                    break

    def _handle_client(self, conn: Connection, addr: tuple) -> None:
        if not self._session_lock.acquire(blocking=False):
            log.warning("reject %s: session busy", addr)
            try:
                conn.send_json(MsgType.HELLO_ACK, {"ok": False, "reason": "busy"})
            except OSError:
                pass
            return

        log.info("client connected %s", addr)
        sender: threading.Thread | None = None
        watchdog: threading.Thread | None = None
        session_stop = threading.Event()
        injector: InputInjector | None = None
        self._clear_clipboard_queues()

        try:
            if not self._handshake(conn):
                return

            self.session_live.set()
            injector = InputInjector(self._capturer.src_width, self._capturer.src_height)
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
            self._clear_clipboard_queues()
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
            log.info("client disconnected %s", addr)

    def _handshake(self, conn: Connection) -> bool:
        frame = conn.recv_frame()
        if frame.type != MsgType.HELLO:
            conn.send_json(MsgType.HELLO_ACK, {"ok": False, "reason": "expected_hello"})
            return False
        hello = decode_json(frame.payload)
        client_ver = int(hello.get("version", -1))
        if client_ver != PROTOCOL_VERSION:
            conn.send_json(MsgType.HELLO_ACK, {"ok": False, "reason": "version_mismatch"})
            return False
        if not password_matches(self.config.net.password, str(hello.get("password", ""))):
            conn.send_json(MsgType.HELLO_ACK, {"ok": False, "reason": "auth_failed"})
            log.warning("auth failed")
            return False

        q = hello.get("quality")
        if isinstance(q, dict):
            self._apply_quality(q)

        conn.send_json(
            MsgType.HELLO_ACK,
            {
                "ok": True,
                "screen_w": self._capturer.src_width,
                "screen_h": self._capturer.src_height,
                "version": PROTOCOL_VERSION,
                "features": ["clipboard"],
            },
        )
        return True

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

    def _flush_clipboard_out(self, conn: Connection, session_stop: threading.Event) -> bool:
        """Send pending clipboard packets (reliable). False if connection died."""
        while not session_stop.is_set():
            try:
                packet = self.clipboard_out.get_nowait()
            except queue.Empty:
                return True
            try:
                conn.send_raw(packet)
            except (ConnectionError, OSError):
                return False
        return True

    def _send_loop(self, conn: Connection, session_stop: threading.Event) -> None:
        pending_bytes = 0
        last_adapt = time.monotonic()
        send_failures = 0
        while not session_stop.is_set() and not self._stop.is_set():
            if not self._flush_clipboard_out(conn, session_stop):
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
            packet = pack_frame_message(
                frame.jpeg,
                width=frame.width,
                height=frame.height,
                seq=self._capturer.sequence,
                quality=frame.quality,
                scale=frame.scale,
            )
            if not conn.try_send_raw(packet):
                send_failures += 1
                if conn.closed or send_failures >= 8:
                    session_stop.set()
                    break
                self._apply_quality(
                    {
                        "max_fps": max(10.0, self.stream.max_fps - 5),
                        "jpeg_quality": max(self.stream.min_jpeg_quality, self.stream.jpeg_quality - 8),
                        "scale": max(self.stream.min_scale, self.stream.scale - 0.1),
                    }
                )
                session_stop.wait(0.01)
                continue
            send_failures = 0
            pending_bytes = len(packet)

            now = time.monotonic()
            if now - last_adapt > 1.2:
                last_adapt = now
                target_q = self.config.stream.jpeg_quality
                target_scale = self.config.stream.scale
                if pending_bytes > 350_000:
                    next_q = max(self.stream.min_jpeg_quality, self.stream.jpeg_quality - 4)
                    next_scale = self.stream.scale
                    if self.stream.jpeg_quality <= self.stream.min_jpeg_quality + 2:
                        next_scale = max(self.stream.min_scale, self.stream.scale - 0.05)
                    if next_q != self.stream.jpeg_quality or next_scale != self.stream.scale:
                        self._apply_quality(
                            {
                                "max_fps": self.stream.max_fps,
                                "jpeg_quality": next_q,
                                "scale": next_scale,
                            }
                        )
                elif pending_bytes < 120_000:
                    next_q = min(target_q, self.stream.jpeg_quality + 4)
                    next_scale = min(target_scale, self.stream.scale + 0.05)
                    if next_q != self.stream.jpeg_quality or next_scale != self.stream.scale:
                        self._apply_quality(
                            {
                                "max_fps": self.stream.max_fps,
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
            elif frame.type == MsgType.HEARTBEAT:
                continue
            elif frame.type == MsgType.BYE:
                session_stop.set()
                break
            else:
                log.debug("ignore msg %s", frame.type)
