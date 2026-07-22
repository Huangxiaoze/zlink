"""Themed confirmation dialog shared by main window and remote viewer."""

from __future__ import annotations

from typing import Optional

from .i18n import i18n
from .qt_bind import (
    DialogAccepted,
    NoFocus,
    PointingHandCursor,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
    WA_StyledBackground,
    dialog_exec,
    qt_enum_eq,
)


class ConfirmDialog(QDialog):
    def __init__(
        self,
        parent: Optional[QWidget],
        *,
        title: str,
        message: str,
        eyebrow: str = "",
        ok_text: str = "",
        cancel_text: str = "",
        danger: bool = True,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("confirmDialog")
        self.setAttribute(WA_StyledBackground, True)
        self.setModal(True)
        self.setWindowTitle(title)
        self.setMinimumWidth(420)
        self.setMaximumWidth(520)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        accent = QFrame()
        accent.setObjectName("confirmAccent")
        accent.setAttribute(WA_StyledBackground, True)
        # QSS attribute selectors match string values more reliably cross Qt versions.
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

        lbl_msg = QLabel(message)
        lbl_msg.setObjectName("confirmMessage")
        lbl_msg.setWordWrap(True)
        body_l.addWidget(lbl_msg)
        root.addWidget(body)

        footer = QFrame()
        footer.setObjectName("confirmFooter")
        footer.setAttribute(WA_StyledBackground, True)
        foot = QHBoxLayout(footer)
        foot.setContentsMargins(24, 14, 24, 18)
        foot.setSpacing(10)
        foot.addStretch(1)

        btn_cancel = QPushButton(cancel_text or i18n.t("keep_open"))
        btn_cancel.setObjectName("confirmCancel")
        btn_cancel.setCursor(PointingHandCursor)
        btn_cancel.setFocusPolicy(NoFocus)
        btn_cancel.clicked.connect(self.reject)
        foot.addWidget(btn_cancel)

        btn_ok = QPushButton(ok_text or i18n.t("close_action"))
        btn_ok.setObjectName("confirmOk")
        btn_ok.setProperty("danger", "true" if danger else "false")
        btn_ok.setCursor(PointingHandCursor)
        btn_ok.setFocusPolicy(NoFocus)
        btn_ok.clicked.connect(self.accept)
        btn_ok.setDefault(True)
        foot.addWidget(btn_ok)

        root.addWidget(footer)

        # Ensure dynamic properties take effect under the active theme QSS.
        for widget in (accent, btn_ok):
            widget.style().unpolish(widget)
            widget.style().polish(widget)


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
    dialog = ConfirmDialog(
        parent,
        title=title,
        message=message,
        eyebrow=eyebrow,
        ok_text=ok_text,
        cancel_text=cancel_text,
        danger=danger,
    )
    return qt_enum_eq(dialog_exec(dialog), DialogAccepted)
