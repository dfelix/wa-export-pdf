"""Locate and run FFmpeg in a platform-independent way.

Search order:

1. explicit ``--ffmpeg`` path
2. ``WA_EXPORT_PDF_FFMPEG`` environment variable
3. ``ffmpeg`` on ``PATH`` (``shutil.which`` handles ``.exe`` on Windows)
4. the binary shipped by the optional ``imageio-ffmpeg`` package
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

log = logging.getLogger(__name__)

ENV_VAR = "WA_EXPORT_PDF_FFMPEG"

_CREATIONFLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


@lru_cache(maxsize=8)
def find_ffmpeg(explicit: str | None = None) -> Path | None:
    candidates: list[str | None] = [explicit, os.environ.get(ENV_VAR)]
    for c in candidates:
        if c:
            p = Path(c).expanduser()
            if p.is_file():
                return p
            log.warning("FFmpeg not found at %s", p)
    found = shutil.which("ffmpeg")
    if found:
        return Path(found)
    try:
        import imageio_ffmpeg  # type: ignore

        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).is_file():
            return Path(exe)
    except Exception:  # package absent or binary missing
        pass
    return None


def run(args: list[str | os.PathLike], timeout: float = 120, capture_stdout: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(a) for a in args],
        stdout=subprocess.PIPE if capture_stdout else subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        timeout=timeout,
        creationflags=_CREATIONFLAGS,
        check=False,
    )


@dataclass
class ProbeInfo:
    duration: float | None = None
    width: int | None = None
    height: int | None = None
    rotation: int = 0
    has_video: bool = False
    has_audio: bool = False


_DURATION = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_VIDEO = re.compile(r"Stream #.*?Video:.*?(\d{2,5})x(\d{2,5})")
_ROTATE = re.compile(r"(?:rotate\s*:\s*|rotation of\s*)(-?\d+(?:\.\d+)?)")


def probe(ffmpeg: Path, path: Path) -> ProbeInfo:
    """Read stream information from ``ffmpeg -i`` (ffprobe is not always shipped)."""
    info = ProbeInfo()
    try:
        proc = run([ffmpeg, "-hide_banner", "-i", path], timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.debug("ffmpeg probe failed for %s: %s", path, exc)
        return info
    text = proc.stderr.decode("utf-8", "replace")
    m = _DURATION.search(text)
    if m:
        h, mi, s = m.groups()
        info.duration = int(h) * 3600 + int(mi) * 60 + float(s)
    m = _VIDEO.search(text)
    if m:
        info.has_video = True
        info.width, info.height = int(m.group(1)), int(m.group(2))
    info.has_audio = "Audio:" in text
    m = _ROTATE.search(text)
    if m:
        info.rotation = int(round(float(m.group(1)))) % 360
        if info.rotation in (90, 270) and info.width and info.height:
            info.width, info.height = info.height, info.width
    return info
