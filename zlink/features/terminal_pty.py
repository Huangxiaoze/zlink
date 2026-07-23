"""Cross-platform PTY helper for the host-side remote terminal."""

from __future__ import annotations

import logging
import os
import shutil
import struct
import subprocess
import sys
import threading
import time
from typing import Optional

log = logging.getLogger(__name__)

FEATURE_TERMINAL = "terminal"


def default_shell() -> list[str]:
    if sys.platform == "win32":
        comspec = os.environ.get("COMSPEC") or shutil.which("cmd.exe") or "cmd.exe"
        return [comspec]
    shell = os.environ.get("SHELL") or "/bin/bash"
    if os.path.basename(shell) in {"bash", "zsh", "fish"}:
        return [shell, "-l"]
    return [shell]


class PtySession:
    """Interactive PTY process with resize support."""

    def __init__(self, cols: int = 120, rows: int = 32) -> None:
        self.cols = max(20, min(400, int(cols)))
        self.rows = max(5, min(200, int(rows)))
        self._closed = False
        self._lock = threading.Lock()
        self._proc: Optional[subprocess.Popen] = None
        self._master_fd: Optional[int] = None
        self._winpty = None  # winpty.PtyProcess when available
        self._spawn()

    @property
    def alive(self) -> bool:
        if self._closed:
            return False
        if self._winpty is not None:
            return bool(self._winpty.isalive())
        if self._proc is None:
            return False
        return self._proc.poll() is None

    def write(self, data: bytes) -> None:
        if not data or self._closed:
            return
        with self._lock:
            if self._winpty is not None:
                try:
                    self._winpty.write(data.decode("utf-8", errors="replace"))
                except Exception as exc:
                    log.debug("winpty write failed: %s", exc)
                return
            fd = self._master_fd
            if fd is None:
                return
            view = memoryview(data)
            while view:
                try:
                    n = os.write(fd, view)
                except OSError as exc:
                    log.debug("pty write failed: %s", exc)
                    return
                if n <= 0:
                    return
                view = view[n:]

    def read(self, max_bytes: int = 8192) -> bytes:
        """Blocking-ish read for the host pump thread.

        POSIX master fd is non-blocking; winpty ``read`` blocks until data or EOF.
        """
        if self._closed:
            return b""
        if self._winpty is not None:
            try:
                text = self._winpty.read(max_bytes)
            except Exception:
                return b""
            if not text:
                return b""
            return text.encode("utf-8", errors="replace") if isinstance(text, str) else bytes(text)
        fd = self._master_fd
        if fd is None:
            return b""
        try:
            return os.read(fd, max_bytes)
        except OSError:
            return b""

    def resize(self, cols: int, rows: int) -> None:
        self.cols = max(20, min(400, int(cols)))
        self.rows = max(5, min(200, int(rows)))
        with self._lock:
            if self._winpty is not None:
                try:
                    self._winpty.setwinsize(self.rows, self.cols)
                except Exception as exc:
                    log.debug("winpty resize failed: %s", exc)
                return
            fd = self._master_fd
            if fd is None or sys.platform == "win32":
                return
            try:
                import fcntl
                import termios

                winsz = struct.pack("HHHH", self.rows, self.cols, 0, 0)
                fcntl.ioctl(fd, termios.TIOCSWINSZ, winsz)
            except Exception as exc:
                log.debug("pty resize failed: %s", exc)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            if self._winpty is not None:
                try:
                    self._winpty.terminate(force=True)
                except Exception:
                    pass
                self._winpty = None
            if self._proc is not None:
                try:
                    self._proc.terminate()
                except Exception:
                    pass
                try:
                    self._proc.wait(timeout=1.0)
                except Exception:
                    try:
                        self._proc.kill()
                    except Exception:
                        pass
                self._proc = None
            if self._master_fd is not None:
                try:
                    os.close(self._master_fd)
                except OSError:
                    pass
                self._master_fd = None

    def _spawn(self) -> None:
        if sys.platform == "win32":
            self._spawn_windows()
        else:
            self._spawn_posix()

    def _spawn_posix(self) -> None:
        import pty

        master, slave = pty.openpty()
        try:
            self._set_winsize_fd(slave, self.cols, self.rows)
            env = os.environ.copy()
            env.setdefault("TERM", "xterm-256color")
            env["COLUMNS"] = str(self.cols)
            env["LINES"] = str(self.rows)
            self._proc = subprocess.Popen(
                default_shell(),
                stdin=slave,
                stdout=slave,
                stderr=slave,
                cwd=os.path.expanduser("~"),
                env=env,
                preexec_fn=os.setsid,
                close_fds=True,
            )
        finally:
            try:
                os.close(slave)
            except OSError:
                pass
        self._master_fd = master
        try:
            os.set_blocking(master, False)  # type: ignore[attr-defined]
        except (AttributeError, OSError):
            pass

    def _spawn_windows(self) -> None:
        try:
            from winpty import PtyProcess  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "Windows terminal needs pywinpty (pip install pywinpty)"
            ) from exc
        env = os.environ.copy()
        env.setdefault("TERM", "xterm-256color")
        cmdline = subprocess.list2cmdline(default_shell())
        # backend=1 prefers ConPTY (Windows 10+); winpty backend often fails to echo input.
        self._winpty = PtyProcess.spawn(
            cmdline,
            dimensions=(self.rows, self.cols),
            cwd=os.path.expanduser("~"),
            env=env,
            backend=1,
        )

    @staticmethod
    def _set_winsize_fd(fd: int, cols: int, rows: int) -> None:
        try:
            import fcntl
            import termios

            winsz = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(fd, termios.TIOCSWINSZ, winsz)
        except Exception:
            pass


class HostTerminalBridge:
    """Owns one PTY for the active remote session and pumps output packets."""

    def __init__(self, send_packet) -> None:
        self._send_packet = send_packet
        self._session: Optional[PtySession] = None
        self._stop = threading.Event()
        self._reader: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    @property
    def active(self) -> bool:
        sess = self._session
        return sess is not None and sess.alive

    def handle_payload(self, payload: bytes) -> None:
        from ..core.protocol import unpack_term_message

        meta, blob = unpack_term_message(payload)
        op = str(meta.get("op") or "")
        if op == "open":
            self.open(int(meta.get("cols") or 120), int(meta.get("rows") or 32))
        elif op == "data":
            self.write(blob)
        elif op == "resize":
            self.resize(int(meta.get("cols") or 120), int(meta.get("rows") or 32))
        elif op == "close":
            self.close(send_closed=True)

    def open(self, cols: int, rows: int) -> None:
        from ..core.protocol import pack_term_message

        with self._lock:
            self._stop_reader_locked()
            if self._session is not None:
                self._session.close()
                self._session = None
            try:
                self._session = PtySession(cols=cols, rows=rows)
            except Exception as exc:
                log.exception("terminal open failed")
                try:
                    self._send_packet(
                        pack_term_message({"op": "open_err", "error": str(exc)})
                    )
                except Exception:
                    pass
                return
            self._stop.clear()
            self._reader = threading.Thread(
                target=self._read_loop, name="host-term-read", daemon=True
            )
            self._reader.start()
        try:
            self._send_packet(
                pack_term_message({"op": "open_ok", "cols": cols, "rows": rows})
            )
        except Exception:
            self.close(send_closed=False)

    def write(self, data: bytes) -> None:
        sess = self._session
        if sess is not None:
            sess.write(data)

    def resize(self, cols: int, rows: int) -> None:
        sess = self._session
        if sess is not None:
            sess.resize(cols, rows)

    def close(self, send_closed: bool = True) -> None:
        from ..core.protocol import pack_term_message

        with self._lock:
            self._stop_reader_locked()
            if self._session is not None:
                self._session.close()
                self._session = None
        if send_closed:
            try:
                self._send_packet(pack_term_message({"op": "closed"}))
            except Exception:
                pass

    def _stop_reader_locked(self) -> None:
        self._stop.set()
        reader = self._reader
        self._reader = None
        if reader is not None and reader.is_alive() and reader is not threading.current_thread():
            reader.join(timeout=1.0)

    def _read_loop(self) -> None:
        from ..core.protocol import pack_term_message

        while not self._stop.is_set():
            sess = self._session
            if sess is None:
                break
            if not sess.alive:
                try:
                    self._send_packet(pack_term_message({"op": "closed"}))
                except Exception:
                    pass
                break
            try:
                chunk = sess.read(8192)
            except Exception:
                chunk = b""
            if chunk:
                try:
                    self._send_packet(pack_term_message({"op": "data"}, chunk))
                except Exception:
                    break
            else:
                # Empty read: process likely exited (winpty) or EAGAIN (POSIX).
                if not sess.alive:
                    try:
                        self._send_packet(pack_term_message({"op": "closed"}))
                    except Exception:
                        pass
                    break
                time.sleep(0.01)
