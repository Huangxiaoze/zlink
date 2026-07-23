"""Windows low-level keyboard capture for keys the OS steals (Alt+Tab)."""

from __future__ import annotations

import ctypes
import logging
import sys
import threading
from ctypes import wintypes
from typing import Callable, Optional

log = logging.getLogger(__name__)

WH_KEYBOARD_LL = 13
WM_KEYUP = 0x0101
WM_SYSKEYUP = 0x0105
VK_TAB = 0x09
VK_MENU = 0x12  # Alt
LLKHF_UP = 0x80

if sys.platform != "win32":  # pragma: no cover

    class AltTabCapture:
        def __init__(self, *_a, **_k) -> None:
            pass

        @property
        def active(self) -> bool:
            return False

        def start(self) -> None:
            return

        def stop(self) -> None:
            return

        def force_release_tab(self) -> None:
            return

else:

    class KBDLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [
            ("vkCode", wintypes.DWORD),
            ("scanCode", wintypes.DWORD),
            ("flags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_size_t),
        ]

    # Single shared callback type — recreating WINFUNCTYPE causes
    # "expected WinFunctionType instance instead of WinFunctionType".
    LRESULT = ctypes.c_ssize_t
    HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.SetWindowsHookExW.argtypes = (
        ctypes.c_int,
        HOOKPROC,
        wintypes.HINSTANCE,
        wintypes.DWORD,
    )
    user32.SetWindowsHookExW.restype = wintypes.HHOOK
    user32.UnhookWindowsHookEx.argtypes = (wintypes.HHOOK,)
    user32.UnhookWindowsHookEx.restype = wintypes.BOOL
    user32.CallNextHookEx.argtypes = (
        wintypes.HHOOK,
        ctypes.c_int,
        wintypes.WPARAM,
        wintypes.LPARAM,
    )
    user32.CallNextHookEx.restype = LRESULT
    user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
    user32.GetAsyncKeyState.restype = wintypes.SHORT

    class AltTabCapture:
        """While enabled, swallow local Alt+Tab and report Tab presses to the app."""

        def __init__(
            self,
            on_tab: Callable[[str], None],
            *,
            is_enabled: Optional[Callable[[], bool]] = None,
        ) -> None:
            self._on_tab = on_tab
            self._is_enabled = is_enabled or (lambda: True)
            self._hook = None
            self._proc = None
            self._lock = threading.Lock()
            self._installed = False
            # True after we forwarded Tab-down to remote; waits for matching up.
            self._tab_down_sent = False

        @property
        def active(self) -> bool:
            return self._installed

        def start(self) -> None:
            with self._lock:
                if self._installed:
                    return
                try:
                    self._proc = HOOKPROC(self._callback)
                    self._hook = user32.SetWindowsHookExW(
                        WH_KEYBOARD_LL,
                        self._proc,
                        wintypes.HINSTANCE(0),
                        0,
                    )
                except Exception:
                    log.exception("SetWindowsHookExW failed; Alt+Tab capture unavailable")
                    self._hook = None
                    self._proc = None
                    return
                if not self._hook:
                    err = ctypes.get_last_error()
                    log.warning(
                        "SetWindowsHookExW returned NULL (err=%s); Alt+Tab capture unavailable",
                        err,
                    )
                    self._proc = None
                    return
                self._installed = True
                self._tab_down_sent = False
                log.info("Alt+Tab capture hook installed")

        def stop(self) -> None:
            with self._lock:
                if not self._installed:
                    return
                try:
                    user32.UnhookWindowsHookEx(self._hook)
                except Exception:
                    log.exception("UnhookWindowsHookEx failed")
                self._hook = None
                self._proc = None
                self._installed = False
                # If Tab was left down on the remote, ask the app to release it.
                if self._tab_down_sent:
                    self._tab_down_sent = False
                    try:
                        self._on_tab("up")
                    except Exception:
                        log.exception("force Tab-up on hook stop failed")
                log.info("Alt+Tab capture hook removed")

        def force_release_tab(self) -> None:
            """Call when Alt is released so a missed Tab-up cannot stick remotely."""
            with self._lock:
                if not self._tab_down_sent:
                    return
                self._tab_down_sent = False
            try:
                self._on_tab("up")
            except Exception:
                log.exception("force Tab-up failed")

        def _emit_tab(self, action: str) -> None:
            try:
                self._on_tab(action)
            except Exception:
                log.exception("Alt+Tab callback failed")

        def _callback(self, n_code: int, w_param: int, l_param: int) -> int:
            try:
                if n_code >= 0 and self._is_enabled():
                    info = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                    vk = int(info.vkCode)
                    going_up = bool(int(info.flags) & LLKHF_UP) or int(w_param) in (
                        WM_KEYUP,
                        WM_SYSKEYUP,
                    )
                    alt_down = bool(user32.GetAsyncKeyState(VK_MENU) & 0x8000)

                    # If Alt goes up while Tab was forwarded, release Tab immediately.
                    # (Users often release Alt before Tab when finishing Alt+Tab.)
                    if vk == VK_MENU and going_up and self._tab_down_sent:
                        self._tab_down_sent = False
                        self._emit_tab("up")
                        # Let Alt-up continue to Qt / normal path.
                        return int(user32.CallNextHookEx(self._hook, n_code, w_param, l_param))

                    if vk == VK_TAB:
                        # Capture Tab while Alt held, OR Tab-up after we sent Tab-down
                        # even if Alt was already released (otherwise Tab sticks remotely).
                        if alt_down or (going_up and self._tab_down_sent):
                            if going_up:
                                if self._tab_down_sent:
                                    self._tab_down_sent = False
                                    self._emit_tab("up")
                            else:
                                # Suppress key-repeat downs — one remote down is enough.
                                if not self._tab_down_sent:
                                    self._tab_down_sent = True
                                    self._emit_tab("down")
                            return 1
            except Exception:
                log.exception("Alt+Tab hook callback error")
            return int(user32.CallNextHookEx(self._hook, n_code, w_param, l_param))
