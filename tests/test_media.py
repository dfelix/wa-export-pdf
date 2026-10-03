from __future__ import annotations

from array import array
from pathlib import Path

import pytest

from wa_export_pdf.media import MediaCache, MediaIndex, MediaSettings, QUALITY_PRESETS, find_ffmpeg, process_media, resolve_media
from wa_export_pdf.media.audio import compute_waveform
from wa_export_pdf.media.containers import mp4_duration, ogg_duration
from wa_export_pdf.media.documents import parse_vcard, pdf_page_count
from wa_export_pdf.media.images import process_image
from wa_export_pdf.media.types import classify_filename, sniff
from wa_export_pdf.models import Media, MessageType
from wa_export_pdf.parser import ParseOptions, parse_file

from .conftest import SAMPLE

FFMPEG = find_ffmpeg(None)
requires_ffmpeg = pytest.mark.skipif(FFMPEG is None, reason="FFmpeg not available")


@pytest.mark.parametrize(
    "name, kind",
    [
        ("IMG-20260101-WA0001.jpg", MessageType.IMAGE),
        ("image.jpeg", MessageType.IMAGE),
        ("photo.PNG", MessageType.IMAGE),
        ("IMG-20260101-WA0002.webp", MessageType.IMAGE),
        ("STK-20260101-WA0003.webp", MessageType.STICKER),
        ("VID-20260101-WA0004.mp4", MessageType.VIDEO),
        ("PTT-20260101-WA0005.opus", MessageType.VOICE),
        ("AUD-20260101-WA0006.opus", MessageType.AUDIO),
        ("AUD-20260101-WA0007.m4a", MessageType.AUDIO),
        ("00000012-PHOTO-2026-01-01-10-00-00.jpg", MessageType.IMAGE),
        ("00000013-AUDIO-2026-01-01-10-00-00.opus", MessageType.VOICE),
        ("00000014-GIF-2026-01-01-10-00-00.mp4", MessageType.GIF),
        ("00000015-STICKER-2026-01-01-10-00-00.webp", MessageType.STICKER),
        ("anim.gif", MessageType.GIF),
        ("contact.vcf", MessageType.CONTACT),
        ("report.pdf", MessageType.DOCUMENT),
        ("weird.xyz", MessageType.DOCUMENT),
    ],
)
def test_classify_filename(name, kind):
    assert classify_filename(name) is kind


def test_sniff_magic_bytes():
    assert sniff(SAMPLE / "document.pdf")[0] == "pdf"
    assert sniff(SAMPLE / "image.jpg")[0] == "jpg"
    assert sniff(SAMPLE / "IMG-20260916-WA0004.png")[0] == "png"
    assert sniff(SAMPLE / "STK-20260917-WA0006.webp")[0] == "webp"
    assert sniff(SAMPLE / "audio.opus")[0] == "ogg"
    assert sniff(SAMPLE / "video.mp4")[0] == "mp4"
    assert sniff(SAMPLE / "chat.txt") is None


def test_index_is_case_and_normalisation_insensitive(tmp_path: Path):
    import unicodedata

    nfd = unicodedata.normalize("NFD", "Relatório.PDF")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / nfd).write_bytes(b"%PDF-1.4")
    index = MediaIndex(tmp_path)
    assert index.find("relatório.pdf") is not None
    assert index.find("missing.pdf") is None


def _image_media(tmp_path: Path, name: str) -> tuple[Media, MediaCache]:
    return Media(filename=name, path=SAMPLE / name), MediaCache(tmp_path / "cache")


def test_jpeg_thumbnail(tmp_path: Path):
    media, cache = _image_media(tmp_path, "image.jpg")
    process_image(media, cache, 640, 80)
    assert media.error is None
    assert (media.width, media.height) == (1600, 1000)
    assert media.thumbnail.is_file() and media.thumbnail.suffix == ".jpg"
    from PIL import Image

    with Image.open(media.thumbnail) as im:
        assert max(im.size) <= 640


def test_exif_orientation_is_applied(tmp_path: Path):
    media, cache = _image_media(tmp_path, "IMG-20260916-WA0003.jpg")
    process_image(media, cache, 2000, 80)
    # Stored 800x1200 with orientation 6 -> displayed 1200x800 (landscape).
    assert (media.width, media.height) == (1200, 800)
    from PIL import Image

    with Image.open(media.thumbnail) as im:
        assert im.width > im.height


def test_png_and_webp(tmp_path: Path):
    media, cache = _image_media(tmp_path, "IMG-20260916-WA0004.png")
    process_image(media, cache, 640, 80)
    assert media.error is None and media.width == 800
    media, cache = _image_media(tmp_path, "IMG-20260916-WA0005.webp")
    process_image(media, cache, 640, 80)
    assert media.error is None and media.width == 1000


def test_sticker_keeps_transparency(tmp_path: Path):
    media, cache = _image_media(tmp_path, "STK-20260917-WA0006.webp")
    process_image(media, cache, 380, 80)
    assert media.has_alpha
    assert media.thumbnail.suffix == ".png"


def test_corrupted_image_is_reported_not_raised(tmp_path: Path):
    media, cache = _image_media(tmp_path, "IMG-20260917-WA0009.jpg")
    process_image(media, cache, 640, 80)
    assert media.error == "unreadable"
    assert media.thumbnail is None


def test_huge_image_is_downscaled(tmp_path: Path):
    from PIL import Image

    big = tmp_path / "huge.jpg"
    Image.new("RGB", (9000, 6000), (10, 120, 200)).save(big, quality=60)
    media = Media(filename="huge.jpg", path=big)
    process_image(media, MediaCache(tmp_path / "c"), 1100, 80)
    with Image.open(media.thumbnail) as im:
        assert max(im.size) <= 1100
    assert (media.width, media.height) == (9000, 6000)


def test_cache_reuse(tmp_path: Path):
    media, cache = _image_media(tmp_path, "image.jpg")
    process_image(media, cache, 640, 80)
    first = media.thumbnail
    mtime = first.stat().st_mtime_ns
    media2 = Media(filename="image.jpg", path=SAMPLE / "image.jpg")
    process_image(media2, cache, 640, 80)
    assert media2.thumbnail == first and first.stat().st_mtime_ns == mtime


def test_container_durations():
    assert ogg_duration(SAMPLE / "audio.opus") == pytest.approx(7.0, abs=0.1)
    assert mp4_duration(SAMPLE / "video.mp4") == pytest.approx(3.0, abs=0.15)
    assert mp4_duration(SAMPLE / "AUD-20260918-WA0012.m4a") == pytest.approx(4.0, abs=0.15)
    assert ogg_duration(SAMPLE / "image.jpg") is None


def test_waveform_shape():
    samples = array("h", [0] * 100 + [1000] * 100 + [30000] * 100 + [0] * 100)
    wf = compute_waveform(samples, bars=4)
    assert len(wf) == 4
    assert wf[2] == 1.0 and wf[0] == 0.0 and 0 < wf[1] < 1


def test_pdf_page_count_and_vcard():
    assert pdf_page_count(SAMPLE / "document.pdf") == 3
    name, phones = parse_vcard(SAMPLE / "Marta Ferreira.vcf")
    assert name == "Marta Ferreira"
    assert phones == ["+351 910 000 000"]


def _sample_conversation(ffmpeg=None):
    conv = parse_file(SAMPLE / "chat.txt", ParseOptions(me="Rui Costa"))
    stats = resolve_media(conv, MediaIndex(SAMPLE, exclude={SAMPLE / "chat.txt"}))
    return conv, stats


def test_resolve_reports_missing_files():
    conv, stats = _sample_conversation()
    assert stats["missing"] == 1
    missing = [m for m in conv.messages if m.media and not m.media.exists]
    assert missing[0].media.filename == "IMG-20260917-WA0008.jpg"


def test_process_without_ffmpeg(tmp_path: Path):
    conv, _ = _sample_conversation()
    settings = MediaSettings(quality=QUALITY_PRESETS["low"], ffmpeg=None, pdf_previews=False, jobs=2)
    stats = process_media(conv, MediaCache(tmp_path / "cache"), settings)
    assert stats["processed"] == 14
    video = next(m for m in conv.messages if m.media and m.media.filename == "video.mp4")
    assert video.media.thumbnail is None
    assert video.media.duration == pytest.approx(3.0, abs=0.15)   # pure-python fallback
    voice = next(m for m in conv.messages if m.type is MessageType.VOICE)
    assert voice.media.duration == pytest.approx(7.0, abs=0.1)
    assert voice.media.waveform is None
    gif = next(m for m in conv.messages if m.type is MessageType.GIF)
    assert gif.media.thumbnail is not None                         # Pillow handles .gif


@requires_ffmpeg
def test_video_frame_and_voice_waveform(tmp_path: Path):
    conv, _ = _sample_conversation()
    settings = MediaSettings(quality=QUALITY_PRESETS["low"], ffmpeg=FFMPEG, jobs=2)
    process_media(conv, MediaCache(tmp_path / "cache"), settings)
    video = next(m for m in conv.messages if m.media and m.media.filename == "video.mp4")
    assert video.media.thumbnail and video.media.thumbnail.is_file()
    assert (video.media.width, video.media.height) == (480, 270)
    portrait = next(m for m in conv.messages if m.media and m.media.filename.startswith("VID-"))
    assert portrait.media.height > portrait.media.width
    voice = next(m for m in conv.messages if m.type is MessageType.VOICE)
    assert voice.media.waveform and len(voice.media.waveform) == 44
    assert max(voice.media.waveform) == 1.0


def test_unknown_file_is_document(tmp_path: Path, lines):
    from wa_export_pdf.parser import parse_lines

    (tmp_path / "data.xyz").write_bytes(b"\x00\x01binary")
    conv = parse_lines(lines("15/09/26, 10:00 - A: data.xyz (ficheiro anexado)"))
    resolve_media(conv, MediaIndex(tmp_path))
    m = conv.messages[0]
    assert m.type is MessageType.DOCUMENT and m.media.exists and m.media.size_bytes == 8
