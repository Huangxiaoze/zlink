#!/usr/bin/env python3
"""Build ZLink for the current platform with PyInstaller.

Usage (from repo root `remote/`):
  python scripts/build.py
  python scripts/build.py --console          # keep terminal window (debug / CLI)
  python scripts/build.py --clean
  python scripts/build.py --onefile          # single portable exe (slower start)
  python scripts/build.py --installer        # Windows: also build Setup.exe (Inno Setup)
  python scripts/build.py --deb              # Linux: also build .deb package
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
BUILD = ROOT / "build"
SCRIPTS = ROOT / "scripts"
NAME = "ZLink"
PKG_NAME = "zlink"
ISS = SCRIPTS / "windows" / "zlink.iss"
ICON_PNG = ROOT / "resources" / "icon" / "app.png"
ICON_ICO = ROOT / "resources" / "icon" / "app.ico"
OPT_DIR = "/opt/%s" % PKG_NAME


def _app_version() -> str:
    init_py = ROOT / "remote_desktop" / "__init__.py"
    text = init_py.read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("__version__"):
            return line.split("=", 1)[1].strip().strip("\"'")
    return "0.0.0"


def _ensure_app_ico() -> Path | None:
    """Build a multi-size .ico from app.png for Windows exe / installer."""
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
        "remote_desktop.toggle_switch",
        "remote_desktop.file_transfer",
        "remote_desktop.remote_files",
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


def _deb_arch() -> str:
    machine = platform.machine().lower()
    return {
        "x86_64": "amd64",
        "amd64": "amd64",
        "aarch64": "arm64",
        "arm64": "arm64",
        "armv7l": "armhf",
        "armv6l": "armhf",
        "i686": "i386",
        "i386": "i386",
    }.get(machine, machine)


def _write_text(path: Path, text: str, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(mode)


def _dir_size_kb(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            fp = Path(root) / name
            try:
                total += fp.stat().st_size
            except OSError:
                pass
    return max(1, (total + 1023) // 1024)


def _build_deb(version: str) -> int:
    """Assemble a Debian package from the PyInstaller onedir tree."""
    if shutil.which("dpkg-deb") is None:
        print("ERROR: dpkg-deb not found. Install packaging tools:", file=sys.stderr)
        print("  sudo apt install -y dpkg-dev", file=sys.stderr)
        return 2

    app_dir = DIST / NAME
    binary = app_dir / NAME
    if not binary.is_file():
        print("ERROR: missing PyInstaller output:", binary, file=sys.stderr)
        print("Build the Linux onedir first (without --onefile).", file=sys.stderr)
        return 1

    arch = _deb_arch()
    stage = DIST / ("deb-root-%s" % PKG_NAME)
    if stage.exists():
        shutil.rmtree(stage)

    opt = stage / "opt" / PKG_NAME
    bin_dir = stage / "usr" / "bin"
    apps = stage / "usr" / "share" / "applications"
    pixmaps = stage / "usr" / "share" / "pixmaps"
    icons = stage / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps"
    doc = stage / "usr" / "share" / "doc" / PKG_NAME
    debian = stage / "DEBIAN"

    shutil.copytree(app_dir, opt, symlinks=True)
    # Ensure the main binary is executable after copy.
    binary_dst = opt / NAME
    binary_dst.chmod(binary_dst.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    _write_text(
        bin_dir / PKG_NAME,
        textwrap.dedent(
            """\
            #!/bin/sh
            exec %s/%s "$@"
            """
            % (OPT_DIR, NAME)
        ),
        mode=0o755,
    )

    _write_text(
        apps / ("%s.desktop" % PKG_NAME),
        textwrap.dedent(
            """\
            [Desktop Entry]
            Type=Application
            Version=1.0
            Name=%s
            GenericName=Remote Desktop
            Comment=Cross-platform remote desktop (host + client)
            Exec=%s
            Icon=%s
            Terminal=false
            Categories=Network;RemoteAccess;
            StartupNotify=true
            """
            % (NAME, PKG_NAME, PKG_NAME)
        ),
    )

    if ICON_PNG.is_file():
        icons.mkdir(parents=True, exist_ok=True)
        pixmaps.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ICON_PNG, icons / ("%s.png" % PKG_NAME))
        shutil.copy2(ICON_PNG, pixmaps / ("%s.png" % PKG_NAME))

    _write_text(
        doc / "copyright",
        textwrap.dedent(
            """\
            Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
            Upstream-Name: %s
            Source: https://github.com/Huangxiaoze/remote_desktop

            Files: *
            Copyright: ZLink contributors
            License: Proprietary
             See the upstream repository for license terms.
            """
            % NAME
        ),
    )

    installed_size = _dir_size_kb(stage)
    control = textwrap.dedent(
        """\
        Package: %s
        Version: %s
        Section: net
        Priority: optional
        Architecture: %s
        Maintainer: ZLink Maintainers <zlink@users.noreply.github.com>
        Installed-Size: %d
        Depends: libc6, libx11-6, libxcb1, libxkbcommon0, libxkbcommon-x11-0, libxcb-xinerama0, libglib2.0-0, libdbus-1-3, libfontconfig1, libfreetype6, libxrender1, libxi6, libsm6, libice6, libgl1 | libgl1-mesa-glx
        Recommends: fonts-noto-cjk | fonts-wqy-microhei
        Homepage: https://github.com/Huangxiaoze/remote_desktop
        Description: Cross-platform remote desktop (host + client)
         ZLink provides a Qt device-manager GUI for hosting and
         controlling remote desktops over a direct TCP connection.
        """
        % (PKG_NAME, version, arch, installed_size)
    )
    _write_text(debian / "control", control)

    _write_text(
        debian / "postinst",
        textwrap.dedent(
            """\
            #!/bin/sh
            set -e
            if command -v update-desktop-database >/dev/null 2>&1; then
              update-desktop-database -q /usr/share/applications || true
            fi
            if command -v gtk-update-icon-cache >/dev/null 2>&1; then
              gtk-update-icon-cache -q /usr/share/icons/hicolor 2>/dev/null || true
            fi
            exit 0
            """
        ),
        mode=0o755,
    )
    _write_text(
        debian / "postrm",
        textwrap.dedent(
            """\
            #!/bin/sh
            set -e
            if [ "$1" = remove ] || [ "$1" = purge ]; then
              if command -v update-desktop-database >/dev/null 2>&1; then
                update-desktop-database -q /usr/share/applications || true
              fi
              if command -v gtk-update-icon-cache >/dev/null 2>&1; then
                gtk-update-icon-cache -q /usr/share/icons/hicolor 2>/dev/null || true
              fi
            fi
            exit 0
            """
        ),
        mode=0o755,
    )

    deb_name = "%s_%s_%s.deb" % (PKG_NAME, version, arch)
    deb_path = DIST / deb_name
    if deb_path.exists():
        deb_path.unlink()

    cmd = ["dpkg-deb", "--root-owner-group", "-Zxz", "-b", str(stage), str(deb_path)]
    print("Running :", " ".join(cmd))
    print()
    proc = subprocess.run(cmd, cwd=str(ROOT))
    if proc.returncode != 0:
        # Older dpkg-deb (Ubuntu 18.04) may lack --root-owner-group.
        if "--root-owner-group" in cmd:
            cmd = ["dpkg-deb", "-Zxz", "-b", str(stage), str(deb_path)]
            print("Retrying without --root-owner-group ...")
            proc = subprocess.run(cmd, cwd=str(ROOT))
        if proc.returncode != 0:
            return proc.returncode

    print("OK — Debian package:", deb_path)
    print("Install with: sudo apt install ./%s" % deb_path.name)
    print("          or: sudo dpkg -i %s && sudo apt-get install -f -y" % deb_path)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build ZLink executable / Windows installer / Ubuntu .deb"
    )
    parser.add_argument(
        "--console",
        action="store_true",
        help="show console window (also useful for host/client CLI)",
    )
    parser.add_argument("--clean", action="store_true", help="remove previous build/dist first")
    parser.add_argument(
        "--onefile",
        action="store_true",
        help="single-file portable exe (slower startup; installer/deb still use onedir)",
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
    parser.add_argument(
        "--deb",
        action="store_true",
        help="Linux only: build a .deb package after PyInstaller",
    )
    parser.add_argument(
        "--deb-only",
        action="store_true",
        help="Linux only: skip PyInstaller and only assemble .deb from dist/ZLink",
    )
    args = parser.parse_args(argv)

    version = _app_version()
    system = platform.system().lower()

    if args.installer or args.installer_only:
        if system != "windows":
            print("ERROR: --installer is only supported on Windows.", file=sys.stderr)
            return 1

    if args.deb or args.deb_only:
        if system != "linux":
            print("ERROR: --deb is only supported on Linux.", file=sys.stderr)
            return 1

    if args.installer_only:
        _ensure_app_ico()
        return _build_installer(version)

    if args.deb_only:
        return _build_deb(version)

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

    # Installer / deb packaging needs the onedir tree; --onefile is portable-only.
    use_onefile = bool(args.onefile) and not args.installer and not args.deb
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
    if args.deb:
        print()
        return _build_deb(version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
