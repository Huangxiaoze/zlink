"""Themed dialogs shared by main window and remote viewer (no native QMessageBox)."""

from __future__ import annotations

from typing import Optional, Tuple

from .i18n import i18n
from .qt_bind import (
    DialogAccepted,
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
    dialog_exec,
    qt_enum_eq,
)


def _polish(*widgets: QWidget) -> None:
    for widget in widgets:
        style = widget.style()
        style.unpolish(widget)
        style.polish(widget)
        widget.update()


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
        self.setAttribute(WA_StyledBackground, True)
        self.setModal(True)
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

        accent = QFrame()
        accent.setObjectName("confirmAccent")
        accent.setAttribute(WA_StyledBackground, True)
        accent.setProperty("kind", kind)
        accent.setProperty("danger", "true" if danger else "false")
        root.addWidget(accent)

        body = QWidget()
        body_l = QVBoxLayout(body)
        body_l.setContentsMargins(24, 20, 24, 16)
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
        _polish(accent, btn_ok)

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
        self.setAttribute(WA_StyledBackground, True)
        self.setModal(True)
        self.setWindowTitle(i18n.t("quick_connect"))
        self.setMinimumWidth(420)
        self.setMaximumWidth(520)
        self.host = ""
        self.password = ""
        self.save = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        accent = QFrame()
        accent.setObjectName("confirmAccent")
        accent.setAttribute(WA_StyledBackground, True)
        accent.setProperty("kind", "info")
        accent.setProperty("danger", "false")
        root.addWidget(accent)

        body = QWidget()
        body_l = QVBoxLayout(body)
        body_l.setContentsMargins(24, 20, 24, 16)
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

        self.chk_save = QCheckBox(i18n.t("quick_save"))
        self.chk_save.setObjectName("confirmCheck")
        self.chk_save.setChecked(True)
        self.chk_save.setCursor(PointingHandCursor)
        body_l.addWidget(self.chk_save)
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

        btn_ok = QPushButton(i18n.t("remote_control"))
        btn_ok.setObjectName("confirmOk")
        btn_ok.setProperty("danger", "false")
        btn_ok.setCursor(PointingHandCursor)
        btn_ok.setFocusPolicy(NoFocus)
        btn_ok.clicked.connect(self._ok)
        btn_ok.setDefault(True)
        foot.addWidget(btn_ok)
        root.addWidget(footer)

        _polish(accent, btn_ok)
        self.edit_host.setFocus()

    def _ok(self) -> None:
        host = self.edit_host.text().strip()
        if not host:
            show_warning(self, title=i18n.t("tip"), message=i18n.t("fill_host"))
            return
        self.host = host
        self.password = self.edit_password.text()
        self.save = bool(self.chk_save.isChecked())
        self.accept()


def ask_quick_connect(
    parent: Optional[QWidget],
) -> Optional[Tuple[str, str, bool]]:
    """Return (host, password, save) or None if cancelled."""
    dialog = QuickConnectDialog(parent)
    if not qt_enum_eq(dialog_exec(dialog), DialogAccepted):
        return None
    return dialog.host, dialog.password, dialog.save
