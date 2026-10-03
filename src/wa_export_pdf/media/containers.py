"""Pure-Python duration readers for the containers WhatsApp uses.

They make durations available even when FFmpeg is not installed:

* MP4 / M4A / 3GP / MOV: ``mvhd`` box (videos, audio files)
* Ogg (Opus / Vorbis): granule position of the last page (voice notes)
"""

from __future__ import annotations

import struct
from pathlib import Path

_CONTAINER_BOXES = {b"moov", b"trak", b"mdia", b"minf", b"stbl", b"udta", b"edts"}


def mp4_duration(path: Path) -> float | None:
    try:
        with path.open("rb") as fh:
            fh.seek(0, 2)
            end = fh.tell()
            return _find_mvhd(fh, 0, end)
    except (OSError, struct.error):
        return None


def _find_mvhd(fh, start: int, end: int) -> float | None:
    pos = start
    while pos + 8 <= end:
        fh.seek(pos)
        header = fh.read(8)
        if len(header) < 8:
            return None
        size, box = struct.unpack(">I4s", header)
        header_len = 8
        if size == 1:
            size = struct.unpack(">Q", fh.read(8))[0]
            header_len = 16
        elif size == 0:
            size = end - pos
        if size < header_len:
            return None
        if box == b"mvhd":
            version = fh.read(1)[0]
            fh.read(3)
            if version == 1:
                fh.read(16)
                timescale, duration = struct.unpack(">IQ", fh.read(12))
            else:
                fh.read(8)
                timescale, duration = struct.unpack(">II", fh.read(8))
            if timescale:
                return duration / timescale
            return None
        if box == b"moov":
            found = _find_mvhd(fh, pos + header_len, pos + size)
            if found is not None:
                return found
        pos += size
    return None


def ogg_duration(path: Path) -> float | None:
    """Duration of an Ogg Opus/Vorbis stream from the last page granule."""
    try:
        with path.open("rb") as fh:
            head = fh.read(256)
            if not head.startswith(b"OggS"):
                return None
            if b"OpusHead" in head:
                idx = head.index(b"OpusHead")
                pre_skip = struct.unpack("<H", head[idx + 10: idx + 12])[0]
                rate = 48000
            elif b"\x01vorbis" in head:
                idx = head.index(b"\x01vorbis")
                rate = struct.unpack("<I", head[idx + 12: idx + 16])[0]
                pre_skip = 0
            else:
                return None
            fh.seek(0, 2)
            size = fh.tell()
            block = 65536
            pos = max(0, size - block)
            while True:
                fh.seek(pos)
                data = fh.read(min(block + 27, size - pos))
                last = data.rfind(b"OggS")
                while last != -1:
                    if last + 14 <= len(data):
                        granule = struct.unpack("<q", data[last + 6: last + 14])[0]
                        if granule > 0 and rate:
                            return max(0.0, (granule - pre_skip) / rate)
                    last = data.rfind(b"OggS", 0, last)
                if pos == 0:
                    return None
                pos = max(0, pos - block)
    except (OSError, struct.error, ValueError):
        return None


def duration_from_container(path: Path) -> float | None:
    with path.open("rb") as fh:
        head = fh.read(12)
    if head.startswith(b"OggS"):
        return ogg_duration(path)
    if head[4:8] == b"ftyp":
        return mp4_duration(path)
    return None
