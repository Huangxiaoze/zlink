"""UI themes for ZLink device manager — every color comes from the palette."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Tuple


def _combo_arrow_url(color: str) -> str:
    """Write a themed chevron SVG once and return a Qt-friendly file URL."""
    safe = "".join(ch for ch in color if ch.isalnum())
    cache = Path(tempfile.gettempdir()) / "zlink_theme"
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


def _hex_to_rgb(color: str) -> Tuple[int, int, int]:
    value = color.lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _rgba(color: str, alpha: float) -> str:
    r, g, b = _hex_to_rgb(color)
    a = max(0.0, min(1.0, float(alpha)))
    return "rgba(%d, %d, %d, %d)" % (r, g, b, int(round(a * 255)))


def _shade(color: str, factor: float) -> str:
    """Darken (factor < 1) or lighten (factor > 1) a #RRGGBB color."""
    r, g, b = _hex_to_rgb(color)
    factor = float(factor)
    if factor < 1.0:
        r = max(0, min(255, int(round(r * factor))))
        g = max(0, min(255, int(round(g * factor))))
        b = max(0, min(255, int(round(b * factor))))
    else:
        t = factor - 1.0
        r = max(0, min(255, int(round(r + (255 - r) * t))))
        g = max(0, min(255, int(round(g + (255 - g) * t))))
        b = max(0, min(255, int(round(b + (255 - b) * t))))
    return "#%02X%02X%02X" % (r, g, b)


def _contrast_text(bg: str, light: str = "#FFFFFF", dark: str = "#14212B") -> str:
    """Pick readable text for a solid accent/button background (YIQ)."""
    r, g, b = _hex_to_rgb(bg)
    yiq = (r * 299 + g * 587 + b * 114) / 1000.0
    return dark if yiq >= 160 else light


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

SAKURA = ThemeColors(
    id="sakura",
    bg="#FBF3F5",
    card="#FFFFFF",
    text="#3A2430",
    muted="#8B6B78",
    line="#EBD5DC",
    accent="#D46A8C",
    accent_2="#B85574",
    danger="#D64545",
    danger_hover="#B93737",
    warn="#C48A00",
    online="#2F9B6A",
    offline="#C0392B",
    online_bg="#DDF3E8",
    offline_bg="#F8E0DE",
    unknown_bg="#F3E8EC",
    input_bg="#FFFFFF",
    input_border="#EBD5DC",
    btn_bg="#F8EEF1",
    btn_hover="#F0E0E6",
    card_tile="#F8F0F3",
    card_tile_hover="#F3E6EB",
    card_selected="#F5DCE6",
    scroll="#D4B8C2",
    side="#2A1820",
    side_2="#3A2230",
    side_line="#553644",
    side_text="#FFF5F8",
    side_muted="#C9A8B4",
    side_soft="#EED8E0",
    side_input_bg="#20141A",
    side_input_text="#FFEAF1",
    side_input_border="#553644",
    side_check="#CDB0BB",
    pass_value="#FFB7CF",
    host_ok="#FFB7CF",
    ghost_bg="#3F2834",
    ghost_hover="#523748",
    ghost_border="#664458",
    ghost_text="#FFEAF1",
    splitter="#EBD5DC",
)

CORAL = ThemeColors(
    id="coral",
    bg="#FBF1ED",
    card="#FFF9F7",
    text="#3A241C",
    muted="#8A6A5C",
    line="#E8D0C6",
    accent="#E06B4E",
    accent_2="#C4573D",
    danger="#D04545",
    danger_hover="#B53737",
    warn="#C48A00",
    online="#2F9B6A",
    offline="#C0392B",
    online_bg="#DDF3E8",
    offline_bg="#F8E0DE",
    unknown_bg="#F3E7E2",
    input_bg="#FFFFFF",
    input_border="#E8D0C6",
    btn_bg="#F7ECE7",
    btn_hover="#EFD8D0",
    card_tile="#F7EDE8",
    card_tile_hover="#F0E2DB",
    card_selected="#F5DCD2",
    scroll="#D4B4A8",
    side="#2A1814",
    side_2="#3A241C",
    side_line="#55382E",
    side_text="#FFF6F2",
    side_muted="#C9A89C",
    side_soft="#EED8CE",
    side_input_bg="#201410",
    side_input_text="#FFEDE6",
    side_input_border="#55382E",
    side_check="#CDB0A4",
    pass_value="#FFB39A",
    host_ok="#FFB39A",
    ghost_bg="#3F2820",
    ghost_hover="#52362C",
    ghost_border="#664438",
    ghost_text="#FFEDE6",
    splitter="#E8D0C6",
)

MATCHA = ThemeColors(
    id="matcha",
    bg="#F2F6EC",
    card="#FBFFF7",
    text="#24301C",
    muted="#6A7A58",
    line="#D4DEC4",
    accent="#6F9B3C",
    accent_2="#5A8230",
    danger="#C94B4B",
    danger_hover="#B03F3F",
    warn="#B88420",
    online="#2F8F5B",
    offline="#C0392B",
    online_bg="#DCF0E4",
    offline_bg="#F6E1DF",
    unknown_bg="#E8EEDF",
    input_bg="#FFFFFF",
    input_border="#D4DEC4",
    btn_bg="#EDF3E4",
    btn_hover="#E2EBD6",
    card_tile="#F0F5E8",
    card_tile_hover="#E6EFD9",
    card_selected="#DDECC8",
    scroll="#B8C8A0",
    side="#1A2414",
    side_2="#26321C",
    side_line="#3C4A2E",
    side_text="#F5FFE8",
    side_muted="#A8B890",
    side_soft="#D8E4C4",
    side_input_bg="#141C10",
    side_input_text="#F0FADA",
    side_input_border="#3C4A2E",
    side_check="#B0C098",
    pass_value="#C8EE8A",
    host_ok="#C8EE8A",
    ghost_bg="#2A3620",
    ghost_hover="#38482C",
    ghost_border="#485A38",
    ghost_text="#F0FADA",
    splitter="#D4DEC4",
)

SKY = ThemeColors(
    id="sky",
    bg="#EEF6FC",
    card="#FFFFFF",
    text="#173048",
    muted="#5E7A90",
    line="#C8DCEB",
    accent="#3B9BE0",
    accent_2="#2E82C2",
    danger="#D05050",
    danger_hover="#B74242",
    warn="#C08A1E",
    online="#1A8F6A",
    offline="#C44545",
    online_bg="#D7F0E6",
    offline_bg="#F7E1E1",
    unknown_bg="#E4EEF5",
    input_bg="#FFFFFF",
    input_border="#C8DCEB",
    btn_bg="#EDF5FB",
    btn_hover="#DFEDF7",
    card_tile="#F0F7FC",
    card_tile_hover="#E4F1FA",
    card_selected="#D6ECFA",
    scroll="#AFC8DA",
    side="#123048",
    side_2="#1A3E5A",
    side_line="#2C5674",
    side_text="#F2F9FF",
    side_muted="#97B4C8",
    side_soft="#C8DCEB",
    side_input_bg="#0E2438",
    side_input_text="#E8F4FC",
    side_input_border="#2C5674",
    side_check="#9FBCD0",
    pass_value="#8AD0FF",
    host_ok="#8AD0FF",
    ghost_bg="#1C4460",
    ghost_hover="#285674",
    ghost_border="#346888",
    ghost_text="#E8F4FC",
    splitter="#C8DCEB",
)

SLATE = ThemeColors(
    id="slate",
    bg="#ECEFF3",
    card="#FFFFFF",
    text="#1C2733",
    muted="#667788",
    line="#CDD5DE",
    accent="#5B7C99",
    accent_2="#4A6782",
    danger="#C94B4B",
    danger_hover="#B03F3F",
    warn="#B8860B",
    online="#2F8F5B",
    offline="#C0392B",
    online_bg="#DCF0E4",
    offline_bg="#F6E1DF",
    unknown_bg="#E6EBEF",
    input_bg="#FFFFFF",
    input_border="#CDD5DE",
    btn_bg="#F1F4F7",
    btn_hover="#E5EAF0",
    card_tile="#F3F6F8",
    card_tile_hover="#E9EEF3",
    card_selected="#DDE6EF",
    scroll="#B4C0CC",
    side="#1A2430",
    side_2="#243240",
    side_line="#3A4A5A",
    side_text="#F2F6FA",
    side_muted="#A0B0C0",
    side_soft="#D0DAE4",
    side_input_bg="#121A24",
    side_input_text="#EAF0F6",
    side_input_border="#3A4A5A",
    side_check="#A8B8C8",
    pass_value="#A8C8E8",
    host_ok="#A8C8E8",
    ghost_bg="#2A3848",
    ghost_hover="#3A4A5C",
    ghost_border="#4A5C70",
    ghost_text="#EAF0F6",
    splitter="#CDD5DE",
)

NOIR = ThemeColors(
    id="noir",
    bg="#0A0A0C",
    card="#141418",
    text="#F0F0F2",
    muted="#9A9AA4",
    line="#2A2A32",
    # Mid silver — stays “mono” but keeps primary buttons readable.
    accent="#B8B8C4",
    accent_2="#9A9AA8",
    danger="#E05555",
    danger_hover="#C94444",
    warn="#E0B04A",
    online="#3DDC97",
    offline="#FF7A7A",
    online_bg="#143028",
    offline_bg="#3A2224",
    unknown_bg="#1C1C22",
    input_bg="#101014",
    input_border="#2A2A32",
    btn_bg="#1C1C22",
    btn_hover="#282830",
    card_tile="#1A1A20",
    card_tile_hover="#24242C",
    card_selected="#2A2A34",
    scroll="#3A3A44",
    side="#050506",
    side_2="#101014",
    side_line="#282830",
    side_text="#F5F5F7",
    side_muted="#8E8E98",
    side_soft="#C8C8D0",
    side_input_bg="#08080A",
    side_input_text="#EEEEF2",
    side_input_border="#282830",
    side_check="#9898A2",
    pass_value="#FFFFFF",
    host_ok="#B8F0C8",
    ghost_bg="#1E1E24",
    ghost_hover="#2A2A32",
    ghost_border="#3A3A44",
    ghost_text="#EEEEF2",
    splitter="#2A2A32",
)

EMBER = ThemeColors(
    id="ember",
    bg="#160E0C",
    card="#221612",
    text="#F6EBE4",
    muted="#B49A8E",
    line="#3E2A22",
    accent="#E85D3A",
    accent_2="#C94A2C",
    danger="#E05555",
    danger_hover="#C94444",
    warn="#E0B04A",
    online="#5CBF7A",
    offline="#FF7A7A",
    online_bg="#1F3528",
    offline_bg="#3A2222",
    unknown_bg="#2C1E1A",
    input_bg="#1A120F",
    input_border="#3E2A22",
    btn_bg="#2A1C16",
    btn_hover="#3A2820",
    card_tile="#2E1E18",
    card_tile_hover="#3C2A22",
    card_selected="#4A2C20",
    scroll="#5A4034",
    side="#0E0908",
    side_2="#1A1210",
    side_line="#3A2820",
    side_text="#FFF0E8",
    side_muted="#B49A8E",
    side_soft="#E0C8B8",
    side_input_bg="#0A0706",
    side_input_text="#F6EBE4",
    side_input_border="#3A2820",
    side_check="#B8A094",
    pass_value="#FF9A78",
    host_ok="#FF9A78",
    ghost_bg="#281A14",
    ghost_hover="#3A2820",
    ghost_border="#4A3830",
    ghost_text="#F6EBE4",
    splitter="#3E2A22",
)

AURORA = ThemeColors(
    id="aurora",
    bg="#0B1620",
    card="#122430",
    text="#E6F4F6",
    muted="#8FB0B8",
    line="#274550",
    accent="#2FD4B8",
    accent_2="#22B49C",
    danger="#E05A6A",
    danger_hover="#C94A58",
    warn="#E0B04A",
    online="#3DDC97",
    offline="#FF7A8A",
    online_bg="#17382E",
    offline_bg="#3A2228",
    unknown_bg="#1A2E38",
    input_bg="#0E1C26",
    input_border="#274550",
    btn_bg="#183038",
    btn_hover="#224048",
    card_tile="#183038",
    card_tile_hover="#224850",
    card_selected="#1A4848",
    scroll="#3A6068",
    side="#071018",
    side_2="#101C28",
    side_line="#243844",
    side_text="#F0FBFC",
    side_muted="#8FB0B8",
    side_soft="#C4E0E4",
    side_input_bg="#060E14",
    side_input_text="#E6F4F6",
    side_input_border="#243844",
    side_check="#98B8C0",
    pass_value="#7EF0D8",
    host_ok="#7EF0D8",
    ghost_bg="#162830",
    ghost_hover="#223840",
    ghost_border="#304850",
    ghost_text="#E6F4F6",
    splitter="#274550",
)

VIOLET = ThemeColors(
    id="violet",
    bg="#14101C",
    card="#1E182A",
    text="#F0EAF8",
    muted="#A89AB8",
    line="#3A304E",
    accent="#9B7BFF",
    accent_2="#7F62E0",
    danger="#E05A6A",
    danger_hover="#C94A58",
    warn="#E0B04A",
    online="#3DDC97",
    offline="#FF7A8A",
    online_bg="#17382E",
    offline_bg="#3A2228",
    unknown_bg="#262038",
    input_bg="#161222",
    input_border="#3A304E",
    btn_bg="#262038",
    btn_hover="#322A48",
    card_tile="#262038",
    card_tile_hover="#322A48",
    card_selected="#32285A",
    scroll="#4A4068",
    side="#0E0A16",
    side_2="#181222",
    side_line="#322A48",
    side_text="#F6F0FF",
    side_muted="#A89AB8",
    side_soft="#D4C8EC",
    side_input_bg="#0A0812",
    side_input_text="#F0EAF8",
    side_input_border="#322A48",
    side_check="#B0A0C8",
    pass_value="#C8B4FF",
    host_ok="#C8B4FF",
    ghost_bg="#221C34",
    ghost_hover="#2E2644",
    ghost_border="#3E3658",
    ghost_text="#F0EAF8",
    splitter="#3A304E",
)

WINE = ThemeColors(
    id="wine",
    bg="#180E12",
    card="#24141C",
    text="#F6E8EE",
    muted="#B894A0",
    line="#4A2836",
    accent="#C94B72",
    accent_2="#A83C5C",
    danger="#E05555",
    danger_hover="#C94444",
    warn="#E0B04A",
    online="#5CBF7A",
    offline="#FF7A7A",
    online_bg="#1F3528",
    offline_bg="#3A2222",
    unknown_bg="#2E1A22",
    input_bg="#1C1016",
    input_border="#4A2836",
    btn_bg="#2E1A22",
    btn_hover="#3E2430",
    card_tile="#2E1A22",
    card_tile_hover="#3E2430",
    card_selected="#4A2438",
    scroll="#5A3848",
    side="#100A0E",
    side_2="#1C1016",
    side_line="#3E2430",
    side_text="#FFF0F5",
    side_muted="#B894A0",
    side_soft="#E8C8D4",
    side_input_bg="#0C080A",
    side_input_text="#F6E8EE",
    side_input_border="#3E2430",
    side_check="#C0A0AC",
    pass_value="#FFA0C0",
    host_ok="#FFA0C0",
    ghost_bg="#2A1620",
    ghost_hover="#3A2030",
    ghost_border="#4A3040",
    ghost_text="#F6E8EE",
    splitter="#4A2836",
)

COPPER = ThemeColors(
    id="copper",
    bg="#F4EDE6",
    card="#FFFBF7",
    text="#2C2118",
    muted="#7A6858",
    line="#DCCAB8",
    accent="#B87333",
    accent_2="#9A5F28",
    danger="#C94B4B",
    danger_hover="#B03F3F",
    warn="#B8860B",
    online="#2F8F5B",
    offline="#C0392B",
    online_bg="#DCF0E4",
    offline_bg="#F6E1DF",
    unknown_bg="#EDE4DA",
    input_bg="#FFFFFF",
    input_border="#DCCAB8",
    btn_bg="#F0E6DC",
    btn_hover="#E6D8CA",
    card_tile="#F2E8DE",
    card_tile_hover="#EADFD2",
    card_selected="#E8D4BC",
    scroll="#C4AE98",
    side="#241C14",
    side_2="#32281E",
    side_line="#4A3C2E",
    side_text="#FFF6EC",
    side_muted="#C2AE98",
    side_soft="#E6D4C0",
    side_input_bg="#1A140E",
    side_input_text="#FFF4E8",
    side_input_border="#4A3C2E",
    side_check="#C6B29C",
    pass_value="#E8B878",
    host_ok="#E8B878",
    ghost_bg="#3A2E22",
    ghost_hover="#4A3C2E",
    ghost_border="#5A4C3C",
    ghost_text="#FFF4E8",
    splitter="#DCCAB8",
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
    SAKURA.id: SAKURA,
    CORAL.id: CORAL,
    MATCHA.id: MATCHA,
    SKY.id: SKY,
    SLATE.id: SLATE,
    COPPER.id: COPPER,
    NOIR.id: NOIR,
    EMBER.id: EMBER,
    AURORA.id: AURORA,
    VIOLET.id: VIOLET,
    WINE.id: WINE,
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
    chrome_bg = _rgba(c.side, 0.92)
    chrome_btn_bg = _rgba(c.ghost_bg, 0.75)
    chrome_btn_hover = _rgba(c.accent, 0.28)
    chrome_btn_pressed = _rgba(c.accent, 0.48)
    chrome_btn_border = _rgba(c.accent, 0.55)
    btn_pressed = _shade(c.btn_hover, 0.90)
    primary_pressed = _shade(c.accent_2, 0.82)
    danger_pressed = _shade(c.danger_hover, 0.85)
    ghost_pressed = _shade(c.ghost_hover, 0.88)
    # Light accents (e.g. noir) need dark label text; dark accents keep white.
    on_accent = _contrast_text(c.accent)
    on_accent_2 = _contrast_text(c.accent_2)
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
}}
QLabel#passValue {{
    color: {c.pass_value};
    font-size: 22px;
    font-weight: 800;
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
QScrollArea#sideScroll, QScrollArea#sideScroll > QWidget > QWidget {{
    background: {c.side};
    border: none;
}}
QWidget#sideTop {{
    background: {c.side};
}}
QFrame#sideActions {{
    background: {c.side_2};
    border-top: 1px solid {c.side_line};
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
    selection-color: {on_accent};
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
QPushButton:pressed {{
    background: {btn_pressed};
    border-color: {c.accent};
    padding: 9px 13px 7px 15px;
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
    color: {on_accent};
    border: none;
    font-weight: 700;
}}
QPushButton#primary:hover {{
    background: {c.accent_2};
    color: {on_accent_2};
}}
QPushButton#primary:pressed {{
    background: {primary_pressed};
    color: {on_accent_2};
    padding: 9px 13px 7px 15px;
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
QPushButton#danger:pressed {{
    background: {danger_pressed};
    padding: 9px 13px 7px 15px;
}}
QPushButton#ghostDark {{
    background: {c.ghost_bg};
    color: {c.ghost_text};
    border: 1px solid {c.ghost_border};
}}
QPushButton#ghostDark:hover {{
    background: {c.ghost_hover};
}}
QPushButton#ghostDark:pressed {{
    background: {ghost_pressed};
    border-color: {c.accent};
    padding: 9px 13px 7px 15px;
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
QLabel#cardOs {{
    color: {c.muted};
    background: {c.card_tile};
    border: 1px solid {c.line};
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
QDialog#confirmDialog, QMainWindow#confirmDialog {{
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
QFrame#dialogTitleBar[compact="true"] {{
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
}}
QLabel#dialogCaption {{
    color: {c.text};
    font-size: 13px;
    font-weight: 700;
}}
QFrame#dialogTitleBar[compact="true"] QLabel#dialogCaption {{
    font-size: 12px;
    font-weight: 600;
}}
QPushButton#dialogClose, QPushButton#windowChromeBtn {{
    background: transparent;
    color: {c.muted};
    border: none;
    border-radius: 8px;
    font-size: 18px;
    font-weight: 700;
    padding: 0;
}}
QFrame#dialogTitleBar[compact="true"] QPushButton#dialogClose {{
    border-radius: 6px;
    font-size: 15px;
}}
QPushButton#dialogClose:hover, QPushButton#windowChromeBtn:hover {{
    background: {c.btn_hover};
    color: {c.text};
}}
QPushButton#dialogClose:pressed, QPushButton#windowChromeBtn:pressed {{
    background: {btn_pressed};
    color: {c.text};
}}
QPushButton#windowChromeBtn {{
    font-size: 16px;
}}
QLabel#confirmEyebrow {{
    color: {c.muted};
    font-size: 11px;
    font-weight: 700;
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
    selection-color: {on_accent};
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
QLabel#confirmCheck {{
    color: {c.text};
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
QPushButton#confirmCancel:pressed {{
    background: {btn_pressed};
    border-color: {c.accent};
    padding: 10px 17px 8px 19px;
}}
QPushButton#confirmOk {{
    background: {c.accent};
    color: {on_accent};
    border: none;
    border-radius: 8px;
    padding: 9px 18px;
    font-weight: 700;
    min-width: 96px;
}}
QPushButton#confirmOk:hover {{
    background: {c.accent_2};
    color: {on_accent_2};
}}
QPushButton#confirmOk:pressed {{
    background: {primary_pressed};
    color: {on_accent_2};
    padding: 10px 17px 8px 19px;
}}
QPushButton#confirmOk[danger="true"] {{
    background: {c.danger};
    color: #FFFFFF;
}}
QPushButton#confirmOk[danger="true"]:hover {{
    background: {c.danger_hover};
    color: #FFFFFF;
}}
QPushButton#confirmOk[danger="true"]:pressed {{
    background: {danger_pressed};
    color: #FFFFFF;
}}
QPushButton#remoteNavBtn {{
    background: {c.btn_bg};
    color: {c.text};
    border: 1px solid {c.line};
    border-radius: 8px;
    padding: 7px 12px;
    font-weight: 600;
    min-width: 56px;
}}
QPushButton#remoteNavBtn:hover {{
    background: {c.btn_hover};
}}
QPushButton#remoteNavBtn:pressed {{
    background: {btn_pressed};
    border-color: {c.accent};
    padding: 8px 11px 6px 13px;
}}
QPushButton#remoteNavBtn:disabled {{
    color: {c.muted};
    background: {c.card};
}}
QTableWidget#remoteFileTable {{
    background: {c.input_bg};
    color: {c.text};
    border: 1px solid {c.line};
    border-radius: 10px;
    gridline-color: transparent;
    outline: 0;
    padding: 2px;
    selection-background-color: {c.card_selected};
    selection-color: {c.text};
    alternate-background-color: {_rgba(c.text, 0.04)};
}}
QTableWidget#remoteFileTable::item {{
    color: {c.text};
    background: transparent;
    padding: 4px 10px;
    border: none;
}}
QTableWidget#remoteFileTable::item:hover {{
    background: {_rgba(c.accent, 0.10)};
    color: {c.text};
}}
QTableWidget#remoteFileTable::item:selected {{
    background: {c.card_selected};
    color: {c.text};
}}
QTableWidget#remoteFileTable::item:selected:hover {{
    background: {c.card_selected};
    color: {c.text};
}}
QTableWidget#remoteFileTable QHeaderView::section {{
    background: {c.card};
    color: {c.muted};
    border: none;
    border-bottom: 1px solid {c.line};
    border-right: 1px solid transparent;
    padding: 8px 10px;
    font-size: 12px;
    font-weight: 700;
}}
QTableWidget#remoteFileTable QHeaderView::section:first {{
    border-top-left-radius: 10px;
}}
QTableWidget#remoteFileTable QHeaderView::section:last {{
    border-top-right-radius: 10px;
}}
QTableWidget#remoteFileTable QCornerButton::section {{
    background: {c.card};
    border: none;
}}
QFrame#viewerChromeBar {{
    background: {chrome_bg};
    border: none;
    border-bottom-left-radius: 10px;
    border-bottom-right-radius: 10px;
}}
QPushButton#viewerChromeBtn {{
    color: {c.side_text};
    background: {chrome_btn_bg};
    border: 1px solid {chrome_btn_border};
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 12px;
    font-weight: 600;
}}
QPushButton#viewerChromeBtn:hover {{
    background: {chrome_btn_hover};
    color: #FFFFFF;
    border-color: {c.accent};
}}
QPushButton#viewerChromeBtn:pressed {{
    background: {chrome_btn_pressed};
    color: #FFFFFF;
    border-color: {c.accent};
    padding: 7px 13px 5px 15px;
}}
QPushButton#viewerExitFsBtn {{
    background: transparent;
    border: none;
    padding: 0;
}}
"""
