"""Tests for process_input() orchestration.

Note: process_input() returns clean HTML. Highlighting uses the CSS
Custom Highlight API on the client side — no char spans are produced.
"""

import pytest
from selectolax.lexbor import LexborHTMLParser

from promptgrimoire.input_pipeline.html_input import process_input
from tests.conftest import load_conversation_fixture


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
