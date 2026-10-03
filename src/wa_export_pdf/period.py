"""Restrict a conversation to a start/end period (``--from`` / ``--to``).

The filter runs right after parsing, so media processing, rendering and all
counters only ever see the messages inside the period.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from .models import Conversation

_FORMAT_HINT = "YYYY-MM-DD, 'YYYY-MM-DD HH:MM' or 'YYYY-MM-DD HH:MM:SS'"
_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?$")


class PeriodError(ValueError):
    pass


@dataclass(frozen=True)
class Bound:
    """A ``--from``/``--to`` value; ``precision`` is what the user typed."""

    value: datetime
    precision: str          # "day" | "minute" | "second"

    def __str__(self) -> str:
        if self.precision == "day":
            return self.value.date().isoformat()
        if self.precision == "minute":
            return self.value.strftime("%Y-%m-%d %H:%M")
        return self.value.strftime("%Y-%m-%d %H:%M:%S")


def parse_bound(text: str) -> Bound:
    m = _PATTERN.match(text.strip())
    if not m:
        raise PeriodError(f"invalid date '{text}', expected {_FORMAT_HINT}")
    day_s, hour, minute, second = m.groups()
    try:
        day = date.fromisoformat(day_s)
        if hour is None:
            return Bound(datetime.combine(day, time()), "day")
        t = time(int(hour), int(minute), int(second or 0))
    except ValueError as exc:
        raise PeriodError(f"invalid date '{text}': {exc}") from exc
    return Bound(datetime.combine(day, t), "second" if second else "minute")


@dataclass(frozen=True)
class Period:
    """Inclusive period. A ``--to`` day or minute covers that whole day/minute."""

    start: Bound | None = None
    end: Bound | None = None

    def __post_init__(self) -> None:
        if self.start and self.end and self.start.value > self.end_limit:
            raise PeriodError(f"--from {self.start} is after --to {self.end}")

    @property
    def active(self) -> bool:
        return self.start is not None or self.end is not None

    @property
    def end_limit(self) -> datetime:
        """Last instant included by ``end`` (or datetime.max)."""
        if self.end is None:
            return datetime.max
        step = {"day": timedelta(days=1), "minute": timedelta(minutes=1), "second": timedelta(seconds=1)}
        return self.end.value + step[self.end.precision] - timedelta(microseconds=1)

    def contains(self, ts: datetime) -> bool:
        if self.start and ts < self.start.value:
            return False
        return ts <= self.end_limit

    def describe(self) -> str:
        return f"{self.start or '…'} → {self.end or '…'}"


def apply_period(conv: Conversation, period: Period) -> int:
    """Keep only the messages inside ``period``; returns how many were dropped.

    Raises :class:`PeriodError` when the period contains no message, naming
    the range the chat actually covers.
    """
    if not period.active:
        return 0
    total = len(conv.messages)
    kept = [m for m in conv.messages if period.contains(m.timestamp)]
    if not kept:
        first = conv.messages[0].timestamp if conv.messages else None
        last = conv.messages[-1].timestamp if conv.messages else None
        span = f" (the chat goes from {first:%Y-%m-%d %H:%M} to {last:%Y-%m-%d %H:%M})" if first and last else ""
        raise PeriodError(f"no messages between {period.describe()}{span}")
    conv.messages = kept
    for p in conv.participants.values():
        p.message_count = 0
    for m in kept:
        if m.sender in conv.participants:
            conv.participants[m.sender].message_count += 1
    return total - len(kept)
