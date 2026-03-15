"""Tests for process_input() orchestration.

Note: process_input() returns clean HTML. Highlighting uses the CSS
Custom Highlight API on the client side — no char spans are produced.
"""

from pathlib import Path

import pytest
from selectolax.lexbor import LexborHTMLParser

from promptgrimoire.input_pipeline.html_input import process_input
from tests.conftest import load_conversation_fixture

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures"


class TestProcessInput:
    """Tests for process_input()."""

    @pytest.mark.asyncio
    async def test_empty_text_input(self) -> None:
        """Empty text input produces empty paragraph."""
        result = await process_input("", source_type="text")
        assert "<p>" in result

    @pytest.mark.asyncio
    async def test_plain_text_conversion(self) -> None:
        """Plain text is converted to HTML paragraphs."""
        result = await process_input("Hello world", source_type="text")
        assert "<p>" in result
        assert "Hello world" in result
        # No char spans — highlighting uses CSS Highlight API
        assert "data-char-index" not in result

    @pytest.mark.asyncio
    async def test_html_passthrough(self) -> None:
        """HTML content goes through preprocessing (no span injection)."""
        result = await process_input("<p>Test</p>", source_type="html")
        assert "Test" in result
        # No char spans — highlighting uses CSS Highlight API
        assert "data-char-index" not in result

    @pytest.mark.asyncio
    async def test_text_double_newline_paragraphs(self) -> None:
        """Double newlines create separate paragraphs."""
        result = await process_input("Para 1\n\nPara 2", source_type="text")
        # Should have two <p> tags
        assert result.count("<p>") == 2

    @pytest.mark.asyncio
    async def test_bytes_input(self) -> None:
        """Bytes input is decoded and processed."""
        result = await process_input(b"<p>Test</p>", source_type="html")
        assert "Test" in result
        # No char spans — highlighting uses CSS Highlight API
        assert "data-char-index" not in result

    @pytest.mark.asyncio
    async def test_unsupported_format_raises(self) -> None:
        """Unsupported formats raise NotImplementedError."""
        with pytest.raises(NotImplementedError, match="not yet implemented"):
            await process_input("content", source_type="rtf")

    @pytest.mark.asyncio
    async def test_returns_clean_html(self) -> None:
        """Output is clean HTML without char-span markup."""
        result = await process_input("<p>Hello</p>", source_type="html")
        assert "Hello" in result
        # Clean HTML — no char spans (highlighting uses CSS Highlight API)
        assert "data-char-index" not in result
        assert '<span class="char"' not in result

    @pytest.mark.asyncio
    async def test_chatcraft_fixture_preserves_blockquotes_and_code_blocks(
        self,
    ) -> None:
        """Real ChatCraft cards keep rich block structure through process_input()."""
        html = load_conversation_fixture("chatcraft_sonnet-232")

        result = await process_input(
            html,
            source_type="html",
            platform_hint="chatcraft",
        )
        tree = LexborHTMLParser(result)

        assert len(tree.css("blockquote")) >= 1
        assert len(tree.css("pre")) >= 1
        assert len(tree.css("code")) >= 1
        assert "The above summary is nested:" in result
        assert "CONTROL PARAGRAPH." in result


class TestProcessInputDocx:
    """Tests for DOCX through process_input() pipeline.

    Verifies: file-upload-109.AC1.1, file-upload-109.AC1.2
    """

    @pytest.mark.asyncio
    async def test_docx_produces_semantic_html(self) -> None:
        """AC1.1: DOCX bytes through process_input produce semantic HTML tags."""
        docx_bytes = (FIXTURES_DIR / "2025 LAWS1000 case.docx").read_bytes()
        result = await process_input(docx_bytes, source_type="docx")
        assert "<p>" in result
        assert isinstance(result, str)
        assert len(result) > 100

    @pytest.mark.asyncio
    async def test_shen_v_r_fixture_full_pipeline(self) -> None:
        """AC1.2: Shen v R DOCX fixture produces valid HTML through full pipeline."""
        docx_bytes = (FIXTURES_DIR / "2025 LAWS1000 case.docx").read_bytes()
        result = await process_input(docx_bytes, source_type="docx")
        tree = LexborHTMLParser(result)
        # Should have paragraph structure
        paragraphs = tree.css("p")
        assert len(paragraphs) >= 1
        # Should contain text content (not empty conversion)
        text = tree.text()
        assert len(text) > 50

    @pytest.mark.asyncio
    async def test_docx_string_input_raises_type_error(self) -> None:
        """DOCX requires bytes input — string raises TypeError."""
        with pytest.raises(TypeError, match="bytes"):
            await process_input("not bytes", source_type="docx")


@pytest.mark.smoke
class TestProcessInputPdf:
    """Tests for PDF through process_input() pipeline.

    Verifies: file-upload-109.AC2.1, file-upload-109.AC2.2
    """

    @pytest.mark.asyncio
    async def test_pdf_produces_paragraph_html(self) -> None:
        """AC2.1: PDF bytes produce HTML with paragraph structure."""
        pdf_bytes = (
            FIXTURES_DIR / "Lawlis v R [2025] NSWCCA 183 (3 November 2025).pdf"
        ).read_bytes()
        result = await process_input(pdf_bytes, source_type="pdf")
        assert "<p>" in result
        assert isinstance(result, str)
        assert len(result) > 100

    @pytest.mark.asyncio
    async def test_lawlis_v_r_fixture_full_pipeline(self) -> None:
        """AC2.2: Lawlis v R PDF fixture produces valid HTML through full pipeline."""
        pdf_bytes = (
            FIXTURES_DIR / "Lawlis v R [2025] NSWCCA 183 (3 November 2025).pdf"
        ).read_bytes()
        result = await process_input(pdf_bytes, source_type="pdf")
        tree = LexborHTMLParser(result)
        # Should have paragraph structure
        paragraphs = tree.css("p")
        assert len(paragraphs) >= 1
        # Should contain text content
        text = tree.text()
        assert len(text) > 50

    @pytest.mark.asyncio
    async def test_pdf_string_input_raises_type_error(self) -> None:
        """PDF requires bytes input — string raises TypeError."""
        with pytest.raises(TypeError, match="bytes"):
            await process_input("not bytes", source_type="pdf")


class TestProcessInputPdfPaste:
    """End-to-end tests for PDF paste scenario through process_input().

    Verifies: file-upload-109.AC6.2
    PDF viewers paste plain text wrapped in <html><body>...</body></html>.
    After fake-HTML detection reclassifies this as "text", process_input()
    should produce HTML with line breaks preserved.
    """

    @pytest.mark.asyncio
    async def test_fake_html_paste_produces_line_breaks(self) -> None:
        """AC6.2: HTML-wrapped plain text produces <br> tags between lines."""
        from promptgrimoire.input_pipeline.html_input import detect_content_type

        pasted = "<html><body>line1\nline2\nline3</body></html>"

        # Verify detect_content_type reclassifies HTML-wrapped plain text as "text"
        detected = detect_content_type(pasted)
        assert detected == "text", f"Expected 'text' but got '{detected}'"

        result = await process_input(pasted, source_type=detected)
        # _text_to_html strips the HTML wrapper, then converts \n to <br>
        assert "line1" in result
        assert "line2" in result
        assert "line3" in result
        # Lines should be separated by <br> tags (single newlines)
        assert "<br>" in result

    @pytest.mark.asyncio
    async def test_evince_fixture_produces_multiple_blocks(self) -> None:
        """AC6.2: Evince PDF paste fixture produces distinct blocks."""
        import gzip

        fixture_path = FIXTURES_DIR / "conversations" / "evince_cooking.html.gz"
        raw_text = gzip.decompress(fixture_path.read_bytes()).decode("utf-8")

        # Wrap in HTML body tags as PDF viewers do
        wrapped = f"<html><body>{raw_text}</body></html>"

        # Auto-detect the content type — should classify as "text" (fake HTML)
        from promptgrimoire.input_pipeline.html_input import detect_content_type

        detected = detect_content_type(wrapped)
        assert detected == "text", f"Expected 'text' but got '{detected}'"

        result = await process_input(wrapped, source_type=detected)
        tree = LexborHTMLParser(result)

        # Should produce multiple paragraphs or line breaks — not one giant block
        paragraphs = tree.css("p")
        br_tags = tree.css("br")
        # The fixture has many lines; we expect substantial structure
        total_blocks = len(paragraphs) + len(br_tags)
        assert total_blocks > 5, (
            f"Expected multiple text blocks, got "
            f"{len(paragraphs)} <p> and {len(br_tags)} <br>"
        )
