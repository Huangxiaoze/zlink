"""UI themes for LeafLink device manager — every color comes from the palette."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Tuple


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

THEMES: Dict[str, ThemeColors] = {
    LIGHT.id: LIGHT,
    DARK.id: DARK,
    FOREST.id: FOREST,
}

DEFAULT_THEME = LIGHT.id


def theme_ids() -> Tuple[str, ...]:
    return tuple(THEMES.keys())


def resolve_theme(theme_id: str | None) -> ThemeColors:
    if theme_id and theme_id in THEMES:
        return THEMES[theme_id]
    return THEMES[DEFAULT_THEME]


def iter_themes() -> Iterable[ThemeColors]:
    return (THEMES[k] for k in theme_ids())


def build_stylesheet(theme_id: str | None = None) -> str:
    c = resolve_theme(theme_id)
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
QLabel#pageSub, QLabel#pageMuted, QLabel#statusBar {{
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
QLineEdit, QComboBox, QAbstractSpinBox {{
    background: {c.input_bg};
    color: {c.text};
    border: 1px solid {c.input_border};
    border-radius: 8px;
    padding: 8px 10px;
    min-height: 18px;
    selection-background-color: {c.accent};
    selection-color: #FFFFFF;
}}
QComboBox QAbstractItemView {{
    background: {c.card};
    color: {c.text};
    border: 1px solid {c.line};
    selection-background-color: {c.accent};
    selection-color: #FFFFFF;
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
QLabel#cardEmpty {{
    color: {c.muted};
    font-size: 13px;
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
QMessageBox {{
    background: {c.card};
    color: {c.text};
}}
QMessageBox QLabel {{
    color: {c.text};
}}
"""
