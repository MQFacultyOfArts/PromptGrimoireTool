"""Tests for text extraction from HTML.

Kept from the original test_char_spans.py after char-span functions
were removed (Phase 3, Task 5). The char-span parity test is replaced
by JS/Python parity tests in tests/integration/test_text_walker_parity.py.
"""

from promptgrimoire.input_pipeline.html_input import (
    _strip_html_to_text,
    extract_text_from_html,
)


class TestStripHtmlToText:
    """Tests for _strip_html_to_text() - QEditor HTML to plain text."""

    def test_strips_div_tags(self) -> None:
        """Div tags from QEditor become newlines."""
        html = "<div>line1</div><div>line2</div>"
        result = _strip_html_to_text(html)
        assert "line1" in result
        assert "line2" in result

    def test_strips_br_tags(self) -> None:
        """BR tags become newlines."""
        html = "line1<br>line2"
        result = _strip_html_to_text(html)
        assert "line1" in result
        assert "line2" in result

    def test_empty_input(self) -> None:
        """Empty input returns empty string."""
        assert _strip_html_to_text("") == ""

    def test_plain_text_passthrough(self) -> None:
        """Plain text without tags passes through."""
        text = "just plain text"
        result = _strip_html_to_text(text)
        assert result.strip() == text


class TestExtractTextFromHtml:
    """Tests for extract_text_from_html() - clean HTML to char list.

    Must match client-side JS walkTextNodes behaviour exactly so
    that server-side document_chars indices agree with client-side
    text walker output.
    """

    # --- Basic tests ---

    def test_simple_text(self) -> None:
        """Extracts text from simple paragraph."""
        chars = extract_text_from_html("<p>Hello</p>")
        assert "".join(chars) == "Hello"

    def test_multiple_paragraphs(self) -> None:
        """Extracts text from multiple paragraphs."""
        chars = extract_text_from_html("<p>A</p><p>B</p>")
        text = "".join(chars)
        assert "A" in text
        assert "B" in text

    def test_nested_elements(self) -> None:
        """Extracts text from nested elements."""
        chars = extract_text_from_html("<div><span>Hi</span></div>")
        assert "".join(chars) == "Hi"

    def test_empty_html(self) -> None:
        """Empty HTML returns empty list."""
        assert extract_text_from_html("") == []

    def test_preserves_spaces(self) -> None:
        """Spaces are preserved as characters."""
        chars = extract_text_from_html("<p>A B</p>")
        assert " " in chars
        assert "".join(chars) == "A B"

    def test_full_document(self) -> None:
        """Works with full HTML document structure."""
        html = "<!DOCTYPE html><html><body><p>Test</p></body></html>"
        chars = extract_text_from_html(html)
        assert "".join(chars) == "Test"

    # --- Parity with client-side JS text walker ---

    def test_br_becomes_newline(self) -> None:
        """<br> tags are counted as newline characters."""
        chars = extract_text_from_html("<p>A<br>B</p>")
        assert "".join(chars) == "A\nB"

    def test_multiple_br_tags(self) -> None:
        """Multiple <br> tags each produce a newline."""
        chars = extract_text_from_html("<p>A<br><br>B</p>")
        assert "".join(chars) == "A\n\nB"

    def test_whitespace_only_text_in_block_skipped(
        self,
    ) -> None:
        """Whitespace-only text in block containers is removed."""
        html = "<ul>\n  <li>A</li>\n  <li>B</li>\n</ul>"
        chars = extract_text_from_html(html)
        text = "".join(chars)
        assert "A" in text
        assert "B" in text
        assert text.strip() == text

    def test_whitespace_collapse(self) -> None:
        """Whitespace runs are collapsed to a single space."""
        chars = extract_text_from_html("<p>A   B</p>")
        assert "".join(chars) == "A B"

    def test_tab_and_newline_collapse(self) -> None:
        """Tabs and newlines in text nodes collapse to space."""
        chars = extract_text_from_html("<p>A\t\n\tB</p>")
        assert "".join(chars) == "A B"

    def test_script_tag_skipped(self) -> None:
        """Script tags and content are excluded entirely."""
        chars = extract_text_from_html("<p>A</p><script>var x = 1;</script><p>B</p>")
        text = "".join(chars)
        assert "var" not in text
        assert "A" in text
        assert "B" in text

    def test_style_tag_skipped(self) -> None:
        """Style tags and content are excluded entirely."""
        chars = extract_text_from_html("<p>X</p><style>.cls{}</style><p>Y</p>")
        text = "".join(chars)
        assert ".cls" not in text
        assert "X" in text
        assert "Y" in text

    def test_noscript_tag_skipped(self) -> None:
        """Noscript tags and content are excluded."""
        chars = extract_text_from_html("<p>A</p><noscript>Enable JS</noscript><p>B</p>")
        text = "".join(chars)
        assert "Enable" not in text

    def test_template_tag_skipped(self) -> None:
        """Template tags and content are excluded."""
        chars = extract_text_from_html(
            "<p>A</p><template><p>hidden</p></template><p>B</p>"
        )
        text = "".join(chars)
        assert "hidden" not in text

    def test_html_entities_decoded(self) -> None:
        """HTML entities are decoded to characters."""
        chars = extract_text_from_html("<p>&amp; &lt; &gt;</p>")
        text = "".join(chars)
        assert "&" in text
        assert "<" in text
        assert ">" in text

    def test_nbsp_collapsed_to_space(self) -> None:
        """Non-breaking spaces collapse with whitespace."""
        chars = extract_text_from_html("<p>A&nbsp;B</p>")
        text = "".join(chars)
        assert text == "A B"

    def test_inline_element_whitespace_preserved(
        self,
    ) -> None:
        """Whitespace inside inline elements is preserved."""
        chars = extract_text_from_html("<p><span>A </span><span>B</span></p>")
        text = "".join(chars)
        assert text == "A B"

    # --- Bug #267: inter-paragraph whitespace must not produce phantom chars ---

    def test_inter_paragraph_newlines_skipped(self) -> None:
        """Whitespace-only text nodes between paragraphs must be skipped.

        Bug #267: extract_text_from_html parses standalone HTML where
        inter-paragraph whitespace (e.g. ``\\n\\n`` between ``</p>``
        and ``<p>``) has parent ``<body>``.  But the browser renders
        inside ``<div id="doc-container">`` where the same whitespace
        has parent ``<div>`` — a block container.  The JS walker skips
        whitespace-only text in block containers, so the Python walker
        must match.

        Without this fix, each inter-paragraph gap adds a phantom
        space character, causing cumulative negative drift in
        annotation citation offsets.
        """
        # Standalone HTML: \n\n between paragraphs, parent is <body>
        html = "<html><body><p>AAA</p>\n\n<p>BBB</p>\n\n<p>CCC</p></body></html>"
        chars = extract_text_from_html(html)
        text = "".join(chars)

        # Must NOT contain phantom spaces between paragraph text.
        # "AAABBBCCC" is what the browser's JS walker produces.
        assert text == "AAABBBCCC", (
            f"Phantom whitespace between paragraphs: {text!r}. "
            f"Expected 'AAABBBCCC' (9 chars), got {len(text)} chars. "
            f"Inter-paragraph whitespace nodes with parent <body> must "
            f"be skipped, same as <div> parents."
        )

    def test_inter_paragraph_whitespace_with_comment_fragment(self) -> None:
        """Real-world Word paste HTML with fragments and o:p tags.

        Reproduces the exact structure from bug #267 production data:
        Word-pasted legal documents with ``<!--StartFragment-->``,
        ``<o:p></o:p>`` namespace tags, and ``\\n\\n`` between paragraphs.
        """
        html = (
            "<!--StartFragment--><html><head></head><body>"
            "<p>Court of Criminal Appeal<o:p></o:p></p>\n\n"
            "<p>Case Name: Shen v R<o:p></o:p></p>\n\n"
            "<p>Citation: [2024] NSWCCA 252<o:p></o:p></p>"
            "<!--EndFragment--></body></html>"
        )
        chars = extract_text_from_html(html)
        text = "".join(chars)

        # "Shen v R" must start at the same offset regardless of
        # whether parsed standalone or inside a <div>
        shen_pos = text.find("Shen v R")
        assert shen_pos != -1, f"'Shen v R' not found in extracted text: {text!r}"

        # Without phantom spaces: "Court of Criminal Appeal" (24)
        # + "Case Name: " (11) = 35 chars before "Shen v R"
        expected_prefix = "Court of Criminal AppealCase Name: "
        assert text[:shen_pos] == expected_prefix, (
            f"Offset drift detected: text before 'Shen v R' is "
            f"{text[:shen_pos]!r} ({shen_pos} chars), "
            f"expected {expected_prefix!r} ({len(expected_prefix)} chars). "
            f"Delta: {shen_pos - len(expected_prefix)} phantom chars from "
            f"inter-paragraph whitespace."
        )

    def test_body_and_html_treated_as_block_containers(self) -> None:
        """<body> and <html> must skip whitespace-only children.

        Both <body> and <html> are block-level containers. Whitespace-only
        text nodes that are direct children of these elements are formatting
        indentation, not document content — same as whitespace inside <div>,
        <table>, etc.
        """
        # Whitespace between block children of <body>
        html = "<html><body>\n<p>X</p>\n<p>Y</p>\n</body></html>"
        chars = extract_text_from_html(html)
        text = "".join(chars)
        assert text == "XY", (
            f"Whitespace-only text nodes in <body> should be skipped: {text!r}"
        )
