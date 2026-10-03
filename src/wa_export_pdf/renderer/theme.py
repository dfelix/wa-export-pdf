"""Theme loading.

A theme is a folder with a ``theme.json`` manifest, CSS files and assets::

    themes/whatsapp/
        theme.json        {"name": ..., "extends": null, "stylesheets": [...],
                           "doodle": "assets/doodle.svg"}
        variables.css     colours, radii, fonts (CSS custom properties)
        bubbles.css ...   one file per area of the UI
        assets/           SVG/PNG resources referenced from CSS

A theme may ``extend`` another one; its stylesheets are loaded after the
parent's, so a dark theme only needs to override ``variables.css``.
Themes can be given by name (bundled) or by path (custom theme folder).
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent.parent
THEMES_DIR = PACKAGE_DIR / "themes"
FONTS_DIR = PACKAGE_DIR / "fonts"


class ThemeError(Exception):
    pass


@dataclass
class Theme:
    name: str
    folders: list[Path]                 # base first
    stylesheets: list[Path]
    header_stylesheets: list[Path]
    doodle: Path | None
    template_dirs: list[Path] = field(default_factory=list)
    dark: bool = False

    def doodle_data_uri(self) -> str | None:
        if not self.doodle or not self.doodle.is_file():
            return None
        data = base64.b64encode(self.doodle.read_bytes()).decode("ascii")
        mime = "image/svg+xml" if self.doodle.suffix == ".svg" else "image/png"
        return f"data:{mime};base64,{data}"

    def css_text(self, files: list[Path]) -> str:
        return "\n".join(p.read_text("utf-8") for p in files)


def available_themes() -> list[str]:
    return sorted(p.name for p in THEMES_DIR.iterdir() if (p / "theme.json").is_file())


def _theme_folder(name_or_path: str) -> Path:
    candidate = Path(name_or_path).expanduser()
    if (candidate / "theme.json").is_file():
        return candidate.resolve()
    bundled = THEMES_DIR / name_or_path
    if (bundled / "theme.json").is_file():
        return bundled
    raise ThemeError(f"Unknown theme '{name_or_path}'. Available: {', '.join(available_themes())}")


def load_theme(name_or_path: str) -> Theme:
    chain: list[tuple[Path, dict]] = []
    seen: set[Path] = set()
    current: str | None = name_or_path
    while current:
        folder = _theme_folder(current)
        if folder in seen:
            raise ThemeError(f"Theme inheritance loop at {folder}")
        seen.add(folder)
        manifest = json.loads((folder / "theme.json").read_text("utf-8"))
        chain.append((folder, manifest))
        current = manifest.get("extends")
    chain.reverse()

    stylesheets: list[Path] = []
    header_css: list[Path] = []
    doodle: Path | None = None
    template_dirs: list[Path] = []
    dark = False
    for folder, manifest in chain:
        for rel in manifest.get("stylesheets", []):
            p = folder / rel
            if not p.is_file():
                raise ThemeError(f"Missing stylesheet {p}")
            stylesheets.append(p)
        for rel in manifest.get("header_stylesheets", []):
            header_css.append(folder / rel)
        if manifest.get("doodle"):
            doodle = folder / manifest["doodle"]
        if (folder / "templates").is_dir():
            template_dirs.insert(0, folder / "templates")
        dark = manifest.get("dark", dark)
    name = chain[-1][1].get("name", chain[-1][0].name)
    return Theme(
        name=name,
        folders=[f for f, _ in chain],
        stylesheets=stylesheets,
        header_stylesheets=header_css,
        doodle=doodle,
        template_dirs=template_dirs,
        dark=dark,
    )


def font_face_css(emoji_font: str = "bundled") -> str:
    """@font-face rules for the bundled fonts (file URLs, work offline)."""
    rules = []
    for family, weight, style, file in (
        ("WA Roboto", 400, "normal", "Roboto-Regular.ttf"),
        ("WA Roboto", 500, "normal", "Roboto-Medium.ttf"),
        ("WA Roboto", 700, "normal", "Roboto-Bold.ttf"),
        ("WA Roboto", 400, "italic", "Roboto-Italic.ttf"),
        ("WA Roboto", 700, "italic", "Roboto-BoldItalic.ttf"),
        ("WA Mono", 400, "normal", "RobotoMono-Regular.ttf"),
    ):
        rules.append(
            f'@font-face{{font-family:"{family}";font-weight:{weight};font-style:{style};'
            f'src:url("{(FONTS_DIR / file).as_uri()}") format("truetype");font-display:block}}'
        )
    if emoji_font == "bundled":
        # unicode-range keeps digits, '#', '*' and spaces in the text font.
        rules.append(
            '@font-face{font-family:"WA Emoji";'
            f'src:url("{(FONTS_DIR / "NotoColorEmoji-COLRv1.ttf").as_uri()}") format("truetype");'
            "font-display:block;"
            "unicode-range:U+00A9,U+00AE,U+200D,U+203C,U+2049,U+20E3,U+2122,U+2139,U+2194-21AA,"
            "U+231A-23FF,U+24C2,U+25AA-25FE,U+2600-27BF,U+2934-2935,U+2B05-2B55,U+3030,U+303D,"
            "U+3297,U+3299,U+FE0F,U+1F000-1FAFF,U+E0020-E007F}"
        )
    return "\n".join(rules)


def header_font_data_uris() -> dict[str, str]:
    """Fonts for Chromium's header template, which cannot load file URLs.

    The exact same data URI is also declared in the main document so the
    font is already decoded when the header is painted.
    """
    out = {}
    for key, file in (("regular", "Roboto-Regular.ttf"), ("medium", "Roboto-Medium.ttf")):
        data = base64.b64encode((FONTS_DIR / file).read_bytes()).decode("ascii")
        out[key] = f"data:font/ttf;base64,{data}"
    return out
