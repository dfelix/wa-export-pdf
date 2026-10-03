"""Image thumbnails: EXIF orientation, huge images, transparency, corruption."""

from __future__ import annotations

import logging
import warnings
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from ..models import Media
from .cache import MediaCache

log = logging.getLogger(__name__)

# Refuse truly absurd images (decompression bombs) but allow big photos.
Image.MAX_IMAGE_PIXELS = 400_000_000

_ROTATING_ORIENTATIONS = {5, 6, 7, 8}


def _oriented_size(im: Image.Image) -> tuple[int, int]:
    w, h = im.size
    try:
        orientation = im.getexif().get(0x0112, 1)
    except Exception:
        orientation = 1
    if orientation in _ROTATING_ORIENTATIONS:
        return h, w
    return w, h


def make_thumbnail(
    source: Path,
    cache: MediaCache,
    max_px: int,
    jpeg_quality: int,
    keep_alpha: bool = True,
    op: str = "img",
) -> tuple[Path, int, int, bool]:
    """Create (or reuse) a display copy of ``source``.

    Returns ``(path, width, height, has_alpha)`` where width/height are the
    oriented dimensions of the *original* image (needed for aspect ratio).
    """
    key = cache.key(source, op, f"{max_px}|{jpeg_quality}|{keep_alpha}")
    meta = cache.load_meta(key)
    if meta and Path(meta["path"]).is_file():
        return Path(meta["path"]), meta["width"], meta["height"], meta["alpha"]

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with Image.open(source) as im:
            width, height = _oriented_size(im)
            if getattr(im, "is_animated", False):
                im.seek(0)
            if im.format == "JPEG":
                # Decode at reduced scale: much faster for big camera photos.
                im.draft("RGB", (max_px, max_px))
            im.load()
            im = ImageOps.exif_transpose(im) or im
            has_alpha = keep_alpha and (
                im.mode in ("RGBA", "LA", "PA")
                or (im.mode == "P" and "transparency" in im.info)
            )
            if has_alpha:
                im = im.convert("RGBA")
                # Fully opaque images do not need PNG.
                extrema = im.getchannel("A").getextrema()
                if extrema[0] == 255:
                    has_alpha = False
            if not has_alpha:
                im = im.convert("RGB")
            if max(im.size) > max_px:
                im.thumbnail((max_px, max_px), Image.Resampling.LANCZOS)
            if has_alpha:
                out = cache.path(key, ".png")
                im.save(out, "PNG", optimize=False, compress_level=6)
            else:
                out = cache.path(key, ".jpg")
                im.save(out, "JPEG", quality=jpeg_quality, optimize=True, progressive=False)
    cache.save_meta(key, {"path": str(out), "width": width, "height": height, "alpha": has_alpha})
    return out, width, height, has_alpha


def process_image(media: Media, cache: MediaCache, max_px: int, jpeg_quality: int) -> None:
    assert media.path is not None
    try:
        thumb, w, h, alpha = make_thumbnail(media.path, cache, max_px, jpeg_quality)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, SyntaxError) as exc:
        log.warning("Cannot read image %s: %s", media.path.name, exc)
        media.error = "unreadable"
        return
    media.thumbnail = thumb
    media.width, media.height = w, h
    media.has_alpha = alpha

