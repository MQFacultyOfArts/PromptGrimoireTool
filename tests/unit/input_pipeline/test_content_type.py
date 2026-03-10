"""Tests for content type detection."""

import gzip
from pathlib import Path

import pytest

from promptgrimoire.input_pipeline.html_input import detect_content_type

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures"


class TestDetectContentType:
    """Tests for detect_content_type()."""

    def test_html_doctype(self) -> None:
        """Detect HTML from DOCTYPE declaration."""
        content = "<!DOCTYPE html><html><body>Hello</body></html>"
        assert detect_content_type(content) == "html"

    def test_html_tag_only(self) -> None:
        """Detect HTML from html tag without DOCTYPE."""
        content = "<html><body><p>Hello</p></body></html>"
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
        content = "<HTML><BODY><P>Hello</P></BODY></HTML>"
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
        content = b"<html><body><p>Hello</p></body></html>"
        assert detect_content_type(content) == "html"


class TestDetectContentTypeFixtures:
    """Tests for detect_content_type() using real fixture files."""

    # HTML fixtures - should all be detected as HTML
    @pytest.mark.parametrize(
        "fixture_path",
        [
            "183-austlii.html",
            "183-libreoffice.html",
            "conversations/austlii.html",
            "conversations/chinese_wikipedia.html",
            "conversations/claude_cooking.html",
            "conversations/claude_maths.html",
            "conversations/clean/chinese_wikipedia.html",
            "conversations/clean/translation_japanese_sample.html",
            "conversations/clean/translation_korean_sample.html",
            "conversations/clean/translation_spanish_sample.html",
            "conversations/translation_japanese_sample.html",
            "conversations/translation_korean_sample.html",
            "conversations/translation_spanish_sample.html",
        ],
    )
    def test_html_fixtures(self, fixture_path: str) -> None:
        """HTML fixture files are detected as HTML."""
        content = (FIXTURES_DIR / fixture_path).read_bytes()
        assert detect_content_type(content) == "html"

    # Gzipped HTML fixtures
    @pytest.mark.parametrize(
        "fixture_path",
        [
            "conversations/claude_cooking.html.gz",
            "conversations/claude_maths.html.gz",
            "conversations/google_aistudio_image.html.gz",
            "conversations/google_aistudio_ux_discussion.html.gz",
            "conversations/google_gemini_debug.html.gz",
            "conversations/google_gemini_deep_research.html.gz",
            "conversations/openai_biblatex.html.gz",
            "conversations/openai_dh_dr.html.gz",
            "conversations/openai_dprk_denmark.html.gz",
            "conversations/openai_software_long_dr.html.gz",
            "conversations/scienceos_loc.html.gz",
            "conversations/scienceos_philsci.html.gz",
        ],
    )
    def test_gzipped_html_fixtures(self, fixture_path: str) -> None:
        """Gzipped HTML fixture files are detected as HTML after decompression."""
        compressed = (FIXTURES_DIR / fixture_path).read_bytes()
        content = gzip.decompress(compressed)
        assert detect_content_type(content) == "html"

    def test_rtf_fixture(self) -> None:
        """RTF fixture file is detected as RTF."""
        content = (FIXTURES_DIR / "183.rtf").read_bytes()
        assert detect_content_type(content) == "rtf"

    def test_json_fixture_plain_text(self) -> None:
        """JSON fixture (SillyTavern card) is detected as text."""
        content = (FIXTURES_DIR / "Becky Bennett (2).json").read_bytes()
        assert detect_content_type(content) == "text"

    def test_blns_contains_html_tags(self) -> None:
        """BLNS (Big List of Naughty Strings) contains HTML XSS strings.

        This file is detected as HTML because it contains actual <div> tags
        as part of XSS test payloads. This is correct behavior - the detector
        sees HTML tags and reports HTML.
        """
        content = (FIXTURES_DIR / "blns.txt").read_bytes()
        # BLNS contains XSS strings like: ABC<div style="x:expression(...)">DEF
        assert detect_content_type(content) == "html"

    def test_blns_json_contains_html_tags(self) -> None:
        """BLNS JSON also contains HTML XSS strings."""
        content = (FIXTURES_DIR / "blns.json").read_bytes()
        assert detect_content_type(content) == "html"


class TestFakeHtmlDetection:
    """Tests for fake-HTML reclassification (AC6.2).

    PDF viewers paste plain text wrapped in <html><body>...</body></html>.
    This should be detected as "text", not "html", so that _text_to_html()
    converts newlines to <br/> tags.
    """

    def test_html_wrapped_plain_text_is_text(self) -> None:
        """AC6.2: HTML wrapper around plain text is reclassified as text."""
        content = "<html><head></head><body>line1\nline2\nline3</body></html>"
        assert detect_content_type(content) == "text"

    def test_real_html_with_p_tags_stays_html(self) -> None:
        """Real HTML with <p> tags is still detected as HTML."""
        content = "<html><body><p>paragraph one</p><p>paragraph two</p></body></html>"
        assert detect_content_type(content) == "html"

    def test_real_html_with_div_stays_html(self) -> None:
        """HTML with <div> elements stays HTML."""
        content = "<html><body><div>content</div></body></html>"
        assert detect_content_type(content) == "html"

    def test_real_html_with_heading_stays_html(self) -> None:
        """HTML with heading elements stays HTML."""
        content = "<html><body><h1>Title</h1>Some text</body></html>"
        assert detect_content_type(content) == "html"

    def test_real_html_with_table_stays_html(self) -> None:
        """HTML with <table> stays HTML."""
        content = "<html><body><table><tr><td>cell</td></tr></table></body></html>"
        assert detect_content_type(content) == "html"

    def test_real_html_with_ul_stays_html(self) -> None:
        """HTML with <ul> stays HTML."""
        content = "<html><body><ul><li>item</li></ul></body></html>"
        assert detect_content_type(content) == "html"

    def test_real_html_with_ol_stays_html(self) -> None:
        """HTML with <ol> stays HTML."""
        content = "<html><body><ol><li>item</li></ol></body></html>"
        assert detect_content_type(content) == "html"

    def test_real_html_with_blockquote_stays_html(self) -> None:
        """HTML with <blockquote> stays HTML."""
        content = "<html><body><blockquote>quote</blockquote></body></html>"
        assert detect_content_type(content) == "html"

    def test_real_html_with_pre_stays_html(self) -> None:
        """HTML with <pre> stays HTML."""
        content = "<html><body><pre>code block</pre></body></html>"
        assert detect_content_type(content) == "html"

    def test_real_html_with_section_stays_html(self) -> None:
        """HTML with <section> stays HTML."""
        content = "<html><body><section>content</section></body></html>"
        assert detect_content_type(content) == "html"

    def test_real_html_with_article_stays_html(self) -> None:
        """HTML with <article> stays HTML."""
        content = "<html><body><article>content</article></body></html>"
        assert detect_content_type(content) == "html"

    def test_plain_text_without_wrapper_still_text(self) -> None:
        """Plain text without HTML wrapper is still detected as text."""
        content = "Just plain text\nwith newlines\nand nothing else."
        assert detect_content_type(content) == "text"

    def test_evince_fixture_wrapped_in_html_is_text(self) -> None:
        """Real-world evince PDF paste fixture wrapped in HTML body is text.

        The evince_cooking fixture contains plain text output from a PDF
        viewer. When wrapped in <html><body>, it should be reclassified as
        text since there are no block-level elements.
        """
        compressed = (
            FIXTURES_DIR / "conversations" / "evince_cooking.html.gz"
        ).read_bytes()
        raw_text = gzip.decompress(compressed).decode("utf-8")
        wrapped = f"<html><body>{raw_text}</body></html>"
        assert detect_content_type(wrapped) == "text"

    def test_html_with_only_span_is_text(self) -> None:
        """HTML with only inline elements (span) is reclassified as text.

        Span is inline, not block-level — no structural HTML present.
        """
        content = "<html><body><span>just inline</span> text</body></html>"
        assert detect_content_type(content) == "text"

    def test_html_with_only_br_is_text(self) -> None:
        """HTML with only <br> tags (no block elements) is text.

        <br> is inline/void, not a block-level structural element.
        """
        content = "<html><body>line1<br>line2<br>line3</body></html>"
        assert detect_content_type(content) == "text"
