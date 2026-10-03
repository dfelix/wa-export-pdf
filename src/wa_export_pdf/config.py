"""Rendering options and page geometry."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class PageSize:
    """Physical page plus the WhatsApp-like layout metrics used on it.

    ``a4``/``letter`` reproduce WhatsApp Desktop/Web (a wide chat panel);
    ``phone`` reproduces a phone screen (Android 412x915 CSS px viewport)
    and therefore produces one "screenshot-like" page per screen.
    """

    name: str
    css_width: str
    css_height: str
    width_px: int                  # page width in CSS px (96 dpi)
    lane_padding: int              # left/right padding of the chat lane
    bubble_max: str                # max bubble width
    media_w: int                   # max media width inside a bubble
    media_h: int                   # max media height
    media_min_w: int
    media_min_h: int
    sticker: int
    voice_w: int
    header_h: int                  # top margin occupied by the app bar
    bottom_margin: int


PAGE_SIZES: dict[str, PageSize] = {
    "a4": PageSize("a4", "210mm", "297mm", 794, 56, "65%", 330, 360, 150, 100, 190, 336, 60, 16),
    "letter": PageSize("letter", "8.5in", "11in", 816, 58, "65%", 330, 360, 150, 100, 190, 336, 60, 16),
    "phone": PageSize("phone", "412px", "915px", 412, 10, "84%", 262, 330, 140, 96, 150, 262, 56, 10),
}


@dataclass
class RenderOptions:
    theme: str = "whatsapp"
    page_size: str = "a4"
    background: str = "doodle"         # doodle | plain
    header: bool = True                # WhatsApp app bar on top of every page
    ticks: bool = False                # cosmetic read ticks (not in the export!)
    emoji_font: str = "bundled"        # bundled | system
    include_media: bool = True
    chunk_size: int = 2000             # messages per Chromium render pass
    title: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    extra_css: list[Path] = field(default_factory=list)

    @property
    def page(self) -> PageSize:
        return PAGE_SIZES[self.page_size]
