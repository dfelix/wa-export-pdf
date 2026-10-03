"""Derived-media cache (thumbnails, video frames, waveforms).

By default the cache lives inside the per-run temporary directory and is
removed at the end, so no image derived from a private conversation stays on
disk. ``--cache-dir`` makes it persistent, which speeds up re-runs a lot on
big exports.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

CACHE_VERSION = "3"


class MediaCache:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def key(self, source: Path, operation: str, params: str = "") -> str:
        try:
            st = source.stat()
            fingerprint = f"{source.resolve()}|{st.st_size}|{st.st_mtime_ns}"
        except OSError:
            fingerprint = str(source)
        raw = f"{CACHE_VERSION}|{fingerprint}|{operation}|{params}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def path(self, key: str, suffix: str) -> Path:
        folder = self.root / key[:2]
        folder.mkdir(exist_ok=True)
        return folder / f"{key}{suffix}"

    def load_meta(self, key: str) -> dict[str, Any] | None:
        p = self.path(key, ".json")
        if not p.is_file():
            return None
        try:
            return json.loads(p.read_text("utf-8"))
        except (OSError, ValueError):
            return None

    def save_meta(self, key: str, data: dict[str, Any]) -> None:
        p = self.path(key, ".json")
        fd, tmp = tempfile.mkstemp(dir=p.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        os.replace(tmp, p)
