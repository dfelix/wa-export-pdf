from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SAMPLE = FIXTURES / "sample_backup"


def _chromium_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            return Path(pw.chromium.executable_path).exists()
    except Exception:
        return False


CHROMIUM = _chromium_available()


@pytest.fixture
def sample_dir(tmp_path: Path) -> Path:
    """A private copy of the sample export (tests may modify it)."""
    target = tmp_path / "sample_backup"
    shutil.copytree(SAMPLE, target)
    return target


@pytest.fixture
def lines():
    def make(text: str) -> list[str]:
        return text.strip("\n").split("\n")

    return make


requires_chromium = pytest.mark.skipif(not CHROMIUM, reason="Playwright Chromium not installed")
