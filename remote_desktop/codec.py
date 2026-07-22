from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image


@dataclass
class EncodedFrame:
    jpeg: bytes
    width: int
    height: int
    src_width: int
    src_height: int
    quality: int
    scale: float


def encode_bgra(
    bgra: bytes,
    src_width: int,
    src_height: int,
    *,
    scale: float,
    quality: int,
) -> EncodedFrame:
    image = Image.frombytes("RGB", (src_width, src_height), bgra, "raw", "BGRX")
    scale = max(0.1, min(1.0, scale))
    if scale < 0.999:
        dst_w = max(1, int(src_width * scale))
        dst_h = max(1, int(src_height * scale))
        # Pillow 9: Image.BILINEAR; Pillow 10+: Image.Resampling.BILINEAR
        resample = getattr(getattr(Image, "Resampling", Image), "BILINEAR", Image.BILINEAR)
        image = image.resize((dst_w, dst_h), resample)
    else:
        dst_w, dst_h = src_width, src_height

    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=int(quality), optimize=False)
    return EncodedFrame(
        jpeg=buf.getvalue(),
        width=dst_w,
        height=dst_h,
        src_width=src_width,
        src_height=src_height,
        quality=int(quality),
        scale=scale,
    )


def decode_jpeg(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data)).convert("RGB")
