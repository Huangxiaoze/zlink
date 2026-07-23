"""Controller-side remote file browser (list + download from the host)."""

from __future__ import annotations

import time
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Callable, List, Optional

from .confirm_dialog import DialogDragBar, make_frameless_dialog
from .file_transfer import (
    MAX_FILE_BYTES,
    pack_download_request,
    pack_list_request,
    remote_parent_path,
)
from .i18n import i18n
from .qt_bind import (
    Fixed,
    NoEditTriggers,
    NoFocus,
    PointingHandCursor,
    QColor,
    QDialog,
    QFont,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPainter,
    QPushButton,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    ResizeToContents,
    SelectRows,
    SingleSelection,
    Stretch,
    UserRole,
    WA_StyledBackground,
    qt_enum_int,
)
from .themes import CURRENT

# Plain ints — avoid Qt enum objects entirely (PySide2 StateFlag/AlignmentFlag crash).
_ALIGN_LEFT_VCENTER = 0x0001 | 0x0080  # Qt.AlignLeft | Qt.AlignVCenter
_ALIGN_RIGHT_VCENTER = 0x0002 | 0x0080  # Qt.AlignRight | Qt.AlignVCenter
_USER_ROLE = 256  # Qt.UserRole


def _fmt_size(size: int, is_dir: bool) -> str:
    if is_dir:
        return "—"
    if size < 1024:
        return "%d B" % size
    if size < 1024 * 1024:
        return "%.1f KB" % (size / 1024.0)
    if size < 1024 * 1024 * 1024:
        return "%.1f MB" % (size / (1024.0 * 1024.0))
    return "%.2f GB" % (size / (1024.0 * 1024.0 * 1024.0))


def _fmt_mtime(ts: int) -> str:
    if not ts:
        return "—"
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))
    except (OverflowError, OSError, ValueError):
        return "—"


def _align(item: QTableWidgetItem, align: int = _ALIGN_LEFT_VCENTER) -> None:
    try:
        item.setTextAlignment(int(align))
    except Exception:
        pass


def _item_role() -> int:
    try:
        return int(qt_enum_int(UserRole))
    except Exception:
        return _USER_ROLE


class RemoteFileItemDelegate(QStyledItemDelegate):
    """Paint row chrome + text ourselves.

    Important for Ubuntu 18.04 / PySide2: never read ``option.state`` or use
    ``QStyle.StateFlag`` / AlignmentFlag objects — ``int()`` / ``&`` on them
    raises TypeError and can even mis-report at ``painter.save()``.
    """

    def __init__(self, table: QTableWidget) -> None:
        super().__init__(table)
        self._table = table

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:  # type: ignore[override]
        try:
            self._paint_row(painter, option, index)
        except Exception:
            try:
                super().paint(painter, option, index)
            except Exception:
                pass

    def _row_selected(self, index) -> bool:
        try:
            sm = self._table.selectionModel()
            return bool(sm is not None and sm.isSelected(index))
        except Exception:
            return False

    def _paint_row(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        rect = option.rect
        role = _item_role()
        entry = index.sibling(index.row(), 0).data(role)
        is_dir = isinstance(entry, dict) and bool(entry.get("is_dir"))
        col = int(index.column())
        text = str(index.data() or "")
        selected = self._row_selected(index)

        painter.save()
        try:
            painter.setClipRect(rect)
            painter.fillRect(rect, QColor(CURRENT.input_bg))
            if (int(index.row()) % 2) == 1 and not selected:
                alt = QColor(CURRENT.text)
                alt.setAlpha(12)
                painter.fillRect(rect, alt)
            if selected:
                painter.fillRect(rect, QColor(CURRENT.card_selected))

            if col == 0:
                color = QColor(CURRENT.accent if is_dir else CURRENT.text)
                label = ("▸  %s" % text) if is_dir else ("    %s" % text)
                font = QFont(option.font)
                if is_dir:
                    font.setBold(True)
                align = _ALIGN_LEFT_VCENTER
            elif col == 1:
                color = QColor(CURRENT.accent if is_dir else CURRENT.muted)
                label = text
                font = QFont(option.font)
                if is_dir:
                    font.setBold(True)
                align = _ALIGN_LEFT_VCENTER
            elif col == 2:
                color = QColor(CURRENT.muted)
                label = text
                font = QFont(option.font)
                align = _ALIGN_RIGHT_VCENTER
            else:
                color = QColor(CURRENT.muted)
                label = text
                font = QFont(option.font)
                align = _ALIGN_LEFT_VCENTER

            painter.setPen(color)
            painter.setFont(font)
            painter.drawText(rect.adjusted(10, 0, -8, 0), int(align), label)
        finally:
            painter.restore()


class RemoteFileBrowser(QDialog):
    """Browse the controlled PC and download selected files."""

    def __init__(
        self,
        parent: Optional[QWidget],
        send_packet: Callable[[bytes], None],
    ) -> None:
        super().__init__(parent)
        self.setObjectName("confirmDialog")
        make_frameless_dialog(self, modal=False, as_window=True)
        self.setWindowTitle(i18n.t("remote_files_title"))
        self.setMinimumSize(680, 440)
        self.resize(760, 520)

        self._send_packet = send_packet
        self._current_path = ""
        self._busy = False
        self._entries: List[dict[str, Any]] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(
            DialogDragBar(self, i18n.t("remote_files_title"), "info", False, window_controls=True)
        )

        body = QWidget()
        body_l = QVBoxLayout(body)
        body_l.setContentsMargins(20, 14, 20, 16)
        body_l.setSpacing(12)

        nav = QHBoxLayout()
        nav.setSpacing(8)
        self.btn_up = QPushButton(i18n.t("remote_files_up"))
        self.btn_up.setObjectName("remoteNavBtn")
        self.btn_up.setCursor(PointingHandCursor)
        self.btn_up.setFocusPolicy(NoFocus)
        self.btn_up.clicked.connect(self._go_up)
        self.btn_roots = QPushButton(i18n.t("remote_files_roots"))
        self.btn_roots.setObjectName("remoteNavBtn")
        self.btn_roots.setCursor(PointingHandCursor)
        self.btn_roots.setFocusPolicy(NoFocus)
        self.btn_roots.clicked.connect(lambda: self.request_list(""))
        self.btn_refresh = QPushButton(i18n.t("remote_files_refresh"))
        self.btn_refresh.setObjectName("remoteNavBtn")
        self.btn_refresh.setCursor(PointingHandCursor)
        self.btn_refresh.setFocusPolicy(NoFocus)
        self.btn_refresh.clicked.connect(self._refresh)
        self.edit_path = QLineEdit()
        self.edit_path.setObjectName("confirmInput")
        self.edit_path.setPlaceholderText(i18n.t("remote_files_path_hint"))
        self.edit_path.returnPressed.connect(self._go_path)
        nav.addWidget(self.btn_up)
        nav.addWidget(self.btn_roots)
        nav.addWidget(self.btn_refresh)
        nav.addWidget(self.edit_path, 1)
        body_l.addLayout(nav)

        self.table = QTableWidget(0, 4)
        self.table.setObjectName("remoteFileTable")
        self.table.setHorizontalHeaderLabels(
            [
                i18n.t("remote_files_col_name"),
                i18n.t("remote_files_col_type"),
                i18n.t("remote_files_col_size"),
                i18n.t("remote_files_col_mtime"),
            ]
        )
        self.table.setSelectionBehavior(SelectRows)
        self.table.setSelectionMode(SingleSelection)
        self.table.setEditTriggers(NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setFocusPolicy(NoFocus)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(34)
        header = self.table.horizontalHeader()
        header.setHighlightSections(False)
        try:
            header.setDefaultAlignment(int(_ALIGN_LEFT_VCENTER))
        except Exception:
            pass
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, Stretch)
        header.setSectionResizeMode(1, ResizeToContents)
        header.setSectionResizeMode(2, Fixed)
        header.setSectionResizeMode(3, Fixed)
        self.table.setColumnWidth(2, 96)
        self.table.setColumnWidth(3, 132)
        self.table.cellDoubleClicked.connect(self._on_double_click)
        self._item_delegate = RemoteFileItemDelegate(self.table)
        self.table.setItemDelegate(self._item_delegate)
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

            item_name = QTableWidgetItem(name)
            item_name.setData(_item_role(), entry)
            _align(item_name, _ALIGN_LEFT_VCENTER)

            item_type = QTableWidgetItem(
                i18n.t("remote_files_type_dir") if is_dir else i18n.t("remote_files_type_file")
            )
            _align(item_type, _ALIGN_LEFT_VCENTER)

            item_size = QTableWidgetItem(_fmt_size(size, is_dir))
            _align(item_size, _ALIGN_RIGHT_VCENTER)

            item_mtime = QTableWidgetItem(_fmt_mtime(mtime))
            _align(item_mtime, _ALIGN_LEFT_VCENTER)

            self.table.setItem(row, 0, item_name)
            self.table.setItem(row, 1, item_type)
            self.table.setItem(row, 2, item_size)
            self.table.setItem(row, 3, item_mtime)

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
        data = item.data(_item_role())
        return data if isinstance(data, dict) else None

    def _on_double_click(self, row: int, _col: int) -> None:
        item = self.table.item(row, 0)
        if item is None:
            return
        entry = item.data(_item_role())
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

    def _remote_name(self, path: str, fallback: str = "") -> str:
        """Basename of a remote path without using the controller OS Path rules."""
        text = (path or "").strip()
        if not text:
            return fallback
        if (len(text) >= 2 and text[0].isalpha() and text[1] == ":") or ("\\" in text):
            name = PureWindowsPath(text.replace("/", "\\")).name
        else:
            name = PurePosixPath(text).name
        return name or fallback

    def _start_download(self, entry: dict[str, Any]) -> None:
        path = str(entry.get("path") or "")
        name = str(entry.get("name") or self._remote_name(path) or "file.bin")
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
        self.request_list(remote_parent_path(self._current_path))

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
