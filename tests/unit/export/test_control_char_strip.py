"""Tests for control character stripping in LaTeX export pipeline.

Regression tests for invalid character LaTeX compilation failures.
Students paste content from PDFs containing C0/C1 control characters
(e.g. backspace U+0008) that are valid HTML but invalid in LaTeX source.

See incident 2026-03-25: two students hit "Text line contains an invalid
character" errors from ^^H (backspace) in case citations.

Fixture: fixtures/pdf_with_control_chars.html — extracted from 66.pdf
(Adelaide Law Review article) via pymupdf4llm + pandoc, reproducing
the exact production failure pattern: page numbers with embedded
backspace characters in running headers.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from promptgrimoire.export.pandoc import convert_html_to_latex

_FIXTURES = Path(__file__).parent / "fixtures"


class TestControlCharStripping:
    """Control characters in HTML must not reach LaTeX output."""

    @pytest.mark.asyncio
    async def test_backspace_stripped(self) -> None:
        """U+0008 BACKSPACE (the production failure) is stripped."""
        html = "<p>302\x08 case citation</p>"
        latex = await convert_html_to_latex(html)
        assert "\x08" not in latex
        assert "302" in latex
        assert "case citation" in latex

    @pytest.mark.asyncio
    async def test_c0_controls_stripped(self) -> None:
        """All C0 controls except tab/newline/CR are stripped."""
        # Build string with all C0 controls (0x00-0x1F)
        c0_chars = "".join(chr(i) for i in range(0x20))
        html = f"<p>before{c0_chars}after</p>"
        latex = await convert_html_to_latex(html)
        # Tab, newline, CR may survive (they're valid in LaTeX)
        for cp in range(0x20):
            if chr(cp) in "\t\n\r":
                continue
            assert chr(cp) not in latex, f"U+{cp:04X} should be stripped"
        assert "before" in latex
        assert "after" in latex

    @pytest.mark.asyncio
    async def test_del_stripped(self) -> None:
        """U+007F DEL is stripped."""
        html = "<p>text\x7fmore</p>"
        latex = await convert_html_to_latex(html)
        assert "\x7f" not in latex

    @pytest.mark.asyncio
    async def test_c1_controls_stripped(self) -> None:
        """C1 controls (0x80-0x9F) are stripped."""
        for cp in range(0x80, 0xA0):
            html = f"<p>a{chr(cp)}b</p>"
            latex = await convert_html_to_latex(html)
            assert chr(cp) not in latex, f"U+{cp:04X} should be stripped"

    @pytest.mark.asyncio
    async def test_normal_unicode_preserved(self) -> None:
        """Regular Unicode (accents, CJK, etc.) is not stripped."""
        html = "<p>café naïve 日本語</p>"
        latex = await convert_html_to_latex(html)
        assert "caf" in latex
        assert "ve" in latex

    @pytest.mark.asyncio
    async def test_real_pdf_fixture(self) -> None:
        """Fixture from 66.pdf (Adelaide Law Review) with backspace in headers.

        The PDF typesetting embeds U+0008 BACKSPACE between page numbers
        and running header text. pymupdf4llm extracts it faithfully,
        pandoc passes it through to HTML, and it must be stripped before
        LaTeX compilation.
        """
        html = (_FIXTURES / "pdf_with_control_chars.html").read_text()
        assert "\x08" in html or "&#x8;" in html, "Fixture must contain backspace"
        latex = await convert_html_to_latex(html)
        assert "\x08" not in latex
        # Content survived the strip
        assert "CALCULATING CULTURAL" in latex
        assert "880" in latex
        assert "Indigenous" in latex
