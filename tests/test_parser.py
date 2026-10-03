from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from wa_export_pdf.models import Direction, MessageType
from wa_export_pdf.parser import ParseOptions, find_chat_file, locate_export, parse_file, parse_lines
from wa_export_pdf.parser.formats import title_from_filename

from .conftest import SAMPLE

LRM = "‎"


def test_simple_message(lines):
    conv = parse_lines(lines("15/09/26, 10:32 - João: Olá! Tudo bem?"))
    assert len(conv.messages) == 1
    m = conv.messages[0]
    assert m.timestamp == datetime(2026, 9, 15, 10, 32)
    assert m.sender == "João"
    assert m.text == "Olá! Tudo bem?"
    assert m.type is MessageType.TEXT


def test_multiline_message(lines):
    conv = parse_lines(lines("""
15/09/26, 10:32 - Ana: primeira linha
segunda linha

quarta linha
15/09/26, 10:33 - João: ok
"""))
    assert [m.text for m in conv.messages] == ["primeira linha\nsegunda linha\n\nquarta linha", "ok"]


def test_unicode_and_emoji(lines):
    text = "Ção 😀👍🏽👨‍👩‍👧 🇵🇹 مرحبا 你好 こんにちは Привет"
    conv = parse_lines(lines(f"01/02/26, 08:00 - José Ñúñez: {text}"))
    assert conv.messages[0].text == text
    assert conv.messages[0].sender == "José Ñúñez"


def test_names_with_accents_and_colons_in_text(lines):
    conv = parse_lines(lines("01/02/26, 08:00 - Inês Gonçalves: horário: 10:30 às 12:00"))
    m = conv.messages[0]
    assert m.sender == "Inês Gonçalves"
    assert m.text == "horário: 10:30 às 12:00"


@pytest.mark.parametrize(
    "line, expected",
    [
        ("15/09/2026, 10:32 - A: x", datetime(2026, 9, 15, 10, 32)),
        ("15.09.26, 10:32 - A: x", datetime(2026, 9, 15, 10, 32)),
        ("2026-09-15 10:32 - A: x", datetime(2026, 9, 15, 10, 32)),
        ("9/15/26, 10:32 PM - A: x", datetime(2026, 9, 15, 22, 32)),
        ("9/15/26, 12:05 AM - A: x", datetime(2026, 9, 15, 0, 5)),
        ("[15/09/26, 10:32:45] A: x", datetime(2026, 9, 15, 10, 32, 45)),
        ("[9/15/26, 3:04:05 p.m.] A: x", datetime(2026, 9, 15, 15, 4, 5)),
    ],
)
def test_timestamp_formats(lines, line, expected):
    conv = parse_lines(lines(line))
    assert conv.messages[0].timestamp == expected


def test_ambiguous_dates_use_chronology(lines):
    # All days <= 12: month/day order is decided by monotonic time.
    conv = parse_lines(lines("""
1/2/26, 10:00 - A: a
1/3/26, 10:00 - B: b
1/4/26, 10:00 - A: c
"""))
    days = [m.timestamp.date().isoformat() for m in conv.messages]
    assert days == ["2026-02-01", "2026-03-01", "2026-04-01"]

    conv = parse_lines(lines("""
2/1/26, 10:00 - A: a
3/1/26, 10:00 - B: b
12/1/26, 10:00 - A: c
"""), ParseOptions(date_order="mdy"))
    assert conv.messages[2].timestamp.month == 12


def test_us_format_detected_from_day_over_12(lines):
    conv = parse_lines(lines("""
9/15/26, 10:00 AM - A: a
9/16/26, 10:00 AM - B: b
"""))
    assert conv.messages[0].timestamp.day == 15


def test_system_messages(lines):
    conv = parse_lines(lines("""
15/09/26, 09:00 - As mensagens e as chamadas são encriptadas ponto a ponto. Só as pessoas nesta conversa as podem ler.
15/09/26, 09:01 - Ana criou o grupo "Férias: 2026"
15/09/26, 09:02 - Ana adicionou João
15/09/26, 09:03 - Ana: olá
15/09/26, 09:04 - João saiu
"""))
    kinds = [m.type for m in conv.messages]
    assert kinds == [MessageType.SYSTEM, MessageType.SYSTEM, MessageType.SYSTEM, MessageType.TEXT, MessageType.SYSTEM]
    assert conv.messages[1].text == 'Ana criou o grupo "Férias: 2026"'
    assert all(m.direction is Direction.SYSTEM for m in conv.messages if m.type is MessageType.SYSTEM)


def test_ios_group_name_pseudo_sender(lines):
    conv = parse_lines(lines(f"""
[15/09/26, 09:00:00] Viagem: {LRM}Messages and calls are end-to-end encrypted.
[15/09/26, 09:00:01] Viagem: {LRM}Ana created group "Viagem"
[15/09/26, 09:00:05] Ana: Hello
[15/09/26, 09:01:00] Bob: {LRM}<attached: 00000003-PHOTO-2026-09-15-09-01-00.jpg>
"""))
    types = [m.type for m in conv.messages]
    assert types[:2] == [MessageType.SYSTEM, MessageType.SYSTEM]
    assert types[2] is MessageType.TEXT
    assert types[3] is MessageType.IMAGE
    assert conv.messages[3].media.filename == "00000003-PHOTO-2026-09-15-09-01-00.jpg"
    assert "Viagem" not in conv.participants


def test_attachments_android(lines):
    conv = parse_lines(lines(f"""
15/09/26, 10:00 - A: {LRM}IMG-20260915-WA0001.jpg (ficheiro anexado)
legenda da foto
15/09/26, 10:01 - A: {LRM}VID-20260915-WA0002.mp4 (ficheiro anexado)
15/09/26, 10:02 - A: {LRM}PTT-20260915-WA0003.opus (ficheiro anexado)
15/09/26, 10:03 - A: {LRM}AUD-20260915-WA0004.m4a (ficheiro anexado)
15/09/26, 10:04 - A: {LRM}STK-20260915-WA0005.webp (ficheiro anexado)
15/09/26, 10:05 - A: {LRM}Relatório final.pdf (ficheiro anexado)
Relatório final.pdf
15/09/26, 10:06 - A: {LRM}Maria.vcf (ficheiro anexado)
15/09/26, 10:07 - A: IMG-20260915-WA0006.jpg (file attached)
15/09/26, 10:08 - A: DOC-20260915-WA0007. (arquivo anexado)
"""))
    m = conv.messages
    assert [x.type for x in m] == [
        MessageType.IMAGE, MessageType.VIDEO, MessageType.VOICE, MessageType.AUDIO,
        MessageType.STICKER, MessageType.DOCUMENT, MessageType.CONTACT, MessageType.IMAGE,
        MessageType.DOCUMENT,
    ]
    assert m[0].media.filename == "IMG-20260915-WA0001.jpg"
    assert m[0].text == "legenda da foto"
    assert m[5].media.filename == "Relatório final.pdf"
    assert m[5].text == ""  # document name line is not a caption
    assert m[5].metadata["document_title"] == "Relatório final.pdf"


def test_media_omitted_deleted_edited_view_once(lines):
    conv = parse_lines(lines("""
15/09/26, 10:00 - A: <Multimédia omitido>
15/09/26, 10:01 - A: Esta mensagem foi eliminada
15/09/26, 10:02 - B: You deleted this message
15/09/26, 10:03 - B: corrigido <Esta mensagem foi editada>
15/09/26, 10:04 - A: <Ficheiro não revelado>
15/09/26, 10:05 - A: <algo novo do whatsapp>
"""))
    m = conv.messages
    assert m[0].media.omitted
    assert m[1].type is MessageType.DELETED and m[2].type is MessageType.DELETED
    assert m[3].type is MessageType.TEXT and m[3].edited and m[3].text == "corrigido"
    assert m[4].type is MessageType.VIEW_ONCE
    assert m[5].type is MessageType.UNKNOWN


def test_location_and_poll(lines):
    conv = parse_lines(lines("""
15/09/26, 10:00 - A: localização: https://maps.google.com/?q=38.7223,-9.1393
15/09/26, 10:01 - A: POLL:
Where?
OPTION: Beach (3 votes)
OPTION: Mountain (1 vote)
"""))
    loc = conv.messages[0]
    assert loc.type is MessageType.LOCATION
    assert loc.location.latitude == pytest.approx(38.7223)
    poll = conv.messages[1]
    assert poll.type is MessageType.POLL
    assert poll.poll.question == "Where?"
    assert [(o.text, o.votes) for o in poll.poll.options] == [("Beach", 3), ("Mountain", 1)]


def test_malformed_lines_do_not_break_parse(lines):
    conv = parse_lines(lines("""
garbage before the first message
15/09/26, 10:00 - A: ok
99/99/26, 10:01 - B: impossible date
15/09/26, 10:02 - B: still fine
"""))
    texts = [m.text for m in conv.messages]
    assert texts[0].startswith("ok")
    assert texts[-1] == "still fine"
    assert conv.warnings


def test_empty_input_raises():
    with pytest.raises(ValueError):
        parse_lines(["not a chat", "at all"])


def test_me_detection_from_title(lines):
    conv = parse_lines(
        lines("15/09/26, 10:00 - Ana: a\n15/09/26, 10:01 - Rui: b"),
        source_name="Conversa no WhatsApp com Ana",
    )
    assert conv.title == "Ana"
    assert conv.me.name == "Rui"
    assert conv.messages[1].direction is Direction.OUTGOING
    assert conv.messages[0].direction is Direction.INCOMING
    assert not conv.is_group


def test_me_option_and_groups(lines):
    conv = parse_lines(
        lines("15/09/26, 10:00 - Ana: a\n15/09/26, 10:01 - Rui: b\n15/09/26, 10:02 - Zé: c"),
        ParseOptions(me="rui"),
    )
    assert conv.is_group
    assert conv.me.name == "Rui"


def test_locale_detection(lines):
    conv = parse_lines(lines("15/09/26, 10:00 - A: IMG-1.jpg (ficheiro anexado)"))
    assert conv.locale == "pt"
    conv = parse_lines(lines("9/15/26, 10:00 AM - A: <Media omitted>"))
    assert conv.locale == "en"


def test_title_prefixes():
    assert title_from_filename("Conversa no WhatsApp com Ana Franco") == "Ana Franco"
    assert title_from_filename("WhatsApp Chat with Bob") == "Bob"
    assert title_from_filename("Chat de WhatsApp con Lucía") == "Lucía"
    assert title_from_filename("random") is None


def test_sample_fixture_parses():
    chat = find_chat_file(SAMPLE)
    conv = parse_file(chat, ParseOptions(me="Rui Costa"))
    types = {m.type for m in conv.messages}
    assert {MessageType.IMAGE, MessageType.VIDEO, MessageType.VOICE, MessageType.DOCUMENT,
            MessageType.STICKER, MessageType.GIF, MessageType.CONTACT, MessageType.LOCATION,
            MessageType.POLL, MessageType.DELETED, MessageType.VIEW_ONCE, MessageType.SYSTEM} <= types
    assert conv.messages == sorted(conv.messages, key=lambda m: m.timestamp)


def test_locate_zip_export(tmp_path: Path):
    import zipfile

    archive = tmp_path / "WhatsApp Chat with Joana.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.write(SAMPLE / "chat.txt", "_chat.txt")
        z.write(SAMPLE / "image.jpg", "image.jpg")
    loc = locate_export(archive, tmp_path / "work")
    assert loc.chat_file.name == "_chat.txt"
    assert (loc.media_root / "image.jpg").is_file()
    assert loc.title_source == "WhatsApp Chat with Joana"


def test_encodings(tmp_path: Path):
    p = tmp_path / "chat.txt"
    p.write_text("15/09/26, 10:00 - Zé: Olá ação", encoding="utf-16")
    conv = parse_file(p)
    assert conv.messages[0].text == "Olá ação"
    p.write_bytes("15/09/26, 10:00 - Zé: Olá ação".encode("cp1252"))
    conv = parse_file(p)
    assert conv.messages[0].text == "Olá ação"


def test_crlf_and_bom(tmp_path: Path):
    p = tmp_path / "chat.txt"
    p.write_bytes("﻿15/09/26, 10:00 - Zé: linha 1\r\nlinha 2\r\n15/09/26, 10:01 - Ana: ok\r\n".encode("utf-8"))
    conv = parse_file(p)
    assert [m.text for m in conv.messages] == ["linha 1\nlinha 2", "ok"]
    assert conv.messages[0].sender == "Zé"
