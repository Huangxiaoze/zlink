from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class StreamConfig:
    max_fps: float = 30.0
    jpeg_quality: int = 60
    scale: float = 0.75
    min_jpeg_quality: int = 30
    max_jpeg_quality: int = 85
    min_scale: float = 0.4
    max_scale: float = 1.0

    def clamp(self) -> StreamConfig:
        self.jpeg_quality = max(self.min_jpeg_quality, min(self.max_jpeg_quality, int(self.jpeg_quality)))
        self.scale = max(self.min_scale, min(self.max_scale, float(self.scale)))
        self.max_fps = max(1.0, min(60.0, float(self.max_fps)))
        return self


@dataclass(slots=True)
class NetConfig:
    host: str = "0.0.0.0"
    port: int = 5959
    password: str = ""
    heartbeat_interval_s: float = 2.0
    heartbeat_timeout_s: float = 8.0
    connect_timeout_s: float = 8.0
    frame_queue_size: int = 2
    max_payload: int = 16 * 1024 * 1024
    recv_buffer: int = 256 * 1024


@dataclass(slots=True)
class HostConfig:
    net: NetConfig
    stream: StreamConfig
    bind_require_password: bool = True


@dataclass(slots=True)
class ClientConfig:
    net: NetConfig
    stream: StreamConfig
    window_title: str = "Remote Desktop"
    reconnect: bool = True
    reconnect_max_s: float = 15.0
