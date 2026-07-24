from __future__ import annotations

import logging
import queue
import threading
import time
from pathlib import Path

from .qt_bind import (
    AA_DontShowIconsInMenus,
    AlignCenter,
    AlignLeft,
    AlignRight,
    AlignVCenter,
    Cancel,
    CustomContextMenu,
    DialogAccepted,
    Horizontal,
    HoverEnter,
    HoverLeave,
    FocusIn,
    LeftButton,
    MouseButtonPress,
    MouseButtonRelease,
    MouseMove,
    NoFocus,
    Normal,
    Password,
    PointingHandCursor,
    QAction,
    QApplication,
    QAbstractButton,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGuiApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QObject,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTimer,
    QVBoxLayout,
    QWidget,
    Save,
    Signal,
    WA_DeleteOnClose,
    WA_Hover,
    dialog_exec,
    make_dialog_button_box,
    make_alignment,
    menu_exec,
    qt_enum_eq,
    qt_has_flag,
    qt_enum_int,
)

from ..core.config import DEFAULT_PORT, ClientConfig, HostConfig, NetConfig, StreamConfig
from ..core.protocol import unpack_file_message
from ..features.clipboard_sync import ClipboardBridge
from ..features.autostart import apply as apply_autostart, supports_autostart
from ..features.devices import Device, DeviceStore, list_local_ipv4, make_verify_code, probe_device
from ..features.file_transfer import (
    FileAssembler,
    file_size_over_limit,
    list_directory,
    pack_download_error,
    pack_list_result,
    send_file,
)
from ..features.terminal_view import DirectTerminalWindow
from ..session.client import RemoteClientPage, ViewerShell
from ..session.host import RemoteHost
from .app_icon import apply_app_icon
from .confirm_dialog import (
    DialogDragBar,
    HeaderSettingsButton,
    PasswordEyeButton,
    ICON_CLOSE,
    ICON_MINIMIZE,
    WindowChromeButton,
    ask_confirm,
    make_frameless_dialog,
    show_error,
    show_info,
    show_warning,
)
from .i18n import i18n
from .qt_fonts import apply_app_font, ensure_utf8_stdio
from ..features.terminal_view import DirectTerminalWindow
from .tray_icon import AppTray
from .window_chrome import apply_window_chrome, bind_frameless_shell, ensure_windows_app_id
from .themes import (
    DEFAULT_THEME,
    ThemeColors,
    build_stylesheet,
    resolve_theme,
    set_current_theme,
    theme_ids,
)
from .toggle_switch import ToggleSwitch

log = logging.getLogger(__name__)

# Active palette (updated by apply_theme).
THEME: ThemeColors = resolve_theme(DEFAULT_THEME)


def _global_pos(event):
    if hasattr(event, "globalPosition"):
        return event.globalPosition().toPoint()
    return event.globalPos()


def _available_screen_size(widget: QWidget | None = None) -> tuple[int, int]:
    """Usable desktop size for the screen hosting *widget* (or primary)."""
    screen = None
    if widget is not None:
        try:
            handle = widget.window().windowHandle() if widget.window() else None
            if handle is not None:
                screen = handle.screen()
        except RuntimeError:
            screen = None
    if screen is None:
        screen = QGuiApplication.primaryScreen()
    if screen is None:
        app = QApplication.instance()
        if app is not None and hasattr(app, "primaryScreen"):
            screen = app.primaryScreen()
    if screen is not None:
        geo = screen.availableGeometry()
        return int(geo.width()), int(geo.height())
    return 1280, 720


def _widget_allows_window_drag(widget: QObject, host: QMainWindow) -> bool:
    """True when a frameless window may be dragged from this click target."""
    if not isinstance(widget, QWidget):
        return False
    if widget.window() is not host:
        return False
    blocked = (
        QLineEdit,
        QPushButton,
        QAbstractButton,
        QComboBox,
        ToggleSwitch,
    )
    w: QWidget | None = widget
    while w is not None:
        if w is host:
            break
        if w.objectName() == "deviceCard":
            return False
        if isinstance(w, blocked):
            return False
        w = w.parentWidget()
    return True


class _WindowDragFilter(QObject):
    """Allow dragging a frameless window from decorative UI regions."""

    def __init__(self, host: QMainWindow) -> None:
        super().__init__(host)
        self._host = host
        self._drag_offset = None

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        et = event.type()
        if qt_enum_eq(et, MouseButtonPress):
            if (
                qt_enum_eq(event.button(), LeftButton)
                and not self._host.isMaximized()
                and _widget_allows_window_drag(obj, self._host)
            ):
                self._drag_offset = _global_pos(event) - self._host.frameGeometry().topLeft()
            return False
        if qt_enum_eq(et, MouseMove):
            if self._drag_offset is not None and not self._host.isMaximized():
                if qt_has_flag(event.buttons(), LeftButton):
                    self._host.move(_global_pos(event) - self._drag_offset)
            return False
        if qt_enum_eq(et, MouseButtonRelease):
            self._drag_offset = None
            return False
        return False


class _DeviceCardSelectionFilter(QObject):
    """Drop the accent selection ring when focus or clicks leave device cards."""

    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window)
        self._window = window

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        et = event.type()
        if not isinstance(obj, QWidget):
            return False
        if qt_enum_eq(et, MouseButtonPress):
            if not self._window._widget_is_device_card(obj):
                self._window._clear_card_selection()
            return False
        if qt_enum_eq(et, FocusIn):
            app = QApplication.instance()
            if app is not None and app.activePopupWidget() is not None:
                return False
            if not self._window._widget_is_device_card(obj):
                self._window._clear_card_selection()
            return False
        return False


def apply_theme(app: QApplication | None, theme_id: str | None) -> ThemeColors:
    global THEME
    THEME = set_current_theme(theme_id)
    if app is not None:
        app.setStyleSheet(build_stylesheet(THEME.id))
    return THEME


def _status_style(status_key: str) -> tuple[str, str]:
    # Solid status dot shares the badge text color (online / offline / unknown).
    if status_key == "online":
        return "● %s" % i18n.t("online"), "color:%s; background:%s;" % (
            THEME.online,
            THEME.online_bg,
        )
    if status_key == "offline":
        return "● %s" % i18n.t("offline"), "color:%s; background:%s;" % (
            THEME.offline,
            THEME.offline_bg,
        )
    return "● %s" % i18n.t("unknown"), "color:%s; background:%s;" % (
        THEME.muted,
        THEME.unknown_bg,
    )


class DeviceCard(QFrame):
    """Interactive device tile for the device grid."""

    selected = Signal(str)
    activated = Signal(str)
    term_activated = Signal(str)
    context_menu = Signal(str, object)
    hover_changed = Signal(bool)

    def __init__(self, device: Device, status_key: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.device_id = device.id
        self.setObjectName("deviceCard")
        self.setCursor(PointingHandCursor)
        self.setMinimumWidth(180)
        self.setMaximumWidth(360)
        self.setProperty("selected", False)
        self.setAttribute(WA_Hover, True)
        self.setContextMenuPolicy(CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)

        top = QHBoxLayout()
        self.lbl_status = QLabel()
        self.lbl_status.setObjectName("cardStatus")
        self.lbl_os = QLabel()
        self.lbl_os.setObjectName("cardOs")
        top.addWidget(self.lbl_status, 0)
        top.addWidget(self.lbl_os, 0)
        top.addStretch(1)

        self.lbl_name = QLabel()
        self.lbl_name.setObjectName("cardName")
        self.lbl_name.setWordWrap(True)
        self.lbl_host = QLabel()
        self.lbl_host.setObjectName("cardHost")
        self.lbl_notes = QLabel()
        self.lbl_notes.setObjectName("cardMeta")
        self.lbl_notes.setWordWrap(True)

        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        bottom.addStretch(1)
        self.btn_term = QPushButton()
        self.btn_term.setCursor(PointingHandCursor)
        self.btn_term.setFocusPolicy(NoFocus)
        self.btn_term.clicked.connect(lambda: self.term_activated.emit(self.device_id))
        bottom.addWidget(self.btn_term)
        self.btn_connect = QPushButton()
        self.btn_connect.setObjectName("primary")
        self.btn_connect.setCursor(PointingHandCursor)
        self.btn_connect.setFocusPolicy(NoFocus)
        self.btn_connect.clicked.connect(lambda: self.activated.emit(self.device_id))
        bottom.addWidget(self.btn_connect)

        root.addLayout(top)
        root.addWidget(self.lbl_name)
        root.addWidget(self.lbl_host)
        root.addWidget(self.lbl_notes)
        root.addStretch(1)
        root.addLayout(bottom)

        self.bind(device, status_key)

    def _on_context_menu(self, pos) -> None:
        self.selected.emit(self.device_id)
        self.context_menu.emit(self.device_id, self.mapToGlobal(pos))

    def event(self, event):  # noqa: N802
        etype = event.type()
        if qt_enum_eq(etype, HoverEnter):
            self.hover_changed.emit(True)
        elif qt_enum_eq(etype, HoverLeave):
            self.hover_changed.emit(False)
        return super().event(event)

    def bind(self, device: Device, status_key: str) -> None:
        status_text, status_qss = _status_style(status_key)
        self.lbl_status.setText(status_text)
        self.lbl_status.setStyleSheet(status_qss)
        os_name = (device.os_name or "").strip()
        if os_name:
            self.lbl_os.setText(os_name)
            self.lbl_os.setVisible(True)
        else:
            self.lbl_os.setText(i18n.t("os_unknown"))
            self.lbl_os.setVisible(True)
        self.lbl_name.setText(device.name)
        self.lbl_host.setText(device.host)
        notes = (device.notes or "").strip()
        self.lbl_notes.setText(notes)
        self.lbl_notes.setVisible(bool(notes))
        self.btn_term.setText(i18n.t("connect_terminal"))
        self.btn_connect.setText(i18n.t("remote_control"))

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self.activated.emit(self.device_id)
        super().mouseDoubleClickEvent(event)


class DeviceDialog(QDialog):
    def __init__(self, parent: QWidget, title: str, device: Device | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("confirmDialog")
        make_frameless_dialog(self)
        self.setWindowTitle(title)
        self.setMinimumWidth(420)
        self.result_device: Device | None = None
        self._device = device

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(DialogDragBar(self, title, "info", False))

        form_host = QWidget()
        form = QFormLayout(form_host)
        form.setContentsMargins(20, 16, 20, 16)
        form.setSpacing(10)
        self.name = QLineEdit(device.name if device else "")
        self.host = QLineEdit(device.host if device else "")
        self.password = QLineEdit(device.password if device else "")
        self.password.setEchoMode(Password)
        self.password.setObjectName("confirmInput")
        pwd_wrap = QWidget()
        pwd_l = QVBoxLayout(pwd_wrap)
        pwd_l.setContentsMargins(0, 0, 0, 0)
        pwd_l.setSpacing(6)
        pwd_l.addWidget(self.password)
        show_row = QHBoxLayout()
        show_row.setContentsMargins(0, 0, 0, 0)
        show_row.setSpacing(8)
        show_row.addStretch(1)
        self.lbl_show_pwd = QLabel(i18n.t("show_code"))
        self.lbl_show_pwd.setObjectName("confirmCheck")
        self.lbl_show_pwd.setCursor(PointingHandCursor)
        self.chk_show_pwd = ToggleSwitch()
        self.chk_show_pwd.toggled.connect(self._on_show_password_toggled)
        self.lbl_show_pwd.mousePressEvent = (  # type: ignore[method-assign]
            lambda event: self.chk_show_pwd.toggle()
        )
        show_row.addWidget(self.lbl_show_pwd, 0)
        show_row.addWidget(self.chk_show_pwd, 0)
        pwd_l.addLayout(show_row)
        self.notes = QLineEdit(device.notes if device else "")
        form.addRow(i18n.t("field_name"), self.name)
        form.addRow(i18n.t("field_host"), self.host)
        form.addRow(i18n.t("field_password"), pwd_wrap)
        form.addRow(i18n.t("field_notes"), self.notes)

        buttons = make_dialog_button_box(Save, Cancel)
        buttons.button(Save).setText(i18n.t("save"))
        buttons.button(Cancel).setText(i18n.t("cancel"))
        buttons.button(Save).setObjectName("primary")
        buttons.accepted.connect(self._ok)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        root.addWidget(form_host)

    def _on_show_password_toggled(self, _checked: bool = False) -> None:
        if self.chk_show_pwd.isChecked():
            self.password.setEchoMode(Normal)
            self.lbl_show_pwd.setText(i18n.t("hide_code"))
        else:
            self.password.setEchoMode(Password)
            self.lbl_show_pwd.setText(i18n.t("show_code"))

    def _ok(self) -> None:
        host = self.host.text().strip()
        if not host:
            show_warning(self, title=i18n.t("tip"), message=i18n.t("fill_host"))
            return
        name = self.name.text().strip() or host
        if self._device:
            self.result_device = Device(
                id=self._device.id,
                name=name,
                host=host,
                port=DEFAULT_PORT,
                password=self.password.text(),
                notes=self.notes.text().strip(),
                os_name=self._device.os_name,
                last_connected=self._device.last_connected,
                created_at=self._device.created_at,
            )
        else:
            self.result_device = Device.create(
                name=name,
                host=host,
                password=self.password.text(),
                notes=self.notes.text().strip(),
            )
        self.accept()


class SettingsDialog(QDialog):
    def __init__(self, parent: QWidget, store: DeviceStore) -> None:
        super().__init__(parent)
        self.store = store
        self.setObjectName("confirmDialog")
        make_frameless_dialog(self)
        self.setWindowTitle(i18n.t("settings_title"))
        self.setMinimumWidth(420)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(DialogDragBar(self, i18n.t("settings_title"), "info", False))

        form_host = QWidget()
        form = QFormLayout(form_host)
        form.setContentsMargins(20, 16, 20, 16)
        form.setSpacing(10)

        self.lang = QComboBox()
        self.lang.setCursor(PointingHandCursor)
        self.lang.setMaxVisibleItems(8)
        self.lang.addItem(i18n.t("lang_zh"), "zh_CN")
        self.lang.addItem(i18n.t("lang_en"), "en_US")
        idx = self.lang.findData(store.settings.language)
        self.lang.setCurrentIndex(max(0, idx))

        self.theme = QComboBox()
        self.theme.setCursor(PointingHandCursor)
        self.theme.setMaxVisibleItems(12)
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

        self.chk_launch_at_login = ToggleSwitch()
        self.chk_launch_at_login.setChecked(bool(store.settings.launch_at_login))
        self.chk_start_minimized = ToggleSwitch()
        self.chk_start_minimized.setChecked(bool(store.settings.start_minimized))
        if supports_autostart():
            form.addRow(i18n.t("launch_at_login"), self._settings_toggle_row(self.chk_launch_at_login))
            form.addRow(i18n.t("start_minimized"), self._settings_toggle_row(self.chk_start_minimized))
            autostart_hint = QLabel(i18n.t("launch_at_login_hint"))
        else:
            self.chk_launch_at_login.setEnabled(False)
            self.chk_start_minimized.setEnabled(False)
            autostart_hint = QLabel(i18n.t("autostart_unsupported"))
        autostart_hint.setObjectName("pageMuted")
        autostart_hint.setWordWrap(True)
        form.addRow(autostart_hint)
        minimized_hint = QLabel(i18n.t("start_minimized_hint"))
        minimized_hint.setObjectName("pageMuted")
        minimized_hint.setWordWrap(True)
        form.addRow(minimized_hint)

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
        root.addWidget(form_host)

    @staticmethod
    def _settings_toggle_row(toggle: ToggleSwitch) -> QWidget:
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addStretch(1)
        lay.addWidget(toggle, 0, make_alignment(AlignRight, AlignVCenter))
        return row

    def _apply_hd(self) -> None:
        self.fps.setText("30")
        self.quality.setText("95")
        self.scale.setText("1.0")

    def _save(self) -> None:
        try:
            self.store.settings.max_fps = float(self.fps.text())
            self.store.settings.jpeg_quality = int(self.quality.text())
            self.store.settings.scale = float(self.scale.text())
            self.store.settings.auto_probe_s = max(3.0, float(self.probe.text()))
            self.store.settings.language = str(self.lang.currentData())
            self.store.settings.theme = str(self.theme.currentData() or DEFAULT_THEME)
            self.store.settings.settings_version = 3
            launch_at_login = self.chk_launch_at_login.isChecked()
            start_minimized = self.chk_start_minimized.isChecked()
        except ValueError:
            show_warning(self, title=i18n.t("tip"), message=i18n.t("invalid_number"))
            return
        if supports_autostart():
            try:
                apply_autostart(launch_at_login, start_minimized=start_minimized)
            except OSError as exc:
                show_warning(
                    self,
                    title=i18n.t("tip"),
                    message=i18n.t("autostart_failed", error=str(exc)),
                )
                return
        self.store.settings.launch_at_login = launch_at_login
        self.store.settings.start_minimized = start_minimized
        self.store.save()
        self.accept()


class MainWindow(QMainWindow):
    probe_done = Signal(dict)
    host_crashed = Signal()
    host_clip_wakeup = Signal()
    host_file_wakeup = Signal()
    file_status = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.store = DeviceStore()
        i18n.set_lang(self.store.settings.language)
        self._status: dict[str, str] = {}
        self._host: RemoteHost | None = None
        self._host_thread: threading.Thread | None = None
        self._probe_stop = threading.Event()
        self._viewer_shell: ViewerShell | None = None
        self._terminals: list[DirectTerminalWindow] = []
        self._host_clip: ClipboardBridge | None = None
        self._host_clip_timer: QTimer | None = None
        self._host_files: FileAssembler | None = None
        self._host_file_timer: QTimer | None = None
        self._file_sending = False
        self._file_send_stop = threading.Event()
        self._selected_device_id: str | None = None
        self._device_cards: dict[str, DeviceCard] = {}
        self._card_hover_count = 0
        self._tray: AppTray | None = None
        self._quitting = False

        self.probe_done.connect(self._apply_probe)
        self.host_crashed.connect(self._on_host_crashed)
        self.host_clip_wakeup.connect(self._drain_host_clipboard_in)
        self.host_file_wakeup.connect(self._drain_host_file_in)
        self.file_status.connect(self._set_status)

        self._build()
        apply_app_icon(self)
        self.retranslate()
        self._refresh_local()
        self._reload_devices()
        self._start_probe_loop()
        i18n.on_change(self.retranslate)
        # Start hosting after the first UI paint; user can still stop/start manually.
        QTimer.singleShot(0, self._auto_start_host)
        QTimer.singleShot(0, self._setup_tray)

    def apply_startup_visibility(self, *, minimized: bool) -> None:
        """Hide to tray after startup when --minimized or setting enabled."""
        if not minimized:
            return

        def _finish() -> None:
            if self._tray is not None and self._tray.is_visible():
                self.hide()
            else:
                self.showNormal()

        QTimer.singleShot(150, _finish)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        # winId() is valid after the native window exists.
        apply_window_chrome(self, THEME)
        # Clamp once the native screen is known (multi-monitor / DPI-safe).
        if not getattr(self, "_geometry_fitted", False):
            self._geometry_fitted = True
            avail_w, avail_h = _available_screen_size(self)
            if self.width() > avail_w - 24 or self.height() > avail_h - 24:
                self._apply_window_geometry()

    def _apply_window_geometry(self) -> None:
        """Fixed main-window size for the current screen."""
        avail_w, avail_h = _available_screen_size(self)
        max_w = max(560, avail_w - 24)
        max_h = max(360, avail_h - 24)

        target_w = min(1120, max_w)
        target_h = min(620, max_h)
        if avail_w < 1100 or avail_h < 700:
            target_w = max_w
            target_h = max_h
        self.setFixedSize(int(target_w), int(target_h))

    def _build(self) -> None:
        make_frameless_dialog(self, modal=False, as_window=True)
        self.setObjectName("mainWindow")
        self._drag_filter = _WindowDragFilter(self)
        self._apply_window_geometry()

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
        side.setMinimumWidth(220)
        side.setMaximumWidth(360)
        side_l = QVBoxLayout(side)
        side_l.setContentsMargins(0, 0, 0, 0)
        side_l.setSpacing(0)

        # Upper info can scroll; action buttons stay pinned at the bottom.
        side_scroll = QScrollArea()
        side_scroll.setObjectName("sideScroll")
        side_scroll.setWidgetResizable(True)
        side_scroll.setFrameShape(getattr(getattr(QFrame, "Shape", QFrame), "NoFrame", 0))
        side_top = QWidget()
        side_top.setObjectName("sideTop")
        top_l = QVBoxLayout(side_top)
        top_l.setContentsMargins(22, 24, 22, 12)
        top_l.setSpacing(10)

        self.lbl_brand = QLabel()
        self.lbl_brand.setObjectName("brand")
        self.lbl_brand_tag = QLabel()
        self.lbl_brand_tag.setObjectName("brandTag")
        # Frameless: drag the window from brand / titles.
        self.lbl_brand.installEventFilter(self._drag_filter)
        self.lbl_brand_tag.installEventFilter(self._drag_filter)

        self.lbl_side_title = QLabel()
        self.lbl_side_title.setObjectName("sectionTitle")
        self.lbl_side_hint = QLabel()
        self.lbl_side_hint.setObjectName("sideMuted")
        self.lbl_side_hint.setWordWrap(True)
        self.lbl_side_title.installEventFilter(self._drag_filter)

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
        self.chk_show = ToggleSwitch(compact=True)
        self.chk_show.toggled.connect(self._on_show_code_toggled)
        # Clicking the text also toggles the switch.
        self.lbl_show_code.mousePressEvent = (  # type: ignore[method-assign]
            lambda event: self.chk_show.toggle()
        )
        self.lbl_verify = QLabel()
        self.lbl_verify.setObjectName("passValue")

        verify_head = QHBoxLayout()
        verify_head.setSpacing(6)
        verify_head.addWidget(self.lbl_verify_title, 1)
        verify_head.addWidget(self.lbl_show_code, 0)
        verify_head.addWidget(self.chk_show, 0)

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
        card_l.addWidget(self.lbl_ips_title)
        card_l.addWidget(self.lbl_ips)

        top_l.addWidget(self.lbl_brand)
        top_l.addWidget(self.lbl_brand_tag)
        top_l.addSpacing(14)
        top_l.addWidget(self.lbl_side_title)
        top_l.addWidget(self.lbl_side_hint)
        top_l.addWidget(card)
        top_l.addStretch(1)
        side_scroll.setWidget(side_top)

        actions = QFrame()
        actions.setObjectName("sideActions")
        act_l = QVBoxLayout(actions)
        act_l.setContentsMargins(22, 12, 22, 22)
        act_l.setSpacing(10)

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
        self.lbl_host_state.setWordWrap(True)

        act_l.addWidget(self.btn_host)
        act_l.addLayout(row_side_btns)
        act_l.addWidget(self.lbl_host_state)

        side_l.addWidget(side_scroll, 1)
        side_l.addWidget(actions, 0)

        main = QWidget()
        main.setObjectName("mainPanel")
        main_l = QVBoxLayout(main)
        main_l.setContentsMargins(22, 12, 12, 16)
        main_l.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(10)
        header.setContentsMargins(0, 0, 0, 0)
        vcenter = make_alignment(AlignVCenter)
        align_left = make_alignment(AlignLeft, AlignVCenter)
        align_right = make_alignment(AlignRight, AlignVCenter)

        self.lbl_list_title = QLabel()
        self.lbl_list_title.setObjectName("pageTitle")
        self.lbl_list_title.installEventFilter(self._drag_filter)
        header.addWidget(self.lbl_list_title, 1, align_left)

        search_strip = QFrame()
        search_strip.setObjectName("headerSearchStrip")
        search_l = QHBoxLayout(search_strip)
        search_l.setContentsMargins(8, 2, 8, 2)
        search_l.setSpacing(0)
        self.search = QLineEdit()
        self.search.setObjectName("deviceSearchInput")
        self.search.setMinimumWidth(220)
        self.search.setMaximumWidth(360)
        self.search.textChanged.connect(self._reload_devices)
        search_l.addWidget(self.search, 1)
        header.addWidget(search_strip, 0, vcenter)

        header_right = QWidget()
        header_right.setObjectName("headerRightChrome")
        right_l = QHBoxLayout(header_right)
        right_l.setContentsMargins(0, 0, 0, 0)
        right_l.setSpacing(4)
        right_l.addStretch(1)

        self.btn_settings = HeaderSettingsButton(self)
        self.btn_settings.clicked.connect(self._open_settings)
        right_l.addWidget(self.btn_settings, 0, vcenter)

        chrome_wrap = QWidget()
        chrome_l = QHBoxLayout(chrome_wrap)
        chrome_l.setContentsMargins(4, 0, 0, 0)
        chrome_l.setSpacing(2)

        self.btn_win_min = WindowChromeButton(
            ICON_MINIMIZE, self, object_name="windowChromeBtn", width=32, height=28
        )
        self.btn_win_min.setToolTip(i18n.t("window_minimize"))
        self.btn_win_min.clicked.connect(self.showMinimized)
        chrome_l.addWidget(self.btn_win_min, 0)

        self.btn_win_close = WindowChromeButton(
            ICON_CLOSE, self, object_name="windowCloseBtn", width=36, height=28
        )
        self.btn_win_close.setToolTip(i18n.t("close_action"))
        self.btn_win_close.clicked.connect(self.close)
        chrome_l.addWidget(self.btn_win_close, 0)
        right_l.addWidget(chrome_wrap, 0, vcenter)

        header.addWidget(header_right, 1, align_right)

        connect_block = QVBoxLayout()
        connect_block.setSpacing(6)
        self.lbl_connect_hint = QLabel()
        self.lbl_connect_hint.setObjectName("connectHint")
        self.lbl_connect_hint.setWordWrap(True)
        connect_block.addWidget(self.lbl_connect_hint)

        connect_row = QHBoxLayout()
        connect_row.setSpacing(10)
        self.connect_host = QLineEdit()
        self.connect_host.setObjectName("connectHostInput")
        self.connect_host.setMinimumWidth(108)
        self.connect_host.setMaximumWidth(168)
        self.connect_password = QLineEdit()
        self.connect_password.setObjectName("connectPasswordInput")
        self.connect_password.setEchoMode(Password)
        self.connect_password.setMinimumWidth(108)
        self.connect_password.setMaximumWidth(176)
        self.connect_password.returnPressed.connect(lambda: self._connect_from_bar("desktop"))
        self.btn_connect_password_eye = PasswordEyeButton(self.connect_password)

        self.lbl_connect_dash = QLabel("—")
        self.lbl_connect_dash.setObjectName("connectDash")
        self.lbl_connect_dash.setAlignment(AlignCenter)
        self.lbl_connect_dash.setFixedWidth(22)

        connect_strip = QFrame()
        connect_strip.setObjectName("connectInputStrip")
        strip_l = QHBoxLayout(connect_strip)
        strip_l.setContentsMargins(4, 2, 4, 2)
        strip_l.setSpacing(0)
        strip_l.addWidget(self.connect_host, 0)
        strip_l.addWidget(self.lbl_connect_dash, 0)
        strip_l.addWidget(self.connect_password, 0)
        strip_l.addWidget(self.btn_connect_password_eye, 0)

        self.btn_connect = QPushButton()
        self.btn_connect.setObjectName("headerActionPrimary")
        self.btn_connect.setCursor(PointingHandCursor)
        self.btn_connect.setFocusPolicy(NoFocus)
        self.btn_connect.setFlat(True)
        self.btn_connect.clicked.connect(lambda: self._connect_from_bar("desktop"))
        connect_row.addWidget(connect_strip, 0)
        connect_row.addWidget(self.btn_connect, 0)
        connect_row.addStretch(1)
        connect_block.addLayout(connect_row)

        list_card = QFrame()
        list_card.setObjectName("mainCard")
        list_l = QVBoxLayout(list_card)
        list_l.setContentsMargins(12, 12, 12, 12)
        list_l.setSpacing(10)

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

        self.empty_host = QWidget()
        self.empty_host.setObjectName("deviceEmptyHost")
        empty_l = QVBoxLayout(self.empty_host)
        empty_l.setContentsMargins(24, 24, 24, 24)
        empty_l.setSpacing(0)
        self.lbl_device_empty = QLabel()
        self.lbl_device_empty.setObjectName("cardEmpty")
        self.lbl_device_empty.setAlignment(AlignCenter)
        self.lbl_device_empty.setWordWrap(True)
        empty_l.addStretch(1)
        empty_l.addWidget(self.lbl_device_empty, 0)
        empty_l.addStretch(1)
        self.empty_host.hide()

        list_l.addWidget(self.device_scroll, 1)
        list_l.addWidget(self.empty_host, 1)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        footer.setSpacing(12)
        self.status = QLabel()
        self.status.setObjectName("statusBar")
        self.lbl_card_hint = QLabel()
        self.lbl_card_hint.setObjectName("cardHint")
        self.lbl_card_hint.setWordWrap(False)
        # Keep the footer height stable: never show/hide this label.
        self._sync_footer_height()
        footer.addWidget(self.status, 1)
        footer.addWidget(self.lbl_card_hint, 0)

        main_l.addLayout(header)
        main_l.addLayout(connect_block)
        main_l.addWidget(list_card, 1)
        main_l.addLayout(footer)

        splitter.addWidget(side)
        splitter.addWidget(main)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([320, 800])

        self._card_selection_filter = _DeviceCardSelectionFilter(self)
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self._card_selection_filter)
            app.installEventFilter(self._drag_filter)

        bind_frameless_shell(self, resizable=False, rounded=True, radius=16)

    def _setup_tray(self) -> None:
        """Windows tray / Ubuntu top-panel StatusNotifier icon."""
        if self._tray is not None:
            return
        if not AppTray.available():
            log.info("system tray unavailable; close button will quit the app")
            return
        try:
            self._tray = AppTray(self, on_quit=self._quit_from_tray)
        except Exception as exc:
            log.warning("failed to create tray icon: %s", exc)
            self._tray = None
            return
        app = QApplication.instance()
        if app is not None:
            app.setQuitOnLastWindowClosed(False)

    def retranslate(self) -> None:
        self.setWindowTitle(i18n.t("app_title"))
        min_btn = getattr(self, "btn_win_min", None)
        if min_btn is not None:
            min_btn.setToolTip(i18n.t("window_minimize"))
        close_btn = getattr(self, "btn_win_close", None)
        if close_btn is not None:
            close_btn.setToolTip(i18n.t("close_action"))
        if self._tray is not None:
            self._tray.retranslate()
        self.lbl_brand.setText(i18n.t("brand"))
        self.lbl_brand_tag.setText(i18n.t("brand_tag"))
        self.lbl_side_title.setText(i18n.t("local_control"))
        self.lbl_side_hint.setText(i18n.t("local_control_hint"))
        self.lbl_code_hint.setText(i18n.t("device_code"))
        self.lbl_verify_title.setText(i18n.t("verify_code"))
        self._sync_show_code_label()
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
            self.lbl_host_state.setText(i18n.t("host_on", port=DEFAULT_PORT))
            self._restyle(self.lbl_host_state, "hostOk")
        self.lbl_list_title.setText(i18n.t("device_list"))
        self.btn_settings.setToolTip(i18n.t("settings"))
        self.lbl_connect_hint.setText(i18n.t("connect_bar_hint"))
        self.connect_host.setPlaceholderText(i18n.t("connect_host_ph"))
        self.connect_password.setPlaceholderText(i18n.t("connect_password_ph"))
        self.btn_connect.setText(i18n.t("connect_action"))
        self.btn_connect.setToolTip(i18n.t("connect_bar_hint"))
        eye = getattr(self, "btn_connect_password_eye", None)
        if eye is not None and hasattr(eye, "retranslate"):
            eye.retranslate()
        self.search.setPlaceholderText(i18n.t("search_ph"))
        self._refresh_local()
        self._reload_devices()
        if not self.status.text():
            self.status.setText(i18n.t("ready"))
        self._sync_footer_height()
        self._update_card_hint()

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
        ips = list_local_ipv4()
        self.lbl_ips.setText("\n".join(ips))
        self._sync_show_code_label()

    def _filtered_devices(self) -> list[Device]:
        keyword = self.search.text().strip().lower()
        rows: list[Device] = []
        for device in self.store.devices:
            hay = "%s %s %s %s" % (device.name, device.host, device.notes, device.os_name)
            if keyword and keyword not in hay.lower():
                continue
            rows.append(device)
        return rows

    def _sync_footer_height(self) -> None:
        """Reserve a constant footer band so hover hints don't resize the list."""
        tip = i18n.t("device_list_sub")
        metrics = self.lbl_card_hint.fontMetrics()
        height = max(metrics.height(), metrics.boundingRect(tip).height()) + 4
        self.status.setFixedHeight(height)
        self.lbl_card_hint.setFixedHeight(height)

    def _update_card_hint(self) -> None:
        if self._card_hover_count > 0:
            self.lbl_card_hint.setText(i18n.t("device_list_sub"))
        else:
            self.lbl_card_hint.clear()

    def _clear_device_grid(self) -> None:
        while self.device_grid.count():
            item = self.device_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._device_cards.clear()
        self._card_hover_count = 0
        self._update_card_hint()

    def _reload_devices(self) -> None:
        rows = self._filtered_devices()
        selected = self._selected_device_id
        if selected and selected not in {d.id for d in rows}:
            selected = None
            self._selected_device_id = None

        self._clear_device_grid()

        if not rows:
            self.device_scroll.hide()
            self.empty_host.show()
            if self.search.text().strip():
                self.lbl_device_empty.setText(i18n.t("device_empty_search"))
            else:
                self.lbl_device_empty.setText(i18n.t("device_empty"))
            return

        self.empty_host.hide()
        self.device_scroll.show()

        cols = self._device_columns()
        self._laid_cols = cols
        for index, device in enumerate(rows):
            status_key = self._status.get(device.id, "unknown")
            card = DeviceCard(device, status_key, self.device_grid_host)
            card.selected.connect(self._on_card_selected)
            card.activated.connect(self._on_card_activated)
            card.term_activated.connect(self._on_card_term_activated)
            card.context_menu.connect(self._on_card_context_menu)
            card.hover_changed.connect(self._on_card_hover_changed)
            card.set_selected(device.id == selected)
            self._device_cards[device.id] = card
            self.device_grid.addWidget(card, index // cols, index % cols)

        # Keep cards left-aligned in the last row.
        self.device_grid.setRowStretch((len(rows) + cols - 1) // cols, 1)
        self.device_grid.setColumnStretch(cols, 1)

    def _device_columns(self) -> int:
        width = max(1, self.device_scroll.viewport().width())
        return max(1, min(3, width // 200))

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if not getattr(self, "_device_cards", None):
            return
        cols = self._device_columns()
        if cols != getattr(self, "_laid_cols", None):
            self._reload_devices()

    def _on_card_hover_changed(self, hovering: bool) -> None:
        if hovering:
            self._card_hover_count += 1
        else:
            self._card_hover_count = max(0, self._card_hover_count - 1)
        self._update_card_hint()

    def _widget_is_device_card(self, widget: QWidget) -> bool:
        w: QWidget | None = widget
        while w is not None:
            if isinstance(w, DeviceCard):
                return True
            if w is self:
                break
            w = w.parentWidget()
        return False

    def _clear_card_selection(self) -> None:
        if self._selected_device_id is None and not any(
            c.property("selected") for c in self._device_cards.values()
        ):
            return
        self._selected_device_id = None
        for card in self._device_cards.values():
            card.set_selected(False)

    def _on_card_selected(self, device_id: str) -> None:
        self._selected_device_id = device_id
        for did, card in self._device_cards.items():
            card.set_selected(did == device_id)

    def _on_card_activated(self, device_id: str) -> None:
        self._selected_device_id = device_id
        device = self.store.get(device_id)
        if device is None:
            return
        self._launch_client(device.host, DEFAULT_PORT, device.password, device.name, device.id)

    def _on_card_term_activated(self, device_id: str) -> None:
        self._selected_device_id = device_id
        device = self.store.get(device_id)
        if device is None:
            return
        self._launch_terminal(device.host, DEFAULT_PORT, device.password, device.name, device.id)

    def _on_card_context_menu(self, device_id: str, global_pos) -> None:
        self._on_card_selected(device_id)
        menu = QMenu(self)
        act_desktop = QAction(i18n.t("remote_control"), menu)
        act_term = QAction(i18n.t("connect_terminal"), menu)
        act_edit = QAction(i18n.t("edit"), menu)
        act_delete = QAction(i18n.t("delete"), menu)
        menu.addAction(act_desktop)
        menu.addAction(act_term)
        menu.addSeparator()
        menu.addAction(act_edit)
        menu.addAction(act_delete)
        chosen = menu_exec(menu, global_pos)
        if chosen is act_desktop:
            self._on_card_activated(device_id)
        elif chosen is act_term:
            self._on_card_term_activated(device_id)
        elif chosen is act_edit:
            self._edit_device(device_id)
        elif chosen is act_delete:
            self._delete_device(device_id)

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

    def _edit_device(self, device_id: str | None = None) -> None:
        device = self.store.get(device_id) if device_id else self._selected_device()
        if not device:
            show_info(self, title=i18n.t("tip"), message=i18n.t("select_device"))
            return
        dialog = DeviceDialog(self, i18n.t("edit_title"), device)
        if qt_enum_eq(dialog_exec(dialog), DialogAccepted) and dialog.result_device:
            self.store.upsert(dialog.result_device)
            self._selected_device_id = dialog.result_device.id
            self._reload_devices()
            self._set_status(i18n.t("updated", name=dialog.result_device.name))

    def _delete_device(self, device_id: str | None = None) -> None:
        device = self.store.get(device_id) if device_id else self._selected_device()
        if not device:
            show_info(self, title=i18n.t("tip"), message=i18n.t("select_device"))
            return
        if not ask_confirm(
            self,
            title=i18n.t("delete_title"),
            message=i18n.t("delete_confirm", name=device.name),
            eyebrow=i18n.t("confirm"),
            ok_text=i18n.t("delete"),
            cancel_text=i18n.t("cancel"),
            danger=True,
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
        apply_window_chrome(self, THEME)
        if self._viewer_shell is not None:
            try:
                apply_window_chrome(self._viewer_shell, THEME)
            except RuntimeError:
                pass
        for term in list(self._terminals):
            try:
                apply_window_chrome(term, THEME)
            except RuntimeError:
                pass
        self._set_status(i18n.t("settings_saved"))

    def _regen_password(self) -> None:
        if self._host is not None:
            show_warning(self, title=i18n.t("tip"), message=i18n.t("stop_before_regen"))
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

    def _auto_start_host(self) -> None:
        if self._host is not None:
            return
        self._start_host()

    def _start_host(self) -> None:
        password = self.store.settings.host_password.strip()
        if not password:
            show_warning(self, title=i18n.t("tip"), message=i18n.t("empty_password"))
            return
        self.store.settings.host_port = DEFAULT_PORT
        self.store.save()

        stream = StreamConfig(
            max_fps=self.store.settings.max_fps,
            jpeg_quality=self.store.settings.jpeg_quality,
            scale=self.store.settings.scale,
        ).clamp()
        net = NetConfig(host=self.store.settings.host_bind, port=DEFAULT_PORT, password=password)
        host = RemoteHost(HostConfig(net=net, stream=stream, bind_require_password=True))
        # Wake GUI immediately when clipboard / file packets arrive.
        host.clipboard_notify = lambda: self.host_clip_wakeup.emit()
        host.file_notify = lambda: self.host_file_wakeup.emit()
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
        self._start_host_files()
        self.btn_host.setText(i18n.t("stop_host"))
        self._restyle(self.btn_host, "danger")
        self.lbl_host_state.setText(i18n.t("host_on", port=DEFAULT_PORT))
        self._restyle(self.lbl_host_state, "hostOk")
        self._set_status(i18n.t("host_started", port=DEFAULT_PORT))

    def _enqueue_host_clipboard(self, packet: bytes) -> None:
        host = self._host
        if host is None or not host.session_live.is_set():
            return
        try:
            host.clipboard_out.put_nowait(packet)
        except queue.Full:
            log.warning("host clipboard_out full")

    def _enqueue_host_file(self, packet: bytes) -> None:
        host = self._host
        if host is None or not host.session_live.is_set():
            raise ConnectionError("no remote session")
        # Blocking put so large transfers don't drop mid-file.
        host.file_out.put(packet, timeout=60.0)

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

    def _start_host_files(self) -> None:
        self._stop_host_files()
        self._file_send_stop.clear()
        self._host_files = FileAssembler(
            on_progress=lambda name, done, total: self.file_status.emit(
                i18n.t(
                    "file_receiving",
                    name=name,
                    pct=(100 if total <= 0 else min(100, int(done * 100 / total))),
                )
            ),
            on_complete=lambda path: self.file_status.emit(
                i18n.t("file_saved_to", path=str(path))
            ),
            on_error=lambda err: self.file_status.emit(
                i18n.t("file_transfer_failed", error=err)
            ),
        )
        self._host_file_timer = QTimer(self)
        self._host_file_timer.setInterval(100)
        self._host_file_timer.timeout.connect(self._on_host_file_tick)
        self._host_file_timer.start()

    def _on_host_file_tick(self) -> None:
        self._drain_host_file_in()

    def _drain_host_file_in(self) -> None:
        host = self._host
        assembler = self._host_files
        if host is None or assembler is None:
            return
        while True:
            try:
                payload = host.file_in.get_nowait()
            except queue.Empty:
                break
            try:
                meta, _blob = unpack_file_message(payload)
            except Exception:
                log.exception("bad host file payload")
                continue
            op = str(meta.get("op") or "chunk")
            if op == "list":
                self._handle_remote_list_request(meta)
            elif op == "download":
                self._handle_remote_download_request(meta)
            elif op == "chunk":
                assembler.handle_payload(payload)
            else:
                # Ignore control replies that shouldn't arrive on the host.
                log.debug("ignore file op on host: %s", op)

    def _handle_remote_list_request(self, meta: dict) -> None:
        path = str(meta.get("path") or "")

        def worker() -> None:
            try:
                resolved, entries = list_directory(path)
                packet = pack_list_result(resolved, entries)
            except Exception as exc:
                log.warning("remote list failed path=%s: %s", path, exc)
                packet = pack_list_result(path, error=str(exc))
            try:
                self._enqueue_host_file(packet)
            except Exception as exc:
                log.warning("cannot reply list result: %s", exc)

        # Don't block the Qt UI thread on large folders / slow volumes.
        threading.Thread(target=worker, name="host-remote-list", daemon=True).start()

    def _handle_remote_download_request(self, meta: dict) -> None:
        from ..features.file_transfer import resolve_browse_path

        path = str(meta.get("path") or "")
        if self._file_sending:
            try:
                self._enqueue_host_file(
                    pack_download_error(path, i18n.t("file_transfer_busy"))
                )
            except Exception:
                pass
            return
        src = resolve_browse_path(path)
        if not src.is_file():
            try:
                self._enqueue_host_file(
                    pack_download_error(path, "not a file: %s" % path)
                )
            except Exception:
                pass
            return
        if file_size_over_limit(src.stat().st_size):
            try:
                self._enqueue_host_file(
                    pack_download_error(path, i18n.t("file_too_large", name=src.name))
                )
            except Exception:
                pass
            return

        self._file_sending = True
        self._file_send_stop.clear()
        self._set_status(i18n.t("file_sending", name=src.name, pct=0))

        def worker() -> None:
            try:
                send_file(
                    src,
                    self._enqueue_host_file,
                    on_progress=lambda name, done, total: self.file_status.emit(
                        i18n.t(
                            "file_sending",
                            name=name,
                            pct=(100 if total <= 0 else min(100, int(done * 100 / total))),
                        )
                    ),
                    should_stop=lambda: self._file_send_stop.is_set(),
                )
                self.file_status.emit(i18n.t("file_sent", name=src.name))
            except InterruptedError:
                self.file_status.emit(i18n.t("file_transfer_failed", error="cancelled"))
            except Exception as exc:
                log.exception("remote download failed")
                try:
                    self._enqueue_host_file(pack_download_error(path, str(exc)))
                except Exception:
                    pass
                self.file_status.emit(i18n.t("file_transfer_failed", error=str(exc)))
            finally:
                self._file_sending = False

        threading.Thread(target=worker, name="host-remote-download", daemon=True).start()

    def _stop_host_files(self) -> None:
        self._file_send_stop.set()
        self._file_sending = False
        if self._host_file_timer is not None:
            self._host_file_timer.stop()
            self._host_file_timer.deleteLater()
            self._host_file_timer = None
        if self._host_files is not None:
            self._host_files.clear()
            self._host_files = None

    def _stop_host(self) -> None:
        self._stop_host_clipboard()
        self._stop_host_files()
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
        self._stop_host_files()
        self._host = None
        self.btn_host.setText(i18n.t("start_host"))
        self._restyle(self.btn_host, "primary")
        self.lbl_host_state.setText(i18n.t("host_crashed"))
        self._restyle(self.lbl_host_state, "hostDanger")
        show_error(self, title=i18n.t("error"), message=i18n.t("host_crash_msg"))

    def _find_device_by_host(self, host: str, port: int) -> Device | None:
        host_key = host.strip().lower()
        port_key = int(port)
        for device in self.store.devices:
            if device.host.strip().lower() == host_key and int(device.port) == port_key:
                return device
        return None

    def _apply_peer_ack(
        self,
        device_id: str | None,
        host: str,
        ack: dict,
        page: RemoteClientPage | None = None,
        terminal: DirectTerminalWindow | None = None,
    ) -> None:
        if not device_id:
            return
        device = self.store.get(device_id)
        if device is None:
            return
        username = str(ack.get("username") or "").strip()
        os_name = str(ack.get("os") or "").strip()
        host_key = host.strip().lower()
        changed = False
        if username and (
            device.name.strip().lower() == host_key
            or device.name.strip() == device.host.strip()
        ):
            device.name = username
            changed = True
        if os_name and os_name != device.os_name:
            device.os_name = os_name
            changed = True
        if changed:
            self.store.upsert(device)
            self._reload_devices()
        display_name = (device.name or "").strip() or (device.host or "").strip()
        if page is not None and display_name:
            page.set_display_name(display_name)
        if terminal is not None and display_name:
            terminal.set_display_name(display_name)

    def _device_display_name(self, device_id: str | None, fallback: str = "") -> str:
        if device_id:
            device = self.store.get(device_id)
            if device is not None:
                name = (device.name or "").strip()
                if name:
                    return name
                host = (device.host or "").strip()
                if host:
                    return host
        return (fallback or "").strip()

    def _connect_from_bar(self, mode: str = "desktop") -> None:
        host = self.connect_host.text().strip()
        if not host:
            show_warning(self, title=i18n.t("tip"), message=i18n.t("fill_host"))
            return
        password = self.connect_password.text()
        existing = self._find_device_by_host(host, DEFAULT_PORT)
        if existing is not None:
            existing.password = password
            self.store.upsert(existing)
            device_id = existing.id
            display_title = existing.name
        else:
            device = Device.create(name=host, host=host, password=password)
            self.store.upsert(device)
            device_id = device.id
            display_title = host
        self._reload_devices()
        if mode == "terminal":
            self._launch_terminal(host, DEFAULT_PORT, password, display_title, device_id)
        else:
            self._launch_client(host, DEFAULT_PORT, password, display_title, device_id)


    def _ensure_viewer_shell(self) -> ViewerShell:
        shell = self._viewer_shell
        if shell is not None:
            try:
                # Touch a Qt property to detect deleted C++ wrappers.
                _ = shell.isVisible()
                return shell
            except RuntimeError:
                self._viewer_shell = None

        shell = ViewerShell(
            parent=None,
            on_add_remote=self._bring_main_to_front,
        )
        shell.setAttribute(WA_DeleteOnClose, True)

        def _drop(*_: object) -> None:
            if self._viewer_shell is shell:
                self._viewer_shell = None

        shell.destroyed.connect(_drop)
        self._viewer_shell = shell
        shell.show()
        apply_window_chrome(shell, THEME)
        return shell

    def _bring_main_to_front(self) -> None:
        try:
            if self.isMinimized():
                self.showNormal()
            self.show()
            self.raise_()
            self.activateWindow()
            app = QApplication.instance()
            if app is not None:
                app.setActiveWindow(self)
        except RuntimeError:
            return

    def _find_viewer(
        self,
        host: str,
        port: int,
        device_id: str | None,
    ) -> RemoteClientPage | None:
        shell = self._viewer_shell
        if shell is None:
            return None
        try:
            return shell.find_page(host, port, device_id)
        except RuntimeError:
            self._viewer_shell = None
            return None

    def _focus_viewer(self, page: RemoteClientPage, title: str) -> None:
        shell = self._viewer_shell
        if shell is None:
            return
        try:
            shell.focus_page(page)
            app = QApplication.instance()
            if app is not None:
                app.setActiveWindow(shell)
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
        title = self._device_display_name(device_id, title)
        existing = self._find_viewer(host, port, device_id)
        if existing is not None:
            existing.set_display_name(title)
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
        shell = self._ensure_viewer_shell()
        try:
            page = shell.add_session(cfg, device_id=device_id)
            page.session_ack.connect(
                lambda ack, did=device_id, h=host, p=page: self._apply_peer_ack(did, h, ack, p)
            )
            shell.focus_page(page)
        except RuntimeError:
            self._viewer_shell = None
            return
        if device_id:
            self.store.touch_connected(device_id)
            self._reload_devices()
        self._set_status(i18n.t("connecting", title=title, host=host, port=port))

    def _find_terminal(
        self,
        host: str,
        port: int,
        device_id: str | None,
    ) -> DirectTerminalWindow | None:
        host_key = host.strip().lower()
        port_key = int(port)
        for win in list(self._terminals):
            try:
                win_host = str(win.net.host).strip().lower()
                win_port = int(win.net.port)
                win_id = getattr(win, "device_id", None)
            except RuntimeError:
                if win in self._terminals:
                    self._terminals.remove(win)
                continue
            if device_id and win_id and win_id == device_id:
                return win
            if win_host == host_key and win_port == port_key:
                return win
        return None

    def _focus_terminal(self, win: DirectTerminalWindow, title: str) -> None:
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
        self._set_status(i18n.t("terminal_focus_existing", title=title))

    def _launch_terminal(
        self,
        host: str,
        port: int,
        password: str,
        title: str,
        device_id: str | None,
    ) -> None:
        title = self._device_display_name(device_id, title)
        existing = self._find_terminal(host, port, device_id)
        if existing is not None:
            existing.set_display_name(title)
            self._focus_terminal(existing, title)
            if device_id:
                self.store.touch_connected(device_id)
                self._reload_devices()
            return

        net = NetConfig(host=host, port=port, password=password)
        try:
            # Child of main window, modeless — does not block the home UI.
            win = DirectTerminalWindow(net=net, title=title, parent=self, reconnect=True)
        except Exception as exc:
            log.exception("open terminal window failed")
            show_error(
                self,
                title=i18n.t("error"),
                message=i18n.t("terminal_failed", error=str(exc)),
            )
            return
        win.device_id = device_id
        win.setAttribute(WA_DeleteOnClose, True)
        win.session_ack.connect(
            lambda ack, did=device_id, h=host, w=win: self._apply_peer_ack(
                did, h, ack, terminal=w
            )
        )
        self._terminals.append(win)

        def _drop(*_: object, window: DirectTerminalWindow = win) -> None:
            if window in self._terminals:
                self._terminals.remove(window)

        win.destroyed.connect(_drop)
        win.show()
        apply_window_chrome(win, THEME)
        win.start()
        if device_id:
            self.store.touch_connected(device_id)
            self._reload_devices()
        self._set_status(i18n.t("terminal_connecting_host", title=title, host=host, port=port))

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
        os_changed = False
        for device in list(self.store.devices):
            online, os_name = probe_device(device.host, device.port)
            results[device.id] = "online" if online else "offline"
            if os_name and os_name != device.os_name:
                device.os_name = os_name
                os_changed = True
        if os_changed:
            self.store.save()
        self.probe_done.emit(results)

    def _apply_probe(self, results: dict) -> None:
        self._status.update(results)
        self._reload_devices()
        online_n = sum(1 for v in results.values() if v == "online")
        self._set_status(i18n.t("status_updated", online=online_n, total=len(results)))

    def _quit_from_tray(self) -> None:
        self._quitting = True
        self.close()

    def _shutdown_app(self) -> None:
        self._probe_stop.set()
        self._stop_host_clipboard()
        if self._host is not None:
            self._stop_host()
        shell = self._viewer_shell
        if shell is not None:
            try:
                shell.force_close = True
                shell.close()
            except RuntimeError:
                pass
            self._viewer_shell = None
        for win in list(self._terminals):
            try:
                win.force_close()
            except RuntimeError:
                pass
        if self._tray is not None:
            self._tray.hide()

    def closeEvent(self, event) -> None:  # noqa: N802
        # With a tray icon, the window close button only hides to tray/panel.
        if (
            not self._quitting
            and self._tray is not None
            and self._tray.is_visible()
        ):
            event.ignore()
            self.hide()
            self._tray.notify_hidden()
            return

        if not ask_confirm(
            self,
            title=i18n.t("close_main_title"),
            message=i18n.t("close_main_confirm"),
            eyebrow=i18n.t("brand"),
            ok_text=i18n.t("close_action"),
            cancel_text=i18n.t("keep_open"),
            danger=True,
        ):
            self._quitting = False
            event.ignore()
            return

        self._shutdown_app()
        super().closeEvent(event)
        app = QApplication.instance()
        if app is not None:
            app.quit()


def run_app(*, minimized: bool = False) -> None:
    ensure_utf8_stdio()
    ensure_windows_app_id()
    app = QApplication.instance() or QApplication([])
    apply_app_font(app, point_size=10)
    app.setStyle("Fusion")
    app.setAttribute(AA_DontShowIconsInMenus, False)
    apply_app_icon(app)
    bootstrap = DeviceStore()
    from ..features.autostart import sync_settings

    sync_settings(
        launch_at_login=bootstrap.settings.launch_at_login,
        start_minimized=bootstrap.settings.start_minimized,
    )
    i18n.set_lang(bootstrap.settings.language)
    apply_theme(app, bootstrap.settings.theme)
    win = MainWindow()
    start_hidden = bool(minimized or bootstrap.settings.start_minimized)
    if start_hidden:
        win.apply_startup_visibility(minimized=True)
    win.show()
    apply_window_chrome(win, THEME)
    QTimer.singleShot(200, win._probe_now)
    (getattr(app, "exec_", None) or app.exec)()
