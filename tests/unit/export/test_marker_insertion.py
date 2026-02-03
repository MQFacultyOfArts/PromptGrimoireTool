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

    def test_html_entity_escape_before_markers_causes_mismatch(self) -> None:
        """Verify the OLD flow (escape before markers) causes index mismatch.

        Issue #113: This test documents the bug where escaping BEFORE marker
        insertion causes character index mismatch. This test should FAIL with
        the old flow, demonstrating the problem.

        The fix is to NOT escape before marker insertion - see
        test_html_entity_escape_after_markers_works below.
        """
        import html as html_module

        # Raw text with HTML entity-like string
        raw_text = "jav&#x0A;ascript"

        # OLD FLOW: Escape BEFORE marker insertion (WRONG!)
        escaped_html = f"<p>{html_module.escape(raw_text)}</p>"
        # This produces: <p>jav&amp;#x0A;ascript</p>

        # UI creates highlight at raw text positions 4-8 (the "#x0A;" substring)
        highlights = [{"start_char": 4, "end_char": 9, "tag": "test"}]

        result, _ = _insert_markers_into_html(escaped_html, highlights)

        # With the old flow, markers are at WRONG positions (around "amp;#")
        # This assertion verifies the bug exists when using the old flow
        assert "HLSTART0ENDHLamp;#" in result, (
            f"Old flow should produce wrong markers around 'amp;#', got: {result}"
        )

    def test_html_entity_escape_after_markers_works(self) -> None:
        """Verify the NEW flow (escape after markers) aligns indices correctly.

        Issue #113 fix: By NOT escaping before marker insertion, character
        indices match between UI and PDF export. Escaping happens AFTER
        markers are in place, so markers end up at correct positions.
        """
        from promptgrimoire.export.latex import _escape_html_text_content
        from promptgrimoire.export.pdf_export import _plain_text_to_html

        # Raw text with HTML entity-like string
        raw_text = "jav&#x0A;ascript"
        # Characters: j=0, a=1, v=2, &=3, #=4, x=5, 0=6, A=7, ;=8, a=9, s=10...

        # NEW FLOW: Wrap in <p> WITHOUT escaping (uses data-structural marker)
        unescaped_html = _plain_text_to_html(raw_text, escape=False)

        # UI creates highlight at raw text positions 4-8 (the "#x0A;" substring)
        highlights = [{"start_char": 4, "end_char": 9, "tag": "test"}]

        # Insert markers (now counting raw chars)
        result, _ = _insert_markers_into_html(unescaped_html, highlights)

        # Verify markers are at correct positions (around "#x0A;")
        assert "HLSTART0ENDHL#" in result, (
            f"Marker should start before '#', got: {result}"
        )
        assert ";HLEND0ENDHL" in result, f"Marker should end after ';', got: {result}"

        # Now escape AFTER markers (this is what convert_html_with_annotations does)
        escaped_result = _escape_html_text_content(result)

        # Verify escaping works correctly:
        # - The & before markers gets escaped to &amp;
        # - Markers are preserved (they're ASCII, not affected by html.escape)
        assert "&amp;HLSTART0ENDHL#" in escaped_result, (
            f"& should be escaped to &amp; before marker, got: {escaped_result}"
        )
        # The highlighted content #x0A; should still be wrapped by markers
        assert "HLSTART0ENDHL#x0A;HLEND0ENDHL" in escaped_result, (
            f"'#x0A;' should be wrapped by markers, got: {escaped_result}"
        )
