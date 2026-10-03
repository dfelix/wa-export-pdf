"""Documents (page count, first-page preview) and contact cards (vCard)."""

from __future__ import annotations

import logging
import quopri
import re
from pathlib import Path

from ..models import Media
from .cache import MediaCache

log = logging.getLogger(__name__)


def pdf_page_count(path: Path) -> int | None:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path), strict=False)
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                return None
        return len(reader.pages)
    except Exception as exc:
        log.debug("page count failed for %s: %s", path.name, exc)
        return None


def pdf_preview(path: Path, cache: MediaCache, width_px: int, quality: int) -> Path | None:
    """Render the top of the first page (needs the optional pypdfium2)."""
    key = cache.key(path, "pdfprev", f"{width_px}|{quality}")
    meta = cache.load_meta(key)
    if meta is not None:
        p = meta.get("path")
        return Path(p) if p and Path(p).is_file() else None
    try:
        import pypdfium2 as pdfium  # type: ignore
    except ImportError:
        return None
    out = cache.path(key, ".jpg")
    try:
        doc = pdfium.PdfDocument(str(path))
        try:
            page = doc[0]
            w_pt = page.get_width()
            scale = width_px / w_pt if w_pt else 1.0
            bitmap = page.render(scale=scale)
            image = bitmap.to_pil().convert("RGB")
            image.save(out, "JPEG", quality=quality)
            page.close()
        finally:
            doc.close()
    except Exception as exc:
        log.debug("pdf preview failed for %s: %s", path.name, exc)
        cache.save_meta(key, {"path": None})
        return None
    cache.save_meta(key, {"path": str(out)})
    return out


def process_document(media: Media, cache: MediaCache, previews: bool, quality: int) -> None:
    assert media.path is not None
    if media.extension == "pdf" or media.mime == "application/pdf":
        media.page_count = pdf_page_count(media.path)
        if previews:
            prev = pdf_preview(media.path, cache, 660, quality)
            if prev is not None:
                media.thumbnail = prev
                try:
                    from PIL import Image

                    with Image.open(prev) as im:
                        media.width, media.height = im.size
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# vCard
# ---------------------------------------------------------------------------

def _unfold(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines():
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        elif raw.endswith("=") and "QUOTED-PRINTABLE" in raw.upper():
            lines.append(raw)
        elif lines and lines[-1].endswith("=") and "QUOTED-PRINTABLE" in lines[-1].upper():
            lines[-1] = lines[-1][:-1] + raw
        else:
            lines.append(raw)
    return lines


def _decode_value(params: str, value: str) -> str:
    if "QUOTED-PRINTABLE" in params.upper():
        charset = "utf-8"
        m = re.search(r"CHARSET=([\w-]+)", params, re.I)
        if m:
            charset = m.group(1)
        try:
            return quopri.decodestring(value.encode("ascii", "replace")).decode(charset, "replace")
        except LookupError:
            return quopri.decodestring(value.encode("ascii", "replace")).decode("utf-8", "replace")
    return value.replace("\\,", ",").replace("\\;", ";").replace("\\n", " ")


def parse_vcard(path: Path) -> tuple[str | None, list[str]]:
    try:
        text = path.read_text("utf-8", errors="replace")
    except OSError:
        return None, []
    name = None
    fallback = None
    phones: list[str] = []
    for line in _unfold(text):
        if ":" not in line:
            continue
        head, value = line.split(":", 1)
        prop, _, params = head.partition(";")
        prop = prop.upper().split(".")[-1]  # "item1.TEL" -> "TEL"
        if prop == "FN" and not name:
            name = _decode_value(params, value).strip() or None
        elif prop == "N" and not fallback:
            parts = [p for p in _decode_value(params, value).split(";") if p.strip()]
            if parts:
                fallback = " ".join(reversed(parts[:2])).strip()
        elif prop == "TEL":
            phone = value.strip()
            if phone and phone not in phones:
                phones.append(phone)
    return name or fallback, phones


def process_contact(media: Media) -> None:
    assert media.path is not None
    media.contact_name, media.contact_phones = parse_vcard(media.path)
