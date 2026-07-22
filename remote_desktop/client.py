from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple

from . import PROTOCOL_VERSION
from .clipboard_sync import ClipboardBridge
from .config import ClientConfig
from .i18n import i18n
from .net import Connection, connect_to
from .protocol import MsgType, ProtocolError, decode_json, unpack_frame_message
from .qt_bind import (
    AltModifier,
    ControlModifier,
    FastTransformation,
    Format_RGB32,
    KeepAspectRatio,
    Key_C,
    Key_V,
    MiddleButton,
    MouseFocusReason,
    QApplication,
    QImage,
    QKeyEvent,
    QKeySequence,
    QLabel,
    QMainWindow,
    QMouseEvent,
    QObject,
    QPainter,
    QPixmap,
    QShortcut,
    QTimer,
    QVBoxLayout,
    QWheelEvent,
    QWidget,
    RightButton,
    Signal,
    SmoothPixmapTransform,
    SmoothTransformation,
    StrongFocus,
    WA_NoSystemBackground,
    WA_OpaquePaintEvent,
    WA_TransparentForMouseEvents,
    WindowShortcut,
    black,
    event_pos,
    qt_key_constants,
)

log = logging.getLogger(__name__)
_KEY_CONSTANTS = qt_key_constants()


class FrameBus(QObject):
    frame_jpeg = Signal(object, object)  # bytes, dict — object for PySide2 safety
    status = Signal(str)
    session_ended = Signal(str)
    start_clipboard = Signal()
    stop_clipboard = Signal()
    clipboard_payload = Signal(object)


class RemoteCanvas(QWidget):
    """Keeps last frame and paints in one pass to avoid black-flash flickering."""

    def __init__(self) -> None:
        super().__init__()
        self._source = QPixmap()
        self._scaled = QPixmap()
        self._scaled_for = (0, 0)
        self._blit_rect = (0, 0, 0, 0)
        self.on_mouse: Optional[Callable[[str, float, float, Dict[str, Any]], None]] = None
        self.on_key: Optional[Callable[[str, str], None]] = None
        self.setAttribute(WA_OpaquePaintEvent, True)
        self.setAttribute(WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setMouseTracking(True)
        self.setFocusPolicy(StrongFocus)
        self.setMinimumSize(320, 240)

    def set_image(self, image: QImage) -> None:
        if image.isNull():
            return
        self._source = QPixmap.fromImage(image)
        self._scaled = QPixmap()
        self._scaled_for = (0, 0)
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        w, h = self.width(), self.height()
        if self._source.isNull():
            painter.fillRect(self.rect(), black)
            return

        src_w, src_h = self._source.width(), self._source.height()
        if self._scaled.isNull() or self._scaled_for != (w, h):
            scale = min(float(w) / max(1, src_w), float(h) / max(1, src_h))
            tw = max(1, int(src_w * scale))
            th = max(1, int(src_h * scale))
            if tw == src_w and th == src_h:
                self._scaled = self._source
            elif scale < 1.0:
                # Downscale smoothly for anti-aliasing.
                painter.setRenderHint(SmoothPixmapTransform, True)
                self._scaled = self._source.scaled(tw, th, KeepAspectRatio, SmoothTransformation)
            else:
                # Upscale with nearest-neighbor to keep UI text crisp.
                self._scaled = self._source.scaled(tw, th, KeepAspectRatio, FastTransformation)
            self._scaled_for = (w, h)

        sw, sh = self._scaled.width(), self._scaled.height()
        x = (w - sw) // 2
        y = (h - sh) // 2
        self._blit_rect = (x, y, sw, sh)
        painter.fillRect(self.rect(), black)
        painter.drawPixmap(x, y, self._scaled)

    def _norm(self, px: float, py: float) -> Optional[Tuple[float, float]]:
        x, y, w, h = self._blit_rect
        if w <= 0 or h <= 0:
            return None
        if px < x or py < y or px >= x + w or py >= y + h:
            return None
        return (px - x) / w, (py - y) / h

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._emit_mouse("move", event)
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._emit_mouse("down", event, button=_qt_button(event.button()))
        self.setFocus(MouseFocusReason)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._emit_mouse("up", event, button=_qt_button(event.button()))
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        px, py = event_pos(event)
        norm = self._norm(px, py)
        if norm and self.on_mouse:
            if hasattr(event, "angleDelta"):
                delta = event.angleDelta()
                dy = 1 if delta.y() > 0 else -1 if delta.y() < 0 else 0
                dx = 1 if delta.x() > 0 else -1 if delta.x() < 0 else 0
            else:
                # Very old Qt5 fallback
                delta = int(getattr(event, "delta", lambda: 0)())
                dy = 1 if delta > 0 else -1 if delta < 0 else 0
                dx = 0
            self.on_mouse("scroll", norm[0], norm[1], {"dx": dx, "dy": dy})
        super().wheelEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        # Clipboard hotkeys are handled by the parent window; don't inject them.
        mods = event.modifiers()
        if (mods & ControlModifier) and (mods & AltModifier) and event.key() in {Key_C, Key_V}:
            event.ignore()
            return
        if not event.isAutoRepeat() and self.on_key:
            self.on_key("down", _qt_key_name(event))
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        mods = event.modifiers()
        if (mods & ControlModifier) and (mods & AltModifier) and event.key() in {Key_C, Key_V}:
            event.ignore()
            return
        if not event.isAutoRepeat() and self.on_key:
            self.on_key("up", _qt_key_name(event))
        super().keyReleaseEvent(event)

    def _emit_mouse(self, action: str, event: QMouseEvent, **extra: Any) -> None:
        if not self.on_mouse:
            return
        px, py = event_pos(event)
        norm = self._norm(px, py)
        if norm is None:
            return
        self.on_mouse(action, norm[0], norm[1], extra)


class RemoteClientWindow(QMainWindow):
    def __init__(self, config: ClientConfig, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.config = config
        self._stop = threading.Event()
        self._conn: Optional[Connection] = None
        self._bus = FrameBus()
        self._pending_jpeg: Optional[bytes] = None
        self._pending_meta: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._net_thread: Optional[threading.Thread] = None
        self._hud_tick = 0
        self._last_mouse_move_ts = 0.0
        self._mouse_move_interval_s = 1.0 / 30.0  # throttle move flood
        self._clip: Optional[ClipboardBridge] = None

        self.setWindowTitle(config.window_title)
        self.resize(1280, 720)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.canvas = RemoteCanvas()
        self.canvas.on_mouse = self._handle_mouse
        self.canvas.on_key = self._handle_key
        self.hud = QLabel(self.canvas)
        self.hud.setStyleSheet(
            "QLabel { color: #B8F0C8; background: rgba(0,0,0,120); padding: 4px 8px; }"
        )
        self.hud.setAttribute(WA_TransparentForMouseEvents, True)
        self.hud.move(8, 8)
        layout.addWidget(self.canvas, 1)
        self.setCentralWidget(central)

        self._bus.frame_jpeg.connect(self._on_frame_jpeg)
        self._bus.status.connect(self._on_status)
        self._bus.session_ended.connect(self._on_status)
        self._bus.start_clipboard.connect(self._on_start_clipboard)
        self._bus.stop_clipboard.connect(self._stop_clipboard)
        self._bus.clipboard_payload.connect(self._on_clipboard_payload)

        self._present_timer = QTimer(self)
        self._present_timer.setInterval(16)
        self._present_timer.timeout.connect(self._present_pending)
        self._present_timer.start()

        # Explicit clipboard hotkeys (normal Ctrl+C/V are injected to remote OS).
        self._sc_push = QShortcut(QKeySequence("Ctrl+Alt+C"), self)
        self._sc_push.setContext(WindowShortcut)
        self._sc_push.activated.connect(self._hotkey_push_clipboard)
        self._sc_pull = QShortcut(QKeySequence("Ctrl+Alt+V"), self)
        self._sc_pull.setContext(WindowShortcut)
        self._sc_pull.activated.connect(self._hotkey_pull_clipboard)

    def _hotkey_push_clipboard(self) -> None:
        if self._clip is not None:
            self._clip.push_now()
            self._on_status(i18n.t("clipboard_push"))

    def _hotkey_pull_clipboard(self) -> None:
        if self._clip is not None:
            self._clip.request_remote()
            self._on_status(i18n.t("clipboard_pull"))

    def start(self) -> None:
        self._stop.clear()
        self._net_thread = threading.Thread(target=self._session_loop, name="qt-client-net", daemon=True)
        self._net_thread.start()
        self._bus.status.emit(i18n.t("viewer_connecting"))

    def closeEvent(self, event) -> None:  # noqa: N802
        self._shutdown()
        super().closeEvent(event)

    def _shutdown(self) -> None:
        self._stop.set()
        self._stop_clipboard()
        conn = self._conn
        if conn:
            try:
                conn.send_json(MsgType.BYE, {"reason": "client_close"})
            except Exception:
                pass
            conn.close()
        self._present_timer.stop()

    def _stop_clipboard(self) -> None:
        if self._clip is not None:
            self._clip.stop()
            self._clip.deleteLater()
            self._clip = None

    def _on_status(self, text: str) -> None:
        self.hud.setText(text)
        self.hud.adjustSize()
        self.hud.raise_()

    def _on_frame_jpeg(self, jpeg: object, meta: object) -> None:
        with self._lock:
            self._pending_jpeg = bytes(jpeg) if jpeg is not None else None
            self._pending_meta = dict(meta) if isinstance(meta, dict) else {}

    def _present_pending(self) -> None:
        with self._lock:
            jpeg = self._pending_jpeg
            meta = dict(self._pending_meta)
            self._pending_jpeg = None
        if not jpeg:
            return
        image = QImage.fromData(jpeg, "JPEG")
        if image.isNull():
            return
        if image.format() != Format_RGB32:
            image = image.convertToFormat(Format_RGB32)
        self.canvas.set_image(image)
        self._hud_tick = (self._hud_tick + 1) % 15
        if self._hud_tick == 0:
            self._on_status(
                "seq=%s q=%s %sx%s"
                % (meta.get("seq", "-"), meta.get("q", "-"), meta.get("w", "-"), meta.get("h", "-"))
            )

    def _session_loop(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                self._connect_once()
                backoff = 1.0
            except (ConnectionError, OSError, ProtocolError) as exc:
                log.warning("session error: %s", exc)
                msg = str(exc) or i18n.t("viewer_disconnected")
                self._bus.session_ended.emit(msg)
            except Exception as exc:
                log.exception("client crashed")
                self._bus.session_ended.emit(str(exc))

            if self._stop.is_set() or not self.config.reconnect:
                break
            self._bus.status.emit(i18n.t("viewer_reconnecting", sec="%.0f" % backoff))
            if self._stop.wait(backoff):
                break
            backoff = min(self.config.reconnect_max_s, backoff * 1.7)

    def _connect_once(self) -> None:
        net = self.config.net
        conn = connect_to(net.host, net.port, net.connect_timeout_s, net.recv_buffer)
        self._conn = conn
        conn.send_json(
            MsgType.HELLO,
            {
                "role": "client",
                "version": PROTOCOL_VERSION,
                "password": net.password,
                "quality": {
                    "max_fps": self.config.stream.max_fps,
                    "jpeg_quality": self.config.stream.jpeg_quality,
                    "scale": self.config.stream.scale,
                },
            },
        )
        frame = conn.recv_frame()
        if frame.type != MsgType.HELLO_ACK:
            raise ProtocolError("expected HELLO_ACK")
        ack = decode_json(frame.payload)
        if not ack.get("ok"):
            reason = str(ack.get("reason") or "auth_failed")
            if reason == "auth_failed":
                raise ProtocolError(i18n.t("viewer_auth_failed"))
            raise ProtocolError(reason)

        session_stop = threading.Event()
        self._bus.start_clipboard.emit()
        self._bus.status.emit(i18n.t("clipboard_ready"))

        hb = threading.Thread(
            target=self._heartbeat_loop,
            args=(conn, session_stop),
            name="qt-client-hb",
            daemon=True,
        )
        hb.start()
        try:
            while not self._stop.is_set() and not session_stop.is_set():
                try:
                    fr = conn.recv_frame(stop_event=session_stop)
                except ConnectionError:
                    break
                if fr.type == MsgType.FRAME:
                    meta, jpeg = unpack_frame_message(fr.payload)
                    self._bus.frame_jpeg.emit(jpeg, meta)
                elif fr.type == MsgType.CLIPBOARD:
                    self._bus.clipboard_payload.emit(fr.payload)
                elif fr.type == MsgType.HEARTBEAT:
                    continue
                elif fr.type == MsgType.BYE:
                    break
        finally:
            session_stop.set()
            self._bus.stop_clipboard.emit()
            conn.close()
            if self._conn is conn:
                self._conn = None
            hb.join(timeout=2.0)

    def _on_start_clipboard(self) -> None:
        self._stop_clipboard()

        def send_packet(packet: bytes) -> None:
            c = self._conn
            if c is None or c.closed:
                return
            try:
                c.send_raw(packet)
            except (ConnectionError, OSError):
                self._stop.set()

        self._clip = ClipboardBridge(send_packet=send_packet, parent=self)
        self._clip.status.connect(self._on_status)
        self._clip.start()

    def _on_clipboard_payload(self, payload: object) -> None:
        if self._clip is not None and payload is not None:
            self._clip.handle_remote_payload(bytes(payload))

    def _heartbeat_loop(self, conn: Connection, session_stop: threading.Event) -> None:
        interval = self.config.net.heartbeat_interval_s
        timeout = self.config.net.heartbeat_timeout_s
        while not session_stop.is_set() and not self._stop.is_set():
            # Only send heartbeat when we have been quiet on TX for a while;
            # frames/input already prove the pipe is alive from host side.
            if (time.monotonic() - conn.last_tx) >= interval:
                try:
                    conn.send_heartbeat()
                except (ConnectionError, OSError):
                    session_stop.set()
                    conn.close()
                    break
            if conn.is_heartbeat_expired(timeout):
                log.warning("host idle timeout (%.1fs)", timeout)
                session_stop.set()
                conn.close()
                break
            session_stop.wait(min(1.0, interval))

    def _handle_mouse(self, action: str, x: float, y: float, extra: Dict[str, Any]) -> None:
        conn = self._conn
        if not conn or conn.closed:
            return
        if action == "move":
            now = time.monotonic()
            if (now - self._last_mouse_move_ts) < self._mouse_move_interval_s:
                return
            self._last_mouse_move_ts = now
        payload = {"action": action, "x": x, "y": y}
        payload.update(extra)
        try:
            conn.send_json(MsgType.MOUSE, payload)
        except (ConnectionError, OSError):
            self._stop.set()

    def _handle_key(self, action: str, key: str) -> None:
        conn = self._conn
        if not conn or conn.closed:
            return
        try:
            conn.send_json(MsgType.KEY, {"action": action, "key": key})
        except (ConnectionError, OSError):
            self._stop.set()


def _qt_button(button: Any) -> str:
    if button == RightButton:
        return "right"
    if button == MiddleButton:
        return "middle"
    return "left"


def _qt_key_name(event: QKeyEvent) -> str:
    key = event.key()
    if key in _KEY_CONSTANTS:
        return _KEY_CONSTANTS[key]
    text = event.text()
    if text:
        return text
    name = QKeySequence(key).toString().lower()
    return name or str(key)


class RemoteClient:
    """CLI entry: run Qt viewer as a standalone application."""

    def __init__(self, config: ClientConfig) -> None:
        self.config = config

    def run(self) -> None:
        from .qt_fonts import apply_app_font, ensure_utf8_stdio

        ensure_utf8_stdio()
        app = QApplication.instance() or QApplication([])
        apply_app_font(app)
        win = RemoteClientWindow(self.config)
        win.show()
        win.start()
        # PySide2: exec_(); PySide6: exec()
        fn = getattr(app, "exec_", None) or getattr(app, "exec")
        fn()
