"""Structured, parser-independent representation of a WhatsApp conversation.

The renderer only ever sees these classes; it knows nothing about the
``.txt`` export format.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any


class Direction(str, Enum):
    INCOMING = "incoming"
    OUTGOING = "outgoing"
    SYSTEM = "system"


class MessageType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    GIF = "gif"
    AUDIO = "audio"          # music / generic audio file
    VOICE = "voice"          # push-to-talk voice note (PTT)
    DOCUMENT = "document"
    STICKER = "sticker"
    CONTACT = "contact"      # shared vCard
    LOCATION = "location"
    POLL = "poll"
    CALL = "call"            # missed/started voice or video call
    DELETED = "deleted"
    VIEW_ONCE = "view_once"  # view-once media, never exported
    SYSTEM = "system"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class Media:
    """An attachment referenced by a message.

    ``path`` is None when the file is not present in the export (either
    because WhatsApp omitted it or because it was deleted afterwards).
    The processing fields are filled lazily by :mod:`wa_export_pdf.media`.
    """

    filename: str
    path: Path | None = None
    omitted: bool = False            # export made "without media"
    mime: str | None = None
    size_bytes: int | None = None
    # Filled by media processing
    width: int | None = None         # display-oriented pixel size
    height: int | None = None
    duration: float | None = None    # seconds (audio/video)
    thumbnail: Path | None = None    # browser-friendly preview image
    has_alpha: bool = False
    waveform: list[float] | None = None   # 0..1 amplitudes (voice notes)
    page_count: int | None = None    # documents
    extension: str = ""
    contact_name: str | None = None  # vCard
    contact_phones: list[str] = field(default_factory=list)
    error: str | None = None         # processing failure (corrupted, ...)

    @property
    def exists(self) -> bool:
        return self.path is not None


@dataclass(slots=True)
class Reply:
    """Quoted message. Plain-text exports do not contain replies; the model
    supports them so other importers (or future export formats) can."""

    sender: str | None
    text: str
    message_id: str | None = None
    media_type: MessageType | None = None


@dataclass(slots=True)
class Reaction:
    emoji: str
    sender: str | None = None
    count: int = 1


@dataclass(slots=True)
class PollOption:
    text: str
    votes: int | None = None


@dataclass(slots=True)
class Poll:
    question: str
    options: list[PollOption] = field(default_factory=list)


@dataclass(slots=True)
class Location:
    latitude: float | None
    longitude: float | None
    url: str | None = None
    name: str | None = None


@dataclass(slots=True)
class Message:
    id: str
    timestamp: datetime
    sender: str | None
    direction: Direction
    type: MessageType
    text: str = ""
    media: Media | None = None
    reply: Reply | None = None
    reactions: list[Reaction] = field(default_factory=list)
    edited: bool = False
    poll: Poll | None = None
    location: Location | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    source_line: int | None = None

    @property
    def day(self) -> date:
        return self.timestamp.date()

    @property
    def is_system(self) -> bool:
        return self.direction is Direction.SYSTEM


@dataclass(slots=True)
class Participant:
    name: str
    is_me: bool = False
    color_index: int = 0
    message_count: int = 0


@dataclass(slots=True)
class Conversation:
    title: str
    messages: list[Message]
    participants: dict[str, Participant]
    is_group: bool
    locale: str = "en"
    uses_12h_clock: bool = False
    source: Path | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def me(self) -> Participant | None:
        return next((p for p in self.participants.values() if p.is_me), None)
