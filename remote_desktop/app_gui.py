from __future__ import annotations

import logging
import queue
import threading
import time

from .qt_bind import (
    AA_DontShowIconsInMenus,
    Antialiasing,
    Cancel,
    DialogAccepted,
    Horizontal,
    NoFocus,
    NoPen,
    Password,
    PointingHandCursor,
    QAbstractButton,
    QApplication,
    QColor,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPainter,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTimer,
    QVBoxLayout,
    QWidget,
    Save,
    Signal,
    WA_DeleteOnClose,
    Yes,
    dialog_exec,
    make_dialog_button_box,
    qt_enum_eq,
)

from .client import RemoteClientWindow
from .clipboard_sync import ClipboardBridge
from .config import ClientConfig, HostConfig, NetConfig, StreamConfig
from .devices import Device, DeviceStore, list_local_ipv4, make_verify_code, probe_online
from .host import RemoteHost
from .i18n import i18n
from .qt_fonts import apply_app_font, ensure_utf8_stdio
from .confirm_dialog import ask_confirm
from .themes import (
    DEFAULT_THEME,
    ThemeColors,
    build_stylesheet,
    resolve_theme,
    set_current_theme,
    theme_ids,
)

log = logging.getLogger(__name__)

# Active palette (updated by apply_theme).
THEME: ThemeColors = resolve_theme(DEFAULT_THEME)


def apply_theme(app: QApplication | None, theme_id: str | None) -> ThemeColors:
    global THEME
    THEME = set_current_theme(theme_id)
    if app is not None:
        app.setStyleSheet(build_stylesheet(THEME.id))
    return THEME


def _status_style(status_key: str) -> tuple[str, str]:
    if status_key == "online":
        return i18n.t("online"), "color:%s; background:%s;" % (THEME.online, THEME.online_bg)
    if status_key == "offline":
        return i18n.t("offline"), "color:%s; background:%s;" % (THEME.offline, THEME.offline_bg)
    return i18n.t("unknown"), "color:%s; background:%s;" % (THEME.muted, THEME.unknown_bg)


class ToggleSwitch(QAbstractButton):
    """Compact pill switch for the dark side rail."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(PointingHandCursor)
        self.setFocusPolicy(NoFocus)
        self.setFixedSize(46, 26)

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(Antialiasing, True)
        checked = self.isChecked()
        track = QColor(THEME.accent if checked else THEME.side_line)
        thumb = QColor("#FFFFFF")
        if not self.isEnabled():
            track = QColor(THEME.side_line)
            thumb = QColor("#C8D0D6")

        painter.setPen(NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(0, 0, self.width(), self.height(), 13, 13)

        margin = 3
        diameter = self.height() - margin * 2
        x = self.width() - margin - diameter if checked else margin
        painter.setBrush(thumb)
        painter.drawEllipse(x, margin, diameter, diameter)


class DeviceCard(QFrame):
    """Interactive device tile for the device grid."""

    selected = Signal(str)
    activated = Signal(str)

    def __init__(self, device: Device, status_key: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.device_id = device.id
        self.setObjectName("deviceCard")
        self.setCursor(PointingHandCursor)
        self.setMinimumWidth(220)
        self.setMaximumWidth(360)
        self.setProperty("selected", False)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)

        top = QHBoxLayout()
        self.lbl_status = QLabel()
        self.lbl_status.setObjectName("cardStatus")
        self.lbl_last = QLabel()
        self.lbl_last.setObjectName("cardMeta")
        top.addWidget(self.lbl_status, 0)
        top.addStretch(1)
        top.addWidget(self.lbl_last, 0)

        self.lbl_name = QLabel()
        self.lbl_name.setObjectName("cardName")
        self.lbl_name.setWordWrap(True)
        self.lbl_host = QLabel()
        self.lbl_host.setObjectName("cardHost")
        self.lbl_notes = QLabel()
        self.lbl_notes.setObjectName("cardMeta")
        self.lbl_notes.setWordWrap(True)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.btn_connect = QPushButton()
        self.btn_connect.setObjectName("primary")
        self.btn_connect.setCursor(PointingHandCursor)
        self.btn_connect.clicked.connect(lambda: self.activated.emit(self.device_id))
        bottom.addWidget(self.btn_connect)

        root.addLayout(top)
        root.addWidget(self.lbl_name)
        root.addWidget(self.lbl_host)
        root.addWidget(self.lbl_notes)
        root.addStretch(1)
        root.addLayout(bottom)

        self.bind(device, status_key)

    def bind(self, device: Device, status_key: str) -> None:
        status_text, status_qss = _status_style(status_key)
        self.lbl_status.setText(status_text)
        self.lbl_status.setStyleSheet(status_qss)
        if device.last_connected:
            self.lbl_last.setText(i18n.t("last_connected", time=_fmt_time(device.last_connected)))
        else:
            self.lbl_last.setText(i18n.t("never_connected"))
        self.lbl_name.setText(device.name)
        self.lbl_host.setText("%s:%s" % (device.host, device.port))
        notes = (device.notes or "").strip()
        self.lbl_notes.setText(notes)
        self.lbl_notes.setVisible(bool(notes))
        self.btn_connect.setText(i18n.t("remote_control"))

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self.selected.emit(self.device_id)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self.activated.emit(self.device_id)
        super().mouseDoubleClickEvent(event)


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

        buttons = make_dialog_button_box(Save, Cancel)
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

        self.theme = QComboBox()
        for theme_id in theme_ids():
            label = i18n.t("theme_%s" % theme_id)
            if label == "theme_%s" % theme_id:
                label = theme_id
            self.theme.addItem(label, theme_id)
        tidx = self.theme.findData(store.settings.theme or DEFAULT_THEME)
        self.theme.setCurrentIndex(max(0, tidx))

        self.fps = QLineEdit(str(store.settings.max_fps))
        self.quality = QLineEdit(str(store.settings.jpeg_quality))
        self.scale = QLineEdit(str(store.settings.scale))
        self.probe = QLineEdit(str(store.settings.auto_probe_s))

        form.addRow(i18n.t("language"), self.lang)
        form.addRow(i18n.t("theme"), self.theme)
        form.addRow(i18n.t("max_fps"), self.fps)
        form.addRow(i18n.t("jpeg_quality"), self.quality)
        form.addRow(i18n.t("scale"), self.scale)
        form.addRow(i18n.t("probe_interval"), self.probe)

        self.btn_hd = QPushButton(i18n.t("hd_preset"))
        self.btn_hd.setObjectName("primary")
        self.btn_hd.clicked.connect(self._apply_hd)
        form.addRow(self.btn_hd)

        hint = QLabel(i18n.t("font_hint"))
        hint.setObjectName("pageMuted")
        hint.setWordWrap(True)
        form.addRow(hint)

        buttons = make_dialog_button_box(Save, Cancel)
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
            self.store.settings.theme = str(self.theme.currentData() or DEFAULT_THEME)
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
        self._selected_device_id: str | None = None
        self._device_cards: dict[str, DeviceCard] = {}

        self.probe_done.connect(self._apply_probe)
        self.host_crashed.connect(self._on_host_crashed)
        self.host_clip_wakeup.connect(self._drain_host_clipboard_in)

        self._build()
        self.retranslate()
        self._refresh_local()
        self._reload_devices()
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
        self.lbl_side_hint.setObjectName("sideMuted")
        self.lbl_side_hint.setWordWrap(True)

        card = QFrame()
        card.setObjectName("infoCard")
        card_l = QVBoxLayout(card)
        card_l.setContentsMargins(14, 14, 14, 14)
        card_l.setSpacing(8)

        self.lbl_local_name = QLabel()
        self.lbl_local_name.setObjectName("sideSoft")
        self.lbl_code_hint = QLabel()
        self.lbl_code_hint.setObjectName("sideMuted")
        self.lbl_code = QLabel()
        self.lbl_code.setObjectName("codeValue")
        self.lbl_verify_title = QLabel()
        self.lbl_verify_title.setObjectName("sideMuted")
        self.lbl_show_code = QLabel()
        self.lbl_show_code.setObjectName("sideMuted")
        self.lbl_show_code.setCursor(PointingHandCursor)
        self.chk_show = ToggleSwitch()
        self.chk_show.toggled.connect(self._on_show_code_toggled)
        # Clicking the text also toggles the switch.
        self.lbl_show_code.mousePressEvent = (  # type: ignore[method-assign]
            lambda event: self.chk_show.toggle()
        )
        self.lbl_verify = QLabel()
        self.lbl_verify.setObjectName("passValue")

        verify_head = QHBoxLayout()
        verify_head.setSpacing(8)
        verify_head.addWidget(self.lbl_verify_title, 1)
        verify_head.addWidget(self.lbl_show_code, 0)
        verify_head.addWidget(self.chk_show, 0)

        port_row = QHBoxLayout()
        self.lbl_port = QLabel()
        self.lbl_port.setObjectName("sideMuted")
        self.edit_port = QLineEdit()
        self.edit_port.setFixedWidth(90)
        port_row.addWidget(self.lbl_port)
        port_row.addWidget(self.edit_port)
        port_row.addStretch(1)

        self.lbl_ips_title = QLabel()
        self.lbl_ips_title.setObjectName("sideMuted")
        self.lbl_ips = QLabel()
        self.lbl_ips.setObjectName("sideIp")
        self.lbl_ips.setWordWrap(True)

        card_l.addWidget(self.lbl_local_name)
        card_l.addSpacing(4)
        card_l.addWidget(self.lbl_code_hint)
        card_l.addWidget(self.lbl_code)
        card_l.addSpacing(6)
        card_l.addLayout(verify_head)
        card_l.addWidget(self.lbl_verify)
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
        self.lbl_host_state.setObjectName("hostWarn")

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
        self.lbl_search.setObjectName("pageMuted")
        self.search = QLineEdit()
        self.search.textChanged.connect(self._reload_devices)
        search_row.addWidget(self.lbl_search)
        search_row.addWidget(self.search, 1)

        list_card = QFrame()
        list_card.setObjectName("mainCard")
        list_l = QVBoxLayout(list_card)
        list_l.setContentsMargins(12, 12, 12, 12)

        self.device_scroll = QScrollArea()
        self.device_scroll.setObjectName("deviceScroll")
        self.device_scroll.setWidgetResizable(True)
        no_frame = getattr(QFrame, "NoFrame", None)
        if no_frame is None:
            shape_ns = getattr(QFrame, "Shape", None)
            no_frame = getattr(shape_ns, "NoFrame", 0) if shape_ns is not None else 0
        self.device_scroll.setFrameShape(no_frame)

        self.device_grid_host = QWidget()
        self.device_grid = QGridLayout(self.device_grid_host)
        self.device_grid.setContentsMargins(4, 4, 4, 4)
        self.device_grid.setHorizontalSpacing(12)
        self.device_grid.setVerticalSpacing(12)
        self.device_scroll.setWidget(self.device_grid_host)

        self.lbl_device_empty = QLabel()
        self.lbl_device_empty.setObjectName("cardEmpty")
        self.lbl_device_empty.setWordWrap(True)
        self.lbl_device_empty.hide()

        list_l.addWidget(self.device_scroll, 1)
        list_l.addWidget(self.lbl_device_empty)

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
        self.status.setObjectName("statusBar")

        main_l.addLayout(header)
        main_l.addLayout(search_row)
        main_l.addWidget(list_card, 1)
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
        self._sync_show_code_label()
        self.lbl_port.setText(i18n.t("port"))
        self.lbl_ips_title.setText(i18n.t("local_ip"))
        self.btn_refresh_local.setText(i18n.t("refresh_local"))
        self.btn_regen.setText(i18n.t("regen_code"))
        if self._host is None:
            self.btn_host.setText(i18n.t("start_host"))
            self._restyle(self.btn_host, "primary")
            self.lbl_host_state.setText(i18n.t("host_off"))
            self._restyle(self.lbl_host_state, "hostWarn")
        else:
            self.btn_host.setText(i18n.t("stop_host"))
            self._restyle(self.btn_host, "danger")
            self.lbl_host_state.setText(i18n.t("host_on", port=self.store.settings.host_port))
            self._restyle(self.lbl_host_state, "hostOk")
        self.lbl_list_title.setText(i18n.t("device_list"))
        self.lbl_list_sub.setText(i18n.t("device_list_sub"))
        self.btn_settings.setText(i18n.t("settings"))
        self.btn_quick.setText(i18n.t("quick_connect"))
        self.lbl_search.setText(i18n.t("search"))
        self.search.setPlaceholderText(i18n.t("search_ph"))
        self.btn_add.setText(i18n.t("add_device"))
        self.btn_edit.setText(i18n.t("edit"))
        self.btn_del.setText(i18n.t("delete"))
        self.btn_probe.setText(i18n.t("refresh_status"))
        self.btn_connect.setText(i18n.t("remote_control"))
        self._refresh_local()
        self._reload_devices()
        if not self.status.text():
            self.status.setText(i18n.t("ready"))

    def _restyle(self, widget: QWidget, object_name: str) -> None:
        """Switch objectName and clear inline styles so theme QSS applies cleanly."""
        widget.setStyleSheet("")
        widget.setObjectName(object_name)
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()

    def _set_status(self, text: str) -> None:
        self.status.setText(text)

    def _format_code(self, code: str) -> str:
        digits = "".join(ch for ch in code if ch.isdigit())
        if len(digits) == 9:
            return f"{digits[:3]} {digits[3:6]} {digits[6:]}"
        return code

    def _sync_show_code_label(self) -> None:
        if self.chk_show.isChecked():
            self.lbl_show_code.setText(i18n.t("hide_code"))
        else:
            self.lbl_show_code.setText(i18n.t("show_code"))

    def _on_show_code_toggled(self, _checked: bool = False) -> None:
        self._sync_show_code_label()
        self._refresh_local()
        self.chk_show.update()

    def _refresh_local(self) -> None:
        s = self.store.settings
        self.lbl_local_name.setText(i18n.t("local_name", name=s.local_name))
        self.lbl_code.setText(self._format_code(s.device_code))
        pwd = s.host_password
        self.lbl_verify.setText(pwd if self.chk_show.isChecked() else ("•" * max(4, len(pwd))))
        self.edit_port.setText(str(s.host_port))
        ips = list_local_ipv4()
        self.lbl_ips.setText("\n".join(ips))
        self._sync_show_code_label()

    def _filtered_devices(self) -> list[Device]:
        keyword = self.search.text().strip().lower()
        rows: list[Device] = []
        for device in self.store.devices:
            hay = "%s %s %s" % (device.name, device.host, device.notes)
            if keyword and keyword not in hay.lower():
                continue
            rows.append(device)
        return rows

    def _clear_device_grid(self) -> None:
        while self.device_grid.count():
            item = self.device_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._device_cards.clear()

    def _reload_devices(self) -> None:
        rows = self._filtered_devices()
        selected = self._selected_device_id
        if selected and selected not in {d.id for d in rows}:
            selected = None
            self._selected_device_id = None

        self._clear_device_grid()

        if not rows:
            self.device_scroll.hide()
            self.lbl_device_empty.show()
            if self.search.text().strip():
                self.lbl_device_empty.setText(i18n.t("device_empty_search"))
            else:
                self.lbl_device_empty.setText(i18n.t("device_empty"))
            return

        self.lbl_device_empty.hide()
        self.device_scroll.show()

        cols = self._device_columns()
        self._laid_cols = cols
        for index, device in enumerate(rows):
            status_key = self._status.get(device.id, "unknown")
            card = DeviceCard(device, status_key, self.device_grid_host)
            card.selected.connect(self._on_card_selected)
            card.activated.connect(self._on_card_activated)
            card.set_selected(device.id == selected)
            self._device_cards[device.id] = card
            self.device_grid.addWidget(card, index // cols, index % cols)

        # Keep cards left-aligned in the last row.
        self.device_grid.setRowStretch((len(rows) + cols - 1) // cols, 1)
        self.device_grid.setColumnStretch(cols, 1)

    def _device_columns(self) -> int:
        width = max(1, self.device_scroll.viewport().width())
        return max(1, min(3, width // 260))

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if not getattr(self, "_device_cards", None):
            return
        cols = self._device_columns()
        if cols != getattr(self, "_laid_cols", None):
            self._reload_devices()

    def _on_card_selected(self, device_id: str) -> None:
        self._selected_device_id = device_id
        for did, card in self._device_cards.items():
            card.set_selected(did == device_id)

    def _on_card_activated(self, device_id: str) -> None:
        self._selected_device_id = device_id
        device = self.store.get(device_id)
        if device is None:
            return
        self._launch_client(device.host, device.port, device.password, device.name, device.id)

    def _selected_device(self) -> Device | None:
        if not self._selected_device_id:
            return None
        return self.store.get(self._selected_device_id)

    def _add_device(self) -> None:
        dialog = DeviceDialog(self, i18n.t("add_title"))
        if qt_enum_eq(dialog_exec(dialog), DialogAccepted) and dialog.result_device:
            self.store.upsert(dialog.result_device)
            self._selected_device_id = dialog.result_device.id
            self._reload_devices()
            self._set_status(i18n.t("added", name=dialog.result_device.name))
            self._probe_now()

    def _edit_device(self) -> None:
        device = self._selected_device()
        if not device:
            QMessageBox.information(self, i18n.t("tip"), i18n.t("select_device"))
            return
        dialog = DeviceDialog(self, i18n.t("edit_title"), device)
        if qt_enum_eq(dialog_exec(dialog), DialogAccepted) and dialog.result_device:
            self.store.upsert(dialog.result_device)
            self._selected_device_id = dialog.result_device.id
            self._reload_devices()
            self._set_status(i18n.t("updated", name=dialog.result_device.name))

    def _delete_device(self) -> None:
        device = self._selected_device()
        if not device:
            QMessageBox.information(self, i18n.t("tip"), i18n.t("select_device"))
            return
        if not qt_enum_eq(
            QMessageBox.question(
                self,
                i18n.t("confirm"),
                i18n.t("delete_confirm", name=device.name),
            ),
            Yes,
        ):
            return
        self.store.remove(device.id)
        self._status.pop(device.id, None)
        self._selected_device_id = None
        self._reload_devices()
        self._set_status(i18n.t("device_deleted"))

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self, self.store)
        if not qt_enum_eq(dialog_exec(dialog), DialogAccepted):
            return
        i18n.set_lang(self.store.settings.language)
        apply_theme(QApplication.instance(), self.store.settings.theme)
        # Force every themed widget to drop stale inline colors.
        self.retranslate()
        self._restyle(self.status, "statusBar")
        self._restyle(self.lbl_search, "pageMuted")
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
        self._restyle(self.btn_host, "danger")
        self.lbl_host_state.setText(i18n.t("host_on", port=port))
        self._restyle(self.lbl_host_state, "hostOk")
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
        self._restyle(self.btn_host, "primary")
        self.lbl_host_state.setText(i18n.t("host_off"))
        self._restyle(self.lbl_host_state, "hostWarn")
        self._set_status(i18n.t("host_stopped"))

    def _on_host_crashed(self) -> None:
        self._stop_host_clipboard()
        self._host = None
        self.btn_host.setText(i18n.t("start_host"))
        self._restyle(self.btn_host, "primary")
        self.lbl_host_state.setText(i18n.t("host_crashed"))
        self._restyle(self.lbl_host_state, "hostDanger")
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
        save = qt_enum_eq(
            QMessageBox.question(self, i18n.t("quick_connect"), i18n.t("quick_save")),
            Yes,
        )
        device_id = None
        if save:
            device = Device.create(name=host.strip(), host=host.strip(), port=port, password=password)
            self.store.upsert(device)
            device_id = device.id
            self._reload_devices()
        self._launch_client(host.strip(), port, password, host.strip(), device_id)

    def _find_viewer(
        self,
        host: str,
        port: int,
        device_id: str | None,
    ) -> RemoteClientWindow | None:
        host_key = host.strip().lower()
        port_key = int(port)
        for win in list(self._viewers):
            try:
                win_host = str(win.config.net.host).strip().lower()
                win_port = int(win.config.net.port)
                win_id = getattr(win, "device_id", None)
            except RuntimeError:
                # C++ object already deleted.
                if win in self._viewers:
                    self._viewers.remove(win)
                continue
            if device_id and win_id and win_id == device_id:
                return win
            if win_host == host_key and win_port == port_key:
                return win
        return None

    def _focus_viewer(self, win: RemoteClientWindow, title: str) -> None:
        try:
            if win.isMinimized():
                win.showNormal()
            win.show()
            win.raise_()
            win.activateWindow()
            app = QApplication.instance()
            if app is not None:
                app.setActiveWindow(win)
        except RuntimeError:
            return
        self._set_status(i18n.t("viewer_focus_existing", title=title))

    def _launch_client(
        self,
        host: str,
        port: int,
        password: str,
        title: str,
        device_id: str | None,
    ) -> None:
        existing = self._find_viewer(host, port, device_id)
        if existing is not None:
            self._focus_viewer(existing, title)
            if device_id:
                self.store.touch_connected(device_id)
                self._reload_devices()
            return

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
        win.device_id = device_id
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
            self._reload_devices()
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
        self._reload_devices()
        online_n = sum(1 for v in results.values() if v == "online")
        self._set_status(i18n.t("status_updated", online=online_n, total=len(results)))

    def closeEvent(self, event) -> None:  # noqa: N802
        if not ask_confirm(
            self,
            title=i18n.t("close_main_title"),
            message=i18n.t("close_main_confirm"),
            eyebrow=i18n.t("brand"),
            ok_text=i18n.t("close_action"),
            cancel_text=i18n.t("keep_open"),
            danger=True,
        ):
            event.ignore()
            return

        self._probe_stop.set()
        self._stop_host_clipboard()
        if self._host is not None:
            self._stop_host()
        for win in list(self._viewers):
            try:
                win.force_close = True
                win.close()
            except RuntimeError:
                pass
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
    app.setAttribute(AA_DontShowIconsInMenus, False)
    bootstrap = DeviceStore()
    i18n.set_lang(bootstrap.settings.language)
    apply_theme(app, bootstrap.settings.theme)
    win = MainWindow()
    win.show()
    QTimer.singleShot(200, win._probe_now)
    (getattr(app, "exec_", None) or app.exec)()
