"""Host-side local vs remote pointer arbitration and cursor telemetry."""

from __future__ import annotations

import threading
import time


class PointerAuthority:
    """Tracks who moves the host cursor and the latest normalized position."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_remote_ts = 0.0
        self._host_active = False
        self._norm_x = 0.5
        self._norm_y = 0.5
        # Ignore pynput move events right after remote inject (injection also moves cursor).
        self._remote_grace_s = 0.08

    def note_remote_inject(self) -> None:
        with self._lock:
            self._last_remote_ts = time.monotonic()
            self._host_active = False

    def note_local_move(self, abs_x: int, abs_y: int, screen_w: int, screen_h: int) -> None:
        w = max(1, int(screen_w))
        h = max(1, int(screen_h))
        nx = max(0.0, min(1.0, float(abs_x) / max(1, w - 1)))
        ny = max(0.0, min(1.0, float(abs_y) / max(1, h - 1)))
        with self._lock:
            self._norm_x = nx
            self._norm_y = ny
            if time.monotonic() - self._last_remote_ts > self._remote_grace_s:
                self._host_active = True

    def snapshot(self) -> tuple[float, float, bool]:
        with self._lock:
            return self._norm_x, self._norm_y, self._host_active
