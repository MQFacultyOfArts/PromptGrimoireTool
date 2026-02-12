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
