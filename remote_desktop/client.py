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
from .confirm_dialog import (
    ICON_ADD,
    DialogDragBar,
    WindowChromeButton,
    ask_confirm,
    make_frameless_dialog,
    show_warning,
)
from .themes import CURRENT
from .file_transfer import (
    FEATURE_FILE_TRANSFER,
    FileAssembler,
    file_size_over_limit,
    send_file,
)
from .remote_files import RemoteFileBrowser
from .terminal_pty import FEATURE_TERMINAL
from .terminal_view import RemoteTerminalWindow
from .window_chrome import apply_window_chrome, ensure_windows_app_id
from .i18n import i18n
from .net import Connection, connect_to
from .protocol import MsgType, ProtocolError, decode_json, unpack_file_message, unpack_frame_message
from .qt_bind import (
    AltModifier,
    ArrowCursor,
    BlankCursor,
    Antialiasing,
    ApplicationActive,
    ControlModifier,
    ElideRight,
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
    NoPen,
    PointingHandCursor,
    WA_StyledBackground,
    QApplication,
    QColor,
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
    QPen,
    QPixmap,
    QPushButton,
    QShortcut,
    QStackedWidget,
    QTabBar,
    QTimer,
    QVBoxLayout,
    QWheelEvent,
    QWidget,
    RightButton,
    RoundCap,
    Signal,
    SmoothPixmapTransform,
    SmoothTransformation,
    SolidLine,
    StrongFocus,
    TabBarRightSide,
    WA_NoSystemBackground,
    WA_OpaquePaintEvent,
    WA_TransparentForMouseEvents,
    WindowActivate,
    WindowDeactivate,
    WindowShortcut,
    black,
    event_pos,
    qt_enum_eq,
    qt_enum_int,
    qt_has_flag,
    qt_key_constants,
    qt_key_in,
    widget_painter,
)
from .win_input_capture import AltTabCapture

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
        self._remote_cx = 0.5
        self._remote_cy = 0.5
        self._show_remote_cursor = False
        self._host_pointer_passive = False
        self.on_mouse: Optional[Callable[[str, float, float, Dict[str, Any]], None]] = None
        self.on_key: Optional[Callable[[str, str], None]] = None
        # Called before injecting Ctrl+V so local clipboard can be pushed first.
        self.on_before_remote_paste: Optional[Callable[[], None]] = None
        # Local chrome keys (fullscreen); return True to swallow.
        self.on_local_key: Optional[Callable[[QKeyEvent], bool]] = None
        self.host_window: Optional["RemoteClientPage"] = None
        self.setAttribute(WA_OpaquePaintEvent, True)
        self.setAttribute(WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setMouseTracking(True)
        self.setFocusPolicy(StrongFocus)
        self.setMinimumSize(320, 240)
        self.setCursor(ArrowCursor)

    def set_remote_cursor(self, norm_x: float, norm_y: float) -> None:
        self._remote_cx = max(0.0, min(1.0, float(norm_x)))
        self._remote_cy = max(0.0, min(1.0, float(norm_y)))
        self._show_remote_cursor = True
        self.update()

    def set_pointer_passive(self, passive: bool) -> None:
        passive = bool(passive)
        if passive == self._host_pointer_passive:
            return
        self._host_pointer_passive = passive
        self.setCursor(BlankCursor if passive else ArrowCursor)
        self.update()

    def _draw_remote_cursor(self, painter: QPainter) -> None:
        if not self._show_remote_cursor:
            return
        bx, by, bw, bh = self._blit_rect
        if bw <= 0 or bh <= 0:
            return
        px = bx + self._remote_cx * bw
        py = by + self._remote_cy * bh
        painter.setRenderHint(Antialiasing, True)
        outline = QPen(QColor(0, 0, 0, 210))
        outline.setWidthF(2.0)
        painter.setPen(outline)
        painter.setBrush(QColor(255, 255, 255, 230))
        painter.drawEllipse(int(round(px - 5)), int(round(py - 5)), 10, 10)
        painter.drawLine(int(round(px - 10)), int(round(py)), int(round(px + 10)), int(round(py)))
        painter.drawLine(int(round(px)), int(round(py - 10)), int(round(px)), int(round(py + 10)))
        fill = QPen(QColor(255, 80, 80, 240))
        fill.setWidthF(1.5)
        painter.setPen(fill)
        painter.setBrush(QColor(255, 80, 80, 200))
        painter.drawEllipse(int(round(px - 2.5)), int(round(py - 2.5)), 5, 5)

    def focusNextPrevChild(self, _next: bool) -> bool:  # noqa: N802
        # Keep keyboard focus on the canvas so Tab / shortcuts stay remote-bound.
        return False

    def set_image(self, image: QImage) -> None:
        if image.isNull():
            return
        self._source = QPixmap.fromImage(image)
        self._scaled = QPixmap()
        self._scaled_for = (0, 0)
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        with widget_painter(self) as painter:
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
            self._draw_remote_cursor(painter)

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
        win = self.host_window
        if win is not None and win.isFullScreen():
            try:
                self.grabKeyboard()
            except RuntimeError:
                pass
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._emit_mouse("up", event, button=_qt_button(event.button()))
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        px, py = event_pos(event)
        norm = self._norm(px, py)
        if norm and self.on_mouse:
            host = self.host_window
            if host is not None and host.block_mouse_action("scroll"):
                super().wheelEvent(event)
                return
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
        # Clipboard hotkeys: handle here so grabKeyboard() in fullscreen still works.
        mods = event.modifiers()
        if (
            qt_has_flag(mods, ControlModifier)
            and qt_has_flag(mods, AltModifier)
            and qt_key_in(event.key(), Key_C, Key_V)
        ):
            win = self.host_window
            if win is not None and not event.isAutoRepeat():
                if qt_key_in(event.key(), Key_C):
                    win._hotkey_push_clipboard()
                else:
                    win._hotkey_pull_clipboard()
            event.accept()
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
        event.accept()

    def keyReleaseEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        mods = event.modifiers()
        if (
            qt_has_flag(mods, ControlModifier)
            and qt_has_flag(mods, AltModifier)
            and qt_key_in(event.key(), Key_C, Key_V)
        ):
            event.accept()
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
        event.accept()

    def _emit_mouse(self, action: str, event: QMouseEvent, **extra: Any) -> None:
        if not self.on_mouse:
            return
        host = self.host_window
        if host is not None and host.block_mouse_action(action):
            return
        px, py = event_pos(event)
        norm = self._norm(px, py)
        if norm is None:
            return
        self.on_mouse(action, norm[0], norm[1], extra)


class ViewerExitFullscreenButton(QPushButton):
    """Top-center translucent icon control shown only while fullscreen."""

    _W = 44
    _H = 30

    def __init__(
        self,
        parent: QWidget,
        on_exit: Callable[[], None],
        on_hover: Callable[[bool], None],
    ) -> None:
        super().__init__(parent)
        self._on_hover = on_hover
        self.setObjectName("viewerExitFsBtn")
        self.setCursor(PointingHandCursor)
        self.setFocusPolicy(NoFocus)
        self.setFixedSize(self._W, self._H)
        self.setText("")
        self.setToolTip(i18n.t("viewer_exit_fullscreen"))
        self.clicked.connect(on_exit)
        self.hide()

    def enterEvent(self, event) -> None:  # noqa: N802
        self._on_hover(True)
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._on_hover(False)
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _event) -> None:  # noqa: N802
        with widget_painter(self) as painter:
            painter.setRenderHint(Antialiasing, True)
            hovered = bool(self.underMouse())
            bg = QColor(0, 0, 0, 165 if hovered else 105)
            border = QColor(255, 255, 255, 100 if hovered else 60)
            painter.setBrush(bg)
            painter.setPen(border)
            painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 15, 15)

            # Compact "exit fullscreen" glyph: four corner brackets pointing inward.
            ink = QColor(255, 255, 255, 235 if hovered else 210)
            cx = self.width() * 0.5
            cy = self.height() * 0.5
            box = 11.0
            arm = 4.5
            thick = 2.0
            left = cx - box * 0.5
            right = cx + box * 0.5
            top = cy - box * 0.5
            bottom = cy + box * 0.5
            painter.setPen(NoPen)
            painter.setBrush(ink)

            def bar(x: float, y: float, w: float, h: float) -> None:
                painter.drawRoundedRect(x, y, w, h, 0.8, 0.8)

            # top-left
            bar(left, top, arm, thick)
            bar(left, top, thick, arm)
            # top-right
            bar(right - arm, top, arm, thick)
            bar(right - thick, top, thick, arm)
            # bottom-left
            bar(left, bottom - thick, arm, thick)
            bar(left, bottom - arm, thick, arm)
            # bottom-right
            bar(right - arm, bottom - thick, arm, thick)
            bar(right - thick, bottom - arm, thick, arm)


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


class RemoteClientPage(QWidget):
    """One remote-desktop session page (embedded in ViewerShell tabs)."""

    caption_changed = Signal(str)
    session_ack = Signal(object)

    def __init__(
        self,
        config: ClientConfig,
        shell: Optional["ViewerShell"] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self._shell = shell
        self.device_id: Optional[str] = None
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
        self._tab_label = self._short_tab_label(config.window_title)
        self._swallow_esc_up = False
        self._chrome_edge_px = 10
        self._chrome_hover = False
        self._features: Set[str] = set()
        self._file_assembler: Optional[FileAssembler] = None
        self._file_sending = False
        self._file_send_stop = threading.Event()
        self._file_browser: Optional[RemoteFileBrowser] = None
        self._terminal: Optional[RemoteTerminalWindow] = None
        self._pressed_keys: Set[str] = set()
        self._input_armed = True
        self._host_pointer_active = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.canvas = RemoteCanvas()
        self.canvas.host_window = self
        self.canvas.on_mouse = self._handle_mouse
        self.canvas.on_key = self._handle_key
        self.canvas.on_before_remote_paste = self._before_remote_paste
        self.canvas.on_local_key = self._handle_local_key
        layout.addWidget(self.canvas, 1)

        self.chrome_bar = ViewerChromeBar(
            self.canvas,
            on_send_file=self._pick_and_send_file,
            on_browse_files=self._open_remote_files,
            on_terminal=self._open_terminal,
            on_hover=self._on_chrome_hover,
        )
        self._exit_fs_btn = ViewerExitFullscreenButton(
            self.canvas,
            on_exit=lambda: self._set_fullscreen(False),
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

    @staticmethod
    def _short_tab_label(title: str) -> str:
        text = (title or "").strip()
        if " — " in text:
            text = text.split(" — ", 1)[-1].strip()
        elif " - " in text:
            text = text.split(" - ", 1)[-1].strip()
        return text or i18n.t("viewer_tab_unnamed")

    def tab_label(self) -> str:
        return self._tab_label

    def set_display_name(self, name: str) -> None:
        name = (name or "").strip() or self.config.net.host
        self._tab_label = self._short_tab_label(name)
        self._base_title = i18n.t("viewer_title", name=name)
        shell = self._shell
        if shell is not None:
            idx = shell.stack.indexOf(self)
            if idx >= 0:
                shell.tab_bar.setTabText(idx, self._tab_label)
                shell.tab_bar.setTabToolTip(idx, self._base_title)
        self.caption_changed.emit(self._base_title)

    def isFullScreen(self) -> bool:  # noqa: N802 — match QWidget API used below
        shell = self._shell
        return bool(shell is not None and shell.isFullScreen())

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
        shell = self._shell
        if shell is None:
            return
        # Shell owns chrome + keyboard grab for the active tab only.
        shell.set_fullscreen(bool(enabled))

    def on_shell_fullscreen_changed(self, enabled: bool) -> None:
        """Update overlay chrome only; keyboard grab is handled by ViewerShell."""
        self._chrome_hide_timer.stop()
        self._chrome_hover = False
        self.chrome_bar.hide()
        self._exit_fs_btn.hide()
        if enabled and self.isVisible():
            self._show_chrome_bar()
            self._chrome_hide_timer.start(1600)

    def _ensure_canvas_keyboard(self, grab: bool) -> None:
        """Own keyboard input while this page is the active fullscreen target."""
        try:
            if grab:
                self.canvas.setFocus(MouseFocusReason)
                self.canvas.grabKeyboard()
                self._input_armed = True
            else:
                self.canvas.releaseKeyboard()
        except RuntimeError:
            pass

    def arm_remote_input(self, armed: bool) -> None:
        """Gate mouse/key injection; flush sticky keys when leaving the viewer."""
        armed = bool(armed)
        if armed == self._input_armed:
            if armed:
                return
        self._input_armed = armed
        if not armed:
            self.flush_remote_input()

    def flush_remote_input(self) -> None:
        """Release any keys/buttons left down on the remote (Alt+Tab local steal)."""
        conn = self._conn
        stuck = list(self._pressed_keys)
        self._pressed_keys.clear()
        if not conn or conn.closed:
            return
        try:
            for key in stuck:
                conn.send_json(MsgType.KEY, {"action": "up", "key": key})
            # Host also force-releases modifiers / mouse buttons.
            conn.send_json(MsgType.KEY, {"action": "flush"})
            conn.send_json(MsgType.MOUSE, {"action": "flush"})
        except (ConnectionError, OSError):
            self._stop.set()

    def _on_canvas_mouse_y(self, y: float) -> None:
        # Same reveal gesture in windowed and fullscreen modes.
        if y <= self._chrome_edge_px:
            self._show_chrome_bar()
            return
        if self._chrome_hover:
            return
        if self.isFullScreen():
            edge = self._exit_fs_btn.height() + 16
        else:
            edge = self.chrome_bar.height() + 8
        if y > edge:
            self._chrome_hide_timer.start(280)

    def _on_chrome_hover(self, hovering: bool) -> None:
        self._chrome_hover = hovering
        if hovering:
            self._chrome_hide_timer.stop()
            self._show_chrome_bar()
        else:
            self._chrome_hide_timer.start(350)

    def _place_exit_fs_btn(self) -> None:
        self._exit_fs_btn.setToolTip(i18n.t("viewer_exit_fullscreen"))
        bw = int(self._exit_fs_btn._W)
        bh = int(self._exit_fs_btn._H)
        cw = max(1, self.canvas.width())
        self._exit_fs_btn.setGeometry(max(0, (cw - bw) // 2), 8, bw, bh)
        self._exit_fs_btn.raise_()

    def _show_chrome_bar(self) -> None:
        self._chrome_hide_timer.stop()
        # Fullscreen: only the exit icon. Windowed: file/terminal chrome bar.
        if self.isFullScreen():
            self.chrome_bar.hide()
            self._place_exit_fs_btn()
            self._exit_fs_btn.show()
            return

        self._exit_fs_btn.hide()
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
        self._exit_fs_btn.hide()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self.chrome_bar.isVisible() or self._exit_fs_btn.isVisible():
            self._show_chrome_bar()

    def start(self) -> None:
        self._stop.clear()
        self._net_thread = threading.Thread(target=self._session_loop, name="qt-client-net", daemon=True)
        self._net_thread.start()
        self._bus.status.emit(i18n.t("viewer_connecting"))

    def confirm_and_close(self) -> bool:
        """Ask the user, then shut down. Returns False if cancelled."""
        title = self._base_title or self.tab_label()
        if not ask_confirm(
            self.window() or self,
            title=i18n.t("close_viewer_title"),
            message=i18n.t("close_viewer_confirm", title=title),
            eyebrow=i18n.t("brand"),
            ok_text=i18n.t("close_action"),
            cancel_text=i18n.t("keep_open"),
            danger=True,
        ):
            return False
        self.shutdown()
        return True

    def shutdown(self) -> None:
        self._ensure_canvas_keyboard(False)
        self._stop.set()
        self._stop_clipboard()
        if self._terminal is not None:
            try:
                self._terminal.force_close()
            except RuntimeError:
                pass
            self._terminal = None
        if self._file_browser is not None:
            try:
                self._file_browser.close()
            except RuntimeError:
                pass
            self._file_browser = None
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
        text = (text or "").strip()
        caption = "%s — %s" % (self._base_title, text) if text else self._base_title
        self.caption_changed.emit(caption)

    def block_mouse_action(self, action: str) -> bool:
        """True when the host is driving the pointer and this action should not inject."""
        if not self._host_pointer_active:
            return False
        if action == "down":
            self._host_pointer_active = False
            self.canvas.set_pointer_passive(False)
            self._bus.status.emit("")
            return False
        return True

    def _apply_frame_pointer_meta(self, meta: dict[str, Any]) -> None:
        cx = meta.get("cx")
        cy = meta.get("cy")
        if cx is not None and cy is not None:
            try:
                self.canvas.set_remote_cursor(float(cx), float(cy))
            except (TypeError, ValueError):
                pass
        host_ptr = bool(meta.get("host_ptr"))
        if host_ptr != self._host_pointer_active:
            self._host_pointer_active = host_ptr
            self.canvas.set_pointer_passive(host_ptr)
            if host_ptr:
                self._bus.status.emit(i18n.t("viewer_host_pointer"))
            else:
                self._bus.status.emit("")

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
        self._apply_frame_pointer_meta(meta)
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
        self._features = set(str(x) for x in features)
        try:
            self.session_ack.emit(ack)
        except RuntimeError:
            pass
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
        if file_size_over_limit(src.stat().st_size):
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
        if not self._input_armed or self._host_pointer_active:
            return
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
        if not self._input_armed and action != "up":
            return
        conn = self._conn
        if not conn or conn.closed:
            return
        key = (key or "").strip()
        if not key:
            return
        if action == "down":
            self._pressed_keys.add(key)
        elif action == "up":
            self._pressed_keys.discard(key)
        try:
            conn.send_json(MsgType.KEY, {"action": action, "key": key})
        except (ConnectionError, OSError):
            self._stop.set()
            return
        # Alt often released before Tab/` when finishing Alt+Tab / Alt+` — force up.
        if action == "up" and key in {"alt", "alt_l", "alt_r", "cmd", "cmd_l", "cmd_r", "win"}:
            shell = self._shell
            if shell is not None:
                try:
                    shell._alt_tab.force_release_tab()
                except Exception:
                    pass
            if "tab" in self._pressed_keys:
                self._handle_key("up", "tab")
            for grave_name in ("grave", "`", "above_tab"):
                if grave_name in self._pressed_keys:
                    self._handle_key("up", grave_name)


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


class ViewerTabCloseButton(QPushButton):
    """Compact tab close control — soft disc + thin X (not the stock QTabBar glyph)."""

    def __init__(self, tab_bar: QTabBar) -> None:
        super().__init__(tab_bar)
        self._tab_bar = tab_bar
        self.setObjectName("viewerTabCloseBtn")
        self.setFixedSize(16, 16)
        self.setCursor(PointingHandCursor)
        self.setFocusPolicy(NoFocus)
        self.setToolTip(i18n.t("close_action"))
        self.clicked.connect(self._on_clicked)

    def _on_clicked(self) -> None:
        for i in range(self._tab_bar.count()):
            if self._tab_bar.tabButton(i, TabBarRightSide) is self:
                self._tab_bar.tabCloseRequested.emit(i)
                return

    def enterEvent(self, event) -> None:  # noqa: N802
        super().enterEvent(event)
        self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        super().leaveEvent(event)
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        with widget_painter(self) as painter:
            painter.setRenderHint(Antialiasing, True)
            cx = self.width() * 0.5
            cy = self.height() * 0.5
            if self.isDown():
                painter.setPen(NoPen)
                painter.setBrush(QColor(CURRENT.danger))
                painter.drawEllipse(int(round(cx - 7)), int(round(cy - 7)), 14, 14)
                ink = QColor(255, 255, 255)
            elif self.underMouse():
                painter.setPen(NoPen)
                painter.setBrush(QColor(CURRENT.btn_hover))
                painter.drawEllipse(int(round(cx - 7)), int(round(cy - 7)), 14, 14)
                ink = QColor(CURRENT.text)
            else:
                ink = QColor(CURRENT.muted)
            pen = QPen(ink)
            pen.setWidthF(1.2)
            pen.setStyle(SolidLine)
            pen.setCapStyle(RoundCap)
            painter.setPen(pen)
            d = 3.0
            painter.drawLine(
                int(round(cx - d)), int(round(cy - d)), int(round(cx + d)), int(round(cy + d))
            )
            painter.drawLine(
                int(round(cx + d)), int(round(cy - d)), int(round(cx - d)), int(round(cy + d))
            )


class ViewerShell(QMainWindow):
    """Single frameless window; session tabs live in the custom title bar."""

    # Cross-thread marshal from the Win32 keyboard hook into the Qt GUI thread.
    _alt_tab_sig = Signal(str)

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        on_add_remote: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(parent)
        self.force_close = False
        self._on_add_remote = on_add_remote
        self.setObjectName("confirmDialog")
        make_frameless_dialog(self, modal=False, as_window=True)
        self.setWindowTitle(i18n.t("viewer_shell_title"))
        self.resize(1280, 720)
        apply_app_icon(self)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.tab_bar = QTabBar()
        self.tab_bar.setObjectName("viewerTabBar")
        self.tab_bar.setDocumentMode(True)
        self.tab_bar.setExpanding(False)
        self.tab_bar.setDrawBase(False)
        # Custom close buttons via setTabButton (stock QTabBar close glyph is ugly).
        self.tab_bar.setTabsClosable(False)
        self.tab_bar.setMovable(True)
        self.tab_bar.setElideMode(ElideRight)
        self.tab_bar.currentChanged.connect(self._on_current_changed)
        self.tab_bar.tabCloseRequested.connect(self._on_tab_close_requested)
        self.tab_bar.tabMoved.connect(self._on_tab_moved)

        tab_cluster = QWidget()
        tab_cluster.setObjectName("viewerTabCluster")
        cluster_l = QHBoxLayout(tab_cluster)
        cluster_l.setContentsMargins(0, 0, 0, 0)
        cluster_l.setSpacing(2)
        cluster_l.addWidget(self.tab_bar, 0)

        self.btn_add_tab = WindowChromeButton(
            ICON_ADD,
            tab_cluster,
            object_name="viewerAddTabBtn",
            width=24,
            height=22,
        )
        self.btn_add_tab.setToolTip(i18n.t("viewer_show_main"))
        self.btn_add_tab.clicked.connect(self._request_add_remote)
        self.btn_add_tab.setVisible(self._on_add_remote is not None)
        cluster_l.addWidget(self.btn_add_tab, 0)

        self._drag = DialogDragBar(
            self,
            i18n.t("viewer_shell_title"),
            "info",
            False,
            window_controls=True,
            compact=True,
            on_fullscreen=self._toggle_fullscreen,
            content_widget=tab_cluster,
        )
        layout.addWidget(self._drag)

        self.stack = QStackedWidget()
        self.stack.setObjectName("viewerStack")
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self._viewer_active = True
        self._alt_tab_sig.connect(self._on_captured_alt_tab)
        self._alt_tab = AltTabCapture(
            lambda action: self._alt_tab_sig.emit(action),
            is_enabled=self._alt_tab_capture_enabled,
        )
        app = QApplication.instance()
        if app is not None and hasattr(app, "applicationStateChanged"):
            app.applicationStateChanged.connect(self._on_app_state_changed)
        QTimer.singleShot(0, self._sync_alt_tab_hook)

    def set_on_add_remote(self, callback: Optional[Callable[[], None]]) -> None:
        self._on_add_remote = callback
        try:
            self.btn_add_tab.setVisible(callback is not None)
            self.btn_add_tab.setToolTip(i18n.t("viewer_show_main"))
        except RuntimeError:
            pass

    def _request_add_remote(self) -> None:
        if self._on_add_remote is not None:
            self._on_add_remote()

    def _install_tab_close(self, index: int) -> None:
        btn = ViewerTabCloseButton(self.tab_bar)
        self.tab_bar.setTabButton(index, TabBarRightSide, btn)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        apply_window_chrome(self, CURRENT)
        QTimer.singleShot(0, lambda: apply_window_chrome(self, CURRENT))

    def pages(self) -> list[RemoteClientPage]:
        out: list[RemoteClientPage] = []
        for i in range(self.stack.count()):
            page = self.stack.widget(i)
            if isinstance(page, RemoteClientPage):
                out.append(page)
        return out

    def find_page(
        self,
        host: str,
        port: int,
        device_id: Optional[str],
    ) -> Optional[RemoteClientPage]:
        host_key = host.strip().lower()
        port_key = int(port)
        for page in self.pages():
            try:
                win_host = str(page.config.net.host).strip().lower()
                win_port = int(page.config.net.port)
                win_id = getattr(page, "device_id", None)
            except RuntimeError:
                continue
            if device_id and win_id and win_id == device_id:
                return page
            if win_host == host_key and win_port == port_key:
                return page
        return None

    def focus_page(self, page: RemoteClientPage) -> None:
        idx = self.stack.indexOf(page)
        if idx >= 0:
            self.tab_bar.setCurrentIndex(idx)
            self.stack.setCurrentIndex(idx)
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()
        page.canvas.setFocus(MouseFocusReason)

    def add_session(
        self,
        config: ClientConfig,
        device_id: Optional[str] = None,
    ) -> RemoteClientPage:
        page = RemoteClientPage(config, shell=self, parent=self.stack)
        page.device_id = device_id
        page.caption_changed.connect(lambda text, p=page: self._on_page_caption(p, text))
        idx = self.stack.addWidget(page)
        self.tab_bar.insertTab(idx, page.tab_label())
        self.tab_bar.setTabToolTip(idx, config.window_title)
        self._install_tab_close(idx)
        self.tab_bar.setCurrentIndex(idx)
        self.stack.setCurrentIndex(idx)
        page.start()
        self._sync_chrome_title()
        return page

    def _on_page_caption(self, page: RemoteClientPage, caption: str) -> None:
        idx = self.stack.indexOf(page)
        if idx < 0:
            return
        self.tab_bar.setTabToolTip(idx, caption)
        if self.tab_bar.currentIndex() == idx:
            self._sync_chrome_title()

    def _on_current_changed(self, index: int) -> None:
        if index < 0:
            return
        self.stack.setCurrentIndex(index)
        self._sync_chrome_title()
        self._sync_fullscreen_keyboard()
        page = self.stack.widget(index)
        if isinstance(page, RemoteClientPage) and not self.isFullScreen():
            page.canvas.setFocus(MouseFocusReason)

    def _on_tab_moved(self, from_index: int, to_index: int) -> None:
        page = self.stack.widget(from_index)
        if page is None:
            return
        self.stack.blockSignals(True)
        self.stack.removeWidget(page)
        self.stack.insertWidget(to_index, page)
        self.stack.setCurrentIndex(self.tab_bar.currentIndex())
        self.stack.blockSignals(False)

    def _sync_chrome_title(self) -> None:
        idx = self.tab_bar.currentIndex()
        page = self.stack.currentWidget()
        if isinstance(page, RemoteClientPage) and idx >= 0:
            caption = page.tab_label() or self.tab_bar.tabToolTip(idx) or page._base_title
        elif self.stack.count() <= 1:
            caption = i18n.t("viewer_shell_title")
        else:
            caption = "%s (%d)" % (i18n.t("viewer_shell_title"), self.stack.count())
        self.setWindowTitle(caption)

    def _toggle_fullscreen(self) -> None:
        self.set_fullscreen(not self.isFullScreen())

    def set_fullscreen(self, enabled: bool) -> None:
        if enabled:
            self._drag.hide()
            self.showFullScreen()
        else:
            self.showNormal()
            self._drag.show()
        self._drag.sync_fullscreen_btn(bool(enabled))
        for page in self.pages():
            page.on_shell_fullscreen_changed(bool(enabled))
        # Defer grab: showFullScreen() clears focus asynchronously on Windows.
        QTimer.singleShot(0, self._sync_fullscreen_keyboard)
        QTimer.singleShot(50, self._sync_fullscreen_keyboard)

    def _sync_fullscreen_keyboard(self) -> None:
        """Only the active tab may grab the keyboard (avoids multi-tab fights)."""
        active = self.stack.currentWidget()
        for page in self.pages():
            want = bool(self.isFullScreen() and page is active and self._viewer_active)
            page._ensure_canvas_keyboard(want)
        self._sync_alt_tab_hook()

    def _alt_tab_capture_enabled(self) -> bool:
        return bool(
            self._viewer_active
            and self.isVisible()
            and not self.isMinimized()
            and self.isActiveWindow()
        )

    def _sync_alt_tab_hook(self) -> None:
        # Capture Alt+Tab whenever the viewer is the active foreground window so
        # Tab reaches the remote instead of the local task switcher.
        try:
            if self._alt_tab_capture_enabled():
                self._alt_tab.start()
            else:
                self._alt_tab.stop()
        except Exception:
            log.exception("Alt+Tab hook sync failed")

    def _on_captured_alt_tab(self, action: str) -> None:
        page = self.stack.currentWidget()
        if not isinstance(page, RemoteClientPage):
            return
        if action == "down":
            # Ensure Alt is marked down on the remote before Tab arrives.
            if "alt" not in page._pressed_keys:
                page._handle_key("down", "alt")
            # Ignore OS key-repeat; only one Tab-down until matching up.
            if "tab" in page._pressed_keys:
                return
            page._handle_key("down", "tab")
            return
        if "tab" in page._pressed_keys:
            page._handle_key("up", "tab")

    def _set_viewer_active(self, active: bool) -> None:
        active = bool(active)
        if active == self._viewer_active:
            self._sync_alt_tab_hook()
            return
        self._viewer_active = active
        for page in self.pages():
            page.arm_remote_input(active)
        if active:
            QTimer.singleShot(0, self._sync_fullscreen_keyboard)
        else:
            self._alt_tab.stop()
            for page in self.pages():
                page._ensure_canvas_keyboard(False)

    def _on_app_state_changed(self, state) -> None:
        try:
            active = qt_enum_eq(state, ApplicationActive)
        except Exception:
            active = True
        if not active:
            self._set_viewer_active(False)
        elif self.isActiveWindow():
            self._set_viewer_active(True)

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        etype = event.type()
        if qt_enum_eq(etype, WindowDeactivate):
            self._set_viewer_active(False)
        elif qt_enum_eq(etype, WindowActivate):
            self._set_viewer_active(True)

    def _on_tab_close_requested(self, index: int) -> None:
        page = self.stack.widget(index)
        if not isinstance(page, RemoteClientPage):
            self.tab_bar.removeTab(index)
            if page is not None:
                self.stack.removeWidget(page)
            return
        if not page.confirm_and_close():
            return
        self.tab_bar.removeTab(index)
        self.stack.removeWidget(page)
        page.deleteLater()
        if self.stack.count() == 0:
            self.force_close = True
            self.close()
        else:
            self._sync_chrome_title()

    def closeEvent(self, event) -> None:  # noqa: N802
        self._alt_tab.stop()
        pages = self.pages()
        if not self.force_close and pages:
            if len(pages) == 1:
                title = pages[0]._base_title or pages[0].tab_label()
                ok = ask_confirm(
                    self,
                    title=i18n.t("close_viewer_title"),
                    message=i18n.t("close_viewer_confirm", title=title),
                    eyebrow=i18n.t("brand"),
                    ok_text=i18n.t("close_action"),
                    cancel_text=i18n.t("keep_open"),
                    danger=True,
                )
            else:
                ok = ask_confirm(
                    self,
                    title=i18n.t("close_viewer_all_title"),
                    message=i18n.t("close_viewer_all_confirm"),
                    eyebrow=i18n.t("brand"),
                    ok_text=i18n.t("close_action"),
                    cancel_text=i18n.t("keep_open"),
                    danger=True,
                )
            if not ok:
                event.ignore()
                return
        for page in pages:
            page.arm_remote_input(False)
            page._ensure_canvas_keyboard(False)
            page.shutdown()
        super().closeEvent(event)


class RemoteClientWindow(ViewerShell):
    """CLI / compatibility wrapper: one session in the shared tab shell."""

    def __init__(self, config: ClientConfig, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.config = config
        self._page = self.add_session(config, device_id=None)
        self.device_id = None

    def start(self) -> None:
        # Session already started by add_session().
        return


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
        # PySide2: exec_(); PySide6: exec()
        fn = getattr(app, "exec_", None) or getattr(app, "exec")
        fn()
