"""Resolve and load the ZLink application icon (dev + frozen builds)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable, Optional

from .qt_bind import KeepAspectRatio, QIcon, QPixmap, SmoothTransformation

_ICON: Optional[QIcon] = None
_PNG_NAME = "app.png"
_ICO_NAME = "app.ico"


def _candidate_dirs() -> Iterable[Path]:
    here = Path(__file__).resolve().parent
    seen: set[Path] = set()

    # Dev layout: repo root contains main.py and resources/icon (e.g. remote/zlink/ui/…).
    for base in (here, *here.parents):
        icon_dir = base / "resources" / "icon"
        if icon_dir.is_dir():
            resolved = icon_dir.resolve()
            if resolved not in seen:
                seen.add(resolved)
                yield icon_dir
        if (base / "main.py").is_file():
            break

    legacy = here / "resources" / "icon"
    if legacy.is_dir() and legacy.resolve() not in seen:
        yield legacy

    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        exe_dir = Path(sys.executable).resolve().parent
        yield meipass / "resources" / "icon"
        yield exe_dir / "resources" / "icon"
        yield exe_dir / "_internal" / "resources" / "icon"


def icon_png_path() -> Optional[Path]:
    for folder in _candidate_dirs():
        path = folder / _PNG_NAME
        if path.is_file():
            return path
    return None


def icon_ico_path() -> Optional[Path]:
    for folder in _candidate_dirs():
        path = folder / _ICO_NAME
        if path.is_file():
            return path
    return None


def load_app_icon() -> QIcon:
    global _ICON
    if _ICON is not None and not _ICON.isNull():
        return _ICON

    icon = QIcon()
    # Prefer .ico on Windows title bars / taskbar; PNG as fallback / HiDPI source.
    ico = icon_ico_path()
    if ico is not None:
        icon.addFile(str(ico))
    png = icon_png_path()
    if png is not None:
        pix = QPixmap(str(png))
        if not pix.isNull():
            for size in (16, 20, 24, 32, 40, 48, 64, 128, 256):
                icon.addPixmap(
                    pix.scaled(size, size, KeepAspectRatio, SmoothTransformation)
                )

    _ICON = icon
    return icon


def apply_app_icon(target) -> None:
    """Set window/application icon when available."""
    icon = load_app_icon()
    if icon.isNull():
        return
    setter = getattr(target, "setWindowIcon", None)
    if callable(setter):
        setter(icon)
