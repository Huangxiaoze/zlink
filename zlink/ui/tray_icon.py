"""System tray / status-notifier icon (Windows tray, Ubuntu top panel)."""

from __future__ import annotations

import logging
from typing import Callable

from .app_icon import load_app_icon
from .i18n import i18n
from .qt_bind import (
    QAction,
    QMainWindow,
    QMenu,
    QSystemTrayIcon,
    TrayDoubleClick,
    TrayMessageInformation,
    TrayTrigger,
    qt_enum_eq,
)

log = logging.getLogger(__name__)


class AppTray:
    """Keep the app reachable from the desktop tray / indicator area."""

    def __init__(
        self,
        window: QMainWindow,
        on_quit: Callable[[], None],
    ) -> None:
        self._window = window
        self._on_quit = on_quit
        self._hint_shown = False

        icon = load_app_icon()
        self._tray = QSystemTrayIcon(icon, window)
        self._menu = QMenu(window)
        self._act_show = QAction(i18n.t("tray_show"), self._menu)
        self._act_quit = QAction(i18n.t("tray_quit"), self._menu)
        self._act_show.triggered.connect(self.show_window)
        self._act_quit.triggered.connect(self._on_quit)
        self._menu.addAction(self._act_show)
        self._menu.addSeparator()
        self._menu.addAction(self._act_quit)
        self._tray.setContextMenu(self._menu)
        self._tray.activated.connect(self._on_activated)
        self.retranslate()
        self._tray.show()

    @staticmethod
    def available() -> bool:
        try:
            return bool(QSystemTrayIcon.isSystemTrayAvailable())
        except Exception:
            return False

    def is_visible(self) -> bool:
        try:
            return bool(self._tray.isVisible())
        except RuntimeError:
            return False

    def retranslate(self) -> None:
        self._act_show.setText(i18n.t("tray_show"))
        self._act_quit.setText(i18n.t("tray_quit"))
        self._tray.setToolTip(i18n.t("tray_tooltip"))

    def show_window(self) -> None:
        win = self._window
        try:
            win.showNormal()
            win.show()
            win.raise_()
            win.activateWindow()
        except RuntimeError:
            return
        try:
            from .qt_bind import QApplication

            app = QApplication.instance()
            if app is not None:
                app.setActiveWindow(win)
        except Exception:
            pass

    def notify_hidden(self) -> None:
        if self._hint_shown:
            return
        self._hint_shown = True
        try:
            if not self._tray.supportsMessages():
                return
            self._tray.showMessage(
                i18n.t("tray_hidden_title"),
                i18n.t("tray_hidden_msg"),
                TrayMessageInformation,
                3500,
            )
        except Exception as exc:
            log.debug("tray balloon failed: %s", exc)

    def hide(self) -> None:
        try:
            self._tray.hide()
        except RuntimeError:
            pass

    def _on_activated(self, reason) -> None:
        if qt_enum_eq(reason, TrayTrigger) or qt_enum_eq(reason, TrayDoubleClick):
            self.show_window()
