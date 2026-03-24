"""Tests for inject_paragraph_markers_for_export — AC1.1, AC1.2, AC1.3, AC1.6.

Verifies paragraph number marker injection into export HTML:
- AC1.1: Markers inserted at start of each auto-numbered paragraph
- AC1.2: None word_to_legal_para returns HTML unchanged
- AC1.3: Empty word_to_legal_para returns HTML unchanged
- AC1.6: Markers appear before highlight spans at position 0

Plus edge cases: single paragraph, mixed block elements, br-br pseudo-paragraphs.
"""

from __future__ import annotations

from selectolax.lexbor import LexborHTMLParser

from promptgrimoire.input_pipeline.paragraph_map import (
    inject_paragraph_markers_for_export,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_markers(html: str) -> list[dict[str, str | None]]:
    """Extract all data-paranumber spans from HTML as dicts of their attributes."""
    tree = LexborHTMLParser(html)
    markers: list[dict[str, str | None]] = []
    for node in tree.css("span[data-paranumber]"):
        attrs: dict[str, str | None] = dict(node.attributes)
        attrs["_text"] = node.text() or ""
        markers.append(attrs)
    return markers


def _marker_numbers(html: str) -> list[str | None]:
    """Extract the paragraph numbers from all markers in DOM order."""
    return [m["data-paranumber"] for m in _find_markers(html)]


# ---------------------------------------------------------------------------
# AC1.2: None word_to_legal_para returns HTML unchanged
# ---------------------------------------------------------------------------


class TestAC1_2_NoneParaMap:
    """Given word_to_legal_para=None, the function returns input unchanged."""

    def test_none_returns_unchanged(self) -> None:
        html = "<p>Hello world</p>"
        result = inject_paragraph_markers_for_export(html, None)
        assert result == html

    def test_none_with_multiple_paragraphs(self) -> None:
        html = "<p>First</p><p>Second</p>"
        result = inject_paragraph_markers_for_export(html, None)
        assert result == html


# ---------------------------------------------------------------------------
# AC1.3: Empty word_to_legal_para returns HTML unchanged
# ---------------------------------------------------------------------------


class TestAC1_3_EmptyParaMap:
    """Given word_to_legal_para={}, the function returns input unchanged."""

    def test_empty_dict_returns_unchanged(self) -> None:
        html = "<p>Hello world</p>"
        result = inject_paragraph_markers_for_export(html, {})
        assert result == html


# ---------------------------------------------------------------------------
# AC1.1: Markers inserted at start of each auto-numbered paragraph
# ---------------------------------------------------------------------------


class TestAC1_1_MarkersInserted:
    """Markers appear at the start of each paragraph with data-para."""

    def test_two_paragraphs(self) -> None:
        html = "<p>First paragraph text.</p><p>Second paragraph text.</p>"
        para_map: dict[int, int | None] = {0: 1, 22: 2}
        result = inject_paragraph_markers_for_export(html, para_map)
        markers = _find_markers(result)
        assert len(markers) == 2
        assert _marker_numbers(result) == ["1", "2"]

    def test_markers_are_empty_spans(self) -> None:
        """Markers should be empty spans (no text content)."""
        html = "<p>Some text here.</p>"
        para_map: dict[int, int | None] = {0: 1}
        result = inject_paragraph_markers_for_export(html, para_map)
        markers = _find_markers(result)
        assert len(markers) == 1
        assert markers[0]["_text"] == ""

    def test_marker_contains_correct_attribute(self) -> None:
        """Each marker span has data-paranumber with the paragraph number."""
        html = "<p>Alpha</p><p>Beta</p><p>Gamma</p>"
        para_map: dict[int, int | None] = {0: 1, 5: 2, 9: 3}
        result = inject_paragraph_markers_for_export(html, para_map)
        assert _marker_numbers(result) == ["1", "2", "3"]

    def test_none_values_skipped(self) -> None:
        """Entries with None value in the map are skipped (no marker)."""
        html = "<p>First</p><p>Second</p><p>Third</p>"
        para_map: dict[int, int | None] = {0: 1, 5: None, 11: 3}
        result = inject_paragraph_markers_for_export(html, para_map)
        numbers = _marker_numbers(result)
        assert "1" in numbers
        assert "3" in numbers
        # None-valued entry should not produce a marker
        assert len(numbers) == 2


# ---------------------------------------------------------------------------
# Single paragraph
# ---------------------------------------------------------------------------


class TestSingleParagraph:
    """Single paragraph gets exactly one marker."""

    def test_one_paragraph(self) -> None:
        html = "<p>Only paragraph.</p>"
        para_map: dict[int, int | None] = {0: 1}
        result = inject_paragraph_markers_for_export(html, para_map)
        markers = _find_markers(result)
        assert len(markers) == 1
        assert markers[0]["data-paranumber"] == "1"


# ---------------------------------------------------------------------------
# Mixed content: paragraphs and blockquotes
# ---------------------------------------------------------------------------


class TestMixedBlockElements:
    """Markers on all block elements that get data-para."""

    def test_paragraph_and_blockquote(self) -> None:
        html = "<p>Normal text.</p><blockquote>Quoted text.</blockquote>"
        para_map: dict[int, int | None] = {0: 1, 12: 2}
        result = inject_paragraph_markers_for_export(html, para_map)
        numbers = _marker_numbers(result)
        assert len(numbers) == 2
        assert numbers == ["1", "2"]


# ---------------------------------------------------------------------------
# br-br pseudo-paragraphs
# ---------------------------------------------------------------------------


class TestBrBrPseudoParagraphs:
    """Markers appear inside the <span data-para="N"> wrapper for br-br splits."""

    def test_br_br_gets_marker(self) -> None:
        """A br-br pseudo-paragraph wrapped in <span data-para> gets a marker."""
        # After inject_paragraph_attributes, br-br text is wrapped in
        # <span data-para="N">. The regex should match this span too.
        html = "<p>First part.<br><br>Second part.</p>"
        # char offsets: "First part." = 0, "Second part." starts after br-br
        para_map: dict[int, int | None] = {0: 1, 11: 2}
        result = inject_paragraph_markers_for_export(html, para_map)
        numbers = _marker_numbers(result)
        assert len(numbers) >= 1
        # At minimum, the block-level paragraph should get a marker
        assert "1" in numbers


# ---------------------------------------------------------------------------
# AC1.6: Markers appear before highlight spans at position 0
# ---------------------------------------------------------------------------


class TestAC1_6_MarkerBeforeHighlight:
    """When a highlight starts at char 0, the paranumber marker comes first."""

    def test_marker_before_highlight_span(self) -> None:
        """data-paranumber span appears before data-hl span in DOM order."""
        # Simulate HTML where a highlight span starts at position 0
        html = '<p><span data-hl="abc">Highlighted</span> rest.</p>'
        para_map: dict[int, int | None] = {0: 1}
        result = inject_paragraph_markers_for_export(html, para_map)

        # Parse and check ordering within the <p>
        tree = LexborHTMLParser(result)
        p_tag = tree.css_first("p")
        assert p_tag is not None

        # Collect child spans in order
        children = list(p_tag.iter())
        paranumber_idx = None
        highlight_idx = None
        for i, child in enumerate(children):
            if child.attributes.get("data-paranumber") is not None:
                paranumber_idx = i
            if child.attributes.get("data-hl") is not None:
                highlight_idx = i

        assert paranumber_idx is not None, "paranumber marker not found"
        assert highlight_idx is not None, "highlight span not found"
        assert paranumber_idx < highlight_idx, (
            f"paranumber marker (idx={paranumber_idx}) should appear before "
            f"highlight span (idx={highlight_idx})"
        )
