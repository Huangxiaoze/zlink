from __future__ import annotations

import hashlib
import hmac
import logging
import select
import socket
import sys
import threading
import time
from typing import Callable, Optional

from .protocol import (
    HEADER_SIZE,
    Frame,
    MsgType,
    ProtocolError,
    decode_json,
    pack_frame,
    pack_json,
    unpack_header,
)

log = logging.getLogger(__name__)


def configure_socket(sock: socket.socket, recv_buffer: int = 2 * 1024 * 1024) -> None:
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, recv_buffer)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, recv_buffer)
    except OSError:
        pass
    _enable_keepalive_probes(sock)
    # Allow recv/send loops to wake periodically; 2s balances liveness vs HD frames.
    sock.settimeout(2.0)


def _enable_keepalive_probes(sock: socket.socket) -> None:
    """Faster dead-peer detection than default OS keepalive."""
    try:
        if sys.platform == "win32":
            # Windows: SIO_KEEPALIVE_VALS — on, idle 30s, interval 5s
            idle_ms, interval_ms = 30_000, 5_000
            sock.ioctl(socket.SIO_KEEPALIVE_VALS, (1, idle_ms, interval_ms))  # type: ignore[attr-defined]
            return
        if hasattr(socket, "TCP_KEEPIDLE"):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 30)
        if hasattr(socket, "TCP_KEEPINTVL"):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 5)
        if hasattr(socket, "TCP_KEEPCNT"):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 5)
        # macOS uses TCP_KEEPALIVE (idle seconds)
        if sys.platform == "darwin" and hasattr(socket, "TCP_KEEPALIVE"):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPALIVE, 30)
    except (OSError, AttributeError, ValueError):
        pass


def password_digest(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def password_matches(expected: str, provided: str) -> bool:
    if not expected:
        return True
    return hmac.compare_digest(password_digest(expected), password_digest(provided))


class Connection:
    def __init__(self, sock: socket.socket, max_payload: int = 16 * 1024 * 1024) -> None:
        self.sock = sock
        self.max_payload = max_payload
        self._closed = False
        self._send_lock = threading.Lock()
        now = time.monotonic()
        self.last_rx = now
        self.last_tx = now
        # Any successful IO progress (including partial recv of a large frame).
        self.last_activity = now

    @property
    def closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass

    def touch_rx(self) -> None:
        now = time.monotonic()
        self.last_rx = now
        self.last_activity = now

    def touch_tx(self) -> None:
        now = time.monotonic()
        self.last_tx = now
        self.last_activity = now

    def send_raw(self, data: bytes) -> None:
        """Send a full packet. Never abandons a partial write (would desync protocol)."""
        if self._closed:
            raise ConnectionError("connection closed")
        view = memoryview(data)
        with self._send_lock:
            if self._closed:
                raise ConnectionError("connection closed")
            stall_rounds = 0
            while view:
                try:
                    n = self.sock.send(view)
                    stall_rounds = 0
                except socket.timeout:
                    stall_rounds += 1
                    self.touch_tx()  # still alive, just backed up
                    if stall_rounds >= 15:  # ~30s with 2s timeout
                        raise ConnectionError("send stalled too long")
                    continue
                if n == 0:
                    raise ConnectionError("socket closed during send")
                view = view[n:]
                self.touch_tx()

    def send_frame(self, frame: Frame) -> None:
        self.send_raw(pack_frame(frame.type, frame.payload, frame.flags))

    def send_json(self, msg_type: MsgType, data: dict) -> None:
        self.send_raw(pack_json(msg_type, data))

    def send_heartbeat(self) -> None:
        self.send_json(MsgType.HEARTBEAT, {"t": time.time()})

    def try_send_raw(self, data: bytes) -> bool:
        """Drop whole frame if socket not writable; never partially send."""
        if self._closed:
            return False
        try:
            with self._send_lock:
                if self._closed:
                    return False
                _, writable, _ = select.select([], [self.sock], [], 0.0)
                if not writable:
                    return False
            # send_raw re-acquires lock and writes the full datagram atomically
            # relative to other senders.
            self.send_raw(data)
            return True
        except (ConnectionError, OSError) as exc:
            log.debug("try_send failed: %s", exc)
            return False

    def recv_exact(self, size: int, stop_event: Optional[threading.Event] = None) -> bytes:
        chunks: list[bytes] = []
        remaining = size
        while remaining > 0:
            if self._closed or (stop_event is not None and stop_event.is_set()):
                raise ConnectionError("connection closed during recv")
            try:
                chunk = self.sock.recv(min(remaining, 256 * 1024))
            except socket.timeout:
                continue
            if not chunk:
                raise ConnectionError("socket closed during recv")
            # Critical: update liveness on every chunk so large FRAME transfers
            # do not trip heartbeat watchdog mid-download.
            self.touch_rx()
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def recv_frame(self, stop_event: Optional[threading.Event] = None) -> Frame:
        header = self.recv_exact(HEADER_SIZE, stop_event=stop_event)
        msg_type, flags, length = unpack_header(header)
        if length > self.max_payload:
            raise ProtocolError(f"payload {length} exceeds max {self.max_payload}")
        payload = self.recv_exact(length, stop_event=stop_event) if length else b""
        return Frame(type=msg_type, payload=payload, flags=flags)

    def is_heartbeat_expired(self, timeout_s: float) -> bool:
        # Use last_activity so partial transfers / sends count as alive.
        return (time.monotonic() - self.last_activity) > timeout_s


def serve_forever(
    bind_host: str,
    port: int,
    handler: Callable[[Connection, tuple], None],
    should_stop: Callable[[], bool],
    recv_buffer: int = 2 * 1024 * 1024,
) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((bind_host, port))
        server.listen(1)
        server.settimeout(1.0)
        log.info("listening on %s:%s", bind_host, port)
        while not should_stop():
            try:
                client_sock, addr = server.accept()
            except socket.timeout:
                continue
            except OSError:
                if should_stop():
                    break
                raise
            configure_socket(client_sock, recv_buffer=recv_buffer)
            conn = Connection(client_sock)
            try:
                handler(conn, addr)
            finally:
                conn.close()


def connect_to(host: str, port: int, timeout_s: float, recv_buffer: int = 2 * 1024 * 1024) -> Connection:
    sock = socket.create_connection((host, port), timeout=timeout_s)
    configure_socket(sock, recv_buffer=recv_buffer)
    return Connection(sock)


def read_json_frame(conn: Connection, expected: MsgType | None = None) -> tuple[MsgType, dict]:
    frame = conn.recv_frame()
    if expected is not None and frame.type != expected:
        raise ProtocolError(f"expected {expected}, got {frame.type}")
    return frame.type, decode_json(frame.payload)
