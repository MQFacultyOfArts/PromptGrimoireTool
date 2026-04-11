"""Integration test: LaTeX special characters in annotations compile successfully.

Uses the Pabai workspace fixture (5 highlights with & in para_ref and
comment text) which caused a production LaTeX compilation failure on
2026-04-11.  The fix escapes para_ref via escape_unicode_latex().

This test proves the fix works end-to-end through the full pipeline:
Python escaping → Pandoc → Lua filter → LuaLaTeX compilation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import pytest_asyncio

from promptgrimoire.export.pdf_export import export_annotation_pdf
from tests.conftest import requires_full_latexmk
from tests.integration.conftest import extract_pdf_text_pymupdf

FIXTURE_PATH = (
    Path(__file__).parents[1] / "fixtures" / "workspace_pabai_latex_specials.json"
)


def _load_fixture() -> dict:
    with FIXTURE_PATH.open() as f:
        return json.load(f)


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def specials_result(tmp_path_factory):
    """Compile the latex-specials fixture once for all tests in this module."""
    output_dir = tmp_path_factory.mktemp("pabai_specials")
    fixture = _load_fixture()

    pdf_path = await export_annotation_pdf(
        html_content=fixture["html_content"],
        highlights=fixture["highlights"],
        tag_colours=fixture["tag_colours"],
        output_dir=output_dir,
    )

    tex_path = output_dir / "annotated_document.tex"
    tex_content = tex_path.read_text()
    pdf_text = extract_pdf_text_pymupdf(pdf_path)

    return {
        "pdf_path": pdf_path,
        "tex_path": tex_path,
        "tex_content": tex_content,
        "pdf_text": pdf_text,
        "output_dir": output_dir,
        "fixture": fixture,
    }


@requires_full_latexmk
class TestLatexSpecialsCompile:
    """Annotations with LaTeX specials must compile without error."""

    @pytest.mark.asyncio(loop_scope="module")
    async def test_pdf_is_produced(self, specials_result) -> None:
        """Export must succeed despite & in para_ref and comments."""
        pdf_path = specials_result["pdf_path"]
        assert pdf_path.exists()
        assert pdf_path.stat().st_size > 1000

    @pytest.mark.asyncio(loop_scope="module")
    async def test_all_annotation_numbers_present(self, specials_result) -> None:
        """Every annotation number (1-5) must appear in the PDF."""
        pdf_text = specials_result["pdf_text"]
        fixture = specials_result["fixture"]
        n_highlights = len(fixture["highlights"])

        for i in range(1, n_highlights + 1):
            assert str(i) in pdf_text, f"Annotation {i} not found in PDF text"

    @pytest.mark.asyncio(loop_scope="module")
    async def test_ampersand_rendered_in_pdf(self, specials_result) -> None:
        """The & character must appear as literal text in the PDF output."""
        pdf_text = specials_result["pdf_text"]
        # The para_ref "fn 8 & fn 9" should render with a visible &
        assert "&" in pdf_text, "Escaped & not rendered as literal ampersand in PDF"

    @pytest.mark.asyncio(loop_scope="module")
    async def test_comment_text_present(self, specials_result) -> None:
        """Comment text with & must appear in the PDF."""
        pdf_text = specials_result["pdf_text"]
        # "Nicholls & Nolan" appears in multiple comments
        assert "Nicholls" in pdf_text, (
            "Comment text 'Nicholls & Nolan' not found in PDF"
        )
