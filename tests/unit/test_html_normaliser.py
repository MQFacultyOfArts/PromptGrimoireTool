"""Tests for HTML normaliser that wraps styled <p> tags for Pandoc."""

from promptgrimoire.export.html_normaliser import normalise_styled_paragraphs


class TestNormaliseStyledParagraphs:
    """Test wrapping styled <p> tags in <div> wrappers."""

    def test_wraps_styled_paragraph(self):
        """A <p style="..."> should be wrapped in <div style="...">."""
        html = '<p style="margin-left: 0.94in">Content</p>'
        result = normalise_styled_paragraphs(html)

        # The div should have the style, the p should not
        assert '<div style="margin-left: 0.94in">' in result
        assert "<p>Content</p>" in result
        # p should no longer have style attribute
        assert "<p style=" not in result

    def test_preserves_unstyled_paragraphs(self):
        """Paragraphs without style attributes should be unchanged."""
        html = "<p>Plain content</p>"
        result = normalise_styled_paragraphs(html)

        assert "<p>Plain content</p>" in result
        assert "<div" not in result

    def test_handles_multiple_styled_paragraphs(self):
        """Multiple styled paragraphs should each get their own wrapper."""
        html = """
        <p style="margin-left: 1in">First</p>
        <p style="margin-left: 2in">Second</p>
        """
        result = normalise_styled_paragraphs(html)

        assert '<div style="margin-left: 1in">' in result
        assert '<div style="margin-left: 2in">' in result
        # Each styled paragraph gets its own wrapper div
        assert result.count('<div style="margin-left:') == 2

    def test_preserves_nested_elements(self):
        """Nested elements inside <p> should be preserved."""
        html = (
            '<p style="margin-left: 1in"><strong>Bold</strong> and <em>italic</em></p>'
        )
        result = normalise_styled_paragraphs(html)

        assert "<strong>Bold</strong>" in result
        assert "<em>italic</em>" in result

    def test_preserves_other_p_attributes(self):
        """Other attributes on <p> (like class, id) should be preserved."""
        html = '<p style="margin-left: 1in" class="legal" id="para1">Content</p>'
        result = normalise_styled_paragraphs(html)

        # Style moves to div
        assert '<div style="margin-left: 1in">' in result
        # Other attributes stay on p
        assert 'class="legal"' in result
        assert 'id="para1"' in result

    def test_handles_complex_style_attribute(self):
        """Complex style attributes with multiple properties should be preserved."""
        html = (
            '<p style="margin-left: 0.94in; line-height: 150%; '
            'text-indent: 0.5in">Content</p>'
        )
        result = normalise_styled_paragraphs(html)

        # The full style should be on the div
        assert "margin-left: 0.94in" in result
        assert "line-height: 150%" in result
        assert "text-indent: 0.5in" in result

    def test_does_not_double_wrap_already_wrapped(self):
        """If a styled <p> is already inside a <div>, don't create nested wrappers."""
        # This tests that we don't create <div><div><p>
        html = '<div><p style="margin-left: 1in">Content</p></div>'
        result = normalise_styled_paragraphs(html)

        # Should have exactly 2 divs - the original outer and the new wrapper
        # The structure should be <div><div style="..."><p>Content</p></div></div>
        assert result.count("<div") == 2

    def test_handles_mixed_content(self):
        """Mix of styled and unstyled paragraphs should be handled correctly."""
        html = """
        <p>Unstyled</p>
        <p style="margin-left: 1in">Styled</p>
        <p>Another unstyled</p>
        """
        result = normalise_styled_paragraphs(html)

        # Only one styled div wrapper (lxml may add a container for fragments)
        assert result.count('<div style="margin-left: 1in">') == 1
        # Unstyled paragraphs remain without wrappers
        assert "<p>Unstyled</p>" in result
        assert "<p>Another unstyled</p>" in result

    def test_handles_empty_document(self):
        """Empty or whitespace-only input should not crash."""
        assert normalise_styled_paragraphs("") == ""
        assert normalise_styled_paragraphs("   ").strip() == ""

    def test_handles_document_with_no_paragraphs(self):
        """Document with no <p> tags should pass through unchanged."""
        html = "<div><span>Content</span></div>"
        result = normalise_styled_paragraphs(html)

        assert "<span>Content</span>" in result

    def test_preserves_html_structure(self):
        """Overall document structure should be preserved."""
        html = """<!DOCTYPE html>
<html>
<head><title>Test</title></head>
<body>
<p style="margin-left: 1in">Content</p>
</body>
</html>"""
        result = normalise_styled_paragraphs(html)

        assert "<html>" in result
        assert "<body>" in result
        assert '<div style="margin-left: 1in">' in result

    def test_handles_real_libreoffice_output(self):
        """Test with realistic LibreOffice HTML output."""
        html = """<p lang="en-AU" style="margin-left: 0.94in; line-height: 150%">
        <font face="Courier New, monospace"><font size="2" style="font-size: 10pt">
        (a) the injured person; or
        </font></font></p>"""
        result = normalise_styled_paragraphs(html)

        # Style should be on a wrapper div
        assert "<div style=" in result
        assert "margin-left: 0.94in" in result
        # lang attribute should stay on p
        assert 'lang="en-AU"' in result
        # Content should be preserved
        assert "(a) the injured person; or" in result
