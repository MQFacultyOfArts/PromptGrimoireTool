"""Tests for inject_paragraph_markers_for_export — AC1.1, AC1.2, AC1.3, AC1.6.

Verifies paragraph number marker injection into export HTML:
- AC1.1: Markers inserted at start of each auto-numbered paragraph
- AC1.2: None word_to_legal_para returns HTML unchanged
- AC1.3: Empty word_to_legal_para returns HTML unchanged
- AC1.6: Markers appear before highlight spans at position 0

Plus edge cases: single paragraph, mixed block elements, br-br pseudo-paragraphs.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

from selectolax.lexbor import LexborHTMLParser

from promptgrimoire.input_pipeline.paragraph_map import (
    inject_paragraph_markers_for_export,
)
from tests.conftest import requires_pandoc

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
# All-None values guard: word_to_legal_para with only None values
# ---------------------------------------------------------------------------


class TestAllNoneValues:
    """Given word_to_legal_para where all values are None, HTML is unchanged."""

    def test_all_none_values_skips_injection(self) -> None:
        """All-None para_map hits the empty-after-filter guard; HTML unchanged."""
        html = "<p>Hello world</p>"
        para_map: dict[int, int | None] = {0: None, 5: None}
        result = inject_paragraph_markers_for_export(html, para_map)
        assert result == html


# ---------------------------------------------------------------------------
# AC1.1: Markers inserted at start of each auto-numbered paragraph
# ---------------------------------------------------------------------------


class TestAC1_1_MarkersInserted:
    """Markers appear at the start of each paragraph with data-para."""

    def test_two_paragraphs(self) -> None:
        html = "<p>First paragraph text.</p><p>Second paragraph text.</p>"
        para_map: dict[int, int | None] = {0: 1, 21: 2}
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
        para_map: dict[int, int | None] = {0: 1, 13: 2}
        result = inject_paragraph_markers_for_export(html, para_map)
        numbers = _marker_numbers(result)
        assert numbers == ["1", "2"]


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


# ---------------------------------------------------------------------------
# Pandoc round-trip: verify empty data-paranumber spans survive the AST
# ---------------------------------------------------------------------------


@requires_pandoc
class TestPandocRoundTrip:
    """Verify Pandoc preserves <span data-paranumber="N"></span> through its AST.

    Phase 2 of #417 adds a Lua filter that reads these spans from the AST.
    This smoke test confirms the Phase 1 -> Phase 2 contract: Pandoc must
    represent empty attributed spans as Span nodes with the paranumber
    attribute intact.

    **Important discovery:** Pandoc strips the ``data-`` prefix from HTML
    data attributes when building its AST.  ``data-paranumber="1"`` in HTML
    becomes a key-value pair ``["paranumber", "1"]`` in the Pandoc JSON AST.
    The Phase 2 Lua filter must therefore look up ``paranumber``, not
    ``data-paranumber``.
    """

    # Pandoc strips the "data-" prefix from HTML data attributes in its AST.
    _AST_ATTR = "paranumber"

    def _pandoc_html_to_ast(self, html: str) -> dict[str, Any]:
        """Run pandoc --from html --to json and return parsed AST dict."""
        result = subprocess.run(
            ["pandoc", "--from", "html", "--to", "json"],
            input=html,
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(result.stdout)

    def _find_spans_with_attr(
        self,
        node: Any,
        attr_name: str,
    ) -> list[dict[str, Any]]:
        """Recursively find Span nodes in the Pandoc AST carrying *attr_name*.

        Pandoc JSON AST represents inline elements as::

            {"t": "Span", "c": [["id", ["class", ...], [["key", "val"], ...]], [...]]}

        The third element of the attribute triple is the key-value pair list.
        """
        hits: list[dict[str, Any]] = []
        if isinstance(node, dict):
            if node.get("t") == "Span":
                attrs = node["c"][0]  # [id, classes, kvpairs]
                kvpairs = attrs[2]
                for key, val in kvpairs:
                    if key == attr_name:
                        hits.append({"key": key, "value": val, "node": node})
            # Recurse into all dict values
            for v in node.values():
                hits.extend(self._find_spans_with_attr(v, attr_name))
        elif isinstance(node, list):
            for item in node:
                hits.extend(self._find_spans_with_attr(item, attr_name))
        return hits

    def test_empty_paranumber_span_preserved(self) -> None:
        """A single empty <span data-paranumber="1"></span> survives the AST."""
        html = '<p><span data-paranumber="1"></span>Some paragraph text.</p>'
        ast = self._pandoc_html_to_ast(html)
        spans = self._find_spans_with_attr(ast, self._AST_ATTR)

        assert len(spans) == 1, (
            f"Expected 1 Span with {self._AST_ATTR}, found {len(spans)}"
        )
        assert spans[0]["value"] == "1"

    def test_multiple_paranumber_spans_preserved(self) -> None:
        """Multiple paranumber markers in separate paragraphs all survive."""
        html = (
            '<p><span data-paranumber="1"></span>First paragraph.</p>'
            '<p><span data-paranumber="2"></span>Second paragraph.</p>'
            '<p><span data-paranumber="3"></span>Third paragraph.</p>'
        )
        ast = self._pandoc_html_to_ast(html)
        spans = self._find_spans_with_attr(ast, self._AST_ATTR)

        assert len(spans) == 3, (
            f"Expected 3 Span nodes with {self._AST_ATTR}, found {len(spans)}"
        )
        values = [s["value"] for s in spans]
        assert values == ["1", "2", "3"]

    def test_paranumber_span_alongside_highlight_span(self) -> None:
        """Paranumber span coexists with a highlight span in the same paragraph."""
        html = (
            "<p>"
            '<span data-paranumber="5"></span>'
            '<span data-hl="abc">Highlighted text</span>'
            " rest of paragraph."
            "</p>"
        )
        ast = self._pandoc_html_to_ast(html)
        para_spans = self._find_spans_with_attr(ast, self._AST_ATTR)
        # Pandoc strips "data-" prefix: data-hl -> hl
        hl_spans = self._find_spans_with_attr(ast, "hl")

        assert len(para_spans) == 1
        assert para_spans[0]["value"] == "5"
        assert len(hl_spans) == 1
        assert hl_spans[0]["value"] == "abc"
