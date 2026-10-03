"""Tolerant parser for WhatsApp ``.txt`` chat exports (Android and iOS).

The parser works in two passes:

1. *Tokenise*: every line that starts with a timestamp header opens a new
   raw record; any other line is a continuation of the previous record
   (multi-line messages, captions, poll options...).
2. *Interpret*: once all records are known we can decide the date order
   (DMY / MDY / YMD), tell senders from system notices and classify each
   message (text, media, deleted, poll, location...).

A record that cannot be interpreted never aborts the parse: it becomes an
``UNKNOWN`` message (or is attached to the previous one) and a warning is
recorded on the :class:`Conversation`.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator

from ..media.types import classify_filename
from ..models import (
    Conversation,
    Direction,
    Location,
    Media,
    Message,
    MessageType,
    Participant,
    Poll,
    PollOption,
)
from . import formats as F

log = logging.getLogger(__name__)

NAME_COLOR_COUNT = 20


@dataclass
class ParseOptions:
    me: str | None = None
    date_order: str = "auto"          # auto | dmy | mdy | ymd
    title: str | None = None
    locale: str | None = None         # force UI locale (otherwise detected)


@dataclass
class _Record:
    line_no: int
    style: str                        # "android" | "ios"
    date: str
    time: str
    ampm: str | None
    rest: str
    extra: list[str] = field(default_factory=list)

    @property
    def body(self) -> str:
        if not self.extra:
            return self.rest
        return "\n".join([self.rest, *self.extra])


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def read_lines(path: Path) -> Iterator[str]:
    """Yield the lines of an export, detecting the text encoding."""
    with path.open("rb") as fh:
        head = fh.read(4)
    if head.startswith((b"\xff\xfe", b"\xfe\xff")):
        encoding = "utf-16"
    else:
        encoding = "utf-8-sig"
        try:
            with path.open("r", encoding=encoding) as fh:
                for _ in fh:
                    pass
        except UnicodeDecodeError:
            encoding = "cp1252"
    with path.open("r", encoding=encoding, errors="replace", newline=None) as fh:
        for line in fh:
            yield line.rstrip("\r\n")


def _tokenise(lines: Iterable[str]) -> tuple[list[_Record], list[str]]:
    records: list[_Record] = []
    orphans: list[str] = []
    for line_no, line in enumerate(lines, start=1):
        m = None
        style = ""
        for style, pattern in (("android", F.ANDROID_HEADER), ("ios", F.IOS_HEADER)):
            m = pattern.match(line)
            if m:
                break
        if m:
            records.append(
                _Record(
                    line_no=line_no,
                    style=style,
                    date=m.group("date"),
                    time=m.group("time"),
                    ampm=m.group("ampm"),
                    rest=m.group("rest"),
                )
            )
        elif records:
            records[-1].extra.append(line)
        elif line.strip():
            orphans.append(line)
    return records, orphans


# ---------------------------------------------------------------------------
# Timestamps
# ---------------------------------------------------------------------------

_DATE_SPLIT = re.compile(r"[./\-]")
_AM = {"a", "午前", "上午", "오전", "ص"}


def _date_parts(date: str) -> tuple[int, int, int, int]:
    """Return (a, b, c, len_of_first_component)."""
    raw = _DATE_SPLIT.split(date)
    return int(raw[0]), int(raw[1]), int(raw[2]), len(raw[0])


def _detect_date_order(records: list[_Record]) -> str:
    if not records:
        return "dmy"
    if _date_parts(records[0].date)[3] == 4:
        return "ymd"
    first_gt_12 = second_gt_12 = False
    for r in records:
        a, b, _c, _ = _date_parts(r.date)
        first_gt_12 |= a > 12
        second_gt_12 |= b > 12
        if first_gt_12 or second_gt_12:
            break
    if first_gt_12 and not second_gt_12:
        return "dmy"
    if second_gt_12 and not first_gt_12:
        return "mdy"
    # Ambiguous (all days <= 12): pick the order with fewer time travels.
    best, best_score = "dmy", None
    for order in ("dmy", "mdy"):
        score = 0
        previous = None
        for r in records:
            ts = _make_timestamp(r, order)
            if ts is None:
                score += 1
                continue
            if previous and ts < previous:
                score += 1
            previous = ts
        if best_score is None or score < best_score:
            best, best_score = order, score
    return best


def _make_timestamp(r: _Record, order: str) -> datetime | None:
    try:
        a, b, c, _ = _date_parts(r.date)
        if order == "ymd":
            year, month, day = a, b, c
        elif order == "mdy":
            month, day, year = a, b, c
        else:
            day, month, year = a, b, c
        if year < 100:
            year += 2000
        tparts = [int(x) for x in re.split(r"[:.]", r.time)]
        hour, minute = tparts[0], tparts[1]
        second = tparts[2] if len(tparts) > 2 else 0
        if r.ampm:
            token = r.ampm.replace(".", "").replace(" ", "").replace(" ", "").replace(" ", "").lower()
            is_am = token in _AM or token.startswith("a")
            if is_am and hour == 12:
                hour = 0
            elif not is_am and hour != 12:
                hour += 12
        return datetime(year, month, day, hour, minute, second)
    except (ValueError, IndexError):
        return None


# ---------------------------------------------------------------------------
# Interpretation
# ---------------------------------------------------------------------------

def _looks_like_sentence(candidate: str) -> bool:
    return (
        len(candidate.split()) > 6
        or any(q in candidate for q in '"“”«»')
        or candidate.strip() != candidate
    )


def _split_sender(rest: str) -> tuple[str | None, str]:
    m = F.SENDER_SPLIT.match(rest)
    if m:
        return F.strip_bidi(m.group("sender")).strip(), m.group("text")
    m = F.SENDER_SPLIT_EMPTY.match(rest)
    if m:
        return F.strip_bidi(m.group("sender")).strip(), ""
    return None, rest


def _is_document_title(caption: str, filename: str) -> bool:
    caption = caption.strip()
    if not caption or "\n" in caption:
        return False
    stem = Path(filename).stem.rstrip(".")
    cap_stem = Path(caption).stem if Path(caption).suffix else caption
    return caption == filename or cap_stem == stem or (len(cap_stem) >= 4 and stem.startswith(cap_stem))


def _is_system_text(text: str) -> bool:
    return any(p.search(text) for p in F.SYSTEM_PATTERNS)


class _Interpreter:
    def __init__(self, records: list[_Record], order: str):
        self.records = records
        self.order = order
        self.sender_counts: Counter[str] = Counter()
        # iOS uses the group name as a pseudo-sender for system notices whose
        # text starts with an LRM mark. A sender whose *every* message looks
        # like that is not a real participant.
        self.lrm_only: Counter[str] = Counter()
        for r in records:
            sender, text = _split_sender(r.rest)
            if sender is not None:
                self.sender_counts[sender] += 1
                if r.style == "ios" and text.startswith("‎") and not self._is_media_marker(text):
                    self.lrm_only[sender] += 1
        self.pseudo_senders = {
            s for s, n in self.lrm_only.items() if n == self.sender_counts[s]
        }

    @staticmethod
    def _is_media_marker(text: str) -> bool:
        t = F.strip_bidi(text).strip()
        return bool(
            F.IOS_ATTACHMENT.match(t)
            or F.ANDROID_ATTACHMENT.match(t.split("\n", 1)[0])
            or t.lower() in F.MEDIA_OMITTED
        )

    def interpret(self, index: int, r: _Record) -> Message | None:
        ts = _make_timestamp(r, self.order)
        if ts is None:
            return None
        sender, text = _split_sender(r.rest)
        if r.extra:
            text = "\n".join([text, *r.extra])
        msg_id = f"m{index:06d}"

        is_system = False
        if sender is None:
            is_system = True
            text = r.body
        elif sender in self.pseudo_senders:
            is_system = True
        elif r.style == "ios" and text.startswith("‎") and _is_system_text(text):
            is_system = True
        elif self.sender_counts[sender] == 1 and (_looks_like_sentence(sender) or _is_system_text(r.rest)):
            is_system = True
            sender, text = None, r.body

        if is_system:
            return Message(
                id=msg_id,
                timestamp=ts,
                sender=None,
                direction=Direction.SYSTEM,
                type=MessageType.SYSTEM,
                text=F.strip_bidi(text).strip(),
                source_line=r.line_no,
            )
        msg = Message(
            id=msg_id,
            timestamp=ts,
            sender=sender,
            direction=Direction.INCOMING,
            type=MessageType.TEXT,
            source_line=r.line_no,
        )
        self._classify_content(msg, text)
        return msg

    # -- content ------------------------------------------------------------

    def _classify_content(self, msg: Message, text: str) -> None:
        m = F.EDITED_SUFFIX.search(text)
        if m:
            msg.edited = True
            text = text[: m.start()]

        stripped = F.strip_bidi(text).strip()
        first_line, _, remainder = stripped.partition("\n")
        first_line = F.strip_bidi(first_line).strip()
        lower = stripped.lower()

        # Attachments ------------------------------------------------------
        att = F.ANDROID_ATTACHMENT.match(first_line) or F.IOS_ATTACHMENT.match(first_line)
        if att:
            filename = F.strip_bidi(att.group("file")).strip()
            msg.type = classify_filename(filename)
            msg.media = Media(filename=filename)
            caption = F.strip_bidi(remainder).strip("\n")
            if msg.type is MessageType.DOCUMENT and _is_document_title(caption, filename):
                # Android writes the document's original name on the next line.
                msg.metadata["document_title"] = caption.strip()
                caption = ""
            msg.text = caption
            return

        if lower in F.MEDIA_OMITTED:
            msg.type = F.MEDIA_OMITTED[lower]
            msg.media = Media(filename="", omitted=True)
            msg.metadata["placeholder"] = stripped
            return

        if lower in F.VIEW_ONCE_MARKERS:
            msg.type = MessageType.VIEW_ONCE
            msg.metadata["placeholder"] = stripped.strip("<>")
            return

        if lower.rstrip(".") in F.DELETED_MARKERS or lower in F.DELETED_MARKERS:
            msg.type = MessageType.DELETED
            msg.text = stripped
            return

        call_kind = F.CALL_MARKERS.get(lower.split(",")[0].strip())
        if call_kind and len(stripped) < 80:
            msg.type = MessageType.CALL
            msg.text = stripped.split(",")[0].strip()
            msg.metadata["call"] = call_kind
            return

        loc = F.LOCATION.match(stripped)
        if loc:
            msg.type = MessageType.LOCATION
            msg.location = Location(
                latitude=float(loc.group("lat")),
                longitude=float(loc.group("lon")),
                url=loc.group("url"),
            )
            return

        if F.POLL_HEADER.match(first_line):
            poll = self._parse_poll(remainder)
            if poll:
                msg.type = MessageType.POLL
                msg.poll = poll
                return

        if re.fullmatch(r"<[^<>\n]{2,80}>", stripped):
            # A placeholder we do not know (new WhatsApp feature, other language).
            msg.type = MessageType.UNKNOWN
            msg.metadata["placeholder"] = stripped.strip("<>")
            return

        msg.type = MessageType.TEXT
        msg.text = text.strip("\n").lstrip("‎")

    @staticmethod
    def _parse_poll(body: str) -> Poll | None:
        lines = [F.strip_bidi(l).strip() for l in body.split("\n")]
        lines = [l for l in lines if l]
        if not lines:
            return None
        question = lines[0]
        options = []
        for line in lines[1:]:
            m = F.POLL_OPTION.match(line)
            if m:
                votes = m.group("votes")
                options.append(PollOption(text=m.group("text"), votes=int(votes) if votes else None))
        if not options:
            return None
        return Poll(question=question, options=options)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_locale(sample: str, title_hint: str | None = None) -> str:
    scores: Counter[str] = Counter()
    haystack = sample + "\n" + (title_hint or "")
    for locale, signatures in F.LOCALE_SIGNATURES.items():
        for sig in signatures:
            if sig in haystack:
                scores[locale] += haystack.count(sig)
    if not scores:
        return "en"
    return scores.most_common(1)[0][0]


def parse_lines(
    lines: Iterable[str],
    options: ParseOptions | None = None,
    source_name: str | None = None,
) -> Conversation:
    options = options or ParseOptions()
    lines = list(lines)
    records, orphans = _tokenise(lines)
    warnings: list[str] = []
    if orphans:
        warnings.append(f"{len(orphans)} line(s) before the first message were ignored")
    if not records:
        raise ValueError("No WhatsApp messages found: the file does not look like a WhatsApp export")

    order = options.date_order if options.date_order != "auto" else _detect_date_order(records)
    log.debug("date order: %s", order)
    interp = _Interpreter(records, order)

    messages: list[Message] = []
    for idx, rec in enumerate(records):
        try:
            msg = interp.interpret(idx, rec)
        except Exception as exc:  # never lose the whole chat for one record
            log.debug("record at line %d failed: %s", rec.line_no, exc, exc_info=True)
            msg = None
        if msg is None:
            warnings.append(f"line {rec.line_no}: could not interpret message, kept as text")
            if messages:
                messages[-1].text += "\n" + rec.body
                continue
            continue
        messages.append(msg)

    uses_12h = any(r.ampm for r in records[:200])

    # Participants -----------------------------------------------------------
    counts: Counter[str] = Counter(m.sender for m in messages if m.sender)
    participants: dict[str, Participant] = {}
    for name in sorted(counts, key=lambda n: (-counts[n], n)):
        participants[name] = Participant(name=name, message_count=counts[name])
    # Colour per participant follows first appearance, like WhatsApp does.
    first_seen = list(dict.fromkeys(m.sender for m in messages if m.sender))
    for i, name in enumerate(first_seen):
        participants[name].color_index = i % NAME_COLOR_COUNT

    title_hint = F.title_from_filename(source_name) if source_name else None
    title = options.title or title_hint or (source_name or "WhatsApp")
    is_group = len(participants) > 2 or (
        title_hint is not None and title_hint not in participants and len(participants) != 2
    )

    me = _resolve_me(options.me, participants, title_hint, warnings)
    if me:
        participants[me].is_me = True
        for msg in messages:
            if msg.sender == me:
                msg.direction = Direction.OUTGOING

    sample = "\n".join(lines[:3000])
    locale = options.locale or detect_locale(sample, source_name)

    return Conversation(
        title=title,
        messages=messages,
        participants=participants,
        is_group=is_group,
        locale=locale,
        uses_12h_clock=uses_12h,
        warnings=warnings,
    )


def _resolve_me(
    requested: str | None,
    participants: dict[str, Participant],
    title_hint: str | None,
    warnings: list[str],
) -> str | None:
    if requested:
        if requested in participants:
            return requested
        lowered = {p.casefold(): p for p in participants}
        if requested.casefold() in lowered:
            return lowered[requested.casefold()]
        warnings.append(f"--me '{requested}' is not a participant; known: {', '.join(participants)}")
        return None
    if len(participants) == 2 and title_hint:
        others = [p for p in participants if p != title_hint]
        if len(others) == 1 and title_hint in participants:
            return others[0]
    if len(participants) == 1 and title_hint and title_hint not in participants:
        return next(iter(participants))
    if participants:
        warnings.append(
            "could not tell which participant is you; all messages are shown as received. "
            "Use --me \"Your Name\" to fix this."
        )
    return None


def parse_file(path: Path, options: ParseOptions | None = None, title_source: str | None = None) -> Conversation:
    conv = parse_lines(read_lines(path), options, source_name=title_source or path.stem)
    conv.source = path
    return conv
