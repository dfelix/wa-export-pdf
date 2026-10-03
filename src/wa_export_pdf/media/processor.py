"""Process every attachment of a conversation, in parallel and with caching.

Nothing is held in RAM: each worker reads one file, writes a display copy to
the cache directory and only keeps the resulting path and a few numbers on
the :class:`~wa_export_pdf.models.Media` object.
"""

from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from ..models import Conversation, Message, MessageType
from .audio import process_audio
from .cache import MediaCache
from .documents import process_contact, process_document
from .images import process_image
from .video import process_gif_image, process_video

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Quality:
    name: str
    image_px: int        # longest side for photos / video frames
    sticker_px: int
    jpeg: int


QUALITY_PRESETS = {
    "low": Quality("low", 720, 256, 72),
    "medium": Quality("medium", 1100, 380, 82),
    "high": Quality("high", 1600, 512, 90),
    "original": Quality("original", 6000, 1024, 94),
}


@dataclass
class MediaSettings:
    quality: Quality
    ffmpeg: Path | None
    waveforms: bool = True
    pdf_previews: bool = True
    jobs: int = 0

    @property
    def workers(self) -> int:
        return self.jobs or min(8, (os.cpu_count() or 2))


def _process_one(msg: Message, cache: MediaCache, settings: MediaSettings) -> None:
    media = msg.media
    assert media is not None and media.path is not None
    q = settings.quality
    t = msg.type
    if t is MessageType.IMAGE:
        process_image(media, cache, q.image_px, q.jpeg)
    elif t is MessageType.STICKER:
        process_image(media, cache, q.sticker_px, q.jpeg)
    elif t is MessageType.GIF:
        if (media.extension or "") == "gif":
            process_gif_image(media, cache, q.image_px, q.jpeg)
        else:
            process_video(media, cache, settings.ffmpeg, q.image_px, q.jpeg)
    elif t is MessageType.VIDEO:
        process_video(media, cache, settings.ffmpeg, q.image_px, q.jpeg)
    elif t in (MessageType.VOICE, MessageType.AUDIO):
        process_audio(media, cache, settings.ffmpeg, settings.waveforms and t is MessageType.VOICE)
    elif t is MessageType.DOCUMENT:
        process_document(media, cache, settings.pdf_previews, q.jpeg)
    elif t is MessageType.CONTACT:
        process_contact(media)


def process_media(conv: Conversation, cache: MediaCache, settings: MediaSettings) -> dict[str, int]:
    todo = [m for m in conv.messages if m.media is not None and m.media.path is not None]
    stats = {"processed": 0, "errors": 0}
    if not todo:
        return stats
    log.info("Processing %d attachments with %d workers", len(todo), settings.workers)
    started = time.monotonic()
    last_report = started
    with ThreadPoolExecutor(max_workers=settings.workers) as pool:
        futures = {pool.submit(_process_one, m, cache, settings): m for m in todo}
        for done, fut in enumerate(as_completed(futures), start=1):
            msg = futures[fut]
            try:
                fut.result()
            except Exception as exc:  # one broken file must not stop the run
                assert msg.media is not None
                msg.media.error = msg.media.error or "failed"
                log.warning("Failed to process %s: %s", msg.media.filename, exc)
                log.debug("traceback", exc_info=True)
            if msg.media and msg.media.error:
                stats["errors"] += 1
            stats["processed"] += 1
            now = time.monotonic()
            if now - last_report > 5 or done == len(todo):
                log.info("  media %d/%d (%.0fs)", done, len(todo), now - started)
                last_report = now
    return stats
