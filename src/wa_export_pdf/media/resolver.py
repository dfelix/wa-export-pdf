"""Map attachment names found in the chat to files on disk."""

from __future__ import annotations

import logging
import unicodedata
from pathlib import Path

from ..models import Conversation, Message, MessageType
from .types import classify_extension, mime_for_extension, sniff

log = logging.getLogger(__name__)


def _key(name: str) -> str:
    # macOS stores file names decomposed (NFD); exports are NFC. Compare both
    # normalised and case-insensitively (Windows/macOS file systems are).
    return unicodedata.normalize("NFC", name).casefold()


class MediaIndex:
    """Index of every file below the export folder, by normalised name."""

    def __init__(self, root: Path, exclude: set[Path] | None = None):
        self.root = root
        self._files: dict[str, Path] = {}
        exclude = {p.resolve() for p in (exclude or set())}
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.resolve() in exclude:
                continue
            key = _key(path.name)
            # Prefer the shallowest file when names collide.
            if key not in self._files:
                self._files[key] = path
        log.debug("indexed %d files under %s", len(self._files), root)

    def __len__(self) -> int:
        return len(self._files)

    def find(self, filename: str) -> Path | None:
        if not filename:
            return None
        direct = self.root / filename
        if direct.is_file():
            return direct
        return self._files.get(_key(Path(filename).name))


def resolve_media(conv: Conversation, index: MediaIndex) -> dict[str, int]:
    """Attach file paths, sizes and MIME types to every media message.

    Returns counters (found / missing / omitted) for reporting.
    """
    stats = {"found": 0, "missing": 0, "omitted": 0}
    for msg in conv.messages:
        media = msg.media
        if media is None:
            continue
        if media.omitted:
            stats["omitted"] += 1
            continue
        path = index.find(media.filename)
        media.extension = Path(media.filename).suffix.lower().lstrip(".")
        if path is None:
            stats["missing"] += 1
            media.mime = mime_for_extension(media.extension)
            continue
        stats["found"] += 1
        media.path = path
        try:
            media.size_bytes = path.stat().st_size
        except OSError:
            media.size_bytes = None
        _refine_type(msg, path)
    return stats


def _refine_type(msg: Message, path: Path) -> None:
    """Use magic bytes when the extension is missing or misleading."""
    media = msg.media
    assert media is not None
    detected = sniff(path)
    if detected:
        ext, mime = detected
        media.mime = mime
        if not media.extension:
            media.extension = ext
        # A document without extension that is really an image, etc.
        if msg.type is MessageType.DOCUMENT and not Path(media.filename).suffix.strip("."):
            kind = classify_extension(ext)
            if kind in (MessageType.IMAGE,):
                msg.type = kind
        # GIF files sent as images.
        if ext == "gif" and msg.type is MessageType.IMAGE:
            msg.type = MessageType.GIF
    else:
        media.mime = mime_for_extension(media.extension)
