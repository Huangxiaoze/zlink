from __future__ import annotations

import logging
import queue
import threading
import time

from .qt_bind import (
    AA_DontShowIconsInMenus,
    Cancel,
    DialogAccepted,
    Horizontal,
    NoEditTriggers,
    Password,
    PointingHandCursor,
    QApplication,
    QBrush,
    QCheckBox,
    QColor,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTimer,
    QVBoxLayout,
    QWidget,
    Save,
    SelectRows,
    Signal,
    SingleSelection,
    Stretch,
    UserRole,
    WA_DeleteOnClose,
    Yes,
    dialog_exec,
)

from .client import RemoteClientWindow
from .clipboard_sync import ClipboardBridge
from .config import ClientConfig, HostConfig, NetConfig, StreamConfig
from .devices import Device, DeviceStore, list_local_ipv4, make_verify_code, probe_online
from .host import RemoteHost
from .i18n import i18n
from .qt_fonts import apply_app_font, ensure_utf8_stdio

log = logging.getLogger(__name__)

# Slate + teal — remote-tool look, not purple / cream defaults.
C_BG = "#EEF2F4"
C_SIDE = "#0F1C24"
C_SIDE_2 = "#162832"
C_CARD = "#FFFFFF"
C_TEXT = "#14212B"
C_MUTED = "#6A7A86"
C_LINE = "#D5DEE5"
C_ACCENT = "#0F9D7A"
C_ACCENT_2 = "#0B7F63"
C_DANGER = "#D64545"
C_WARN = "#E3A008"
C_ONLINE = "#0B8F5B"
C_OFFLINE = "#C0392B"

APP_QSS = f"""
QMainWindow, QWidget#root {{
    background: {C_BG};
    color: {C_TEXT};
}}
QLabel#brand {{
    color: #FFFFFF;
    font-size: 22px;
    font-weight: 800;
    letter-spacing: 0.5px;
}}
QLabel#brandTag {{
    color: #8FA3B0;
    font-size: 11px;
}}
QLabel#sectionTitle {{
    color: #FFFFFF;
    font-size: 13px;
    font-weight: 700;
}}
QLabel#muted {{
    color: #8FA3B0;
    font-size: 12px;
}}
QLabel#codeValue {{
    color: #FFFFFF;
    font-size: 26px;
    font-weight: 800;
    letter-spacing: 1px;
}}
QLabel#passValue {{
    color: #7DFFCE;
    font-size: 22px;
    font-weight: 800;
    letter-spacing: 2px;
}}
QLabel#pageTitle {{
    color: {C_TEXT};
    font-size: 22px;
    font-weight: 800;
}}
QLabel#pageSub {{
    color: {C_MUTED};
    font-size: 12px;
}}
QFrame#side {{
    background: {C_SIDE};
}}
QFrame#infoCard {{
    background: {C_SIDE_2};
    border: 1px solid #243845;
    border-radius: 12px;
}}
QFrame#mainCard {{
    background: {C_CARD};
    border: 1px solid {C_LINE};
    border-radius: 14px;
}}
QLineEdit, QComboBox {{
    background: #FFFFFF;
    border: 1px solid {C_LINE};
    border-radius: 8px;
    padding: 8px 10px;
    min-height: 18px;
    selection-background-color: {C_ACCENT};
}}
QFrame#side QLineEdit {{
    background: #0C171E;
    color: #E8F1F5;
    border: 1px solid #2A3D4A;
}}
QFrame#side QCheckBox {{
    color: #9BB0BD;
    spacing: 8px;
}}
QPushButton {{
    background: #F4F7F9;
    color: {C_TEXT};
    border: 1px solid {C_LINE};
    border-radius: 8px;
    padding: 8px 14px;
    font-weight: 600;
}}
QPushButton:hover {{
    background: #E8EEF2;
}}
QPushButton#primary {{
    background: {C_ACCENT};
    color: white;
    border: none;
    font-weight: 700;
}}
QPushButton#primary:hover {{
    background: {C_ACCENT_2};
}}
QPushButton#danger {{
    background: {C_DANGER};
    color: white;
    border: none;
    font-weight: 700;
}}
QPushButton#danger:hover {{
    background: #B93737;
}}
QPushButton#ghostDark {{
    background: #21313B;
    color: #E7F0F5;
    border: 1px solid #314552;
}}
QPushButton#ghostDark:hover {{
    background: #2A3E4A;
}}
QTableWidget {{
    background: transparent;
    border: none;
    gridline-color: transparent;
    outline: none;
    font-size: 13px;
}}
QTableWidget::item {{
    padding: 10px 8px;
    border-bottom: 1px solid #EEF2F5;
}}
QTableWidget::item:selected {{
    background: #E6F7F2;
    color: {C_TEXT};
}}
QHeaderView::section {{
    background: transparent;
    color: {C_MUTED};
    border: none;
    border-bottom: 1px solid {C_LINE};
    padding: 10px 8px;
    font-weight: 700;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 4px 2px;
}}
QScrollBar::handle:vertical {{
    background: #C5D0D8;
    border-radius: 4px;
    min-height: 30px;
}}
"""


class DeviceDialog(QDialog):
    def __init__(self, parent: QWidget, title: str, device: Device | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(420)
        self.result_device: Device | None = None
        self._device = device

        form = QFormLayout(self)
        form.setContentsMargins(20, 20, 20, 16)
        form.setSpacing(10)
        self.name = QLineEdit(device.name if device else "")
        self.host = QLineEdit(device.host if device else "")
        self.port = QLineEdit(str(device.port if device else 5959))
        self.password = QLineEdit(device.password if device else "")
        self.password.setEchoMode(Password)
        self.notes = QLineEdit(device.notes if device else "")
        form.addRow(i18n.t("field_name"), self.name)
        form.addRow(i18n.t("field_host"), self.host)
        form.addRow(i18n.t("field_port"), self.port)
        form.addRow(i18n.t("field_password"), self.password)
        form.addRow(i18n.t("field_notes"), self.notes)

        buttons = QDialogButtonBox(Save | Cancel)
        buttons.button(Save).setText(i18n.t("save"))
        buttons.button(Cancel).setText(i18n.t("cancel"))
        buttons.button(Save).setObjectName("primary")
        buttons.accepted.connect(self._ok)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _ok(self) -> None:
        host = self.host.text().strip()
        if not host:
            QMessageBox.warning(self, i18n.t("tip"), i18n.t("fill_host"))
            return
        try:
            port = int(self.port.text().strip())
            if not (1 <= port <= 65535):
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, i18n.t("tip"), i18n.t("bad_port"))
            return
        name = self.name.text().strip() or host
        if self._device:
            self.result_device = Device(
                id=self._device.id,
                name=name,
                host=host,
                port=port,
                password=self.password.text(),
                notes=self.notes.text().strip(),
                last_connected=self._device.last_connected,
                created_at=self._device.created_at,
            )
        else:
            self.result_device = Device.create(
                name=name,
                host=host,
                port=port,
                password=self.password.text(),
                notes=self.notes.text().strip(),
            )
        self.accept()


class SettingsDialog(QDialog):
    def __init__(self, parent: QWidget, store: DeviceStore) -> None:
        super().__init__(parent)
        self.store = store
        self.setWindowTitle(i18n.t("settings_title"))
        self.setModal(True)
        self.setMinimumWidth(420)
        form = QFormLayout(self)
        form.setContentsMargins(20, 20, 20, 16)
        form.setSpacing(10)

        self.lang = QComboBox()
        self.lang.addItem(i18n.t("lang_zh"), "zh_CN")
        self.lang.addItem(i18n.t("lang_en"), "en_US")
        idx = self.lang.findData(store.settings.language)
        self.lang.setCurrentIndex(max(0, idx))

        self.fps = QLineEdit(str(store.settings.max_fps))
        self.quality = QLineEdit(str(store.settings.jpeg_quality))
        self.scale = QLineEdit(str(store.settings.scale))
        self.probe = QLineEdit(str(store.settings.auto_probe_s))

        form.addRow(i18n.t("language"), self.lang)
        form.addRow(i18n.t("max_fps"), self.fps)
        form.addRow(i18n.t("jpeg_quality"), self.quality)
        form.addRow(i18n.t("scale"), self.scale)
        form.addRow(i18n.t("probe_interval"), self.probe)

        self.btn_hd = QPushButton(i18n.t("hd_preset"))
        self.btn_hd.setObjectName("primary")
        self.btn_hd.clicked.connect(self._apply_hd)
        form.addRow(self.btn_hd)

        hint = QLabel(i18n.t("font_hint"))
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {C_MUTED};")
        form.addRow(hint)

        buttons = QDialogButtonBox(Save | Cancel)
        buttons.button(Save).setText(i18n.t("save"))
        buttons.button(Cancel).setText(i18n.t("cancel"))
        buttons.button(Save).setObjectName("primary")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _apply_hd(self) -> None:
        self.fps.setText("30")
        self.quality.setText("90")
        self.scale.setText("1.0")

    def _save(self) -> None:
        try:
            self.store.settings.max_fps = float(self.fps.text())
            self.store.settings.jpeg_quality = int(self.quality.text())
            self.store.settings.scale = float(self.scale.text())
            self.store.settings.auto_probe_s = max(3.0, float(self.probe.text()))
            self.store.settings.language = str(self.lang.currentData())
            self.store.settings.settings_version = 2
        except ValueError:
            QMessageBox.warning(self, i18n.t("tip"), i18n.t("invalid_number"))
            return
        self.store.save()
        self.accept()


class MainWindow(QMainWindow):
    probe_done = Signal(dict)
    host_crashed = Signal()
    host_clip_wakeup = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.store = DeviceStore()
        i18n.set_lang(self.store.settings.language)
        self._status: dict[str, str] = {}
        self._host: RemoteHost | None = None
        self._host_thread: threading.Thread | None = None
        self._probe_stop = threading.Event()
        self._viewers: list[RemoteClientWindow] = []
        self._host_clip: ClipboardBridge | None = None
        self._host_clip_timer: QTimer | None = None

        self.probe_done.connect(self._apply_probe)
        self.host_crashed.connect(self._on_host_crashed)
        self.host_clip_wakeup.connect(self._drain_host_clipboard_in)

        self._build()
        self.retranslate()
        self._refresh_local()
        self._reload_table()
        self._start_probe_loop()
        i18n.on_change(self.retranslate)

    def _build(self) -> None:
        self.resize(1120, 700)
        self.setMinimumSize(920, 580)
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        splitter = QSplitter(Horizontal)
        outer.addWidget(splitter)

        side = QFrame()
        side.setObjectName("side")
        side.setMinimumWidth(300)
        side.setMaximumWidth(360)
        side_l = QVBoxLayout(side)
        side_l.setContentsMargins(22, 24, 22, 22)
        side_l.setSpacing(10)

        self.lbl_brand = QLabel()
        self.lbl_brand.setObjectName("brand")
        self.lbl_brand_tag = QLabel()
        self.lbl_brand_tag.setObjectName("brandTag")

        self.lbl_side_title = QLabel()
        self.lbl_side_title.setObjectName("sectionTitle")
        self.lbl_side_hint = QLabel()
        self.lbl_side_hint.setObjectName("muted")
        self.lbl_side_hint.setWordWrap(True)

        card = QFrame()
        card.setObjectName("infoCard")
        card_l = QVBoxLayout(card)
        card_l.setContentsMargins(14, 14, 14, 14)
        card_l.setSpacing(8)

        self.lbl_local_name = QLabel()
        self.lbl_local_name.setStyleSheet("color:#D7E4EC; font-size:13px; font-weight:600;")
        self.lbl_code_hint = QLabel()
        self.lbl_code_hint.setObjectName("muted")
        self.lbl_code = QLabel()
        self.lbl_code.setObjectName("codeValue")
        self.lbl_verify_title = QLabel()
        self.lbl_verify_title.setObjectName("muted")
        self.lbl_verify = QLabel()
        self.lbl_verify.setObjectName("passValue")
        self.chk_show = QCheckBox()
        self.chk_show.toggled.connect(self._refresh_local)

        port_row = QHBoxLayout()
        self.lbl_port = QLabel()
        self.lbl_port.setObjectName("muted")
        self.edit_port = QLineEdit()
        self.edit_port.setFixedWidth(90)
        port_row.addWidget(self.lbl_port)
        port_row.addWidget(self.edit_port)
        port_row.addStretch(1)

        self.lbl_ips_title = QLabel()
        self.lbl_ips_title.setObjectName("muted")
        self.lbl_ips = QLabel()
        self.lbl_ips.setObjectName("muted")
        self.lbl_ips.setWordWrap(True)
        self.lbl_ips.setStyleSheet("color:#C5D6E0; font-size:12px;")

        card_l.addWidget(self.lbl_local_name)
        card_l.addSpacing(4)
        card_l.addWidget(self.lbl_code_hint)
        card_l.addWidget(self.lbl_code)
        card_l.addSpacing(6)
        card_l.addWidget(self.lbl_verify_title)
        card_l.addWidget(self.lbl_verify)
        card_l.addWidget(self.chk_show)
        card_l.addSpacing(4)
        card_l.addLayout(port_row)
        card_l.addWidget(self.lbl_ips_title)
        card_l.addWidget(self.lbl_ips)

        self.btn_host = QPushButton()
        self.btn_host.setObjectName("primary")
        self.btn_host.setCursor(PointingHandCursor)
        self.btn_host.setMinimumHeight(40)
        self.btn_host.clicked.connect(self._toggle_host)

        row_side_btns = QHBoxLayout()
        self.btn_refresh_local = QPushButton()
        self.btn_refresh_local.setObjectName("ghostDark")
        self.btn_refresh_local.clicked.connect(self._refresh_local)
        self.btn_regen = QPushButton()
        self.btn_regen.setObjectName("ghostDark")
        self.btn_regen.clicked.connect(self._regen_password)
        row_side_btns.addWidget(self.btn_refresh_local)
        row_side_btns.addWidget(self.btn_regen)

        self.lbl_host_state = QLabel()
        self.lbl_host_state.setStyleSheet(f"color:{C_WARN}; font-size:12px; font-weight:600;")

        side_l.addWidget(self.lbl_brand)
        side_l.addWidget(self.lbl_brand_tag)
        side_l.addSpacing(14)
        side_l.addWidget(self.lbl_side_title)
        side_l.addWidget(self.lbl_side_hint)
        side_l.addWidget(card)
        side_l.addSpacing(8)
        side_l.addWidget(self.btn_host)
        side_l.addLayout(row_side_btns)
        side_l.addWidget(self.lbl_host_state)
        side_l.addStretch(1)

        main = QWidget()
        main_l = QVBoxLayout(main)
        main_l.setContentsMargins(22, 20, 22, 16)
        main_l.setSpacing(12)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        self.lbl_list_title = QLabel()
        self.lbl_list_title.setObjectName("pageTitle")
        self.lbl_list_sub = QLabel()
        self.lbl_list_sub.setObjectName("pageSub")
        title_box.addWidget(self.lbl_list_title)
        title_box.addWidget(self.lbl_list_sub)
        header.addLayout(title_box, 1)
        self.btn_quick = QPushButton()
        self.btn_settings = QPushButton()
        self.btn_quick.clicked.connect(self._quick_connect)
        self.btn_settings.clicked.connect(self._open_settings)
        header.addWidget(self.btn_quick)
        header.addWidget(self.btn_settings)

        search_row = QHBoxLayout()
        self.lbl_search = QLabel()
        self.lbl_search.setStyleSheet(f"color:{C_MUTED};")
        self.search = QLineEdit()
        self.search.textChanged.connect(self._reload_table)
        search_row.addWidget(self.lbl_search)
        search_row.addWidget(self.search, 1)

        table_card = QFrame()
        table_card.setObjectName("mainCard")
        table_l = QVBoxLayout(table_card)
        table_l.setContentsMargins(8, 8, 8, 8)
        self.table = QTableWidget(0, 4)
        self.table.setSelectionBehavior(SelectRows)
        self.table.setSelectionMode(SingleSelection)
        self.table.setEditTriggers(NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(46)
        self.table.horizontalHeader().setSectionResizeMode(Stretch)
        self.table.setAlternatingRowColors(False)
        self.table.doubleClicked.connect(self._connect_selected)
        table_l.addWidget(self.table)

        actions = QHBoxLayout()
        self.btn_add = QPushButton()
        self.btn_edit = QPushButton()
        self.btn_del = QPushButton()
        self.btn_probe = QPushButton()
        self.btn_connect = QPushButton()
        self.btn_connect.setObjectName("primary")
        self.btn_connect.setMinimumWidth(140)
        self.btn_connect.setMinimumHeight(38)
        self.btn_add.clicked.connect(self._add_device)
        self.btn_edit.clicked.connect(self._edit_device)
        self.btn_del.clicked.connect(self._delete_device)
        self.btn_probe.clicked.connect(self._probe_now)
        self.btn_connect.clicked.connect(self._connect_selected)
        actions.addWidget(self.btn_add)
        actions.addWidget(self.btn_edit)
        actions.addWidget(self.btn_del)
        actions.addWidget(self.btn_probe)
        actions.addStretch(1)
        actions.addWidget(self.btn_connect)

        self.status = QLabel()
        self.status.setStyleSheet(f"color:{C_MUTED}; font-size:12px;")

        main_l.addLayout(header)
        main_l.addLayout(search_row)
        main_l.addWidget(table_card, 1)
        main_l.addLayout(actions)
        main_l.addWidget(self.status)

        splitter.addWidget(side)
        splitter.addWidget(main)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([320, 800])

    def retranslate(self) -> None:
        self.setWindowTitle(i18n.t("app_title"))
        self.lbl_brand.setText(i18n.t("brand"))
        self.lbl_brand_tag.setText(i18n.t("brand_tag"))
        self.lbl_side_title.setText(i18n.t("local_control"))
        self.lbl_side_hint.setText(i18n.t("local_control_hint"))
        self.lbl_code_hint.setText(i18n.t("device_code"))
        self.lbl_verify_title.setText(i18n.t("verify_code"))
        self.chk_show.setText(i18n.t("show"))
        self.lbl_port.setText(i18n.t("port"))
        self.lbl_ips_title.setText(i18n.t("local_ip"))
        self.btn_refresh_local.setText(i18n.t("refresh_local"))
        self.btn_regen.setText(i18n.t("regen_code"))
        if self._host is None:
            self.btn_host.setText(i18n.t("start_host"))
            self.btn_host.setObjectName("primary")
            self.btn_host.style().unpolish(self.btn_host)
            self.btn_host.style().polish(self.btn_host)
            self.lbl_host_state.setText(i18n.t("host_off"))
            self.lbl_host_state.setStyleSheet(f"color:{C_WARN}; font-size:12px; font-weight:600;")
        else:
            self.btn_host.setText(i18n.t("stop_host"))
            self.btn_host.setObjectName("danger")
            self.btn_host.style().unpolish(self.btn_host)
            self.btn_host.style().polish(self.btn_host)
            self.lbl_host_state.setText(i18n.t("host_on", port=self.store.settings.host_port))
            self.lbl_host_state.setStyleSheet(f"color:#7DFFCE; font-size:12px; font-weight:600;")
        self.lbl_list_title.setText(i18n.t("device_list"))
        self.lbl_list_sub.setText(i18n.t("device_list_sub"))
        self.btn_settings.setText(i18n.t("settings"))
        self.btn_quick.setText(i18n.t("quick_connect"))
        self.lbl_search.setText(i18n.t("search"))
        self.search.setPlaceholderText(i18n.t("search_ph"))
        self.table.setHorizontalHeaderLabels(
            [i18n.t("col_name"), i18n.t("col_address"), i18n.t("col_status"), i18n.t("col_last")]
        )
        self.btn_add.setText(i18n.t("add_device"))
        self.btn_edit.setText(i18n.t("edit"))
        self.btn_del.setText(i18n.t("delete"))
        self.btn_probe.setText(i18n.t("refresh_status"))
        self.btn_connect.setText(i18n.t("remote_control"))
        self._refresh_local()
        self._reload_table()
        if not self.status.text():
            self.status.setText(i18n.t("ready"))

    def _set_status(self, text: str) -> None:
        self.status.setText(text)

    def _format_code(self, code: str) -> str:
        digits = "".join(ch for ch in code if ch.isdigit())
        if len(digits) == 9:
            return f"{digits[:3]} {digits[3:6]} {digits[6:]}"
        return code

    def _refresh_local(self) -> None:
        s = self.store.settings
        self.lbl_local_name.setText(i18n.t("local_name", name=s.local_name))
        self.lbl_code.setText(self._format_code(s.device_code))
        pwd = s.host_password
        self.lbl_verify.setText(pwd if self.chk_show.isChecked() else ("•" * max(4, len(pwd))))
        self.edit_port.setText(str(s.host_port))
        ips = list_local_ipv4()
        self.lbl_ips.setText("\n".join(ips))

    def _reload_table(self) -> None:
        keyword = self.search.text().strip().lower()
        rows = []
        for device in self.store.devices:
            hay = f"{device.name} {device.host} {device.notes}".lower()
            if keyword and keyword not in hay:
                continue
            rows.append(device)

        self.table.setRowCount(len(rows))
        for r, device in enumerate(rows):
            status_key = self._status.get(device.id, "unknown")
            status_text = {
                "online": i18n.t("online"),
                "offline": i18n.t("offline"),
            }.get(status_key, i18n.t("unknown"))
            color = {
                "online": QColor(C_ONLINE),
                "offline": QColor(C_OFFLINE),
            }.get(status_key, QColor(C_MUTED))

            values = [
                device.name,
                f"{device.host}:{device.port}",
                status_text,
                _fmt_time(device.last_connected),
            ]
            for c, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(UserRole, device.id)
                if c == 2:
                    item.setForeground(QBrush(color))
                self.table.setItem(r, c, item)

    def _selected_device(self) -> Device | None:
        items = self.table.selectedItems()
        if not items:
            return None
        device_id = items[0].data(UserRole)
        return self.store.get(str(device_id))

    def _add_device(self) -> None:
        dialog = DeviceDialog(self, i18n.t("add_title"))
        if dialog_exec(dialog) == DialogAccepted and dialog.result_device:
            self.store.upsert(dialog.result_device)
            self._reload_table()
            self._set_status(i18n.t("added", name=dialog.result_device.name))
            self._probe_now()

    def _edit_device(self) -> None:
        device = self._selected_device()
        if not device:
            QMessageBox.information(self, i18n.t("tip"), i18n.t("select_device"))
            return
        dialog = DeviceDialog(self, i18n.t("edit_title"), device)
        if dialog_exec(dialog) == DialogAccepted and dialog.result_device:
            self.store.upsert(dialog.result_device)
            self._reload_table()
            self._set_status(i18n.t("updated", name=dialog.result_device.name))

    def _delete_device(self) -> None:
        device = self._selected_device()
        if not device:
            QMessageBox.information(self, i18n.t("tip"), i18n.t("select_device"))
            return
        if (
            QMessageBox.question(
                self,
                i18n.t("confirm"),
                i18n.t("delete_confirm", name=device.name),
            )
            != Yes
        ):
            return
        self.store.remove(device.id)
        self._status.pop(device.id, None)
        self._reload_table()
        self._set_status(i18n.t("device_deleted"))

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self, self.store)
        if dialog_exec(dialog) != DialogAccepted:
            return
        i18n.set_lang(self.store.settings.language)
        self._set_status(i18n.t("settings_saved"))

    def _regen_password(self) -> None:
        if self._host is not None:
            QMessageBox.warning(self, i18n.t("tip"), i18n.t("stop_before_regen"))
            return
        self.store.settings.host_password = make_verify_code()
        self.store.save()
        self._refresh_local()
        self._set_status(i18n.t("code_updated"))

    def _toggle_host(self) -> None:
        if self._host is not None:
            self._stop_host()
        else:
            self._start_host()

    def _start_host(self) -> None:
        try:
            port = int(self.edit_port.text().strip())
            if not (1 <= port <= 65535):
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, i18n.t("tip"), i18n.t("bad_port"))
            return
        password = self.store.settings.host_password.strip()
        if not password:
            QMessageBox.warning(self, i18n.t("tip"), i18n.t("empty_password"))
            return
        self.store.settings.host_port = port
        self.store.save()

        stream = StreamConfig(
            max_fps=self.store.settings.max_fps,
            jpeg_quality=self.store.settings.jpeg_quality,
            scale=self.store.settings.scale,
        ).clamp()
        net = NetConfig(host=self.store.settings.host_bind, port=port, password=password)
        host = RemoteHost(HostConfig(net=net, stream=stream, bind_require_password=True))
        # Wake GUI immediately when clipboard arrives (queued across threads).
        host.clipboard_notify = lambda: self.host_clip_wakeup.emit()
        self._host = host

        def runner() -> None:
            try:
                host.run()
            except Exception:
                log.exception("host failed")
                self.host_crashed.emit()

        self._host_thread = threading.Thread(target=runner, name="gui-host", daemon=True)
        self._host_thread.start()
        self._start_host_clipboard()
        self.btn_host.setText(i18n.t("stop_host"))
        self.btn_host.setObjectName("danger")
        self.btn_host.style().unpolish(self.btn_host)
        self.btn_host.style().polish(self.btn_host)
        self.lbl_host_state.setText(i18n.t("host_on", port=port))
        self.lbl_host_state.setStyleSheet("color:#7DFFCE; font-size:12px; font-weight:600;")
        self._set_status(i18n.t("host_started", port=port))

    def _enqueue_host_clipboard(self, packet: bytes) -> None:
        host = self._host
        if host is None or not host.session_live.is_set():
            return
        try:
            host.clipboard_out.put_nowait(packet)
        except queue.Full:
            log.warning("host clipboard_out full")

    def _start_host_clipboard(self) -> None:
        self._stop_host_clipboard()
        self._host_clip = ClipboardBridge(
            send_packet=self._enqueue_host_clipboard,
            enabled_check=lambda: self._host is not None and self._host.session_live.is_set(),
            parent=self,
        )
        self._host_clip.status.connect(self._set_status)
        self._host_clip.start()
        self._host_clip_timer = QTimer(self)
        self._host_clip_timer.setInterval(100)
        self._host_clip_timer.timeout.connect(self._drain_host_clipboard_in)
        self._host_clip_timer.start()

    def _drain_host_clipboard_in(self) -> None:
        host = self._host
        bridge = self._host_clip
        if host is None:
            return
        try:
            if bridge is not None:
                while True:
                    try:
                        payload = host.clipboard_in.get_nowait()
                    except queue.Empty:
                        break
                    bridge.handle_remote_payload(payload)
        finally:
            # Unblock host recv loop waiting for clipboard apply.
            host.clipboard_applied.set()

    def _stop_host_clipboard(self) -> None:
        if self._host_clip_timer is not None:
            self._host_clip_timer.stop()
            self._host_clip_timer.deleteLater()
            self._host_clip_timer = None
        if self._host_clip is not None:
            self._host_clip.stop()
            self._host_clip.deleteLater()
            self._host_clip = None

    def _stop_host(self) -> None:
        self._stop_host_clipboard()
        host = self._host
        self._host = None
        if host:
            host.stop()
        self.btn_host.setText(i18n.t("start_host"))
        self.btn_host.setObjectName("primary")
        self.btn_host.style().unpolish(self.btn_host)
        self.btn_host.style().polish(self.btn_host)
        self.lbl_host_state.setText(i18n.t("host_off"))
        self.lbl_host_state.setStyleSheet(f"color:{C_WARN}; font-size:12px; font-weight:600;")
        self._set_status(i18n.t("host_stopped"))

    def _on_host_crashed(self) -> None:
        self._stop_host_clipboard()
        self._host = None
        self.btn_host.setText(i18n.t("start_host"))
        self.btn_host.setObjectName("primary")
        self.btn_host.style().unpolish(self.btn_host)
        self.btn_host.style().polish(self.btn_host)
        self.lbl_host_state.setText(i18n.t("host_crashed"))
        self.lbl_host_state.setStyleSheet(f"color:{C_DANGER}; font-size:12px; font-weight:600;")
        QMessageBox.critical(self, i18n.t("error"), i18n.t("host_crash_msg"))

    def _connect_selected(self) -> None:
        device = self._selected_device()
        if not device:
            QMessageBox.information(self, i18n.t("tip"), i18n.t("select_device"))
            return
        self._launch_client(device.host, device.port, device.password, device.name, device.id)

    def _quick_connect(self) -> None:
        host, ok = QInputDialog.getText(self, i18n.t("quick_connect"), i18n.t("quick_host"))
        if not ok or not host.strip():
            return
        port_s, ok = QInputDialog.getText(
            self, i18n.t("quick_connect"), i18n.t("quick_port"), text="5959"
        )
        if not ok:
            return
        try:
            port = int(port_s)
        except ValueError:
            QMessageBox.warning(self, i18n.t("tip"), i18n.t("bad_port"))
            return
        password, ok = QInputDialog.getText(
            self,
            i18n.t("quick_connect"),
            i18n.t("quick_password"),
            echo=Password,
        )
        if not ok:
            return
        save = (
            QMessageBox.question(self, i18n.t("quick_connect"), i18n.t("quick_save"))
            == Yes
        )
        device_id = None
        if save:
            device = Device.create(name=host.strip(), host=host.strip(), port=port, password=password)
            self.store.upsert(device)
            device_id = device.id
            self._reload_table()
        self._launch_client(host.strip(), port, password, host.strip(), device_id)

    def _launch_client(
        self,
        host: str,
        port: int,
        password: str,
        title: str,
        device_id: str | None,
    ) -> None:
        stream = StreamConfig(
            max_fps=self.store.settings.max_fps,
            jpeg_quality=self.store.settings.jpeg_quality,
            scale=self.store.settings.scale,
        ).clamp()
        cfg = ClientConfig(
            net=NetConfig(host=host, port=port, password=password),
            stream=stream,
            window_title=i18n.t("viewer_title", name=title),
            reconnect=True,
        )
        win = RemoteClientWindow(cfg, parent=None)
        win.setAttribute(WA_DeleteOnClose, True)
        self._viewers.append(win)

        def _drop(*_: object, window: RemoteClientWindow = win) -> None:
            if window in self._viewers:
                self._viewers.remove(window)

        win.destroyed.connect(_drop)
        win.show()
        win.start()
        if device_id:
            self.store.touch_connected(device_id)
            self._reload_table()
        self._set_status(i18n.t("connecting", title=title, host=host, port=port))

    def _probe_now(self) -> None:
        threading.Thread(target=self._probe_devices, name="probe-now", daemon=True).start()

    def _start_probe_loop(self) -> None:
        def loop() -> None:
            while not self._probe_stop.is_set():
                self._probe_devices()
                self._probe_stop.wait(max(3.0, self.store.settings.auto_probe_s))

        threading.Thread(target=loop, name="probe-loop", daemon=True).start()

    def _probe_devices(self) -> None:
        results: dict[str, str] = {}
        for device in list(self.store.devices):
            results[device.id] = "online" if probe_online(device.host, device.port) else "offline"
        self.probe_done.emit(results)

    def _apply_probe(self, results: dict) -> None:
        self._status.update(results)
        self._reload_table()
        online_n = sum(1 for v in results.values() if v == "online")
        self._set_status(i18n.t("status_updated", online=online_n, total=len(results)))

    def closeEvent(self, event) -> None:  # noqa: N802
        self._probe_stop.set()
        self._stop_host_clipboard()
        if self._host is not None:
            self._stop_host()
        for win in list(self._viewers):
            win.close()
        super().closeEvent(event)


def _fmt_time(ts: float | None) -> str:
    if not ts:
        return "-"
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))


def run_app() -> None:
    ensure_utf8_stdio()
    app = QApplication.instance() or QApplication([])
    apply_app_font(app, point_size=10)
    app.setStyle("Fusion")
    app.setStyleSheet(APP_QSS)
    app.setAttribute(AA_DontShowIconsInMenus, False)
    win = MainWindow()
    win.show()
    QTimer.singleShot(200, win._probe_now)
    (getattr(app, "exec_", None) or app.exec)()
