from __future__ import annotations

import logging
import os
import sys

from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication

log = logging.getLogger(__name__)

# Ordered fallbacks for Chinese glyphs on Ubuntu/Windows/macOS.
CJK_FAMILIES = [
    "Noto Sans CJK SC",
    "Noto Sans CJK JP",
    "Noto Sans CJK",
    "Noto Sans SC",
    "Source Han Sans SC",
    "WenQuanYi Micro Hei",
    "WenQuanYi Zen Hei",
    "Microsoft YaHei UI",
    "Microsoft YaHei",
    "PingFang SC",
    "Hiragino Sans GB",
    "Arial Unicode MS",
    "Sans Serif",
]


def ensure_utf8_stdio() -> None:
    # Helps CLI logs on some Linux locales; GUI text uses Qt fonts.
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("LANG", os.environ.get("LANG") or "C.UTF-8")
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def apply_app_font(app: QGuiApplication, point_size: int = 10) -> str:
    """Pick a CJK-capable UI font and install family fallbacks."""
    available = set(QFontDatabase.families())
    chosen = next((name for name in CJK_FAMILIES if name in available), None)

    font = QFont()
    # Qt will try families in order when glyphs are missing.
    font.setFamilies(CJK_FAMILIES if chosen is None else [chosen, *CJK_FAMILIES])
    font.setPointSize(point_size)
    font.setStyleHint(QFont.StyleHint.SansSerif)
    font.setHintingPreference(QFont.HintingPreference.PreferDefaultHinting)
    app.setFont(font)

    if chosen:
        log.info("UI font: %s", chosen)
        return chosen
    log.warning(
        "No preferred CJK font found. Install fonts-noto-cjk or fonts-wqy-microhei on Ubuntu."
    )
    return font.family()
