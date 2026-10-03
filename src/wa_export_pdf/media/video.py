"""Video (and GIF-as-MP4) previews: a representative frame + duration."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from PIL import Image

from ..models import Media
from . import ffmpeg as ff
from .cache import MediaCache
from .containers import duration_from_container
from .images import make_thumbnail

log = logging.getLogger(__name__)


def _frame_time(duration: float | None) -> float:
    # WhatsApp shows the first frame; first frames are often black or blurry,
    # so take one a little later when the clip is long enough.
    if not duration or duration < 2:
        return 0.0
    return min(1.0, duration * 0.1)


def extract_frame(ffmpeg: Path, source: Path, cache: MediaCache, max_px: int, quality: int) -> tuple[Path | None, dict]:
    key = cache.key(source, "video", f"{max_px}|{quality}")
    meta = cache.load_meta(key)
    if meta is not None and (meta.get("path") is None or Path(meta["path"]).is_file()):
        return (Path(meta["path"]) if meta.get("path") else None), meta

    info = ff.probe(ffmpeg, source)
    out = cache.path(key, ".jpg")
    qscale = max(2, min(31, round((100 - quality) / 6)))
    scale = f"scale='min({max_px},iw)':'min({max_px},ih)':force_original_aspect_ratio=decrease"
    produced = False
    for t in dict.fromkeys((_frame_time(info.duration), 0.0)):
        try:
            proc = ff.run(
                [ffmpeg, "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", source,
                 "-frames:v", "1", "-vf", scale, "-q:v", str(qscale), out],
                timeout=120, capture_stdout=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            log.debug("frame extraction failed for %s: %s", source.name, exc)
            break
        if proc.returncode == 0 and out.is_file() and out.stat().st_size > 0:
            produced = True
            break
    width, height = info.width, info.height
    if produced:
        try:
            with Image.open(out) as im:
                width, height = im.size
        except Exception:
            produced = False
    meta = {
        "path": str(out) if produced else None,
        "duration": info.duration,
        "width": width,
        "height": height,
    }
    cache.save_meta(key, meta)
    return (out if produced else None), meta


def process_video(media: Media, cache: MediaCache, ffmpeg: Path | None, max_px: int, quality: int) -> None:
    assert media.path is not None
    media.duration = duration_from_container(media.path)
    if ffmpeg is None:
        media.error = media.error or "no-ffmpeg"
        return
    frame, meta = extract_frame(ffmpeg, media.path, cache, max_px, quality)
    if meta.get("duration"):
        media.duration = meta["duration"]
    if frame is None:
        media.error = "no-frame"
        return
    media.thumbnail = frame
    media.width, media.height = meta.get("width"), meta.get("height")


def process_gif_image(media: Media, cache: MediaCache, max_px: int, quality: int) -> None:
    """Real .gif files: first frame through Pillow (no FFmpeg needed)."""
    assert media.path is not None
    try:
        thumb, w, h, alpha = make_thumbnail(media.path, cache, max_px, quality, op="gif")
    except Exception as exc:
        log.warning("Cannot read GIF %s: %s", media.path.name, exc)
        media.error = "unreadable"
        return
    media.thumbnail, media.width, media.height, media.has_alpha = thumb, w, h, alpha
