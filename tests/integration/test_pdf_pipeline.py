"""Integration tests for full PDF export pipeline.

Tests the complete flow: HTML -> markers -> pandoc -> process -> compile.

Most compile tests have been migrated to the English mega-document
(test_english_mega_doc.py). Remaining tests here are scheduled for
deletion in Task 15 (redundant coverage).

To skip these tests (e.g., in CI without LaTeX):
    pytest -m "not latex"
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from tests.conftest import requires_latexmk

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from tests.conftest import PdfExportResult


@pytest.mark.order("first")
class TestPdfPipeline:
    """Integration tests for PDF export pipeline."""

    @requires_latexmk
    @pytest.mark.asyncio
    async def test_interleaved_highlights_compile(
        self,
        pdf_exporter: Callable[..., Coroutine[Any, Any, PdfExportResult]],
    ) -> None:
        """Interleaved highlights should compile to PDF.

        Scheduled for deletion in Task 15 (redundant with
        issue_85_regression which has strictly more assertions).
        """
        html = "<p>One two three four five six seven eight</p>"
        # Use real tag names from TAG_COLOURS in conftest.py
        highlights = [
            {
                "start_char": 1,
                "end_char": 5,
                "tag": "jurisdiction",
                "author": "Test",
                "text": "two three four five",
                "comments": [],
            },
            {
                "start_char": 3,
                "end_char": 7,
                "tag": "legal_issues",
                "author": "Test",
                "text": "four five six seven",
                "comments": [],
            },
        ]

        acceptance_criteria = """
TEST: Interleaved Highlights Compile

WHAT THIS TESTS:
Two highlights that interleave (not properly nested):
- Highlight 1: words 1-5 ("two three four five")
- Highlight 2: words 3-7 ("four five six seven")

WHAT TO CHECK:
1. "two three" has ONE highlight (jurisdiction - blue)
2. "four five" has TWO highlights overlapping
3. "six seven" has ONE highlight (legal_issues - pink)
4. Underlines visible (stacked where overlapping)
5. Document compiles without errors
"""
        result = await pdf_exporter(
            html=html,
            highlights=highlights,
            test_name="interleaved_compile",
            acceptance_criteria=acceptance_criteria,
        )

        assert result.pdf_path.exists()
