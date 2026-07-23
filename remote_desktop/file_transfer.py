"""Dedicated remote file transfer (chunked), separate from clipboard sync."""

from __future__ import annotations

import logging
import os
import platform
import string
import tempfile
import threading
import time
import uuid
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Callable, Optional

from .protocol import pack_file_message, unpack_file_message

log = logging.getLogger(__name__)

MAX_FILE_BYTES = 64 * 1024 * 1024
CHUNK_SIZE = 256 * 1024
MAX_LIST_ENTRIES = 400
FEATURE_FILE_TRANSFER = "file_transfer"


def transfer_dir() -> Path:
    """Prefer the user's Downloads/ZLink folder; fall back to temp."""
    home = Path.home()
    for candidate in (
        home / "Downloads" / "ZLink",
        home / "下载" / "ZLink",
    ):
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        except OSError:
            continue
    path = Path(tempfile.gettempdir()) / "zlink_transfer"
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_name(name: str) -> str:
    base = os.path.basename(name.replace("\\", "/")).strip() or "file.bin"
    return "".join(ch if ch not in '<>:"|?*' else "_" for ch in base)[:180]


def pack_list_request(path: str = "") -> bytes:
    return pack_file_message({"op": "list", "path": str(path or "")}, b"")


def pack_list_result(
    path: str,
    entries: list[dict[str, Any]] | None = None,
    *,
    error: str = "",
) -> bytes:
    if error:
        return pack_file_message(
            {"op": "list_err", "path": str(path or ""), "error": str(error)},
            b"",
        )
    return pack_file_message(
        {
            "op": "list_ok",
            "path": str(path or ""),
            "entries": list(entries or []),
        },
        b"",
    )


def pack_download_request(path: str) -> bytes:
    return pack_file_message({"op": "download", "path": str(path)}, b"")


def pack_download_error(path: str, error: str) -> bytes:
    return pack_file_message(
        {"op": "download_err", "path": str(path or ""), "error": str(error)},
        b"",
    )


# Win32 FILE_ATTRIBUTE_* bits (from GetFileAttributes / DirEntry.stat).
_FILE_ATTRIBUTE_HIDDEN = 0x2
_FILE_ATTRIBUTE_SYSTEM = 0x4
# Soft safety cap while scanning huge folders (sorted before trimming).
_MAX_SCAN_ENTRIES = 5000


def _is_windows() -> bool:
    return platform.system().lower() == "windows"


def _windows_drive_letters() -> list[str]:
    """Return present drive letters without touching each volume (avoids DVD/network hangs)."""
    try:
        import ctypes

        mask = int(ctypes.windll.kernel32.GetLogicalDrives())  # type: ignore[attr-defined]
    except Exception:
        # Fallback: only common fixed letters, never probe A: / empty optical drives.
        return [ch for ch in "CDEFGHIJKLMNOPQRSTUVWXYZ"]
    letters: list[str] = []
    for idx, ch in enumerate(string.ascii_uppercase):
        if mask & (1 << idx):
            letters.append(ch)
    return letters


def _normalize_windows_path_text(text: str) -> str:
    """Fix controller/host path quirks so Windows listing targets the right folder.

    Important: bare ``C:`` is *not* the drive root on Windows — Path('C:') is
    relative to the process cwd on that drive, which makes the browser show a
    completely wrong folder.
    """
    text = (text or "").strip().strip('"')
    if not text:
        return text
    # Controllers may send POSIX separators.
    text = text.replace("/", "\\")
    # ``C:`` → ``C:\`` (drive root).
    if len(text) == 2 and text[0].isalpha() and text[1] == ":":
        return text[0].upper() + ":\\"
    # ``C:Users\...`` (missing slash after drive) → ``C:\Users\...``
    if len(text) >= 3 and text[0].isalpha() and text[1] == ":" and text[2] != "\\":
        text = text[0].upper() + ":\\" + text[2:]
    # Keep drive roots with a trailing slash (``C:`` / ``C:.`` style).
    if len(text) == 2 and text[1] == ":":
        text += "\\"
    return text


def path_to_remote_str(path: Path | str) -> str:
    """Serialize a host path for the FILE protocol (stable Windows drive roots)."""
    if isinstance(path, Path):
        text = str(path)
    else:
        text = str(path or "")
    if _is_windows():
        text = _normalize_windows_path_text(text)
        if len(text) == 2 and text[1] == ":":
            text += "\\"
    return text


def browse_roots() -> list[dict[str, Any]]:
    """Top-level browse targets on the host OS."""
    roots: list[dict[str, Any]] = []
    if _is_windows():
        for letter in _windows_drive_letters():
            roots.append(
                {
                    "name": "%s:" % letter,
                    "path": "%s:\\" % letter,
                    "is_dir": True,
                    "size": 0,
                    "mtime": 0,
                }
            )
    else:
        roots.append(
            {
                "name": "/",
                "path": "/",
                "is_dir": True,
                "size": 0,
                "mtime": 0,
            }
        )
    home = Path.home()
    roots.append(
        {
            "name": home.name or str(home),
            "path": path_to_remote_str(home),
            "is_dir": True,
            "size": 0,
            "mtime": 0,
        }
    )
    return roots


def resolve_browse_path(path: str | None) -> Path:
    text = (path or "").strip().strip('"')
    if not text:
        return Path.home()
    if _is_windows():
        text = _normalize_windows_path_text(text)
    return Path(text).expanduser()


def remote_parent_path(path: str | None) -> str:
    """Parent of a remote path using the remote OS's path rules.

    Controllers must not use local ``Path(...).parent`` — on Windows that turns
    a Linux path like ``/home/u`` into ``\\home``, which then fails to list.
    Empty string means "browse roots".
    """
    text = (path or "").strip()
    if not text:
        return ""
    # POSIX absolute (exclude UNC ``//server/...``).
    if text.startswith("/") and not text.startswith("//"):
        p = PurePosixPath(text)
        parent = p.parent
        if parent == p:
            return ""
        return str(parent)
    looks_win = (
        (len(text) >= 2 and text[0].isalpha() and text[1] == ":")
        or text.startswith("\\\\")
        or text.startswith("//")
        or ("\\" in text)
    )
    if looks_win:
        text = text.replace("/", "\\")
        p = PureWindowsPath(text)
        parent = p.parent
        if parent == p:
            return ""
        out = str(parent)
        if len(out) == 2 and out[1] == ":":
            out += "\\"
        return out
    p = PurePosixPath(text)
    parent = p.parent
    if parent == p:
        return ""
    return str(parent)


def _entry_is_dir(entry: os.DirEntry) -> bool:
    """Directory check that also treats Windows junctions as folders."""
    try:
        if entry.is_dir(follow_symlinks=False):
            return True
    except TypeError:
        try:
            if entry.is_dir():
                return True
        except OSError:
            pass
    except OSError:
        pass
    try:
        is_junction = getattr(entry, "is_junction", None)
        if callable(is_junction) and bool(is_junction()):
            return True
    except OSError:
        pass
    try:
        if entry.is_symlink() and entry.is_dir(follow_symlinks=True):
            return True
    except (TypeError, OSError):
        pass
    return False


def _windows_hidden_or_system(entry: os.DirEntry, st: os.stat_result | None) -> bool:
    """Match Explorer's default view: hide Hidden/System items."""
    attrs = 0
    if st is not None:
        attrs = int(getattr(st, "st_file_attributes", 0) or 0)
    if not attrs:
        try:
            st2 = entry.stat(follow_symlinks=False)
            attrs = int(getattr(st2, "st_file_attributes", 0) or 0)
        except OSError:
            return False
    return bool(attrs & (_FILE_ATTRIBUTE_HIDDEN | _FILE_ATTRIBUTE_SYSTEM))


def list_directory(path: str | None) -> tuple[str, list[dict[str, Any]]]:
    """List a host directory. Empty path returns browse roots.

    Uses ``os.scandir`` so each entry is typically statted once (much faster than
    Path.iterdir + is_dir + stat on Windows).
    """
    text = (path or "").strip()
    if not text:
        return "", browse_roots()

    target = resolve_browse_path(text)
    try:
        # Avoid resolve() symlink walk when possible — absolute is enough for browse.
        # Never resolve bare drive roots through cwd (``C:`` quirk handled above).
        if not target.is_absolute():
            target = target.resolve()
    except OSError as exc:
        raise FileNotFoundError(str(exc)) from exc
    if not target.exists():
        raise FileNotFoundError(str(target))
    if not target.is_dir():
        raise NotADirectoryError(str(target))

    collected: list[tuple[bool, str, dict[str, Any]]] = []
    windows = _is_windows()
    try:
        with os.scandir(str(target)) as it:
            for entry in it:
                try:
                    st = None
                    try:
                        st = entry.stat(follow_symlinks=False)
                    except OSError:
                        st = None
                    if windows and _windows_hidden_or_system(entry, st):
                        continue
                    is_dir = _entry_is_dir(entry)
                    size = 0
                    mtime = 0
                    if st is not None:
                        if not is_dir:
                            size = int(st.st_size)
                        mtime = int(st.st_mtime)
                    entry_path = getattr(entry, "path", None) or str(target / entry.name)
                    collected.append(
                        (
                            is_dir,
                            entry.name.casefold() if windows else entry.name.lower(),
                            {
                                "name": entry.name,
                                "path": path_to_remote_str(entry_path),
                                "is_dir": bool(is_dir),
                                "size": size,
                                "mtime": mtime,
                            },
                        )
                    )
                except OSError:
                    continue
                if len(collected) >= _MAX_SCAN_ENTRIES:
                    break
    except OSError as exc:
        raise PermissionError(str(exc)) from exc

    collected.sort(key=lambda item: (0 if item[0] else 1, item[1]))
    entries = [item[2] for item in collected[:MAX_LIST_ENTRIES]]
    return path_to_remote_str(target), entries


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
