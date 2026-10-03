"""Locate the chat text file inside an export (folder, .txt or .zip)."""

from __future__ import annotations

import logging
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path

from . import formats as F

log = logging.getLogger(__name__)


@dataclass
class ExportLocation:
    chat_file: Path
    media_root: Path
    title_source: str          # file/folder name used to guess the chat title


class DiscoveryError(Exception):
    pass


def _header_score(path: Path, max_lines: int = 60) -> int:
    score = 0
    try:
        with path.open("r", encoding="utf-8-sig", errors="replace") as fh:
            for i, line in enumerate(fh):
                if i >= max_lines:
                    break
                if F.ANDROID_HEADER.match(line) or F.IOS_HEADER.match(line):
                    score += 1
    except OSError:
        return 0
    return score


def find_chat_file(folder: Path) -> Path:
    candidates = [p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() == ".txt"]
    if not candidates:
        raise DiscoveryError(f"No .txt chat file found in {folder}")
    scored = []
    for p in candidates:
        score = _header_score(p)
        bonus = 0
        if F.title_from_filename(p.stem) or p.name.lower() in ("_chat.txt", "chat.txt"):
            bonus = 1000
        depth = len(p.relative_to(folder).parts)
        scored.append((score > 0, bonus + score, -depth, p))
    scored.sort(key=lambda t: (t[0], t[1], t[2]), reverse=True)
    best = scored[0]
    if not best[0]:
        raise DiscoveryError(f"None of the .txt files in {folder} looks like a WhatsApp export")
    return best[3]


def _safe_extract(archive: zipfile.ZipFile, target: Path) -> None:
    root = target.resolve()
    for member in archive.infolist():
        dest = (target / member.filename).resolve()
        if root != dest and root not in dest.parents:
            raise DiscoveryError(f"Unsafe path inside zip: {member.filename}")
        if member.is_dir():
            dest.mkdir(parents=True, exist_ok=True)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(member) as src, dest.open("wb") as dst:
            shutil.copyfileobj(src, dst, 1024 * 1024)


def locate_export(source: Path, work_dir: Path) -> ExportLocation:
    """Resolve the user's input into a chat file + the folder holding media.

    ``work_dir`` is used to unpack ``.zip`` exports (the share-sheet export
    on both Android and iOS produces a zip).
    """
    source = source.expanduser()
    if not source.exists():
        raise DiscoveryError(f"Input not found: {source}")

    if source.is_file() and source.suffix.lower() == ".zip":
        target = work_dir / "export"
        target.mkdir(parents=True, exist_ok=True)
        log.info("Extracting %s", source.name)
        with zipfile.ZipFile(source) as archive:
            _safe_extract(archive, target)
        chat = find_chat_file(target)
        return ExportLocation(chat, chat.parent, _title_source(chat, source.stem))

    if source.is_file():
        return ExportLocation(source, source.parent, _title_source(source, source.parent.name))

    chat = find_chat_file(source)
    return ExportLocation(chat, source, _title_source(chat, source.name))


def _title_source(chat: Path, fallback: str) -> str:
    if F.title_from_filename(chat.stem):
        return chat.stem
    if F.title_from_filename(fallback):
        return fallback
    if chat.name.lower() in ("_chat.txt", "chat.txt"):
        return fallback
    return chat.stem
