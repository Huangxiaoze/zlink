from __future__ import annotations

import hashlib
import hmac
import logging
import socket
import time
from typing import Callable

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


def configure_socket(sock: socket.socket, recv_buffer: int = 256 * 1024) -> None:
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, recv_buffer)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, recv_buffer)
    except OSError:
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
        self.last_rx = time.monotonic()
        self.last_tx = time.monotonic()

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

    def send_raw(self, data: bytes) -> None:
        if self._closed:
            raise ConnectionError("connection closed")
        view = memoryview(data)
        while view:
            n = self.sock.send(view)
            if n == 0:
                raise ConnectionError("socket closed during send")
            view = view[n:]
        self.last_tx = time.monotonic()

    def send_frame(self, frame: Frame) -> None:
        self.send_raw(pack_frame(frame.type, frame.payload, frame.flags))

    def send_json(self, msg_type: MsgType, data: dict) -> None:
        self.send_raw(pack_json(msg_type, data))

    def send_heartbeat(self) -> None:
        self.send_json(MsgType.HEARTBEAT, {"t": time.time()})

    def recv_exact(self, size: int) -> bytes:
        chunks: list[bytes] = []
        remaining = size
        while remaining > 0:
            chunk = self.sock.recv(remaining)
            if not chunk:
                raise ConnectionError("socket closed during recv")
            chunks.append(chunk)
            remaining -= len(chunk)
        self.last_rx = time.monotonic()
        return b"".join(chunks)

    def recv_frame(self) -> Frame:
        header = self.recv_exact(HEADER_SIZE)
        msg_type, flags, length = unpack_header(header)
        if length > self.max_payload:
            raise ProtocolError(f"payload {length} exceeds max {self.max_payload}")
        payload = self.recv_exact(length) if length else b""
        return Frame(type=msg_type, payload=payload, flags=flags)

    def is_heartbeat_expired(self, timeout_s: float) -> bool:
        return (time.monotonic() - self.last_rx) > timeout_s


def serve_forever(
    bind_host: str,
    port: int,
    handler: Callable[[Connection, tuple], None],
    should_stop: Callable[[], bool],
    recv_buffer: int = 256 * 1024,
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


def connect_to(host: str, port: int, timeout_s: float, recv_buffer: int = 256 * 1024) -> Connection:
    sock = socket.create_connection((host, port), timeout=timeout_s)
    configure_socket(sock, recv_buffer=recv_buffer)
    sock.settimeout(None)
    return Connection(sock)


def read_json_frame(conn: Connection, expected: MsgType | None = None) -> tuple[MsgType, dict]:
    frame = conn.recv_frame()
    if expected is not None and frame.type != expected:
        raise ProtocolError(f"expected {expected}, got {frame.type}")
    return frame.type, decode_json(frame.payload)
