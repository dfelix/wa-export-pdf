"""Structured conversation -> WhatsApp-looking HTML pages.

The renderer only consumes :mod:`wa_export_pdf.models`. It computes the
visual decisions WhatsApp makes (grouping of consecutive messages, which
bubble gets the "tail", date chips, media box sizes, jumbo emoji...) and
hands plain view objects to Jinja templates.

Big conversations are split into *chunks* (whole days, ``chunk_size``
messages at most) so each Chromium render pass stays small; the PDFs are
merged afterwards.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, ClassVar, Iterator

from jinja2 import ChoiceLoader, Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from ..config import PageSize, RenderOptions
from ..emoji import emoji_only_count
from ..i18n import Translator
from ..models import Conversation, Direction, Message, MessageType
from .text import format_text, plain_preview
from .theme import Theme, font_face_css, header_font_data_uris

log = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

_E2E = re.compile(
    r"encrypt|encripta|criptograf|cifrad|chiffr|verschlüssel|crittograf|versleuteld|şifrel", re.I
)


# ---------------------------------------------------------------------------
# View objects
# ---------------------------------------------------------------------------

@dataclass
class MediaBox:
    width: int
    height: int
    crop: bool = False


@dataclass
class MessageView:
    view: ClassVar[str] = "message"
    msg: Message
    kind: str                      # message type value, used as CSS class
    side: str                      # "in" | "out"
    first: bool = False            # first of a group: tail + sender name
    last: bool = False
    show_name: bool = False
    show_avatar: bool = False
    name_color: int = 0
    time: str = ""
    text_html: Markup = Markup("")
    jumbo: int = 0
    box: MediaBox | None = None
    media_url: str | None = None
    caption: bool = False
    bubbleless: bool = False
    duration: str = ""
    size: str = ""
    doc_name: str = ""
    doc_ext: str = ""
    doc_meta: str = ""
    doc_icon: str = "generic"
    placeholder: str = ""
    missing: bool = False
    waveform: list[float] = field(default_factory=list)
    poll_max: int = 0
    long: bool = False             # taller than a page: allowed to split


@dataclass
class DayView:
    view: ClassVar[str] = "day"
    day: date
    label: str
    month_label: str


@dataclass
class SystemView:
    view: ClassVar[str] = "system"
    msg: Message
    text_html: Markup
    e2e: bool
    time: str


@dataclass
class Chunk:
    index: int
    items: list[Any]
    message_count: int
    first_day: date | None
    last_day: date | None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def format_duration(seconds: float | None) -> str:
    if seconds is None or seconds < 0 or math.isnan(seconds):
        return ""
    total = int(round(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def format_size(n: int | None) -> str:
    if n is None:
        return ""
    units = ["B", "kB", "MB", "GB"]
    size = float(n)
    for unit in units:
        if size < 1000 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}".replace(".0 ", " ")
        size /= 1000
    return f"{n} B"


def fit_media(w: int | None, h: int | None, page: PageSize) -> MediaBox:
    """Box size WhatsApp would use for a photo/video thumbnail."""
    max_w, max_h = page.media_w, page.media_h
    if not w or not h:
        return MediaBox(max_w, round(max_w * 0.75))
    ratio = w / h
    bw, bh = float(max_w), max_w / ratio
    if bh > max_h:
        bh = max_h
        bw = bh * ratio
    crop = False
    if bw < page.media_min_w:      # very tall: WhatsApp crops (object-fit: cover)
        bw, crop = page.media_min_w, True
    if bh < page.media_min_h:      # very wide panorama
        bh, crop = page.media_min_h, True
    return MediaBox(round(bw), round(bh), crop)


def fit_sticker(w: int | None, h: int | None, page: PageSize) -> MediaBox:
    s = page.sticker
    if not w or not h:
        return MediaBox(s, s)
    scale = s / max(w, h)
    return MediaBox(round(w * scale), round(h * scale))


_DOC_ICONS = {
    "pdf": "pdf",
    "doc": "word", "docx": "word", "odt": "word", "rtf": "word",
    "xls": "excel", "xlsx": "excel", "ods": "excel", "csv": "excel",
    "ppt": "ppt", "pptx": "ppt", "odp": "ppt", "key": "ppt",
    "zip": "zip", "rar": "zip", "7z": "zip", "gz": "zip",
    "txt": "text", "apk": "apk",
}


# A message estimated taller than this many lines may start on the current
# page and continue on the next one, instead of leaving a near-empty page.
LONG_MESSAGE_LINES = 30


def _estimated_lines(text: str, per_line: int = 55) -> int:
    return sum(max(1, math.ceil(len(line) / per_line)) for line in text.split("\n")) if text else 0


def file_uri(path: Path | None) -> str | None:
    return path.resolve().as_uri() if path else None


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

class HtmlRenderer:
    def __init__(self, conv: Conversation, theme: Theme, options: RenderOptions):
        self.conv = conv
        self.theme = theme
        self.options = options
        self.page = options.page
        self.t = Translator(conv.locale)
        loaders = [FileSystemLoader(str(d)) for d in theme.template_dirs]
        loaders.append(FileSystemLoader(str(TEMPLATES_DIR)))
        self.env = Environment(
            loader=ChoiceLoader(loaders),
            autoescape=select_autoescape(["html"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.env.globals.update(t=self.t, opts=options, page=self.page, conv=conv)
        self._fonts = header_font_data_uris()

    # -- view model -----------------------------------------------------------

    def _visible_messages(self) -> Iterator[Message]:
        f, to = self.options.date_from, self.options.date_to
        for m in self.conv.messages:
            d = m.day
            if f and d < f:
                continue
            if to and d > to:
                continue
            yield m

    def _time(self, m: Message) -> str:
        return self.t.time(m.timestamp, self.conv.uses_12h_clock)

    def build_items(self) -> list[Any]:
        """Flat list of DayView / SystemView / MessageView in display order."""
        items: list[Any] = []
        prev: Message | None = None
        prev_view: MessageView | None = None
        for m in self._visible_messages():
            new_day = prev is None or m.day != prev.day
            if new_day:
                items.append(DayView(m.day, self.t.long_date(m.day), self.t.month_year(m.day)))
            if m.direction is Direction.SYSTEM:
                text = m.text
                items.append(SystemView(m, format_text(text), bool(_E2E.search(text)), self._time(m)))
                if prev_view:
                    prev_view.last = True
                prev, prev_view = m, None
                continue
            continues = (
                prev_view is not None
                and not new_day
                and prev is not None
                and prev.sender == m.sender
                and prev.direction is m.direction
            )
            view = self._message_view(m, first=not continues)
            if not continues and prev_view is not None:
                prev_view.last = True
            items.append(view)
            prev, prev_view = m, view
        if prev_view:
            prev_view.last = True
        return items

    def _message_view(self, m: Message, first: bool) -> MessageView:
        side = "out" if m.direction is Direction.OUTGOING else "in"
        participant = self.conv.participants.get(m.sender or "")
        v = MessageView(
            msg=m,
            kind=m.type.value,
            side=side,
            first=first,
            show_name=first and self.conv.is_group and side == "in",
            show_avatar=first and self.conv.is_group and side == "in",
            name_color=participant.color_index if participant else 0,
            time=self._time(m),
        )
        t = m.type
        media = m.media
        include_media = self.options.include_media

        v.long = _estimated_lines(m.text) > LONG_MESSAGE_LINES
        if t is MessageType.TEXT:
            v.jumbo = emoji_only_count(m.text)
            v.text_html = format_text(m.text)
            return v

        v.text_html = format_text(m.text)
        v.caption = bool(m.text.strip())

        if t is MessageType.DELETED:
            # Keep WhatsApp's own wording from the export when available.
            v.placeholder = m.text or self.t("deleted_out" if side == "out" else "deleted_in")
            return v
        if t in (MessageType.VIEW_ONCE, MessageType.UNKNOWN) and not media:
            v.placeholder = m.metadata.get("placeholder") or m.text or self.t("view_once")
            return v
        if t is MessageType.CALL:
            v.placeholder = self.t(f"call_{m.metadata.get('call', 'voice')}") if not m.text else m.text
            return v
        if t is MessageType.LOCATION or t is MessageType.POLL:
            if m.poll:
                v.poll_max = max([o.votes or 0 for o in m.poll.options] + [0])
            return v

        if media is None:
            return v

        v.size = format_size(media.size_bytes)
        v.missing = not media.exists or not include_media
        if media.omitted:
            v.placeholder = m.metadata.get("placeholder", "").strip("<>") or self.t("media_omitted")
        elif not media.exists:
            v.placeholder = self.t("missing_file")
        elif media.error == "unreadable":
            v.placeholder = self.t("unreadable")

        if t in (MessageType.IMAGE, MessageType.VIDEO, MessageType.GIF):
            v.box = fit_media(media.width, media.height, self.page)
            if include_media and media.thumbnail:
                v.media_url = file_uri(media.thumbnail)
            v.duration = format_duration(media.duration)
            if not v.media_url and not v.placeholder and t is MessageType.IMAGE:
                v.placeholder = self.t("unreadable")
        elif t is MessageType.STICKER:
            v.box = fit_sticker(media.width, media.height, self.page)
            if include_media and media.thumbnail:
                v.media_url = file_uri(media.thumbnail)
                v.bubbleless = True
        elif t in (MessageType.VOICE, MessageType.AUDIO):
            v.duration = format_duration(media.duration)
            v.waveform = list(media.waveform or [])
        elif t is MessageType.DOCUMENT:
            name = media.filename
            title = m.metadata.get("document_title")
            if title and not re.match(r"^DOC-\d{8}-WA\d+", title):
                if Path(name).suffix.strip(".") and not Path(title).suffix:
                    title = f"{title}.{Path(name).suffix.strip('.')}"
                name = title
            v.doc_name = name
            ext = (media.extension or Path(name).suffix.lstrip(".")).lower()
            v.doc_ext = ext.upper()
            v.doc_icon = _DOC_ICONS.get(ext, "generic")
            parts = []
            if media.page_count:
                word = self.t("page") if media.page_count == 1 else self.t("pages")
                parts.append(f"{media.page_count} {word}")
            if v.doc_ext:
                parts.append(v.doc_ext)
            if v.size:
                parts.append(v.size)
            v.doc_meta = " • ".join(parts)
            if include_media and media.thumbnail:
                v.media_url = file_uri(media.thumbnail)
                v.box = MediaBox(self.page.media_w, int(min(130, self.page.media_w * 0.4)))
        elif t is MessageType.CONTACT:
            v.doc_name = media.contact_name or Path(media.filename).stem
        return v

    # -- chunking --------------------------------------------------------------

    def chunks(self, items: list[Any] | None = None) -> list[Chunk]:
        items = self.build_items() if items is None else items
        size = max(1, self.options.chunk_size)
        chunks: list[Chunk] = []
        current: list[Any] = []
        count = 0

        def flush() -> None:
            nonlocal current, count
            if not current:
                return
            days = [i.day for i in current if isinstance(i, DayView)]
            chunks.append(Chunk(len(chunks), current, count, days[0] if days else None, days[-1] if days else None))
            current, count = [], 0

        for item in items:
            # Only cut before a date chip: chunks start on a new day.
            if isinstance(item, DayView) and count >= size:
                flush()
            current.append(item)
            if not isinstance(item, DayView):
                count += 1
        flush()
        return chunks

    # -- output -----------------------------------------------------------------

    def _head_context(self) -> dict[str, Any]:
        doodle = self.theme.doodle_data_uri() if self.options.background == "doodle" else None
        return {
            "stylesheets": [p.resolve().as_uri() for p in self.theme.stylesheets]
            + [p.resolve().as_uri() for p in self.options.extra_css],
            "font_faces": Markup(font_face_css(self.options.emoji_font)),
            "header_fonts": self._fonts,
            "doodle": doodle,
            "page_css": Markup(self.page_css()),
            "title": self.document_title(),
        }

    def document_title(self) -> str:
        return self.options.title or self.conv.title

    @property
    def top_margin(self) -> int:
        # App bar + a small gap so content never touches it after a break.
        p = self.page
        return (p.header_h + 8) if self.options.header else p.bottom_margin

    def page_css(self) -> str:
        p = self.page
        top = self.top_margin
        return (
            f"@page{{size:{p.css_width} {p.css_height};margin:{top}px 0 {p.bottom_margin}px 0}}\n"
            f":root{{--lane-pad:{p.lane_padding}px;--bubble-max:{p.bubble_max};"
            f"--media-w:{p.media_w}px;--voice-w:{p.voice_w}px;--sticker:{p.sticker}px}}"
        )

    def render_chunk(self, chunk: Chunk, total: int) -> str:
        template = self.env.get_template("conversation.html")
        ctx = self._head_context()
        ctx.update(
            items=chunk.items,
            chunk=chunk,
            total_chunks=total,
            is_first=chunk.index == 0,
            subtitle=self.subtitle(),
        )
        return template.render(**ctx)

    def subtitle(self) -> str:
        if not self.conv.is_group:
            return ""
        names = [p.name for p in self.conv.participants.values()]
        names = [self.t("you") if self.conv.participants[n].is_me else n for n in names]
        return plain_preview(", ".join(names), 120)

    def header_template(self) -> str:
        """HTML for Chromium's headerTemplate (the app bar on every page)."""
        tpl = self.env.get_template("header.html")
        css = self.theme.css_text(self.theme.header_stylesheets)
        return tpl.render(
            css=Markup(css),
            header_fonts=self._fonts,
            title=self.document_title(),
            subtitle=self.subtitle(),
            show_bar=self.options.header,
            height=self.top_margin,
            bar_height=self.page.header_h,
            doodle=self.theme.doodle_data_uri() if self.options.background == "doodle" else None,
        )

    def footer_template(self) -> str:
        tpl = self.env.get_template("footer.html")
        css = self.theme.css_text(self.theme.header_stylesheets)
        return tpl.render(
            css=Markup(css),
            height=self.page.bottom_margin,
            doodle=self.theme.doodle_data_uri() if self.options.background == "doodle" else None,
        )

    def write_chunks(self, out_dir: Path) -> list[tuple[Chunk, Path]]:
        out_dir.mkdir(parents=True, exist_ok=True)
        chunks = self.chunks()
        written = []
        for chunk in chunks:
            path = out_dir / f"conversation-{chunk.index + 1:03d}.html"
            path.write_text(self.render_chunk(chunk, len(chunks)), encoding="utf-8")
            written.append((chunk, path))
        return written

