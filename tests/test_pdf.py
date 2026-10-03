from __future__ import annotations

from pathlib import Path

import pytest
from pypdf import PdfReader

from wa_export_pdf.cli import main
from wa_export_pdf.config import RenderOptions
from wa_export_pdf.parser import ParseOptions
from wa_export_pdf.pipeline import ConvertOptions, convert

from .conftest import requires_chromium

pytestmark = [requires_chromium, pytest.mark.chromium]


def _text(pdf: Path) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(str(pdf)).pages)


def test_pdf_is_created_with_text_links_and_outline(sample_dir: Path, tmp_path: Path):
    out = tmp_path / "conversa.pdf"
    result = convert(sample_dir, out, ConvertOptions(parse=ParseOptions(me="Rui Costa")))
    assert out.is_file() and result.pages >= 3
    reader = PdfReader(str(out))
    assert len(reader.pages) == result.pages
    text = _text(out)
    # Text stays text (searchable), Unicode preserved
    assert "Olá Rui! Tudo bem?" in text
    assert "Straße" in text and "Привет" in text
    assert "14 DE SETEMBRO DE 2026" in text.upper()
    # Clickable links
    uris = []
    for page in reader.pages:
        for annot in page.get("/Annots") or []:
            a = annot.get_object()
            if a.get("/A") and a["/A"].get("/URI"):
                uris.append(a["/A"]["/URI"])
    assert any("example.com/viagem" in u for u in uris)
    # Month/day bookmarks
    outline = reader.outline
    assert outline and outline[0].title.lower().startswith("setembro")
    assert reader.metadata.title == "sample_backup"
    # Media embedded as images, not the whole page rasterised
    assert sum(len(p.images) for p in reader.pages) >= 5


def test_cli_end_to_end_with_debug(sample_dir: Path, tmp_path: Path):
    out = tmp_path / "out" / "chat.pdf"
    code = main([str(sample_dir), str(out), "--me", "Rui Costa", "--page-size", "phone",
                 "--theme", "whatsapp-dark", "--debug", "--screenshots", "2", "-q"])
    assert code == 0 and out.is_file()
    debug = tmp_path / "out" / "chat-debug"
    assert (debug / "conversation.html").is_file()
    assert (debug / "conversation.json").is_file()
    pngs = sorted(debug.glob("*.png"))
    assert 1 <= len(pngs) <= 2
    first = PdfReader(str(out)).pages[0]
    assert round(float(first.mediabox.width)) == 309   # 412 CSS px = 309 pt


def test_no_media_mode(sample_dir: Path, tmp_path: Path):
    out = tmp_path / "nomedia.pdf"
    convert(sample_dir, out, ConvertOptions(parse=ParseOptions(me="Rui Costa"),
                                            render=RenderOptions(include_media=False)))
    reader = PdfReader(str(out))
    assert sum(len(p.images) for p in reader.pages) == 0
    assert "image.jpg" in _text(out)


def test_chunked_output_is_merged(sample_dir: Path, tmp_path: Path):
    out = tmp_path / "chunked.pdf"
    result = convert(sample_dir, out, ConvertOptions(parse=ParseOptions(me="Rui Costa"),
                                                     render=RenderOptions(chunk_size=5)))
    assert result.chunks > 1
    text = _text(out)
    assert text.index("Olá Rui!") < text.index("Boa noite!")
    titles = [o.title for o in PdfReader(str(out)).outline if not isinstance(o, list)]
    assert len(titles) == len(set(titles))   # one bookmark per month after merging


def test_missing_input_gives_error(tmp_path: Path):
    assert main([str(tmp_path / "nothing"), str(tmp_path / "x.pdf"), "-q"]) == 1
