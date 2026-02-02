"""Integration tests for full PDF export pipeline.

Tests the complete flow: HTML -> markers -> pandoc -> process -> compile.

Includes Issue #85 regression test to ensure literal markers never appear
in final LaTeX output.

To skip these tests (e.g., in CI without LaTeX):
    pytest -m "not latex"
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.conftest import requires_latexmk

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.conftest import PdfExportResult


class TestPdfPipeline:
    """Integration tests for PDF export pipeline."""

    @requires_latexmk
    def test_issue_85_regression_no_literal_markers(
        self, pdf_exporter: Callable[..., PdfExportResult]
    ) -> None:
        """Regression test: markers are processed, not literal text.

        Issue #85: Nested/interleaved highlights left literal HLSTART/HLEND
        markers in the output instead of processing them into LaTeX commands.

        CRITICAL: This test MUST fail if Issue #85 regresses.
        """
        html = """
        <p>The quick brown fox jumps over the lazy dog.</p>
        """
        # Create interleaved highlights (the problematic case)
        # Use real tag names from TAG_COLOURS in conftest.py
        highlights = [
            {
                "start_word": 1,  # "quick"
                "end_word": 4,  # through "fox"
                "tag": "jurisdiction",
                "author": "Test User",
                "text": "quick brown fox",
                "comments": [],
                "created_at": "2026-01-28T10:00:00+00:00",
            },
            {
                "start_word": 2,  # "brown"
                "end_word": 6,  # through "over"
                "tag": "legal_issues",
                "author": "Test User",
                "text": "brown fox jumps over",
                "comments": [],
                "created_at": "2026-01-28T10:00:00+00:00",
            },
        ]

        acceptance_criteria = """
TEST: Issue #85 Regression - No Literal Markers

WHAT THIS TESTS:
Two interleaved highlights ("quick brown fox" and "brown fox jumps over")
that overlap. The lexer must process highlight markers into LaTeX commands.

WHAT TO CHECK:
1. "quick" has ONE highlight (jurisdiction - blue)
2. "brown fox" has TWO highlights overlapping (jurisdiction + legal_issues)
3. "jumps over" has ONE highlight (legal_issues - pink)
4. NO literal marker text visible (no HL-START, HL-END, etc.)
5. Underlines visible under highlighted text

IF YOU SEE RAW MARKER TEXT: Issue #85 has regressed!
"""
        result = pdf_exporter(
            html=html,
            highlights=highlights,
            test_name="issue_85_regression",
            acceptance_criteria=acceptance_criteria,
        )

        latex_content = result.tex_path.read_text()

        # CRITICAL ASSERTIONS - markers must NOT appear literally
        assert "HLSTART" not in latex_content, (
            "HLSTART marker found in output - Issue #85 regression!"
        )
        assert "HLEND" not in latex_content, (
            "HLEND marker found in output - Issue #85 regression!"
        )
        assert "ANNMARKER" not in latex_content, (
            "ANNMARKER found in output - Issue #85 regression!"
        )
        assert "ENDHL" not in latex_content, (
            "ENDHL found in output - Issue #85 regression!"
        )
        assert "ENDMARKER" not in latex_content, (
            "ENDMARKER found in output - Issue #85 regression!"
        )

        # Positive assertions - LaTeX commands should be present
        assert r"\highLight" in latex_content, "No \\highLight command in output"

        # PDF should compile successfully
        assert result.pdf_path.exists(), "PDF was not generated"

    @requires_latexmk
    def test_interleaved_highlights_compile(
        self, pdf_exporter: Callable[..., PdfExportResult]
    ) -> None:
        """Interleaved highlights should compile to PDF."""
        html = "<p>One two three four five six seven eight</p>"
        # Use real tag names from TAG_COLOURS in conftest.py
        highlights = [
            {
                "start_word": 1,
                "end_word": 5,
                "tag": "jurisdiction",
                "author": "Test",
                "text": "two three four five",
                "comments": [],
            },
            {
                "start_word": 3,
                "end_word": 7,
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
        result = pdf_exporter(
            html=html,
            highlights=highlights,
            test_name="interleaved_compile",
            acceptance_criteria=acceptance_criteria,
        )

        assert result.pdf_path.exists()

    @requires_latexmk
    def test_three_overlapping_compile(
        self, pdf_exporter: Callable[..., PdfExportResult]
    ) -> None:
        """Three overlapping highlights should compile to PDF."""
        html = "<p>Word one word two word three word four</p>"
        # Use real tag names from TAG_COLOURS in conftest.py
        highlights = [
            {
                "start_word": 0,
                "end_word": 6,
                "tag": "jurisdiction",
                "author": "Test",
                "text": "Word one word two word three",
                "comments": [],
            },
            {
                "start_word": 1,
                "end_word": 5,
                "tag": "legal_issues",
                "author": "Test",
                "text": "one word two word",
                "comments": [],
            },
            {
                "start_word": 2,
                "end_word": 4,
                "tag": "reasons",
                "author": "Test",
                "text": "word two",
                "comments": [],
            },
        ]

        acceptance_criteria = """
TEST: Three Overlapping Highlights

WHAT THIS TESTS:
Three highlights all overlapping in the middle:
- Highlight 1: words 0-6 (jurisdiction - blue)
- Highlight 2: words 1-5 (legal_issues - pink)
- Highlight 3: words 2-4 (reasons - green)

WHAT TO CHECK:
1. "Word" has ONE highlight (jurisdiction - blue)
2. "one" has TWO highlights
3. "word two" has THREE highlights (all colours visible)
4. "word" has TWO highlights
5. "three" has ONE highlight (jurisdiction)
6. Three overlapping = single thick "many-dark" underline (not stacked)
"""
        result = pdf_exporter(
            html=html,
            highlights=highlights,
            test_name="three_overlapping",
            acceptance_criteria=acceptance_criteria,
        )

        assert result.pdf_path.exists()

    @requires_latexmk
    def test_overlapping_highlights_crossing_list_boundary(
        self, pdf_exporter: Callable[..., PdfExportResult]
    ) -> None:
        """Compound case: overlapping highlights that cross environment boundary.

        Issue #87: Tests that both overlap handling AND boundary splitting
        work correctly together.
        """
        # HTML with a list - pandoc will convert to enumerate environment
        html = """
        <p>Before the list starts here.</p>
        <ol>
            <li>First item in the list.</li>
            <li>Second item in the list.</li>
        </ol>
        <p>After the list ends here.</p>
        """
        # Two overlapping highlights that both cross the list boundary
        # Words: Before(0) the(1) list(2) starts(3) here(4) First(5) item(6)
        #        in(7) the(8) list(9) Second(10) item(11) in(12) the(13) list(14)
        #        After(15) the(16) list(17) ends(18) here(19)
        highlights = [
            {
                "start_word": 3,  # "starts"
                "end_word": 11,  # through "item" (second)
                "tag": "jurisdiction",
                "author": "Test",
                "text": "starts here First item in the list Second item",
                "comments": [],
            },
            {
                "start_word": 6,  # "item" (first)
                "end_word": 15,  # through "After"
                "tag": "legal_issues",
                "author": "Test",
                "text": "item in the list Second item in the list After",
                "comments": [],
            },
        ]

        acceptance_criteria = """
TEST: Overlapping Highlights Crossing List Boundary (Issue #87)

WHAT THIS TESTS:
Two overlapping highlights that BOTH cross the list environment boundary.
This compound case exercises both the overlap handling AND boundary splitting.

- Highlight 1 (jurisdiction): words 3-11, crosses into list
- Highlight 2 (legal_issues): words 6-15, crosses out of list

WHAT TO CHECK:
1. "starts here" has ONE highlight (jurisdiction - blue)
2. "First item in the list Second item" has TWO highlights overlapping
3. "in the list After" has ONE highlight (legal_issues - pink)
4. List structure preserved (numbered items render correctly)
5. No compilation errors or 'Lonely item' warnings
"""
        result = pdf_exporter(
            html=html,
            highlights=highlights,
            test_name="overlapping_cross_boundary",
            acceptance_criteria=acceptance_criteria,
        )

        assert result.pdf_path.exists()
