"""Unit tests for marker insertion into HTML.

Tests _insert_markers_into_html() which adds HLSTART/HLEND/ANNMARKER
markers to HTML content before pandoc conversion.

Extracted from tests/unit/test_latex_export.py during Phase 5 reorganization.
"""

from __future__ import annotations

from promptgrimoire.export.latex import _insert_markers_into_html


class TestInsertMarkersIntoHtml:
    """Tests for _insert_markers_into_html function."""

    def test_empty_highlights(self) -> None:
        """Empty highlights should return unchanged HTML."""
        html = "<p>Hello world</p>"
        result, markers = _insert_markers_into_html(html, [])
        assert result == html
        assert markers == []

    def test_single_highlight(self) -> None:
        """Single highlight should insert marker at word position."""
        html = "<p>Hello world test</p>"
        highlights = [{"start_word": 1, "tag": "test"}]
        result, markers = _insert_markers_into_html(html, highlights)
        assert "ANNMARKER0ENDMARKER" in result
        assert "world" in result
        assert len(markers) == 1

    def test_multiple_highlights(self) -> None:
        """Multiple highlights should insert multiple markers."""
        html = "<p>One two three four five</p>"
        highlights = [
            {"start_word": 1, "tag": "a"},
            {"start_word": 3, "tag": "b"},
        ]
        result, markers = _insert_markers_into_html(html, highlights)
        assert "ANNMARKER0ENDMARKER" in result
        assert "ANNMARKER1ENDMARKER" in result
        assert len(markers) == 2

    def test_preserves_html_tags(self) -> None:
        """HTML tags should be preserved."""
        html = "<p><strong>Bold</strong> text</p>"
        highlights = [{"start_word": 0, "tag": "test"}]
        result, _ = _insert_markers_into_html(html, highlights)
        assert "<strong>" in result
        assert "</strong>" in result
