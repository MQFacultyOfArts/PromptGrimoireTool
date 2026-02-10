"""Integration tests for PDF export pipeline.

These tests require external dependencies (Pandoc, TinyTeX/latexmk).

To skip these tests (e.g., in CI without LaTeX):
    pytest -m "not latex"
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path as RealPath
from typing import TYPE_CHECKING, ClassVar

import pytest

from promptgrimoire.export.pandoc import convert_html_to_latex
from promptgrimoire.export.pdf import LaTeXCompilationError, compile_latex
from promptgrimoire.export.pdf_export import export_annotation_pdf
from tests.conftest import PDF_TEST_OUTPUT_DIR, requires_latexmk

if TYPE_CHECKING:
    from pathlib import Path

# Fixture paths for i18n tests - use clean fixtures (article content only)
FIXTURES_DIR = RealPath(__file__).parent.parent / "fixtures" / "conversations" / "clean"


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

    @pytest.mark.asyncio
    async def test_export_annotation_pdf_basic(self, tmp_path: Path) -> None:
        """export_annotation_pdf should produce a valid PDF."""
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


@pytest.mark.order("first")
@requires_pandoc
@requires_latexmk
class TestI18nPdfExport:
    """Integration tests for multilingual PDF export (Issue #101).

    Output saved to: output/test_output/i18n_exports/

    Tests verify:
    - PDF is created and valid
    - LaTeX log has no font substitution errors
    - TEX file contains expected i18n characters
    """

    # Persistent output directory for visual inspection
    _OUTPUT_DIR = PDF_TEST_OUTPUT_DIR / "i18n_exports"

    # Expected characters per fixture (for content verification)
    # Must match actual content in first 2000 chars of fixture
    _EXPECTED_CHARS: ClassVar[dict[str, list[str]]] = {
        "chinese_wikipedia": ["维基百科", "示例内容"],  # from clean fixture
        "translation_japanese_sample": ["家庭法令", "離婚判決謄本", "オーストラリア"],
        "translation_korean_sample": [
            "법은",
            "차이를",
            "조정하는",
        ],  # "Law" "differences" "coordinating"
        "translation_spanish_sample": ["vehículo", "búsqueda"],  # "vehicle" "search"
    }

    @staticmethod
    def _check_log_for_font_errors(log_path: RealPath) -> list[str]:
        """Check LaTeX log for font-related errors.

        Returns list of error lines found (empty if clean).
        """
        if not log_path.exists():
            return ["Log file not found"]

        errors = []
        log_content = log_path.read_text(encoding="utf-8", errors="replace")

        # Patterns indicating font problems
        error_patterns = [
            "Font .* not found",
            "Missing character:",
            "! Font \\\\",
            "kpathsea: Running mktextfm",  # Font generation = missing font
        ]

        for line in log_content.split("\n"):
            for pattern in error_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    errors.append(line.strip())
                    break

        return errors

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
    async def test_export_i18n_fixture(self, fixture_name: str) -> None:
        """Export multilingual fixture to PDF without errors.

        Verifies:
        1. PDF is created with valid header
        2. TEX file contains expected i18n characters
        3. LaTeX log has no font substitution errors
        """
        fixture_path = FIXTURES_DIR / f"{fixture_name}.html"
        if not fixture_path.exists():
            pytest.skip(f"Fixture {fixture_name}.html not found")

        # Pass raw HTML to export - production pipeline handles script stripping
        html_content = fixture_path.read_text(encoding="utf-8")

        # Use persistent output directory for inspection
        output_dir = self._OUTPUT_DIR / fixture_name
        output_dir.mkdir(parents=True, exist_ok=True)

        pdf_path = await export_annotation_pdf(
            html_content=html_content,
            highlights=[],
            tag_colours={},
            output_dir=output_dir,
            filename=fixture_name,
        )

        # 1. Verify PDF is created and valid
        assert pdf_path.exists(), f"PDF not created for {fixture_name}"
        assert pdf_path.stat().st_size > 0, f"PDF is empty for {fixture_name}"
        with pdf_path.open("rb") as f:
            header = f.read(4)
        assert header == b"%PDF", f"Invalid PDF header for {fixture_name}"

        # 2. Verify TEX file contains expected i18n characters
        tex_path = output_dir / f"{fixture_name}.tex"
        assert tex_path.exists(), f"TEX file not found for {fixture_name}"
        tex_content = tex_path.read_text(encoding="utf-8")

        expected_chars = self._EXPECTED_CHARS.get(fixture_name, [])
        for expected in expected_chars:
            assert expected in tex_content, (
                f"Expected '{expected}' not found in TEX for {fixture_name}"
            )

        # 3. Verify LaTeX log has no font errors
        log_path = output_dir / f"{fixture_name}.log"
        font_errors = self._check_log_for_font_errors(log_path)
        assert not font_errors, f"Font errors in {fixture_name}:\n" + "\n".join(
            font_errors[:5]
        )

    @pytest.mark.asyncio
    async def test_export_cjk_with_highlight(self) -> None:
        """Export CJK content with highlight annotation."""
        html = "这是中文测试文本。日本語のテスト。한국어 테스트."
        highlights = [
            {
                "id": "h1",
                "start_char": 0,
                "end_char": 1,
                "tag": "jurisdiction",
                "text": "这是中文",
                "author": "Tester",
                "created_at": "2026-01-26T14:30:00+00:00",
                "comments": [],
            }
        ]
        tag_colours = {"jurisdiction": "#1f77b4"}

        # Use persistent output directory for inspection
        output_dir = self._OUTPUT_DIR / "cjk_highlight_test"
        output_dir.mkdir(parents=True, exist_ok=True)

        pdf_path = await export_annotation_pdf(
            html_content=html,
            highlights=highlights,
            tag_colours=tag_colours,
            output_dir=output_dir,
            filename="cjk_highlight_test",
        )

        assert pdf_path.exists()
        assert pdf_path.stat().st_size > 0


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
    async def test_export_with_markdown_notes_ac6_1(self, tmp_path: RealPath) -> None:
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
    async def test_export_empty_draft_no_section_ac6_2(
        self, tmp_path: RealPath
    ) -> None:
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
    async def test_export_with_rich_markdown_ac6_1(self, tmp_path: RealPath) -> None:
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
        self, tmp_path: RealPath
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
