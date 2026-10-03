"""HTML -> PDF with Chromium driven by Playwright.

Playwright downloads and manages its own Chromium build per platform
(``python -m playwright install chromium``), so no browser path ever has to
be configured. Pages are loaded from ``file://`` URLs and every resource is
local: the conversion works offline.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

INSTALL_HINT = (
    "Chromium for Playwright is not installed. Run once (needs Internet):\n"
    "    python -m playwright install chromium\n"
    "On Linux you may also need system libraries:  python -m playwright install-deps chromium"
)


class BrowserError(Exception):
    pass


_WAIT_FOR_ASSETS = """
async (families) => {
  for (const f of families) {
    try { await document.fonts.load(f); } catch (e) {}
  }
  await document.fonts.ready;
  const imgs = Array.from(document.images);
  await Promise.all(imgs.map(img => img.complete ? Promise.resolve() :
      new Promise(res => { img.onload = img.onerror = res; })));
  await Promise.all(imgs.map(img => img.decode ? img.decode().catch(() => {}) : null));
  return imgs.length;
}
"""

# Families that the header template re-declares; they must be decoded in the
# main document first so Chromium reuses them when painting the header.
_HEADER_FAMILIES = ['16px "WA Header"', '16px "WA Header Medium"', '14px "WA Roboto"', '500 14px "WA Roboto"']


@dataclass
class PdfJob:
    html: Path
    pdf: Path
    header_template: str
    footer_template: str


class ChromiumRenderer:
    """Context manager owning one Chromium instance for all render passes."""

    def __init__(self) -> None:
        self._pw = None
        self._browser = None

    def __enter__(self) -> "ChromiumRenderer":
        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - dependency missing
            raise BrowserError("The 'playwright' package is not installed: pip install playwright") from exc
        self._pw = sync_playwright().start()
        try:
            self._browser = self._pw.chromium.launch(
                args=["--allow-file-access-from-files", "--disable-gpu", "--font-render-hinting=none"]
            )
        except PlaywrightError as exc:
            self._pw.stop()
            message = str(exc)
            if "Executable doesn't exist" in message or "playwright install" in message:
                raise BrowserError(INSTALL_HINT) from exc
            raise BrowserError(f"Could not start Chromium: {message}") from exc
        return self

    def __exit__(self, *exc) -> None:
        try:
            if self._browser:
                self._browser.close()
        finally:
            if self._pw:
                self._pw.stop()

    def _open(self, html: Path, viewport_width: int):
        assert self._browser is not None
        context = self._browser.new_context(
            viewport={"width": viewport_width, "height": 1000},
            device_scale_factor=1,
            offline=True,              # belt and braces: no network at all
            java_script_enabled=True,
        )
        page = context.new_page()
        page.set_default_timeout(0)
        page.goto(html.resolve().as_uri(), wait_until="load", timeout=0)
        count = page.evaluate(_WAIT_FOR_ASSETS, _HEADER_FAMILIES)
        log.debug("%s: %d images ready", html.name, count)
        return context, page

    def render_pdf(self, job: PdfJob, viewport_width: int) -> None:
        started = time.monotonic()
        context, page = self._open(job.html, viewport_width)
        try:
            page.emulate_media(media="print")
            page.pdf(
                path=str(job.pdf),
                prefer_css_page_size=True,
                print_background=True,
                display_header_footer=True,
                header_template=job.header_template,
                footer_template=job.footer_template,
                outline=True,
                tagged=True,
            )
        finally:
            context.close()
        log.debug("rendered %s in %.1fs", job.pdf.name, time.monotonic() - started)

    def screenshot_html(self, html: Path, out_dir: Path, viewport_width: int, page_height: int, limit: int | None) -> list[Path]:
        """Fallback screenshots (no pypdfium2): slices of the screen layout."""
        context, page = self._open(html, viewport_width)
        written: list[Path] = []
        try:
            page.emulate_media(media="print")
            total = page.evaluate("document.documentElement.scrollHeight")
            n = max(1, -(-total // page_height))
            if limit is not None:
                n = min(n, limit)
            for i in range(n):
                path = out_dir / f"{html.stem}-screen-{i + 1:03d}.png"
                page.screenshot(
                    path=str(path),
                    full_page=True,
                    clip={"x": 0, "y": i * page_height, "width": viewport_width,
                          "height": min(page_height, total - i * page_height)},
                )
                written.append(path)
        finally:
            context.close()
        return written
