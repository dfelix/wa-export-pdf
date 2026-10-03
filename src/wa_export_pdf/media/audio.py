"""Audio: duration and a WhatsApp-style waveform for voice notes."""

from __future__ import annotations

import logging
import subprocess
import sys
from array import array
from pathlib import Path

from ..models import Media
from . import ffmpeg as ff
from .cache import MediaCache
from .containers import duration_from_container

log = logging.getLogger(__name__)

WAVEFORM_BARS = 44


def compute_waveform(samples: array, bars: int = WAVEFORM_BARS) -> list[float]:
    """Peak amplitude per bucket, normalised to 0..1 with a soft curve."""
    n = len(samples)
    if n == 0:
        return []
    size = max(1, n // bars)
    peaks: list[float] = []
    for i in range(bars):
        chunk = samples[i * size: (i + 1) * size] if i < bars - 1 else samples[i * size:]
        if not chunk:
            peaks.append(0.0)
            continue
        peak = max(max(chunk), -min(chunk))
        peaks.append(float(peak))
    top = max(peaks) or 1.0
    # sqrt makes quiet passages visible, like WhatsApp's waveform does.
    return [round((p / top) ** 0.5, 3) for p in peaks]


def waveform(ffmpeg: Path, source: Path, cache: MediaCache, duration: float | None) -> list[float] | None:
    key = cache.key(source, "wave", str(WAVEFORM_BARS))
    meta = cache.load_meta(key)
    if meta is not None:
        return meta.get("waveform")
    # Keep the decoded PCM small even for very long recordings.
    rate = 4000
    if duration and duration > 60:
        rate = max(200, int(240000 / duration))
    try:
        proc = ff.run(
            [ffmpeg, "-v", "error", "-i", source, "-map", "0:a:0", "-ac", "1",
             "-ar", str(rate), "-f", "s16le", "-acodec", "pcm_s16le", "-"],
            timeout=300,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.debug("waveform failed for %s: %s", source.name, exc)
        return None
    if proc.returncode != 0 or not proc.stdout:
        cache.save_meta(key, {"waveform": None})
        return None
    data = proc.stdout
    if len(data) % 2:
        data = data[:-1]
    samples = array("h")
    samples.frombytes(data)
    if sys.byteorder == "big":
        samples.byteswap()
    wf = compute_waveform(samples)
    cache.save_meta(key, {"waveform": wf, "duration": len(samples) / rate})
    return wf


def process_audio(media: Media, cache: MediaCache, ffmpeg: Path | None, with_waveform: bool) -> None:
    assert media.path is not None
    try:
        media.duration = duration_from_container(media.path)
    except OSError:
        media.duration = None
    if ffmpeg is None:
        return
    if media.duration is None:
        info = ff.probe(ffmpeg, media.path)
        media.duration = info.duration
    if with_waveform:
        media.waveform = waveform(ffmpeg, media.path, cache, media.duration)
