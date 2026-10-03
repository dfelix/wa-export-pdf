"""Emoji detection without third-party packages.

The regex below matches complete emoji sequences (skin tones, ZWJ families,
flags, keycaps, tag sequences) closely enough to wrap them in a ``<span>``
that uses the bundled colour emoji font, and to detect "emoji-only"
messages that WhatsApp shows in a bigger size.
"""

from __future__ import annotations

import re

_PICTO = (
    "©®‼⁉™ℹ↔-↙↩↪"
    "⌚⌛⌨⏏⏩-⏳⏸-⏺Ⓜ▪▫▶◀"
    "◻-◾☀-➿⤴⤵⬅-⬇⬛⬜⭐⭕"
    "〰〽㊗㊙"
    "\U0001f000-\U0001f0ff\U0001f10d-\U0001f1ad\U0001f200-\U0001f2ff"
    "\U0001f300-\U0001f5ff\U0001f600-\U0001f64f\U0001f680-\U0001f6ff"
    "\U0001f7e0-\U0001f7ff\U0001f900-\U0001f9ff\U0001fa70-\U0001faff"
)
# Characters that are emoji only when followed by VS16 (U+FE0F).
_TEXT_DEFAULT = "©®‼⁉™ℹ↔-↙↩↪Ⓜ▪▫▶◀⤴⤵〰〽"

_MOD = "[\U0001f3fb-\U0001f3ff]"
_VS = "️?"
_ELEMENT = f"(?:[{_PICTO}]{_VS}{_MOD}?)"
_SEQ = f"{_ELEMENT}(?:‍{_ELEMENT})*"
_FLAG = "[\U0001f1e6-\U0001f1ff]{2}"
_KEYCAP = "[0-9#*]️?⃣"
_TAGS = "\U0001f3f4[\U000e0020-\U000e007e]+\U000e007f"

EMOJI_RE = re.compile(f"(?:{_TAGS}|{_FLAG}|{_KEYCAP}|{_SEQ})")
_TEXT_ONLY = re.compile(f"^[{_TEXT_DEFAULT}]$")


def is_emoji(seq: str) -> bool:
    """True if ``seq`` (a regex match) should be drawn as a colour emoji."""
    if _TEXT_ONLY.match(seq):
        return False  # ©, ®, ™ ... without VS16 stay text, like on phones
    return True


def iter_emoji(text: str):
    for m in EMOJI_RE.finditer(text):
        if is_emoji(m.group(0)):
            yield m


def emoji_only_count(text: str, limit: int = 3) -> int:
    """Number of emoji when ``text`` consists only of emoji (and spaces).

    Returns 0 when the text has anything else or more than ``limit`` emoji.
    """
    stripped = text.strip()
    if not stripped:
        return 0
    count = 0
    pos = 0
    for m in iter_emoji(stripped):
        if stripped[pos: m.start()].strip():
            return 0
        count += 1
        if count > limit:
            return 0
        pos = m.end()
    if stripped[pos:].strip():
        return 0
    return count
