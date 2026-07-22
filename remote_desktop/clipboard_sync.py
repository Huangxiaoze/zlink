from __future__ import annotations

import logging
import os
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Callable, Optional

from .protocol import pack_clipboard_message, unpack_clipboard_message
from .qt_bind import (
    QApplication,
    QClipboard,
    QMimeData,
    QObject,
    QTimer,
    QUrl,
    Signal,
)

log = logging.getLogger(__name__)

MAX_TEXT_BYTES = 2 * 1024 * 1024
MAX_FILE_BYTES = 64 * 1024 * 1024
CHUNK_SIZE = 256 * 1024
MAX_FILES_PER_SYNC = 8


def clipboard_temp_dir() -> Path:
    path = Path(tempfile.gettempdir()) / "leaflink_clipboard"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_name(name: str) -> str:
    base = os.path.basename(name.replace("\\", "/")).strip() or "file.bin"
    # Prevent weird names on Windows/Linux.
    return "".join(ch if ch not in '<>:"|?*' else "_" for ch in base)[:180]


class ClipboardBridge(QObject):
    """Main-thread clipboard poller + remote applier (text and local files)."""

    status = Signal(str)

    def __init__(
        self,
        send_packet: Callable[[bytes], None],
        parent: Optional[QObject] = None,
        *,
        enabled_check: Optional[Callable[[], bool]] = None,
        poll_ms: int = 500,
    ) -> None:
        super().__init__(parent)
        self._send_packet = send_packet
        self._enabled_check = enabled_check
        self._last_sig = ""
        self._suppress_sig = ""
        self._suppress_until = 0.0
        self._sending = False
        self._incoming: dict[str, dict] = {}
        self._recent_files: list[str] = []
        self._lock = threading.Lock()

        self._timer = QTimer(self)
        self._timer.setInterval(poll_ms)
        self._timer.timeout.connect(self._poll_local)

    def start(self) -> None:
        self._capture_signature(seed=True)
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def handle_remote_payload(self, payload: bytes) -> None:
        try:
            meta, blob = unpack_clipboard_message(payload)
        except Exception:
            log.exception("bad clipboard payload")
            return
        kind = meta.get("kind")
        if kind == "text":
            self._apply_text(blob.decode("utf-8", errors="replace"))
        elif kind == "file":
            self._apply_file_chunk(meta, blob)
        else:
            log.debug("ignore clipboard kind=%s", kind)

    def _app_clipboard(self) -> Optional[QClipboard]:
        app = QApplication.instance()
        if app is None:
            return None
        return app.clipboard()

    def _enabled(self) -> bool:
        if self._enabled_check is None:
            return True
        try:
            return bool(self._enabled_check())
        except Exception:
            return False

    def _capture_signature(self, seed: bool = False) -> str:
        cb = self._app_clipboard()
        if cb is None:
            return ""
        md = cb.mimeData()
        if md is None:
            sig = "empty"
        elif md.hasUrls():
            paths = []
            for url in md.urls():
                if url.isLocalFile():
                    paths.append(url.toLocalFile())
            sig = "files:" + "|".join(paths)
        elif md.hasText():
            text = md.text() or ""
            sig = "text:%d:%s" % (len(text), hash(text))
        else:
            sig = "other"
        if seed:
            self._last_sig = sig
        return sig

    def _poll_local(self) -> None:
        if not self._enabled() or self._sending:
            return
        now = time.monotonic()
        if now < self._suppress_until:
            self._last_sig = self._capture_signature()
            return
        sig = self._capture_signature()
        if not sig or sig == self._last_sig or sig == self._suppress_sig:
            return
        self._last_sig = sig
        try:
            self._sending = True
            if sig.startswith("files:"):
                paths = [p for p in sig[6:].split("|") if p]
                self._send_files(paths)
            elif sig.startswith("text:"):
                cb = self._app_clipboard()
                if cb is None:
                    return
                text = cb.text() or ""
                self._send_text(text)
        except Exception:
            log.exception("clipboard send failed")
        finally:
            self._sending = False

    def _send_text(self, text: str) -> None:
        raw = text.encode("utf-8")
        if len(raw) > MAX_TEXT_BYTES:
            self.status.emit("clipboard text too large, skipped")
            log.warning("clipboard text too large: %s bytes", len(raw))
            return
        packet = pack_clipboard_message({"kind": "text"}, raw)
        self._send_packet(packet)
        self.status.emit("clipboard text synced")

    def _send_files(self, paths: list[str]) -> None:
        sent = 0
        for path_str in paths[:MAX_FILES_PER_SYNC]:
            path = Path(path_str)
            if not path.is_file():
                continue
            size = path.stat().st_size
            if size > MAX_FILE_BYTES:
                self.status.emit("file too large: %s" % path.name)
                log.warning("skip large file %s (%s)", path, size)
                continue
            file_id = uuid.uuid4().hex
            name = _safe_name(path.name)
            offset = 0
            with path.open("rb") as fh:
                while True:
                    chunk = fh.read(CHUNK_SIZE)
                    done = not chunk or (offset + len(chunk) >= size)
                    if not chunk and offset == 0:
                        # empty file
                        packet = pack_clipboard_message(
                            {
                                "kind": "file",
                                "id": file_id,
                                "name": name,
                                "size": 0,
                                "offset": 0,
                                "done": True,
                            },
                            b"",
                        )
                        self._send_packet(packet)
                        break
                    if not chunk:
                        break
                    packet = pack_clipboard_message(
                        {
                            "kind": "file",
                            "id": file_id,
                            "name": name,
                            "size": int(size),
                            "offset": int(offset),
                            "done": bool(done),
                        },
                        chunk,
                    )
                    self._send_packet(packet)
                    offset += len(chunk)
                    if done:
                        break
            sent += 1
        if sent:
            self.status.emit("clipboard files synced (%d)" % sent)

    def _apply_text(self, text: str) -> None:
        cb = self._app_clipboard()
        if cb is None:
            return
        self._suppress_sig = "text:%d:%s" % (len(text), hash(text))
        self._suppress_until = time.monotonic() + 1.5
        cb.setText(text)
        self._last_sig = self._suppress_sig
        self.status.emit("remote text pasted to clipboard")

    def _apply_file_chunk(self, meta: dict, blob: bytes) -> None:
        file_id = str(meta.get("id") or "")
        name = _safe_name(str(meta.get("name") or "file.bin"))
        size = int(meta.get("size") or 0)
        offset = int(meta.get("offset") or 0)
        done = bool(meta.get("done"))
        if not file_id or size < 0 or size > MAX_FILE_BYTES:
            return
        with self._lock:
            state = self._incoming.get(file_id)
            if state is None:
                dest = clipboard_temp_dir() / ("%s_%s" % (file_id[:8], name))
                state = {
                    "name": name,
                    "size": size,
                    "path": dest,
                    "received": 0,
                    "fh": dest.open("wb"),
                }
                self._incoming[file_id] = state
            fh = state["fh"]
            if offset != state["received"]:
                log.warning("clipboard file offset mismatch id=%s", file_id)
            fh.write(blob)
            state["received"] = offset + len(blob)
            if done or state["received"] >= size:
                fh.close()
                path = state["path"]
                del self._incoming[file_id]
                self._recent_files.append(str(path))
                self._recent_files = self._recent_files[-MAX_FILES_PER_SYNC:]
                self._set_files_clipboard(list(self._recent_files))
                self.status.emit("remote file ready: %s" % name)

    def _set_files_clipboard(self, paths: list[str]) -> None:
        cb = self._app_clipboard()
        if cb is None:
            return
        md = QMimeData()
        urls = []
        for p in paths:
            urls.append(QUrl.fromLocalFile(p))
        md.setUrls(urls)
        # Also set text path for apps that only accept text.
        md.setText("\n".join(paths))
        sig = "files:" + "|".join(paths)
        self._suppress_sig = sig
        self._suppress_until = time.monotonic() + 2.0
        cb.setMimeData(md)
        self._last_sig = sig
