"""Tests for DOCX and PDF converter functions.

Verifies:
- file-upload-109.AC1.1: DOCX produces semantic HTML
- file-upload-109.AC1.3: Corrupt/empty DOCX returns ValueError
- file-upload-109.AC2.1: PDF produces HTML with paragraph structure
- file-upload-109.AC2.3: Corrupt/empty PDF returns ValueError
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from promptgrimoire.input_pipeline.converters import (
    convert_docx_to_html,
    convert_pdf_to_html,
)

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures"


class TestConvertDocxToHtml:
    """Tests for DOCX to HTML conversion (file-upload-109.AC1)."""

    def test_produces_paragraph_tags(self) -> None:
        """AC1.1: DOCX paragraphs produce <p> tags."""
        docx_bytes = (FIXTURES_DIR / "2025 LAWS1000 case.docx").read_bytes()
        html = convert_docx_to_html(docx_bytes)
        assert "<p>" in html

    def test_produces_semantic_html(self) -> None:
        """AC1.1: DOCX with bold/italic produces <strong> and <em> tags.

        Uses 2025FCA0796 - Summary.docx which contains formatted text
        (bold headings, italicised citations). The Shen v R case fixture
        (2025 LAWS1000 case.docx) has no inline formatting.
        """
        docx_bytes = (FIXTURES_DIR / "2025FCA0796 - Summary.docx").read_bytes()
        html = convert_docx_to_html(docx_bytes)
        assert "<strong>" in html or "<em>" in html

    def test_returns_string(self) -> None:
        """Converter returns a plain string, not bytes."""
        docx_bytes = (FIXTURES_DIR / "2025 LAWS1000 case.docx").read_bytes()
        html = convert_docx_to_html(docx_bytes)
        assert isinstance(html, str)

    def test_corrupt_docx_raises_value_error(self) -> None:
        """AC1.3: Invalid bytes raise ValueError."""
        with pytest.raises(ValueError, match=r"(?i)docx"):
            convert_docx_to_html(b"not a docx file")

    def test_empty_bytes_raises_value_error(self) -> None:
        """AC1.3: Empty bytes raise ValueError."""
        with pytest.raises(ValueError, match=r"(?i)docx"):
            convert_docx_to_html(b"")


class TestConvertPdfToHtml:
    """Tests for PDF to HTML conversion (file-upload-109.AC2)."""

    @pytest.mark.asyncio
    async def test_produces_paragraph_tags(self) -> None:
        """AC2.1: PDF produces HTML with <p> paragraph structure."""
        pdf_bytes = (
            FIXTURES_DIR / "Lawlis v R [2025] NSWCCA 183 (3 November 2025).pdf"
        ).read_bytes()
        html = await convert_pdf_to_html(pdf_bytes)
        assert "<p>" in html

    @pytest.mark.asyncio
    async def test_produces_heading_tags(self) -> None:
        """AC2.1: PDF with headings produces heading tags."""
        pdf_bytes = (
            FIXTURES_DIR / "Lawlis v R [2025] NSWCCA 183 (3 November 2025).pdf"
        ).read_bytes()
        html = await convert_pdf_to_html(pdf_bytes)
        # pymupdf4llm extracts headings as markdown ## which pandoc converts to <h2>
        assert "<h" in html

    @pytest.mark.asyncio
    async def test_returns_string(self) -> None:
        """Converter returns a plain string, not bytes."""
        pdf_bytes = (
            FIXTURES_DIR / "Lawlis v R [2025] NSWCCA 183 (3 November 2025).pdf"
        ).read_bytes()
        html = await convert_pdf_to_html(pdf_bytes)
        assert isinstance(html, str)
        assert len(html) > 100

    @pytest.mark.asyncio
    async def test_corrupt_pdf_raises_value_error(self) -> None:
        """AC2.3: Invalid bytes raise ValueError."""
        with pytest.raises(ValueError, match=r"(?i)pdf"):
            await convert_pdf_to_html(b"not a pdf file")

    @pytest.mark.asyncio
    async def test_empty_bytes_raises_value_error(self) -> None:
        """AC2.3: Empty bytes raise ValueError."""
        with pytest.raises(ValueError, match=r"(?i)pdf"):
            await convert_pdf_to_html(b"")

    @pytest.mark.asyncio
    async def test_pandoc_failure_raises_value_error(self) -> None:
        """AC2.3: Pandoc non-zero exit raises ValueError (not CalledProcessError).

        Mocks asyncio.create_subprocess_exec so the test does not depend on
        pandoc being installed or behaving badly in CI.
        """
        mock_proc = AsyncMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(
            return_value=(b"", b"pandoc: simulated failure")
        )

        pdf_bytes = (
            FIXTURES_DIR / "Lawlis v R [2025] NSWCCA 183 (3 November 2025).pdf"
        ).read_bytes()

        with (
            patch(
                "promptgrimoire.input_pipeline.converters.asyncio.create_subprocess_exec",
                return_value=mock_proc,
            ),
            pytest.raises(ValueError, match=r"pandoc failed"),
        ):
            await convert_pdf_to_html(pdf_bytes)
