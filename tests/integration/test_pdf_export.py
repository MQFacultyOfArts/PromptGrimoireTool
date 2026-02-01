"""Integration tests for PDF export pipeline.

These tests require external dependencies (Pandoc, TinyTeX/latexmk).
Tests are skipped if dependencies are not available.
"""

from __future__ import annotations

import shutil
from pathlib import Path as RealPath
from typing import TYPE_CHECKING

import pytest

from promptgrimoire.export.latex import convert_html_to_latex
from promptgrimoire.export.pdf import LaTeXCompilationError, compile_latex
from promptgrimoire.export.pdf_export import export_annotation_pdf
from tests.conftest import requires_latexmk

if TYPE_CHECKING:
    from pathlib import Path

# Fixture paths for i18n tests
FIXTURES_DIR = RealPath(__file__).parent.parent / "fixtures" / "conversations"


def _has_pandoc() -> bool:
    """Check if Pandoc is available."""
    return shutil.which("pandoc") is not None


requires_pandoc = pytest.mark.skipif(not _has_pandoc(), reason="Pandoc not installed")


@requires_pandoc
class TestHtmlToLatexIntegration:
    """Integration tests for HTML to LaTeX conversion."""

    def test_legal_document_structure(self) -> None:
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

        result = convert_html_to_latex(html, filter_path=filter_path)

        assert "CASE NAME" in result
        assert r"\begin{enumerate}" in result
        assert "paragraph one" in result


@requires_latexmk
class TestPdfCompilation:
    """Integration tests for LaTeX to PDF compilation."""

    def test_compile_simple_document(self, tmp_path: Path) -> None:
        """Compile a simple LaTeX document to PDF."""
        tex_content = r"""
\documentclass{article}
\begin{document}
Hello, world!
\end{document}
"""
        tex_path = tmp_path / "test.tex"
        tex_path.write_text(tex_content)

        pdf_path = compile_latex(tex_path, output_dir=tmp_path)

        assert pdf_path.exists()
        assert pdf_path.suffix == ".pdf"
        # Check it's actually a PDF (starts with %PDF)
        with pdf_path.open("rb") as f:
            header = f.read(4)
        assert header == b"%PDF"

    def test_compile_failure_raises(self, tmp_path: Path) -> None:
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
            compile_latex(tex_path, output_dir=tmp_path)

    def test_output_dir_defaults_to_tex_parent(self, tmp_path: Path) -> None:
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

        pdf_path = compile_latex(tex_path)

        assert pdf_path.parent == subdir


@requires_pandoc
@requires_latexmk
class TestMarginnoteExportPipeline:
    """Tests for the marginalia+lua-ul export pipeline."""

    @pytest.mark.asyncio
    async def test_export_annotation_pdf_basic(self, tmp_path: Path) -> None:
        """export_annotation_pdf should produce a valid PDF."""
        html = "<p>This is a test document with highlighted text.</p>"
        highlights = [
            {
                "id": "h1",
                "start_word": 3,
                "end_word": 5,
                "tag": "jurisdiction",
                "text": "test document",
                "author": "Tester",
                "created_at": "2026-01-26T14:30:00+00:00",
                "comments": [],
            }
        ]
        tag_colours = {"jurisdiction": "#1f77b4"}

        pdf_path = await export_annotation_pdf(
            html_content=html,
            highlights=highlights,
            tag_colours=tag_colours,
            output_dir=tmp_path,
        )

        assert pdf_path.exists()
        assert pdf_path.suffix == ".pdf"
        # Check it's actually a PDF
        with pdf_path.open("rb") as f:
            header = f.read(4)
        assert header == b"%PDF"

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
                "start_word": 0,
                "end_word": 4,
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


@requires_pandoc
@requires_latexmk
class TestI18nPdfExport:
    """Integration tests for multilingual PDF export (Issue #101)."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "fixture_name",
        [
            "chinese_wikipedia",
            "translation_japanese_sample",
            "translation_korean_sample",
            "translation_spanish_sample",
        ],
    )
    async def test_export_i18n_fixture(self, tmp_path: Path, fixture_name: str) -> None:
        """Export multilingual fixture to PDF without errors."""
        fixture_path = FIXTURES_DIR / f"{fixture_name}.html"
        if not fixture_path.exists():
            pytest.skip(f"Fixture {fixture_name}.html not found")

        html_content = fixture_path.read_text(encoding="utf-8")
        # Strip HTML tags for raw content simulation
        import re

        text_content = re.sub(r"<[^>]+>", " ", html_content)
        text_content = re.sub(r"\s+", " ", text_content).strip()

        # Use first 2000 chars to keep test fast
        text_content = text_content[:2000]

        pdf_path = await export_annotation_pdf(
            html_content=text_content,
            highlights=[],
            tag_colours={},
            output_dir=tmp_path,
            filename=fixture_name,
        )

        assert pdf_path.exists(), f"PDF not created for {fixture_name}"
        assert pdf_path.stat().st_size > 0, f"PDF is empty for {fixture_name}"
        # Verify PDF header
        with pdf_path.open("rb") as f:
            header = f.read(4)
        assert header == b"%PDF", f"Invalid PDF header for {fixture_name}"

    @pytest.mark.asyncio
    async def test_export_cjk_with_highlight(self, tmp_path: Path) -> None:
        """Export CJK content with highlight annotation."""
        html = "这是中文测试文本。日本語のテスト。한국어 테스트."
        highlights = [
            {
                "id": "h1",
                "start_word": 0,
                "end_word": 1,
                "tag": "jurisdiction",
                "text": "这是中文",
                "author": "Tester",
                "created_at": "2026-01-26T14:30:00+00:00",
                "comments": [],
            }
        ]
        tag_colours = {"jurisdiction": "#1f77b4"}

        pdf_path = await export_annotation_pdf(
            html_content=html,
            highlights=highlights,
            tag_colours=tag_colours,
            output_dir=tmp_path,
            filename="cjk_highlight_test",
        )

        assert pdf_path.exists()
        assert pdf_path.stat().st_size > 0
