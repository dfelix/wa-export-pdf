from __future__ import annotations

import re
from datetime import datetime
from wa_export_pdf.config import PAGE_SIZES, RenderOptions
from wa_export_pdf.emoji import emoji_only_count
from wa_export_pdf.models import (
    Conversation, Direction, Message, MessageType, Participant, Reaction, Reply,
)
from wa_export_pdf.parser import ParseOptions, parse_file, parse_lines
from wa_export_pdf.renderer import HtmlRenderer, format_text, load_theme
from wa_export_pdf.renderer.html import DayView, MessageView, fit_media, format_duration, format_size
from wa_export_pdf.renderer.theme import ThemeError, available_themes

from .conftest import SAMPLE


# -- text formatting ---------------------------------------------------------

def test_format_bold_italic_strike_mono():
    html = str(format_text("*negrito* _itálico_ ~riscado~ ```código *x*```"))
    assert "<strong>negrito</strong>" in html
    assert "<em>itálico</em>" in html
    assert "<del>riscado</del>" in html
    assert '<code class="mono">código *x*</code>' in html


def test_format_does_not_touch_inner_words():
    html = str(format_text("snake_case_name e 2*3*4 e file_name.txt"))
    assert "<em>" not in html and "<strong>" not in html


def test_html_is_escaped():
    html = str(format_text('<script>alert("x")</script> & <b>'))
    assert "<script>" not in html and "&lt;script&gt;" in html and "&amp;" in html


def test_links_are_clickable_and_underscores_preserved():
    html = str(format_text("vê https://example.com/a_b_c?x=1&y=2. e www.site.pt"))
    assert '<a href="https://example.com/a_b_c?x=1&amp;y=2">' in html
    assert "</a>." in html            # trailing dot is not part of the link
    assert '<a href="http://www.site.pt">' in html
    assert "<em>" not in html


def test_emoji_wrapped():
    html = str(format_text("olá 👍🏽 👨‍👩‍👧 🇵🇹 1️⃣"))
    assert html.count('class="emoji"') == 4
    assert '<span class="emoji">👨‍👩‍👧</span>' in html


def test_quote_and_lists():
    html = str(format_text("> citação\n- um\n* dois\n1. três"))
    assert 'class="wa-quote"' in html
    assert html.count('class="wa-li"') == 3


def test_jumbo_emoji_detection():
    assert emoji_only_count("😂") == 1
    assert emoji_only_count(" 🎉🎂🥳 ") == 3
    assert emoji_only_count("🎉🎂🥳😂") == 0
    assert emoji_only_count("ok 😂") == 0
    assert emoji_only_count("©") == 0


# -- helpers -----------------------------------------------------------------

def test_format_helpers():
    assert format_duration(37.4) == "0:37"
    assert format_duration(3725) == "1:02:05"
    assert format_duration(None) == ""
    assert format_size(2_400_000) == "2.4 MB"
    assert format_size(999) == "999 B"


def test_fit_media_limits():
    page = PAGE_SIZES["a4"]
    box = fit_media(4000, 3000, page)
    assert box.width == page.media_w and box.height < page.media_h
    tall = fit_media(500, 5000, page)
    assert tall.height == page.media_h and tall.width == page.media_min_w and tall.crop
    assert fit_media(None, None, page).width == page.media_w


def test_themes_load():
    assert {"whatsapp", "whatsapp-dark"} <= set(available_themes())
    dark = load_theme("whatsapp-dark")
    assert dark.dark
    names = [p.name for p in dark.stylesheets]
    assert names[0] == "variables.css" and names[-1] == "variables.css"   # override loaded last
    try:
        load_theme("nope")
    except ThemeError:
        pass
    else:
        raise AssertionError("unknown theme must fail")


# -- view model ----------------------------------------------------------------

def _conv(messages, group=False):
    names = {m.sender for m in messages if m.sender}
    parts = {n: Participant(n, is_me=(n == "Eu"), color_index=i) for i, n in enumerate(sorted(names))}
    return Conversation(title="Teste", messages=messages, participants=parts, is_group=group, locale="pt")


def _msg(i, sender, minute, day=15, text="x", t=MessageType.TEXT, **kw):
    direction = Direction.SYSTEM if sender is None else (Direction.OUTGOING if sender == "Eu" else Direction.INCOMING)
    return Message(
        id=f"m{i}", timestamp=datetime(2026, 9, day, 10, minute), sender=sender,
        direction=direction, type=t if sender else MessageType.SYSTEM, text=text, **kw,
    )


def test_grouping_and_date_separators():
    msgs = [
        _msg(1, "Ana", 0), _msg(2, "Ana", 1), _msg(3, "Eu", 2), _msg(4, "Eu", 3),
        _msg(5, None, 4, text="Ana adicionou Bob"), _msg(6, "Ana", 5),
        _msg(7, "Ana", 0, day=16),
    ]
    r = HtmlRenderer(_conv(msgs), load_theme("whatsapp"), RenderOptions())
    items = r.build_items()
    kinds = [type(i).__name__ for i in items]
    assert kinds == ["DayView", "MessageView", "MessageView", "MessageView", "MessageView",
                     "SystemView", "MessageView", "DayView", "MessageView"]
    views = [i for i in items if isinstance(i, MessageView)]
    assert [(v.first, v.last) for v in views] == [
        (True, False), (False, True), (True, False), (False, True), (True, True), (True, True)
    ]
    assert views[0].side == "in" and views[2].side == "out"
    day = items[0]
    assert isinstance(day, DayView) and day.label == "15 de setembro de 2026"


def test_names_only_in_groups():
    msgs = [_msg(1, "Ana", 0), _msg(2, "Bob", 1), _msg(3, "Eu", 2)]
    r = HtmlRenderer(_conv(msgs, group=True), load_theme("whatsapp"), RenderOptions())
    views = [i for i in r.build_items() if isinstance(i, MessageView)]
    assert views[0].show_name and views[1].show_name and not views[2].show_name
    r = HtmlRenderer(_conv(msgs[:1] + msgs[2:]), load_theme("whatsapp"), RenderOptions())
    assert not any(v.show_name for v in r.build_items() if isinstance(v, MessageView))


def test_reply_and_reactions_rendered_when_present():
    m = _msg(1, "Ana", 0, text="Sim, concordo.")
    m.reply = Reply(sender="Eu", text="Isto é a mensagem original")
    m.reactions = [Reaction("❤️", "Eu"), Reaction("😂", "Bob")]
    html = HtmlRenderer(_conv([m, _msg(2, "Eu", 1)]), load_theme("whatsapp"), RenderOptions()).render_chunk(
        HtmlRenderer(_conv([m, _msg(2, "Eu", 1)]), load_theme("whatsapp"), RenderOptions()).chunks()[0], 1
    )
    assert 'class="quote' in html and "Isto é a mensagem original" in html
    assert 'class="reactions"' in html and "❤️" in html


def test_no_invented_reactions_or_ticks():
    html = _render_sample()
    assert 'class="reactions"' not in html
    assert 'class="ticks"' not in html


def test_ticks_are_opt_in():
    html = _render_sample(RenderOptions(ticks=True))
    assert 'class="ticks"' in html


def test_chunks_split_on_day_boundaries():
    msgs = [_msg(i, "Ana" if i % 2 else "Eu", i % 50, day=1 + i // 60) for i in range(600)]
    r = HtmlRenderer(_conv(msgs), load_theme("whatsapp"), RenderOptions(chunk_size=100))
    chunks = r.chunks()
    assert len(chunks) > 1
    assert sum(c.message_count for c in chunks) == 600
    for c in chunks:
        assert isinstance(c.items[0], DayView)


def _render_sample(options: RenderOptions | None = None) -> str:
    conv = parse_file(SAMPLE / "chat.txt", ParseOptions(me="Rui Costa"))
    from wa_export_pdf.media import MediaIndex, resolve_media

    resolve_media(conv, MediaIndex(SAMPLE))
    r = HtmlRenderer(conv, load_theme("whatsapp"), options or RenderOptions())
    return r.render_chunk(r.chunks()[0], 1)


def test_sample_html_structure():
    html = _render_sample()
    assert html.startswith("<!doctype html>")
    assert 'class="date-chip">14 de setembro de 2026<' in html
    assert 'class="system-chip e2e"' in html
    assert html.count('class="row ') == 32
    assert "Editada" in html
    assert 'class="bubble document-bubble' in html
    assert 'class="bubble voice-bubble' in html
    assert 'class="bubble contact-bubble' in html
    assert 'class="bubble poll-bubble' in html
    assert 'class="bubble location-bubble' in html
    assert "IMG-20260917-WA0008.jpg" in html and "Ficheiro não incluído na exportação" in html
    # no remote resources: everything is file:// or data:
    for url in re.findall(r'(?:src|href)="([^"]+)"', html):
        assert url.startswith(("file:", "data:", "http://www.", "https://www.example", "https://maps.")), url
    assert "@page{size:210mm 297mm" in html


def test_phone_page_size_and_dark_theme():
    conv = parse_lines(["15/09/26, 10:00 - Ana: olá"], ParseOptions())
    r = HtmlRenderer(conv, load_theme("whatsapp-dark"), RenderOptions(page_size="phone"))
    html = r.render_chunk(r.chunks()[0], 1)
    assert "@page{size:412px 915px" in html
    assert "whatsapp-dark/variables.css" in html
    header = r.header_template()
    assert "appbar" in header


def test_header_template_is_self_contained():
    conv = parse_lines(["15/09/26, 10:00 - Ana: olá"], ParseOptions(), source_name="Conversa no WhatsApp com Ana")
    r = HtmlRenderer(conv, load_theme("whatsapp"), RenderOptions())
    header = r.header_template()
    assert "file:" not in header                    # header templates cannot load files
    assert "data:font/ttf;base64," in header
    assert ">Ana<" in header
    assert 'class="appbar"' not in HtmlRenderer(conv, load_theme("whatsapp"), RenderOptions(header=False)).header_template()
