"""Integration tests for full PDF export pipeline.

Tests the complete flow: HTML -> markers -> pandoc -> process -> compile.

Includes Issue #85 regression test to ensure literal markers never appear
in final LaTeX output.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.conftest import PdfExportResult


def _has_latexmk() -> bool:
    """Check if latexmk is available via TinyTeX."""
    from promptgrimoire.export.pdf import get_latexmk_path

    try:
        get_latexmk_path()
        return True
    except FileNotFoundError:
        return False


requires_latexmk = pytest.mark.skipif(
    not _has_latexmk(), reason="latexmk not installed"
)


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

        result = pdf_exporter(
            html=html,
            highlights=highlights,
            test_name="issue_85_regression",
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

        result = pdf_exporter(
            html=html,
            highlights=highlights,
            test_name="interleaved_compile",
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

        result = pdf_exporter(
            html=html,
            highlights=highlights,
            test_name="three_overlapping",
        )

        assert result.pdf_path.exists()
