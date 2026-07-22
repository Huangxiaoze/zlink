from __future__ import annotations

import logging
import threading
import time
from typing import Any

from . import PROTOCOL_VERSION
from .codec import decode_jpeg
from .config import ClientConfig
from .input_io import pygame_key_name
from .net import Connection, connect_to
from .protocol import MsgType, ProtocolError, decode_json, unpack_frame_message

log = logging.getLogger(__name__)


class RemoteClient:
    def __init__(self, config: ClientConfig) -> None:
        self.config = config
        self._stop = threading.Event()
        self._conn: Connection | None = None
        self._frame_lock = threading.Lock()
        self._latest_jpeg: bytes | None = None
        self._frame_meta: dict[str, Any] = {}
        self._screen_w = 1
        self._screen_h = 1
        self._view_w = 1280
        self._view_h = 720
        self._pygame: Any = None

    def stop(self) -> None:
        self._stop.set()
        if self._conn:
            try:
                self._conn.send_json(MsgType.BYE, {"reason": "client_close"})
            except Exception:
                pass
            self._conn.close()

    def run(self) -> None:
        import pygame

        self._pygame = pygame
        pygame.init()
        pygame.display.set_caption(self.config.window_title)
        screen = pygame.display.set_mode((self._view_w, self._view_h), pygame.RESIZABLE)
        clock = pygame.time.Clock()
        backoff = 1.0

        try:
            while not self._stop.is_set():
                try:
                    self._connect_and_stream(screen, clock)
                    backoff = 1.0
                except (ConnectionError, OSError, ProtocolError) as exc:
                    log.warning("disconnected: %s", exc)
                except Exception:
                    log.exception("client session error")

                if self._stop.is_set() or not self.config.reconnect:
                    break

                log.info("reconnect in %.1fs", backoff)
                self._wait_with_ui(screen, clock, backoff)
                backoff = min(self.config.reconnect_max_s, backoff * 1.7)
        finally:
            self.stop()
            pygame.quit()

    def _wait_with_ui(self, screen: Any, clock: Any, seconds: float) -> None:
        pygame = self._pygame
        end = time.monotonic() + seconds
        font = pygame.font.SysFont(None, 28)
        while time.monotonic() < end and not self._stop.is_set():
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._stop.set()
                    return
                if event.type == pygame.VIDEORESIZE:
                    self._view_w, self._view_h = event.w, event.h
                    screen = pygame.display.set_mode((self._view_w, self._view_h), pygame.RESIZABLE)
            screen.fill((20, 20, 24))
            text = font.render("Reconnecting...", True, (220, 220, 220))
            screen.blit(text, (24, 24))
            pygame.display.flip()
            clock.tick(30)

    def _connect_and_stream(self, screen: Any, clock: Any) -> None:
        net = self.config.net
        conn = connect_to(net.host, net.port, net.connect_timeout_s, net.recv_buffer)
        self._conn = conn
        hello = {
            "role": "client",
            "version": PROTOCOL_VERSION,
            "password": net.password,
            "quality": {
                "max_fps": self.config.stream.max_fps,
                "jpeg_quality": self.config.stream.jpeg_quality,
                "scale": self.config.stream.scale,
            },
        }
        conn.send_json(MsgType.HELLO, hello)
        frame = conn.recv_frame()
        if frame.type != MsgType.HELLO_ACK:
            raise ProtocolError("expected HELLO_ACK")
        ack = decode_json(frame.payload)
        if not ack.get("ok"):
            raise ProtocolError(f"handshake failed: {ack.get('reason')}")
        self._screen_w = max(1, int(ack.get("screen_w", 1)))
        self._screen_h = max(1, int(ack.get("screen_h", 1)))
        log.info("connected to host screen %sx%s", self._screen_w, self._screen_h)

        session_stop = threading.Event()
        rx = threading.Thread(target=self._recv_loop, args=(conn, session_stop), name="client-rx", daemon=True)
        hb = threading.Thread(target=self._heartbeat_loop, args=(conn, session_stop), name="client-hb", daemon=True)
        rx.start()
        hb.start()

        try:
            self._ui_loop(screen, clock, conn, session_stop)
        finally:
            session_stop.set()
            conn.close()
            rx.join(timeout=2.0)
            hb.join(timeout=2.0)
            self._conn = None

    def _recv_loop(self, conn: Connection, session_stop: threading.Event) -> None:
        try:
            while not session_stop.is_set() and not self._stop.is_set():
                frame = conn.recv_frame()
                if frame.type == MsgType.FRAME:
                    meta, jpeg = unpack_frame_message(frame.payload)
                    with self._frame_lock:
                        self._latest_jpeg = jpeg
                        self._frame_meta = meta
                elif frame.type == MsgType.HEARTBEAT:
                    continue
                elif frame.type == MsgType.BYE:
                    session_stop.set()
                    break
                else:
                    log.debug("ignore %s", frame.type)
        except (ConnectionError, OSError, ProtocolError):
            session_stop.set()

    def _heartbeat_loop(self, conn: Connection, session_stop: threading.Event) -> None:
        interval = self.config.net.heartbeat_interval_s
        timeout = self.config.net.heartbeat_timeout_s
        while not session_stop.is_set() and not self._stop.is_set():
            try:
                conn.send_heartbeat()
            except (ConnectionError, OSError):
                session_stop.set()
                break
            if conn.is_heartbeat_expired(timeout):
                log.warning("host heartbeat timeout")
                session_stop.set()
                conn.close()
                break
            session_stop.wait(interval)

    def _ui_loop(
        self,
        screen: Any,
        clock: Any,
        conn: Connection,
        session_stop: threading.Event,
    ) -> None:
        pygame = self._pygame
        font = pygame.font.SysFont(None, 22)
        while not session_stop.is_set() and not self._stop.is_set():
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._stop.set()
                    session_stop.set()
                    return
                if event.type == pygame.VIDEORESIZE:
                    self._view_w, self._view_h = max(320, event.w), max(240, event.h)
                    screen = pygame.display.set_mode((self._view_w, self._view_h), pygame.RESIZABLE)
                self._forward_input(conn, event)

            jpeg = None
            meta: dict[str, Any] = {}
            with self._frame_lock:
                if self._latest_jpeg is not None:
                    jpeg = self._latest_jpeg
                    meta = dict(self._frame_meta)
                    self._latest_jpeg = None

            surface = pygame.display.get_surface() or screen
            surface.fill((0, 0, 0))
            if jpeg:
                try:
                    image = decode_jpeg(jpeg)
                    raw = image.tobytes()
                    if hasattr(pygame.image, "frombytes"):
                        surf = pygame.image.frombytes(raw, image.size, "RGB")
                    else:
                        surf = pygame.image.frombuffer(raw, image.size, "RGB")
                    fitted = _fit_surface(pygame, surf, self._view_w, self._view_h)
                    x = (self._view_w - fitted.get_width()) // 2
                    y = (self._view_h - fitted.get_height()) // 2
                    surface.blit(fitted, (x, y))
                    self._blit_rect = (x, y, fitted.get_width(), fitted.get_height())
                except Exception:
                    log.exception("decode/present failed")

            hud = f"seq={meta.get('seq', '-')} q={meta.get('q', '-')} {meta.get('w', '-')}x{meta.get('h', '-')}"
            surface.blit(font.render(hud, True, (180, 255, 180)), (8, 8))
            pygame.display.flip()
            clock.tick(60)

    def _forward_input(self, conn: Connection, event: Any) -> None:
        pygame = self._pygame
        try:
            if event.type == pygame.MOUSEMOTION:
                nx, ny = self._norm_mouse(event.pos)
                if nx is None:
                    return
                conn.send_json(MsgType.MOUSE, {"action": "move", "x": nx, "y": ny})
            elif event.type == pygame.MOUSEBUTTONDOWN:
                nx, ny = self._norm_mouse(event.pos)
                if nx is None:
                    return
                conn.send_json(
                    MsgType.MOUSE,
                    {"action": "down", "x": nx, "y": ny, "button": _mouse_button(event.button)},
                )
            elif event.type == pygame.MOUSEBUTTONUP:
                nx, ny = self._norm_mouse(event.pos)
                if nx is None:
                    return
                conn.send_json(
                    MsgType.MOUSE,
                    {"action": "up", "x": nx, "y": ny, "button": _mouse_button(event.button)},
                )
            elif event.type == pygame.MOUSEWHEEL:
                pos = pygame.mouse.get_pos()
                nx, ny = self._norm_mouse(pos)
                if nx is None:
                    return
                conn.send_json(
                    MsgType.MOUSE,
                    {"action": "scroll", "x": nx, "y": ny, "dx": int(event.x), "dy": int(event.y)},
                )
            elif event.type == pygame.KEYDOWN:
                conn.send_json(
                    MsgType.KEY,
                    {"action": "down", "key": pygame_key_name(event.key, pygame)},
                )
            elif event.type == pygame.KEYUP:
                conn.send_json(
                    MsgType.KEY,
                    {"action": "up", "key": pygame_key_name(event.key, pygame)},
                )
        except (ConnectionError, OSError):
            self._stop.set()

    def _norm_mouse(self, pos: tuple[int, int]) -> tuple[float, float] | tuple[None, None]:
        rect = getattr(self, "_blit_rect", None)
        if not rect:
            return None, None
        x, y, w, h = rect
        px, py = pos
        if w <= 0 or h <= 0 or px < x or py < y or px >= x + w or py >= y + h:
            return None, None
        return (px - x) / w, (py - y) / h


def _fit_surface(pygame: Any, surf: Any, max_w: int, max_h: int) -> Any:
    sw, sh = surf.get_size()
    if sw <= 0 or sh <= 0:
        return surf
    scale = min(max_w / sw, max_h / sh)
    if abs(scale - 1.0) < 0.01:
        return surf
    size = (max(1, int(sw * scale)), max(1, int(sh * scale)))
    return pygame.transform.smoothscale(surf, size)


def _mouse_button(button: int) -> str:
    return {1: "left", 2: "middle", 3: "right"}.get(button, "left")
