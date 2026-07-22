from __future__ import annotations

import logging
from typing import Any

from pynput.keyboard import Controller as KeyController
from pynput.keyboard import Key
from pynput.mouse import Button
from pynput.mouse import Controller as MouseController

log = logging.getLogger(__name__)

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
    def __init__(self, screen_w: int, screen_h: int) -> None:
        self.screen_w = max(1, screen_w)
        self.screen_h = max(1, screen_h)
        self._mouse = MouseController()
        self._keyboard = KeyController()

    def set_screen_size(self, width: int, height: int) -> None:
        self.screen_w = max(1, width)
        self.screen_h = max(1, height)

    def handle_mouse(self, msg: dict[str, Any]) -> None:
        action = msg.get("action")
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
            elif action == "up":
                self._mouse.release(button)
            elif action == "click":
                self._mouse.click(button, int(msg.get("clicks", 1)))
            elif action == "scroll":
                self._mouse.scroll(int(msg.get("dx", 0)), int(msg.get("dy", 0)))
        except Exception:
            log.exception("mouse inject failed action=%s", action)

    def handle_key(self, msg: dict[str, Any]) -> None:
        action = msg.get("action")
        key_name = str(msg.get("key", ""))
        if not key_name:
            return
        key = _resolve_key(key_name)
        try:
            if action == "down":
                self._keyboard.press(key)
            elif action == "up":
                self._keyboard.release(key)
            elif action == "type":
                self._keyboard.type(key_name)
        except Exception:
            log.exception("key inject failed key=%s action=%s", key_name, action)


def _resolve_key(name: str):
    lowered = name.lower()
    if lowered in _SPECIAL_KEYS:
        return _SPECIAL_KEYS[lowered]
    if len(name) == 1:
        return name
    # pygame-style names like "a", "K_a" etc.
    if lowered.startswith("k_") and len(lowered) == 3:
        return lowered[-1]
    return name


def pygame_key_name(pygame_key: int, pygame_module: Any) -> str:
    name = pygame_module.key.name(pygame_key)
    return name or str(pygame_key)
