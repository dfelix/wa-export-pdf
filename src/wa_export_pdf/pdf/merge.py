"""Merge chunk PDFs into one document with a month/day outline."""

from __future__ import annotations

import logging
from pathlib import Path

from pypdf import PdfReader, PdfWriter

log = logging.getLogger(__name__)


def _collect_outline(reader: PdfReader, items, level: int, offset: int, out: list) -> None:
    for item in items:
        if isinstance(item, list):
            _collect_outline(reader, item, level + 1, offset, out)
            continue
        try:
            page = reader.get_destination_page_number(item)
        except Exception:
            continue
        if page is None or page < 0:
            continue
        out.append((level, str(item.title).strip(), offset + page))


def merge_pdfs(
    parts: list[Path],
    output: Path,
    title: str,
    subject: str = "",
    day_labels: list[list[tuple[str, str]]] | None = None,
) -> int:
    """Concatenate ``parts`` into ``output``; returns the page count.

    Chromium creates one bookmark per date chip (``<h3>``). Those are read
    back from every part and rebuilt as a two-level outline - month, then
    day - using ``day_labels`` (``(month, day)`` per date chip, in order),
    so a month that spans two parts appears once.
    """
    writer = PdfWriter()
    entries: list[tuple[int, str, int]] = []
    offset = 0
    for i, part in enumerate(parts):
        reader = PdfReader(str(part))
        writer.append(reader, import_outline=False)
        found: list[tuple[int, str, int]] = []
        _collect_outline(reader, reader.outline, 0, offset, found)
        labels = day_labels[i] if day_labels and i < len(day_labels) else None
        if labels and len(labels) == len(found):
            for (month, day), (_lvl, _t, page) in zip(labels, found):
                entries.append((0, month, page))
                entries.append((1, day, page))
        else:
            entries.extend(found)
        offset += len(reader.pages)

    current_month = None
    current_title = None
    for level, text, page in entries:
        if not text:
            continue
        if level == 0:
            if text == current_title:
                continue
            current_month = writer.add_outline_item(text, page)
            current_title = text
        else:
            writer.add_outline_item(text, page, parent=current_month)
    writer.add_metadata(
        {
            "/Title": title,
            "/Subject": subject,
            "/Creator": "wa-export-pdf",
        }
    )
    writer.page_mode = "/UseOutlines" if entries else "/UseNone"
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_name(output.name + ".part")
    with tmp.open("wb") as fh:
        writer.write(fh)
    tmp.replace(output)
    return offset


def render_pdf_pages_png(pdf: Path, out_dir: Path, limit: int | None, scale: float = 1.5) -> list[Path] | None:
    """Rasterise PDF pages to PNG (needs pypdfium2); None when unavailable."""
    try:
        import pypdfium2 as pdfium  # type: ignore
    except ImportError:
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    doc = pdfium.PdfDocument(str(pdf))
    try:
        n = len(doc) if limit is None else min(limit, len(doc))
        for i in range(n):
            page = doc[i]
            image = page.render(scale=scale).to_pil()
            path = out_dir / f"page-{i + 1:03d}.png"
            image.save(path)
            written.append(path)
            page.close()
    finally:
        doc.close()
    return written
