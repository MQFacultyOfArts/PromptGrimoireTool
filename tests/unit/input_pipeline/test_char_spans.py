"""Tests for char span injection and stripping."""

from promptgrimoire.input_pipeline.html_input import (
    _strip_html_to_text,
    extract_chars_from_spans,
    extract_text_from_html,
    inject_char_spans,
    strip_char_spans,
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


class TestInjectCharSpans:
    """Tests for inject_char_spans()."""

    def test_simple_text(self) -> None:
        """Basic text gets wrapped character by character."""
        result = inject_char_spans("<p>Hi</p>")
        assert '<span class="char" data-char-index="0">' in result
        assert '<span class="char" data-char-index="1">' in result
        # H and i should be wrapped
        assert 'data-char-index="0">H</span>' in result
        assert 'data-char-index="1">i</span>' in result

    def test_preserves_tags(self) -> None:
        """HTML structure tags are preserved."""
        result = inject_char_spans("<div><p>A</p></div>")
        assert "<div>" in result
        assert "<p>" in result
        assert "</p>" in result
        assert "</div>" in result

    def test_sequential_indices(self) -> None:
        """Indices are sequential across elements."""
        result = inject_char_spans("<p>AB</p><p>CD</p>")
        assert 'data-char-index="0">A</span>' in result
        assert 'data-char-index="1">B</span>' in result
        assert 'data-char-index="2">C</span>' in result
        assert 'data-char-index="3">D</span>' in result

    def test_spaces_preserved(self) -> None:
        """Spaces are preserved as regular spaces (CSS handles visibility)."""
        result = inject_char_spans("<p>A B</p>")
        # Space should be wrapped in a char span (not converted to &nbsp;)
        assert 'data-char-index="1"> </span>' in result

    def test_br_as_newline(self) -> None:
        """<br> tags become newline characters with indices."""
        result = inject_char_spans("<p>A<br>B</p>")
        # br should be converted to a newline span
        assert 'data-char-index="1">\n</span>' in result

    def test_html_entities_preserved(self) -> None:
        """HTML entities are kept as single characters."""
        result = inject_char_spans("<p>&amp;</p>")
        # &amp; should be wrapped as one character
        assert "&amp;</span>" in result

    def test_strips_script_tags(self) -> None:
        """Script tags are stripped entirely (security: NiceGUI rejects them)."""
        result = inject_char_spans("<p>A</p><script>var x=1;</script><p>B</p>")
        # Script tag should be removed entirely
        assert "<script>" not in result
        assert "var x=1" not in result
        # Only A and B should be indexed
        assert 'data-char-index="0">A</span>' in result
        assert 'data-char-index="1">B</span>' in result

    def test_strips_style_tags(self) -> None:
        """Style tags are stripped entirely (security: NiceGUI rejects them)."""
        result = inject_char_spans("<p>X</p><style>.cls{}</style>")
        # Style tag should be removed entirely
        assert "<style>" not in result
        assert ".cls{}" not in result

    def test_strips_img_tags(self) -> None:
        """Img tags are stripped (removes base64 images from clipboard paste)."""
        result = inject_char_spans(
            '<p>A</p><img src="data:image/png;base64,abc123"><p>B</p>'
        )
        # Img tag should be removed entirely
        assert "<img" not in result
        assert "base64" not in result
        assert "abc123" not in result
        # Text content preserved with sequential indices
        assert 'data-char-index="0">A</span>' in result
        assert 'data-char-index="1">B</span>' in result

    def test_strips_img_self_closing(self) -> None:
        """Self-closing img tags are stripped."""
        result = inject_char_spans('<p>X</p><img src="test.png" />')
        assert "<img" not in result
        assert "test.png" not in result

    def test_attributes_preserved(self) -> None:
        """Element attributes are preserved."""
        result = inject_char_spans('<div class="foo" id="bar">X</div>')
        assert 'class="foo"' in result
        assert 'id="bar"' in result

    def test_empty_input(self) -> None:
        """Empty input returns empty output."""
        result = inject_char_spans("")
        assert result == ""

    def test_nested_elements(self) -> None:
        """Nested elements work correctly."""
        result = inject_char_spans("<div><span>AB</span></div>")
        assert 'data-char-index="0">A</span>' in result
        assert 'data-char-index="1">B</span>' in result

    def test_full_document_structure(self) -> None:
        """Full HTML documents are handled properly."""
        result = inject_char_spans("<!DOCTYPE html><html><body><p>Hi</p></body></html>")
        # Should preserve DOCTYPE and html structure
        assert "<!DOCTYPE html>" in result
        assert "<html>" in result
        assert "<body>" in result
        # Characters should be wrapped
        assert 'data-char-index="0">H</span>' in result
        assert 'data-char-index="1">i</span>' in result

    def test_special_chars_escaped(self) -> None:
        """Special HTML characters in text are escaped."""
        # Using a fragment without body - selectolax handles this as fragment
        result = inject_char_spans("<p>a&lt;b</p>")
        # The entity &lt; should be preserved as a single indexed character
        assert "&lt;</span>" in result


class TestStripCharSpans:
    """Tests for strip_char_spans()."""

    def test_roundtrip_simple(self) -> None:
        """Inject then strip returns similar content."""
        original = "<p>Hello</p>"
        injected = inject_char_spans(original)
        stripped = strip_char_spans(injected)
        # Should have text content back (may have &nbsp; for spaces)
        assert "Hello" in stripped or "H" in stripped

    def test_removes_char_spans(self) -> None:
        """Char spans are removed."""
        injected = '<p><span class="char" data-char-index="0">A</span></p>'
        stripped = strip_char_spans(injected)
        assert "data-char-index" not in stripped
        assert 'class="char"' not in stripped
        assert "A" in stripped

    def test_preserves_other_spans(self) -> None:
        """Non-char spans are kept."""
        html = '<p><span class="highlight">A</span></p>'
        result = strip_char_spans(html)
        assert 'class="highlight"' in result


class TestExtractCharsFromSpans:
    """Tests for extract_chars_from_spans()."""

    def test_extracts_simple_text(self) -> None:
        """Extracts characters in index order."""
        html = inject_char_spans("<p>Hi</p>")
        chars = extract_chars_from_spans(html)
        assert chars == ["H", "i"]

    def test_extracts_with_spaces(self) -> None:
        """Extracts spaces correctly."""
        html = inject_char_spans("<p>A B</p>")
        chars = extract_chars_from_spans(html)
        assert chars == ["A", " ", "B"]

    def test_empty_html(self) -> None:
        """Empty HTML returns empty list."""
        chars = extract_chars_from_spans("")
        assert chars == []

    def test_no_char_spans(self) -> None:
        """HTML without char spans returns empty list."""
        chars = extract_chars_from_spans("<p>Hello</p>")
        assert chars == []

    def test_roundtrip_preserves_text(self) -> None:
        """Inject then extract gives original characters."""
        original = "<p>Hello World</p>"
        injected = inject_char_spans(original)
        chars = extract_chars_from_spans(injected)
        assert "".join(chars) == "Hello World"


class TestExtractTextFromHtml:
    """Tests for extract_text_from_html() - clean HTML to char list.

    Used for client-side span injection architecture where we need to build
    document_chars from clean HTML (no char spans).
    """

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
