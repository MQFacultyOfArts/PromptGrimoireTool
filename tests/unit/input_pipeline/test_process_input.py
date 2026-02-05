"""Tests for process_input() orchestration."""

import pytest

from promptgrimoire.input_pipeline.html_input import process_input, strip_char_spans


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
        assert 'data-char-index="0">' in result

    @pytest.mark.asyncio
    async def test_html_passthrough(self) -> None:
        """HTML content goes through preprocessing and span injection."""
        result = await process_input("<p>Test</p>", source_type="html")
        assert 'data-char-index="0">' in result

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
        assert 'data-char-index="0">' in result

    @pytest.mark.asyncio
    async def test_unsupported_format_raises(self) -> None:
        """Unsupported formats raise NotImplementedError."""
        with pytest.raises(NotImplementedError, match="not yet implemented"):
            await process_input("content", source_type="rtf")

    @pytest.mark.asyncio
    async def test_output_strippable(self) -> None:
        """Output can be stripped back to clean HTML."""
        result = await process_input("<p>Hello</p>", source_type="html")
        stripped = strip_char_spans(result)
        assert "Hello" in stripped
        assert "data-char-index" not in stripped
