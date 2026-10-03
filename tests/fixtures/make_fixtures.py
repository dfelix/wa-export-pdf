"""Regenerate the binary files of the test fixtures (all data is fictitious).

    python tests/fixtures/make_fixtures.py

Images, the PDF, the sticker and the GIF are produced with Pillow. The video
and audio files need FFmpeg (found like the application finds it); they are
committed so the test-suite itself does not need FFmpeg to run.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
SAMPLE = HERE / "sample_backup"
sys.path.insert(0, str(HERE.parent.parent / "src"))


def gradient(w: int, h: int, top: tuple, bottom: tuple) -> Image.Image:
    im = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(im)
    for y in range(h):
        t = y / max(1, h - 1)
        color = tuple(round(a + (b - a) * t) for a, b in zip(top, bottom))
        draw.line([(0, y), (w, y)], fill=color)
    return im


def landscape(w: int, h: int) -> Image.Image:
    im = gradient(w, h, (120, 180, 235), (250, 215, 160))
    d = ImageDraw.Draw(im)
    d.ellipse([w * 0.68, h * 0.12, w * 0.82, h * 0.12 + w * 0.14], fill=(255, 236, 140))
    d.polygon([(0, h), (w * 0.3, h * 0.45), (w * 0.55, h), ], fill=(70, 110, 90))
    d.polygon([(w * 0.35, h), (w * 0.7, h * 0.35), (w, h * 0.8), (w, h)], fill=(50, 90, 75))
    d.rectangle([0, h * 0.88, w, h], fill=(60, 130, 170))
    return im


def portrait(w: int, h: int) -> Image.Image:
    im = gradient(w, h, (255, 190, 200), (140, 120, 210))
    d = ImageDraw.Draw(im)
    for i in range(6):
        r = w * (0.08 + 0.03 * i)
        cx, cy = w * (0.2 + 0.12 * i), h * (0.25 + 0.1 * i)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 255, 255), width=6)
    return im


def make_images() -> None:
    landscape(1600, 1000).save(SAMPLE / "image.jpg", quality=88)
    portrait(900, 1600).save(SAMPLE / "IMG-20260915-WA0002.jpg", quality=88)

    # Stored sideways with EXIF orientation 6 (rotate 90° clockwise to view).
    upright = landscape(1200, 800)
    d = ImageDraw.Draw(upright)
    d.text((40, 40), "UP", fill=(0, 0, 0))
    stored = upright.transpose(Image.Transpose.ROTATE_90)
    exif = Image.Exif()
    exif[0x0112] = 6
    stored.save(SAMPLE / "IMG-20260916-WA0003.jpg", quality=88, exif=exif)

    png = gradient(800, 500, (30, 30, 60), (90, 40, 120))
    ImageDraw.Draw(png).rectangle([100, 100, 700, 400], outline=(255, 255, 255), width=8)
    png.save(SAMPLE / "IMG-20260916-WA0004.png")

    webp = landscape(1000, 1000)
    webp.save(SAMPLE / "IMG-20260916-WA0005.webp", quality=80)

    # Sticker: transparent 512x512 WebP
    st = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    d = ImageDraw.Draw(st)
    d.ellipse([56, 56, 456, 456], fill=(255, 204, 77, 255), outline=(255, 255, 255, 255), width=14)
    d.ellipse([170, 190, 210, 250], fill=(60, 40, 20, 255))
    d.ellipse([302, 190, 342, 250], fill=(60, 40, 20, 255))
    d.arc([150, 220, 362, 380], 20, 160, fill=(60, 40, 20, 255), width=14)
    st.save(SAMPLE / "STK-20260917-WA0006.webp", lossless=True)

    # Animated GIF
    frames = []
    for i in range(8):
        f = Image.new("RGB", (320, 240), (240, 240, 250))
        x = 30 + i * 30
        ImageDraw.Draw(f).ellipse([x, 90, x + 60, 150], fill=(0, 168, 132))
        frames.append(f)
    frames[0].save(SAMPLE / "animation.gif", save_all=True, append_images=frames[1:], duration=80, loop=0)

    (SAMPLE / "IMG-20260917-WA0009.jpg").write_bytes(b"\xff\xd8\xff\xe0 this is not really a jpeg" + b"\x00" * 200)


def make_pdf() -> None:
    pages = []
    for n in range(1, 4):
        page = Image.new("RGB", (1240, 1754), "white")
        d = ImageDraw.Draw(page)
        d.rectangle([90, 90, 1150, 220], fill=(0, 128, 105))
        d.text((120, 140), f"Relatorio ficticio - pagina {n}", fill="white")
        for i in range(30):
            d.line([(120, 300 + i * 40), (1100 - (i % 4) * 120, 300 + i * 40)], fill=(170, 170, 170), width=6)
        pages.append(page)
    pages[0].save(SAMPLE / "document.pdf", save_all=True, append_images=pages[1:], resolution=150)


def make_vcard() -> None:
    (SAMPLE / "Marta Ferreira.vcf").write_text(
        "BEGIN:VCARD\nVERSION:3.0\nN:Ferreira;Marta;;;\nFN:Marta Ferreira\n"
        "item1.TEL;waid=351910000000:+351 910 000 000\nitem1.X-ABLabel:Telemóvel\nEND:VCARD\n",
        encoding="utf-8",
    )


def make_av() -> None:
    from wa_export_pdf.media.ffmpeg import find_ffmpeg

    ff = find_ffmpeg(None)
    if ff is None:
        print("FFmpeg not found: skipping video/audio fixtures")
        return
    run = lambda *a: subprocess.run([str(ff), "-v", "error", "-y", *map(str, a)], check=True)  # noqa: E731
    run("-f", "lavfi", "-i", "testsrc2=size=480x270:rate=15:duration=3",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
        "-c:v", "mpeg4", "-q:v", "8", "-c:a", "aac", "-b:a", "48k", "-shortest", SAMPLE / "video.mp4")
    run("-f", "lavfi", "-i", "testsrc2=size=240x426:rate=15:duration=2",
        "-c:v", "mpeg4", "-q:v", "8", SAMPLE / "VID-20260918-WA0010.mp4")
    # Voice note: speech-like amplitude modulation
    run("-f", "lavfi", "-i",
        "aevalsrc=sin(2*PI*220*t)*(0.15+0.85*abs(sin(2*PI*0.9*t))*abs(sin(2*PI*2.7*t))):s=48000:d=7",
        "-c:a", "libopus", "-b:a", "24k", SAMPLE / "audio.opus")
    run("-f", "lavfi", "-i", "sine=frequency=330:duration=4", "-c:a", "aac", "-b:a", "64k",
        SAMPLE / "AUD-20260918-WA0012.m4a")


def main() -> None:
    SAMPLE.mkdir(parents=True, exist_ok=True)
    make_images()
    make_pdf()
    make_vcard()
    make_av()
    print("fixtures written to", SAMPLE)


if __name__ == "__main__":
    main()
