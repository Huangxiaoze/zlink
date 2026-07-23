"""Qt binding shim: PySide2 first (Ubuntu 18.04), else PySide6."""

from __future__ import annotations

from typing import Any

try:
    from PySide2.QtCore import QEvent, QMimeData, QObject, Qt, QTimer, QUrl, Signal
    from PySide2.QtGui import (
        QBrush,
        QClipboard,
        QColor,
        QFont,
        QFontDatabase,
        QFontMetrics,
        QGuiApplication,
        QIcon,
        QImage,
        QKeyEvent,
        QKeySequence,
        QMouseEvent,
        QPainter,
        QPixmap,
        QWheelEvent,
    )
    from PySide2.QtWidgets import (
        QAbstractButton,
        QAction,
        QApplication,
        QCheckBox,
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QFileDialog,
        QFormLayout,
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QHeaderView,
        QInputDialog,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMenu,
        QMessageBox,
        QPushButton,
        QScrollArea,
        QShortcut,
        QSplitter,
        QStyle,
        QStyledItemDelegate,
        QStyleOptionViewItem,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )

    QT_API = "PySide2"
except ImportError:  # pragma: no cover - modern hosts
    from PySide6.QtCore import QEvent, QMimeData, QObject, Qt, QTimer, QUrl, Signal
    from PySide6.QtGui import (
        QAction,
        QBrush,
        QClipboard,
        QColor,
        QFont,
        QFontDatabase,
        QFontMetrics,
        QGuiApplication,
        QIcon,
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
        QAbstractButton,
        QApplication,
        QCheckBox,
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QFileDialog,
        QFormLayout,
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QHeaderView,
        QInputDialog,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMenu,
        QMessageBox,
        QPushButton,
        QScrollArea,
        QSplitter,
        QStyle,
        QStyledItemDelegate,
        QStyleOptionViewItem,
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
WA_StyledBackground = _enum(
    getattr(Qt, "WA_StyledBackground", None),
    getattr(getattr(Qt, "WidgetAttribute", None), "WA_StyledBackground", None),
)
WA_Hover = _enum(
    getattr(Qt, "WA_Hover", None),
    getattr(getattr(Qt, "WidgetAttribute", None), "WA_Hover", None),
)
HoverEnter = _enum(
    getattr(QEvent, "HoverEnter", None),
    getattr(getattr(QEvent, "Type", None), "HoverEnter", None),
)
HoverLeave = _enum(
    getattr(QEvent, "HoverLeave", None),
    getattr(getattr(QEvent, "Type", None), "HoverLeave", None),
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
AlignCenter = _enum(
    getattr(Qt, "AlignCenter", None),
    getattr(getattr(Qt, "AlignmentFlag", None), "AlignCenter", None),
)
AlignLeft = _enum(
    getattr(Qt, "AlignLeft", None),
    getattr(getattr(Qt, "AlignmentFlag", None), "AlignLeft", None),
)
AlignRight = _enum(
    getattr(Qt, "AlignRight", None),
    getattr(getattr(Qt, "AlignmentFlag", None), "AlignRight", None),
)
AlignTop = _enum(
    getattr(Qt, "AlignTop", None),
    getattr(getattr(Qt, "AlignmentFlag", None), "AlignTop", None),
)
AlignVCenter = _enum(
    getattr(Qt, "AlignVCenter", None),
    getattr(getattr(Qt, "AlignmentFlag", None), "AlignVCenter", None),
)
Fixed = _enum(
    getattr(QHeaderView, "Fixed", None),
    getattr(getattr(QHeaderView, "ResizeMode", None), "Fixed", None),
)
ResizeToContents = _enum(
    getattr(QHeaderView, "ResizeToContents", None),
    getattr(getattr(QHeaderView, "ResizeMode", None), "ResizeToContents", None),
)
AA_DontShowIconsInMenus = _enum(
    getattr(Qt, "AA_DontShowIconsInMenus", None),
    getattr(getattr(Qt, "ApplicationAttribute", None), "AA_DontShowIconsInMenus", None),
)
LeftButton = _enum(
    getattr(Qt, "LeftButton", None),
    getattr(getattr(Qt, "MouseButton", None), "LeftButton", None),
)
RightButton = _enum(
    getattr(Qt, "RightButton", None),
    getattr(getattr(Qt, "MouseButton", None), "RightButton", None),
)
CustomContextMenu = _enum(
    getattr(Qt, "CustomContextMenu", None),
    getattr(getattr(Qt, "ContextMenuPolicy", None), "CustomContextMenu", None),
)
MiddleButton = _enum(
    getattr(Qt, "MiddleButton", None),
    getattr(getattr(Qt, "MouseButton", None), "MiddleButton", None),
)
FramelessWindowHint = _enum(
    getattr(Qt, "FramelessWindowHint", None),
    getattr(getattr(Qt, "WindowType", None), "FramelessWindowHint", None),
)
DialogWindow = _enum(
    getattr(Qt, "Dialog", None),
    getattr(getattr(Qt, "WindowType", None), "Dialog", None),
)
WindowTypeFlag = _enum(
    getattr(Qt, "Window", None),
    getattr(getattr(Qt, "WindowType", None), "Window", None),
)
SmoothPixmapTransform = _enum(
    getattr(QPainter, "SmoothPixmapTransform", None),
    getattr(getattr(QPainter, "RenderHint", None), "SmoothPixmapTransform", None),
)
Antialiasing = _enum(
    getattr(QPainter, "Antialiasing", None),
    getattr(getattr(QPainter, "RenderHint", None), "Antialiasing", None),
)
NoPen = _enum(
    getattr(Qt, "NoPen", None),
    getattr(getattr(Qt, "PenStyle", None), "NoPen", None),
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
No = _enum(
    getattr(QMessageBox, "No", None),
    getattr(getattr(QMessageBox, "StandardButton", None), "No", None),
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
Key_Return = _enum(
    getattr(Qt, "Key_Return", None),
    getattr(getattr(Qt, "Key", None), "Key_Return", None),
)
Key_Enter = _enum(
    getattr(Qt, "Key_Enter", None),
    getattr(getattr(Qt, "Key", None), "Key_Enter", None),
)
Key_Backspace = _enum(
    getattr(Qt, "Key_Backspace", None),
    getattr(getattr(Qt, "Key", None), "Key_Backspace", None),
)
Key_Tab = _enum(
    getattr(Qt, "Key_Tab", None),
    getattr(getattr(Qt, "Key", None), "Key_Tab", None),
)
Key_Delete = _enum(
    getattr(Qt, "Key_Delete", None),
    getattr(getattr(Qt, "Key", None), "Key_Delete", None),
)
Key_Up = _enum(
    getattr(Qt, "Key_Up", None),
    getattr(getattr(Qt, "Key", None), "Key_Up", None),
)
Key_Down = _enum(
    getattr(Qt, "Key_Down", None),
    getattr(getattr(Qt, "Key", None), "Key_Down", None),
)
Key_Left = _enum(
    getattr(Qt, "Key_Left", None),
    getattr(getattr(Qt, "Key", None), "Key_Left", None),
)
Key_Right = _enum(
    getattr(Qt, "Key_Right", None),
    getattr(getattr(Qt, "Key", None), "Key_Right", None),
)
Key_Home = _enum(
    getattr(Qt, "Key_Home", None),
    getattr(getattr(Qt, "Key", None), "Key_Home", None),
)
Key_End = _enum(
    getattr(Qt, "Key_End", None),
    getattr(getattr(Qt, "Key", None), "Key_End", None),
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


def menu_exec(menu: QMenu, position: Any = None) -> Any:
    fn = getattr(menu, "exec_", None) or getattr(menu, "exec")
    if position is None:
        return fn()
    return fn(position)


# Qt5/Qt6 KeyboardModifier bit values (stable across versions).
_MODIFIER_BITS = {
    "NoModifier": 0x00000000,
    "ShiftModifier": 0x02000000,
    "ControlModifier": 0x04000000,
    "AltModifier": 0x08000000,
    "MetaModifier": 0x10000000,
    "KeypadModifier": 0x20000000,
    "GroupSwitchModifier": 0x40000000,
}


def qt_enum_int(value: Any) -> int:
    """PySide2 enums often reject implicit int(); normalize for constructors/compare."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        pass
    for attr in ("value", "_value_", "__enum_value__"):
        raw = getattr(value, attr, None)
        if raw is None or raw is value:
            continue
        try:
            return int(raw)
        except (TypeError, ValueError):
            continue
    try:
        import operator

        return int(operator.index(value))
    except Exception:
        pass
    try:
        return int(getattr(value, "__int__")())
    except Exception as exc:
        raise TypeError("cannot convert %r to int" % (value,)) from exc


def _modifier_bit(flag: Any) -> int:
    """Resolve a single KeyboardModifier member to its bit value."""
    try:
        return qt_enum_int(flag)
    except (TypeError, ValueError):
        pass
    text = str(flag)
    for name, bits in _MODIFIER_BITS.items():
        if text.endswith(name) or text == name:
            return int(bits)
    raise TypeError("cannot convert modifier %r to int" % (flag,))


def qt_enum_eq(left: Any, right: Any) -> bool:
    try:
        return left == right or qt_enum_int(left) == qt_enum_int(right)
    except (TypeError, ValueError):
        return False


def qt_has_flag(flags: Any, flag: Any) -> bool:
    """Safe ``flags & flag`` for PySide2 KeyboardModifier / StateFlag enums."""
    try:
        return bool(qt_enum_int(flags) & _modifier_bit(flag))
    except (TypeError, ValueError):
        pass
    # Some PySide2 builds allow ``|`` / equality but reject ``int()`` / ``&``.
    try:
        return (flags | flag) == flags
    except Exception:
        pass
    try:
        return bool(flags & flag)
    except Exception:
        return False


def qt_key_in(key: Any, *candidates: Any) -> bool:
    for candidate in candidates:
        if qt_enum_eq(key, candidate):
            return True
    return False


def make_window_flags(*flags: Any) -> Any:
    """Combine window flags for ``setWindowFlags`` on PySide2 and PySide6.

    PySide2 often cannot ``|`` WindowType enums directly, and also rejects a plain
    ``int`` — ``setWindowFlags`` expects ``Qt.WindowFlags``.
    """
    value = 0
    for flag in flags:
        value |= qt_enum_int(flag)
    window_flags = getattr(Qt, "WindowFlags", None)
    if window_flags is not None:
        try:
            return window_flags(value)
        except TypeError:
            pass
    try:
        result = flags[0]
        for flag in flags[1:]:
            result = result | flag
        return result
    except TypeError:
        return value


def make_dialog_button_box(*buttons: Any) -> QDialogButtonBox:
    """Create QDialogButtonBox on both PySide2 and PySide6.

    PySide2 rejects ``QDialogButtonBox(Save | Cancel)`` because the OR result is a
    StandardButton enum, not a plain int.

    Standard buttons often get theme icons on Linux (Ubuntu); strip them so the UI
    matches Windows (text-only).
    """
    flags = 0
    for button in buttons:
        flags |= qt_enum_int(button)
    box: QDialogButtonBox
    try:
        box = QDialogButtonBox(flags)
    except TypeError:
        std = getattr(QDialogButtonBox, "StandardButtons", None)
        if std is not None:
            try:
                box = QDialogButtonBox(std(flags))
            except TypeError:
                box = QDialogButtonBox()
                for button in buttons:
                    box.addButton(button)
        else:
            box = QDialogButtonBox()
            for button in buttons:
                box.addButton(button)
    for btn in box.buttons():
        try:
            btn.setIcon(QIcon())
        except Exception:
            pass
    return box


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
