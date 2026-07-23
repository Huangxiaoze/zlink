from __future__ import annotations

import getpass
import json
import os
import platform
import socket
import sys
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from . import PROTOCOL_VERSION
from .config import DEFAULT_PORT


def detect_os_label() -> str:
    """Short OS category for device cards: Windows / macOS / Ubuntu / …"""
    system = platform.system()
    if system == "Windows":
        return "Windows"
    if system == "Darwin":
        return "macOS"
    if system == "Linux":
        return _linux_distro_label()
    return system or ""


def remote_username() -> str:
    """Login / display name of this machine (sent to controllers in HELLO_ACK)."""
    candidates: list[str] = []
    try:
        candidates.append(getpass.getuser())
    except Exception:
        pass
    for key in ("USERNAME", "USER", "LOGNAME"):
        val = os.environ.get(key)
        if val:
            candidates.append(str(val))
    try:
        candidates.append(socket.gethostname())
    except Exception:
        pass
    for raw in candidates:
        name = str(raw or "").strip()
        if name and name.lower() not in {".", "localhost"}:
            return name[:64]
    return "Remote"


def _linux_distro_label() -> str:
    try:
        text = Path("/etc/os-release").read_text(encoding="utf-8")
    except OSError:
        return "Linux"
    data: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key] = value.strip().strip('"')
    distro_id = (data.get("ID") or "").lower()
    mapping = {
        "ubuntu": "Ubuntu",
        "debian": "Debian",
        "fedora": "Fedora",
        "arch": "Arch",
        "centos": "CentOS",
        "rhel": "RHEL",
        "opensuse": "openSUSE",
        "opensuse-leap": "openSUSE",
        "opensuse-tumbleweed": "openSUSE",
        "linuxmint": "Linux Mint",
        "kali": "Kali",
        "raspbian": "Raspberry Pi OS",
        "raspberrypi": "Raspberry Pi OS",
        "pop": "Pop!_OS",
        "elementary": "elementary OS",
        "manjaro": "Manjaro",
    }
    if distro_id in mapping:
        return mapping[distro_id]
    for like in (data.get("ID_LIKE") or "").lower().split():
        if like in mapping:
            return mapping[like]
    pretty = (data.get("NAME") or data.get("PRETTY_NAME") or "").strip()
    if pretty:
        return pretty.split()[0][:32]
    return "Linux"


def app_data_dir() -> Path:
    if os.name == "nt":
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    path = root / "remote_desktop"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class Device:
    id: str
    name: str
    host: str
    port: int = DEFAULT_PORT
    password: str = ""
    notes: str = ""
    os_name: str = ""
    last_connected: float | None = None
    created_at: float = field(default_factory=time.time)

    @staticmethod
    def create(
        name: str,
        host: str,
        port: int = DEFAULT_PORT,
        password: str = "",
        notes: str = "",
        os_name: str = "",
    ) -> Device:
        return Device(
            id=uuid.uuid4().hex,
            name=name.strip() or host.strip(),
            host=host.strip(),
            port=DEFAULT_PORT,
            password=password,
            notes=notes.strip(),
            os_name=(os_name or "").strip(),
        )


@dataclass
class AppSettings:
    host_bind: str = "0.0.0.0"
    host_port: int = DEFAULT_PORT
    host_password: str = ""
    local_name: str = ""
    device_code: str = ""
    max_fps: float = 30.0
    jpeg_quality: int = 95
    scale: float = 1.0
    auto_probe_s: float = 8.0
    language: str = "zh_CN"
    theme: str = "light"
    # Bump when default stream quality changes so old installs get upgraded once.
    settings_version: int = 3


class DeviceStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (app_data_dir() / "devices.json")
        self.settings = AppSettings()
        self.devices: list[Device] = []
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            self.settings.local_name = socket.gethostname()
            self.settings.device_code = _make_device_code()
            if not self.settings.host_password:
                self.settings.host_password = _make_verify_code()
            self.save()
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}
        settings = raw.get("settings") or {}
        lang = str(settings.get("language") or "zh_CN")
        if lang not in {"zh_CN", "en_US"}:
            lang = "zh_CN"
        from .themes import DEFAULT_THEME, theme_ids

        theme = str(settings.get("theme") or DEFAULT_THEME)
        if theme not in set(theme_ids()):
            theme = DEFAULT_THEME
        version = int(settings.get("settings_version") or 0)
        jpeg_quality = int(settings.get("jpeg_quality", 95))
        scale = float(settings.get("scale", 1.0))
        max_fps = float(settings.get("max_fps", 30.0))
        # Migrate old soft defaults (0.75 / q60) to HD once.
        if version < 2 and jpeg_quality <= 70 and scale <= 0.85:
            jpeg_quality = 90
            scale = 1.0
            version = 2
        # v3: stop under-serving LAN — raise quality floor for prior HD defaults.
        if version < 3 and jpeg_quality <= 90 and scale >= 0.99:
            jpeg_quality = 95
            scale = 1.0
            version = 3
        self.settings = AppSettings(
            host_bind=str(settings.get("host_bind", "0.0.0.0")),
            host_port=DEFAULT_PORT,
            host_password=str(settings.get("host_password", "")),
            local_name=str(settings.get("local_name") or socket.gethostname()),
            device_code=str(settings.get("device_code") or _make_device_code()),
            max_fps=max_fps,
            jpeg_quality=jpeg_quality,
            scale=scale,
            auto_probe_s=float(settings.get("auto_probe_s", 8.0)),
            language=lang,
            theme=theme,
            settings_version=max(version, 3),
        )
        if not self.settings.host_password:
            self.settings.host_password = _make_verify_code()
        if int(settings.get("settings_version") or 0) < 3:
            self.save()
        self.devices = []
        for item in raw.get("devices") or []:
            try:
                self.devices.append(
                    Device(
                        id=str(item.get("id") or uuid.uuid4().hex),
                        name=str(item.get("name") or item.get("host") or "device"),
                        host=str(item.get("host") or ""),
                        port=DEFAULT_PORT,
                        password=str(item.get("password") or ""),
                        notes=str(item.get("notes") or ""),
                        os_name=str(item.get("os_name") or ""),
                        last_connected=item.get("last_connected"),
                        created_at=float(item.get("created_at") or time.time()),
                    )
                )
            except (TypeError, ValueError):
                continue

    def save(self) -> None:
        self.settings.host_port = DEFAULT_PORT
        for device in self.devices:
            device.port = DEFAULT_PORT
        payload: dict[str, Any] = {
            "settings": asdict(self.settings),
            "devices": [asdict(d) for d in self.devices],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(payload, ensure_ascii=False, indent=2)
        fd, tmp_name = tempfile.mkstemp(prefix="devices_", suffix=".json", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(data)
            os.replace(tmp_name, self.path)
        finally:
            if os.path.exists(tmp_name):
                try:
                    os.remove(tmp_name)
                except OSError:
                    pass

    def upsert(self, device: Device) -> None:
        device.port = DEFAULT_PORT
        for i, existing in enumerate(self.devices):
            if existing.id == device.id:
                self.devices[i] = device
                self.save()
                return
        self.devices.append(device)
        self.save()

    def remove(self, device_id: str) -> bool:
        before = len(self.devices)
        self.devices = [d for d in self.devices if d.id != device_id]
        if len(self.devices) != before:
            self.save()
            return True
        return False

    def get(self, device_id: str) -> Device | None:
        for device in self.devices:
            if device.id == device_id:
                return device
        return None

    def touch_connected(self, device_id: str) -> None:
        device = self.get(device_id)
        if not device:
            return
        device.last_connected = time.time()
        self.save()


def list_local_ipv4() -> list[str]:
    ips: list[str] = []
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if ip and not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
    except OSError:
        pass
    # Fallback: UDP trick for default route IP
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            ip = sock.getsockname()[0]
            if ip and not ip.startswith("127.") and ip not in ips:
                ips.insert(0, ip)
    except OSError:
        pass
    return ips or ["127.0.0.1"]


def probe_device(host: str, port: int, timeout_s: float = 0.8) -> tuple[bool, str]:
    """Probe host liveness and read OS label from HELLO_ACK (no auth required)."""
    from .net import connect_to
    from .protocol import MsgType, decode_json

    conn = None
    try:
        conn = connect_to(str(host), int(port), float(timeout_s), 64 * 1024)
        conn.send_json(
            MsgType.HELLO,
            {
                "role": "probe",
                "version": PROTOCOL_VERSION,
                "password": "",
            },
        )
        frame = conn.recv_frame()
        if int(frame.type) != int(MsgType.HELLO_ACK):
            return True, ""
        ack = decode_json(frame.payload)
        os_name = str(ack.get("os") or "").strip()
        return True, os_name
    except Exception:
        return False, ""
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def probe_online(host: str, port: int, timeout_s: float = 0.8) -> bool:
    online, _os_name = probe_device(host, port, timeout_s=timeout_s)
    return online


def make_device_code() -> str:
    # 9-digit sunflower-like identification code (local only; not a relay ID)
    return f"{uuid.uuid4().int % 10**9:09d}"


def make_verify_code() -> str:
    return f"{uuid.uuid4().int % 10**6:06d}"


# Keep private aliases for older call sites in this module.
_make_device_code = make_device_code
_make_verify_code = make_verify_code
