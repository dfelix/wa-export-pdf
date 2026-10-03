"""Attachment classification from file names and magic bytes (pure functions)."""

from __future__ import annotations

import re
from pathlib import Path

from ..models import MessageType

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".heic", ".heif", ".avif", ".jfif"}
VIDEO_EXT = {".mp4", ".3gp", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
AUDIO_EXT = {".opus", ".ogg", ".oga", ".m4a", ".mp3", ".aac", ".amr", ".wav", ".flac", ".wma"}
CONTACT_EXT = {".vcf"}

# Android: IMG-20260101-WA0001.jpg  /  iOS: 00000012-PHOTO-2026-01-01-10-00-00.jpg
_ANDROID_PREFIX = re.compile(r"^(?P<kind>IMG|VID|AUD|PTT|STK|DOC|GIF)-\d{8}-WA\d+", re.I)
_IOS_KIND = re.compile(r"^\d+-(?P<kind>PHOTO|VIDEO|AUDIO|STICKER|GIF|CONTACT|DOCUMENT)-", re.I)

_PREFIX_TYPES = {
    "IMG": MessageType.IMAGE,
    "PHOTO": MessageType.IMAGE,
    "VID": MessageType.VIDEO,
    "VIDEO": MessageType.VIDEO,
    "PTT": MessageType.VOICE,
    "AUD": MessageType.AUDIO,
    "AUDIO": MessageType.VOICE,   # iOS names voice notes "-AUDIO-....opus"
    "STK": MessageType.STICKER,
    "STICKER": MessageType.STICKER,
    "GIF": MessageType.GIF,
    "DOC": MessageType.DOCUMENT,
    "DOCUMENT": MessageType.DOCUMENT,
    "CONTACT": MessageType.CONTACT,
}


def classify_filename(filename: str) -> MessageType:
    """Best guess of the message type from an attachment's file name."""
    name = Path(filename).name
    ext = Path(name).suffix.lower()
    m = _ANDROID_PREFIX.match(name) or _IOS_KIND.match(name)
    if m:
        kind = _PREFIX_TYPES[m.group("kind").upper()]
        if kind in (MessageType.VOICE, MessageType.AUDIO):
            if ext not in AUDIO_EXT:
                return MessageType.DOCUMENT
            prefix = m.group("kind").upper()
            if prefix == "PTT" or (prefix == "AUDIO" and ext == ".opus"):
                return MessageType.VOICE
            return MessageType.AUDIO
        if kind is MessageType.IMAGE and ext == ".gif":
            return MessageType.GIF
        return kind
    if ext in CONTACT_EXT:
        return MessageType.CONTACT
    if ext == ".gif":
        return MessageType.GIF
    if ext == ".webp":
        return MessageType.IMAGE
    if ext in IMAGE_EXT:
        return MessageType.IMAGE
    if ext in VIDEO_EXT:
        return MessageType.VIDEO
    if ext == ".opus":
        return MessageType.VOICE
    if ext in AUDIO_EXT:
        return MessageType.AUDIO
    return MessageType.DOCUMENT


_MAGIC: list[tuple[bytes, int, str, str]] = [
    # (signature, offset, extension, mime)
    (b"%PDF", 0, "pdf", "application/pdf"),
    (b"\xff\xd8\xff", 0, "jpg", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", 0, "png", "image/png"),
    (b"GIF8", 0, "gif", "image/gif"),
    (b"OggS", 0, "ogg", "audio/ogg"),
    (b"ID3", 0, "mp3", "audio/mpeg"),
    (b"#!AMR", 0, "amr", "audio/amr"),
    (b"BEGIN:VCARD", 0, "vcf", "text/vcard"),
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", 0, "doc", "application/msword"),
    (b"Rar!", 0, "rar", "application/vnd.rar"),
    (b"7z\xbc\xaf\x27\x1c", 0, "7z", "application/x-7z-compressed"),
]

_MIME_BY_EXT = {
    "pdf": "application/pdf", "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
    "gif": "image/gif", "webp": "image/webp", "heic": "image/heic", "mp4": "video/mp4",
    "3gp": "video/3gpp", "mov": "video/quicktime", "webm": "video/webm", "mkv": "video/x-matroska",
    "opus": "audio/ogg", "ogg": "audio/ogg", "m4a": "audio/mp4", "mp3": "audio/mpeg",
    "aac": "audio/aac", "amr": "audio/amr", "wav": "audio/wav", "vcf": "text/vcard",
    "doc": "application/msword", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xls": "application/vnd.ms-excel", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "ppt": "application/vnd.ms-powerpoint", "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "txt": "text/plain", "zip": "application/zip", "csv": "text/csv", "apk": "application/vnd.android.package-archive",
}


def sniff(path: Path) -> tuple[str, str] | None:
    """Detect (extension, mime) from the first bytes of a file."""
    try:
        with path.open("rb") as fh:
            head = fh.read(64)
    except OSError:
        return None
    for sig, offset, ext, mime in _MAGIC:
        if head[offset: offset + len(sig)] == sig:
            return ext, mime
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp", "image/webp"
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "wav", "audio/wav"
    if head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand in (b"M4A ", b"M4B "):
            return "m4a", "audio/mp4"
        if brand in (b"heic", b"heix", b"mif1", b"msf1"):
            return "heic", "image/heic"
        if brand == b"qt  ":
            return "mov", "video/quicktime"
        if brand.startswith(b"3gp"):
            return "3gp", "video/3gpp"
        return "mp4", "video/mp4"
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "webm", "video/webm"
    if head[:4] == b"PK\x03\x04":
        return "zip", "application/zip"
    return None


def mime_for_extension(ext: str) -> str | None:
    return _MIME_BY_EXT.get(ext.lower().lstrip("."))


def classify_extension(ext: str) -> MessageType | None:
    ext = "." + ext.lower().lstrip(".")
    if ext in IMAGE_EXT or ext == ".webp":
        return MessageType.IMAGE
    if ext == ".gif":
        return MessageType.GIF
    if ext in VIDEO_EXT:
        return MessageType.VIDEO
    if ext in AUDIO_EXT:
        return MessageType.AUDIO
    if ext in CONTACT_EXT:
        return MessageType.CONTACT
    return None
