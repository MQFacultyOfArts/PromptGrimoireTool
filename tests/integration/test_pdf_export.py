"""Integration tests for PDF export pipeline.

These tests require external dependencies (Pandoc, TinyTeX/latexmk).

To skip these tests (e.g., in CI without LaTeX):
    pytest -m "not latex"
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import pytest

from promptgrimoire.export.pandoc import convert_html_to_latex
from promptgrimoire.export.pdf import LaTeXCompilationError, compile_latex
from promptgrimoire.export.pdf_export import export_annotation_pdf
from tests.conftest import requires_latexmk

if TYPE_CHECKING:
    from pathlib import Path


def _has_pandoc() -> bool:
    """Check if Pandoc is available."""
    return shutil.which("pandoc") is not None


requires_pandoc = pytest.mark.skipif(not _has_pandoc(), reason="Pandoc not installed")


@requires_pandoc
class TestHtmlToLatexIntegration:
    """Integration tests for HTML to LaTeX conversion."""

    @pytest.mark.asyncio
    async def test_legal_document_structure(self) -> None:
        """Convert legal document HTML with numbered paragraphs."""
        html = """
        <html>
        <body>
        <p><b>CASE NAME v OTHER PARTY</b></p>
        <ol start="1">
            <li>This is paragraph one of the judgment.</li>
            <li>This is paragraph two with more details.</li>
        </ol>
        <ol start="3">
            <li>Continuing with paragraph three.</li>
        </ol>
        </body>
        </html>
        """
        from pathlib import Path as RealPath

        filter_path = (
            RealPath(__file__).parent.parent.parent
            / "src"
            / "promptgrimoire"
            / "export"
            / "filters"
            / "legal.lua"
        )

        result = await convert_html_to_latex(html, filter_paths=[filter_path])

        assert "CASE NAME" in result
        assert r"\begin{enumerate}" in result
        assert "paragraph one" in result


@pytest.mark.order("first")
@requires_latexmk
class TestPdfCompilation:
    """Integration tests for LaTeX to PDF compilation."""

    @pytest.mark.asyncio
    async def test_compile_simple_document(self, tmp_path: Path) -> None:
        """Compile a simple LaTeX document to PDF."""
        tex_content = r"""
\documentclass{article}
\begin{document}
Hello, world!
\end{document}
"""
        tex_path = tmp_path / "test.tex"
        tex_path.write_text(tex_content)

        pdf_path = await compile_latex(tex_path, output_dir=tmp_path)

        assert pdf_path.exists()
        assert pdf_path.suffix == ".pdf"
        # Check it's actually a PDF (starts with %PDF)
        with pdf_path.open("rb") as f:
            header = f.read(4)
        assert header == b"%PDF"

    @pytest.mark.asyncio
    async def test_compile_failure_raises(self, tmp_path: Path) -> None:
        """Compilation failure raises LaTeXCompilationError."""
        tex_content = r"""
\documentclass{article}
\begin{document}
This has an \undefined command.
\end{document}
"""
        tex_path = tmp_path / "bad.tex"
        tex_path.write_text(tex_content)

        with pytest.raises(LaTeXCompilationError):
            await compile_latex(tex_path, output_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_output_dir_defaults_to_tex_parent(self, tmp_path: Path) -> None:
        """Output directory defaults to tex file's parent."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()

        tex_content = r"""
\documentclass{article}
\begin{document}
Test.
\end{document}
"""
        tex_path = subdir / "test.tex"
        tex_path.write_text(tex_content)

        pdf_path = await compile_latex(tex_path)

        assert pdf_path.parent == subdir


@pytest.mark.order("first")
@requires_pandoc
@requires_latexmk
class TestMarginnoteExportPipeline:
    """Tests for the marginalia+lua-ul export pipeline."""

    # test_export_annotation_pdf_basic removed — migrated to
    # test_english_mega_doc.py::TestBasicPipeline

    @pytest.mark.asyncio
    async def test_export_with_general_notes(self, tmp_path: Path) -> None:
        """export_annotation_pdf should include general notes section."""
        html = "<p>Document text here.</p>"
        highlights: list[dict] = []
        tag_colours = {"jurisdiction": "#1f77b4"}
        general_notes = "<p>These are <strong>general notes</strong> for document.</p>"

        pdf_path = await export_annotation_pdf(
            html_content=html,
            highlights=highlights,
            tag_colours=tag_colours,
            general_notes=general_notes,
            output_dir=tmp_path,
        )

        assert pdf_path.exists()
        # Check the tex file was created with notes section
        tex_path = tmp_path / "annotated_document.tex"
        tex_content = tex_path.read_text()
        assert "General Notes" in tex_content

    @pytest.mark.asyncio
    async def test_export_with_comments(self, tmp_path: Path) -> None:
        """export_annotation_pdf should include comment threads."""
        html = "<p>The court held that the defendant was liable.</p>"
        highlights = [
            {
                "id": "h1",
                "start_char": 0,
                "end_char": 4,
                "tag": "decision",
                "text": "The court held that",
                "author": "Alice",
                "created_at": "2026-01-26T10:00:00+00:00",
                "comments": [
                    {"author": "Bob", "text": "Good catch on this point."},
                    {"author": "Alice", "text": "Thanks, see also para 45."},
                ],
            }
        ]
        tag_colours = {"decision": "#e377c2"}

        pdf_path = await export_annotation_pdf(
            html_content=html,
            highlights=highlights,
            tag_colours=tag_colours,
            output_dir=tmp_path,
        )

        assert pdf_path.exists()
        # Check the tex file includes comments
        tex_path = tmp_path / "annotated_document.tex"
        tex_content = tex_path.read_text()
        assert "Bob" in tex_content
        assert "Good catch" in tex_content


# TestI18nPdfExport removed — migrated to test_i18n_mega_doc.py (Task 12).
# test_export_cjk_with_highlight removed — redundant coverage (Task 15).


@pytest.mark.order("first")
@requires_pandoc
@requires_latexmk
class TestResponseDraftExport:
    """Integration tests for PDF export with response draft markdown (Phase 7).

    Tests AC6.1 (response draft in PDF), AC6.2 (empty draft = no section),
    AC6.3 (CRDT fallback). These test the export pipeline directly, not
    the UI layer.
    """

    @pytest.mark.asyncio
    async def test_export_with_markdown_notes_ac6_1(self, tmp_path: Path) -> None:
        """AC6.1: Export PDF includes response draft content.

        Converts markdown to LaTeX via Pandoc and includes it in the
        General Notes section.
        """
        from promptgrimoire.export.pdf_export import markdown_to_latex_notes

        html = "<p>Document text for annotation.</p>"
        highlights: list[dict] = []
        tag_colours = {"jurisdiction": "#1f77b4"}

        # Simulate response draft markdown from Milkdown editor
        markdown = "# My Response\n\nThis is my **analysis** of the document."
        notes_latex = await markdown_to_latex_notes(markdown)

        pdf_path = await export_annotation_pdf(
            html_content=html,
            highlights=highlights,
            tag_colours=tag_colours,
            notes_latex=notes_latex,
            output_dir=tmp_path,
        )

        assert pdf_path.exists()
        tex_path = tmp_path / "annotated_document.tex"
        tex_content = tex_path.read_text()
        assert "General Notes" in tex_content
        assert "My Response" in tex_content
        assert "analysis" in tex_content

    @pytest.mark.asyncio
    async def test_export_empty_draft_no_section_ac6_2(self, tmp_path: Path) -> None:
        """AC6.2: Empty response draft produces no extra section in PDF."""
        html = "<p>Document text for annotation.</p>"
        highlights: list[dict] = []
        tag_colours = {"jurisdiction": "#1f77b4"}

        pdf_path = await export_annotation_pdf(
            html_content=html,
            highlights=highlights,
            tag_colours=tag_colours,
            notes_latex="",
            output_dir=tmp_path,
        )

        assert pdf_path.exists()
        tex_path = tmp_path / "annotated_document.tex"
        tex_content = tex_path.read_text()
        assert "General Notes" not in tex_content

    @pytest.mark.asyncio
    async def test_export_with_rich_markdown_ac6_1(self, tmp_path: Path) -> None:
        """AC6.1: Rich markdown (lists, bold, italic) survives export."""
        from promptgrimoire.export.pdf_export import markdown_to_latex_notes

        html = "<p>Source document.</p>"
        highlights: list[dict] = []
        tag_colours: dict[str, str] = {}

        markdown = (
            "## Key Findings\n\n"
            "- Point **one** is critical\n"
            "- Point *two* needs review\n"
            "- Point three is resolved\n\n"
            "The overall conclusion is positive."
        )
        notes_latex = await markdown_to_latex_notes(markdown)

        pdf_path = await export_annotation_pdf(
            html_content=html,
            highlights=highlights,
            tag_colours=tag_colours,
            notes_latex=notes_latex,
            output_dir=tmp_path,
        )

        assert pdf_path.exists()
        tex_path = tmp_path / "annotated_document.tex"
        tex_content = tex_path.read_text()
        assert "General Notes" in tex_content
        assert "Key Findings" in tex_content
        assert r"\begin{itemize}" in tex_content
        assert "overall conclusion" in tex_content

    @pytest.mark.asyncio
    async def test_notes_latex_takes_precedence_over_general_notes(
        self, tmp_path: Path
    ) -> None:
        """notes_latex takes precedence over general_notes HTML."""
        from promptgrimoire.export.pdf_export import markdown_to_latex_notes

        html = "<p>Document text.</p>"
        highlights: list[dict] = []
        tag_colours: dict[str, str] = {}

        # Both paths provided — LaTeX should win
        general_notes_html = "<p>HTML notes content</p>"
        markdown = "Markdown response draft content"
        notes_latex = await markdown_to_latex_notes(markdown)

        pdf_path = await export_annotation_pdf(
            html_content=html,
            highlights=highlights,
            tag_colours=tag_colours,
            general_notes=general_notes_html,
            notes_latex=notes_latex,
            output_dir=tmp_path,
        )

        assert pdf_path.exists()
        tex_path = tmp_path / "annotated_document.tex"
        tex_content = tex_path.read_text()
        assert "General Notes" in tex_content
        assert "Markdown response draft content" in tex_content


@requires_pandoc
class TestGenerateTexOnly:
    """Tests for generate_tex_only() — AC1.4.

    generate_tex_only() runs the full export pipeline up to .tex file creation
    but does NOT invoke compile_latex(). This enables fast assertions on LaTeX
    content without paying the 5-10s compilation cost.
    """

    @pytest.mark.asyncio
    async def test_returns_tex_path_without_compilation(self, tmp_path: Path) -> None:
        """AC1.4: generate_tex_only() returns .tex path, no PDF created."""
        from promptgrimoire.export.pdf_export import generate_tex_only

        html = "<p>This is a test document with highlighted text.</p>"
        highlights = [
            {
                "id": "h1",
                "start_char": 3,
                "end_char": 5,
                "tag": "jurisdiction",
                "text": "test document",
                "author": "Tester",
                "created_at": "2026-01-26T14:30:00+00:00",
                "comments": [],
            }
        ]
        tag_colours = {"jurisdiction": "#1f77b4"}

        tex_path = await generate_tex_only(
            html_content=html,
            highlights=highlights,
            tag_colours=tag_colours,
            output_dir=tmp_path,
        )

        # Returns a Path to a .tex file that exists
        assert tex_path.exists(), "generate_tex_only() must create the .tex file"
        assert tex_path.suffix == ".tex"

        # .tex file contains expected LaTeX structure
        tex_content = tex_path.read_text()
        assert r"\documentclass" in tex_content
        assert r"\begin{document}" in tex_content

        # .tex file contains highlight commands (from the annotation pipeline)
        assert r"\highLight" in tex_content or r"\underLine" in tex_content

        # No PDF file exists — compile_latex was NOT called
        pdf_files = list(tmp_path.glob("*.pdf"))
        assert pdf_files == [], (
            f"generate_tex_only() must NOT produce a PDF, found: {pdf_files}"
        )

    @pytest.mark.asyncio
    async def test_with_general_notes(self, tmp_path: Path) -> None:
        """generate_tex_only() includes General Notes section when provided."""
        from promptgrimoire.export.pdf_export import generate_tex_only

        html = "<p>Document text here.</p>"
        general_notes = "<p>These are <strong>general notes</strong> for document.</p>"

        tex_path = await generate_tex_only(
            html_content=html,
            highlights=[],
            tag_colours={"jurisdiction": "#1f77b4"},
            output_dir=tmp_path,
            general_notes=general_notes,
        )

        tex_content = tex_path.read_text()
        assert "General Notes" in tex_content

    @pytest.mark.asyncio
    async def test_with_notes_latex(self, tmp_path: Path) -> None:
        """generate_tex_only() includes pre-converted LaTeX notes."""
        from promptgrimoire.export.pdf_export import generate_tex_only

        html = "<p>Document text here.</p>"
        notes_latex = r"This is \textbf{pre-converted} LaTeX notes content."

        tex_path = await generate_tex_only(
            html_content=html,
            highlights=[],
            tag_colours={"jurisdiction": "#1f77b4"},
            output_dir=tmp_path,
            notes_latex=notes_latex,
        )

        tex_content = tex_path.read_text()
        assert "General Notes" in tex_content
        assert r"pre-converted" in tex_content
