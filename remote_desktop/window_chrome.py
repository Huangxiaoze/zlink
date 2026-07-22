"""Native window chrome helpers (Windows title bar theme + app icon)."""

from __future__ import annotations

import ctypes
import sys
from typing import Any, Optional

from .app_icon import apply_app_icon
from .qt_bind import QEvent, QObject, qt_enum_eq
from .themes import CURRENT, ThemeColors


_APP_ID = "LeafLink.RemoteDesktop.App"
_Show = getattr(QEvent, "Show", None) or getattr(getattr(QEvent, "Type", None), "Show", None)


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


def apply_window_chrome(window: Any, theme: Optional[ThemeColors] = None) -> None:
    """Apply app icon + native title-bar theming to a top-level window."""
    apply_app_icon(window)
    if theme is not None:
        apply_windows_title_bar(window, theme)


def bind_themed_chrome(window: Any) -> None:
    """Keep title-bar theme in sync for dialogs (applied on every Show)."""
    if getattr(window, "_leaflink_chrome_filter", None) is not None:
        return
    filt = _ChromeEventFilter(window)
    window.installEventFilter(filt)
    window._leaflink_chrome_filter = filt
    # Apply immediately if the native handle already exists.
    try:
        if int(window.winId()) != 0:
            apply_window_chrome(window, CURRENT)
    except Exception:
        pass
