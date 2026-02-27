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
    detect_source_numbering,
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
        """AC1.2: Mixed block elements (<p>, <blockquote>, <li>) all numbered."""
        html = "<p>Text</p><blockquote>Quote</blockquote><ul><li>Item</li></ul>"
        result = build_paragraph_map(html, auto_number=True)
        assert len(result) == 3
        values = sorted(result.values())
        assert values == [1, 2, 3]
        # "Text" at 0, "Quote" at 4, "Item" at 9
        assert result[0] == 1
        assert result[4] == 2
        assert result[9] == 3

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
