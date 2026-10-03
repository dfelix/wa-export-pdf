"""End-to-end conversion: export folder -> PDF."""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from .config import RenderOptions
from .media import MediaCache, MediaIndex, MediaSettings, QUALITY_PRESETS, find_ffmpeg, process_media, resolve_media
from .models import Conversation
from .parser import ParseOptions, locate_export, parse_file
from .pdf import ChromiumRenderer, PdfJob, merge_pdfs, render_pdf_pages_png
from .renderer.html import HtmlRenderer
from .renderer.theme import load_theme

log = logging.getLogger(__name__)


@dataclass
class ConvertOptions:
    parse: ParseOptions = field(default_factory=ParseOptions)
    render: RenderOptions = field(default_factory=RenderOptions)
    quality: str = "medium"
    ffmpeg: str | None = None
    waveforms: bool = True
    pdf_previews: bool = True
    jobs: int = 0
    cache_dir: Path | None = None
    keep_temp: bool = False
    debug_dir: Path | None = None
    screenshots: int | None = 10       # pages to rasterise in debug mode (None = all)
    html_only: bool = False


@dataclass
class ConvertResult:
    output: Path | None
    pages: int
    messages: int
    chunks: int
    media: dict[str, int]
    warnings: list[str]
    html_files: list[Path]
    screenshots: list[Path]
    seconds: float
    work_dir: Path | None = None


@contextmanager
def _work_dir(keep: bool) -> Iterator[Path]:
    path = Path(tempfile.mkdtemp(prefix="wa-export-pdf-"))
    try:
        yield path
    finally:
        if keep:
            log.info("Temporary files kept in %s", path)
        else:
            shutil.rmtree(path, ignore_errors=True)


def _summary(conv: Conversation, media_stats: dict[str, int]) -> dict:
    from collections import Counter

    return {
        "title": conv.title,
        "locale": conv.locale,
        "is_group": conv.is_group,
        "participants": {
            name: {"messages": p.message_count, "is_me": p.is_me} for name, p in conv.participants.items()
        },
        "messages": len(conv.messages),
        "types": dict(Counter(m.type.value for m in conv.messages)),
        "first": conv.messages[0].timestamp.isoformat() if conv.messages else None,
        "last": conv.messages[-1].timestamp.isoformat() if conv.messages else None,
        "media": media_stats,
        "warnings": conv.warnings,
    }


def convert(source: Path, output: Path | None, options: ConvertOptions) -> ConvertResult:
    started = time.monotonic()
    keep = options.keep_temp
    with _work_dir(keep) as work:
        # 1. Locate + parse ----------------------------------------------------
        location = locate_export(source, work)
        log.info("Chat file: %s", location.chat_file.name)
        conv = parse_file(location.chat_file, options.parse, title_source=location.title_source)
        me = conv.me.name if conv.me else "?"
        log.info(
            "Parsed %d messages, %d participants (you: %s), language: %s",
            len(conv.messages), len(conv.participants), me, conv.locale,
        )
        for w in conv.warnings[:20]:
            log.warning(w)
        if len(conv.warnings) > 20:
            log.warning("... and %d more parser warnings", len(conv.warnings) - 20)

        # 2. Media ----------------------------------------------------------------
        index = MediaIndex(location.media_root, exclude={location.chat_file})
        media_stats = resolve_media(conv, index)
        log.info(
            "Attachments: %d found, %d missing, %d omitted by WhatsApp",
            media_stats["found"], media_stats["missing"], media_stats["omitted"],
        )
        debug_dir = options.debug_dir
        if debug_dir:
            debug_dir.mkdir(parents=True, exist_ok=True)
        cache_root = options.cache_dir or ((debug_dir / "media-cache") if debug_dir else work / "media-cache")
        if options.render.include_media:
            ffmpeg = find_ffmpeg(options.ffmpeg)
            if ffmpeg is None:
                log.warning(
                    "FFmpeg not found: videos will show without a preview frame and voice notes "
                    "without a waveform. Install FFmpeg or `pip install imageio-ffmpeg`."
                )
            else:
                log.debug("FFmpeg: %s", ffmpeg)
            settings = MediaSettings(
                quality=QUALITY_PRESETS[options.quality],
                ffmpeg=ffmpeg,
                waveforms=options.waveforms,
                pdf_previews=options.pdf_previews,
                jobs=options.jobs,
            )
            stats = process_media(conv, MediaCache(cache_root), settings)
            media_stats.update(stats)

        # 3. HTML -----------------------------------------------------------------
        theme = load_theme(options.render.theme)
        renderer = HtmlRenderer(conv, theme, options.render)
        html_dir = debug_dir or (work / "html")
        written = renderer.write_chunks(html_dir)
        if debug_dir and len(written) == 1:
            single = debug_dir / "conversation.html"
            written[0][1].replace(single)
            written = [(written[0][0], single)]
        if debug_dir:
            (debug_dir / "conversation.json").write_text(
                json.dumps(_summary(conv, media_stats), ensure_ascii=False, indent=2), encoding="utf-8"
            )
        log.info("HTML: %d part(s)", len(written))

        result = ConvertResult(
            output=None,
            pages=0,
            messages=sum(c.message_count for c, _ in written),
            chunks=len(written),
            media=media_stats,
            warnings=list(conv.warnings),
            html_files=[p for _, p in written],
            screenshots=[],
            seconds=0.0,
            work_dir=work if keep else None,
        )
        if options.html_only or output is None:
            result.seconds = time.monotonic() - started
            return result

        # 4. PDF --------------------------------------------------------------------
        header = renderer.header_template()
        footer = renderer.footer_template()
        parts: list[Path] = []
        parts_dir = work / "parts"
        parts_dir.mkdir(exist_ok=True)
        with ChromiumRenderer() as chromium:
            for i, (chunk, html) in enumerate(written, start=1):
                part = parts_dir / f"part-{i:03d}.pdf"
                t0 = time.monotonic()
                chromium.render_pdf(PdfJob(html, part, header, footer), options.render.page.width_px)
                log.info(
                    "PDF part %d/%d (%s .. %s, %d messages) in %.1fs",
                    i, len(written), chunk.first_day, chunk.last_day, chunk.message_count,
                    time.monotonic() - t0,
                )
                parts.append(part)

            day_labels = [
                [(item.month_label, item.label) for item in chunk.items if getattr(item, "view", "") == "day"]
                for chunk, _ in written
            ]
            pages = merge_pdfs(
                parts, output, renderer.document_title(), subject="WhatsApp conversation", day_labels=day_labels
            )
            log.info("Wrote %s (%d pages)", output, pages)
            result.output = output
            result.pages = pages

            # 5. Debug screenshots -----------------------------------------------------
            if debug_dir:
                shots = render_pdf_pages_png(output, debug_dir, options.screenshots)
                if shots is None:
                    log.info("pypdfium2 not installed: screenshots taken from the HTML instead of the PDF")
                    page_h = _page_height_px(options.render)
                    shots = chromium.screenshot_html(
                        written[0][1], debug_dir, options.render.page.width_px, page_h, options.screenshots
                    )
                result.screenshots = shots
                log.info("Debug files in %s (%d screenshots)", debug_dir, len(shots))

        result.seconds = time.monotonic() - started
        return result


def _page_height_px(render: RenderOptions) -> int:
    page = render.page
    h = page.css_height
    if h.endswith("mm"):
        return round(float(h[:-2]) / 25.4 * 96)
    if h.endswith("in"):
        return round(float(h[:-2]) * 96)
    return int(float(h.rstrip("px")))
