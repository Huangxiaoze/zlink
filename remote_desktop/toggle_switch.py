"""Shared pill toggle used by host rail and themed dialogs."""

from __future__ import annotations

from .qt_bind import (
    Antialiasing,
    NoFocus,
    NoPen,
    PointingHandCursor,
    QAbstractButton,
    QColor,
    QWidget,
    widget_painter,
)
from .themes import CURRENT


class ToggleSwitch(QAbstractButton):
    """Compact accent pill switch."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(PointingHandCursor)
        self.setFocusPolicy(NoFocus)
        self.setFixedSize(46, 26)

    def paintEvent(self, _event) -> None:  # noqa: N802
        with widget_painter(self) as painter:
            painter.setRenderHint(Antialiasing, True)
            checked = self.isChecked()
            # Prefer content-panel border for off-track so it reads on light dialogs
            # and still contrasts on the dark side rail.
            track = QColor(CURRENT.accent if checked else CURRENT.line)
            thumb = QColor("#FFFFFF")
            if not self.isEnabled():
                track = QColor(CURRENT.line)
                thumb = QColor("#C8D0D6")

            painter.setPen(NoPen)
            painter.setBrush(track)
            painter.drawRoundedRect(0, 0, self.width(), self.height(), 13, 13)

            margin = 3
            diameter = self.height() - margin * 2
            x = self.width() - margin - diameter if checked else margin
            painter.setBrush(thumb)
            painter.drawEllipse(x, margin, diameter, diameter)
