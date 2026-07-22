"""UI themes for LeafLink device manager — every color comes from the palette."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Tuple


def _combo_arrow_url(color: str) -> str:
    """Write a themed chevron SVG once and return a Qt-friendly file URL."""
    safe = "".join(ch for ch in color if ch.isalnum())
    cache = Path(tempfile.gettempdir()) / "leaflink_theme"
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / ("combo_arrow_%s.svg" % safe)
    if not path.exists():
        path.write_text(
            (
                '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 12 12">'
                '<path d="M2.2 4.3 L6 8.1 L9.8 4.3" fill="none" stroke="%s" '
                'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>'
                "</svg>"
            )
            % color,
            encoding="utf-8",
        )
    return "file:///" + path.resolve().as_posix()


@dataclass(frozen=True)
class ThemeColors:
    id: str
    # Main / content
    bg: str
    card: str
    text: str
    muted: str
    line: str
    accent: str
    accent_2: str
    danger: str
    danger_hover: str
    warn: str
    online: str
    offline: str
    online_bg: str
    offline_bg: str
    unknown_bg: str
    input_bg: str
    input_border: str
    btn_bg: str
    btn_hover: str
    card_tile: str
    card_tile_hover: str
    card_selected: str
    scroll: str
    # Side rail (always a darker companion panel)
    side: str
    side_2: str
    side_line: str
    side_text: str
    side_muted: str
    side_soft: str
    side_input_bg: str
    side_input_text: str
    side_input_border: str
    side_check: str
    pass_value: str
    host_ok: str
    ghost_bg: str
    ghost_hover: str
    ghost_border: str
    ghost_text: str
    splitter: str


LIGHT = ThemeColors(
    id="light",
    bg="#EEF2F4",
    card="#FFFFFF",
    text="#14212B",
    muted="#6A7A86",
    line="#D5DEE5",
    accent="#0F9D7A",
    accent_2="#0B7F63",
    danger="#D64545",
    danger_hover="#B93737",
    warn="#C48A00",
    online="#0B8F5B",
    offline="#C0392B",
    online_bg="#D8F3E7",
    offline_bg="#F8E0DE",
    unknown_bg="#E8EEF2",
    input_bg="#FFFFFF",
    input_border="#D5DEE5",
    btn_bg="#F4F7F9",
    btn_hover="#E8EEF2",
    card_tile="#F7FAFB",
    card_tile_hover="#EEF7F3",
    card_selected="#E3F5EE",
    scroll="#C5D0D8",
    side="#0F1C24",
    side_2="#162832",
    side_line="#2A3D4A",
    side_text="#F2F7FA",
    side_muted="#8FA3B0",
    side_soft="#D7E4EC",
    side_input_bg="#0C171E",
    side_input_text="#E8F1F5",
    side_input_border="#2A3D4A",
    side_check="#9BB0BD",
    pass_value="#7DFFCE",
    host_ok="#7DFFCE",
    ghost_bg="#21313B",
    ghost_hover="#2A3E4A",
    ghost_border="#314552",
    ghost_text="#E7F0F5",
    splitter="#D5DEE5",
)

DARK = ThemeColors(
    id="dark",
    bg="#10181F",
    card="#182229",
    text="#E8F0F4",
    muted="#9AADB8",
    line="#2C3C48",
    accent="#2BC49A",
    accent_2="#21A682",
    danger="#E05555",
    danger_hover="#C94444",
    warn="#E0B04A",
    online="#3DDC97",
    offline="#FF7A7A",
    online_bg="#1A3A2E",
    offline_bg="#3A2224",
    unknown_bg="#243038",
    input_bg="#121C24",
    input_border="#2C3C48",
    btn_bg="#1C2A34",
    btn_hover="#263846",
    card_tile="#1C2A34",
    card_tile_hover="#243642",
    card_selected="#1A3830",
    scroll="#3A4E5C",
    side="#0B1218",
    side_2="#132029",
    side_line="#2A3B48",
    side_text="#F2F7FA",
    side_muted="#8FA3B0",
    side_soft="#C9D8E2",
    side_input_bg="#0A141B",
    side_input_text="#E8F1F5",
    side_input_border="#2A3B48",
    side_check="#9BB0BD",
    pass_value="#7DFFCE",
    host_ok="#7DFFCE",
    ghost_bg="#1A2A34",
    ghost_hover="#243642",
    ghost_border="#314552",
    ghost_text="#E7F0F5",
    splitter="#2C3C48",
)

FOREST = ThemeColors(
    id="forest",
    bg="#E7F0E9",
    card="#F6FBF7",
    text="#14261B",
    muted="#5C7264",
    line="#C2D4C8",
    accent="#2F8F5B",
    accent_2="#247449",
    danger="#C94B4B",
    danger_hover="#B03F3F",
    warn="#B88420",
    online="#1F8A4C",
    offline="#B33B3B",
    online_bg="#D7EFE0",
    offline_bg="#F5E1E0",
    unknown_bg="#E2EBE5",
    input_bg="#FFFFFF",
    input_border="#C2D4C8",
    btn_bg="#EEF5F0",
    btn_hover="#E0EDE4",
    card_tile="#EEF6F1",
    card_tile_hover="#E4F1E9",
    card_selected="#D7EDE0",
    scroll="#B4C7B9",
    side="#13241C",
    side_2="#1A3226",
    side_line="#2C4638",
    side_text="#F1FFF5",
    side_muted="#9BB5A4",
    side_soft="#D0E4D7",
    side_input_bg="#0F1C16",
    side_input_text="#EAF6EE",
    side_input_border="#2C4638",
    side_check="#A7C0B1",
    pass_value="#8AFFC0",
    host_ok="#8AFFC0",
    ghost_bg="#1E3428",
    ghost_hover="#274433",
    ghost_border="#355544",
    ghost_text="#EAF6EE",
    splitter="#C2D4C8",
)

OCEAN = ThemeColors(
    id="ocean",
    bg="#EAF2F7",
    card="#FFFFFF",
    text="#132836",
    muted="#5E7586",
    line="#C7D7E3",
    accent="#1F7FAF",
    accent_2="#186890",
    danger="#D05050",
    danger_hover="#B74242",
    warn="#C08A1E",
    online="#1A8F6A",
    offline="#C44545",
    online_bg="#D7F0E6",
    offline_bg="#F7E1E1",
    unknown_bg="#E4EDF3",
    input_bg="#FFFFFF",
    input_border="#C7D7E3",
    btn_bg="#EFF5F9",
    btn_hover="#E1EBF2",
    card_tile="#F1F7FB",
    card_tile_hover="#E6F1F8",
    card_selected="#D9ECF7",
    scroll="#B5C8D6",
    side="#102433",
    side_2="#173247",
    side_line="#27485E",
    side_text="#F1F8FC",
    side_muted="#95B0C2",
    side_soft="#C9DCE8",
    side_input_bg="#0C1C28",
    side_input_text="#E7F3FA",
    side_input_border="#27485E",
    side_check="#9CB8C9",
    pass_value="#7ED7FF",
    host_ok="#7ED7FF",
    ghost_bg="#1A3346",
    ghost_hover="#234257",
    ghost_border="#31556C",
    ghost_text="#E7F3FA",
    splitter="#C7D7E3",
)

MIDNIGHT = ThemeColors(
    id="midnight",
    bg="#0D1524",
    card="#152238",
    text="#E6EEF8",
    muted="#9AADC4",
    line="#2A3D58",
    accent="#4C8DFF",
    accent_2="#3A74DB",
    danger="#E25B6A",
    danger_hover="#C94A58",
    warn="#E0B04A",
    online="#3DDC97",
    offline="#FF7A8A",
    online_bg="#17382E",
    offline_bg="#3A2228",
    unknown_bg="#1E2C40",
    input_bg="#101B2D",
    input_border="#2A3D58",
    btn_bg="#1A2A40",
    btn_hover="#233552",
    card_tile="#1A2A40",
    card_tile_hover="#223650",
    card_selected="#1A3050",
    scroll="#3A5070",
    side="#09101C",
    side_2="#121C2E",
    side_line="#243652",
    side_text="#F0F5FC",
    side_muted="#93A7C0",
    side_soft="#C4D2E6",
    side_input_bg="#070E18",
    side_input_text="#E8F0FA",
    side_input_border="#243652",
    side_check="#9BB0C8",
    pass_value="#9EC1FF",
    host_ok="#9EC1FF",
    ghost_bg="#18263C",
    ghost_hover="#223352",
    ghost_border="#314866",
    ghost_text="#E8F0FA",
    splitter="#2A3D58",
)

GRAPHITE = ThemeColors(
    id="graphite",
    bg="#EDEFF1",
    card="#FFFFFF",
    text="#1B1F24",
    muted="#6B737C",
    line="#D2D7DD",
    accent="#4A5562",
    accent_2="#3A4450",
    danger="#C94B4B",
    danger_hover="#B03F3F",
    warn="#B8860B",
    online="#2F8F5B",
    offline="#C0392B",
    online_bg="#DCF0E4",
    offline_bg="#F6E1DF",
    unknown_bg="#E8EBEE",
    input_bg="#FFFFFF",
    input_border="#D2D7DD",
    btn_bg="#F3F5F7",
    btn_hover="#E7EAEE",
    card_tile="#F5F6F8",
    card_tile_hover="#EEEFF2",
    card_selected="#E4E8ED",
    scroll="#B8C0C8",
    side="#1A1E24",
    side_2="#242A32",
    side_line="#3A424C",
    side_text="#F4F6F8",
    side_muted="#A0A8B2",
    side_soft="#D5DAE0",
    side_input_bg="#12151A",
    side_input_text="#EEF1F4",
    side_input_border="#3A424C",
    side_check="#A7AFB8",
    pass_value="#D0D6DE",
    host_ok="#B8F0C8",
    ghost_bg="#2C333C",
    ghost_hover="#3A424C",
    ghost_border="#4A5360",
    ghost_text="#EEF1F4",
    splitter="#D2D7DD",
)

DUSK = ThemeColors(
    id="dusk",
    bg="#1A1412",
    card="#261C19",
    text="#F3E9E2",
    muted="#B5A398",
    line="#43342E",
    accent="#E08A3E",
    accent_2="#C4732E",
    danger="#E05A5A",
    danger_hover="#C84A4A",
    warn="#E0B04A",
    online="#5CBF7A",
    offline="#FF7A7A",
    online_bg="#1F3528",
    offline_bg="#3A2222",
    unknown_bg="#322622",
    input_bg="#1E1714",
    input_border="#43342E",
    btn_bg="#2E221E",
    btn_hover="#3A2C27",
    card_tile="#403028",
    card_tile_hover="#524038",
    card_selected="#4A3424",
    scroll="#5A463E",
    side="#120E0C",
    side_2="#1E1613",
    side_line="#3A2C27",
    side_text="#FAF1EA",
    side_muted="#B5A398",
    side_soft="#E0D0C4",
    side_input_bg="#0E0A09",
    side_input_text="#F3E9E2",
    side_input_border="#3A2C27",
    side_check="#B9A89C",
    pass_value="#FFC48A",
    host_ok="#FFC48A",
    ghost_bg="#2A1F1B",
    ghost_hover="#3A2C27",
    ghost_border="#4A3A33",
    ghost_text="#F3E9E2",
    splitter="#43342E",
)

FROST = ThemeColors(
    id="frost",
    bg="#F2F6FA",
    card="#FFFFFF",
    text="#1A2A36",
    muted="#6A7F90",
    line="#D3DEE8",
    accent="#3A9EAE",
    accent_2="#2F8492",
    danger="#D05050",
    danger_hover="#B74242",
    warn="#C08A1E",
    online="#1F9A6A",
    offline="#C44545",
    online_bg="#D8F2E6",
    offline_bg="#F7E1E1",
    unknown_bg="#E8EFF4",
    input_bg="#FFFFFF",
    input_border="#D3DEE8",
    btn_bg="#F0F5F8",
    btn_hover="#E4ECF2",
    card_tile="#F4F8FB",
    card_tile_hover="#EAF3F6",
    card_selected="#DDF1F4",
    scroll="#B7C7D4",
    side="#143039",
    side_2="#1B3D48",
    side_line="#2D5562",
    side_text="#F2FBFC",
    side_muted="#9BB7C0",
    side_soft="#CDE2E8",
    side_input_bg="#0F262D",
    side_input_text="#EAF7F9",
    side_input_border="#2D5562",
    side_check="#A3BEC7",
    pass_value="#8FE7F0",
    host_ok="#8FE7F0",
    ghost_bg="#1E4450",
    ghost_hover="#285664",
    ghost_border="#366675",
    ghost_text="#EAF7F9",
    splitter="#D3DEE8",
)

AMBER = ThemeColors(
    id="amber",
    bg="#F7F1E8",
    card="#FFFBF5",
    text="#2A2116",
    muted="#7A6A55",
    line="#E2D4BF",
    accent="#C47A12",
    accent_2="#A6650E",
    danger="#C94B4B",
    danger_hover="#B03F3F",
    warn="#B8860B",
    online="#2F8F5B",
    offline="#C0392B",
    online_bg="#DCF0E4",
    offline_bg="#F6E1DF",
    unknown_bg="#EEE6DA",
    input_bg="#FFFFFF",
    input_border="#E2D4BF",
    btn_bg="#F3EADF",
    btn_hover="#E9DDCE",
    card_tile="#F4ECE1",
    card_tile_hover="#EDE2D3",
    card_selected="#F0E0C8",
    scroll="#C9B8A0",
    side="#2A2118",
    side_2="#3A2E22",
    side_line="#534433",
    side_text="#FFF8EE",
    side_muted="#C2B19A",
    side_soft="#E8D9C4",
    side_input_bg="#1E1812",
    side_input_text="#FFF6EB",
    side_input_border="#534433",
    side_check="#C7B59C",
    pass_value="#FFD28A",
    host_ok="#FFD28A",
    ghost_bg="#3F3225",
    ghost_hover="#524233",
    ghost_border="#65533F",
    ghost_text="#FFF6EB",
    splitter="#E2D4BF",
)

THEMES: Dict[str, ThemeColors] = {
    LIGHT.id: LIGHT,
    DARK.id: DARK,
    FOREST.id: FOREST,
    OCEAN.id: OCEAN,
    MIDNIGHT.id: MIDNIGHT,
    GRAPHITE.id: GRAPHITE,
    DUSK.id: DUSK,
    FROST.id: FROST,
    AMBER.id: AMBER,
}

DEFAULT_THEME = LIGHT.id

# Process-wide active palette (updated when the UI theme changes).
CURRENT: ThemeColors = LIGHT


def theme_ids() -> Tuple[str, ...]:
    return tuple(THEMES.keys())


def resolve_theme(theme_id: str | None) -> ThemeColors:
    if theme_id and theme_id in THEMES:
        return THEMES[theme_id]
    return THEMES[DEFAULT_THEME]


def set_current_theme(theme_id: str | None) -> ThemeColors:
    global CURRENT
    CURRENT = resolve_theme(theme_id)
    return CURRENT


def iter_themes() -> Iterable[ThemeColors]:
    return (THEMES[k] for k in theme_ids())


def build_stylesheet(theme_id: str | None = None) -> str:
    c = resolve_theme(theme_id)
    arrow = _combo_arrow_url(c.muted)
    arrow_open = _combo_arrow_url(c.accent)
    return f"""
QMainWindow, QWidget#root {{
    background: {c.bg};
    color: {c.text};
}}
QDialog {{
    background: {c.card};
    color: {c.text};
}}
QLabel {{
    color: {c.text};
}}
QLabel#brand {{
    color: {c.side_text};
    font-size: 22px;
    font-weight: 800;
    letter-spacing: 0.5px;
}}
QLabel#brandTag {{
    color: {c.side_muted};
    font-size: 11px;
}}
QLabel#sectionTitle {{
    color: {c.side_text};
    font-size: 13px;
    font-weight: 700;
}}
QLabel#sideMuted, QLabel#muted {{
    color: {c.side_muted};
    font-size: 12px;
}}
QLabel#sideSoft {{
    color: {c.side_soft};
    font-size: 13px;
    font-weight: 600;
}}
QLabel#sideIp {{
    color: {c.side_soft};
    font-size: 12px;
}}
QLabel#codeValue {{
    color: {c.side_text};
    font-size: 26px;
    font-weight: 800;
    letter-spacing: 1px;
}}
QLabel#passValue {{
    color: {c.pass_value};
    font-size: 22px;
    font-weight: 800;
    letter-spacing: 2px;
}}
QLabel#pageTitle {{
    color: {c.text};
    font-size: 22px;
    font-weight: 800;
}}
QLabel#pageSub, QLabel#pageMuted, QLabel#statusBar, QLabel#cardHint {{
    color: {c.muted};
    font-size: 12px;
}}
QLabel#hostWarn {{
    color: {c.warn};
    font-size: 12px;
    font-weight: 600;
}}
QLabel#hostOk {{
    color: {c.host_ok};
    font-size: 12px;
    font-weight: 600;
}}
QLabel#hostDanger {{
    color: {c.danger};
    font-size: 12px;
    font-weight: 600;
}}
QFrame#side {{
    background: {c.side};
}}
QFrame#infoCard {{
    background: {c.side_2};
    border: 1px solid {c.side_line};
    border-radius: 12px;
}}
QFrame#mainCard {{
    background: {c.card};
    border: 1px solid {c.line};
    border-radius: 14px;
}}
QLineEdit, QAbstractSpinBox {{
    background: {c.input_bg};
    color: {c.text};
    border: 1px solid {c.input_border};
    border-radius: 10px;
    padding: 8px 12px;
    min-height: 18px;
    selection-background-color: {c.accent};
    selection-color: #FFFFFF;
}}
QLineEdit:hover, QAbstractSpinBox:hover {{
    border-color: {c.accent};
}}
QLineEdit:focus, QAbstractSpinBox:focus {{
    border-color: {c.accent};
}}
QComboBox {{
    background: {c.input_bg};
    color: {c.text};
    border: 1px solid {c.input_border};
    border-radius: 10px;
    padding: 8px 34px 8px 12px;
    min-height: 20px;
    font-weight: 600;
    combobox-popup: 0;
}}
QComboBox:hover {{
    border-color: {c.accent};
    background: {c.card_tile_hover};
}}
QComboBox:focus, QComboBox:on {{
    border-color: {c.accent};
}}
QComboBox:disabled {{
    color: {c.muted};
    background: {c.btn_bg};
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 30px;
    border: none;
    background: transparent;
}}
QComboBox::down-arrow {{
    image: url("{arrow}");
    width: 12px;
    height: 12px;
}}
QComboBox:hover::down-arrow, QComboBox:on::down-arrow {{
    image: url("{arrow_open}");
}}
QComboBox QAbstractItemView {{
    background: {c.card};
    color: {c.text};
    border: 1px solid {c.line};
    border-radius: 10px;
    padding: 6px;
    outline: 0;
    selection-background-color: {c.card_selected};
    selection-color: {c.text};
}}
QComboBox QAbstractItemView::item {{
    min-height: 30px;
    padding: 6px 12px;
    border-radius: 8px;
    margin: 1px 0;
}}
QComboBox QAbstractItemView::item:hover {{
    background: {c.card_tile_hover};
    color: {c.text};
}}
QComboBox QAbstractItemView::item:selected {{
    background: {c.card_selected};
    color: {c.text};
}}
QFrame#side QLineEdit {{
    background: {c.side_input_bg};
    color: {c.side_input_text};
    border: 1px solid {c.side_input_border};
}}
QFrame#side QCheckBox {{
    color: {c.side_check};
    spacing: 8px;
}}
QFrame#side QCheckBox::indicator {{
    width: 14px;
    height: 14px;
}}
QPushButton {{
    background: {c.btn_bg};
    color: {c.text};
    border: 1px solid {c.line};
    border-radius: 8px;
    padding: 8px 14px;
    font-weight: 600;
}}
QPushButton:hover {{
    background: {c.btn_hover};
}}
QMenu {{
    background: {c.card};
    color: {c.text};
    border: 1px solid {c.line};
    border-radius: 10px;
    padding: 6px;
}}
QMenu::item {{
    background: transparent;
    padding: 8px 18px;
    border-radius: 8px;
    margin: 1px 0;
}}
QMenu::item:selected {{
    background: {c.card_selected};
    color: {c.text};
}}
QMenu::separator {{
    height: 1px;
    background: {c.line};
    margin: 4px 8px;
}}
QPushButton#primary {{
    background: {c.accent};
    color: #FFFFFF;
    border: none;
    font-weight: 700;
}}
QPushButton#primary:hover {{
    background: {c.accent_2};
}}
QPushButton#danger {{
    background: {c.danger};
    color: #FFFFFF;
    border: none;
    font-weight: 700;
}}
QPushButton#danger:hover {{
    background: {c.danger_hover};
}}
QPushButton#ghostDark {{
    background: {c.ghost_bg};
    color: {c.ghost_text};
    border: 1px solid {c.ghost_border};
}}
QPushButton#ghostDark:hover {{
    background: {c.ghost_hover};
}}
QFrame#deviceCard {{
    background: {c.card_tile};
    border: 1px solid {c.line};
    border-radius: 12px;
}}
QFrame#deviceCard:hover {{
    border-color: {c.accent};
    background: {c.card_tile_hover};
}}
QFrame#deviceCard[selected="true"] {{
    background: {c.card_selected};
    border: 2px solid {c.accent};
}}
QLabel#cardName {{
    color: {c.text};
    font-size: 15px;
    font-weight: 700;
}}
QLabel#cardHost, QLabel#cardMeta {{
    color: {c.muted};
    font-size: 12px;
}}
QLabel#cardMeta {{
    font-size: 11px;
}}
QLabel#cardStatus {{
    font-size: 11px;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 8px;
}}
QWidget#deviceEmptyHost {{
    background: transparent;
}}
QLabel#cardEmpty {{
    color: {c.muted};
    font-size: 14px;
    font-weight: 600;
    qproperty-alignment: AlignCenter;
}}
QScrollArea#deviceScroll, QScrollArea#deviceScroll > QWidget > QWidget {{
    background: transparent;
    border: none;
}}
QSplitter::handle {{
    background: {c.splitter};
    width: 1px;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 4px 2px;
}}
QScrollBar::handle:vertical {{
    background: {c.scroll};
    border-radius: 4px;
    min-height: 30px;
}}
QDialog#confirmDialog {{
    background: {c.card};
    color: {c.text};
    border: 1px solid {c.line};
    border-radius: 14px;
}}
QFrame#dialogTitleBar {{
    background: {c.card};
    border: none;
    border-bottom: 1px solid {c.line};
    border-top-left-radius: 14px;
    border-top-right-radius: 14px;
}}
QLabel#dialogCaption {{
    color: {c.text};
    font-size: 13px;
    font-weight: 700;
}}
QPushButton#dialogClose {{
    background: transparent;
    color: {c.muted};
    border: none;
    border-radius: 8px;
    font-size: 18px;
    font-weight: 700;
    padding: 0;
}}
QPushButton#dialogClose:hover {{
    background: {c.btn_hover};
    color: {c.text};
}}
QLabel#confirmEyebrow {{
    color: {c.muted};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.4px;
}}
QLabel#confirmTitle {{
    color: {c.text};
    font-size: 18px;
    font-weight: 800;
}}
QLabel#confirmMessage {{
    color: {c.muted};
    font-size: 13px;
}}
QLineEdit#confirmInput {{
    background: {c.input_bg};
    color: {c.text};
    border: 1px solid {c.input_border};
    border-radius: 10px;
    padding: 8px 12px;
    min-height: 20px;
    selection-background-color: {c.accent};
    selection-color: #FFFFFF;
}}
QLineEdit#confirmInput:focus {{
    border-color: {c.accent};
}}
QCheckBox#confirmCheck {{
    color: {c.text};
    spacing: 8px;
    font-size: 13px;
    font-weight: 600;
}}
QFrame#confirmFooter {{
    background: transparent;
    border-top: 1px solid {c.line};
}}
QPushButton#confirmCancel {{
    background: {c.btn_bg};
    color: {c.text};
    border: 1px solid {c.line};
    border-radius: 8px;
    padding: 9px 18px;
    font-weight: 600;
    min-width: 96px;
}}
QPushButton#confirmCancel:hover {{
    background: {c.btn_hover};
}}
QPushButton#confirmOk {{
    background: {c.accent};
    color: #FFFFFF;
    border: none;
    border-radius: 8px;
    padding: 9px 18px;
    font-weight: 700;
    min-width: 96px;
}}
QPushButton#confirmOk:hover {{
    background: {c.accent_2};
}}
QPushButton#confirmOk[danger="true"] {{
    background: {c.danger};
}}
QPushButton#confirmOk[danger="true"]:hover {{
    background: {c.danger_hover};
}}
"""
