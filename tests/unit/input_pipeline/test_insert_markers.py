"""Tests for insert_markers_into_dom.

Verifies:
- AC3.1: Round-trip property (extract_text_from_html[start:end] == marked text)
- AC3.2: Multi-block HTML (whitespace between blocks doesn't drift)
- AC3.3: <br> tags counted as single newline
- AC3.4: Whitespace runs collapsed to single space
- AC3.5: Formatted spans preserved, markers at correct positions
- AC1.3: Highlights at correct character positions
- AC1.4: CJK/Unicode content highlights correctly
"""

from __future__ import annotations

import html as html_module
import re

import pytest

from promptgrimoire.input_pipeline.html_input import (
    extract_text_from_html,
    insert_markers_into_dom,
)

_WHITESPACE_RUN = re.compile(r"[\s\u00a0]+")


def _extract_marked_text(marked_html: str, hl_idx: int) -> str:
    """Extract text between HLSTART and HLEND markers, stripping tags and entities."""
    start_marker = f"HLSTART{hl_idx}ENDHL"
    end_marker = f"HLEND{hl_idx}ENDHL"
    sm_pos = marked_html.find(start_marker)
    em_pos = marked_html.find(end_marker)
    assert sm_pos != -1, f"HLSTART{hl_idx} not found in {marked_html!r}"
    assert em_pos != -1, f"HLEND{hl_idx} not found in {marked_html!r}"

    between = marked_html[sm_pos + len(start_marker) : em_pos]
    # Strip HTML tags
    between_text = re.sub(r"<[^>]+>", "", between)
    # Decode HTML entities
    between_text = html_module.unescape(between_text)
    # Collapse whitespace same way as the pipeline
    between_text = _WHITESPACE_RUN.sub(" ", between_text)
    return between_text


def _assert_round_trip(
    html: str, highlights: list[dict], *, check_annmarker: bool = True
) -> str:
    """Assert the round-trip property for all highlights.

    Returns the marked HTML for further assertions.
    """
    chars = extract_text_from_html(html)
    marked, ordered = insert_markers_into_dom(html, highlights)

    for hl_idx, hl in enumerate(ordered):
        start = int(hl.get("start_char", hl.get("start_word", 0)))
        end = int(hl.get("end_char", hl.get("end_word", start + 1)))
        expected = "".join(chars[start:end])
        actual = _extract_marked_text(marked, hl_idx)
        assert actual == expected, (
            f"Highlight {hl_idx} [{start}:{end}]: "
            f"expected {expected!r}, got {actual!r}\n"
            f"Marked HTML: {marked!r}"
        )
        if check_annmarker:
            assert f"ANNMARKER{hl_idx}ENDMARKER" in marked

    return marked


class TestRoundTripProperty:
    """AC3.1: extract_text_from_html[start:end] == text between markers."""

    def test_simple_paragraph(self) -> None:
        """Simple paragraph, highlight 'Hello'."""
        _assert_round_trip(
            "<p>Hello world</p>",
            [{"start_char": 0, "end_char": 5}],
        )

    def test_multi_paragraph(self) -> None:
        """Two paragraphs, two highlights."""
        _assert_round_trip(
            "<p>Hello</p><p>World</p>",
            [
                {"start_char": 0, "end_char": 5},
                {"start_char": 5, "end_char": 10},
            ],
        )

    def test_html_entities(self) -> None:
        """AC1.3: HTML entity byte length handled correctly."""
        _assert_round_trip(
            "<p>A &amp; B</p>",
            [{"start_char": 0, "end_char": 5}],
        )

    def test_multiple_entities(self) -> None:
        """Multiple entities in one text node, highlight on single entity char."""
        _assert_round_trip(
            "<p>x &lt; y &amp; y &gt; z</p>",
            [{"start_char": 2, "end_char": 3}],
        )

    def test_entity_at_highlight_boundary(self) -> None:
        """Highlight starting at an entity character."""
        _assert_round_trip(
            "<p>Hello &amp; world</p>",
            [{"start_char": 6, "end_char": 13}],
        )


class TestFormattedSpans:
    """AC3.5: Formatted spans preserved, markers at correct positions."""

    def test_bold_highlight(self) -> None:
        """Highlight on bold text, tags preserved."""
        marked = _assert_round_trip(
            "<p>Hello <strong>bold</strong> text</p>",
            [{"start_char": 6, "end_char": 10}],
        )
        # The <strong> tag should still be present
        assert "<strong>" in marked

    def test_cross_tag_boundary(self) -> None:
        """Highlight spanning across a tag boundary."""
        _assert_round_trip(
            "<p>Hello <strong>bold</strong> world</p>",
            [{"start_char": 4, "end_char": 14}],
        )


class TestWhitespaceCollapsing:
    """AC3.4: Whitespace runs collapsed to single space."""

    def test_multiple_spaces(self) -> None:
        """Multiple spaces collapsed, highlight on collapsed text."""
        _assert_round_trip(
            "<p>Hello   world</p>",
            [{"start_char": 0, "end_char": 11}],
        )


class TestBrTag:
    """AC3.3: <br> tags counted as single newline character."""

    def test_br_before_highlight(self) -> None:
        """Highlight before <br> tag."""
        _assert_round_trip(
            "<p>Line one<br>Line two</p>",
            [{"start_char": 0, "end_char": 8}],
        )


class TestBlockWhitespace:
    """AC3.2: Whitespace between block tags doesn't cause index drift."""

    def test_div_with_indented_paragraphs(self) -> None:
        """Whitespace-only text nodes inside block containers are skipped."""
        _assert_round_trip(
            "<div>\n  <p>Hello</p>\n  <p>World</p>\n</div>",
            [
                {"start_char": 0, "end_char": 5},
                {"start_char": 5, "end_char": 10},
            ],
        )


class TestCJKCharacters:
    """AC1.4: CJK characters indexed individually, not by byte."""

    def test_cjk_highlight(self) -> None:
        """Highlight on CJK characters."""
        _assert_round_trip(
            "<p>\u4f60\u597d\u4e16\u754c</p>",
            [{"start_char": 0, "end_char": 2}],
        )


class TestTableContent:
    """Table content handled correctly."""

    def test_table_cell(self) -> None:
        _assert_round_trip(
            "<table><tr><td>Cell 1</td></tr></table>",
            [{"start_char": 0, "end_char": 6}],
        )


class TestHeadingAndParagraph:
    """Heading + paragraph combination."""

    def test_heading_then_paragraph(self) -> None:
        _assert_round_trip(
            "<h1>Title</h1><p>Body text here</p>",
            [
                {"start_char": 0, "end_char": 5},
                {"start_char": 5, "end_char": 19},
            ],
        )


class TestEmptyHighlights:
    """Empty/error cases."""

    def test_empty_highlights_returns_unchanged(self) -> None:
        """Empty highlights list returns HTML unchanged."""
        html = "<p>Hello world</p>"
        result, markers = insert_markers_into_dom(html, [])
        assert result == html
        assert markers == []

    def test_empty_html_with_highlights_raises(self) -> None:
        """Empty HTML with non-empty highlights raises ValueError."""
        with pytest.raises(ValueError, match="empty HTML"):
            insert_markers_into_dom("", [{"start_char": 0, "end_char": 5}])


class TestBackwardCompat:
    """Legacy start_word/end_word field names work as aliases."""

    def test_start_word_end_word(self) -> None:
        html = "<p>Hello world</p>"
        chars = extract_text_from_html(html)
        marked, _ordered = insert_markers_into_dom(
            html,
            [{"start_word": 0, "end_word": 5, "tag": "legacy"}],
        )
        expected = "".join(chars[0:5])
        actual = _extract_marked_text(marked, 0)
        assert actual == expected


class TestAnnmarkerPresent:
    """ANNMARKER inserted at end of each highlight."""

    def test_annmarker_present(self) -> None:
        marked = _assert_round_trip(
            "<p>Hello world</p>",
            [{"start_char": 0, "end_char": 5}],
            check_annmarker=True,
        )
        # ANNMARKER should appear after HLEND
        hlend_pos = marked.find("HLEND0ENDHL")
        ann_pos = marked.find("ANNMARKER0ENDMARKER")
        assert hlend_pos < ann_pos, (
            f"ANNMARKER should appear after HLEND: "
            f"HLEND at {hlend_pos}, ANNMARKER at {ann_pos}"
        )
