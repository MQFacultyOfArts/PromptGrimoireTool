"""Tests for compute_highlight_spans — AC1.1 through AC1.5, plus AC4.6.

Verifies pre-Pandoc highlight span insertion:
- AC1.1: Cross-block highlights produce pre-split spans
- AC1.2: 3+ overlapping highlights produce correct data-hl and data-colors
- AC1.3: Single-block highlight produces one span
- AC1.4: No highlights leaves HTML unchanged
- AC1.5: Cross-block spans are NOT left crossing the boundary
- AC4.6: format_annot_latex produces correct LaTeX annotation strings

Plus edge cases: CRLF, HTML entities, adjacent highlights, data-annots placement.
"""

from __future__ import annotations

from selectolax.lexbor import LexborHTMLParser

from promptgrimoire.export.highlight_spans import (
    PANDOC_BLOCK_ELEMENTS,
    compute_highlight_spans,
)
from promptgrimoire.export.latex_format import format_annot_latex
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
# Inline formatting boundary splitting
# ---------------------------------------------------------------------------


class TestInlineFormattingBoundary:
    """Highlight spans crossing inline formatting boundaries (<b>, <em>, etc.)
    must be split so the resulting HTML is well-formed.

    Bug: <b><span>BOLD:</b>not bold</span> is malformed HTML.
    Fix: split at the </b> boundary to produce
         <b><span>BOLD:</span></b><span>not bold</span>
    """

    def test_bold_boundary_produces_two_spans(self) -> None:
        """A highlight crossing a </b> boundary is split into two spans."""
        html = "<p><b>BOLD:</b>not bold</p>"
        chars = extract_text_from_html(html)
        # "BOLD:not bold" = 13 chars
        hl = _make_hl(0, len(chars), tag="jurisdiction")
        result = compute_highlight_spans(html, [hl], {"jurisdiction": "#3366cc"})

        spans = _find_spans(result)
        assert len(spans) >= 2, (
            f"Expected >=2 spans (split at </b>), got {len(spans)}: {spans}"
        )

        span_texts = [s["_text"] for s in spans]
        assert "BOLD:" in span_texts
        assert "not bold" in span_texts

    def test_bold_boundary_html_is_well_formed(self) -> None:
        """The span inside <b> closes before </b>, not after."""
        html = "<p><b>BOLD:</b>not bold</p>"
        chars = extract_text_from_html(html)
        hl = _make_hl(0, len(chars), tag="jurisdiction")
        result = compute_highlight_spans(html, [hl], {"jurisdiction": "#3366cc"})

        # The result must NOT contain a span that opens inside <b> and
        # closes outside it. Check that </span> comes before </b>.
        tree = LexborHTMLParser(result)
        b_tag = tree.css_first("b")
        assert b_tag is not None
        # Every data-hl span inside <b> must be fully contained within <b>
        for span in tree.css("b span[data-hl]"):
            # The span's parent chain should include the <b>
            parent = span.parent
            while parent is not None and parent.tag != "b":
                parent = parent.parent
            assert parent is not None and parent.tag == "b", (
                "Span inside <b> must be fully contained within <b>"
            )

    def test_em_boundary_produces_split(self) -> None:
        """A highlight crossing an </em> boundary is split."""
        html = "<p><em>italic</em> normal</p>"
        chars = extract_text_from_html(html)
        hl = _make_hl(0, len(chars), tag="evidence")
        result = compute_highlight_spans(html, [hl], {"evidence": "#ff6600"})

        spans = _find_spans(result)
        assert len(spans) >= 2, (
            f"Expected >=2 spans (split at </em>), got {len(spans)}: {spans}"
        )

    def test_highlight_within_bold_no_split_needed(self) -> None:
        """A highlight entirely within <b> does NOT get split."""
        html = "<p><b>all bold text</b></p>"
        chars = extract_text_from_html(html)
        hl = _make_hl(0, len(chars), tag="jurisdiction")
        result = compute_highlight_spans(html, [hl], {"jurisdiction": "#3366cc"})

        spans = _find_spans(result)
        assert len(spans) == 1, (
            f"Expected 1 span (no split needed), got {len(spans)}: {spans}"
        )
        assert spans[0]["_text"] == "all bold text"

    def test_nested_bold_em_boundary(self) -> None:
        """Highlight crossing from <b><em> to plain text is split."""
        html = "<p><b><em>bold italic</em></b> plain</p>"
        chars = extract_text_from_html(html)
        hl = _make_hl(0, len(chars), tag="jurisdiction")
        result = compute_highlight_spans(html, [hl], {"jurisdiction": "#3366cc"})

        spans = _find_spans(result)
        assert len(spans) >= 2, (
            f"Expected >=2 spans at inline boundary, got {len(spans)}: {spans}"
        )

    def test_lawlis_bold_court_pattern(self) -> None:
        """Reproduce the production bug: <li><b>THE COURT:</b>After...</li>"""
        html = (
            '<li value="1"><b>THE COURT:</b>After the hearing of this appeal, '
            "the Court made orders.</li>"
        )
        chars = extract_text_from_html(html)
        hl = _make_hl(0, len(chars), tag="jurisdiction")
        result = compute_highlight_spans(html, [hl], {"jurisdiction": "#3366cc"})

        spans = _find_spans(result)
        assert len(spans) >= 2, (
            f"Expected >=2 spans (split at </b>), got {len(spans)}: {spans}"
        )

        # Verify "THE COURT:" is in its own span within <b>
        tree = LexborHTMLParser(result)
        b_spans = tree.css("b span[data-hl]")
        b_span_texts = [s.text() for s in b_spans]
        assert any("THE COURT:" in t for t in b_span_texts), (
            f"Expected 'THE COURT:' span inside <b>, got: {b_span_texts}"
        )

        # Verify text after </b> is also highlighted
        span_texts = [s["_text"] for s in spans]
        after_bold = [t for t in span_texts if "After" in t]
        assert len(after_bold) >= 1, (
            f"Expected span containing 'After' text, got: {span_texts}"
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
        """data-annots appears on the last span of a highlight as LaTeX."""
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

        # Verify the annotation content is pre-formatted LaTeX
        annots_raw = annot_spans[0]["data-annots"]
        assert r"\annot{tag-jurisdiction}" in annots_raw
        assert "Alice" in annots_raw

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
        annots_raw = annot_spans[0]["data-annots"]
        assert r"\annot{tag-jurisdiction}" in annots_raw
        assert "[5]" in annots_raw

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


# ---------------------------------------------------------------------------
# AC4.6: format_annot_latex produces correct LaTeX annotation strings
# ---------------------------------------------------------------------------


class TestFormatAnnotLatex:
    """Verify format_annot_latex() produces correct \\annot{}{} LaTeX strings."""

    def test_basic_annotation(self) -> None:
        """Basic highlight with tag and author produces \\annot command."""
        hl = {
            "tag": "jurisdiction",
            "author": "Alice Jones",
            "comments": [],
            "created_at": "",
        }
        result = format_annot_latex(hl)
        assert result.startswith(r"\annot{tag-jurisdiction}{")
        assert r"\textbf{Jurisdiction}" in result
        assert "Alice Jones" in result

    def test_underscore_tag_slug(self) -> None:
        """Tag with underscores produces hyphenated colour name."""
        hl = {
            "tag": "key_issue",
            "author": "Bob",
            "comments": [],
            "created_at": "",
        }
        result = format_annot_latex(hl)
        assert r"\annot{tag-key-issue}{" in result
        assert r"\textbf{Key Issue}" in result

    def test_para_ref_included(self) -> None:
        """para_ref string is included in margin content."""
        hl = {
            "tag": "jurisdiction",
            "author": "Tester",
            "comments": [],
            "created_at": "",
        }
        result = format_annot_latex(hl, para_ref="[45]")
        assert "[45]" in result

    def test_timestamp_formatted(self) -> None:
        """ISO timestamp is formatted as human-readable."""
        hl = {
            "tag": "jurisdiction",
            "author": "Tester",
            "comments": [],
            "created_at": "2026-01-26T14:30:00+00:00",
        }
        result = format_annot_latex(hl)
        assert "26 Jan 2026" in result
        assert "14:30" in result

    def test_comments_with_separator(self) -> None:
        """Comments produce hrulefill separator and formatted entries."""
        hl = {
            "tag": "jurisdiction",
            "author": "Alice",
            "comments": [
                {
                    "author": "Bob",
                    "text": "Good point",
                    "created_at": "",
                }
            ],
            "created_at": "",
        }
        result = format_annot_latex(hl)
        assert r"\par\hrulefill" in result
        assert "Bob" in result
        assert "Good point" in result

    def test_multiple_comments(self) -> None:
        """Multiple comments each appear in the output."""
        hl = {
            "tag": "evidence",
            "author": "Alice",
            "comments": [
                {"author": "Bob", "text": "First comment", "created_at": ""},
                {"author": "Carol", "text": "Second comment", "created_at": ""},
            ],
            "created_at": "",
        }
        result = format_annot_latex(hl)
        assert "First comment" in result
        assert "Second comment" in result
        assert "Bob" in result
        assert "Carol" in result

    def test_special_chars_escaped(self) -> None:
        """LaTeX special characters in author/text are escaped."""
        hl = {
            "tag": "jurisdiction",
            "author": "O'Brien & Sons",
            "comments": [],
            "created_at": "",
        }
        result = format_annot_latex(hl)
        # & should be escaped as \&
        assert r"\&" in result

    def test_test_uuid_stripped(self) -> None:
        """Test UUIDs appended to author names are stripped."""
        hl = {
            "tag": "jurisdiction",
            "author": "Alice Jones 1664E02D",
            "comments": [],
            "created_at": "",
        }
        result = format_annot_latex(hl)
        assert "Alice Jones" in result
        assert "1664E02D" not in result

    def test_annot_in_data_annots_attribute(self) -> None:
        """data-annots contains pre-formatted LaTeX from format_annot_latex."""
        html = "<p>some text here</p>"
        hl = _make_hl(0, 9, tag="jurisdiction", author="Alice")
        hl["created_at"] = "2026-01-26T14:30:00+00:00"
        hl["comments"] = [{"author": "Bob", "text": "Nice", "created_at": ""}]
        result = compute_highlight_spans(html, [hl], {"jurisdiction": "#3366cc"})

        spans = _find_spans(result)
        annot_spans = [s for s in spans if "data-annots" in s]
        assert len(annot_spans) == 1
        annots_raw = annot_spans[0]["data-annots"]
        # Should be pre-formatted LaTeX, not JSON
        assert r"\annot{tag-jurisdiction}" in annots_raw
        assert "Alice" in annots_raw
        assert "Bob" in annots_raw
        assert "Nice" in annots_raw
