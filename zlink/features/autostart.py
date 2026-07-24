"""Login autostart helpers (Windows registry Run, Linux XDG autostart)."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

log = logging.getLogger(__name__)

APP_DISPLAY_NAME = "ZLink"
REGISTRY_VALUE_NAME = "ZLink"
DESKTOP_FILE_NAME = "zlink.desktop"


def supports_autostart() -> bool:
    if os.name == "nt":
        return True
    return sys.platform.startswith("linux")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _quote_win_arg(path: str) -> str:
    if not path:
        return '""'
    if path.startswith('"') and path.endswith('"'):
        return path
    return '"%s"' % path.replace('"', "")


def launch_command(*, start_minimized: bool = False) -> str:
    """Shell command written into OS autostart entries."""
    if getattr(sys, "frozen", False):
        parts = [_quote_win_arg(sys.executable)]
    else:
        main_py = _repo_root() / "main.py"
        parts = [
            _quote_win_arg(sys.executable),
            _quote_win_arg(str(main_py)),
            "gui",
        ]
    if start_minimized:
        parts.append("--minimized")
    return " ".join(parts)


def is_enabled() -> bool:
    if not supports_autostart():
        return False
    if os.name == "nt":
        return _win_is_enabled()
    return _linux_desktop_path().is_file()


def apply(enabled: bool, *, start_minimized: bool = False) -> None:
    if not supports_autostart():
        raise OSError("autostart is not supported on this platform")
    if os.name == "nt":
        if enabled:
            _win_enable(start_minimized=start_minimized)
        else:
            _win_disable()
        return
    if enabled:
        _linux_enable(start_minimized=start_minimized)
    else:
        _linux_disable()


def sync_settings(*, launch_at_login: bool, start_minimized: bool) -> None:
    """Align OS autostart entry with saved settings."""
    if not supports_autostart():
        return
    try:
        apply(bool(launch_at_login), start_minimized=bool(start_minimized))
    except OSError:
        log.exception("autostart sync failed")


def _win_is_enabled() -> bool:
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_READ,
        ) as key:
            winreg.QueryValueEx(key, REGISTRY_VALUE_NAME)
            return True
    except OSError:
        return False


def _win_enable(*, start_minimized: bool) -> None:
    import winreg

    cmd = launch_command(start_minimized=start_minimized)
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        winreg.SetValueEx(key, REGISTRY_VALUE_NAME, 0, winreg.REG_SZ, cmd)
    log.info("autostart enabled: %s", cmd)


def _win_disable() -> None:
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.DeleteValue(key, REGISTRY_VALUE_NAME)
        log.info("autostart disabled (Windows)")
    except OSError:
        pass


def _linux_autostart_dir() -> Path:
    root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return root / "autostart"


def _linux_desktop_path() -> Path:
    return _linux_autostart_dir() / DESKTOP_FILE_NAME


def _linux_icon_path() -> str:
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        for candidate in (
            exe_dir / "resources" / "icon" / "app.png",
            exe_dir / "_internal" / "resources" / "icon" / "app.png",
        ):
            if candidate.is_file():
                return str(candidate)
    else:
        icon = _repo_root() / "resources" / "icon" / "app.png"
        if icon.is_file():
            return str(icon)
    return APP_DISPLAY_NAME


def _linux_enable(*, start_minimized: bool) -> None:
    path = _linux_desktop_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    exec_line = launch_command(start_minimized=start_minimized)
    icon = _linux_icon_path()
    body = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Version=1.0\n"
        "Name=%s\n"
        "Comment=ZLink remote desktop\n"
        "Exec=%s\n"
        "Icon=%s\n"
        "Terminal=false\n"
        "Categories=Network;\n"
        "StartupNotify=false\n"
        "X-GNOME-Autostart-enabled=true\n"
    ) % (APP_DISPLAY_NAME, exec_line, icon)
    path.write_text(body, encoding="utf-8")
    log.info("autostart enabled: %s", path)


def _linux_disable() -> None:
    path = _linux_desktop_path()
    try:
        if path.is_file():
            path.unlink()
        log.info("autostart disabled (Linux)")
    except OSError as exc:
        log.warning("failed to remove autostart desktop file: %s", exc)
