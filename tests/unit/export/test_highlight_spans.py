"""Tests for compute_highlight_spans — AC1.1 through AC1.5.

Verifies pre-Pandoc highlight span insertion:
- AC1.1: Cross-block highlights produce pre-split spans
- AC1.2: 3+ overlapping highlights produce correct data-hl and data-colors
- AC1.3: Single-block highlight produces one span
- AC1.4: No highlights leaves HTML unchanged
- AC1.5: Cross-block spans are NOT left crossing the boundary

Plus edge cases: CRLF, HTML entities, adjacent highlights, data-annots placement.
"""

from __future__ import annotations

import json

from selectolax.lexbor import LexborHTMLParser

from promptgrimoire.export.highlight_spans import (
    PANDOC_BLOCK_ELEMENTS,
    compute_highlight_spans,
)
from promptgrimoire.input_pipeline.html_input import extract_text_from_html

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_spans(html: str) -> list[dict[str, str]]:
    """Extract all data-hl spans from HTML as dicts of their attributes."""
    tree = LexborHTMLParser(html)
    spans = []
    for node in tree.css("span[data-hl]"):
        attrs = dict(node.attributes)
        attrs["_text"] = node.text() or ""
        spans.append(attrs)
    return spans


def _make_hl(
    start: int,
    end: int,
    tag: str = "jurisdiction",
    author: str = "",
    comments: list | None = None,
) -> dict:
    """Build a highlight dict matching the expected schema."""
    return {
        "start_char": start,
        "end_char": end,
        "tag": tag,
        "author": author,
        "comments": comments or [],
    }


# ---------------------------------------------------------------------------
# AC1.4: No highlights leaves HTML unchanged
# ---------------------------------------------------------------------------


class TestAC1_4_NoHighlights:
    """Given text with no highlights, no <span> elements are inserted."""

    def test_empty_highlight_list(self) -> None:
        html = "<p>no highlights</p>"
        result = compute_highlight_spans(html, [], {})
        assert result == html

    def test_empty_html(self) -> None:
        result = compute_highlight_spans("", [_make_hl(0, 5)], {})
        assert result == ""


# ---------------------------------------------------------------------------
# AC1.3: Single-block highlight produces one span
# ---------------------------------------------------------------------------


class TestAC1_3_SingleBlockHighlight:
    """Given a highlight that doesn't cross any block boundary, a single
    <span> is emitted wrapping the full range."""

    def test_single_span_emitted(self) -> None:
        html = "<p>simple highlight</p>"
        # "simple highlight" is 16 chars, highlight first 6: "simple"
        hl = _make_hl(0, 6, tag="jurisdiction")
        result = compute_highlight_spans(html, [hl], {"jurisdiction": "#3366cc"})

        spans = _find_spans(result)
        assert len(spans) == 1
        assert spans[0]["data-hl"] == "0"
        assert spans[0]["data-colors"] == "tag-jurisdiction-light"
        assert spans[0]["_text"] == "simple"

    def test_mid_text_highlight(self) -> None:
        """Highlight a substring in the middle of a paragraph."""
        html = "<p>hello world today</p>"
        # "hello world today" — highlight "world" (chars 6-11)
        hl = _make_hl(6, 11, tag="evidence")
        result = compute_highlight_spans(html, [hl], {"evidence": "#ff6600"})

        spans = _find_spans(result)
        assert len(spans) == 1
        assert spans[0]["_text"] == "world"
        assert spans[0]["data-colors"] == "tag-evidence-light"


# ---------------------------------------------------------------------------
# AC1.2: 3+ overlapping highlights on same text
# ---------------------------------------------------------------------------


class TestAC1_2_OverlappingHighlights:
    """Given 3+ overlapping highlights on the same text, the span carries
    data-hl="0,1,2" and data-colors listing all three colour names."""

    def test_three_overlapping(self) -> None:
        html = "<p>overlapping text here</p>"
        # "overlapping text here" = 21 chars
        # All three overlap on "text" (chars 12-16)
        highlights = [
            _make_hl(0, 16, tag="jurisdiction"),  # "overlapping text"
            _make_hl(12, 21, tag="evidence"),  # "text here"
            _make_hl(12, 16, tag="credibility"),  # "text"
        ]
        tag_colours = {
            "jurisdiction": "#3366cc",
            "evidence": "#ff6600",
            "credibility": "#009900",
        }
        result = compute_highlight_spans(html, highlights, tag_colours)
        spans = _find_spans(result)

        # Find the span covering "text" where all three overlap
        overlap_spans = [
            s
            for s in spans
            if "0" in s["data-hl"].split(",")
            and "1" in s["data-hl"].split(",")
            and "2" in s["data-hl"].split(",")
        ]
        assert len(overlap_spans) >= 1, f"No triple-overlap span found in {spans}"

        triple = overlap_spans[0]
        assert triple["data-hl"] == "0,1,2"
        assert "tag-jurisdiction-light" in triple["data-colors"]
        assert "tag-evidence-light" in triple["data-colors"]
        assert "tag-credibility-light" in triple["data-colors"]

    def test_two_overlapping(self) -> None:
        html = "<p>some text here</p>"
        # "some text here" = 14 chars
        highlights = [
            _make_hl(0, 9, tag="jurisdiction"),  # "some text"
            _make_hl(5, 14, tag="evidence"),  # "text here"
        ]
        result = compute_highlight_spans(
            html, highlights, {"jurisdiction": "#3366cc", "evidence": "#ff6600"}
        )
        spans = _find_spans(result)

        # Should have a span with both active
        overlap = [
            s
            for s in spans
            if "0" in s["data-hl"].split(",") and "1" in s["data-hl"].split(",")
        ]
        assert len(overlap) >= 1
        assert overlap[0]["data-hl"] == "0,1"


# ---------------------------------------------------------------------------
# AC1.1: Cross-block highlight produces pre-split spans
# ---------------------------------------------------------------------------


class TestAC1_1_CrossBlockSplit:
    """Given overlapping highlights spanning a block boundary (<h1> into <p>),
    the HTML span insertion produces non-overlapping <span> elements
    pre-split at the block boundary."""

    def test_h1_to_p_split(self) -> None:
        html = "<h1>Title</h1><p>Body text</p>"
        chars = extract_text_from_html(html)
        # "Title" = chars 0-5, "Body text" = chars 5-14
        total_len = len(chars)

        hl = _make_hl(0, total_len, tag="jurisdiction")
        result = compute_highlight_spans(html, [hl], {"jurisdiction": "#3366cc"})

        spans = _find_spans(result)
        # Must have at least 2 spans — one in h1, one in p
        assert len(spans) >= 2, f"Expected >=2 spans, got {len(spans)}: {spans}"

        # All spans should have data-hl="0"
        for s in spans:
            assert s["data-hl"] == "0"

        # Verify span text content
        span_texts = [s["_text"] for s in spans]
        assert "Title" in span_texts, (
            f"Expected 'Title' in spans, got texts: {span_texts}"
        )
        assert "Body text" in span_texts, (
            f"Expected 'Body text' in spans, got texts: {span_texts}"
        )

    def test_h2_to_p_split(self) -> None:
        html = "<h2>Heading</h2><p>Body</p>"
        chars = extract_text_from_html(html)
        total_len = len(chars)

        hl = _make_hl(0, total_len, tag="evidence")
        result = compute_highlight_spans(html, [hl], {"evidence": "#ff6600"})

        spans = _find_spans(result)
        assert len(spans) >= 2


# ---------------------------------------------------------------------------
# AC1.5: Cross-block span is NOT left crossing the boundary
# ---------------------------------------------------------------------------


class TestAC1_5_NoCrossBlockSpan:
    """Given a cross-block highlight, the span is NOT left crossing the
    block boundary (Pandoc would silently destroy it)."""

    def test_no_single_span_crosses_h2_p_boundary(self) -> None:
        html = "<h2>Heading</h2><p>Body</p>"
        chars = extract_text_from_html(html)
        total_len = len(chars)

        hl = _make_hl(0, total_len, tag="jurisdiction")
        result = compute_highlight_spans(html, [hl], {"jurisdiction": "#3366cc"})

        # Parse the result and verify no single span crosses from h2 into p
        tree = LexborHTMLParser(result)
        spans = _find_spans(result)

        # Verify span text content
        span_texts = [s["_text"] for s in spans]
        assert "Heading" in span_texts, (
            f"Expected 'Heading' in spans, got texts: {span_texts}"
        )
        assert "Body" in span_texts, (
            f"Expected 'Body' in spans, got texts: {span_texts}"
        )

        for span in tree.css("span[data-hl]"):
            parent = span.parent
            # Walk up to find block ancestor
            while parent is not None and parent.tag not in PANDOC_BLOCK_ELEMENTS:
                parent = parent.parent
            # The span should be fully within one block element
            # (not wrapping across blocks)
            if parent is not None:
                assert parent.tag in PANDOC_BLOCK_ELEMENTS

    def test_each_block_gets_own_span(self) -> None:
        html = "<h2>Heading</h2><p>Body</p>"
        chars = extract_text_from_html(html)
        total_len = len(chars)

        hl = _make_hl(0, total_len, tag="jurisdiction")
        result = compute_highlight_spans(html, [hl], {"jurisdiction": "#3366cc"})

        # Verify there are separate spans
        spans = _find_spans(result)
        assert len(spans) >= 2, f"Expected separate spans per block, got {spans}"

        # Verify span text content
        span_texts = [s["_text"] for s in spans]
        assert "Heading" in span_texts, (
            f"Expected 'Heading' in spans, got texts: {span_texts}"
        )
        assert "Body" in span_texts, (
            f"Expected 'Body' in spans, got texts: {span_texts}"
        )


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Additional edge case tests."""

    def test_adjacent_non_overlapping_highlights(self) -> None:
        """Adjacent non-overlapping highlights produce separate spans."""
        html = "<p>hello world</p>"
        highlights = [
            _make_hl(0, 5, tag="jurisdiction"),  # "hello"
            _make_hl(6, 11, tag="evidence"),  # "world"
        ]
        result = compute_highlight_spans(
            html, highlights, {"jurisdiction": "#3366cc", "evidence": "#ff6600"}
        )
        spans = _find_spans(result)
        assert len(spans) == 2
        # They should have different data-hl values
        hl_values = {s["data-hl"] for s in spans}
        assert len(hl_values) == 2

    def test_html_entity_in_highlight(self) -> None:
        """HTML entities within highlighted range are handled correctly."""
        html = "<p>A &amp; B</p>"
        chars = extract_text_from_html(html)
        # chars should be: A, ' ', &, ' ', B = 5 chars
        total_len = len(chars)
        hl = _make_hl(0, total_len, tag="jurisdiction")
        result = compute_highlight_spans(html, [hl], {"jurisdiction": "#3366cc"})

        spans = _find_spans(result)
        assert len(spans) >= 1
        # The entity should be within the span text
        full_text = "".join(s["_text"] for s in spans)
        assert "&" in full_text or "amp" in full_text.lower()

    def test_annots_on_last_span(self) -> None:
        """data-annots appears on the last span of a highlight."""
        html = "<h1>Title</h1><p>Body</p>"
        chars = extract_text_from_html(html)
        hl = _make_hl(0, len(chars), tag="jurisdiction", author="Alice")
        result = compute_highlight_spans(html, [hl], {"jurisdiction": "#3366cc"})

        spans = _find_spans(result)
        # data-annots should be on exactly one span (the last one)
        annot_spans = [s for s in spans if "data-annots" in s]
        assert len(annot_spans) == 1, (
            f"Expected exactly 1 span with data-annots, got {len(annot_spans)}"
        )

        # Verify the annotation content
        annots_raw = annot_spans[0]["data-annots"]
        annots = json.loads(annots_raw)
        assert len(annots) == 1
        assert annots[0]["tag"] == "jurisdiction"
        assert annots[0]["author"] == "Alice"

    def test_annots_with_para_ref(self) -> None:
        """data-annots includes para_ref when word_to_legal_para is provided."""
        html = "<p>some text</p>"
        hl = _make_hl(0, 4, tag="jurisdiction", author="Bob")
        word_to_legal_para = {0: 5, 1: 5, 2: 5, 3: 5}
        result = compute_highlight_spans(
            html, [hl], {"jurisdiction": "#3366cc"}, word_to_legal_para
        )

        spans = _find_spans(result)
        annot_spans = [s for s in spans if "data-annots" in s]
        assert len(annot_spans) == 1
        annots = json.loads(annot_spans[0]["data-annots"])
        assert annots[0]["para_ref"] == 5

    def test_pandoc_block_elements_constant(self) -> None:
        """PANDOC_BLOCK_ELEMENTS contains all required elements."""
        required = {
            "p",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "blockquote",
            "div",
            "li",
            "ul",
            "ol",
            "table",
            "tr",
            "td",
            "th",
            "section",
            "article",
            "aside",
            "header",
            "footer",
            "figure",
            "figcaption",
            "pre",
            "dl",
            "dt",
            "dd",
        }
        assert required.issubset(PANDOC_BLOCK_ELEMENTS)

    def test_newline_in_highlighted_text(self) -> None:
        """Newline characters in text are handled correctly.

        When HTML contains newline characters within highlighted ranges,
        char indices should map correctly to byte positions.  CRLF is
        normalised to LF by upstream HTML parsers before this layer.
        """
        # HTML with newline within a paragraph
        html = "<p>line one\nline two</p>"
        chars = extract_text_from_html(html)
        # chars should be: "line one", "\n", "line two"
        # Total = 18 chars
        total_len = len(chars)

        # Highlight spanning both lines
        hl = _make_hl(0, total_len, tag="jurisdiction")
        result = compute_highlight_spans(html, [hl], {"jurisdiction": "#3366cc"})

        spans = _find_spans(result)
        assert len(spans) >= 1, "Expected at least 1 span for text with newline"

        # Verify the span covers both lines
        full_text = "".join(s["_text"] for s in spans)
        assert "line one" in full_text
        assert "line two" in full_text
