from __future__ import annotations

import logging
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
from .config import ClientConfig, HostConfig, NetConfig, StreamConfig
from .devices import Device, DeviceStore, list_local_ipv4, make_verify_code, probe_online
from .host import RemoteHost
from .i18n import i18n
from .qt_fonts import apply_app_font, ensure_utf8_stdio

log = logging.getLogger(__name__)

SIDE_BG = "#1F2A30"
ACCENT = "#2F9E5E"
ACCENT_DARK = "#247A49"
DANGER = "#C24B4B"


class DeviceDialog(QDialog):
    def __init__(self, parent: QWidget, title: str, device: Device | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.result_device: Device | None = None
        self._device = device

        form = QFormLayout(self)
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

        buttons = QDialogButtonBox(
            Save | Cancel
        )
        buttons.button(Save).setText(i18n.t("save"))
        buttons.button(Cancel).setText(i18n.t("cancel"))
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
        form = QFormLayout(self)

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

        hint = QLabel(i18n.t("font_hint"))
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #6B7780;")
        form.addRow(hint)

        buttons = QDialogButtonBox(
            Save | Cancel
        )
        buttons.button(Save).setText(i18n.t("save"))
        buttons.button(Cancel).setText(i18n.t("cancel"))
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _save(self) -> None:
        try:
            self.store.settings.max_fps = float(self.fps.text())
            self.store.settings.jpeg_quality = int(self.quality.text())
            self.store.settings.scale = float(self.scale.text())
            self.store.settings.auto_probe_s = max(3.0, float(self.probe.text()))
            self.store.settings.language = str(self.lang.currentData())
        except ValueError:
            QMessageBox.warning(self, i18n.t("tip"), i18n.t("invalid_number"))
            return
        self.store.save()
        self.accept()


class MainWindow(QMainWindow):
    probe_done = Signal(dict)
    host_crashed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.store = DeviceStore()
        i18n.set_lang(self.store.settings.language)
        self._status: dict[str, str] = {}
        self._host: RemoteHost | None = None
        self._host_thread: threading.Thread | None = None
        self._probe_stop = threading.Event()
        self._viewers: list[RemoteClientWindow] = []

        self.probe_done.connect(self._apply_probe)
        self.host_crashed.connect(self._on_host_crashed)

        self._build()
        self.retranslate()
        self._refresh_local()
        self._reload_table()
        self._start_probe_loop()
        i18n.on_change(self.retranslate)

    def _build(self) -> None:
        self.resize(1000, 640)
        root = QWidget()
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        splitter = QSplitter(Horizontal)
        outer.addWidget(splitter)

        # Side panel
        side = QFrame()
        side.setObjectName("side")
        side.setStyleSheet(
            f"""
            QFrame#side {{ background: {SIDE_BG}; }}
            QLabel {{ color: #E8EEF2; }}
            QLabel#muted {{ color: #9AA7B0; }}
            QLabel#code {{ color: white; font-size: 22px; font-weight: 700; }}
            QLineEdit {{ background: #2B3940; color: white; border: 1px solid #3A4A53; padding: 4px; }}
            QCheckBox {{ color: #9AA7B0; }}
            """
        )
        side_l = QVBoxLayout(side)
        side_l.setContentsMargins(20, 22, 20, 20)
        self.lbl_side_title = QLabel()
        self.lbl_side_title.setStyleSheet("font-size: 16px; font-weight: 700; color: white;")
        self.lbl_side_hint = QLabel()
        self.lbl_side_hint.setObjectName("muted")
        self.lbl_side_hint.setWordWrap(True)
        self.lbl_local_name = QLabel()
        self.lbl_code = QLabel()
        self.lbl_code.setObjectName("code")
        self.lbl_code_hint = QLabel()
        self.lbl_code_hint.setObjectName("muted")
        self.lbl_verify_title = QLabel()
        self.lbl_verify_title.setObjectName("muted")
        self.lbl_verify = QLabel()
        self.lbl_verify.setStyleSheet("font-size: 18px; font-weight: 700; color: white;")
        self.chk_show = QCheckBox()
        self.chk_show.toggled.connect(self._refresh_local)

        port_row = QHBoxLayout()
        self.lbl_port = QLabel()
        self.lbl_port.setObjectName("muted")
        self.edit_port = QLineEdit()
        self.edit_port.setFixedWidth(80)
        port_row.addWidget(self.lbl_port)
        port_row.addWidget(self.edit_port)
        port_row.addStretch(1)

        self.lbl_ips = QLabel()
        self.lbl_ips.setObjectName("muted")
        self.lbl_ips.setWordWrap(True)

        self.btn_host = QPushButton()
        self.btn_host.setCursor(PointingHandCursor)
        self.btn_host.clicked.connect(self._toggle_host)
        self._style_accent_button(self.btn_host)

        self.btn_refresh_local = QPushButton()
        self.btn_refresh_local.clicked.connect(self._refresh_local)
        self._style_side_button(self.btn_refresh_local)

        self.btn_regen = QPushButton()
        self.btn_regen.clicked.connect(self._regen_password)
        self._style_side_button(self.btn_regen)

        self.lbl_host_state = QLabel()
        self.lbl_host_state.setStyleSheet("color: #F0C674;")

        side_l.addWidget(self.lbl_side_title)
        side_l.addWidget(self.lbl_side_hint)
        side_l.addSpacing(8)
        side_l.addWidget(self.lbl_local_name)
        side_l.addSpacing(8)
        side_l.addWidget(self.lbl_code)
        side_l.addWidget(self.lbl_code_hint)
        side_l.addSpacing(12)
        side_l.addWidget(self.lbl_verify_title)
        side_l.addWidget(self.lbl_verify)
        side_l.addWidget(self.chk_show)
        side_l.addSpacing(8)
        side_l.addLayout(port_row)
        side_l.addSpacing(8)
        side_l.addWidget(self.lbl_ips)
        side_l.addSpacing(16)
        side_l.addWidget(self.btn_host)
        side_l.addWidget(self.btn_refresh_local)
        side_l.addWidget(self.btn_regen)
        side_l.addSpacing(12)
        side_l.addWidget(self.lbl_host_state)
        side_l.addStretch(1)
        side.setMinimumWidth(280)
        side.setMaximumWidth(340)

        # Main panel
        main = QWidget()
        main_l = QVBoxLayout(main)
        main_l.setContentsMargins(18, 16, 18, 12)

        header = QHBoxLayout()
        self.lbl_list_title = QLabel()
        self.lbl_list_title.setStyleSheet("font-size: 18px; font-weight: 700;")
        self.btn_settings = QPushButton()
        self.btn_settings.clicked.connect(self._open_settings)
        self.btn_quick = QPushButton()
        self.btn_quick.clicked.connect(self._quick_connect)
        header.addWidget(self.lbl_list_title)
        header.addStretch(1)
        header.addWidget(self.btn_quick)
        header.addWidget(self.btn_settings)

        search_row = QHBoxLayout()
        self.lbl_search = QLabel()
        self.search = QLineEdit()
        self.search.textChanged.connect(self._reload_table)
        search_row.addWidget(self.lbl_search)
        search_row.addWidget(self.search, 1)

        self.table = QTableWidget(0, 4)
        self.table.setSelectionBehavior(SelectRows)
        self.table.setSelectionMode(SingleSelection)
        self.table.setEditTriggers(NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(Stretch)
        self.table.doubleClicked.connect(self._connect_selected)

        actions = QHBoxLayout()
        self.btn_add = QPushButton()
        self.btn_edit = QPushButton()
        self.btn_del = QPushButton()
        self.btn_probe = QPushButton()
        self.btn_connect = QPushButton()
        self.btn_add.clicked.connect(self._add_device)
        self.btn_edit.clicked.connect(self._edit_device)
        self.btn_del.clicked.connect(self._delete_device)
        self.btn_probe.clicked.connect(self._probe_now)
        self.btn_connect.clicked.connect(self._connect_selected)
        self._style_accent_button(self.btn_connect)
        actions.addWidget(self.btn_add)
        actions.addWidget(self.btn_edit)
        actions.addWidget(self.btn_del)
        actions.addWidget(self.btn_probe)
        actions.addStretch(1)
        actions.addWidget(self.btn_connect)

        self.status = QLabel()
        self.status.setStyleSheet("color: #6B7780;")

        main_l.addLayout(header)
        main_l.addLayout(search_row)
        main_l.addWidget(self.table, 1)
        main_l.addLayout(actions)
        main_l.addWidget(self.status)

        splitter.addWidget(side)
        splitter.addWidget(main)
        splitter.setStretchFactor(1, 1)

    def retranslate(self) -> None:
        self.setWindowTitle(i18n.t("app_title"))
        self.lbl_side_title.setText(i18n.t("local_control"))
        self.lbl_side_hint.setText(i18n.t("local_control_hint"))
        self.lbl_code_hint.setText(i18n.t("device_code"))
        self.lbl_verify_title.setText(i18n.t("verify_code"))
        self.chk_show.setText(i18n.t("show"))
        self.lbl_port.setText(i18n.t("port"))
        self.btn_refresh_local.setText(i18n.t("refresh_local"))
        self.btn_regen.setText(i18n.t("regen_code"))
        if self._host is None:
            self.btn_host.setText(i18n.t("start_host"))
            self.lbl_host_state.setText(i18n.t("host_off"))
        else:
            self.btn_host.setText(i18n.t("stop_host"))
            self.lbl_host_state.setText(i18n.t("host_on", port=self.store.settings.host_port))
        self.lbl_list_title.setText(i18n.t("device_list"))
        self.btn_settings.setText(i18n.t("settings"))
        self.btn_quick.setText(i18n.t("quick_connect"))
        self.lbl_search.setText(i18n.t("search"))
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

    @staticmethod
    def _style_accent_button(btn: QPushButton) -> None:
        btn.setStyleSheet(
            f"""
            QPushButton {{
                background: {ACCENT}; color: white; border: none;
                padding: 8px 14px; font-weight: 700; border-radius: 4px;
            }}
            QPushButton:hover {{ background: {ACCENT_DARK}; }}
            """
        )

    @staticmethod
    def _style_side_button(btn: QPushButton) -> None:
        btn.setStyleSheet(
            """
            QPushButton {
                background: #2B3940; color: white; border: none;
                padding: 7px 10px; border-radius: 4px;
            }
            QPushButton:hover { background: #364851; }
            """
        )

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
        self.lbl_verify.setText(pwd if self.chk_show.isChecked() else ("*" * max(4, len(pwd))))
        self.edit_port.setText(str(s.host_port))
        ips = list_local_ipv4()
        self.lbl_ips.setText(i18n.t("local_ip") + "\n" + "\n".join(ips))

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
                "online": QColor("#1B8A4A"),
                "offline": QColor("#A33B3B"),
            }.get(status_key, QColor("#8A8F96"))

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
        self._host = host

        def runner() -> None:
            try:
                host.run()
            except Exception:
                log.exception("host failed")
                self.host_crashed.emit()

        self._host_thread = threading.Thread(target=runner, name="gui-host", daemon=True)
        self._host_thread.start()
        self.btn_host.setText(i18n.t("stop_host"))
        self.btn_host.setStyleSheet(
            f"""
            QPushButton {{
                background: {DANGER}; color: white; border: none;
                padding: 8px 14px; font-weight: 700; border-radius: 4px;
            }}
            QPushButton:hover {{ background: #9E3B3B; }}
            """
        )
        self.lbl_host_state.setText(i18n.t("host_on", port=port))
        self.lbl_host_state.setStyleSheet("color: #7DCEA0;")
        self._set_status(i18n.t("host_started", port=port))

    def _stop_host(self) -> None:
        host = self._host
        self._host = None
        if host:
            host.stop()
        self.btn_host.setText(i18n.t("start_host"))
        self._style_accent_button(self.btn_host)
        self.lbl_host_state.setText(i18n.t("host_off"))
        self.lbl_host_state.setStyleSheet("color: #F0C674;")
        self._set_status(i18n.t("host_stopped"))

    def _on_host_crashed(self) -> None:
        self._host = None
        self.btn_host.setText(i18n.t("start_host"))
        self._style_accent_button(self.btn_host)
        self.lbl_host_state.setText(i18n.t("host_crashed"))
        self.lbl_host_state.setStyleSheet("color: #E07474;")
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
        # Same QApplication: no subprocess, shared fonts/i18n, less flicker risk.
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
    apply_app_font(app)
    # Avoid unnecessary style animations that can worsen perceived flicker.
    app.setAttribute(AA_DontShowIconsInMenus, False)
    win = MainWindow()
    win.show()
    # Defer first probe slightly so UI paints first.
    QTimer.singleShot(200, win._probe_now)
    (getattr(app, 'exec_', None) or app.exec)()
