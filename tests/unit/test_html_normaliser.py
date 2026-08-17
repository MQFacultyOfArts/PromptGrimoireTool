"""Tests for HTML normaliser that wraps styled <p> tags for Pandoc."""

from promptgrimoire.export.html_normaliser import (
    normalise_styled_paragraphs,
    strip_scripts_and_styles,
)


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


class TestStripScriptsAndStyles:
    """Characterisation tests for strip_scripts_and_styles, written before
    decomposing it -- it previously had no dedicated coverage of the
    script/style/noscript removal, tail-text preservation, or event-handler
    stripping branches that drive most of its cognitive complexity.
    """

    def test_removes_script_and_content(self):
        html = "<div><p>keep</p><script>alert(1)</script></div>"
        result = strip_scripts_and_styles(html)
        assert "<script" not in result
        assert "alert" not in result
        assert "<p>keep</p>" in result

    def test_removes_style_and_content(self):
        html = "<div><style>.x{color:red}</style><p>keep</p></div>"
        result = strip_scripts_and_styles(html)
        assert "<style" not in result
        assert "color:red" not in result
        assert "<p>keep</p>" in result

    def test_removes_noscript_and_content(self):
        html = "<div><noscript>fallback text</noscript><p>keep</p></div>"
        result = strip_scripts_and_styles(html)
        assert "<noscript" not in result
        assert "fallback text" not in result
        assert "<p>keep</p>" in result

    def test_tail_text_preserved_with_no_previous_sibling(self):
        """Text after the removed element, with no preceding sibling,
        is reattached to the parent's own text (parent.text branch)."""
        html = "<div><script>alert(1)</script>after</div>"
        result = strip_scripts_and_styles(html)
        assert result == "<div>after</div>"

    def test_tail_text_preserved_with_previous_sibling(self):
        """Text after the removed element, with a preceding sibling,
        is reattached to that sibling's tail (prev.tail branch)."""
        html = "<div><p>before</p><script>alert(1)</script>after</div>"
        result = strip_scripts_and_styles(html)
        assert result == "<div><p>before</p>after</div>"

    def test_removes_inline_event_handlers_case_insensitively(self):
        html = '<button onclick="doThing()" ONLOAD="x()" class="btn">Click</button>'
        result = strip_scripts_and_styles(html)
        assert "onclick" not in result.lower()
        assert "onload" not in result.lower()
        assert 'class="btn"' in result

    def test_preserves_non_event_attributes(self):
        html = '<a href="https://example.com" title="ok">link</a>'
        result = strip_scripts_and_styles(html)
        assert 'href="https://example.com"' in result
        assert 'title="ok"' in result

    def test_empty_string_passthrough(self):
        assert strip_scripts_and_styles("") == ""

    def test_whitespace_only_passthrough(self):
        assert strip_scripts_and_styles("   ") == "   "

    def test_parse_failure_falls_back_to_regex(self):
        """A document lxml cannot parse at all (e.g. a lone HTML comment,
        which lxml.html.fromstring rejects with 'Document is empty') falls
        back to the regex-based stripper rather than raising."""
        html = "<!-- just a comment -->"
        result = strip_scripts_and_styles(html)
        assert result == html
