from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple, Set

from . import PROTOCOL_VERSION
from .clipboard_sync import ClipboardBridge
from .config import ClientConfig
from .app_icon import apply_app_icon
from .confirm_dialog import DialogDragBar, ask_confirm, make_frameless_dialog, show_warning
from .file_transfer import (
    FEATURE_FILE_TRANSFER,
    FileAssembler,
    MAX_FILE_BYTES,
    send_file,
)
from .remote_files import RemoteFileBrowser
from .terminal_pty import FEATURE_TERMINAL
from .terminal_view import RemoteTerminalWindow
from .themes import CURRENT
from .window_chrome import apply_window_chrome, ensure_windows_app_id
from .i18n import i18n
from .net import Connection, connect_to
from .protocol import MsgType, ProtocolError, decode_json, unpack_file_message, unpack_frame_message
from .qt_bind import (
    AltModifier,
    ControlModifier,
    FastTransformation,
    Format_RGB32,
    KeepAspectRatio,
    Key_0,
    Key_9,
    Key_A,
    Key_C,
    Key_Escape,
    Key_F11,
    Key_V,
    Key_Z,
    MiddleButton,
    MouseFocusReason,
    NoFocus,
    PointingHandCursor,
    WA_StyledBackground,
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QImage,
    QKeyEvent,
    QKeySequence,
    QMainWindow,
    QMouseEvent,
    QObject,
    QPainter,
    QPixmap,
    QPushButton,
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
    qt_enum_int,
    qt_has_flag,
    qt_key_constants,
    qt_key_in,
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
    start_file_xfer = Signal(object)  # features list/tuple
    stop_file_xfer = Signal()
    file_payload = Signal(object)
    file_progress = Signal(str)
    file_list_result = Signal(object)  # meta dict
    file_download_error = Signal(object)  # meta dict
    term_payload = Signal(object)


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
        # Called before injecting Ctrl+V so local clipboard can be pushed first.
        self.on_before_remote_paste: Optional[Callable[[], None]] = None
        # Local chrome keys (fullscreen); return True to swallow.
        self.on_local_key: Optional[Callable[[QKeyEvent], bool]] = None
        self.host_window: Optional["RemoteClientWindow"] = None
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
        if self.host_window is not None:
            _px, py = event_pos(event)
            self.host_window._on_canvas_mouse_y(py)
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
        if (
            qt_has_flag(mods, ControlModifier)
            and qt_has_flag(mods, AltModifier)
            and qt_key_in(event.key(), Key_C, Key_V)
        ):
            event.ignore()
            return
        if self.on_local_key is not None and self.on_local_key(event):
            event.accept()
            return
        # Ctrl+V in viewer = paste on remote: push local clipboard first.
        if (
            not event.isAutoRepeat()
            and qt_has_flag(mods, ControlModifier)
            and not qt_has_flag(mods, AltModifier)
            and qt_key_in(event.key(), Key_V)
            and self.on_before_remote_paste is not None
        ):
            self.on_before_remote_paste()
        if not event.isAutoRepeat() and self.on_key:
            self.on_key("down", _qt_key_name(event))
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        mods = event.modifiers()
        if (
            qt_has_flag(mods, ControlModifier)
            and qt_has_flag(mods, AltModifier)
            and qt_key_in(event.key(), Key_C, Key_V)
        ):
            event.ignore()
            return
        # Keep local chrome keys off the remote OS.
        if qt_key_in(event.key(), Key_F11):
            event.accept()
            return
        win = self.host_window
        if qt_key_in(event.key(), Key_Escape) and win is not None and win._swallow_esc_up:
            win._swallow_esc_up = False
            event.accept()
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


class ViewerChromeBar(QFrame):
    """Top-edge pull-down control: send/browse files + terminal."""

    def __init__(
        self,
        parent: QWidget,
        on_send_file: Callable[[], None],
        on_browse_files: Callable[[], None],
        on_terminal: Callable[[], None],
        on_hover: Callable[[bool], None],
    ) -> None:
        super().__init__(parent)
        self._on_hover = on_hover
        self.setObjectName("viewerChromeBar")
        # Colors come from the app stylesheet (themes.py) so settings theme changes apply.
        self.setAttribute(WA_StyledBackground, True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 12, 6)
        lay.setSpacing(8)

        self.btn_send = QPushButton(i18n.t("viewer_send_file"))
        self.btn_send.setObjectName("viewerChromeBtn")
        self.btn_send.setCursor(PointingHandCursor)
        self.btn_send.setFocusPolicy(NoFocus)
        self.btn_send.clicked.connect(on_send_file)
        lay.addWidget(self.btn_send)

        self.btn_browse = QPushButton(i18n.t("viewer_browse_files"))
        self.btn_browse.setObjectName("viewerChromeBtn")
        self.btn_browse.setCursor(PointingHandCursor)
        self.btn_browse.setFocusPolicy(NoFocus)
        self.btn_browse.clicked.connect(on_browse_files)
        lay.addWidget(self.btn_browse)

        self.btn_term = QPushButton(i18n.t("viewer_terminal"))
        self.btn_term.setObjectName("viewerChromeBtn")
        self.btn_term.setCursor(PointingHandCursor)
        self.btn_term.setFocusPolicy(NoFocus)
        self.btn_term.clicked.connect(on_terminal)
        lay.addWidget(self.btn_term)
        lay.addStretch(1)
        self.hide()

    def enterEvent(self, event) -> None:  # noqa: N802
        self._on_hover(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._on_hover(False)
        super().leaveEvent(event)


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
        self._last_mouse_move_ts = 0.0
        self._mouse_move_interval_s = 1.0 / 30.0  # throttle move flood
        self._clip: Optional[ClipboardBridge] = None
        self._base_title = config.window_title
        self._swallow_esc_up = False
        self._chrome_edge_px = 10
        self._chrome_hover = False
        self._features: Set[str] = set()
        self._file_assembler: Optional[FileAssembler] = None
        self._file_sending = False
        self._file_send_stop = threading.Event()
        self._file_browser: Optional[RemoteFileBrowser] = None
        self._terminal: Optional[RemoteTerminalWindow] = None
        # Set by main window when quitting the whole app (skip confirm once).
        self.force_close = False

        self.setObjectName("confirmDialog")
        make_frameless_dialog(self, modal=False, as_window=True)
        self.setWindowTitle(config.window_title)
        self.resize(1280, 720)
        apply_app_icon(self)

        self._central = QWidget()
        layout = QVBoxLayout(self._central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._drag = DialogDragBar(
            self,
            config.window_title,
            "info",
            False,
            window_controls=True,
            compact=True,
            on_fullscreen=self._toggle_fullscreen,
        )
        layout.addWidget(self._drag)

        self.canvas = RemoteCanvas()
        self.canvas.host_window = self
        self.canvas.on_mouse = self._handle_mouse
        self.canvas.on_key = self._handle_key
        self.canvas.on_before_remote_paste = self._before_remote_paste
        self.canvas.on_local_key = self._handle_local_key
        layout.addWidget(self.canvas, 1)
        self.setCentralWidget(self._central)

        # Overlay the canvas only — never cover the custom title bar.
        self.chrome_bar = ViewerChromeBar(
            self.canvas,
            on_send_file=self._pick_and_send_file,
            on_browse_files=self._open_remote_files,
            on_terminal=self._open_terminal,
            on_hover=self._on_chrome_hover,
        )
        self._chrome_hide_timer = QTimer(self)
        self._chrome_hide_timer.setSingleShot(True)
        self._chrome_hide_timer.timeout.connect(self._hide_chrome_bar)

        self._bus.frame_jpeg.connect(self._on_frame_jpeg)
        self._bus.status.connect(self._on_status)
        self._bus.session_ended.connect(self._on_status)
        self._bus.start_clipboard.connect(self._on_start_clipboard)
        self._bus.stop_clipboard.connect(self._stop_clipboard)
        self._bus.clipboard_payload.connect(self._on_clipboard_payload)
        self._bus.start_file_xfer.connect(self._on_start_file_xfer)
        self._bus.stop_file_xfer.connect(self._on_stop_file_xfer)
        self._bus.file_payload.connect(self._on_file_payload)
        self._bus.file_progress.connect(self._on_status)
        self._bus.file_list_result.connect(self._on_file_list_result)
        self._bus.file_download_error.connect(self._on_file_download_error)
        self._bus.term_payload.connect(self._on_term_payload)

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

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        apply_window_chrome(self, CURRENT)
        # DWM caption tint often sticks only after the native handle is fully mapped.
        QTimer.singleShot(0, lambda: apply_window_chrome(self, CURRENT))

    def _hotkey_push_clipboard(self) -> None:
        if self._clip is not None:
            self._clip.push_now()

    def _hotkey_pull_clipboard(self) -> None:
        if self._clip is not None:
            self._clip.request_remote()

    def _before_remote_paste(self) -> None:
        """Push THIS PC clipboard to remote before injecting Ctrl+V."""
        if self._clip is not None:
            self._clip.push_now()

    def _handle_local_key(self, event: QKeyEvent) -> bool:
        if event.isAutoRepeat():
            return False
        if qt_key_in(event.key(), Key_F11):
            self._toggle_fullscreen()
            return True
        if qt_key_in(event.key(), Key_Escape) and self.isFullScreen():
            self._swallow_esc_up = True
            self._set_fullscreen(False)
            return True
        return False

    def _toggle_fullscreen(self) -> None:
        self._set_fullscreen(not self.isFullScreen())

    def _set_fullscreen(self, enabled: bool) -> None:
        self._hide_chrome_bar()
        if enabled:
            self.showFullScreen()
        else:
            self.showNormal()
        # Keep the caption bar visible so exit-fullscreen stays next to window controls.
        self._drag.show()
        self._drag.sync_fullscreen_btn(enabled)
        self.canvas.setFocus(MouseFocusReason)

    def _on_canvas_mouse_y(self, y: float) -> None:
        # Same reveal gesture in windowed and fullscreen modes.
        if y <= self._chrome_edge_px:
            self._show_chrome_bar()
        elif not self._chrome_hover and y > self.chrome_bar.height() + 8:
            self._chrome_hide_timer.start(280)

    def _on_chrome_hover(self, hovering: bool) -> None:
        self._chrome_hover = hovering
        if hovering:
            self._chrome_hide_timer.stop()
            self._show_chrome_bar()
        else:
            self._chrome_hide_timer.start(350)

    def _show_chrome_bar(self) -> None:
        self._chrome_hide_timer.stop()
        self.chrome_bar.btn_send.setText(i18n.t("viewer_send_file"))
        self.chrome_bar.btn_browse.setText(i18n.t("viewer_browse_files"))
        self.chrome_bar.btn_term.setText(i18n.t("viewer_terminal"))
        can_files = FEATURE_FILE_TRANSFER in self._features and not self._file_sending
        self.chrome_bar.btn_send.setEnabled(can_files)
        self.chrome_bar.btn_browse.setEnabled(can_files)
        self.chrome_bar.btn_term.setEnabled(FEATURE_TERMINAL in self._features)
        w = max(1, self.canvas.width())
        self.chrome_bar.setGeometry(0, 0, w, 40)
        self.chrome_bar.raise_()
        self.chrome_bar.show()

    def _hide_chrome_bar(self) -> None:
        self._chrome_hide_timer.stop()
        self._chrome_hover = False
        self.chrome_bar.hide()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self.chrome_bar.isVisible():
            self._show_chrome_bar()

    def start(self) -> None:
        self._stop.clear()
        self._net_thread = threading.Thread(target=self._session_loop, name="qt-client-net", daemon=True)
        self._net_thread.start()
        self._bus.status.emit(i18n.t("viewer_connecting"))

    def closeEvent(self, event) -> None:  # noqa: N802
        if not self.force_close:
            title = self._base_title or self.windowTitle()
            if not ask_confirm(
                self,
                title=i18n.t("close_viewer_title"),
                message=i18n.t("close_viewer_confirm", title=title),
                eyebrow=i18n.t("brand"),
                ok_text=i18n.t("close_action"),
                cancel_text=i18n.t("keep_open"),
                danger=True,
            ):
                event.ignore()
                return
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
        # Keep connection hints in the window title; no on-canvas HUD.
        text = (text or "").strip()
        caption = "%s — %s" % (self._base_title, text) if text else self._base_title
        self.setWindowTitle(caption)
        try:
            self._drag.lbl_title.setText(caption)
        except RuntimeError:
            pass

    def _on_frame_jpeg(self, jpeg: object, meta: object) -> None:
        with self._lock:
            self._pending_jpeg = bytes(jpeg) if jpeg is not None else None
            self._pending_meta = dict(meta) if isinstance(meta, dict) else {}

    def _present_pending(self) -> None:
        with self._lock:
            jpeg = self._pending_jpeg
            self._pending_jpeg = None
        if not jpeg:
            return
        image = QImage.fromData(jpeg, "JPEG")
        if image.isNull():
            return
        if image.format() != Format_RGB32:
            image = image.convertToFormat(Format_RGB32)
        self.canvas.set_image(image)

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

        features = ack.get("features") or []
        if not isinstance(features, (list, tuple)):
            features = []
        session_stop = threading.Event()
        self._bus.start_clipboard.emit()
        self._bus.start_file_xfer.emit(list(features))
        self._bus.status.emit("")  # connected: clear title suffix

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
                elif fr.type == MsgType.FILE:
                    self._bus.file_payload.emit(fr.payload)
                elif fr.type == MsgType.TERM:
                    self._bus.term_payload.emit(fr.payload)
                elif fr.type == MsgType.HEARTBEAT:
                    continue
                elif fr.type == MsgType.BYE:
                    break
        finally:
            session_stop.set()
            self._bus.stop_file_xfer.emit()
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
        self._clip.start()

    def _on_clipboard_payload(self, payload: object) -> None:
        if self._clip is not None and payload is not None:
            self._clip.handle_remote_payload(bytes(payload))

    def _on_start_file_xfer(self, features: object) -> None:
        self._on_stop_file_xfer()
        feat_list = features if isinstance(features, (list, tuple)) else []
        self._features = {str(x) for x in feat_list}
        self._file_send_stop.clear()
        self._file_assembler = FileAssembler(
            on_progress=self._on_file_recv_progress,
            on_complete=self._on_file_recv_complete,
            on_error=lambda err: self._bus.file_progress.emit(
                i18n.t("file_transfer_failed", error=err)
            ),
        )

    def _on_stop_file_xfer(self) -> None:
        self._file_send_stop.set()
        self._file_sending = False
        self._features = set()
        if self._file_assembler is not None:
            self._file_assembler.clear()
            self._file_assembler = None
        if self._file_browser is not None:
            try:
                self._file_browser.close()
            except RuntimeError:
                pass
            self._file_browser = None
        self._close_terminal()

    def _on_file_payload(self, payload: object) -> None:
        if payload is None:
            return
        raw = bytes(payload)
        try:
            meta, _blob = unpack_file_message(raw)
        except Exception:
            log.exception("bad client file payload")
            return
        op = str(meta.get("op") or "chunk")
        if op in {"list_ok", "list_err"}:
            self._bus.file_list_result.emit(meta)
            return
        if op == "download_err":
            self._bus.file_download_error.emit(meta)
            return
        if self._file_assembler is not None and op == "chunk":
            self._file_assembler.handle_payload(raw)

    def _on_file_list_result(self, meta: object) -> None:
        if self._file_browser is not None and isinstance(meta, dict):
            self._file_browser.handle_list_result(meta)

    def _on_file_download_error(self, meta: object) -> None:
        if self._file_browser is not None and isinstance(meta, dict):
            self._file_browser.handle_download_error(meta)
        elif isinstance(meta, dict):
            self._bus.file_progress.emit(
                i18n.t("file_transfer_failed", error=str(meta.get("error") or "download"))
            )

    def _on_file_recv_progress(self, name: str, received: int, total: int) -> None:
        pct = 100 if total <= 0 else min(100, int(received * 100 / total))
        msg = i18n.t("file_receiving", name=name, pct=pct)
        self._bus.file_progress.emit(msg)
        if self._file_browser is not None:
            self._file_browser.mark_download_progress(name, pct)

    def _on_file_recv_complete(self, path: Path) -> None:
        self._bus.file_progress.emit(i18n.t("file_received", name=path.name))
        self._bus.file_progress.emit(i18n.t("file_saved_to", path=str(path)))
        if self._file_browser is not None:
            self._file_browser.mark_download_done(path)

    def _open_remote_files(self) -> None:
        if FEATURE_FILE_TRANSFER not in self._features:
            show_warning(self, title=i18n.t("tip"), message=i18n.t("file_transfer_unsupported"))
            return
        if self._file_browser is not None:
            try:
                self._file_browser.raise_()
                self._file_browser.activateWindow()
                return
            except RuntimeError:
                self._file_browser = None

        def send_packet(packet: bytes) -> None:
            self._send_file_packet(packet)

        browser = RemoteFileBrowser(self, send_packet=send_packet)
        self._file_browser = browser

        def _clear(_result: int = 0) -> None:
            if self._file_browser is browser:
                self._file_browser = None

        browser.finished.connect(_clear)
        browser.show()

    def _open_terminal(self) -> None:
        if FEATURE_TERMINAL not in self._features:
            show_warning(self, title=i18n.t("tip"), message=i18n.t("terminal_unsupported"))
            return
        if self._terminal is not None:
            try:
                self._terminal.raise_()
                self._terminal.activateWindow()
                return
            except RuntimeError:
                self._terminal = None

        def send_packet(packet: bytes) -> None:
            self._send_file_packet(packet)

        win = RemoteTerminalWindow(self, send_packet=send_packet)
        self._terminal = win

        def _clear(_result: int = 0) -> None:
            if self._terminal is win:
                self._terminal = None

        win.finished.connect(_clear)
        win.show()

    def _close_terminal(self) -> None:
        if self._terminal is None:
            return
        try:
            self._terminal.force_close()
        except RuntimeError:
            pass
        self._terminal = None

    def _on_term_payload(self, payload: object) -> None:
        if self._terminal is not None and payload is not None:
            try:
                self._terminal.handle_term_payload(bytes(payload))
            except Exception:
                log.exception("terminal payload handle failed")

    def _send_file_packet(self, packet: bytes) -> None:
        conn = self._conn
        if conn is None or conn.closed:
            raise ConnectionError("not connected")
        conn.send_raw(packet)

    def has_live_session(self) -> bool:
        conn = self._conn
        return conn is not None and not conn.closed

    def can_send_file(self) -> bool:
        """True when this viewer has a live session that supports FILE transfer."""
        return (
            self.has_live_session()
            and FEATURE_FILE_TRANSFER in self._features
            and not self._file_sending
        )

    def send_local_file(self, path: Path | str) -> bool:
        """Send a local file to the remote host. Returns False if rejected."""
        if FEATURE_FILE_TRANSFER not in self._features:
            show_warning(self, title=i18n.t("tip"), message=i18n.t("file_transfer_unsupported"))
            return False
        if self._file_sending:
            show_warning(self, title=i18n.t("tip"), message=i18n.t("file_transfer_busy"))
            return False
        src = Path(path)
        if not src.is_file():
            return False
        if src.stat().st_size > MAX_FILE_BYTES:
            show_warning(
                self,
                title=i18n.t("tip"),
                message=i18n.t("file_too_large", name=src.name),
            )
            return False

        self._file_sending = True
        self._file_send_stop.clear()
        self.chrome_bar.btn_send.setEnabled(False)
        self._bus.file_progress.emit(i18n.t("file_sending", name=src.name, pct=0))

        def worker() -> None:
            try:
                send_file(
                    src,
                    self._send_file_packet,
                    on_progress=lambda name, done, total: self._bus.file_progress.emit(
                        i18n.t(
                            "file_sending",
                            name=name,
                            pct=(100 if total <= 0 else min(100, int(done * 100 / total))),
                        )
                    ),
                    should_stop=lambda: self._file_send_stop.is_set() or self._stop.is_set(),
                )
                self._bus.file_progress.emit(i18n.t("file_sent", name=src.name))
            except InterruptedError:
                self._bus.file_progress.emit(i18n.t("file_transfer_failed", error="cancelled"))
            except Exception as exc:
                log.exception("send file failed")
                self._bus.file_progress.emit(i18n.t("file_transfer_failed", error=str(exc)))
            finally:
                self._file_sending = False
                # Re-enable button on GUI thread via status update path.
                QTimer.singleShot(0, self._refresh_send_button)

        threading.Thread(target=worker, name="client-file-send", daemon=True).start()
        return True

    def _pick_and_send_file(self) -> None:
        if FEATURE_FILE_TRANSFER not in self._features:
            show_warning(self, title=i18n.t("tip"), message=i18n.t("file_transfer_unsupported"))
            return
        if self._file_sending:
            show_warning(self, title=i18n.t("tip"), message=i18n.t("file_transfer_busy"))
            return
        path, _filter = QFileDialog.getOpenFileName(self, i18n.t("send_file_pick"), str(Path.home()))
        if not path:
            return
        self.send_local_file(path)

    def _refresh_send_button(self) -> None:
        can = FEATURE_FILE_TRANSFER in self._features and not self._file_sending
        self.chrome_bar.btn_send.setEnabled(can and self.has_live_session())
        self.chrome_bar.btn_browse.setEnabled(can and self.has_live_session())

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
    # Under Ctrl/Alt, event.text() is often a control char (e.g. Ctrl+V -> \x16).
    # Prefer physical letter/digit key codes so remote paste/copy actually works.
    try:
        key_i = qt_enum_int(key)
        a_i = qt_enum_int(Key_A)
        z_i = qt_enum_int(Key_Z)
        zero_i = qt_enum_int(Key_0)
        nine_i = qt_enum_int(Key_9)
    except (TypeError, ValueError):
        key_i = a_i = z_i = zero_i = nine_i = None
    if key_i is not None and a_i is not None and z_i is not None and a_i <= key_i <= z_i:
        return chr(ord("a") + (key_i - a_i))
    if key_i is not None and zero_i is not None and nine_i is not None and zero_i <= key_i <= nine_i:
        return chr(ord("0") + (key_i - zero_i))
    text = event.text()
    if text and len(text) == 1 and text.isprintable():
        return text
    try:
        name = QKeySequence(qt_enum_int(key) if key_i is None else key_i).toString().lower()
    except Exception:
        name = QKeySequence(key).toString().lower()
    # Strip accidental modifier prefixes from QKeySequence.
    if name.startswith("ctrl+") or name.startswith("alt+") or name.startswith("shift+"):
        name = name.split("+")[-1]
    return name or str(key)


class RemoteClient:
    """CLI entry: run Qt viewer as a standalone application."""

    def __init__(self, config: ClientConfig) -> None:
        self.config = config

    def run(self) -> None:
        from .qt_fonts import apply_app_font, ensure_utf8_stdio

        ensure_utf8_stdio()
        ensure_windows_app_id()
        app = QApplication.instance() or QApplication([])
        apply_app_font(app)
        apply_app_icon(app)
        win = RemoteClientWindow(self.config)
        win.show()
        apply_window_chrome(win, CURRENT)
        win.start()
        # PySide2: exec_(); PySide6: exec()
        fn = getattr(app, "exec_", None) or getattr(app, "exec")
        fn()
