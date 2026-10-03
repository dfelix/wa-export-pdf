"""Message text -> safe HTML, reproducing WhatsApp's own formatting rules.

Supported (as WhatsApp renders them):

* ``*bold*``, ``_italic_``, ``~strikethrough~``
* ```` ```monospace``` ```` blocks and `` `inline code` ``
* ``> quote`` lines, ``- item`` / ``* item`` bullets and ``1. item`` lists
* clickable links
* colour emoji (wrapped in ``<span class="emoji">``)

Everything else is HTML-escaped; message content can never inject markup.
"""

from __future__ import annotations

import html
import re

from markupsafe import Markup

from ..emoji import iter_emoji

_URL = re.compile(
    r"(?:(?:https?|ftp)://|www\.)[^\s<>\"'‎‏]+"
    r"|(?<![\w@.])(?:[a-z0-9-]+\.)+(?:com|org|net|pt|br|es|io|me|app|gov|edu|eu|uk|de|fr|it|ly|gl|co)"
    r"(?:/[^\s<>\"'‎‏]*)?(?![\w@])",
    re.I,
)
_TRAILING = ".,;:!?)]}'\"»”’…"

_MONO_BLOCK = re.compile(r"```(.+?)```", re.S)
_INLINE_CODE = re.compile(r"(?<![\w`])`([^`\n]+?)`(?![\w`])")

# Markers must touch non-space text on the inside and be delimited on the
# outside by start/end, whitespace or punctuation (not letters/digits).
_STYLES = [
    (re.compile(r"(?<![\w*])\*(?=\S)([^*\n]*?\S)\*(?![\w*])"), "strong"),
    (re.compile(r"(?<![\w_])_(?=\S)([^_\n]*?\S)_(?![\w_])"), "em"),
    (re.compile(r"(?<![\w~])~(?=\S)([^~\n]*?\S)~(?![\w~])"), "del"),
]

_PH = "\x00{}\x00"
_PH_RE = re.compile("\x00(\\d+)\x00")


def wrap_emoji(escaped: str) -> str:
    """Wrap emoji sequences of an *already escaped* string in spans."""
    out: list[str] = []
    pos = 0
    for m in iter_emoji(escaped):
        out.append(escaped[pos: m.start()])
        out.append(f'<span class="emoji">{m.group(0)}</span>')
        pos = m.end()
    out.append(escaped[pos:])
    return "".join(out)


def _link(url: str) -> str:
    href = url if re.match(r"^[a-z]+://", url, re.I) else "http://" + url
    return f'<a href="{html.escape(href, quote=True)}">{wrap_emoji(html.escape(url))}</a>'


def _split_trailing(url: str) -> tuple[str, str]:
    tail = ""
    while url and url[-1] in _TRAILING:
        if url[-1] == ")" and url.count("(") >= url.count(")"):
            break
        tail = url[-1] + tail
        url = url[:-1]
    return url, tail


def _inline(text: str, slots: list[str]) -> str:
    """Escape + format a fragment without line structure."""

    def stash(fragment: str) -> str:
        slots.append(fragment)
        return _PH.format(len(slots) - 1)

    text = _INLINE_CODE.sub(lambda m: stash(f'<code class="inline-code">{html.escape(m.group(1))}</code>'), text)

    def url_sub(m: re.Match) -> str:
        url, tail = _split_trailing(m.group(0))
        if not url:
            return m.group(0)
        return stash(_link(url)) + tail

    text = _URL.sub(url_sub, text)
    escaped = html.escape(text, quote=False)
    for _ in range(2):  # allow simple nesting such as *_bold italic_*
        for pattern, tag in _STYLES:
            escaped = pattern.sub(lambda m, t=tag: f"<{t}>{m.group(1)}</{t}>", escaped)
    return wrap_emoji(escaped)


def _lines(text: str, slots: list[str]) -> str:
    out: list[str] = []
    for line in text.split("\n"):
        if line.startswith("> "):
            out.append(f'<span class="wa-quote">{_inline(line[2:], slots)}</span>')
        elif re.match(r"^[*\-] \S", line):
            out.append(f'<span class="wa-li"><span class="wa-bullet">•</span>{_inline(line[2:], slots)}</span>')
        elif m := re.match(r"^(\d{1,3})\. (\S.*)$", line):
            out.append(
                f'<span class="wa-li"><span class="wa-num">{m.group(1)}.</span>{_inline(m.group(2), slots)}</span>'
            )
        else:
            out.append(_inline(line, slots))
    return "\n".join(out)


def format_text(text: str) -> Markup:
    """Render message text as HTML (to be shown with ``white-space: pre-wrap``)."""
    if not text:
        return Markup("")
    slots: list[str] = []
    parts: list[str] = []
    pos = 0
    for m in _MONO_BLOCK.finditer(text):
        parts.append(_lines(text[pos: m.start()], slots))
        parts.append(f'<code class="mono">{wrap_emoji(html.escape(m.group(1)))}</code>')
        pos = m.end()
    parts.append(_lines(text[pos:], slots))
    rendered = "".join(parts)
    # Placeholders may be nested (a link stashed inside inline code is not
    # possible, but be defensive) - resolve until stable.
    for _ in range(3):
        if "\x00" not in rendered:
            break
        rendered = _PH_RE.sub(lambda m: slots[int(m.group(1))], rendered)
    return Markup(rendered)


def plain_preview(text: str, limit: int = 160) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"
