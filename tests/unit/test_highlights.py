"""Tests for server-side highlight insertion."""

import pytest

from promptgrimoire.parsers.highlights import HighlightSpec, insert_highlights


class TestInsertHighlights:
    """Tests for insert_highlights function."""

    def test_no_highlights_returns_original(self) -> None:
        """When no highlights, returns original HTML unchanged."""
        html = "<p>Hello world</p>"
        result = insert_highlights(html, [])
        assert result == html

    def test_single_highlight(self) -> None:
        """Single highlight inserts mark tags correctly."""
        html = "<p>Hello world</p>"
        spec = HighlightSpec(id="abc", start=0, end=5, color="#ff0000", tag="test")
        result = insert_highlights(html, [spec])

        assert '<mark class="case-highlight"' in result
        assert 'data-highlight-id="abc"' in result
        assert 'data-tag="test"' in result
        assert "background-color: #ff000040" in result
        assert "</mark>" in result

    def test_highlight_preserves_html_structure(self) -> None:
        """Highlights don't break surrounding HTML structure."""
        html = "<div><p>Hello world</p></div>"
        spec = HighlightSpec(id="abc", start=0, end=5, color="#ff0000", tag="test")
        result = insert_highlights(html, [spec])

        assert result.startswith("<div><p>")
        assert result.endswith("</p></div>")

    def test_multiple_highlights_non_overlapping(self) -> None:
        """Multiple non-overlapping highlights are all applied."""
        html = "<p>Hello world test</p>"
        specs = [
            HighlightSpec(id="a", start=0, end=5, color="#ff0000", tag="first"),
            HighlightSpec(id="b", start=12, end=16, color="#00ff00", tag="second"),
        ]
        result = insert_highlights(html, specs)

        assert 'data-highlight-id="a"' in result
        assert 'data-highlight-id="b"' in result

    def test_highlight_spans_html_tags(self) -> None:
        """Highlight spanning across HTML tags works correctly."""
        # "Hello " is in first <span>, "world" is in second
        html = "<p><span>Hello </span><span>world</span></p>"
        # Select "lo wor" which spans both spans
        spec = HighlightSpec(id="abc", start=3, end=9, color="#ff0000", tag="test")
        result = insert_highlights(html, [spec])

        # The mark should be inserted, even if it creates invalid nesting
        # (browsers handle this gracefully)
        assert '<mark class="case-highlight"' in result
        assert "</mark>" in result

    def test_handles_html_entities(self) -> None:
        """HTML entities count as single characters."""
        html = "<p>A&nbsp;B</p>"
        # "A B" - &nbsp; is one character, so positions are: A=0, nbsp=1, B=2
        spec = HighlightSpec(id="abc", start=0, end=3, color="#ff0000", tag="test")
        result = insert_highlights(html, [spec])

        assert '<mark class="case-highlight"' in result

    def test_out_of_range_highlight_skipped(self) -> None:
        """Highlights beyond text length are skipped."""
        html = "<p>Hi</p>"
        spec = HighlightSpec(id="abc", start=100, end=200, color="#ff0000", tag="test")
        result = insert_highlights(html, [spec])

        # Should not crash, just return original
        assert result == html

    def test_real_world_paragraph(self) -> None:
        """Test with realistic court judgment HTML structure."""
        html = """<ol start="42"><li><p class="western">The appellant argues that
the trial judge erred in applying the standard.</p></li></ol>"""
        # Highlight "trial judge"
        spec = HighlightSpec(id="xyz", start=27, end=38, color="#1f77b4", tag="reasons")
        result = insert_highlights(html, [spec])

        assert 'data-highlight-id="xyz"' in result
        assert 'data-tag="reasons"' in result
