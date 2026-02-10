"""Tests for export pipeline resilience.

Ensures that:
1. <img> tags (\\includegraphics) cannot crash PDF compilation
2. Pandoc language markup (\\begin{otherlanguage}) doesn't crash compilation
3. Markdown images stripped before Pandoc conversion

Regression tests for:
- Corrupt-PDF bug: lipsum.com banner GIFs pasted into Milkdown respond editor
  caused 'Unknown graphics extension: .gif'.
- Chinese Wikipedia fixture: Pandoc generated \\begin{otherlanguage}{chinese}
  which crashed because babel wasn't loaded.
"""

from __future__ import annotations

import pytest

from promptgrimoire.export.preamble import build_annotation_preamble
from promptgrimoire.export.unicode_latex import UNICODE_PREAMBLE


class TestIncludegraphicsStub:
    """The \\includegraphics stub must appear AFTER hyperref loads graphicx."""

    def test_stub_defined_after_hyperref(self) -> None:
        """\\renewcommand{\\includegraphics} must come after \\usepackage{hyperref}.

        hyperref loads graphicx which defines \\includegraphics via
        \\DeclareRobustCommand. Our no-op stub must use \\renewcommand
        and appear after hyperref to survive.
        """
        preamble = build_annotation_preamble({"test_tag": "#ff0000"})

        # Find the last \usepackage to ensure stub is after ALL packages
        last_usepackage = preamble.rfind(r"\usepackage")

        stub_pos = preamble.find(r"\renewcommand{\includegraphics}")
        assert stub_pos != -1, (
            "Preamble must contain \\renewcommand{\\includegraphics} "
            "(not \\newcommand, which gets clobbered by hyperref/graphicx)"
        )
        assert stub_pos > last_usepackage, (
            "\\renewcommand{\\includegraphics} must appear AFTER all "
            "\\usepackage calls (hyperref loads graphicx which redefines it)"
        )

    def test_stub_not_in_unicode_preamble(self) -> None:
        """The stub should NOT be in UNICODE_PREAMBLE (too early, before hyperref)."""
        assert r"\newcommand{\includegraphics}" not in UNICODE_PREAMBLE, (
            "\\includegraphics stub in UNICODE_PREAMBLE is clobbered by "
            "hyperref loading graphicx. Move to ANNOTATION_PREAMBLE_BASE."
        )


class TestOtherlanguageEnvironment:
    """Pandoc generates \\begin{otherlanguage}{X} for non-English content."""

    def test_otherlanguage_defined_in_preamble(self) -> None:
        """Preamble must define otherlanguage environment as no-op.

        Pandoc detects non-English content (e.g. Chinese Wikipedia) and emits
        \\begin{otherlanguage}{chinese}. Without a definition, LaTeX crashes.
        We handle multilingual via luatexja + font fallbacks, not babel.
        """
        preamble = build_annotation_preamble({"test_tag": "#ff0000"})
        # Uses @ifundefined to handle both cases (babel loaded or not)
        assert r"otherlanguage" in preamble and "newenvironment" in preamble, (
            "Preamble must define otherlanguage environment (no-op) so Pandoc's "
            "language markup doesn't crash compilation."
        )


class TestMarkdownImageStripping:
    """Images in markdown response drafts must be stripped before Pandoc."""

    @pytest.mark.asyncio
    async def test_markdown_images_stripped(self) -> None:
        """![alt](url) syntax must not produce \\includegraphics in LaTeX."""
        from promptgrimoire.export.pdf_export import markdown_to_latex_notes

        md = "Some text\n\n![banner](https://example.com/image.gif)\n\nMore text"
        latex = await markdown_to_latex_notes(md)

        assert r"\includegraphics" not in latex, (
            "Markdown image syntax must be stripped before Pandoc conversion. "
            "\\includegraphics crashes LuaLaTeX with unsupported formats (.gif)."
        )
        # The text content should still be present
        assert "Some text" in latex
        assert "More text" in latex

    @pytest.mark.asyncio
    async def test_markdown_reference_images_stripped(self) -> None:
        """Reference-style images ![alt][id] must also be stripped."""
        from promptgrimoire.export.pdf_export import markdown_to_latex_notes

        md = "Text\n\n![alt][logo]\n\n[logo]: https://example.com/logo.png\n\nEnd"
        latex = await markdown_to_latex_notes(md)

        assert r"\includegraphics" not in latex

    @pytest.mark.asyncio
    async def test_empty_markdown_unaffected(self) -> None:
        """Empty/whitespace markdown returns empty string (no regression)."""
        from promptgrimoire.export.pdf_export import markdown_to_latex_notes

        assert await markdown_to_latex_notes("") == ""
        assert await markdown_to_latex_notes("   ") == ""
        assert await markdown_to_latex_notes(None) == ""
