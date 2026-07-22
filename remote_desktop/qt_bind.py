"""Qt binding shim: PySide2 first (Ubuntu 18.04), else PySide6."""

from __future__ import annotations

from typing import Any

try:
    from PySide2.QtCore import QMimeData, QObject, Qt, QTimer, QUrl, Signal
    from PySide2.QtGui import (
        QBrush,
        QClipboard,
        QColor,
        QFont,
        QFontDatabase,
        QGuiApplication,
        QImage,
        QKeyEvent,
        QKeySequence,
        QMouseEvent,
        QPainter,
        QPixmap,
        QWheelEvent,
    )
    from PySide2.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QFormLayout,
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QHeaderView,
        QInputDialog,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QScrollArea,
        QShortcut,
        QSplitter,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )

    QT_API = "PySide2"
except ImportError:  # pragma: no cover - modern hosts
    from PySide6.QtCore import QMimeData, QObject, Qt, QTimer, QUrl, Signal
    from PySide6.QtGui import (
        QBrush,
        QClipboard,
        QColor,
        QFont,
        QFontDatabase,
        QGuiApplication,
        QImage,
        QKeyEvent,
        QKeySequence,
        QMouseEvent,
        QPainter,
        QPixmap,
        QShortcut,
        QWheelEvent,
    )
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QFormLayout,
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QHeaderView,
        QInputDialog,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QScrollArea,
        QSplitter,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )

    QT_API = "PySide6"


def _enum(*candidates: Any) -> Any:
    for item in candidates:
        if item is not None:
            return item
    raise AttributeError("Qt enum not found: %r" % (candidates,))


# Normalized enums used by UI / client (Qt5 + Qt6).
WA_OpaquePaintEvent = _enum(
    getattr(Qt, "WA_OpaquePaintEvent", None),
    getattr(getattr(Qt, "WidgetAttribute", None), "WA_OpaquePaintEvent", None),
)
WA_NoSystemBackground = _enum(
    getattr(Qt, "WA_NoSystemBackground", None),
    getattr(getattr(Qt, "WidgetAttribute", None), "WA_NoSystemBackground", None),
)
WA_TransparentForMouseEvents = _enum(
    getattr(Qt, "WA_TransparentForMouseEvents", None),
    getattr(getattr(Qt, "WidgetAttribute", None), "WA_TransparentForMouseEvents", None),
)
WA_DeleteOnClose = _enum(
    getattr(Qt, "WA_DeleteOnClose", None),
    getattr(getattr(Qt, "WidgetAttribute", None), "WA_DeleteOnClose", None),
)
StrongFocus = _enum(
    getattr(Qt, "StrongFocus", None),
    getattr(getattr(Qt, "FocusPolicy", None), "StrongFocus", None),
)
NoFocus = _enum(
    getattr(Qt, "NoFocus", None),
    getattr(getattr(Qt, "FocusPolicy", None), "NoFocus", None),
)
MouseFocusReason = _enum(
    getattr(Qt, "MouseFocusReason", None),
    getattr(getattr(Qt, "FocusReason", None), "MouseFocusReason", None),
)
KeepAspectRatio = _enum(
    getattr(Qt, "KeepAspectRatio", None),
    getattr(getattr(Qt, "AspectRatioMode", None), "KeepAspectRatio", None),
)
SmoothTransformation = _enum(
    getattr(Qt, "SmoothTransformation", None),
    getattr(getattr(Qt, "TransformationMode", None), "SmoothTransformation", None),
)
FastTransformation = _enum(
    getattr(Qt, "FastTransformation", None),
    getattr(getattr(Qt, "TransformationMode", None), "FastTransformation", None),
)
black = _enum(getattr(Qt, "black", None), getattr(getattr(Qt, "GlobalColor", None), "black", None))
Horizontal = _enum(
    getattr(Qt, "Horizontal", None),
    getattr(getattr(Qt, "Orientation", None), "Horizontal", None),
)
UserRole = _enum(
    getattr(Qt, "UserRole", None),
    getattr(getattr(Qt, "ItemDataRole", None), "UserRole", None),
)
PointingHandCursor = _enum(
    getattr(Qt, "PointingHandCursor", None),
    getattr(getattr(Qt, "CursorShape", None), "PointingHandCursor", None),
)
AA_DontShowIconsInMenus = _enum(
    getattr(Qt, "AA_DontShowIconsInMenus", None),
    getattr(getattr(Qt, "ApplicationAttribute", None), "AA_DontShowIconsInMenus", None),
)
RightButton = _enum(
    getattr(Qt, "RightButton", None),
    getattr(getattr(Qt, "MouseButton", None), "RightButton", None),
)
MiddleButton = _enum(
    getattr(Qt, "MiddleButton", None),
    getattr(getattr(Qt, "MouseButton", None), "MiddleButton", None),
)
SmoothPixmapTransform = _enum(
    getattr(QPainter, "SmoothPixmapTransform", None),
    getattr(getattr(QPainter, "RenderHint", None), "SmoothPixmapTransform", None),
)
Format_RGB32 = _enum(
    getattr(QImage, "Format_RGB32", None),
    getattr(getattr(QImage, "Format", None), "Format_RGB32", None),
)
Password = _enum(
    getattr(QLineEdit, "Password", None),
    getattr(getattr(QLineEdit, "EchoMode", None), "Password", None),
)
DialogAccepted = _enum(
    getattr(QDialog, "Accepted", None),
    getattr(getattr(QDialog, "DialogCode", None), "Accepted", None),
)
Yes = _enum(
    getattr(QMessageBox, "Yes", None),
    getattr(getattr(QMessageBox, "StandardButton", None), "Yes", None),
)
Save = _enum(
    getattr(QDialogButtonBox, "Save", None),
    getattr(getattr(QDialogButtonBox, "StandardButton", None), "Save", None),
)
Cancel = _enum(
    getattr(QDialogButtonBox, "Cancel", None),
    getattr(getattr(QDialogButtonBox, "StandardButton", None), "Cancel", None),
)
SelectRows = _enum(
    getattr(QTableWidget, "SelectRows", None),
    getattr(getattr(QTableWidget, "SelectionBehavior", None), "SelectRows", None),
)
SingleSelection = _enum(
    getattr(QTableWidget, "SingleSelection", None),
    getattr(getattr(QTableWidget, "SelectionMode", None), "SingleSelection", None),
)
NoEditTriggers = _enum(
    getattr(QTableWidget, "NoEditTriggers", None),
    getattr(getattr(QTableWidget, "EditTrigger", None), "NoEditTriggers", None),
)
Stretch = _enum(
    getattr(QHeaderView, "Stretch", None),
    getattr(getattr(QHeaderView, "ResizeMode", None), "Stretch", None),
)
SansSerif = _enum(
    getattr(QFont, "SansSerif", None),
    getattr(getattr(QFont, "StyleHint", None), "SansSerif", None),
)
PreferDefaultHinting = _enum(
    getattr(QFont, "PreferDefaultHinting", None),
    getattr(getattr(QFont, "HintingPreference", None), "PreferDefaultHinting", None),
)
ControlModifier = _enum(
    getattr(Qt, "ControlModifier", None),
    getattr(getattr(Qt, "KeyboardModifier", None), "ControlModifier", None),
)
AltModifier = _enum(
    getattr(Qt, "AltModifier", None),
    getattr(getattr(Qt, "KeyboardModifier", None), "AltModifier", None),
)
Key_C = _enum(
    getattr(Qt, "Key_C", None),
    getattr(getattr(Qt, "Key", None), "Key_C", None),
)
Key_V = _enum(
    getattr(Qt, "Key_V", None),
    getattr(getattr(Qt, "Key", None), "Key_V", None),
)
Key_A = _enum(
    getattr(Qt, "Key_A", None),
    getattr(getattr(Qt, "Key", None), "Key_A", None),
)
Key_Z = _enum(
    getattr(Qt, "Key_Z", None),
    getattr(getattr(Qt, "Key", None), "Key_Z", None),
)
Key_0 = _enum(
    getattr(Qt, "Key_0", None),
    getattr(getattr(Qt, "Key", None), "Key_0", None),
)
Key_9 = _enum(
    getattr(Qt, "Key_9", None),
    getattr(getattr(Qt, "Key", None), "Key_9", None),
)
WindowShortcut = _enum(
    getattr(Qt, "WindowShortcut", None),
    getattr(getattr(Qt, "ShortcutContext", None), "WindowShortcut", None),
)
Key_F11 = _enum(
    getattr(Qt, "Key_F11", None),
    getattr(getattr(Qt, "Key", None), "Key_F11", None),
)
Key_Escape = _enum(
    getattr(Qt, "Key_Escape", None),
    getattr(getattr(Qt, "Key", None), "Key_Escape", None),
)

KEY_MAP_SRC = [
    ("Key_Return", "enter"),
    ("Key_Enter", "enter"),
    ("Key_Backspace", "backspace"),
    ("Key_Tab", "tab"),
    ("Key_Escape", "esc"),
    ("Key_Space", "space"),
    ("Key_Delete", "delete"),
    ("Key_Insert", "insert"),
    ("Key_Home", "home"),
    ("Key_End", "end"),
    ("Key_PageUp", "pageup"),
    ("Key_PageDown", "pagedown"),
    ("Key_Left", "left"),
    ("Key_Right", "right"),
    ("Key_Up", "up"),
    ("Key_Down", "down"),
    ("Key_Control", "ctrl"),
    ("Key_Shift", "shift"),
    ("Key_Alt", "alt"),
    ("Key_Meta", "cmd"),
    ("Key_F1", "f1"),
    ("Key_F2", "f2"),
    ("Key_F3", "f3"),
    ("Key_F4", "f4"),
    ("Key_F5", "f5"),
    ("Key_F6", "f6"),
    ("Key_F7", "f7"),
    ("Key_F8", "f8"),
    ("Key_F9", "f9"),
    ("Key_F10", "f10"),
    ("Key_F11", "f11"),
    ("Key_F12", "f12"),
]


def qt_key_constants() -> dict[Any, str]:
    key_ns = getattr(Qt, "Key", Qt)
    out: dict[Any, str] = {}
    for attr, name in KEY_MAP_SRC:
        value = getattr(key_ns, attr, None)
        if value is None:
            value = getattr(Qt, attr, None)
        if value is not None:
            out[value] = name
    return out


def event_pos(event: Any) -> tuple[float, float]:
    if hasattr(event, "position"):
        p = event.position()
        return float(p.x()), float(p.y())
    if hasattr(event, "pos"):
        p = event.pos()
        return float(p.x()), float(p.y())
    if hasattr(event, "localPos"):
        p = event.localPos()
        return float(p.x()), float(p.y())
    return 0.0, 0.0


def dialog_exec(dialog: QDialog) -> int:
    fn = getattr(dialog, "exec_", None) or getattr(dialog, "exec")
    return int(fn())


def font_db_families() -> list[str]:
    # Qt5: instance method; Qt6: often static.
    try:
        return list(QFontDatabase.families())
    except TypeError:
        return list(QFontDatabase().families())


def set_font_families(font: QFont, families: list[str]) -> None:
    if hasattr(font, "setFamilies"):
        font.setFamilies(families)
    elif families:
        font.setFamily(families[0])
