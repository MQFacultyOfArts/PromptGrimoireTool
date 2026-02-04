"""Tests for LaTeX highlight behavior across environment boundaries.

These tests verify that highlights spanning list items compile correctly
using the production PDF export pipeline.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from promptgrimoire.parsers.rtf import parse_rtf

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from promptgrimoire.models import ParsedRTF
    from tests.conftest import PdfExportResult

# Run all RTF tests on same worker to share LibreOffice process
pytestmark = pytest.mark.xdist_group("rtf_parser")


@pytest.fixture(scope="module")
def parsed_lawlis() -> ParsedRTF:
    """Parse 183.rtf once for all tests in module."""
    path = Path(__file__).parent.parent / "fixtures" / "183.rtf"
    return parse_rtf(path)


class TestCrossEnvironmentHighlights:
    """Tests verifying highlight behavior across list boundaries."""

    @pytest.mark.asyncio
    async def test_cross_env_highlight_compiles_to_pdf(
        self,
        parsed_lawlis: ParsedRTF,
        pdf_exporter: Callable[..., Coroutine[Any, Any, PdfExportResult]],
    ) -> None:
        """Verify cross-environment highlights compile to PDF successfully.

        Words 848-906 span across a \\item boundary. This test confirms
        the highlight boundary splitting works correctly using the
        production PDF export pipeline.
        """
        highlights: list[dict[str, Any]] = [
            {
                "start_word": 848,
                "end_word": 906,
                "tag": "order",
                "author": "Test User",
                "text": "test highlight spanning list boundary",
                "comments": [],
                "created_at": "2026-01-27T10:00:00+00:00",
            }
        ]

        acceptance_criteria = """
This test verifies highlights spanning list item boundaries compile correctly.

Words 848-906 cross a list item boundary in the source document.

WHAT THIS PROVES:
- Highlight boundary splitting works correctly
- No 'Lonely item' or 'Extra brace' errors occur
- Production pipeline (libreoffice.lua filter, full preamble) is used

WHAT TO CHECK IN THE PDF:
1. Highlight appears around words 848-906
2. Margin annotation shows 'order' tag
3. List structure is preserved (items render correctly)
4. No overfull/underfull vbox warnings (check .log file)
"""

        result = await pdf_exporter(
            html=parsed_lawlis.html,
            highlights=highlights,
            test_name="cross_env_highlight",
            acceptance_criteria=acceptance_criteria,
        )

        assert result.pdf_path.exists(), f"PDF not created at {result.pdf_path}"
        assert result.tex_path.exists(), f"TeX not created at {result.tex_path}"

        print(f"\nPDF saved to: {result.pdf_path.absolute()}")
        print(f"TeX saved to: {result.tex_path.absolute()}")
