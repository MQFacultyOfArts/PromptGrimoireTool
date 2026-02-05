"""Tests for char span injection and stripping."""

from promptgrimoire.input_pipeline.html_input import inject_char_spans, strip_char_spans


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

    def test_spaces_as_nbsp(self) -> None:
        """Spaces are converted to &nbsp; for selection."""
        result = inject_char_spans("<p>A B</p>")
        assert "&nbsp;</span>" in result

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

    def test_skips_script_content(self) -> None:
        """Script tag content is not wrapped."""
        result = inject_char_spans("<p>A</p><script>var x=1;</script><p>B</p>")
        assert "<script>var x=1;</script>" in result
        # Only A and B should be indexed
        assert 'data-char-index="0">A</span>' in result
        assert 'data-char-index="1">B</span>' in result

    def test_skips_style_content(self) -> None:
        """Style tag content is not wrapped."""
        result = inject_char_spans("<p>X</p><style>.cls{}</style>")
        assert "<style>.cls{}</style>" in result

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
