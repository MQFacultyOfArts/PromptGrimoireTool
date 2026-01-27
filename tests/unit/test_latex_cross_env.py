"""Tests for LaTeX highlight behavior across environment boundaries.

These tests demonstrate the current (broken) behavior where highlights
spanning list items cause LaTeX compilation errors. The output artifacts
allow visual inspection before implementing fixes.
"""

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from promptgrimoire.export.latex import (
    build_annotation_preamble,
    convert_html_with_annotations,
)
from promptgrimoire.export.pdf import LaTeXCompilationError, compile_latex
from promptgrimoire.parsers.rtf import parse_rtf

if TYPE_CHECKING:
    from promptgrimoire.models import ParsedRTF

# Output directory for inspection
_OUTPUT_DIR = Path("output/unit/test_latex_cross_env")

# Run all RTF tests on same worker to share LibreOffice process
pytestmark = pytest.mark.xdist_group("rtf_parser")


@pytest.fixture(scope="module")
def parsed_lawlis() -> ParsedRTF:
    """Parse 183.rtf once for all tests in module."""
    path = Path(__file__).parent.parent / "fixtures" / "183.rtf"
    return parse_rtf(path)


# Standard tag colours from live_annotation_demo.py
TAG_COLOURS = {
    "jurisdiction": "#1f77b4",
    "procedural_history": "#ff7f0e",
    "legally_relevant_facts": "#2ca02c",
    "legal_issues": "#d62728",
    "reasons": "#9467bd",
    "courts_reasoning": "#8c564b",
    "decision": "#e377c2",
    "order": "#7f7f7f",
    "domestic_sources": "#bcbd22",
    "reflection": "#17becf",
}


class TestCrossEnvironmentHighlights:
    """Tests demonstrating highlight behavior across list boundaries."""

    def test_highlight_spanning_list_items_generates_latex(
        self, parsed_lawlis: ParsedRTF
    ) -> None:
        """Generate LaTeX with highlight spanning list items for inspection.

        Uses words 848-905 which span across an \\item boundary in the source
        document (per E2E test spec: order tag overlaps with reasons).
        """
        # Highlight spanning list boundary
        highlights = [
            {
                "start_word": 848,
                "end_word": 906,  # CRDT uses exclusive end
                "tag": "order",
                "author": "Test User",
                "text": "test",
                "comments": [],
                "created_at": "2026-01-27T10:00:00+00:00",
            }
        ]

        # Convert to LaTeX
        latex_body = convert_html_with_annotations(
            html=parsed_lawlis.html,
            highlights=highlights,
            tag_colours=TAG_COLOURS,
        )

        # Build complete document
        preamble = build_annotation_preamble(TAG_COLOURS)
        document = f"""\\documentclass[a4paper,12pt]{{article}}
{preamble}

\\begin{{document}}

{latex_body}

\\end{{document}}
"""

        # Save for inspection
        _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        tex_path = _OUTPUT_DIR / "cross_env_highlight.tex"
        tex_path.write_text(document)

        # Basic assertions
        assert "\\highLight" in latex_body
        assert "\\annot{tag-order}" in latex_body

        print(f"\nLaTeX saved to: {tex_path.absolute()}")

    def test_compilation_fails_with_lonely_item(self, parsed_lawlis: ParsedRTF) -> None:
        """Confirm that cross-environment highlights cause compilation failure.

        This test documents the current broken behavior - it should fail
        until we implement proper environment boundary splitting.
        """
        highlights = [
            {
                "start_word": 848,
                "end_word": 906,
                "tag": "order",
                "author": "Test User",
                "text": "test",
                "comments": [],
                "created_at": "2026-01-27T10:00:00+00:00",
            }
        ]

        latex_body = convert_html_with_annotations(
            html=parsed_lawlis.html,
            highlights=highlights,
            tag_colours=TAG_COLOURS,
        )

        preamble = build_annotation_preamble(TAG_COLOURS)
        document = f"""\\documentclass[a4paper,12pt]{{article}}
{preamble}

\\begin{{document}}

{latex_body}

\\end{{document}}
"""

        _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        tex_path = _OUTPUT_DIR / "cross_env_compile_test.tex"
        tex_path.write_text(document)

        # Expect compilation to fail with "Lonely \item" or similar
        with pytest.raises(LaTeXCompilationError) as exc_info:
            compile_latex(tex_path, _OUTPUT_DIR)

        # Verify we can inspect the error
        assert exc_info.value.tex_path == tex_path
        assert exc_info.value.log_path.exists()

        print(f"\nExpected failure - Log: {exc_info.value.log_path}")
