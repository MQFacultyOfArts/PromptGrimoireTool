"""Tests for content type detection."""

from promptgrimoire.input_pipeline.html_input import detect_content_type


class TestDetectContentType:
    """Tests for detect_content_type()."""

    def test_html_doctype(self) -> None:
        """Detect HTML from DOCTYPE declaration."""
        content = "<!DOCTYPE html><html><body>Hello</body></html>"
        assert detect_content_type(content) == "html"

    def test_html_tag_only(self) -> None:
        """Detect HTML from html tag without DOCTYPE."""
        content = "<html><body>Hello</body></html>"
        assert detect_content_type(content) == "html"

    def test_html_with_div(self) -> None:
        """Detect HTML from div tag."""
        content = "<div>Hello world</div>"
        assert detect_content_type(content) == "html"

    def test_html_with_paragraph(self) -> None:
        """Detect HTML from p tag."""
        content = "<p>Hello world</p>"
        assert detect_content_type(content) == "html"

    def test_html_case_insensitive(self) -> None:
        """Detect HTML regardless of tag case."""
        content = "<HTML><BODY>Hello</BODY></HTML>"
        assert detect_content_type(content) == "html"

    def test_html_with_whitespace(self) -> None:
        """Detect HTML even with leading whitespace."""
        content = "   \n\n<!DOCTYPE html><html><body>Hello</body></html>"
        assert detect_content_type(content) == "html"

    def test_rtf_string(self) -> None:
        """Detect RTF from magic header."""
        content = r"{\rtf1\ansi\deff0 Hello}"
        assert detect_content_type(content) == "rtf"

    def test_rtf_bytes(self) -> None:
        """Detect RTF from bytes."""
        content = b"{\\rtf1\\ansi\\deff0 Hello}"
        assert detect_content_type(content) == "rtf"

    def test_pdf_bytes(self) -> None:
        """Detect PDF from magic bytes."""
        content = b"%PDF-1.4 fake pdf content"
        assert detect_content_type(content) == "pdf"

    def test_docx_bytes(self) -> None:
        """Detect DOCX from PK signature and word content marker."""
        # Simulated DOCX header (simplified)
        content = b"PK\x03\x04" + b"\x00" * 100 + b"word/document.xml"
        assert detect_content_type(content) == "docx"

    def test_plain_text(self) -> None:
        """Detect plain text as fallback."""
        content = "Just some plain text without any markup."
        assert detect_content_type(content) == "text"

    def test_plain_text_with_angle_brackets(self) -> None:
        """Plain text with < but no HTML tags is still text."""
        content = "5 < 10 and 10 > 5"
        assert detect_content_type(content) == "text"

    def test_empty_string(self) -> None:
        """Empty string is plain text."""
        assert detect_content_type("") == "text"

    def test_bytes_utf8(self) -> None:
        """Bytes content decoded as UTF-8."""
        content = b"<html><body>Hello</body></html>"
        assert detect_content_type(content) == "html"
