from __future__ import annotations

import hashlib
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
    path = Path(tempfile.gettempdir()) / "zlink_clipboard"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_name(name: str) -> str:
    base = os.path.basename(name.replace("\\", "/")).strip() or "file.bin"
    return "".join(ch if ch not in '<>:"|?*' else "_" for ch in base)[:180]


def _text_sig(text: str) -> str:
    digest = hashlib.md5(text.encode("utf-8", errors="replace")).hexdigest()[:12]
    return "text:%d:%s" % (len(text), digest)


class ClipboardBridge(QObject):
    """Main-thread clipboard sync (text + local files)."""

    status = Signal(str)

    def __init__(
        self,
        send_packet: Callable[[bytes], None],
        parent: Optional[QObject] = None,
        *,
        enabled_check: Optional[Callable[[], bool]] = None,
        poll_ms: int = 400,
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
        self._connected_data_changed = False

        self._timer = QTimer(self)
        self._timer.setInterval(poll_ms)
        self._timer.timeout.connect(self._poll_local)

    def start(self) -> None:
        self._capture_signature(seed=True)
        self._timer.start()
        cb = self._app_clipboard()
        if cb is not None and not self._connected_data_changed:
            cb.dataChanged.connect(self._on_data_changed)
            self._connected_data_changed = True

    def stop(self) -> None:
        self._timer.stop()
        cb = self._app_clipboard()
        if cb is not None and self._connected_data_changed:
            try:
                cb.dataChanged.disconnect(self._on_data_changed)
            except (RuntimeError, TypeError):
                pass
            self._connected_data_changed = False

    def push_now(self) -> bool:
        """Force push current local clipboard to remote (ignores last-signature)."""
        if not self._enabled():
            self.status.emit("clipboard sync idle (no session)")
            return False
        self._last_sig = ""
        self._suppress_until = 0.0
        self._poll_local(force=True)
        return True

    def request_remote(self) -> None:
        """Ask peer to push its clipboard now."""
        if not self._enabled():
            self.status.emit("clipboard sync idle (no session)")
            return
        packet = pack_clipboard_message({"kind": "request"}, b"")
        self._send_packet(packet)
        self.status.emit("requested remote clipboard")

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
        elif kind == "request":
            # Peer asked us to push — do it on the GUI thread timer.
            QTimer.singleShot(0, self.push_now)
        else:
            log.debug("ignore clipboard kind=%s", kind)

    def _on_data_changed(self) -> None:
        # Clipboard changed by any app — sync ASAP.
        QTimer.singleShot(0, self._poll_local)

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

    def _clip_mode(self):
        return getattr(QClipboard, "Clipboard", None)

    def _mime(self):
        cb = self._app_clipboard()
        if cb is None:
            return None, None
        mode = self._clip_mode()
        if mode is not None:
            try:
                return cb, cb.mimeData(mode)
            except TypeError:
                pass
        return cb, cb.mimeData()

    def _capture_signature(self, seed: bool = False) -> str:
        cb, md = self._mime()
        if cb is None or md is None:
            sig = "empty"
        elif md.hasUrls():
            paths = []
            for url in md.urls():
                if url.isLocalFile():
                    p = url.toLocalFile()
                    if p:
                        paths.append(p)
            sig = "files:" + "|".join(paths) if paths else "empty"
        elif md.hasText():
            text = md.text() or ""
            sig = _text_sig(text) if text else "empty"
        else:
            sig = "other"
        if seed:
            self._last_sig = sig
        return sig

    def _poll_local(self, force: bool = False) -> None:
        if not self._enabled() or self._sending:
            return
        now = time.monotonic()
        if not force and now < self._suppress_until:
            self._last_sig = self._capture_signature()
            return
        sig = self._capture_signature()
        if not force:
            if not sig or sig == "empty" or sig == "other":
                return
            if sig == self._last_sig or sig == self._suppress_sig:
                return
        elif sig in {"", "empty", "other"}:
            self.status.emit("local clipboard empty")
            return
        self._last_sig = sig
        try:
            self._sending = True
            if sig.startswith("files:"):
                paths = [p for p in sig[6:].split("|") if p]
                if paths:
                    self._send_files(paths)
            elif sig.startswith("text:"):
                cb, md = self._mime()
                if cb is None or md is None:
                    return
                text = md.text() or ""
                if text:
                    self._send_text(text)
        except Exception:
            log.exception("clipboard send failed")
            self.status.emit("clipboard send failed")
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
        log.info("clipboard text sent (%d bytes)", len(raw))
        self.status.emit("clipboard text synced (%d bytes)" % len(raw))

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
                    if not chunk and offset == 0:
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
                        sent += 1
                        break
                    if not chunk:
                        break
                    done = offset + len(chunk) >= size
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
                        sent += 1
                        break
        if sent:
            log.info("clipboard files sent: %d", sent)
            self.status.emit("clipboard files synced (%d)" % sent)

    def _apply_text(self, text: str) -> None:
        cb = self._app_clipboard()
        if cb is None:
            return
        self._suppress_sig = _text_sig(text)
        self._suppress_until = time.monotonic() + 2.0
        mode = self._clip_mode()
        if mode is not None:
            try:
                cb.setText(text, mode)
            except TypeError:
                cb.setText(text)
        else:
            cb.setText(text)
        self._last_sig = self._suppress_sig
        log.info("clipboard text applied (%d chars)", len(text))
        self.status.emit("remote text -> local clipboard")

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
                log.warning(
                    "clipboard file offset mismatch id=%s expect=%s got=%s",
                    file_id,
                    state["received"],
                    offset,
                )
            fh.write(blob)
            state["received"] = offset + len(blob)
            if done or state["received"] >= size:
                fh.close()
                path = state["path"]
                del self._incoming[file_id]
                self._recent_files.append(str(path))
                self._recent_files = self._recent_files[-MAX_FILES_PER_SYNC:]
                self._set_files_clipboard(list(self._recent_files))
                self.status.emit("remote file -> clipboard: %s" % name)

    def _set_files_clipboard(self, paths: list[str]) -> None:
        cb = self._app_clipboard()
        if cb is None:
            return
        md = QMimeData()
        urls = [QUrl.fromLocalFile(p) for p in paths]
        md.setUrls(urls)
        md.setText("\n".join(paths))
        sig = "files:" + "|".join(paths)
        self._suppress_sig = sig
        self._suppress_until = time.monotonic() + 2.5
        mode = self._clip_mode()
        if mode is not None:
            try:
                cb.setMimeData(md, mode)
            except TypeError:
                cb.setMimeData(md)
        else:
            cb.setMimeData(md)
        self._last_sig = sig
