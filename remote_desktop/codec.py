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
        # LANCZOS keeps text/UI edges sharper when downscaling.
        resampling = getattr(Image, "Resampling", Image)
        resample = getattr(resampling, "LANCZOS", getattr(Image, "LANCZOS", Image.BICUBIC))
        image = image.resize((dst_w, dst_h), resample)
    else:
        dst_w, dst_h = src_width, src_height

    buf = io.BytesIO()
    # subsampling=0 => 4:4:4, much clearer for text than default 4:2:0.
    # qtables keep defaults; high quality + 4:4:4 is the LAN sharpness path.
    image.save(
        buf,
        format="JPEG",
        quality=int(quality),
        optimize=False,
        progressive=False,
        subsampling=0,
    )
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
