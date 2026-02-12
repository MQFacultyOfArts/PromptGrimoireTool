"""Infrastructure verification tests for mega-document compilation.

Verifies that the mega-document builder (compile_mega_document) works
correctly with the subfiles LaTeX package:
- Main .tex compiles to PDF
- Each subfile .tex is independently compilable
- MegaDocResult contains expected segment data
- PDF text contains content from all segments
- Subtests work independently (AC1.6)

AC1.5: Each mega-document body segment is independently compilable via subfiles.
AC1.6: A subtest failure in mega-doc does not prevent remaining subtests.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from promptgrimoire.export.pdf import compile_latex
from tests.conftest import requires_latexmk
from tests.integration.conftest import MegaDocSegment, compile_mega_document


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def mega_result(tmp_path_factory):
    """Compile a mega-document with 2 simple segments.

    Module-scoped to match the pattern used by real mega-document
    fixtures (English, i18n). Compiles once, shared across all tests
    in this module.
    """
    output_dir = tmp_path_factory.mktemp("mega_infra")
    segments = [
        MegaDocSegment(
            name="segment_alpha",
            html="<p>Alpha segment content for infrastructure test.</p>",
            preprocess=False,
        ),
        MegaDocSegment(
            name="segment_beta",
            html="<p>Beta segment content with different text.</p>",
            preprocess=False,
        ),
    ]
    return await compile_mega_document(segments, output_dir)


@requires_latexmk
class TestMegaDocInfrastructure:
    """Verify mega-document compilation infrastructure."""

    @pytest.mark.asyncio(loop_scope="module")
    async def test_mega_doc_compiles_to_pdf(self, mega_result):
        """Main .tex compiles to a non-empty PDF."""
        assert mega_result.pdf_path.exists(), "PDF was not created"
        assert mega_result.pdf_path.stat().st_size > 0, "PDF is empty"
        # Verify PDF magic bytes
        header = mega_result.pdf_path.read_bytes()[:5]
        assert header == b"%PDF-", f"Not a valid PDF: {header!r}"

    @pytest.mark.asyncio(loop_scope="module")
    async def test_segment_tex_has_entries(self, mega_result):
        """MegaDocResult.segment_tex has entries for both segments."""
        assert "segment_alpha" in mega_result.segment_tex
        assert "segment_beta" in mega_result.segment_tex
        assert len(mega_result.segment_tex) == 2

    @pytest.mark.asyncio(loop_scope="module")
    async def test_subfile_paths_exist(self, mega_result):
        """Each subfile .tex file exists on disk."""
        for name, path in mega_result.subfile_paths.items():
            assert path.exists(), f"Subfile {name} not found at {path}"
            assert path.stat().st_size > 0, f"Subfile {name} is empty"

    @pytest.mark.asyncio(loop_scope="module")
    async def test_subfiles_independently_compilable(self, mega_result):
        """AC1.5: Each subfile compiles independently via subfiles package."""
        for name, sf_path in mega_result.subfile_paths.items():
            # Compile each subfile standalone -- it should load the main
            # document's preamble via \documentclass[mega_test.tex]{subfiles}
            pdf_path = await compile_latex(sf_path, mega_result.output_dir)
            assert pdf_path.exists(), f"Subfile {name} failed to compile independently"

    @pytest.mark.asyncio(loop_scope="module")
    async def test_pdf_text_contains_both_segments(self, mega_result):
        """PDF text extraction contains content from both segments."""
        assert "Alpha segment content" in mega_result.pdf_text
        assert "Beta segment content" in mega_result.pdf_text

    @pytest.mark.asyncio(loop_scope="module")
    async def test_main_tex_structure(self, mega_result):
        """Main .tex has correct subfiles structure."""
        tex_content = mega_result.tex_path.read_text()
        assert r"\usepackage{subfiles}" in tex_content
        assert r"\subfile{segment_alpha}" in tex_content
        assert r"\subfile{segment_beta}" in tex_content
        assert r"\clearpage" in tex_content
        assert r"\begin{document}" in tex_content
        assert r"\end{document}" in tex_content

    @pytest.mark.asyncio(loop_scope="module")
    async def test_subfile_tex_structure(self, mega_result):
        """Subfiles have correct documentclass pointing to main document."""
        for name, sf_path in mega_result.subfile_paths.items():
            content = sf_path.read_text()
            assert r"\documentclass[mega_test.tex]{subfiles}" in content, (
                f"Subfile {name} missing correct documentclass"
            )
            assert r"\begin{document}" in content
            assert r"\end{document}" in content

    @pytest.mark.asyncio(loop_scope="module")
    async def test_subtests_independent_execution(self, mega_result, subtests):
        """AC1.6: Subtest failures do not prevent remaining subtests.

        Each segment assertion is wrapped in a subtest context. If one
        fails, the others should still execute.
        """
        segment_names = ["segment_alpha", "segment_beta"]
        for name in segment_names:
            with subtests.test(msg=name):
                assert name in mega_result.segment_tex
                assert name in mega_result.subfile_paths
                assert mega_result.subfile_paths[name].exists()
