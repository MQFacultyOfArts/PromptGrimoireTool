"""Tests for paragraph mapping builder and source-number detection.

Covers acceptance criteria from paragraph-numbering-191 Phase 2:
- AC1: Auto-numbered documents (sequential paragraph numbers)
- AC2: Source-numbered documents (li[value] attributes)
- AC3: Auto-detection of source numbering
- AC8: Char-offset alignment with extract_text_from_html()
"""

from __future__ import annotations

import re

from selectolax.lexbor import LexborHTMLParser

from promptgrimoire.input_pipeline.paragraph_map import (
    build_paragraph_map,
    build_paragraph_map_for_json,
    detect_source_numbering,
    inject_paragraph_attributes,
    lookup_para_ref,
)

# Direct import of extract_text_from_html avoided due to circular import
# through export pipeline; constants and helper duplicated here instead.
_STRIP_TAGS = frozenset(("script", "style", "noscript", "template"))
_BLOCK_TAGS = frozenset(
    (
        "table",
        "tbody",
        "thead",
        "tfoot",
        "tr",
        "td",
        "th",
        "ul",
        "ol",
        "li",
        "dl",
        "dt",
        "dd",
        "div",
        "section",
        "article",
        "aside",
        "header",
        "footer",
        "nav",
        "main",
        "figure",
        "figcaption",
        "blockquote",
    )
)
_WHITESPACE_RUN = re.compile(r"[\s\u00a0]+")


def _extract_text(html: str) -> str:
    """Inline copy of html_input.extract_text_from_html for test assertions.

    Must stay in sync with html_input.extract_text_from_html if that
    function's traversal logic changes.
    """
    if not html:
        return ""
    tree = LexborHTMLParser(html)
    body = tree.body
    root = body if body else tree.root
    if root is None:
        return ""
    chars: list[str] = []

    def _walk(node: object) -> None:
        tag = node.tag  # type: ignore[attr-defined]
        if tag == "-text":
            text = node.text_content  # type: ignore[attr-defined]
            if not text:
                return
            parent = node.parent  # type: ignore[attr-defined]
            if (
                parent is not None
                and parent.tag in _BLOCK_TAGS
                and _WHITESPACE_RUN.fullmatch(text)
            ):
                return
            text = _WHITESPACE_RUN.sub(" ", text)
            chars.extend(text)
            return
        if tag in _STRIP_TAGS:
            return
        if tag == "br":
            chars.append("\n")
            return
        child = node.child  # type: ignore[attr-defined]
        while child is not None:
            _walk(child)
            child = child.next

    child = root.child
    while child is not None:
        _walk(child)
        child = child.next
    return "".join(chars)


class TestAutoNumberParagraphs:
    """AC1: Auto-numbered documents get sequential paragraph numbers."""

    def test_ac1_1_simple_paragraphs(self) -> None:
        """AC1.1: Plain prose with <p> elements gets sequential numbers 1, 2, 3."""
        html = "<p>First</p><p>Second</p><p>Third</p>"
        result = build_paragraph_map(html, auto_number=True)
        # Three paragraphs, numbered 1..3
        assert len(result) == 3
        values = sorted(result.values())
        assert values == [1, 2, 3]
        # Keys are offsets: "First" starts at 0, "Second" at 5, "Third" at 11
        assert result[0] == 1
        assert result[5] == 2
        assert result[11] == 3

    def test_ac1_2_mixed_block_elements(self) -> None:
        """AC1.2: <p> and <blockquote> numbered; <li> skipped in auto-number.

        List items are sub-structure, not discourse-level paragraphs.
        Only <p>, <blockquote>, and leaf <div> receive auto-numbers.
        """
        html = "<p>Text</p><blockquote>Quote</blockquote><ul><li>Item</li></ul>"
        result = build_paragraph_map(html, auto_number=True)
        assert len(result) == 2
        # "Text" at 0, "Quote" at 4; "Item" not numbered
        assert result[0] == 1
        assert result[4] == 2

    def test_blockquote_wrapping_p_not_double_counted(self) -> None:
        """Blockquote containing <p> children is a wrapper — only <p> gets numbered.

        Regression: blockquote consumed a para number then <p> overwrote the
        map entry, causing skipped numbers and double data-para attributes.
        """
        html = "<p>Before</p><blockquote><p>Quoted text</p></blockquote><p>After</p>"
        result = build_paragraph_map(html, auto_number=True)
        # Three paragraphs: "Before", "Quoted text", "After" — no skipped numbers
        assert sorted(result.values()) == [1, 2, 3]

    def test_blockquote_wrapping_multiple_p(self) -> None:
        """Blockquote wrapping multiple <p> children — each <p> gets a number."""
        html = "<blockquote><p>First quote</p><p>Second quote</p></blockquote>"
        result = build_paragraph_map(html, auto_number=True)
        assert sorted(result.values()) == [1, 2]

    def test_leaf_blockquote_numbered(self) -> None:
        """Blockquote with only text (no block children) gets a paragraph number."""
        html = "<p>Before</p><blockquote>Direct quote text</blockquote><p>After</p>"
        result = build_paragraph_map(html, auto_number=True)
        assert sorted(result.values()) == [1, 2, 3]

    def test_ac1_3_br_br_creates_new_paragraph(self) -> None:
        """AC1.3: <br><br>+ sequences within a block create new paragraph numbers."""
        html = "<p>Line one<br><br>Line two</p>"
        result = build_paragraph_map(html, auto_number=True)
        # Two paragraphs: "Line one" and "Line two"
        assert len(result) == 2
        assert result[0] == 1
        # "Line two" starts at offset 10 (after "Line one\n\n")
        assert result[10] == 2

    def test_ac1_4_single_br_no_split(self) -> None:
        """AC1.4: Single <br> within a block does NOT create new paragraph number."""
        html = "<p>Line one<br>Line two</p>"
        result = build_paragraph_map(html, auto_number=True)
        # Only one paragraph -- single br does not split
        assert len(result) == 1
        assert result[0] == 1

    def test_ac1_5_headers_skipped(self) -> None:
        """AC1.5: Headers (h1-h6) are not numbered."""
        html = "<h1>Title</h1><p>Body</p>"
        result = build_paragraph_map(html, auto_number=True)
        # Only the <p> gets a number
        assert len(result) == 1
        # "Title" is at 0-4, "Body" starts at 5
        assert result[5] == 1

    def test_ac1_6_empty_whitespace_blocks_skipped(self) -> None:
        """AC1.6: Empty/whitespace-only blocks are not numbered."""
        html = "<p>   </p><p>Real content</p>"
        result = build_paragraph_map(html, auto_number=True)
        # Only "Real content" gets a number
        assert len(result) == 1
        # Whitespace-only <p> produces a space at offset 0, then "Real content" at 1
        assert result[1] == 1

    def test_ac1_6b_truly_empty_block_skipped(self) -> None:
        """AC1.6: Truly empty <p></p> (no children) is not numbered."""
        html = "<p></p><p>Real</p>"
        result = build_paragraph_map(html, auto_number=True)
        # Only "Real" gets a number; the empty <p> must not be counted
        assert len(result) == 1
        assert 1 in result.values()

    def test_ac1_7_markdown_style_br_br(self) -> None:
        """AC1.7: Pasted markdown with br-br breaks produces sensible numbering."""
        html = (
            "<p>Paragraph one text<br><br>"
            "Paragraph two text<br><br>"
            "Paragraph three text</p>"
        )
        result = build_paragraph_map(html, auto_number=True)
        assert len(result) == 3
        values = sorted(result.values())
        assert values == [1, 2, 3]


class TestSourceNumberParagraphs:
    """AC2: Source-numbered documents use <li value> attributes."""

    def test_ac2_1_numbered_list(self) -> None:
        """AC2.1: AustLII-style numbered list uses li[value] numbers."""
        items = "".join(
            f'<li value="{i}">Paragraph {i} text</li>' for i in range(1, 43)
        )
        html = f"<ol>{items}</ol>"
        result = build_paragraph_map(html, auto_number=False)
        assert len(result) == 42
        # All values should be 1..42
        assert sorted(result.values()) == list(range(1, 43))

    def test_ac2_2_gaps_preserved(self) -> None:
        """AC2.2: Gaps in source numbering are preserved."""
        html = '<ol><li value="1">First</li><li value="5">Fifth</li></ol>'
        result = build_paragraph_map(html, auto_number=False)
        assert len(result) == 2
        values = sorted(result.values())
        assert values == [1, 5]

    def test_ac2_3_non_numbered_blocks_no_entry(self) -> None:
        """AC2.3: Non-numbered block elements between numbered items have no entry."""
        html = '<ol><li value="1">Numbered</li></ol><p>Unnumbered</p>'
        result = build_paragraph_map(html, auto_number=False)
        # Only the <li> with value gets an entry
        assert len(result) == 1
        assert 0 in result
        assert result[0] == 1


class TestDetectSourceNumbering:
    """AC3: Auto-detection of source numbering."""

    def test_ac3_1_detects_source_numbered(self) -> None:
        """AC3.1: HTML with 2+ li[value] elements returns True."""
        html = '<ol><li value="1">A</li><li value="2">B</li><li value="3">C</li></ol>'
        assert detect_source_numbering(html) is True

    def test_ac3_2_no_source_numbering_zero(self) -> None:
        """AC3.2: HTML with 0 li[value] elements returns False."""
        html = "<p>Just paragraphs</p><p>No numbering</p>"
        assert detect_source_numbering(html) is False

    def test_ac3_2_no_source_numbering_one(self) -> None:
        """AC3.2: HTML with exactly 1 li[value] element returns False."""
        html = '<ol><li value="1">Only one</li><li>No value</li></ol>'
        assert detect_source_numbering(html) is False

    def test_detects_two_threshold(self) -> None:
        """Exactly 2 li[value] elements returns True (boundary)."""
        html = '<ol><li value="1">A</li><li value="2">B</li></ol>'
        assert detect_source_numbering(html) is True


class TestCharOffsetAlignment:
    """AC8: Char offsets in paragraph map must align with extract_text_from_html."""

    def _verify_alignment(self, html: str, *, auto_number: bool = True) -> None:
        """Helper: verify all map keys are valid indices into extracted text."""
        text = _extract_text(html)
        result = build_paragraph_map(html, auto_number=auto_number)
        for offset, para_num in result.items():
            assert 0 <= offset < len(text), (
                f"Offset {offset} out of range for text of length {len(text)} "
                f"(para_num={para_num}, text={text!r})"
            )

    def test_ac8_1_simple_paragraphs_aligned(self) -> None:
        """AC8.1: Simple paragraphs have valid char offsets."""
        self._verify_alignment("<p>First</p><p>Second</p><p>Third</p>")

    def test_ac8_1_mixed_elements_aligned(self) -> None:
        """AC8.1: Mixed block elements have valid char offsets."""
        self._verify_alignment(
            "<p>Text</p><blockquote>Quote</blockquote><ul><li>Item</li></ul>"
        )

    def test_ac8_1_br_br_aligned(self) -> None:
        """AC8.1: br-br split offsets are valid."""
        self._verify_alignment("<p>Line one<br><br>Line two</p>")

    def test_ac8_1_source_numbered_aligned(self) -> None:
        """AC8.1: Source-numbered list offsets are valid."""
        self._verify_alignment(
            '<ol><li value="1">First</li><li value="5">Fifth</li></ol>',
            auto_number=False,
        )

    def test_ac8_1_header_with_body_aligned(self) -> None:
        """AC8.1: Header + body offsets are valid."""
        self._verify_alignment("<h1>Title</h1><p>Body</p>")

    def test_ac8_1_whitespace_only_aligned(self) -> None:
        """AC8.1: Whitespace-only blocks produce valid offsets."""
        self._verify_alignment("<p>   </p><p>Real content</p>")

    def test_ac8_1_offsets_point_to_correct_text(self) -> None:
        """AC8.1: Offsets point to first char of paragraph text content."""
        html = "<p>Alpha</p><p>Beta</p>"
        text = _extract_text(html)
        result = build_paragraph_map(html, auto_number=True)
        # Paragraph 1 starts at 'A' (offset 0)
        assert text[next(iter(result))] == "A"
        offsets = sorted(result.keys())
        assert text[offsets[0]] == "A"
        assert text[offsets[1]] == "B"


class TestInjectParagraphAttributes:
    """AC4: Paragraph numbers injected as data-para attributes for margin display."""

    def test_ac4_1_auto_numbered_paragraphs(self) -> None:
        """AC4.1: Auto-numbered HTML gets data-para on each <p>."""
        html = "<p>A</p><p>B</p><p>C</p>"
        para_map = build_paragraph_map_for_json(html, auto_number=True)
        result = inject_paragraph_attributes(html, para_map)
        tree = LexborHTMLParser(result)
        paras = tree.css("p[data-para]")
        assert len(paras) == 3
        assert paras[0].attributes["data-para"] == "1"
        assert paras[1].attributes["data-para"] == "2"
        assert paras[2].attributes["data-para"] == "3"

    def test_ac4_2_source_numbered_li(self) -> None:
        """AC4.2: Source-numbered <li value> gets data-para from map."""
        html = '<ol><li value="5">Fifth</li><li value="10">Tenth</li></ol>'
        para_map = build_paragraph_map_for_json(html, auto_number=False)
        result = inject_paragraph_attributes(html, para_map)
        tree = LexborHTMLParser(result)
        items = tree.css("li[data-para]")
        assert len(items) == 2
        assert items[0].attributes["data-para"] == "5"
        assert items[1].attributes["data-para"] == "10"

    def test_ac4_3_headers_not_attributed(self) -> None:
        """AC4.3: Headers do NOT get data-para attributes."""
        html = "<h1>Title</h1><p>Body</p>"
        para_map = build_paragraph_map_for_json(html, auto_number=True)
        result = inject_paragraph_attributes(html, para_map)
        tree = LexborHTMLParser(result)
        # Header must not have data-para
        headers = tree.css("h1[data-para]")
        assert len(headers) == 0
        # Paragraph should have it
        paras = tree.css("p[data-para]")
        assert len(paras) == 1
        assert paras[0].attributes["data-para"] == "1"

    def test_empty_map_returns_unchanged(self) -> None:
        """Empty paragraph map returns HTML unchanged (no parsing overhead)."""
        html = "<p>Hello</p>"
        result = inject_paragraph_attributes(html, {})
        assert result == html

    def test_empty_html_returns_unchanged(self) -> None:
        """Empty HTML string returns unchanged."""
        result = inject_paragraph_attributes("", {"0": 1})
        assert result == ""

    def test_data_para_values_are_strings(self) -> None:
        """CSS attr() reads string values; data-para must be string."""
        html = "<p>Text</p>"
        para_map = {"0": 42}
        result = inject_paragraph_attributes(html, para_map)
        tree = LexborHTMLParser(result)
        p = tree.css_first("p[data-para]")
        assert p is not None
        # The attribute value is always a string in HTML
        assert p.attributes["data-para"] == "42"

    def test_br_br_pseudo_paragraph(self) -> None:
        """br-br split text gets a <span data-para> wrapper."""
        html = "<p>Line one<br><br>Line two</p>"
        para_map = build_paragraph_map_for_json(html, auto_number=True)
        result = inject_paragraph_attributes(html, para_map)
        tree = LexborHTMLParser(result)
        # The <p> should have data-para for the first paragraph
        p = tree.css_first("p[data-para]")
        assert p is not None
        assert p.attributes["data-para"] == "1"
        # The br-br pseudo-paragraph should have a span wrapper
        span = tree.css_first("span[data-para]")
        assert span is not None
        assert span.attributes["data-para"] == "2"

    def test_br_br_pseudo_paragraph_with_html_entity(self) -> None:
        """br-br text containing HTML entities gets wrapped correctly."""
        html = "<p>Line one<br><br>Line &amp; value</p>"
        para_map = build_paragraph_map_for_json(html, auto_number=True)
        result = inject_paragraph_attributes(html, para_map)
        tree = LexborHTMLParser(result)
        # The br-br pseudo-paragraph with entity should have a span wrapper
        span = tree.css_first("span[data-para]")
        assert span is not None
        assert span.attributes["data-para"] == "2"
        # The entity should be preserved in the output
        assert "&amp;" in result or "& value" in span.text()

    def test_blockquote_wrapping_p_no_double_attribute(self) -> None:
        """Blockquote wrapping <p> — only the <p> gets data-para, not the blockquote.

        Regression: both blockquote and inner <p> got data-para at the same
        offset, causing overlapping paragraph numbers in the margin.
        """
        html = "<p>Before</p><blockquote><p>Quoted</p></blockquote><p>After</p>"
        para_map = build_paragraph_map_for_json(html, auto_number=True)
        result = inject_paragraph_attributes(html, para_map)
        tree = LexborHTMLParser(result)
        # Only <p> elements should have data-para, not <blockquote>
        bq_with_para = tree.css("blockquote[data-para]")
        assert len(bq_with_para) == 0, (
            f"Blockquote should NOT have data-para, found: "
            f"{[bq.attributes for bq in bq_with_para]}"
        )
        p_with_para = tree.css("p[data-para]")
        assert len(p_with_para) == 3
        assert [p.attributes["data-para"] for p in p_with_para] == ["1", "2", "3"]

    def test_elements_not_in_map_unchanged(self) -> None:
        """Elements whose offsets are NOT in the map get no data-para."""
        html = "<p>First</p><p>Second</p><p>Third</p>"
        # Only map the first paragraph
        para_map = {"0": 1}
        result = inject_paragraph_attributes(html, para_map)
        tree = LexborHTMLParser(result)
        attributed = tree.css("[data-para]")
        assert len(attributed) == 1
        assert attributed[0].attributes["data-para"] == "1"


class TestLookupParaRef:
    """AC5: Annotation cards display paragraph references from char offsets."""

    def test_ac5_1_single_paragraph(self) -> None:
        """AC5.1: Highlight within one paragraph returns '[N]'."""
        para_map = {"0": 1, "10": 2, "20": 3}
        assert lookup_para_ref(para_map, start_char=10, end_char=15) == "[2]"

    def test_ac5_2_spanning_paragraphs(self) -> None:
        """AC5.2: Highlight spanning multiple paragraphs returns '[N]-[M]'."""
        para_map = {"0": 1, "10": 2, "20": 3}
        assert lookup_para_ref(para_map, start_char=10, end_char=25) == "[2]-[3]"

    def test_ac5_4_before_first_paragraph(self) -> None:
        """AC5.4: Highlight before first mapped paragraph returns empty string."""
        para_map = {"10": 1, "20": 2}
        assert lookup_para_ref(para_map, start_char=0, end_char=5) == ""

    def test_empty_map(self) -> None:
        """Empty paragraph map returns empty string."""
        assert lookup_para_ref({}, start_char=0, end_char=10) == ""

    def test_single_paragraph_map(self) -> None:
        """Single-entry map returns '[1]' for any position at or after the offset."""
        para_map = {"0": 1}
        assert lookup_para_ref(para_map, start_char=5, end_char=15) == "[1]"

    def test_exactly_at_boundary(self) -> None:
        """Highlight starting exactly at a paragraph boundary gets that paragraph."""
        para_map = {"0": 1, "10": 2, "20": 3}
        assert lookup_para_ref(para_map, start_char=20, end_char=25) == "[3]"

    def test_end_exactly_at_next_boundary(self) -> None:
        """End exactly at next boundary includes that paragraph."""
        para_map = {"0": 1, "10": 2, "20": 3}
        # end_char=20 means bisect_right finds offset 20, so end lands in para 3
        assert lookup_para_ref(para_map, start_char=5, end_char=20) == "[1]-[3]"

    def test_source_numbered_gaps(self) -> None:
        """Source-numbered map with gaps (e.g. [1], [5]) works correctly."""
        para_map = {"0": 1, "50": 5, "100": 10}
        assert lookup_para_ref(para_map, start_char=60, end_char=110) == "[5]-[10]"

    def test_start_and_end_in_same_first_paragraph(self) -> None:
        """Highlight fully within the first paragraph returns '[1]'."""
        para_map = {"0": 1, "10": 2, "20": 3}
        assert lookup_para_ref(para_map, start_char=0, end_char=5) == "[1]"
