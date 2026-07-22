#!/usr/bin/env python3
"""Build LeafLink for the current platform with PyInstaller.

Usage (from repo root `remote/`):
  python scripts/build.py
  python scripts/build.py --console          # keep terminal window (debug / CLI)
  python scripts/build.py --clean
  python scripts/build.py --onefile          # single portable exe (slower start)
  python scripts/build.py --installer        # Windows: also build Setup.exe (Inno Setup)
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
BUILD = ROOT / "build"
SCRIPTS = ROOT / "scripts"
NAME = "LeafLink"
ISS = SCRIPTS / "windows" / "leaflink.iss"
ICON_PNG = ROOT / "resources" / "icon" / "favio.png"
ICON_ICO = ROOT / "resources" / "icon" / "app.ico"


def _app_version() -> str:
    init_py = ROOT / "remote_desktop" / "__init__.py"
    text = init_py.read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("__version__"):
            return line.split("=", 1)[1].strip().strip("\"'")
    return "0.0.0"


def _ensure_app_ico() -> Path | None:
    """Build a multi-size .ico from favio.png for Windows exe / installer."""
    if not ICON_PNG.is_file():
        print("WARNING: app icon PNG missing:", ICON_PNG, file=sys.stderr)
        return ICON_ICO if ICON_ICO.is_file() else None
    try:
        from PIL import Image
    except ImportError:
        print("WARNING: Pillow missing; cannot generate app.ico", file=sys.stderr)
        return ICON_ICO if ICON_ICO.is_file() else None

    img = Image.open(ICON_PNG).convert("RGBA")
    # Drop near-white canvas margins so taskbar/desktop icons look tighter.
    alpha = img.split()[-1]
    bbox = alpha.getbbox()
    if bbox:
        img = img.crop(bbox)
    sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    ICON_ICO.parent.mkdir(parents=True, exist_ok=True)
    img.save(ICON_ICO, format="ICO", sizes=sizes)
    print("Icon   :", ICON_ICO)
    return ICON_ICO


def _datas_args() -> list[str]:
    icon_dir = ROOT / "resources" / "icon"
    if not icon_dir.is_dir():
        return []
    sep = ";" if platform.system().lower() == "windows" else ":"
    return ["--add-data", "%s%sresources/icon" % (icon_dir, sep)]


def _qt_collect_args() -> list[str]:
    try:
        import PySide2  # noqa: F401

        return ["--collect-all", "PySide2"]
    except ImportError:
        pass
    try:
        import PySide6  # noqa: F401

        return ["--collect-all", "PySide6"]
    except ImportError:
        print("ERROR: neither PySide2 nor PySide6 is installed.", file=sys.stderr)
        sys.exit(1)
    return []


def _hidden_imports() -> list[str]:
    mods = [
        "remote_desktop",
        "remote_desktop.app_gui",
        "remote_desktop.client",
        "remote_desktop.host",
        "remote_desktop.clipboard_sync",
        "remote_desktop.confirm_dialog",
        "remote_desktop.app_icon",
        "remote_desktop.window_chrome",
        "remote_desktop.themes",
        "remote_desktop.qt_bind",
        "remote_desktop.qt_fonts",
        "remote_desktop.i18n",
        "remote_desktop.devices",
        "remote_desktop.capture",
        "remote_desktop.codec",
        "remote_desktop.input_io",
        "remote_desktop.net",
        "remote_desktop.protocol",
        "mss",
        "PIL",
        "pynput",
    ]
    system = platform.system().lower()
    if system == "windows":
        mods.extend(["pynput.keyboard._win32", "pynput.mouse._win32"])
    elif system == "darwin":
        mods.extend(["pynput.keyboard._darwin", "pynput.mouse._darwin"])
    else:
        mods.extend(["pynput.keyboard._xorg", "pynput.mouse._xorg"])

    out: list[str] = []
    for m in mods:
        out.extend(["--hidden-import", m])
    return out


def _find_iscc() -> Path | None:
    env = os.environ.get("INNO_SETUP_ISCC") or os.environ.get("ISCC")
    if env:
        path = Path(env)
        if path.is_file():
            return path

    which = shutil.which("ISCC") or shutil.which("iscc")
    if which:
        return Path(which)

    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
        / "Inno Setup 6"
        / "ISCC.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Inno Setup 6" / "ISCC.exe",
        Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
        Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def _build_installer(version: str) -> int:
    iscc = _find_iscc()
    if iscc is None:
        print("ERROR: Inno Setup compiler (ISCC.exe) not found.", file=sys.stderr)
        print("Install Inno Setup 6, then re-run with --installer:", file=sys.stderr)
        print("  winget install --id JRSoftware.InnoSetup -e", file=sys.stderr)
        print("Or set INNO_SETUP_ISCC to the full path of ISCC.exe.", file=sys.stderr)
        return 2

    app_dir = DIST / NAME
    exe = app_dir / ("%s.exe" % NAME)
    if not exe.is_file():
        print("ERROR: missing PyInstaller output:", exe, file=sys.stderr)
        return 1

    # Forward slashes avoid Inno Setup /D backslash-escape issues on Windows.
    repo_root = str(ROOT).replace("\\", "/")
    cmd = [
        str(iscc),
        "/DMyAppVersion=%s" % version,
        "/DMyAppName=%s" % NAME,
        "/DRepoRoot=%s" % repo_root,
        str(ISS),
    ]
    print("Running :", " ".join(cmd))
    print()
    proc = subprocess.run(cmd, cwd=str(ROOT))
    if proc.returncode != 0:
        return proc.returncode

    setup = DIST / ("%s-Setup-%s.exe" % (NAME, version))
    if setup.exists():
        print("OK — Windows installer:", setup)
    else:
        print("OK — installer build finished (check dist/)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build LeafLink executable / Windows installer")
    parser.add_argument(
        "--console",
        action="store_true",
        help="show console window (also useful for host/client CLI)",
    )
    parser.add_argument("--clean", action="store_true", help="remove previous build/dist first")
    parser.add_argument(
        "--onefile",
        action="store_true",
        help="single-file portable exe (slower startup; installer still uses onedir)",
    )
    parser.add_argument(
        "--installer",
        action="store_true",
        help="Windows only: build Setup.exe installer with Inno Setup after PyInstaller",
    )
    parser.add_argument(
        "--installer-only",
        action="store_true",
        help="Windows only: skip PyInstaller and only compile the Inno Setup script",
    )
    args = parser.parse_args(argv)

    version = _app_version()
    system = platform.system().lower()

    if args.installer or args.installer_only:
        if system != "windows":
            print("ERROR: --installer is only supported on Windows.", file=sys.stderr)
            return 1

    if args.installer_only:
        _ensure_app_ico()
        return _build_installer(version)

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("Install build deps first:", file=sys.stderr)
        print("  pip install -r requirements.txt -r requirements-build.txt", file=sys.stderr)
        return 1

    if args.clean:
        for path in (DIST, BUILD):
            if path.exists():
                shutil.rmtree(path, ignore_errors=True)

    # Installer packaging needs the onedir tree; --onefile is for portable builds only.
    use_onefile = bool(args.onefile) and not args.installer
    icon_ico = _ensure_app_ico()

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--name",
        NAME,
        "--paths",
        str(ROOT),
        "--distpath",
        str(DIST),
        "--workpath",
        str(BUILD),
        "--specpath",
        str(BUILD),
        "--onefile" if use_onefile else "--onedir",
    ]
    if not args.console:
        cmd.append("--windowed")
    if icon_ico is not None:
        cmd.extend(["--icon", str(icon_ico)])

    cmd.extend(_qt_collect_args())
    cmd.extend(["--collect-submodules", "remote_desktop"])
    cmd.extend(_hidden_imports())
    cmd.extend(_datas_args())
    cmd.append(str(ROOT / "main.py"))

    print("Platform:", platform.platform())
    print("Python  :", sys.version.split()[0])
    print("Version :", version)
    print("Running :", " ".join(cmd))
    print()

    proc = subprocess.run(cmd, cwd=str(ROOT))
    if proc.returncode != 0:
        return proc.returncode

    if system == "darwin":
        app = DIST / ("%s.app" % NAME)
        out = DIST / NAME
        print("OK — macOS app:", app if app.exists() else out)
    elif system == "windows":
        if use_onefile:
            print("OK — Windows portable exe:", DIST / ("%s.exe" % NAME))
        else:
            print("OK — Windows app folder:", DIST / NAME / ("%s.exe" % NAME))
    else:
        print("OK — Linux binary:", DIST / NAME / NAME if not use_onefile else DIST / NAME)
    print("Artifacts under:", DIST)

    if args.installer:
        print()
        return _build_installer(version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
