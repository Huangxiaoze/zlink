from __future__ import annotations

import logging
import threading
import time
from typing import Callable

import mss

from ..core.codec import EncodedFrame, encode_bgra
from ..core.config import StreamConfig

log = logging.getLogger(__name__)


class ScreenCapturer:
    """Capture + encode loop. Keeps only the latest encoded frame."""

    def __init__(self, stream: StreamConfig) -> None:
        self.stream = stream
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._latest: EncodedFrame | None = None
        self._seq = 0
        self.src_width = 0
        self.src_height = 0
        self.on_stats: Callable[[dict], None] | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="capture", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def pop_latest(self) -> EncodedFrame | None:
        with self._lock:
            frame = self._latest
            self._latest = None
            return frame

    def update_stream(self, stream: StreamConfig) -> None:
        self.stream = stream.clamp()

    def _run(self) -> None:
        interval = 1.0 / max(1.0, self.stream.max_fps)
        try:
            mss_cls = getattr(mss, "MSS", None) or mss.mss
            with mss_cls() as sct:
                monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                self.src_width = int(monitor["width"])
                self.src_height = int(monitor["height"])
                log.info("capture monitor %sx%s", self.src_width, self.src_height)

                while not self._stop.is_set():
                    t0 = time.perf_counter()
                    stream = self.stream
                    interval = 1.0 / max(1.0, stream.max_fps)
                    shot = sct.grab(monitor)
                    encoded = encode_bgra(
                        shot.bgra,
                        shot.width,
                        shot.height,
                        scale=stream.scale,
                        quality=stream.jpeg_quality,
                    )
                    with self._lock:
                        self._seq += 1
                        # Attach sequence via width/height already; seq tracked externally by host
                        self._latest = encoded
                    if self.on_stats:
                        self.on_stats(
                            {
                                "encode_ms": (time.perf_counter() - t0) * 1000.0,
                                "bytes": len(encoded.jpeg),
                            }
                        )
                    elapsed = time.perf_counter() - t0
                    delay = interval - elapsed
                    if delay > 0:
                        self._stop.wait(delay)
        except Exception:
            log.exception("capture loop failed")
            self._stop.set()

    @property
    def sequence(self) -> int:
        return self._seq
