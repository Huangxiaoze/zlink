from __future__ import annotations

from dataclasses import dataclass

# Fixed listen/connect port for GUI and default CLI usage.
DEFAULT_PORT = 5959


@dataclass
class StreamConfig:
    # HD defaults: full resolution + high JPEG quality for sharp remote view.
    max_fps: float = 30.0
    jpeg_quality: int = 95
    scale: float = 1.0
    min_jpeg_quality: int = 55
    max_jpeg_quality: int = 98
    min_scale: float = 0.6
    max_scale: float = 1.0

    def clamp(self) -> StreamConfig:
        self.jpeg_quality = max(self.min_jpeg_quality, min(self.max_jpeg_quality, int(self.jpeg_quality)))
        self.scale = max(self.min_scale, min(self.max_scale, float(self.scale)))
        self.max_fps = max(1.0, min(60.0, float(self.max_fps)))
        return self


@dataclass
class NetConfig:
    host: str = "0.0.0.0"
    port: int = DEFAULT_PORT
    password: str = ""
    # Longer timeout: HD frames can take seconds on weak links; mid-transfer
    # progress now counts as activity, but keep generous margin anyway.
    heartbeat_interval_s: float = 3.0
    heartbeat_timeout_s: float = 25.0
    connect_timeout_s: float = 10.0
    frame_queue_size: int = 2
    max_payload: int = 16 * 1024 * 1024
    recv_buffer: int = 2 * 1024 * 1024


@dataclass
class HostConfig:
    net: NetConfig
    stream: StreamConfig
    bind_require_password: bool = True


@dataclass
class ClientConfig:
    net: NetConfig
    stream: StreamConfig
    window_title: str = "ZLink"
    reconnect: bool = True
    reconnect_max_s: float = 15.0
