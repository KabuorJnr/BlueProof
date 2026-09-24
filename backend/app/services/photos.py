"""Photograph intake: validate, fingerprint, store.

The bytes are stored exactly as received and addressed by their SHA-256, so the
hash in the ledger identifies the precise image the verifier assessed. A
perceptual hash (dHash) sits beside it to catch the same photograph re-encoded,
cropped slightly or screenshotted, which a byte hash cannot see.
"""
from __future__ import annotations

import hashlib
import io
import math
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError

from ..config import settings

_MIME = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}


@dataclass
class Photo:
    data: bytes
    sha256: str
    dhash: str
    mime: str
    width: int
    height: int


def inspect(data: bytes) -> Photo:
    if len(data) > settings.max_photo_bytes:
        raise HTTPException(413, "Photograph too large.")
    try:
        with Image.open(io.BytesIO(data)) as img:
            fmt = img.format or ""
            img.verify()
        with Image.open(io.BytesIO(data)) as img:
            width, height = img.size
            dhash = _dhash(img)
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise HTTPException(400, "That file is not a photograph BlueProof can read.") from exc
    if fmt not in _MIME:
        raise HTTPException(400, f"Unsupported image format {fmt or 'unknown'}; send JPEG, PNG or WebP.")
    if min(width, height) < 200:
        raise HTTPException(400, "Photograph too small to assess.")
    return Photo(
        data=data,
        sha256=hashlib.sha256(data).hexdigest(),
        dhash=dhash,
        mime=_MIME[fmt],
        width=width,
        height=height,
    )


def _dhash(img: Image.Image, size: int = 8) -> str:
    small = img.convert("L").resize((size + 1, size), Image.Resampling.LANCZOS)
    px = small.tobytes()
    bits = 0
    for row in range(size):
        for col in range(size):
            left = px[row * (size + 1) + col]
            right = px[row * (size + 1) + col + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return f"{bits:016x}"


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def path_for(sha256: str) -> Path:
    return Path(settings.photo_dir) / sha256[:2] / f"{sha256}.img"


def store(photo: Photo) -> str:
    path = path_for(photo.sha256)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(photo.data)
        tmp.replace(path)
    return photo.sha256


def load(sha256: str) -> bytes | None:
    path = path_for(sha256)
    return path.read_bytes() if path.exists() else None


def delete(sha256: str) -> bool:
    path = path_for(sha256)
    if path.exists():
        path.unlink()
        return True
    return False


def mime_of(data: bytes) -> str:
    try:
        with Image.open(io.BytesIO(data)) as img:
            return _MIME.get(img.format or "", "application/octet-stream")
    except (UnidentifiedImageError, OSError):
        return "application/octet-stream"


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great circle distance in metres."""
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def side_by_side(previous: bytes, current: bytes, previous_label: str, height: int = 512) -> bytes:
    """Stitch two photographs into one labelled JPEG, previous on the left.

    One image rather than two, because several vision models are only reliable
    with a single image per request.
    """
    from PIL import ImageDraw

    panels = []
    for data in (previous, current):
        with Image.open(io.BytesIO(data)) as img:
            img = img.convert("RGB")
            w = max(1, round(img.width * height / img.height))
            panels.append(img.resize((w, height), Image.Resampling.LANCZOS))
    gap, band = 12, 28
    out = Image.new("RGB", (panels[0].width + gap + panels[1].width, height + band), "white")
    out.paste(panels[0], (0, band))
    out.paste(panels[1], (panels[0].width + gap, band))
    draw = ImageDraw.Draw(out)
    draw.text((8, 7), f"LEFT: previous visit {previous_label}", fill="black")
    draw.text((panels[0].width + gap + 8, 7), "RIGHT: today", fill="black")
    buf = io.BytesIO()
    out.save(buf, format="JPEG", quality=85)
    return buf.getvalue()
