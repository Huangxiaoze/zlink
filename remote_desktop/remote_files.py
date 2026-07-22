"""Controller-side remote file browser (list + download from the host)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, List, Optional

from .confirm_dialog import DialogDragBar, make_frameless_dialog
from .file_transfer import (
    MAX_FILE_BYTES,
    pack_download_request,
    pack_list_request,
)
from .i18n import i18n
from .qt_bind import (
    NoEditTriggers,
    NoFocus,
    PointingHandCursor,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    SelectRows,
    SingleSelection,
    Stretch,
    WA_StyledBackground,
)


def _fmt_size(size: int, is_dir: bool) -> str:
    if is_dir:
        return ""
    if size < 1024:
        return "%d B" % size
    if size < 1024 * 1024:
        return "%.1f KB" % (size / 1024.0)
    if size < 1024 * 1024 * 1024:
        return "%.1f MB" % (size / (1024.0 * 1024.0))
    return "%.2f GB" % (size / (1024.0 * 1024.0 * 1024.0))


def _fmt_mtime(ts: int) -> str:
    if not ts:
        return ""
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))
    except (OverflowError, OSError, ValueError):
        return ""


class RemoteFileBrowser(QDialog):
    """Browse the controlled PC and download selected files."""

    def __init__(
        self,
        parent: Optional[QWidget],
        send_packet: Callable[[bytes], None],
    ) -> None:
        super().__init__(parent)
        self.setObjectName("confirmDialog")
        make_frameless_dialog(self)
        self.setWindowTitle(i18n.t("remote_files_title"))
        self.setMinimumSize(640, 420)
        self.resize(720, 480)

        self._send_packet = send_packet
        self._current_path = ""
        self._busy = False
        self._entries: List[dict[str, Any]] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(DialogDragBar(self, i18n.t("remote_files_title"), "info", False))

        body = QWidget()
        body_l = QVBoxLayout(body)
        body_l.setContentsMargins(20, 14, 20, 16)
        body_l.setSpacing(10)

        nav = QHBoxLayout()
        nav.setSpacing(8)
        self.btn_up = QPushButton(i18n.t("remote_files_up"))
        self.btn_up.setObjectName("confirmCancel")
        self.btn_up.setCursor(PointingHandCursor)
        self.btn_up.setFocusPolicy(NoFocus)
        self.btn_up.clicked.connect(self._go_up)
        self.btn_roots = QPushButton(i18n.t("remote_files_roots"))
        self.btn_roots.setObjectName("confirmCancel")
        self.btn_roots.setCursor(PointingHandCursor)
        self.btn_roots.setFocusPolicy(NoFocus)
        self.btn_roots.clicked.connect(lambda: self.request_list(""))
        self.btn_refresh = QPushButton(i18n.t("remote_files_refresh"))
        self.btn_refresh.setObjectName("confirmCancel")
        self.btn_refresh.setCursor(PointingHandCursor)
        self.btn_refresh.setFocusPolicy(NoFocus)
        self.btn_refresh.clicked.connect(self._refresh)
        self.edit_path = QLineEdit()
        self.edit_path.setObjectName("confirmInput")
        self.edit_path.returnPressed.connect(self._go_path)
        nav.addWidget(self.btn_up)
        nav.addWidget(self.btn_roots)
        nav.addWidget(self.btn_refresh)
        nav.addWidget(self.edit_path, 1)
        body_l.addLayout(nav)

        self.table = QTableWidget(0, 3)
        self.table.setObjectName("remoteFileTable")
        self.table.setHorizontalHeaderLabels(
            [
                i18n.t("remote_files_col_name"),
                i18n.t("remote_files_col_size"),
                i18n.t("remote_files_col_mtime"),
            ]
        )
        self.table.setSelectionBehavior(SelectRows)
        self.table.setSelectionMode(SingleSelection)
        self.table.setEditTriggers(NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, Stretch)
        self.table.cellDoubleClicked.connect(self._on_double_click)
        body_l.addWidget(self.table, 1)

        foot = QHBoxLayout()
        self.lbl_status = QLabel("")
        self.lbl_status.setObjectName("confirmMessage")
        self.lbl_status.setWordWrap(True)
        foot.addWidget(self.lbl_status, 1)
        self.btn_download = QPushButton(i18n.t("remote_files_download"))
        self.btn_download.setObjectName("confirmOk")
        self.btn_download.setCursor(PointingHandCursor)
        self.btn_download.setFocusPolicy(NoFocus)
        self.btn_download.clicked.connect(self._download_selected)
        self.btn_close = QPushButton(i18n.t("close_action"))
        self.btn_close.setObjectName("confirmCancel")
        self.btn_close.setCursor(PointingHandCursor)
        self.btn_close.setFocusPolicy(NoFocus)
        self.btn_close.clicked.connect(self.reject)
        foot.addWidget(self.btn_download)
        foot.addWidget(self.btn_close)
        body_l.addLayout(foot)
        root.addWidget(body)

        self.setAttribute(WA_StyledBackground, True)
        self.request_list("")

    def request_list(self, path: str) -> None:
        if self._busy:
            return
        self._set_status(i18n.t("remote_files_listing"))
        self._busy = True
        self._update_busy_ui()
        try:
            self._send_packet(pack_list_request(path))
        except Exception as exc:
            self._busy = False
            self._update_busy_ui()
            self._set_status(i18n.t("file_transfer_failed", error=str(exc)))

    def handle_list_result(self, meta: dict[str, Any]) -> None:
        self._busy = False
        self._update_busy_ui()
        op = str(meta.get("op") or "")
        if op == "list_err":
            self._set_status(
                i18n.t("file_transfer_failed", error=str(meta.get("error") or "list failed"))
            )
            return
        if op != "list_ok":
            return
        path = str(meta.get("path") or "")
        entries = meta.get("entries") or []
        if not isinstance(entries, list):
            entries = []
        self._current_path = path
        self.edit_path.setText(path if path else i18n.t("remote_files_roots"))
        self._entries = [e for e in entries if isinstance(e, dict)]
        self._populate()
        self._set_status(i18n.t("remote_files_count", n=len(self._entries)))

    def handle_download_error(self, meta: dict[str, Any]) -> None:
        self._busy = False
        self._update_busy_ui()
        self._set_status(
            i18n.t("file_transfer_failed", error=str(meta.get("error") or "download failed"))
        )

    def mark_download_started(self, name: str) -> None:
        self._set_status(i18n.t("file_receiving", name=name, pct=0))

    def mark_download_progress(self, name: str, pct: int) -> None:
        self._set_status(i18n.t("file_receiving", name=name, pct=pct))

    def mark_download_done(self, path: Path) -> None:
        self._busy = False
        self._update_busy_ui()
        self._set_status(i18n.t("file_saved_to", path=str(path)))

    def _populate(self) -> None:
        self.table.setRowCount(0)
        for entry in self._entries:
            row = self.table.rowCount()
            self.table.insertRow(row)
            name = str(entry.get("name") or "")
            is_dir = bool(entry.get("is_dir"))
            size = int(entry.get("size") or 0)
            mtime = int(entry.get("mtime") or 0)
            prefix = "[DIR] " if is_dir else ""
            item_name = QTableWidgetItem(prefix + name)
            item_name.setData(256, entry)  # Qt.UserRole == 256
            item_size = QTableWidgetItem(_fmt_size(size, is_dir))
            item_mtime = QTableWidgetItem(_fmt_mtime(mtime))
            self.table.setItem(row, 0, item_name)
            self.table.setItem(row, 1, item_size)
            self.table.setItem(row, 2, item_mtime)

    def _selected_entry(self) -> Optional[dict[str, Any]]:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows:
            row = self.table.currentRow()
            if row < 0:
                return None
            item = self.table.item(row, 0)
        else:
            item = self.table.item(rows[0].row(), 0)
        if item is None:
            return None
        data = item.data(256)
        return data if isinstance(data, dict) else None

    def _on_double_click(self, row: int, _col: int) -> None:
        item = self.table.item(row, 0)
        if item is None:
            return
        entry = item.data(256)
        if not isinstance(entry, dict):
            return
        if entry.get("is_dir"):
            self.request_list(str(entry.get("path") or ""))
        else:
            self._start_download(entry)

    def _download_selected(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            self._set_status(i18n.t("remote_files_select_one"))
            return
        if entry.get("is_dir"):
            self.request_list(str(entry.get("path") or ""))
            return
        self._start_download(entry)

    def _start_download(self, entry: dict[str, Any]) -> None:
        path = str(entry.get("path") or "")
        name = str(entry.get("name") or Path(path).name)
        size = int(entry.get("size") or 0)
        if not path:
            return
        if size > MAX_FILE_BYTES:
            self._set_status(i18n.t("file_too_large", name=name))
            return
        if self._busy:
            self._set_status(i18n.t("file_transfer_busy"))
            return
        self._busy = True
        self._update_busy_ui()
        self.mark_download_started(name)
        try:
            self._send_packet(pack_download_request(path))
        except Exception as exc:
            self._busy = False
            self._update_busy_ui()
            self._set_status(i18n.t("file_transfer_failed", error=str(exc)))

    def _go_up(self) -> None:
        if not self._current_path:
            self.request_list("")
            return
        parent = str(Path(self._current_path).parent)
        if parent == self._current_path:
            self.request_list("")
        else:
            self.request_list(parent)

    def _go_path(self) -> None:
        text = self.edit_path.text().strip()
        if text == i18n.t("remote_files_roots"):
            text = ""
        self.request_list(text)

    def _refresh(self) -> None:
        self.request_list(self._current_path)

    def _set_status(self, text: str) -> None:
        self.lbl_status.setText(text)

    def _update_busy_ui(self) -> None:
        enabled = not self._busy
        self.btn_up.setEnabled(enabled)
        self.btn_roots.setEnabled(enabled)
        self.btn_refresh.setEnabled(enabled)
        self.btn_download.setEnabled(enabled)
        self.edit_path.setEnabled(enabled)
