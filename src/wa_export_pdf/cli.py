"""Command line interface: ``wa-export-pdf INPUT [OUTPUT] [options]``."""

from __future__ import annotations

import argparse
import logging
import platform
import subprocess
import sys
from datetime import date
from pathlib import Path

from . import __version__
from .config import PAGE_SIZES, RenderOptions
from .media import QUALITY_PRESETS, find_ffmpeg
from .parser import DiscoveryError, ParseOptions
from .pdf import BrowserError
from .renderer.theme import FONTS_DIR, ThemeError, available_themes

log = logging.getLogger("wa_export_pdf")


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid date '{value}', expected YYYY-MM-DD") from exc


def _screens(value: str) -> int | None:
    if value.lower() == "all":
        return None
    n = int(value)
    if n < 0:
        raise argparse.ArgumentTypeError("must be >= 0 or 'all'")
    return n


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="wa-export-pdf",
        description="Turn a WhatsApp chat export into a PDF that looks like WhatsApp.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  wa-export-pdf ./backup ./chat.pdf\n"
            "  wa-export-pdf export.zip chat.pdf --page-size phone --theme whatsapp-dark\n"
            "  wa-export-pdf ./group ./group.pdf --me \"Ana Silva\" --debug\n"
        ),
    )
    p.add_argument("input", nargs="?", type=Path, help="export folder, chat .txt file or .zip")
    p.add_argument("output", nargs="?", type=Path, help="PDF to create (default: <input name>.pdf)")

    look = p.add_argument_group("appearance")
    look.add_argument("--theme", default="whatsapp",
                      help=f"bundled theme ({', '.join(available_themes())}) or path to a theme folder")
    look.add_argument("--page-size", choices=sorted(PAGE_SIZES), default="a4",
                      help="a4/letter: WhatsApp Desktop layout on printable paper; "
                           "phone: 412x915 px pages that look like a phone screen (default: a4)")
    look.add_argument("--background", choices=["doodle", "plain"], default="doodle",
                      help="chat wallpaper (default: doodle)")
    look.add_argument("--no-header", dest="header", action="store_false",
                      help="do not draw the WhatsApp top bar on each page")
    look.add_argument("--ticks", action="store_true",
                      help="draw blue read ticks on sent messages (cosmetic: the export has no read status)")
    look.add_argument("--emoji-font", choices=["bundled", "system"], default="bundled",
                      help="bundled Noto Color Emoji (same on every OS) or the system emoji font")
    look.add_argument("--title", help="title shown in the top bar and PDF metadata")
    look.add_argument("--css", dest="extra_css", type=Path, action="append", default=[],
                      help="extra CSS file applied after the theme (repeatable)")

    content = p.add_argument_group("content")
    content.add_argument("--me", help="your name as it appears in the chat (messages shown on the right)")
    content.add_argument("--from", dest="date_from", type=_date, help="first day to include (YYYY-MM-DD)")
    content.add_argument("--to", dest="date_to", type=_date, help="last day to include (YYYY-MM-DD)")
    content.add_argument("--date-order", choices=["auto", "dmy", "mdy", "ymd"], default="auto",
                         help="date format of the export (default: detect)")
    content.add_argument("--lang", help="UI language for labels (pt, pt-BR, en, es, fr, de, it); default: detect")
    media = content.add_mutually_exclusive_group()
    media.add_argument("--include-media", dest="include_media", action="store_true", default=True,
                       help="embed photos, video frames, stickers... (default)")
    media.add_argument("--no-media", dest="include_media", action="store_false",
                       help="do not embed media; show WhatsApp-like placeholders")

    proc = p.add_argument_group("processing")
    proc.add_argument("--quality", choices=list(QUALITY_PRESETS), default="medium",
                      help="resolution of embedded pictures (default: medium)")
    proc.add_argument("--ffmpeg", help="path to the ffmpeg executable (default: PATH or imageio-ffmpeg)")
    proc.add_argument("--no-waveform", dest="waveforms", action="store_false",
                      help="skip computing voice-note waveforms")
    proc.add_argument("--no-doc-preview", dest="pdf_previews", action="store_false",
                      help="skip first-page previews of PDF documents")
    proc.add_argument("--jobs", "-j", type=int, default=0, help="parallel media workers (default: CPUs, max 8)")
    proc.add_argument("--chunk-size", type=int, default=2000,
                      help="messages per Chromium pass for big chats (default: 2000)")
    proc.add_argument("--cache-dir", type=Path,
                      help="persistent cache for thumbnails/frames (faster re-runs; stores derived images!)")
    proc.add_argument("--keep-temp", action="store_true", help="do not delete the temporary work folder")

    dbg = p.add_argument_group("debugging")
    dbg.add_argument("--debug", action="store_true",
                     help="write HTML, a JSON summary and PNG page screenshots next to the PDF")
    dbg.add_argument("--debug-dir", type=Path, help="where --debug writes its files (default: <output>-debug/)")
    dbg.add_argument("--screenshots", type=_screens, default=10, metavar="N|all",
                     help="pages to screenshot in debug mode (default: 10)")
    dbg.add_argument("--html-only", action="store_true", help="only produce the HTML (implies --debug)")
    dbg.add_argument("-v", "--verbose", action="count", default=0, help="more output (-vv for debug logs)")
    dbg.add_argument("-q", "--quiet", action="store_true", help="only errors")

    tools = p.add_argument_group("setup")
    tools.add_argument("--check", action="store_true", help="check the environment (Chromium, FFmpeg, fonts) and exit")
    tools.add_argument("--install-browser", action="store_true",
                       help="download Playwright's Chromium (one-time, needs Internet) and exit")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def _setup_logging(verbose: int, quiet: bool) -> None:
    # Windows consoles may use a legacy code page (cp1252/cp850): replace
    # characters they cannot show instead of failing on names like "Zoë 🌸".
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    level = logging.WARNING if quiet else logging.INFO
    if verbose >= 2:
        level = logging.DEBUG
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s" if verbose < 2 else "%(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger("wa_export_pdf")
    root.handlers[:] = [handler]
    root.setLevel(level)
    root.propagate = False


def run_check() -> int:
    ok = True
    print(f"wa-export-pdf {__version__}")
    print(f"Python      {platform.python_version()} ({platform.system()} {platform.machine()})")
    try:
        from importlib.metadata import version

        print(f"Playwright  {version('playwright')}")
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            exe = Path(pw.chromium.executable_path)
            if exe.exists():
                print(f"Chromium    OK  {exe}")
            else:
                print("Chromium    MISSING  -> run: wa-export-pdf --install-browser")
                ok = False
    except Exception as exc:
        print(f"Chromium    ERROR {exc}")
        ok = False
    ff = find_ffmpeg(None)
    print(f"FFmpeg      {'OK  ' + str(ff) if ff else 'not found (optional: video frames, waveforms)'}")
    try:
        import pypdfium2  # noqa: F401

        print("pypdfium2   OK (document previews, debug screenshots)")
    except ImportError:
        print("pypdfium2   not installed (optional: pip install pypdfium2)")
    fonts = sorted(p.name for p in FONTS_DIR.glob("*.ttf"))
    print(f"Fonts       {', '.join(fonts)}")
    print(f"Themes      {', '.join(available_themes())}")
    return 0 if ok else 1


def install_browser() -> int:
    cmd = [sys.executable, "-m", "playwright", "install", "chromium"]
    print("Running:", " ".join(cmd))
    return subprocess.call(cmd)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _setup_logging(args.verbose, args.quiet)

    if args.check:
        return run_check()
    if args.install_browser:
        return install_browser()
    if args.input is None:
        parser.print_usage(sys.stderr)
        print("error: INPUT is required", file=sys.stderr)
        return 2

    source: Path = args.input
    output: Path = args.output or Path.cwd() / f"{(source.stem if source.is_file() else source.name) or 'chat'}.pdf"
    if output.suffix.lower() != ".pdf":
        output = output.with_suffix(output.suffix + ".pdf") if output.suffix else output.with_suffix(".pdf")

    debug_dir = None
    if args.debug or args.html_only or args.debug_dir:
        debug_dir = args.debug_dir or output.with_name(output.stem + "-debug")

    from .pipeline import ConvertOptions, convert

    options = ConvertOptions(
        parse=ParseOptions(me=args.me, date_order=args.date_order, title=args.title, locale=args.lang),
        render=RenderOptions(
            theme=args.theme,
            page_size=args.page_size,
            background=args.background,
            header=args.header,
            ticks=args.ticks,
            emoji_font=args.emoji_font,
            include_media=args.include_media,
            chunk_size=args.chunk_size,
            title=args.title,
            date_from=args.date_from,
            date_to=args.date_to,
            extra_css=[c.resolve() for c in args.extra_css],
        ),
        quality=args.quality,
        ffmpeg=args.ffmpeg,
        waveforms=args.waveforms,
        pdf_previews=args.pdf_previews,
        jobs=args.jobs,
        cache_dir=args.cache_dir,
        keep_temp=args.keep_temp,
        debug_dir=debug_dir,
        screenshots=args.screenshots,
        html_only=args.html_only,
    )
    try:
        result = convert(source, output, options)
    except (DiscoveryError, ThemeError, BrowserError, ValueError) as exc:
        log.error("error: %s", exc)
        return 1
    except KeyboardInterrupt:
        log.error("interrupted")
        return 130

    if result.output:
        log.info(
            "Done: %s — %d pages, %d messages, %.0fs",
            result.output, result.pages, result.messages, result.seconds,
        )
    else:
        log.info("HTML written to %s", debug_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
