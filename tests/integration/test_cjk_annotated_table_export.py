"""Integration tests: CJK + annotated table export pipeline (#351).

Tests verify the full generate_tex_only() pipeline produces correct
LaTeX from CJK content with annotations in table cells.

For slow compilation tests (AC1.1, AC1.2, AC4.3, AC5.1), see the
TestCjkSlowCompilation class which requires full latexmk.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
import pytest_asyncio

from promptgrimoire.export.pdf_export import generate_tex_only
from tests.conftest import requires_full_latexmk, requires_pandoc

FIXTURE_DIR = Path(__file__).parents[1] / "fixtures"

# Tag colours matching the fixture's data-annots attributes.
# The exact hex values don't matter for tex generation — only
# that entries exist so the preamble defines the colour commands.
_TAG_COLOURS: dict[str, str] = {
    "tag-issue": "#d62728",
    "tag-ratio": "#2ca02c",
    "tag-rule": "#9467bd",
}


def _load_minimal_html() -> str:
    path = FIXTURE_DIR / "workspace_cjk_annotated_table.html"
    return path.read_text()


def _load_yuki_fixture() -> dict:
    path = FIXTURE_DIR / "workspace_cjk_yuki.json"
    with path.open() as f:
        return json.load(f)


class TestCjkAnnotatedTablePipeline:
    """AC1.3, AC2.1, AC2.2: generate_tex_only with CJK + annotated table."""

    @requires_pandoc
    @pytest.mark.asyncio
    async def test_generates_tex_without_crash(
        self,
        tmp_path: Path,
    ) -> None:
        """AC1.3: Pipeline completes without crash or timeout."""
        html = _load_minimal_html()
        tex_path = await generate_tex_only(
            html_content=html,
            highlights=[],
            tag_colours=_TAG_COLOURS,
            output_dir=tmp_path,
        )
        assert tex_path.exists()
        content = tex_path.read_text()
        assert len(content) > 100

    @requires_pandoc
    @pytest.mark.asyncio
    async def test_annotref_in_tex(self, tmp_path: Path) -> None:
        """AC2.1: \\annotref appears in generated .tex."""
        html = _load_minimal_html()
        tex_path = await generate_tex_only(
            html_content=html,
            highlights=[],
            tag_colours=_TAG_COLOURS,
            output_dir=tmp_path,
        )
        content = tex_path.read_text()
        assert "\\annotref{" in content

    @requires_pandoc
    @pytest.mark.asyncio
    async def test_annotendnote_in_tex(self, tmp_path: Path) -> None:
        """AC2.2: \\annotendnote appears in generated .tex."""
        html = _load_minimal_html()
        tex_path = await generate_tex_only(
            html_content=html,
            highlights=[],
            tag_colours=_TAG_COLOURS,
            output_dir=tmp_path,
        )
        content = tex_path.read_text()
        assert "\\annotendnote{" in content

    @requires_pandoc
    @pytest.mark.asyncio
    async def test_no_annot_inside_longtable(
        self,
        tmp_path: Path,
    ) -> None:
        """Regression guard: no \\annot{} inside longtable at pipeline level."""
        import re

        html = _load_minimal_html()
        tex_path = await generate_tex_only(
            html_content=html,
            highlights=[],
            tag_colours=_TAG_COLOURS,
            output_dir=tmp_path,
        )
        content = tex_path.read_text()
        regions = re.findall(
            r"\\begin\{longtable\}.*?\\end\{longtable\}",
            content,
            re.DOTALL,
        )
        for region in regions:
            assert "\\annot{" not in region


# ===================================================================
# Slow compilation tests (full PDF output)
# ===================================================================


@requires_full_latexmk
@pytest.mark.slow
class TestCjkSlowCompilation:
    """AC1.1, AC1.2, AC4.3, AC5.1: Full compilation of CJK workspace."""

    @pytest_asyncio.fixture(scope="class", loop_scope="class")
    async def compilation_result(
        self,
        tmp_path_factory,
    ) -> dict:
        """Compile Yuki workspace once, reuse across class tests."""
        from promptgrimoire.export.pdf import compile_latex

        output_dir = tmp_path_factory.mktemp("cjk_yuki")
        fixture = _load_yuki_fixture()

        # Extract HTML content from workspace documents
        docs = fixture.get("documents", [])
        assert len(docs) >= 1, "Yuki fixture must have documents"
        html_content = docs[0].get("content", "")
        assert html_content, "Document content must not be empty"

        # Build highlights from CRDT state if available,
        # otherwise pass empty (data-annots are in the HTML)
        highlights: list[dict] = []

        # Tag colours for the Yuki workspace
        tag_colours: dict[str, str] = {
            "prompt": "#1f77b4",
            "MT RISK": "#d62728",
            "Interesting Points": "#2ca02c",
        }

        t0 = time.monotonic()
        tex_path = await generate_tex_only(
            html_content=html_content,
            highlights=highlights,
            tag_colours=tag_colours,
            output_dir=output_dir,
        )
        pdf_path = await compile_latex(tex_path, output_dir)
        elapsed = time.monotonic() - t0

        return {
            "pdf_path": pdf_path,
            "tex_path": tex_path,
            "elapsed": elapsed,
            "output_dir": output_dir,
        }

    def test_pdf_exists_and_nonempty(
        self,
        compilation_result: dict,
    ) -> None:
        """AC1.1/AC5.1: PDF exists and is non-empty."""
        pdf_path = compilation_result["pdf_path"]
        assert pdf_path.exists()
        assert pdf_path.stat().st_size > 0

    def test_compilation_under_30_seconds(
        self,
        compilation_result: dict,
    ) -> None:
        """AC1.2: Total pipeline completes within 30 seconds."""
        elapsed = compilation_result["elapsed"]
        assert elapsed < 30, f"Compilation took {elapsed:.1f}s (limit: 30s)"
