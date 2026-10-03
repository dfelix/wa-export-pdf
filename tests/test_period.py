from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from wa_export_pdf.cli import main
from wa_export_pdf.parser import ParseOptions, parse_lines
from wa_export_pdf.period import Period, PeriodError, apply_period, parse_bound
from wa_export_pdf.pipeline import ConvertOptions, convert


@pytest.mark.parametrize(
    "text, value, precision",
    [
        ("2026-09-15", datetime(2026, 9, 15), "day"),
        ("2026-09-15 18:05", datetime(2026, 9, 15, 18, 5), "minute"),
        ("2026-09-15T08:05:30", datetime(2026, 9, 15, 8, 5, 30), "second"),
        (" 2026-09-15 9:05 ", datetime(2026, 9, 15, 9, 5), "minute"),
    ],
)
def test_parse_bound(text, value, precision):
    b = parse_bound(text)
    assert (b.value, b.precision) == (value, precision)


@pytest.mark.parametrize("text", ["15/09/2026", "2026-13-01", "2026-09-15 25:00", "2026-09-15 10", "yesterday"])
def test_parse_bound_rejects(text):
    with pytest.raises(PeriodError):
        parse_bound(text)


def test_end_bound_covers_whole_day_minute_second():
    day = Period(end=parse_bound("2026-09-15"))
    assert day.contains(datetime(2026, 9, 15, 23, 59, 59))
    assert not day.contains(datetime(2026, 9, 16, 0, 0))
    minute = Period(end=parse_bound("2026-09-15 18:05"))
    assert minute.contains(datetime(2026, 9, 15, 18, 5, 59))
    assert not minute.contains(datetime(2026, 9, 15, 18, 6))
    second = Period(end=parse_bound("2026-09-15 18:05:10"))
    assert second.contains(datetime(2026, 9, 15, 18, 5, 10))
    assert not second.contains(datetime(2026, 9, 15, 18, 5, 11))


def test_start_after_end_is_rejected():
    with pytest.raises(PeriodError, match="after"):
        Period(parse_bound("2026-09-16"), parse_bound("2026-09-15"))
    # Same day as start and end is fine (the whole day).
    Period(parse_bound("2026-09-15 10:00"), parse_bound("2026-09-15"))


def _conv(lines):
    return parse_lines(lines("""
14/09/26, 23:59 - Ana: antes
15/09/26, 00:00 - Rui: meia-noite
15/09/26, 18:05 - Ana: fim de tarde
16/09/26, 09:00 - Rui: depois
16/09/26, 09:01 - Rui: ainda depois
"""), ParseOptions(me="Rui"))


def test_apply_period_filters_and_recounts(lines):
    conv = _conv(lines)
    dropped = apply_period(conv, Period(parse_bound("2026-09-15"), parse_bound("2026-09-15")))
    assert dropped == 3
    assert [m.text for m in conv.messages] == ["meia-noite", "fim de tarde"]
    assert conv.participants["Ana"].message_count == 1
    assert conv.participants["Rui"].message_count == 1


def test_apply_period_with_times_and_open_ends(lines):
    conv = _conv(lines)
    apply_period(conv, Period(start=parse_bound("2026-09-15 18:05")))
    assert [m.text for m in conv.messages] == ["fim de tarde", "depois", "ainda depois"]
    conv = _conv(lines)
    apply_period(conv, Period(end=parse_bound("2026-09-15 00:00")))
    assert [m.text for m in conv.messages] == ["antes", "meia-noite"]


def test_inactive_period_keeps_everything(lines):
    conv = _conv(lines)
    assert apply_period(conv, Period()) == 0 and len(conv.messages) == 5


def test_empty_period_names_the_chat_range(lines):
    conv = _conv(lines)
    with pytest.raises(PeriodError, match="2026-09-14 23:59 to 2026-09-16 09:01"):
        apply_period(conv, Period(parse_bound("2027-01-01")))


def test_media_outside_period_is_not_processed(sample_dir: Path, tmp_path: Path):
    # Only 16/09: four photos/videos/voice + one audio file in the sample.
    opts = ConvertOptions(
        parse=ParseOptions(me="Rui Costa"),
        period=Period(parse_bound("2026-09-16"), parse_bound("2026-09-16")),
        debug_dir=tmp_path / "debug",
        html_only=True,
    )
    result = convert(sample_dir, None, opts)
    assert result.messages == 7
    assert result.media["found"] == 7 and result.media["missing"] == 0
    assert result.media["processed"] == 7
    html = result.html_files[0].read_text("utf-8")
    assert "16 de setembro de 2026" in html
    assert "15 de setembro de 2026" not in html and "17 de setembro de 2026" not in html


def test_cli_rejects_bad_periods(sample_dir: Path, tmp_path: Path, capsys):
    out = str(tmp_path / "x.pdf")
    with pytest.raises(SystemExit) as exc:
        main([str(sample_dir), out, "--from", "2026-09-16", "--to", "2026-09-15"])
    assert exc.value.code == 2
    assert "after" in capsys.readouterr().err
    with pytest.raises(SystemExit) as exc:
        main([str(sample_dir), out, "--from", "16/09/2026"])
    assert exc.value.code == 2
    assert main([str(sample_dir), out, "--from", "2030-01-01", "--me", "Rui Costa", "-q"]) == 1
    assert "no messages between" in capsys.readouterr().err
    assert not Path(out).exists()
