"""Controller-side remote terminal window (VT100 via pyte)."""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

from . import PROTOCOL_VERSION
from .terminal_pty import FEATURE_TERMINAL
from .config import NetConfig
from .confirm_dialog import DialogDragBar, ask_confirm, make_frameless_dialog
from .i18n import i18n
from .net import Connection, connect_to
from .protocol import MsgType, ProtocolError, decode_json, pack_term_message
from .qt_bind import (
    AlignLeft,
    AlignTop,
    ControlModifier,
    qt_has_flag,
    Key_Backspace,
    Key_Delete,
    Key_Down,
    Key_End,
    Key_Enter,
    Key_Escape,
    Key_Home,
    Key_Left,
    Key_Return,
    Key_Right,
    Key_Tab,
    Key_Up,
    QColor,
    QDialog,
    QFont,
    QFontMetrics,
    QObject,
    QPainter,
    QTimer,
    QVBoxLayout,
    QWidget,
    Signal,
    StrongFocus,
    WA_OpaquePaintEvent,
    WA_StyledBackground,
    qt_enum_eq,
    qt_enum_int,
    set_font_families,
)
from .themes import CURRENT

log = logging.getLogger(__name__)

try:
    import pyte
except ImportError:  # pragma: no cover
    pyte = None  # type: ignore


def _key_bytes(event) -> bytes:
    """Map a Qt key event to PTY input bytes (xterm-ish)."""
    key = event.key()
    text = event.text() or ""
    mods = event.modifiers()
    ctrl = qt_has_flag(mods, ControlModifier)

    mapping = (
        (Key_Return, b"\r"),
        (Key_Enter, b"\r"),
        (Key_Backspace, b"\x7f"),
        (Key_Tab, b"\t"),
        (Key_Escape, b"\x1b"),
        (Key_Delete, b"\x1b[3~"),
        (Key_Up, b"\x1b[A"),
        (Key_Down, b"\x1b[B"),
        (Key_Right, b"\x1b[C"),
        (Key_Left, b"\x1b[D"),
        (Key_Home, b"\x1b[H"),
        (Key_End, b"\x1b[F"),
    )
    for qt_key, payload in mapping:
        if qt_enum_eq(key, qt_key):
            return payload

    if ctrl and text:
        ch = text.upper()
        if len(ch) == 1 and "A" <= ch <= "Z":
            return bytes([ord(ch) - 64])
    if text:
        return text.encode("utf-8", errors="replace")
    return b""


class TerminalCanvas(QWidget):
    """Paint a pyte screen and forward keystrokes."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(StrongFocus)
        self.setAttribute(WA_OpaquePaintEvent, True)
        self.cols = 120
        self.rows = 32
        self._cell_w = 9
        self._cell_h = 18
        self._on_input: Optional[Callable[[bytes], None]] = None
        self._font = QFont()
        set_font_families(
            self._font,
            ["Cascadia Mono", "Consolas", "Menlo", "DejaVu Sans Mono", "monospace"],
        )
        self._font.setPointSize(11)
        if pyte is None:
            self.screen = None
            self.stream = None
        else:
            self.screen = pyte.HistoryScreen(self.cols, self.rows, history=2000)
            self.stream = pyte.Stream(self.screen)
        self._cursor_on = True
        self._blink = QTimer(self)
        self._blink.setInterval(530)
        self._blink.timeout.connect(self._toggle_cursor)
        self._blink.start()
        self._measure()

    def set_input_handler(self, handler: Callable[[bytes], None]) -> None:
        self._on_input = handler

    def feed(self, data: bytes) -> None:
        if not data or self.stream is None:
            return
        try:
            self.stream.feed(data.decode("utf-8", errors="replace"))
        except Exception:
            log.exception("terminal feed failed")
            return
        self.update()

    def resize_screen(self, cols: int, rows: int) -> None:
        cols = max(20, min(400, int(cols)))
        rows = max(5, min(200, int(rows)))
        if cols == self.cols and rows == self.rows:
            return
        self.cols = cols
        self.rows = rows
        if pyte is not None:
            self.screen = pyte.HistoryScreen(self.cols, self.rows, history=2000)
            self.stream = pyte.Stream(self.screen)
        self._measure()
        self.update()

    def size_hint_cells(self) -> tuple[int, int]:
        self._measure()
        w = max(20, int(self.width() / max(1, self._cell_w)))
        h = max(5, int(self.height() / max(1, self._cell_h)))
        return w, h

    def _measure(self) -> None:
        metrics = QFontMetrics(self._font)
        if hasattr(metrics, "horizontalAdvance"):
            advance = metrics.horizontalAdvance("M")
        else:
            advance = metrics.width("M")
        self._cell_w = max(6, int(advance))
        self._cell_h = max(12, int(metrics.height() + 2))

    def _toggle_cursor(self) -> None:
        self._cursor_on = not self._cursor_on
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        bg = QColor(CURRENT.side if hasattr(CURRENT, "side") else "#10181F")
        # Prefer near-black terminal chrome for contrast.
        painter.fillRect(self.rect(), QColor("#0E151C"))
        if self.screen is None:
            painter.setPen(QColor(CURRENT.text))
            painter.drawText(
                self.rect(),
                qt_enum_int(AlignLeft) | qt_enum_int(AlignTop),
                "pyte is required for terminal",
            )
            return
        painter.setFont(self._font)
        painter.setPen(QColor("#D7E2EA"))
        try:
            lines = list(self.screen.display)
        except Exception:
            lines = []
        for row, line in enumerate(lines):
            painter.drawText(0, (row + 1) * self._cell_h - 4, line)
        if self._cursor_on:
            try:
                cx = int(self.screen.cursor.x) * self._cell_w
                cy = int(self.screen.cursor.y) * self._cell_h
                painter.fillRect(
                    cx,
                    cy,
                    max(2, self._cell_w // 3),
                    self._cell_h,
                    QColor(CURRENT.accent),
                )
            except Exception:
                pass

    def keyPressEvent(self, event) -> None:  # noqa: N802
        payload = _key_bytes(event)
        if payload and self._on_input is not None:
            self._on_input(payload)
            event.accept()
            return
        super().keyPressEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._measure()


class RemoteTerminalWindow(QDialog):
    """Frameless remote shell window attached to an active viewer session."""

    def __init__(
        self,
        parent: Optional[QWidget],
        send_packet: Callable[[bytes], None],
    ) -> None:
        super().__init__(parent)
        self.setObjectName("confirmDialog")
        make_frameless_dialog(self, modal=False, as_window=True)
        self.setMinimumSize(720, 420)
        self.resize(960, 560)
        self._send_packet = send_packet
        self._opened = False
        self._closed = False
        self._allow_close = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self._drag = DialogDragBar(
            self, i18n.t("terminal_title"), "info", False, window_controls=True
        )
        root.addWidget(self._drag)

        body = QWidget()
        body_l = QVBoxLayout(body)
        body_l.setContentsMargins(12, 10, 12, 12)
        body_l.setSpacing(0)
        self.canvas = TerminalCanvas()
        self.canvas.set_input_handler(self._send_input)
        body_l.addWidget(self.canvas, 1)
        root.addWidget(body)
        self.setAttribute(WA_StyledBackground, True)
        self._set_status(i18n.t("terminal_connecting"))

        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._emit_resize)

        if pyte is None:
            self._set_status(i18n.t("terminal_need_pyte"))
        else:
            QTimer.singleShot(0, self._open_session)

    def _set_status(self, status: str) -> None:
        caption = i18n.t("terminal_caption", status=status)
        self._drag.lbl_title.setText(caption)
        self.setWindowTitle(caption)

    def handle_term_payload(self, payload: bytes) -> None:
        from .protocol import unpack_term_message

        meta, blob = unpack_term_message(payload)
        op = str(meta.get("op") or "")
        if op == "open_ok":
            self._opened = True
            self._set_status(i18n.t("terminal_ready"))
            self.canvas.setFocus()
        elif op == "open_err":
            self._opened = False
            self._set_status(
                i18n.t("terminal_failed", error=str(meta.get("error") or "open failed"))
            )
        elif op == "data":
            self.canvas.feed(blob)
        elif op == "closed":
            self._opened = False
            self._set_status(i18n.t("terminal_closed"))
            # Shell exited (e.g. user typed exit) — close window without prompt.
            QTimer.singleShot(0, self.force_close)

    def _open_session(self) -> None:
        cols, rows = self.canvas.size_hint_cells()
        self.canvas.resize_screen(cols, rows)
        try:
            self._send_packet(pack_term_message({"op": "open", "cols": cols, "rows": rows}))
        except Exception as exc:
            self._set_status(i18n.t("terminal_failed", error=str(exc)))

    def _send_input(self, data: bytes) -> None:
        if not data or self._closed:
            return
        try:
            self._send_packet(pack_term_message({"op": "data"}, data))
        except Exception as exc:
            self._set_status(i18n.t("terminal_failed", error=str(exc)))

    def _emit_resize(self) -> None:
        if not self._opened or self._closed:
            return
        cols, rows = self.canvas.size_hint_cells()
        self.canvas.resize_screen(cols, rows)
        try:
            self._send_packet(pack_term_message({"op": "resize", "cols": cols, "rows": rows}))
        except Exception:
            pass

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._resize_timer.start(180)

    def _confirm_close(self) -> bool:
        if self._allow_close or self._closed:
            return True
        return ask_confirm(
            self,
            title=i18n.t("terminal_close_title"),
            message=i18n.t("terminal_close_confirm"),
            eyebrow=i18n.t("confirm"),
            ok_text=i18n.t("close_action"),
            cancel_text=i18n.t("cancel"),
            danger=True,
        )

    def force_close(self) -> None:
        """Close without confirmation (session teardown)."""
        self._allow_close = True
        self._shutdown()
        self.close()

    def reject(self) -> None:
        if not self._confirm_close():
            return
        self._allow_close = True
        self._shutdown()
        super().reject()

    def closeEvent(self, event) -> None:  # noqa: N802
        if not self._confirm_close():
            event.ignore()
            return
        self._allow_close = True
        self._shutdown()
        super().closeEvent(event)

    def _shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._send_packet(pack_term_message({"op": "close"}))
        except Exception:
            pass


class _TermBus(QObject):
    status = Signal(str)
    term_payload = Signal(object)
    session_ended = Signal(str)
    connected = Signal()


class DirectTerminalWindow(QDialog):
    """Standalone SSH-like terminal: connects with role=terminal (no desktop)."""

    def __init__(
        self,
        net: NetConfig,
        title: str = "",
        parent: Optional[QWidget] = None,
        reconnect: bool = True,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("confirmDialog")
        # Modeless tool window: stays usable with main UI; supports min/max.
        make_frameless_dialog(self, modal=False, as_window=True)
        self.net = net
        self.reconnect = reconnect
        self.device_id: Optional[str] = None
        self._title = title or net.host
        self.setMinimumSize(720, 420)
        self.resize(960, 560)

        self._stop = threading.Event()
        self._conn: Optional[Connection] = None
        self._conn_lock = threading.Lock()
        self._opened = False
        self._shell_closed = False
        self._allow_close = False
        self._net_thread: Optional[threading.Thread] = None
        self._bus = _TermBus()
        self._bus.status.connect(self._on_status)
        self._bus.term_payload.connect(self._on_term_payload)
        self._bus.session_ended.connect(self._on_session_ended)
        self._bus.connected.connect(self._on_connected)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self._drag = DialogDragBar(
            self,
            i18n.t("terminal_direct_title", name=self._title),
            "info",
            False,
            window_controls=True,
        )
        root.addWidget(self._drag)

        body = QWidget()
        body_l = QVBoxLayout(body)
        body_l.setContentsMargins(12, 10, 12, 12)
        body_l.setSpacing(0)
        self.canvas = TerminalCanvas()
        self.canvas.set_input_handler(self._send_input)
        body_l.addWidget(self.canvas, 1)
        root.addWidget(body)
        self.setAttribute(WA_StyledBackground, True)
        self._set_status(i18n.t("viewer_connecting"))

        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._emit_resize)

    def _set_status(self, status: str) -> None:
        caption = i18n.t("terminal_direct_caption", name=self._title, status=status)
        self._drag.lbl_title.setText(caption)
        self.setWindowTitle(caption)

    def start(self) -> None:
        if self._net_thread is not None and self._net_thread.is_alive():
            return
        if pyte is None:
            self._set_status(i18n.t("terminal_need_pyte"))
            return
        self._stop.clear()
        self._net_thread = threading.Thread(
            target=self._net_loop, name="direct-term-net", daemon=True
        )
        self._net_thread.start()

    def stop(self) -> None:
        self._stop.set()
        with self._conn_lock:
            conn = self._conn
        if conn is not None:
            try:
                conn.send_json(MsgType.BYE, {"reason": "client_close"})
            except Exception:
                pass
            conn.close()

    def _confirm_close(self) -> bool:
        if self._allow_close:
            return True
        return ask_confirm(
            self,
            title=i18n.t("terminal_close_title"),
            message=i18n.t("terminal_close_confirm"),
            eyebrow=i18n.t("confirm"),
            ok_text=i18n.t("close_action"),
            cancel_text=i18n.t("cancel"),
            danger=True,
        )

    def force_close(self) -> None:
        """Close without confirmation (app/session teardown)."""
        self._allow_close = True
        self.stop()
        self.close()

    def reject(self) -> None:
        if not self._confirm_close():
            return
        self._allow_close = True
        self.stop()
        super().reject()

    def closeEvent(self, event) -> None:  # noqa: N802
        if not self._confirm_close():
            event.ignore()
            return
        self._allow_close = True
        self.stop()
        super().closeEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._resize_timer.start(180)

    def _on_status(self, text: str) -> None:
        self._set_status(text)

    def _on_session_ended(self, text: str) -> None:
        self._opened = False
        if text:
            self._set_status(text)

    def _on_connected(self) -> None:
        cols, rows = self.canvas.size_hint_cells()
        self.canvas.resize_screen(cols, rows)
        self._set_status(i18n.t("terminal_connecting"))
        try:
            self._send_raw(pack_term_message({"op": "open", "cols": cols, "rows": rows}))
        except Exception as exc:
            self._set_status(i18n.t("terminal_failed", error=str(exc)))

    def _on_term_payload(self, payload: object) -> None:
        if payload is None:
            return
        from .protocol import unpack_term_message

        try:
            meta, blob = unpack_term_message(bytes(payload))
        except Exception as exc:
            self._set_status(i18n.t("terminal_failed", error=str(exc)))
            return
        op = str(meta.get("op") or "")
        if op == "open_ok":
            self._opened = True
            self._shell_closed = False
            self._set_status(i18n.t("terminal_ready"))
            self.canvas.setFocus()
        elif op == "open_err":
            self._opened = False
            self._set_status(
                i18n.t("terminal_failed", error=str(meta.get("error") or "open failed"))
            )
        elif op == "data":
            self.canvas.feed(blob)
        elif op == "closed":
            self._opened = False
            self._shell_closed = True
            self._set_status(i18n.t("terminal_closed"))
            # Shell exited (e.g. user typed exit) — disconnect and close UI.
            self.reconnect = False
            QTimer.singleShot(0, self.force_close)

    def _send_raw(self, packet: bytes) -> None:
        with self._conn_lock:
            conn = self._conn
        if conn is None:
            raise ConnectionError("not connected")
        conn.send_raw(packet)

    def _send_input(self, data: bytes) -> None:
        if not data or not self._opened or self._shell_closed:
            return
        try:
            self._send_raw(pack_term_message({"op": "data"}, data))
        except Exception as exc:
            self._bus.status.emit(i18n.t("terminal_failed", error=str(exc)))

    def _emit_resize(self) -> None:
        if not self._opened or self._shell_closed:
            return
        cols, rows = self.canvas.size_hint_cells()
        self.canvas.resize_screen(cols, rows)
        try:
            self._send_raw(pack_term_message({"op": "resize", "cols": cols, "rows": rows}))
        except Exception:
            pass

    def _net_loop(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                self._connect_once()
                backoff = 1.0
            except Exception as exc:
                if self._stop.is_set():
                    break
                msg = str(exc) or i18n.t("viewer_disconnected")
                self._bus.session_ended.emit(msg)
            if self._stop.is_set() or not self.reconnect:
                break
            self._bus.status.emit(i18n.t("viewer_reconnecting", sec="%.0f" % backoff))
            if self._stop.wait(backoff):
                break
            backoff = min(15.0, backoff * 1.7)

    def _connect_once(self) -> None:
        self._opened = False
        self._shell_closed = False
        self._bus.status.emit(i18n.t("viewer_connecting"))
        conn = connect_to(
            self.net.host,
            self.net.port,
            self.net.connect_timeout_s,
            self.net.recv_buffer,
        )
        with self._conn_lock:
            self._conn = conn
        try:
            conn.send_json(
                MsgType.HELLO,
                {
                    "role": "terminal",
                    "version": PROTOCOL_VERSION,
                    "password": self.net.password,
                },
            )
            frame = conn.recv_frame()
            if frame.type != MsgType.HELLO_ACK:
                raise ProtocolError("expected HELLO_ACK")
            ack = decode_json(frame.payload)
            if not ack.get("ok"):
                reason = str(ack.get("reason") or "auth_failed")
                if reason == "auth_failed":
                    raise ProtocolError(i18n.t("viewer_auth_failed"))
                if reason == "busy":
                    raise ProtocolError(i18n.t("terminal_busy"))
                raise ProtocolError(reason)
            features = ack.get("features") or []
            if FEATURE_TERMINAL not in features:
                raise ProtocolError(i18n.t("terminal_unsupported"))

            session_stop = threading.Event()
            hb = threading.Thread(
                target=self._heartbeat_loop,
                args=(conn, session_stop),
                name="direct-term-hb",
                daemon=True,
            )
            hb.start()
            try:
                self._bus.connected.emit()
                while not self._stop.is_set() and not session_stop.is_set():
                    try:
                        fr = conn.recv_frame(stop_event=session_stop)
                    except ConnectionError:
                        break
                    if fr.type == MsgType.TERM:
                        self._bus.term_payload.emit(fr.payload)
                    elif fr.type == MsgType.HEARTBEAT:
                        continue
                    elif fr.type == MsgType.BYE:
                        break
            finally:
                session_stop.set()
                try:
                    if self._opened:
                        conn.send_raw(pack_term_message({"op": "close"}))
                except Exception:
                    pass
                conn.close()
                with self._conn_lock:
                    if self._conn is conn:
                        self._conn = None
                hb.join(timeout=2.0)
                if not self._stop.is_set():
                    self._bus.session_ended.emit(i18n.t("viewer_disconnected"))
        except Exception:
            conn.close()
            with self._conn_lock:
                if self._conn is conn:
                    self._conn = None
            raise

    def _heartbeat_loop(self, conn: Connection, session_stop: threading.Event) -> None:
        interval = self.net.heartbeat_interval_s
        while not self._stop.is_set() and not session_stop.is_set():
            try:
                now = time.monotonic()
                if (now - conn.last_tx) >= interval:
                    conn.send_heartbeat()
            except (ConnectionError, OSError):
                session_stop.set()
                conn.close()
                break
            session_stop.wait(0.5)
