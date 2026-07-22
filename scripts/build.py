#!/usr/bin/env python3
"""Build a LeafLink executable for the current platform with PyInstaller.

Usage (from repo root `remote/`):
  python scripts/build.py
  python scripts/build.py --console   # keep terminal window (debug / CLI)
  python scripts/build.py --clean
"""

from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
BUILD = ROOT / "build"
NAME = "LeafLink"


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build LeafLink executable")
    parser.add_argument(
        "--console",
        action="store_true",
        help="show console window (also useful for host/client CLI)",
    )
    parser.add_argument("--clean", action="store_true", help="remove previous build/dist first")
    args = parser.parse_args(argv)

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

    system = platform.system().lower()
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
        "--onedir",
    ]
    if not args.console:
        cmd.append("--windowed")

    cmd.extend(_qt_collect_args())
    cmd.extend(["--collect-submodules", "remote_desktop"])
    cmd.extend(_hidden_imports())
    cmd.append(str(ROOT / "main.py"))

    print("Platform:", platform.platform())
    print("Python  :", sys.version.split()[0])
    print("Running :", " ".join(cmd))
    print()

    proc = subprocess.run(cmd, cwd=str(ROOT))
    if proc.returncode != 0:
        return proc.returncode

    out = DIST / NAME
    if system == "darwin":
        app = DIST / ("%s.app" % NAME)
        print("OK — macOS app:", app if app.exists() else out)
    elif system == "windows":
        print("OK — Windows exe:", out / ("%s.exe" % NAME))
    else:
        print("OK — Linux binary:", out / NAME)
    print("Artifacts under:", DIST)
    return 0


if __name__ == "__main__":
    sys.exit(main())
