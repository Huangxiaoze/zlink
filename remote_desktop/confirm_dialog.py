"""Themed dialogs shared by main window and remote viewer (no native QMessageBox)."""

from __future__ import annotations

from typing import Optional, Tuple

from .i18n import i18n
from .qt_bind import (
    DialogAccepted,
    DialogWindow,
    FramelessWindowHint,
    LeftButton,
    NoFocus,
    Password,
    PointingHandCursor,
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
    WA_StyledBackground,
    WindowTypeFlag,
    dialog_exec,
    make_window_flags,
    qt_enum_eq,
)
from .toggle_switch import ToggleSwitch


def _polish(*widgets: QWidget) -> None:
    for widget in widgets:
        style = widget.style()
        style.unpolish(widget)
        style.polish(widget)
        widget.update()


def _global_pos(event):
    if hasattr(event, "globalPosition"):
        return event.globalPosition().toPoint()
    return event.globalPos()


def _make_frameless(
    dialog: QDialog,
    modal: bool = True,
    *,
    as_window: bool = False,
) -> None:
    """Drop the native Windows title bar; use in-dialog chrome instead.

    ``as_window=True`` uses Qt.Window so minimize/maximize work (needed for
    long-lived tool windows like the remote terminal).
    """
    # PySide2 needs Qt.WindowFlags(...), not enum|enum or a plain int.
    base = WindowTypeFlag if as_window else DialogWindow
    dialog.setWindowFlags(make_window_flags(base, FramelessWindowHint))
    dialog.setAttribute(WA_StyledBackground, True)
    dialog.setModal(bool(modal))


class _DragBar(QFrame):
    """Caption strip that can drag a frameless dialog."""

    def __init__(
        self,
        host: QDialog,
        title: str,
        kind: str = "info",
        danger: bool = False,
        *,
        window_controls: bool = False,
    ) -> None:
        super().__init__(host)
        self._host = host
        self._drag_offset = None
        self._window_controls = bool(window_controls)
        self.setObjectName("dialogTitleBar")
        self.setAttribute(WA_StyledBackground, True)
        # Keep kind/danger for callers; accent stripe was removed as visual noise.
        self.setProperty("kind", kind)
        self.setProperty("danger", "true" if danger else "false")

        row = QHBoxLayout(self)
        row.setContentsMargins(16, 10, 10, 8)
        row.setSpacing(4)
        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("dialogCaption")
        row.addWidget(self.lbl_title, 1)

        self.btn_min: QPushButton | None = None
        self.btn_max: QPushButton | None = None
        if self._window_controls:
            self.btn_min = QPushButton("–")
            self.btn_min.setObjectName("dialogClose")
            self.btn_min.setToolTip(i18n.t("window_minimize"))
            self.btn_min.setCursor(PointingHandCursor)
            self.btn_min.setFocusPolicy(NoFocus)
            self.btn_min.setFixedSize(32, 28)
            self.btn_min.clicked.connect(host.showMinimized)
            row.addWidget(self.btn_min, 0)

            self.btn_max = QPushButton("□")
            self.btn_max.setObjectName("dialogClose")
            self.btn_max.setToolTip(i18n.t("window_maximize"))
            self.btn_max.setCursor(PointingHandCursor)
            self.btn_max.setFocusPolicy(NoFocus)
            self.btn_max.setFixedSize(32, 28)
            self.btn_max.clicked.connect(self._toggle_max)
            row.addWidget(self.btn_max, 0)

        btn_close = QPushButton("×")
        btn_close.setObjectName("dialogClose")
        btn_close.setToolTip(i18n.t("close_action"))
        btn_close.setCursor(PointingHandCursor)
        btn_close.setFocusPolicy(NoFocus)
        btn_close.setFixedSize(32, 28)
        btn_close.clicked.connect(host.reject)
        row.addWidget(btn_close, 0)
        self._sync_max_btn()

    def _toggle_max(self) -> None:
        if self._host.isMaximized():
            self._host.showNormal()
        else:
            self._host.showMaximized()
        self._sync_max_btn()

    def _sync_max_btn(self) -> None:
        if self.btn_max is None:
            return
        if self._host.isMaximized():
            self.btn_max.setText("❐")
            self.btn_max.setToolTip(i18n.t("window_restore"))
        else:
            self.btn_max.setText("□")
            self.btn_max.setToolTip(i18n.t("window_maximize"))

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if qt_enum_eq(event.button(), LeftButton) and not self._host.isMaximized():
            self._drag_offset = _global_pos(event) - self._host.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        pressed = False
        try:
            pressed = bool(event.buttons() & LeftButton)
        except TypeError:
            pressed = self._drag_offset is not None
        if self._drag_offset is not None and pressed and not self._host.isMaximized():
            self._host.move(_global_pos(event) - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if self._window_controls and qt_enum_eq(event.button(), LeftButton):
            self._toggle_max()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class ThemedDialog(QDialog):
    """Shared chrome for alerts, confirms, and simple prompts."""

    def __init__(
        self,
        parent: Optional[QWidget],
        *,
        title: str,
        message: str = "",
        eyebrow: str = "",
        kind: str = "info",
        ok_text: str = "",
        cancel_text: str = "",
        show_cancel: bool = True,
        danger: bool | None = None,
        input_label: str = "",
        input_text: str = "",
        password: bool = False,
        checkbox_text: str = "",
        checkbox_checked: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("confirmDialog")
        _make_frameless(self)
        self.setWindowTitle(title)
        self.setMinimumWidth(420)
        self.setMaximumWidth(520)

        if danger is None:
            danger = kind == "danger"
        if danger and kind == "info":
            kind = "danger"

        self._input: QLineEdit | None = None
        self._checkbox: QCheckBox | None = None
        self.result_text = ""
        self.result_checked = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(_DragBar(self, title, kind, danger))

        body = QWidget()
        body_l = QVBoxLayout(body)
        body_l.setContentsMargins(24, 16, 24, 16)
        body_l.setSpacing(10)

        if eyebrow:
            lbl_eye = QLabel(eyebrow)
            lbl_eye.setObjectName("confirmEyebrow")
            body_l.addWidget(lbl_eye)

        lbl_title = QLabel(title)
        lbl_title.setObjectName("confirmTitle")
        lbl_title.setWordWrap(True)
        body_l.addWidget(lbl_title)

        if message:
            lbl_msg = QLabel(message)
            lbl_msg.setObjectName("confirmMessage")
            lbl_msg.setWordWrap(True)
            body_l.addWidget(lbl_msg)

        if input_label or input_text or password:
            if input_label:
                lbl_in = QLabel(input_label)
                lbl_in.setObjectName("confirmMessage")
                body_l.addWidget(lbl_in)
            self._input = QLineEdit(input_text)
            self._input.setObjectName("confirmInput")
            if password:
                self._input.setEchoMode(Password)
            body_l.addWidget(self._input)

        if checkbox_text:
            self._checkbox = QCheckBox(checkbox_text)
            self._checkbox.setObjectName("confirmCheck")
            self._checkbox.setChecked(checkbox_checked)
            self._checkbox.setCursor(PointingHandCursor)
            body_l.addWidget(self._checkbox)

        root.addWidget(body)

        footer = QFrame()
        footer.setObjectName("confirmFooter")
        footer.setAttribute(WA_StyledBackground, True)
        foot = QHBoxLayout(footer)
        foot.setContentsMargins(24, 14, 24, 18)
        foot.setSpacing(10)
        foot.addStretch(1)

        if show_cancel:
            btn_cancel = QPushButton(cancel_text or i18n.t("cancel"))
            btn_cancel.setObjectName("confirmCancel")
            btn_cancel.setCursor(PointingHandCursor)
            btn_cancel.setFocusPolicy(NoFocus)
            btn_cancel.clicked.connect(self.reject)
            foot.addWidget(btn_cancel)

        btn_ok = QPushButton(ok_text or i18n.t("ok"))
        btn_ok.setObjectName("confirmOk")
        btn_ok.setProperty("danger", "true" if danger else "false")
        btn_ok.setCursor(PointingHandCursor)
        btn_ok.setFocusPolicy(NoFocus)
        btn_ok.clicked.connect(self._accept)
        btn_ok.setDefault(True)
        foot.addWidget(btn_ok)

        root.addWidget(footer)
        _polish(btn_ok)

        if self._input is not None:
            self._input.setFocus()

    def _accept(self) -> None:
        if self._input is not None:
            self.result_text = self._input.text()
        if self._checkbox is not None:
            self.result_checked = bool(self._checkbox.isChecked())
        self.accept()


# Backward-compatible alias used by older call sites / imports.
ConfirmDialog = ThemedDialog


def show_alert(
    parent: Optional[QWidget],
    *,
    title: str,
    message: str,
    eyebrow: str = "",
    ok_text: str = "",
    kind: str = "info",
) -> None:
    dialog = ThemedDialog(
        parent,
        title=title,
        message=message,
        eyebrow=eyebrow,
        kind=kind,
        ok_text=ok_text or i18n.t("ok"),
        show_cancel=False,
        danger=(kind == "danger"),
    )
    dialog_exec(dialog)


def show_info(
    parent: Optional[QWidget],
    *,
    title: str,
    message: str,
    eyebrow: str = "",
    ok_text: str = "",
) -> None:
    show_alert(parent, title=title, message=message, eyebrow=eyebrow, ok_text=ok_text, kind="info")


def show_warning(
    parent: Optional[QWidget],
    *,
    title: str,
    message: str,
    eyebrow: str = "",
    ok_text: str = "",
) -> None:
    show_alert(parent, title=title, message=message, eyebrow=eyebrow, ok_text=ok_text, kind="warn")


def show_error(
    parent: Optional[QWidget],
    *,
    title: str,
    message: str,
    eyebrow: str = "",
    ok_text: str = "",
) -> None:
    show_alert(parent, title=title, message=message, eyebrow=eyebrow, ok_text=ok_text, kind="danger")


def ask_confirm(
    parent: Optional[QWidget],
    *,
    title: str,
    message: str,
    eyebrow: str = "",
    ok_text: str = "",
    cancel_text: str = "",
    danger: bool = True,
) -> bool:
    dialog = ThemedDialog(
        parent,
        title=title,
        message=message,
        eyebrow=eyebrow,
        kind="danger" if danger else "info",
        ok_text=ok_text or i18n.t("ok"),
        cancel_text=cancel_text or i18n.t("cancel"),
        show_cancel=True,
        danger=danger,
    )
    return qt_enum_eq(dialog_exec(dialog), DialogAccepted)


def ask_text(
    parent: Optional[QWidget],
    *,
    title: str,
    label: str = "",
    message: str = "",
    eyebrow: str = "",
    text: str = "",
    password: bool = False,
    ok_text: str = "",
    cancel_text: str = "",
) -> Tuple[Optional[str], bool]:
    dialog = ThemedDialog(
        parent,
        title=title,
        message=message,
        eyebrow=eyebrow,
        kind="info",
        ok_text=ok_text or i18n.t("ok"),
        cancel_text=cancel_text or i18n.t("cancel"),
        show_cancel=True,
        danger=False,
        input_label=label,
        input_text=text,
        password=password,
    )
    if not qt_enum_eq(dialog_exec(dialog), DialogAccepted):
        return None, False
    return dialog.result_text, True


class QuickConnectDialog(QDialog):
    """Single themed form: host + password + optional save."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("confirmDialog")
        _make_frameless(self)
        self.setWindowTitle(i18n.t("quick_connect"))
        self.setMinimumWidth(420)
        self.setMaximumWidth(560)
        self.host = ""
        self.password = ""
        self.save = False
        self.mode = "desktop"

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(_DragBar(self, i18n.t("quick_connect"), "info", False))

        body = QWidget()
        body_l = QVBoxLayout(body)
        body_l.setContentsMargins(24, 16, 24, 16)
        body_l.setSpacing(10)

        lbl_eye = QLabel(i18n.t("tip"))
        lbl_eye.setObjectName("confirmEyebrow")
        body_l.addWidget(lbl_eye)

        lbl_title = QLabel(i18n.t("quick_connect"))
        lbl_title.setObjectName("confirmTitle")
        body_l.addWidget(lbl_title)

        lbl_msg = QLabel(i18n.t("quick_connect_hint"))
        lbl_msg.setObjectName("confirmMessage")
        lbl_msg.setWordWrap(True)
        body_l.addWidget(lbl_msg)

        lbl_host = QLabel(i18n.t("quick_host"))
        lbl_host.setObjectName("confirmMessage")
        body_l.addWidget(lbl_host)
        self.edit_host = QLineEdit()
        self.edit_host.setObjectName("confirmInput")
        body_l.addWidget(self.edit_host)

        lbl_pwd = QLabel(i18n.t("quick_password"))
        lbl_pwd.setObjectName("confirmMessage")
        body_l.addWidget(lbl_pwd)
        self.edit_password = QLineEdit()
        self.edit_password.setObjectName("confirmInput")
        self.edit_password.setEchoMode(Password)
        body_l.addWidget(self.edit_password)

        save_row = QHBoxLayout()
        save_row.setSpacing(10)
        self.lbl_save = QLabel(i18n.t("quick_save"))
        self.lbl_save.setObjectName("confirmCheck")
        self.lbl_save.setCursor(PointingHandCursor)
        self.chk_save = ToggleSwitch()
        self.chk_save.setChecked(True)
        self.lbl_save.mousePressEvent = (  # type: ignore[method-assign]
            lambda event: self.chk_save.toggle()
        )
        save_row.addWidget(self.lbl_save, 1)
        save_row.addWidget(self.chk_save, 0)
        body_l.addLayout(save_row)
        root.addWidget(body)

        footer = QFrame()
        footer.setObjectName("confirmFooter")
        footer.setAttribute(WA_StyledBackground, True)
        foot = QHBoxLayout(footer)
        foot.setContentsMargins(24, 14, 24, 18)
        foot.setSpacing(10)
        foot.addStretch(1)

        btn_cancel = QPushButton(i18n.t("cancel"))
        btn_cancel.setObjectName("confirmCancel")
        btn_cancel.setCursor(PointingHandCursor)
        btn_cancel.setFocusPolicy(NoFocus)
        btn_cancel.clicked.connect(self.reject)
        foot.addWidget(btn_cancel)

        btn_term = QPushButton(i18n.t("connect_terminal"))
        btn_term.setObjectName("confirmCancel")
        btn_term.setCursor(PointingHandCursor)
        btn_term.setFocusPolicy(NoFocus)
        btn_term.clicked.connect(lambda: self._ok("terminal"))
        foot.addWidget(btn_term)

        btn_ok = QPushButton(i18n.t("remote_control"))
        btn_ok.setObjectName("confirmOk")
        btn_ok.setProperty("danger", "false")
        btn_ok.setCursor(PointingHandCursor)
        btn_ok.setFocusPolicy(NoFocus)
        btn_ok.clicked.connect(lambda: self._ok("desktop"))
        btn_ok.setDefault(True)
        foot.addWidget(btn_ok)
        root.addWidget(footer)

        _polish(btn_ok)
        self.edit_host.setFocus()

    def _ok(self, mode: str = "desktop") -> None:
        host = self.edit_host.text().strip()
        if not host:
            show_warning(self, title=i18n.t("tip"), message=i18n.t("fill_host"))
            return
        self.host = host
        self.password = self.edit_password.text()
        self.save = bool(self.chk_save.isChecked())
        self.mode = mode
        self.accept()


def ask_quick_connect(
    parent: Optional[QWidget],
) -> Optional[Tuple[str, str, bool, str]]:
    """Return (host, password, save, mode) or None if cancelled. mode: desktop|terminal."""
    dialog = QuickConnectDialog(parent)
    if not qt_enum_eq(dialog_exec(dialog), DialogAccepted):
        return None
    return dialog.host, dialog.password, dialog.save, dialog.mode


# Public aliases for other form dialogs (settings / device editor).
make_frameless_dialog = _make_frameless
DialogDragBar = _DragBar
