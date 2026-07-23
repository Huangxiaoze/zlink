from __future__ import annotations

import logging
import os
import sys

from .qt_bind import (
    PreferDefaultHinting,
    QFont,
    QGuiApplication,
    SansSerif,
    font_db_families,
    set_font_families,
)

log = logging.getLogger(__name__)

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
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("LANG", os.environ.get("LANG") or "C.UTF-8")
    os.environ.setdefault("LC_ALL", os.environ.get("LC_ALL") or "C.UTF-8")
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def apply_app_font(app: QGuiApplication, point_size: int = 10) -> str:
    available = set(font_db_families())
    chosen = next((name for name in CJK_FAMILIES if name in available), None)
    font = QFont()
    families = [chosen, *CJK_FAMILIES] if chosen else list(CJK_FAMILIES)
    # Drop Nones while preserving order.
    ordered: list[str] = []
    for name in families:
        if name and name not in ordered:
            ordered.append(name)
    set_font_families(font, ordered)
    font.setPointSize(point_size)
    font.setStyleHint(SansSerif)
    if PreferDefaultHinting is not None:
        try:
            font.setHintingPreference(PreferDefaultHinting)
        except Exception:
            pass
    app.setFont(font)
    if chosen:
        log.info("UI font: %s", chosen)
        return chosen
    log.warning(
        "No preferred CJK font found. On Ubuntu 18.04 install: "
        "sudo apt install fonts-noto-cjk  (or fonts-wqy-microhei)"
    )
    return font.family()
