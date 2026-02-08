"""Unit tests for markdown-to-LaTeX conversion via Pandoc.

Tests the _markdown_to_latex_notes() function added for Phase 7
(PDF export of response draft from Milkdown editor).
"""

from __future__ import annotations

import shutil

import pytest

from promptgrimoire.export.pdf_export import (
    _build_general_notes_section,
    _markdown_to_latex_notes,
)

requires_pandoc = pytest.mark.skipif(
    not shutil.which("pandoc"), reason="Pandoc not installed"
)


@requires_pandoc
class TestMarkdownToLatexNotes:
    """Tests for converting Milkdown markdown to LaTeX via Pandoc."""

    @pytest.mark.asyncio
    async def test_empty_markdown_returns_empty(self) -> None:
        """Empty or whitespace-only markdown produces empty string."""
        assert await _markdown_to_latex_notes("") == ""
        assert await _markdown_to_latex_notes("   ") == ""
        assert await _markdown_to_latex_notes(None) == ""  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_plain_text(self) -> None:
        """Plain text markdown is converted to LaTeX."""
        result = await _markdown_to_latex_notes("Hello world")
        assert "Hello world" in result

    @pytest.mark.asyncio
    async def test_bold_text(self) -> None:
        """Markdown bold converts to LaTeX textbf."""
        result = await _markdown_to_latex_notes("This is **bold** text")
        assert r"\textbf{bold}" in result

    @pytest.mark.asyncio
    async def test_italic_text(self) -> None:
        """Markdown italic converts to LaTeX emph."""
        result = await _markdown_to_latex_notes("This is *italic* text")
        assert r"\emph{italic}" in result

    @pytest.mark.asyncio
    async def test_heading(self) -> None:
        """Markdown heading converts to LaTeX section."""
        result = await _markdown_to_latex_notes("# My Heading")
        # Pandoc uses \section for h1 in default mode
        assert "My Heading" in result

    @pytest.mark.asyncio
    async def test_bullet_list(self) -> None:
        """Markdown bullet list converts to LaTeX itemize."""
        md = "- Item one\n- Item two\n- Item three"
        result = await _markdown_to_latex_notes(md)
        assert r"\begin{itemize}" in result
        assert "Item one" in result
        assert "Item three" in result

    @pytest.mark.asyncio
    async def test_numbered_list(self) -> None:
        """Markdown numbered list converts to LaTeX enumerate."""
        md = "1. First\n2. Second\n3. Third"
        result = await _markdown_to_latex_notes(md)
        assert r"\begin{enumerate}" in result
        assert "First" in result

    @pytest.mark.asyncio
    async def test_multiline_paragraphs(self) -> None:
        """Multiple paragraphs are preserved in LaTeX output."""
        md = "First paragraph.\n\nSecond paragraph."
        result = await _markdown_to_latex_notes(md)
        assert "First paragraph" in result
        assert "Second paragraph" in result


class TestBuildGeneralNotesSectionWithLatex:
    """Tests for _build_general_notes_section with pre-converted LaTeX."""

    def test_empty_latex_returns_empty(self) -> None:
        """Empty latex_content produces no section."""
        result = _build_general_notes_section("", latex_content="")
        assert result == ""

    def test_latex_content_bypasses_html_conversion(self) -> None:
        """When latex_content is provided, HTML conversion is skipped."""
        latex = r"This is \textbf{pre-converted} LaTeX."
        result = _build_general_notes_section("", latex_content=latex)
        assert "General Notes" in result
        assert r"\textbf{pre-converted}" in result

    def test_html_fallback_still_works(self) -> None:
        """When no latex_content, HTML path still works."""
        html = "<p>Some <strong>HTML</strong> notes.</p>"
        result = _build_general_notes_section(html)
        assert "General Notes" in result
        assert "Some" in result

    def test_latex_content_takes_precedence(self) -> None:
        """latex_content takes precedence over general_notes HTML."""
        html = "<p>HTML content</p>"
        latex = r"\textbf{LaTeX content}"
        result = _build_general_notes_section(html, latex_content=latex)
        assert r"\textbf{LaTeX content}" in result
        # Should NOT contain the HTML-converted content
        assert "HTML content" not in result
