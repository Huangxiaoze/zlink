"""Native window chrome helpers (Windows title bar theme + app icon)."""

from __future__ import annotations

import ctypes
import sys
from typing import Any, Optional

from .app_icon import apply_app_icon
from .qt_bind import (
    ArrowCursor,
    QEvent,
    LeftButton,
    MouseButtonPress,
    MouseButtonRelease,
    MouseMove,
    QObject,
    QPoint,
    QApplication,
    qt_enum_eq,
    qt_has_flag,
)
from .themes import CURRENT, ThemeColors

try:
    from PySide2.QtCore import QAbstractNativeEventFilter, QRect
except ImportError:  # pragma: no cover
    from PySide6.QtCore import QAbstractNativeEventFilter, QRect

try:
    from PySide2.QtGui import QCursor, QRegion, QPainterPath
except ImportError:  # pragma: no cover
    from PySide6.QtGui import QCursor, QRegion, QPainterPath


_APP_ID = "ZLink.RemoteDesktop.App"
_Show = getattr(QEvent, "Show", None) or getattr(getattr(QEvent, "Type", None), "Show", None)
_Resize = getattr(QEvent, "Resize", None) or getattr(getattr(QEvent, "Type", None), "Resize", None)

_WM_NCHITTEST = 0x0084
_HTCLIENT = 1
_HTLEFT = 10
_HTRIGHT = 11
_HTTOP = 12
_HTTOPLEFT = 13
_HTTOPRIGHT = 14
_HTBOTTOM = 15
_HTBOTTOMLEFT = 16
_HTBOTTOMRIGHT = 17

_DWMWA_WINDOW_CORNER_PREFERENCE = 33
_DWMWCP_DONOTROUND = 1
_DWMWCP_ROUNDSMALL = 3

_DEFAULT_CORNER_RADIUS = 10
_DEFAULT_RESIZE_BORDER = 8


class _ChromeEventFilter(QObject):
    """Apply icon + Windows title-bar colors whenever a dialog/window is shown."""

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        try:
            if _Show is not None and qt_enum_eq(event.type(), _Show):
                apply_window_chrome(obj, CURRENT)
        except Exception:
            pass
        return False


def _hex_to_colorref(color: str) -> int:
    """Qt/CSS #RRGGBB -> Windows COLORREF (0x00BBGGRR)."""
    value = color.lstrip("#")
    if len(value) != 6:
        return 0
    r = int(value[0:2], 16)
    g = int(value[2:4], 16)
    b = int(value[4:6], 16)
    return int(r | (g << 8) | (b << 16))


def theme_is_dark(theme: ThemeColors) -> bool:
    value = theme.bg.lstrip("#")
    if len(value) != 6:
        return False
    r = int(value[0:2], 16)
    g = int(value[2:4], 16)
    b = int(value[4:6], 16)
    # Rec. 601 luma threshold.
    return (r * 299 + g * 587 + b * 114) < 140000


def ensure_windows_app_id() -> None:
    """Improve taskbar/title-bar icon behavior when launched via python.exe."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(_APP_ID)
    except Exception:
        pass


def apply_windows_title_bar(window: Any, theme: ThemeColors) -> None:
    """Tint the native Windows 10/11 title bar to follow the active theme."""
    if sys.platform != "win32":
        return
    try:
        hwnd = int(window.winId())
    except Exception:
        return

    dwmapi = ctypes.windll.dwmapi
    dark = ctypes.c_int(1 if theme_is_dark(theme) else 0)
    # 20 = DWMWA_USE_IMMERSIVE_DARK_MODE (Win10 1903+); 19 = older builds.
    for attr in (20, 19):
        try:
            dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(dark), ctypes.sizeof(dark))
            break
        except Exception:
            continue

    # Win11 caption/text colors (ignored on older builds).
    caption = ctypes.c_int(_hex_to_colorref(theme.card if not theme_is_dark(theme) else theme.bg))
    text = ctypes.c_int(_hex_to_colorref(theme.text))
    try:
        dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(caption), ctypes.sizeof(caption))
        dwmapi.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(text), ctypes.sizeof(text))
    except Exception:
        pass


def apply_rounded_corners(window: Any, radius: int = _DEFAULT_CORNER_RADIUS) -> None:
    """Prefer small native rounded corners on Windows 11 frameless windows."""
    if sys.platform != "win32":
        return
    try:
        hwnd = int(window.winId())
    except Exception:
        return
    pref = ctypes.c_int(_DWMWCP_ROUNDSMALL if radius <= 10 else 2)
    try:
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd,
            _DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(pref),
            ctypes.sizeof(pref),
        )
    except Exception:
        pass


def _apply_qt_window_mask(window: Any, radius: int) -> None:
    """Clip non-Windows frameless windows to a rounded rect."""
    if radius <= 0:
        try:
            window.clearMask()
        except Exception:
            pass
        return
    try:
        rect = window.rect()
        path = QPainterPath()
        path.addRoundedRect(float(rect.x()), float(rect.y()), float(rect.width()), float(rect.height()), float(radius), float(radius))
        poly = path.toFillPolygon()
        window.setMask(QRegion(poly.toPolygon()))
    except Exception:
        pass


def _hit_test_edges(x: int, y: int, width: int, height: int, border: int) -> Optional[str]:
    if width <= 0 or height <= 0:
        return None
    on_left = x <= border
    on_right = x >= width - border
    on_top = y <= border
    on_bottom = y >= height - border
    if on_top and on_left:
        return "tl"
    if on_top and on_right:
        return "tr"
    if on_bottom and on_left:
        return "bl"
    if on_bottom and on_right:
        return "br"
    if on_left:
        return "l"
    if on_right:
        return "r"
    if on_top:
        return "t"
    if on_bottom:
        return "b"
    return None


def _edge_to_ht(edge: Optional[str]) -> Optional[int]:
    return {
        "l": _HTLEFT,
        "r": _HTRIGHT,
        "t": _HTTOP,
        "b": _HTBOTTOM,
        "tl": _HTTOPLEFT,
        "tr": _HTTOPRIGHT,
        "bl": _HTBOTTOMLEFT,
        "br": _HTBOTTOMRIGHT,
    }.get(edge or "")


try:
    from PySide2.QtCore import Qt as _Qt
except ImportError:  # pragma: no cover
    from PySide6.QtCore import Qt as _Qt

_SizeHorCursor = getattr(_Qt, "SizeHorCursor", None) or getattr(getattr(_Qt, "CursorShape", _Qt), "SizeHorCursor", None)
_SizeVerCursor = getattr(_Qt, "SizeVerCursor", None) or getattr(getattr(_Qt, "CursorShape", _Qt), "SizeVerCursor", None)
_SizeFDiagCursor = getattr(_Qt, "SizeFDiagCursor", None) or getattr(getattr(_Qt, "CursorShape", _Qt), "SizeFDiagCursor", None)
_SizeBDiagCursor = getattr(_Qt, "SizeBDiagCursor", None) or getattr(getattr(_Qt, "CursorShape", _Qt), "SizeBDiagCursor", None)


def _cursor_for_edge(edge: Optional[str]) -> Any:
    if edge in {"l", "r"} and _SizeHorCursor is not None:
        return QCursor(_SizeHorCursor)
    if edge in {"t", "b"} and _SizeVerCursor is not None:
        return QCursor(_SizeVerCursor)
    if edge in {"tl", "br"} and _SizeFDiagCursor is not None:
        return QCursor(_SizeFDiagCursor)
    if edge in {"tr", "bl"} and _SizeBDiagCursor is not None:
        return QCursor(_SizeBDiagCursor)
    return QCursor(ArrowCursor)


class _WinNativeResizeFilter(QAbstractNativeEventFilter):
    def __init__(self, window: Any, border: int) -> None:
        super().__init__()
        self._window = window
        self._border = int(border)
        self._hwnd = 0
        self._busy = False

    def sync_hwnd(self) -> None:
        try:
            self._hwnd = int(self._window.winId())
        except Exception:
            self._hwnd = 0

    def _client_size(self) -> tuple[int, int]:
        if not self._hwnd:
            return 0, 0
        rect = ctypes.wintypes.RECT()
        if not ctypes.windll.user32.GetClientRect(self._hwnd, ctypes.byref(rect)):
            return 0, 0
        return int(rect.right - rect.left), int(rect.bottom - rect.top)

    def nativeEventFilter(self, event_type: bytes, message: int) -> tuple[bool, int]:  # noqa: N802
        if self._busy or sys.platform != "win32" or event_type != b"windows_generic_MSG":
            return False, 0
        helper = getattr(self._window, "_zlink_frameless_helper", None)
        if helper is None or not helper.resizable:
            return False, 0
        if not self._hwnd:
            return False, 0
        try:
            msg = ctypes.wintypes.MSG.from_address(int(message))
        except Exception:
            return False, 0
        msg_hwnd = int(getattr(msg, "hWnd", None) or getattr(msg, "hwnd", 0) or 0)
        if msg_hwnd != self._hwnd or msg.message != _WM_NCHITTEST:
            return False, 0
        if ctypes.windll.user32.IsZoomed(self._hwnd):
            return False, 0
        self._busy = True
        try:
            gx = ctypes.c_int16(msg.lParam & 0xFFFF).value
            gy = ctypes.c_int16((msg.lParam >> 16) & 0xFFFF).value
            pt = ctypes.wintypes.POINT(gx, gy)
            ctypes.windll.user32.ScreenToClient(self._hwnd, ctypes.byref(pt))
            cw, ch = self._client_size()
            edge = _hit_test_edges(int(pt.x), int(pt.y), cw, ch, self._border)
            ht = _edge_to_ht(edge)
            if ht is not None:
                return True, ht
        except Exception:
            pass
        finally:
            self._busy = False
        return False, 0


class FramelessWindowHelper(QObject):
    """Rounded corners + edge resize for custom-chrome top-level windows."""

    def __init__(
        self,
        window: Any,
        *,
        resizable: bool = True,
        rounded: bool = True,
        radius: int = _DEFAULT_CORNER_RADIUS,
        border: int = _DEFAULT_RESIZE_BORDER,
    ) -> None:
        super().__init__(window)
        self._window = window
        self.resizable = bool(resizable)
        self._rounded = bool(rounded)
        self._radius = int(radius)
        self._border = int(border)
        self._resize_edge: Optional[str] = None
        self._resize_start_pos: Optional[QPoint] = None
        self._resize_start_geom: Optional[QRect] = None
        window.installEventFilter(self)
        if sys.platform == "win32":
            app = QApplication.instance()
            if app is not None:
                filt = _WinNativeResizeFilter(window, self._border)
                app.installNativeEventFilter(filt)
                window._zlink_native_resize = filt

    def set_resizable(self, enabled: bool) -> None:
        self.resizable = bool(enabled)
        if not enabled:
            self._reset_resize_state()

    def set_rounded(self, enabled: bool) -> None:
        self._rounded = bool(enabled)
        self.refresh()

    def _resize_enabled(self) -> bool:
        try:
            return not self._window.isMaximized() and not self._window.isFullScreen()
        except RuntimeError:
            return False

    def refresh(self) -> None:
        native = getattr(self._window, "_zlink_native_resize", None)
        if native is not None and hasattr(native, "sync_hwnd"):
            native.sync_hwnd()
        apply_window_chrome(self._window, CURRENT)
        if self._rounded and self._resize_enabled():
            apply_rounded_corners(self._window, self._radius)
            if sys.platform != "win32":
                _apply_qt_window_mask(self._window, self._radius)
        elif sys.platform != "win32":
            _apply_qt_window_mask(self._window, 0)

    def _reset_resize_state(self) -> None:
        self._resize_edge = None
        self._resize_start_pos = None
        self._resize_start_geom = None
        try:
            self._window.unsetCursor()
        except RuntimeError:
            pass

    def _edge_at(self, pos: QPoint) -> Optional[str]:
        return _hit_test_edges(pos.x(), pos.y(), self._window.width(), self._window.height(), self._border)

    def _begin_resize(self, edge: str, global_pos: QPoint) -> None:
        self._resize_edge = edge
        self._resize_start_pos = QPoint(global_pos)
        self._resize_start_geom = self._window.geometry()

    def _perform_resize(self, global_pos: QPoint) -> None:
        if self._resize_edge is None or self._resize_start_pos is None or self._resize_start_geom is None:
            return
        delta = global_pos - self._resize_start_pos
        geom = self._resize_start_geom
        x, y, w, h = geom.x(), geom.y(), geom.width(), geom.height()
        min_w = max(1, self._window.minimumWidth())
        min_h = max(1, self._window.minimumHeight())
        edge = self._resize_edge
        if "l" in edge:
            nx = x + delta.x()
            nw = w - delta.x()
            if nw < min_w:
                nx = x + (w - min_w)
                nw = min_w
            x, w = nx, nw
        if "r" in edge:
            nw = w + delta.x()
            w = max(min_w, nw)
        if "t" in edge:
            ny = y + delta.y()
            nh = h - delta.y()
            if nh < min_h:
                ny = y + (h - min_h)
                nh = min_h
            y, h = ny, nh
        if "b" in edge:
            nh = h + delta.y()
            h = max(min_h, nh)
        self._window.setGeometry(x, y, w, h)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is not self._window:
            return False
        etype = event.type()
        if _Show is not None and qt_enum_eq(etype, _Show):
            self.refresh()
            return False
        if _Resize is not None and qt_enum_eq(etype, _Resize):
            if self._rounded and sys.platform != "win32" and self._resize_enabled():
                _apply_qt_window_mask(self._window, self._radius)
            return False
        if sys.platform == "win32" or not self.resizable:
            return False
        if not self._resize_enabled():
            self._reset_resize_state()
            return False
        if qt_enum_eq(etype, MouseMove):
            if self._resize_edge is not None:
                try:
                    if qt_has_flag(event.buttons(), LeftButton):
                        self._perform_resize(event.globalPos())
                        return True
                except Exception:
                    pass
            edge = self._edge_at(event.pos())
            self._window.setCursor(_cursor_for_edge(edge))
            return False
        if qt_enum_eq(etype, MouseButtonPress):
            if qt_enum_eq(event.button(), LeftButton):
                edge = self._edge_at(event.pos())
                if edge:
                    self._begin_resize(edge, event.globalPos())
                    event.accept()
                    return True
            return False
        if qt_enum_eq(etype, MouseButtonRelease):
            if self._resize_edge is not None:
                self._reset_resize_state()
                return True
        return False


def apply_window_chrome(window: Any, theme: Optional[ThemeColors] = None) -> None:
    """Apply app icon + native title-bar theming to a top-level window."""
    apply_app_icon(window)
    if theme is not None:
        apply_windows_title_bar(window, theme)
    helper = getattr(window, "_zlink_frameless_helper", None)
    if helper is not None and helper._rounded and helper._resize_enabled():
        apply_rounded_corners(window, helper._radius)


def bind_themed_chrome(window: Any, *, defer_native: bool = False) -> None:
    """Keep title-bar theme in sync for dialogs (applied on every Show)."""
    if getattr(window, "_zlink_chrome_filter", None) is not None:
        return
    filt = _ChromeEventFilter(window)
    window.installEventFilter(filt)
    window._zlink_chrome_filter = filt
    if defer_native:
        return
    # Apply immediately if the native handle already exists.
    try:
        if int(window.winId()) != 0:
            apply_window_chrome(window, CURRENT)
    except Exception:
        pass


def bind_frameless_shell(
    window: Any,
    *,
    resizable: bool = True,
    rounded: bool = True,
    radius: int = _DEFAULT_CORNER_RADIUS,
    border: int = _DEFAULT_RESIZE_BORDER,
) -> FramelessWindowHelper:
    """Attach rounded corners and optional edge resize to a frameless shell window."""
    existing = getattr(window, "_zlink_frameless_helper", None)
    if existing is not None:
        existing.set_resizable(resizable)
        existing.set_rounded(rounded)
        return existing
    helper = FramelessWindowHelper(
        window,
        resizable=resizable,
        rounded=rounded,
        radius=radius,
        border=border,
    )
    window._zlink_frameless_helper = helper
    bind_themed_chrome(window, defer_native=True)
    return helper
