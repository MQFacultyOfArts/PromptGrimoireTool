"""Test that raw_content newlines are preserved in PDF export."""

from promptgrimoire.export.pdf_export import _plain_text_to_html


class TestPlainTextToHtml:
    """Tests for _plain_text_to_html conversion."""

    def test_single_line(self) -> None:
        """Single line produces single paragraph."""
        result = _plain_text_to_html("Hello world")
        assert result == "<p>Hello world</p>"

    def test_multiple_lines(self) -> None:
        """Multiple lines produce multiple paragraphs."""
        result = _plain_text_to_html("Line one.\nLine two.")
        assert "<p>Line one.</p>" in result
        assert "<p>Line two.</p>" in result

    def test_empty_lines_preserved(self) -> None:
        """Empty lines produce empty paragraphs for spacing."""
        result = _plain_text_to_html("Line one.\n\nLine three.")
        assert result.count("<p>") == 3  # Line one, empty, Line three

    def test_special_chars_escaped(self) -> None:
        """HTML special characters are escaped."""
        result = _plain_text_to_html("a < b & c > d")
        assert "&lt;" in result
        assert "&amp;" in result
        assert "&gt;" in result

    def test_empty_input(self) -> None:
        """Empty input returns empty string."""
        assert _plain_text_to_html("") == ""
        assert _plain_text_to_html(None) == ""
