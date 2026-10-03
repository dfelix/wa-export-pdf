"""Generate the chat background "doodle" tiles used by the bundled themes.

WhatsApp's own wallpaper is proprietary artwork, so the project ships an
original pattern drawn in the same spirit: small line-art icons, randomly
rotated, very low contrast. Run from the repository root:

    python tools/make_doodle.py

The SVG is the editable source; the PNG (rendered at 3x by Chromium, then
palette-quantised) is what themes use: Chromium rasterises CSS SVG
backgrounds once per PDF page at 72 dpi, while a bitmap tile is embedded
once and reused as a crisp tiling pattern on every page.
"""

from __future__ import annotations

import random
from pathlib import Path

ICONS = {
    "heart": '<path d="M12 20s-7-4.3-9.2-8.6A5 5 0 0 1 12 6.3a5 5 0 0 1 9.2 5.1C19 15.7 12 20 12 20z"/>',
    "star": '<path d="M12 3l2.7 5.6 6.1.8-4.4 4.3 1.1 6.1L12 17l-5.5 2.8 1.1-6.1-4.4-4.3 6.1-.8z"/>',
    "chat": '<path d="M4 5h16v11H10l-5 4v-4H4z"/><path d="M8 9.5h8M8 12.5h5"/>',
    "phone": '<path d="M6 3.5h3l1.6 4.4-2 1.4a10.5 10.5 0 0 0 6.1 6.1l1.4-2 4.4 1.6v3A2 2 0 0 1 18.5 20 15 15 0 0 1 4 5.5 2 2 0 0 1 6 3.5z"/>',
    "camera": '<rect x="3" y="7" width="18" height="12" rx="2"/><circle cx="12" cy="13" r="3.5"/><path d="M8.5 7l1.5-2.5h4L15.5 7"/>',
    "note": '<path d="M9 17.5V5.5l10-2v12"/><circle cx="6.5" cy="17.5" r="2.5"/><circle cx="16.5" cy="15.5" r="2.5"/>',
    "smile": '<circle cx="12" cy="12" r="8.5"/><path d="M8.5 14.5a4 4 0 0 0 7 0"/><path d="M9.2 9.5h.1M14.8 9.5h.1"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2.5M12 19v2.5M2.5 12H5M19 12h2.5M5.3 5.3l1.8 1.8M16.9 16.9l1.8 1.8M5.3 18.7l1.8-1.8M16.9 7.1l1.8-1.8"/>',
    "moon": '<path d="M19.5 14.5A8 8 0 1 1 9.5 4.5a6.3 6.3 0 0 0 10 10z"/>',
    "cloud": '<path d="M7 18h10.5a3.8 3.8 0 0 0 .3-7.6A5.8 5.8 0 0 0 6.6 11 3.5 3.5 0 0 0 7 18z"/>',
    "cup": '<path d="M5 8h11v5.5a4.5 4.5 0 0 1-4.5 4.5h-2A4.5 4.5 0 0 1 5 13.5z"/><path d="M16 9.5h1.5a2 2 0 0 1 0 4H16M8.5 3.5v2M11.5 3.5v2"/>',
    "plane": '<path d="M3 11.5l18-8-6.5 17-3.2-6.8z"/><path d="M11.3 13.7L21 3.5"/>',
    "clock": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    "mail": '<rect x="3" y="6" width="18" height="12" rx="1.5"/><path d="M3.5 7l8.5 6 8.5-6"/>',
    "umbrella": '<path d="M3 12a9 9 0 0 1 18 0z"/><path d="M12 12v6a2 2 0 0 1-4 0"/>',
    "gift": '<rect x="4" y="10" width="16" height="10"/><rect x="3" y="7" width="18" height="3"/><path d="M12 7v13M12 7c-1.5-3-5-3-4.5-.5M12 7c1.5-3 5-3 4.5-.5"/>',
    "leaf": '<path d="M5 19C5 10 10.5 4.5 20 4.5 20 13 15 19 5 19z"/><path d="M5 19l8.5-8.5"/>',
    "balloon": '<ellipse cx="12" cy="9" rx="5.5" ry="6.5"/><path d="M12 15.5l-1 1.5h2zM12 17c0 2-2 2.5-1 4.5"/>',
    "bolt": '<path d="M13 2.5L5 13.5h6l-1 8 8-11h-6z"/>',
    "pizza": '<path d="M12 21L4 6.5a15 15 0 0 1 16 0z"/><circle cx="10" cy="10" r="1"/><circle cx="14" cy="12" r="1"/>',
    "bike": '<circle cx="6" cy="16" r="3.5"/><circle cx="18" cy="16" r="3.5"/><path d="M6 16l4-7h5l3 7M10 9l2 7h-6M14 6.5h2.5"/>',
    "headphones": '<path d="M4 16v-4a8 8 0 0 1 16 0v4"/><rect x="3" y="14" width="4" height="6" rx="1.5"/><rect x="17" y="14" width="4" height="6" rx="1.5"/>',
    "pin": '<path d="M12 21s-6.5-6.2-6.5-11a6.5 6.5 0 0 1 13 0c0 4.8-6.5 11-6.5 11z"/><circle cx="12" cy="10" r="2.3"/>',
    "icecream": '<path d="M7.5 10a4.5 4.5 0 0 1 9 0z"/><path d="M7.5 10L12 21l4.5-11"/>',
    "house": '<path d="M3.5 11L12 4l8.5 7"/><path d="M5.5 9.5V20h13V9.5M10 20v-5h4v5"/>',
    "bell": '<path d="M6 16.5V11a6 6 0 0 1 12 0v5.5l1.5 1.5h-15z"/><path d="M10 20.5h4"/>',
    "lock": '<rect x="5" y="10.5" width="14" height="10" rx="1.5"/><path d="M8 10.5V8a4 4 0 0 1 8 0v2.5"/>',
    "flower": '<circle cx="12" cy="10" r="2"/><path d="M12 8a2.5 2.5 0 1 1 2-3.4A2.5 2.5 0 1 1 15 9.6 2.5 2.5 0 1 1 12.9 12 2.5 2.5 0 1 1 9 12a2.5 2.5 0 1 1-.9-3.4A2.5 2.5 0 1 1 12 8zM12 12v9M12 17c-2 0-3.5-1-4-2.5"/>',
    "glasses": '<circle cx="7" cy="14" r="3.5"/><circle cx="17" cy="14" r="3.5"/><path d="M10.5 14h3M3.5 14l1-5M20.5 14l-1-5"/>',
    "game": '<path d="M7 8h10a4 4 0 0 1 4 4.5l-.5 3a2.3 2.3 0 0 1-4 1L15 15H9l-1.5 1.5a2.3 2.3 0 0 1-4-1l-.5-3A4 4 0 0 1 7 8z"/><path d="M8 11v3M6.5 12.5h3M15.5 11.5h.1M17.5 13.5h.1"/>',
}

TILE = 420


def build(color: str, opacity: float, seed: int = 7) -> str:
    rng = random.Random(seed)
    names = list(ICONS)
    cols, rows = 6, 6
    cell = TILE / cols
    parts = []
    for r in range(rows):
        for c in range(cols):
            name = names[(r * cols + c) % len(names)] if r * cols + c < len(names) else rng.choice(names)
            scale = rng.uniform(1.05, 1.45)
            x = c * cell + cell / 2 + rng.uniform(-cell * 0.18, cell * 0.18)
            y = r * cell + cell / 2 + rng.uniform(-cell * 0.18, cell * 0.18)
            rot = rng.uniform(-35, 35)
            parts.append(
                f'<g transform="translate({x:.1f} {y:.1f}) rotate({rot:.0f}) scale({scale:.2f}) translate(-12 -12)">'
                f"{ICONS[name]}</g>"
            )
    body = "".join(parts)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{TILE}" height="{TILE}" viewBox="0 0 {TILE} {TILE}">'
        f'<g fill="none" stroke="{color}" stroke-opacity="{opacity}" stroke-width="1.3" '
        f'stroke-linecap="round" stroke-linejoin="round">{body}</g></svg>\n'
    )


def rasterise(svg: Path, png: Path, scale: int = 3) -> None:
    from PIL import Image
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(device_scale_factor=scale, viewport={"width": TILE, "height": TILE})
        page.set_content(f'<html><body style="margin:0">{svg.read_text("utf-8")}</body></html>')
        page.screenshot(path=str(png), omit_background=True, clip={"x": 0, "y": 0, "width": TILE, "height": TILE})
        browser.close()
    with Image.open(png) as im:
        im.load()
        quantised = im.quantize(colors=32, method=Image.Quantize.FASTOCTREE)
    quantised.save(png, optimize=True)


def main() -> None:
    root = Path(__file__).resolve().parent.parent / "src" / "wa_export_pdf" / "themes"
    for theme, color, opacity in (("whatsapp", "#4a3f2f", 0.10), ("whatsapp-dark", "#b9c4c9", 0.06)):
        svg = root / theme / "assets" / "doodle.svg"
        svg.write_text(build(color, opacity), "utf-8")
        rasterise(svg, svg.with_suffix(".png"))
    print("doodles written")


if __name__ == "__main__":
    main()
