from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Any


MAGIC = b"RD01"
HEADER_STRUCT = struct.Struct("!4sBBI")  # magic, type, flags, length
HEADER_SIZE = HEADER_STRUCT.size


class MsgType(IntEnum):
    HELLO = 1
    HELLO_ACK = 2
    FRAME = 3
    MOUSE = 4
    KEY = 5
    QUALITY = 6
    HEARTBEAT = 7
    BYE = 8


class ProtocolError(ValueError):
    """Invalid or oversized protocol frame."""


@dataclass(slots=True)
class Frame:
    type: MsgType
    payload: bytes
    flags: int = 0


def pack_frame(msg_type: MsgType, payload: bytes = b"", flags: int = 0) -> bytes:
    if len(payload) > 16 * 1024 * 1024:
        raise ProtocolError("payload too large")
    return HEADER_STRUCT.pack(MAGIC, int(msg_type), flags, len(payload)) + payload


def pack_json(msg_type: MsgType, data: dict[str, Any], flags: int = 0) -> bytes:
    return pack_frame(msg_type, json.dumps(data, separators=(",", ":")).encode("utf-8"), flags)


def unpack_header(header: bytes) -> tuple[MsgType, int, int]:
    if len(header) != HEADER_SIZE:
        raise ProtocolError("short header")
    magic, msg_type, flags, length = HEADER_STRUCT.unpack(header)
    if magic != MAGIC:
        raise ProtocolError("bad magic")
    try:
        typed = MsgType(msg_type)
    except ValueError as exc:
        raise ProtocolError(f"unknown type {msg_type}") from exc
    return typed, flags, length


def decode_json(payload: bytes) -> dict[str, Any]:
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError("invalid json payload") from exc
    if not isinstance(data, dict):
        raise ProtocolError("json payload must be object")
    return data


def pack_frame_message(
    jpeg: bytes,
    *,
    width: int,
    height: int,
    seq: int,
    quality: int,
    scale: float,
) -> bytes:
    meta = {
        "w": width,
        "h": height,
        "seq": seq,
        "q": quality,
        "scale": scale,
    }
    payload = json.dumps(meta, separators=(",", ":")).encode("utf-8") + b"\n\n" + jpeg
    return pack_frame(MsgType.FRAME, payload)


def unpack_frame_message(payload: bytes) -> tuple[dict[str, Any], bytes]:
    sep = payload.find(b"\n\n")
    if sep < 0:
        raise ProtocolError("frame missing meta separator")
    meta = decode_json(payload[:sep])
    return meta, payload[sep + 2 :]
