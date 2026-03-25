"""Tests for \\paranumber rendering in LaTeX output — AC1.1, AC1.4, AC1.5.

Verifies the full Phase 1 + Phase 2 pipeline: paragraph markers injected
into HTML become \\paranumber{N} commands in the LaTeX output.

- AC1.1: HTML passed to Pandoc contains <span data-paranumber="N">
- AC1.4: LaTeX output contains \\paranumber{N} matching the paragraph map
- AC1.5: PDF compilation succeeds with \\paranumber commands (smoke)

These tests use @requires_pandoc (auto-applies smoke marker) so they
are excluded from the unit lane and collected by ``grimoire test smoke``.
"""

from __future__ import annotations

import pytest

from promptgrimoire.export.pandoc import convert_html_with_annotations
from promptgrimoire.export.pdf_export import generate_tex_only
from promptgrimoire.input_pipeline.paragraph_map import (
    inject_paragraph_markers_for_export,
)
from tests.conftest import requires_latexmk, requires_pandoc


@requires_pandoc
class TestParanumberInLatex:
    """AC1.4: paranumber spans in HTML become \\paranumber{N} in LaTeX."""

    @pytest.mark.asyncio
    async def test_paranumber_spans_produce_latex_commands(self) -> None:
        """Pre-injected paranumber spans convert to \\paranumber{N} in LaTeX."""
        html = (
            '<p><span data-paranumber="1"></span>First paragraph.</p>'
            '<p><span data-paranumber="2"></span>Second paragraph.</p>'
        )
        latex = await convert_html_with_annotations(
            html=html,
            highlights=[],
            tag_colours={},
        )
        assert r"\paranumber{1}" in latex
        assert r"\paranumber{2}" in latex

    @pytest.mark.asyncio
    async def test_no_paranumber_spans_no_commands(self) -> None:
        """HTML without paranumber spans produces no \\paranumber commands."""
        html = "<p>Just plain text.</p><p>Another paragraph.</p>"
        latex = await convert_html_with_annotations(
            html=html,
            highlights=[],
            tag_colours={},
        )
        assert r"\paranumber" not in latex

    @pytest.mark.asyncio
    async def test_paranumber_with_highlights(self) -> None:
        """Both paranumber and highlight spans render correctly together."""
        html = (
            '<p><span data-paranumber="1"></span>'
            '<span data-hl="h1" data-colors="#e377c2" data-annots="">Highlighted</span>'
            " rest of text.</p>"
        )
        highlights = [
            {
                "id": "h1",
                "start_char": 0,
                "end_char": 11,
                "tag": "issue",
                "text": "Highlighted",
                "author": "Alice",
                "created_at": "2026-01-26T10:00:00+00:00",
                "comments": [],
            },
        ]
        tag_colours = {"issue": "#e377c2"}

        latex = await convert_html_with_annotations(
            html=html,
            highlights=highlights,
            tag_colours=tag_colours,
        )
        assert r"\paranumber{1}" in latex
        # Highlight should also be present (underline or highlight command)
        assert r"\highLight" in latex or r"\underLine" in latex


@requires_pandoc
class TestFullPipelineParanumber:
    """AC1.1 + AC1.4: Full pipeline from paragraph map to LaTeX."""

    @pytest.mark.asyncio
    async def test_inject_then_convert(self) -> None:
        """inject_paragraph_markers_for_export + convert_html_with_annotations
        produces \\paranumber{N} for each numbered paragraph."""
        html = "<p>First paragraph text.</p><p>Second paragraph text.</p>"
        # word_to_legal_para: char offset -> paragraph number
        # "First" starts at char 0, "Second" starts at char 21
        para_map: dict[int, int | None] = {0: 1, 21: 2}

        injected = inject_paragraph_markers_for_export(html, para_map)
        # Verify markers are in the HTML (AC1.1)
        assert 'data-paranumber="1"' in injected
        assert 'data-paranumber="2"' in injected

        # Convert to LaTeX (AC1.4)
        latex = await convert_html_with_annotations(
            html=injected,
            highlights=[],
            tag_colours={},
        )
        assert r"\paranumber{1}" in latex
        assert r"\paranumber{2}" in latex

    @pytest.mark.asyncio
    async def test_none_para_map_no_commands(self) -> None:
        """None word_to_legal_para means no markers, so no \\paranumber in LaTeX."""
        html = "<p>Just text.</p>"
        injected = inject_paragraph_markers_for_export(html, None)
        latex = await convert_html_with_annotations(
            html=injected,
            highlights=[],
            tag_colours={},
        )
        assert r"\paranumber" not in latex


@requires_latexmk
class TestParanumberCompilation:
    """AC1.5: PDF compilation succeeds with \\paranumber commands."""

    @pytest.mark.asyncio
    async def test_paranumber_compiles_to_pdf(self, tmp_path) -> None:
        """A document with paranumber markers compiles without LaTeX errors."""
        html = (
            '<p><span data-paranumber="1"></span>First paragraph of the document.</p>'
            '<p><span data-paranumber="2"></span>Second paragraph of the document.</p>'
            '<p><span data-paranumber="3"></span>Third paragraph of the document.</p>'
        )
        tex_path = await generate_tex_only(
            html_content=html,
            highlights=[],
            tag_colours={},
            output_dir=tmp_path,
        )
        # Verify tex contains the commands
        tex_content = tex_path.read_text()
        assert r"\paranumber{1}" in tex_content
        assert r"\paranumber{2}" in tex_content
        assert r"\paranumber{3}" in tex_content

        # Compilation test: generate_tex_only only produces .tex;
        # use compile_latex for PDF compilation.
        from promptgrimoire.export.pdf import compile_latex

        pdf_path = await compile_latex(tex_path)
        assert pdf_path.exists()
        assert pdf_path.stat().st_size > 0
