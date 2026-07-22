"""Dedicated remote file transfer (chunked), separate from clipboard sync."""

from __future__ import annotations

import logging
import os
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Callable, Optional

from .protocol import pack_file_message, unpack_file_message

log = logging.getLogger(__name__)

MAX_FILE_BYTES = 64 * 1024 * 1024
CHUNK_SIZE = 256 * 1024
FEATURE_FILE_TRANSFER = "file_transfer"


def transfer_dir() -> Path:
    """Prefer the user's Downloads/LeafLink folder; fall back to temp."""
    home = Path.home()
    for candidate in (
        home / "Downloads" / "LeafLink",
        home / "下载" / "LeafLink",
    ):
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        except OSError:
            continue
    path = Path(tempfile.gettempdir()) / "leaflink_transfer"
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_name(name: str) -> str:
    base = os.path.basename(name.replace("\\", "/")).strip() or "file.bin"
    return "".join(ch if ch not in '<>:"|?*' else "_" for ch in base)[:180]


def unique_dest(folder: Path, name: str) -> Path:
    dest = folder / name
    if not dest.exists():
        return dest
    stem = dest.stem
    suffix = dest.suffix
    for i in range(1, 1000):
        cand = folder / ("%s (%d)%s" % (stem, i, suffix))
        if not cand.exists():
            return cand
    return folder / ("%s_%s%s" % (stem, uuid.uuid4().hex[:6], suffix))


def send_file(
    path: Path | str,
    send_packet: Callable[[bytes], None],
    *,
    on_progress: Optional[Callable[[str, int, int], None]] = None,
    should_stop: Optional[Callable[[], bool]] = None,
) -> Path:
    """Send one local file as FILE chunks. Returns the path that was sent."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(str(path))
    size = path.stat().st_size
    if size > MAX_FILE_BYTES:
        raise ValueError("file too large: %s bytes (max %s)" % (size, MAX_FILE_BYTES))

    file_id = uuid.uuid4().hex
    name = safe_name(path.name)
    offset = 0
    with path.open("rb") as fh:
        while True:
            if should_stop is not None and should_stop():
                raise InterruptedError("file transfer cancelled")
            chunk = fh.read(CHUNK_SIZE)
            if not chunk and offset == 0:
                packet = pack_file_message(
                    {
                        "op": "chunk",
                        "id": file_id,
                        "name": name,
                        "size": 0,
                        "offset": 0,
                        "done": True,
                    },
                    b"",
                )
                send_packet(packet)
                if on_progress is not None:
                    on_progress(name, 0, 0)
                break
            if not chunk:
                break
            done = offset + len(chunk) >= size
            packet = pack_file_message(
                {
                    "op": "chunk",
                    "id": file_id,
                    "name": name,
                    "size": int(size),
                    "offset": int(offset),
                    "done": bool(done),
                },
                chunk,
            )
            send_packet(packet)
            offset += len(chunk)
            if on_progress is not None:
                on_progress(name, offset, size)
            if done:
                break
    log.info("file sent: %s (%d bytes)", name, size)
    return path


class FileAssembler:
    """Reassemble incoming FILE chunks onto disk under transfer_dir()."""

    def __init__(
        self,
        *,
        on_progress: Optional[Callable[[str, int, int], None]] = None,
        on_complete: Optional[Callable[[Path], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._on_progress = on_progress
        self._on_complete = on_complete
        self._on_error = on_error
        self._incoming: dict[str, dict] = {}
        self._lock = threading.Lock()

    def clear(self) -> None:
        with self._lock:
            for state in self._incoming.values():
                fh = state.get("fh")
                path = state.get("path")
                try:
                    if fh is not None:
                        fh.close()
                except Exception:
                    pass
                if path is not None:
                    try:
                        Path(path).unlink(missing_ok=True)  # type: ignore[arg-type]
                    except TypeError:
                        try:
                            p = Path(path)
                            if p.exists():
                                p.unlink()
                        except OSError:
                            pass
                    except OSError:
                        pass
            self._incoming.clear()

    def handle_payload(self, payload: bytes) -> Optional[Path]:
        try:
            meta, blob = unpack_file_message(payload)
        except Exception:
            log.exception("bad file payload")
            if self._on_error is not None:
                self._on_error("bad file payload")
            return None

        op = str(meta.get("op") or "chunk")
        if op == "cancel":
            file_id = str(meta.get("id") or "")
            self._drop(file_id)
            return None
        if op != "chunk":
            log.debug("ignore file op=%s", op)
            return None
        return self._apply_chunk(meta, blob)

    def _drop(self, file_id: str) -> None:
        if not file_id:
            return
        with self._lock:
            state = self._incoming.pop(file_id, None)
        if state is None:
            return
        try:
            state["fh"].close()
        except Exception:
            pass
        try:
            Path(state["path"]).unlink(missing_ok=True)  # type: ignore[arg-type]
        except TypeError:
            p = Path(state["path"])
            if p.exists():
                p.unlink()
        except OSError:
            pass

    def _apply_chunk(self, meta: dict, blob: bytes) -> Optional[Path]:
        file_id = str(meta.get("id") or "")
        name = safe_name(str(meta.get("name") or "file.bin"))
        size = int(meta.get("size") or 0)
        offset = int(meta.get("offset") or 0)
        done = bool(meta.get("done"))
        if not file_id or size < 0 or size > MAX_FILE_BYTES:
            if self._on_error is not None:
                self._on_error("invalid file meta")
            return None

        completed: Optional[Path] = None
        with self._lock:
            state = self._incoming.get(file_id)
            if state is None:
                dest = unique_dest(transfer_dir(), name)
                try:
                    fh = dest.open("wb")
                except OSError as exc:
                    log.exception("cannot create transfer file")
                    if self._on_error is not None:
                        self._on_error(str(exc))
                    return None
                state = {
                    "name": name,
                    "size": size,
                    "path": dest,
                    "received": 0,
                    "fh": fh,
                }
                self._incoming[file_id] = state

            if offset != state["received"]:
                log.warning(
                    "file offset mismatch id=%s expect=%s got=%s",
                    file_id,
                    state["received"],
                    offset,
                )
            state["fh"].write(blob)
            state["received"] = offset + len(blob)
            received = int(state["received"])
            total = int(state["size"])
            if done or (total > 0 and received >= total):
                state["fh"].close()
                completed = Path(state["path"])
                del self._incoming[file_id]

        if self._on_progress is not None and completed is None:
            self._on_progress(name, min(received, total or received), total or received)
        if completed is not None:
            log.info("file received: %s", completed)
            if self._on_progress is not None:
                self._on_progress(name, size, size)
            if self._on_complete is not None:
                self._on_complete(completed)
        return completed
