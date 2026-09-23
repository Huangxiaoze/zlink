from __future__ import annotations

import logging
import sys
from typing import Any, Optional, TYPE_CHECKING

from pynput.keyboard import Controller as KeyController
from pynput.keyboard import Key
from pynput.mouse import Button
from pynput.mouse import Controller as MouseController

if TYPE_CHECKING:
    from .pointer_sync import PointerAuthority

log = logging.getLogger(__name__)

# Physical key above Tab. GNOME binds switch-group to <Alt>/<Super>Above_Tab,
# which is NOT the same keysym as plain grave/` — char injection misses it.
_GRAVE_NAMES = frozenset({"`", "grave", "quoteleft", "above_tab", "abovetab"})
_ANGLE_BRACKET_CHARS = frozenset({"<", ">"})
_MODIFIER_KEYS = frozenset(
    {
        Key.alt,
        Key.alt_l,
        getattr(Key, "alt_r", Key.alt),
        getattr(Key, "alt_gr", Key.alt),
        Key.cmd,
        Key.cmd_l,
        Key.cmd_r,
    }
)

_SPECIAL_KEYS: dict[str, Key] = {
    "enter": Key.enter,
    "return": Key.enter,
    "tab": Key.tab,
    "space": Key.space,
    "backspace": Key.backspace,
    "esc": Key.esc,
    "escape": Key.esc,
    "up": Key.up,
    "down": Key.down,
    "left": Key.left,
    "right": Key.right,
    "home": Key.home,
    "end": Key.end,
    "pageup": Key.page_up,
    "pagedown": Key.page_down,
    "delete": Key.delete,
    "insert": Key.insert,
    "ctrl": Key.ctrl,
    "ctrl_l": Key.ctrl_l,
    "ctrl_r": Key.ctrl_r,
    "alt": Key.alt,
    "alt_l": Key.alt_l,
    "alt_r": getattr(Key, "alt_r", Key.alt),
    "alt_gr": getattr(Key, "alt_gr", getattr(Key, "alt_r", Key.alt)),
    "shift": Key.shift,
    "shift_l": Key.shift_l,
    "shift_r": Key.shift_r,
    "cmd": Key.cmd,
    "cmd_l": Key.cmd_l,
    "cmd_r": Key.cmd_r,
    "win": Key.cmd,
    "f1": Key.f1,
    "f2": Key.f2,
    "f3": Key.f3,
    "f4": Key.f4,
    "f5": Key.f5,
    "f6": Key.f6,
    "f7": Key.f7,
    "f8": Key.f8,
    "f9": Key.f9,
    "f10": Key.f10,
    "f11": Key.f11,
    "f12": Key.f12,
}

_BUTTONS = {
    "left": Button.left,
    "right": Button.right,
    "middle": Button.middle,
}


class InputInjector:
    def __init__(
        self,
        screen_w: int,
        screen_h: int,
        pointer: Optional["PointerAuthority"] = None,
    ) -> None:
        self.screen_w = max(1, screen_w)
        self.screen_h = max(1, screen_h)
        self._pointer = pointer
        self._mouse = MouseController()
        self._keyboard = KeyController()
        self._pressed_keys: set[Any] = set()
        self._pressed_buttons: set[Button] = set()
        # Logical protocol name -> object actually pressed (modifier-dependent resolve).
        self._injected_by_name: dict[str, Any] = {}

    def set_screen_size(self, width: int, height: int) -> None:
        self.screen_w = max(1, width)
        self.screen_h = max(1, height)

    def handle_mouse(self, msg: dict[str, Any]) -> None:
        action = msg.get("action")
        if action == "flush":
            self.release_all_buttons()
            return
        if self._pointer is not None:
            self._pointer.note_remote_inject()
        x = float(msg.get("x", 0.0))
        y = float(msg.get("y", 0.0))
        abs_x = int(max(0.0, min(1.0, x)) * (self.screen_w - 1))
        abs_y = int(max(0.0, min(1.0, y)) * (self.screen_h - 1))

        try:
            if action in {"move", "down", "up", "click", "drag"}:
                self._mouse.position = (abs_x, abs_y)
            button_name = msg.get("button", "left")
            button = _BUTTONS.get(button_name, Button.left)
            if action == "down":
                self._mouse.press(button)
                self._pressed_buttons.add(button)
            elif action == "up":
                self._mouse.release(button)
                self._pressed_buttons.discard(button)
            elif action == "click":
                self._mouse.click(button, int(msg.get("clicks", 1)))
            elif action == "scroll":
                self._mouse.scroll(int(msg.get("dx", 0)), int(msg.get("dy", 0)))
        except Exception:
            log.exception("mouse inject failed action=%s", action)

    def handle_key(self, msg: dict[str, Any]) -> None:
        action = msg.get("action")
        if action == "flush":
            self.release_all_keys()
            return
        key_name = str(msg.get("key", ""))
        if not key_name:
            return
        name_key = key_name.lower()
        try:
            if action in ("down", "type") and key_name in _ANGLE_BRACKET_CHARS:
                _inject_angle_bracket(self._keyboard, key_name, self._pressed_keys)
                return
            if action == "up" and key_name in _ANGLE_BRACKET_CHARS:
                return
            if action == "down":
                key = _resolve_key(key_name, self._pressed_keys)
                self._keyboard.press(key)
                self._pressed_keys.add(key)
                self._injected_by_name[name_key] = key
            elif action == "up":
                key = self._injected_by_name.pop(name_key, None)
                if key is None:
                    key = _resolve_key(key_name, self._pressed_keys)
                self._keyboard.release(key)
                self._pressed_keys.discard(key)
            elif action == "type":
                self._keyboard.type(key_name)
        except Exception:
            log.exception("key inject failed key=%s action=%s", key_name, action)

    def release_all_keys(self) -> None:
        """Release stuck keys (e.g. Alt left down after local Alt+Tab stole focus)."""
        stuck = list(self._pressed_keys)
        self._pressed_keys.clear()
        self._injected_by_name.clear()
        for key in stuck:
            try:
                self._keyboard.release(key)
            except Exception:
                pass
        # Belt-and-suspenders: always poke common modifiers.
        for key in (
            Key.alt,
            Key.alt_l,
            getattr(Key, "alt_r", Key.alt),
            Key.ctrl,
            Key.ctrl_l,
            Key.ctrl_r,
            Key.shift,
            Key.shift_l,
            Key.shift_r,
            Key.cmd,
            Key.cmd_l,
            Key.cmd_r,
        ):
            try:
                self._keyboard.release(key)
            except Exception:
                pass

    def release_all_buttons(self) -> None:
        stuck = list(self._pressed_buttons)
        self._pressed_buttons.clear()
        for button in stuck:
            try:
                self._mouse.release(button)
            except Exception:
                pass

    def release_all(self) -> None:
        self.release_all_keys()
        self.release_all_buttons()


def _modifier_held(pressed: Optional[set[Any]]) -> bool:
    if not pressed:
        return False
    return any(key in _MODIFIER_KEYS for key in pressed)


def _shift_held(pressed: Optional[set[Any]]) -> bool:
    if not pressed:
        return False
    shift_keys = {Key.shift, Key.shift_l, Key.shift_r}
    return any(key in shift_keys for key in pressed)


_SHIFT_KEYS = (Key.shift, Key.shift_l, Key.shift_r)


def _release_shift_hw(keyboard: KeyController) -> None:
    for sk in _SHIFT_KEYS:
        try:
            keyboard.release(sk)
        except Exception:
            pass


def _restore_shift_hw_if_held(keyboard: KeyController, pressed: set[Any]) -> None:
    if not _shift_held(pressed):
        return
    for sk in _SHIFT_KEYS:
        try:
            keyboard.press(sk)
            return
        except Exception:
            continue


def _inject_angle_bracket(
    keyboard: KeyController, char: str, pressed: set[Any]
) -> None:
    if char not in _ANGLE_BRACKET_CHARS:
        return
    _release_shift_hw(keyboard)
    try:
        keyboard.type(char)
    finally:
        _restore_shift_hw_if_held(keyboard, pressed)


def _x11_key_from_symbol(symbol: str):
    """Resolve an X11 keysym via pynput's Linux backend (None on other platforms)."""
    if not sys.platform.startswith("linux"):
        return None
    try:
        from pynput.keyboard import KeyCode

        from_symbol = getattr(KeyCode, "_from_symbol", None)
        if callable(from_symbol):
            key = from_symbol(symbol)
            if key is not None and getattr(key, "vk", 0):
                return key
    except Exception:
        log.debug("x11 keysym resolve failed symbol=%s", symbol, exc_info=True)
    return None


def _resolve_key(name: str, pressed: Optional[set[Any]] = None):
    lowered = name.lower()
    if lowered in _SPECIAL_KEYS:
        return _SPECIAL_KEYS[lowered]
    if lowered in _GRAVE_NAMES:
        # Ubuntu/GNOME: switch-group is <Alt>Above_Tab / <Super>Above_Tab.
        want_above_tab = lowered in {"above_tab", "abovetab"} or _modifier_held(pressed)
        if want_above_tab:
            above = _x11_key_from_symbol("Above_Tab")
            if above is not None:
                return above
        return "`"
    if len(name) == 1:
        return name
    # pygame-style names like "a", "K_a" etc.
    if lowered.startswith("k_") and len(lowered) == 3:
        return lowered[-1]
    return name


def pygame_key_name(pygame_key: int, pygame_module: Any) -> str:
    name = pygame_module.key.name(pygame_key)
    return name or str(pygame_key)
