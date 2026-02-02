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
        """Single highlight should insert marker at character position."""
        html = "<p>Hello world test</p>"
        # "Hello world test" - 'w' is at index 6 (H=0, e=1, l=2, l=3, o=4, space=5, w=6)
        # Highlight chars 6-11 to cover "world" (w=6, o=7, r=8, l=9, d=10)
        highlights = [{"start_char": 6, "end_char": 11, "tag": "test"}]
        result, markers = _insert_markers_into_html(html, highlights)
        assert "ANNMARKER0ENDMARKER" in result
        # Verify marker is placed around 'w'
        assert "HLSTART0ENDHL" in result
        # The word "world" is now split by markers, but 'w' and 'd' should be present
        assert "HLSTART0ENDHLw" in result  # Highlight starts before 'w'
        assert "dHLEND0ENDHL" in result  # Highlight ends after 'd'
        assert len(markers) == 1

    def test_multiple_highlights(self) -> None:
        """Multiple highlights should insert multiple markers."""
        html = "<p>One two three four five</p>"
        # Character indices: O=0, n=1, e=2, space=3, t=4, w=5, o=6, space=7,
        # t=8, h=9, r=10, e=11, e=12, space=13, f=14, o=15, u=16, r=17
        highlights = [
            {"start_char": 4, "tag": "a"},  # 't' of 'two'
            {"start_char": 14, "tag": "b"},  # 'f' of 'four'
        ]
        result, markers = _insert_markers_into_html(html, highlights)
        assert "ANNMARKER0ENDMARKER" in result
        assert "ANNMARKER1ENDMARKER" in result
        assert len(markers) == 2

    def test_preserves_html_tags(self) -> None:
        """HTML tags should be preserved."""
        html = "<p><strong>Bold</strong> text</p>"
        # 'B' is at index 0 within the text content
        highlights = [{"start_char": 0, "tag": "test"}]
        result, _ = _insert_markers_into_html(html, highlights)
        assert "<strong>" in result
        assert "</strong>" in result

    def test_cjk_character_indexing(self) -> None:
        """Verify CJK characters are indexed individually."""
        html = "你好世界"  # "Hello world" in Chinese, 4 characters
        # Characters: 你(0) 好(1) 世(2) 界(3)
        # Highlight covers indices 1-2 (好世)
        highlights = [
            {"start_char": 1, "end_char": 3, "tag": "test", "color": "#FF0000"}
        ]
        result, _ = _insert_markers_into_html(html, highlights)
        assert "HLSTART0ENDHL" in result
        assert "好" in result
        assert "世" in result
        # Verify the marker structure: HLSTART before 好, HLEND after 世
        # Result should be: 你HLSTART0ENDHL好世HLEND0ENDHLANNMARKER0ENDMARKER界
        assert result.index("HLSTART0ENDHL") < result.index("好")
        assert result.index("世") < result.index("HLEND0ENDHL")

    def test_backward_compat_word_fields(self) -> None:
        """Verify backward compatibility with start_word/end_word field names."""
        html = "Hello"
        # Using old field names should still work
        highlights = [{"start_word": 0, "end_word": 2, "tag": "test"}]
        result, markers = _insert_markers_into_html(html, highlights)
        assert "HLSTART0ENDHL" in result
        assert "HLEND0ENDHL" in result
        assert len(markers) == 1
