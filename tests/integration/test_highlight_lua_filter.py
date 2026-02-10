"""Pandoc round-trip integration tests for highlight.lua filter.

Verifies AC2.1--AC2.6 by running Pandoc as a subprocess with test HTML
and the Lua filter, asserting on LaTeX output.

AC2.1: Single highlight tier
AC2.2: Two-highlight tier (stacked underlines)
AC2.3: Three+ highlight tier (many-dark underline)
AC2.4: Annotation emission (pre-formatted LaTeX)
AC2.5: Heading safety (Pandoc \texorpdfstring wrapping)
AC2.6: No hl attribute (pass-through)
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import pytest

# Path to the Lua filter relative to the project root
_FILTER_PATH = (
    Path(__file__).parents[2]
    / "src"
    / "promptgrimoire"
    / "export"
    / "filters"
    / "highlight.lua"
)


def _run_pandoc_with_filter(html: str) -> str:
    """Run Pandoc with the highlight Lua filter on an HTML input string.

    Writes *html* to a temporary file, invokes Pandoc as a subprocess,
    and returns the LaTeX output.

    Args:
        html: HTML content to convert.

    Returns:
        LaTeX string produced by Pandoc with the filter applied.

    Raises:
        subprocess.CalledProcessError: If Pandoc exits with non-zero status.
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=True) as tmp:
        tmp.write(html)
        tmp.flush()
        result = subprocess.run(
            [
                "pandoc",
                "-f",
                "html+native_divs",
                "-t",
                "latex",
                "--no-highlight",
                "--lua-filter",
                str(_FILTER_PATH),
                tmp.name,
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    return result.stdout


@pytest.fixture(autouse=True)
def _check_filter_exists() -> None:
    """Skip all tests if the Lua filter file is missing."""
    if not _FILTER_PATH.exists():
        pytest.skip(f"Lua filter not found: {_FILTER_PATH}")


class TestSingleHighlight:
    """AC2.1: Single highlight tier produces correct LaTeX wrapping."""

    def test_single_highlight_emits_highlight_and_underline(self) -> None:
        html = (
            "<p>"
            '<span data-hl="0" data-colors="tag-jurisdiction-light">'
            "highlighted text"
            "</span>"
            "</p>"
        )
        latex = _run_pandoc_with_filter(html)

        assert r"\highLight[tag-jurisdiction-light]{" in latex
        assert (
            r"\underLine[color=tag-jurisdiction-dark, height=1pt, bottom=-3pt]{"
            in latex
        )

    def test_single_highlight_content_preserved(self) -> None:
        html = (
            "<p>"
            '<span data-hl="0" data-colors="tag-jurisdiction-light">'
            "highlighted text"
            "</span>"
            "</p>"
        )
        latex = _run_pandoc_with_filter(html)

        assert "highlighted" in latex
        assert "text" in latex


class TestTwoHighlights:
    """AC2.2: Two-highlight tier produces nested highlights and stacked underlines."""

    def test_two_highlights_nested_highlight_wrappers(self) -> None:
        html = (
            "<p>"
            '<span data-hl="0,1" '
            'data-colors="tag-jurisdiction-light,tag-evidence-light">'
            "double highlight"
            "</span>"
            "</p>"
        )
        latex = _run_pandoc_with_filter(html)

        assert r"\highLight[tag-jurisdiction-light]{" in latex
        assert r"\highLight[tag-evidence-light]{" in latex

    def test_two_highlights_stacked_underlines(self) -> None:
        html = (
            "<p>"
            '<span data-hl="0,1" '
            'data-colors="tag-jurisdiction-light,tag-evidence-light">'
            "double highlight"
            "</span>"
            "</p>"
        )
        latex = _run_pandoc_with_filter(html)

        # Outer underline: 2pt, -5pt
        assert (
            r"\underLine[color=tag-jurisdiction-dark, height=2pt, bottom=-5pt]{"
            in latex
        )
        # Inner underline: 1pt, -3pt
        assert r"\underLine[color=tag-evidence-dark, height=1pt, bottom=-3pt]{" in latex

    def test_two_highlights_nesting_order(self) -> None:
        """Outer highlight (lower index) wraps inner (higher index)."""
        html = (
            "<p>"
            '<span data-hl="0,1" '
            'data-colors="tag-jurisdiction-light,tag-evidence-light">'
            "nested"
            "</span>"
            "</p>"
        )
        latex = _run_pandoc_with_filter(html)

        # jurisdiction (outer) should appear before evidence (inner) in opens
        idx_jurisdiction = latex.find(r"\highLight[tag-jurisdiction-light]{")
        idx_evidence = latex.find(r"\highLight[tag-evidence-light]{")
        assert idx_jurisdiction < idx_evidence, (
            "Outer highlight (jurisdiction) should wrap inner (evidence)"
        )


class TestManyHighlights:
    """AC2.3: Three+ highlights use single thick many-dark underline."""

    def test_three_highlights_many_dark_underline(self) -> None:
        html = (
            "<p>"
            '<span data-hl="0,1,2" '
            'data-colors="tag-jurisdiction-light,tag-evidence-light,tag-ratio-light">'
            "many highlights"
            "</span>"
            "</p>"
        )
        latex = _run_pandoc_with_filter(html)

        assert r"\underLine[color=many-dark, height=4pt, bottom=-5pt]{" in latex

    def test_three_highlights_three_nested_highlight_wrappers(self) -> None:
        html = (
            "<p>"
            '<span data-hl="0,1,2" '
            'data-colors="tag-jurisdiction-light,tag-evidence-light,tag-ratio-light">'
            "many highlights"
            "</span>"
            "</p>"
        )
        latex = _run_pandoc_with_filter(html)

        assert r"\highLight[tag-jurisdiction-light]{" in latex
        assert r"\highLight[tag-evidence-light]{" in latex
        assert r"\highLight[tag-ratio-light]{" in latex

    def test_three_highlights_no_individual_underlines(self) -> None:
        """With 3+ highlights, only many-dark underline should appear."""
        html = (
            "<p>"
            '<span data-hl="0,1,2" '
            'data-colors="tag-jurisdiction-light,tag-evidence-light,tag-ratio-light">'
            "many highlights"
            "</span>"
            "</p>"
        )
        latex = _run_pandoc_with_filter(html)

        # Should NOT have individual dark colour underlines
        assert "tag-jurisdiction-dark" not in latex
        assert "tag-evidence-dark" not in latex
        assert "tag-ratio-dark" not in latex


class TestAnnotation:
    """AC2.4: Annotation attribute emitted as RawInline after highlight wrapping."""

    def test_annotation_emitted_after_highlight(self) -> None:
        annot = (
            r"\annot{tag-jurisdiction}"
            r"{\textbf{Jurisdiction}\par{\scriptsize Alice}}"
        )
        html = (
            "<p>"
            '<span data-hl="0" data-colors="tag-jurisdiction-light" '
            f'data-annots="{annot}"'
            ">"
            "annotated text"
            "</span>"
            "</p>"
        )
        latex = _run_pandoc_with_filter(html)

        assert r"\annot{tag-jurisdiction}" in latex
        assert r"\textbf{Jurisdiction}" in latex
        assert r"\scriptsize Alice" in latex

    def test_annotation_appears_after_closing_braces(self) -> None:
        """The annotation must appear AFTER the highlight/underline closing braces."""
        html = (
            "<p>"
            '<span data-hl="0" data-colors="tag-jurisdiction-light" '
            r'data-annots="\annot{tag-jurisdiction}{content}"'
            ">"
            "text"
            "</span>"
            "</p>"
        )
        latex = _run_pandoc_with_filter(html)

        # Find the last closing brace of the highlight wrapping
        # The annotation should come after that
        idx_annot = latex.find(r"\annot{")
        idx_highlight_open = latex.find(r"\highLight[")
        assert idx_annot > idx_highlight_open, (
            "Annotation should appear after highlight opening"
        )

        # Count braces: after highlight opens and content, all highlight/underline
        # braces should close before \annot appears
        before_annot = latex[:idx_annot]
        open_braces = before_annot.count("{")
        close_braces = before_annot.count("}")
        assert open_braces == close_braces, (
            f"All highlight/underline braces should be closed before \\annot: "
            f"opens={open_braces}, closes={close_braces}"
        )


class TestHeading:
    """AC2.5: Pandoc auto-wraps highlighted heading content in texorpdfstring."""

    def test_heading_gets_texorpdfstring(self) -> None:
        html = (
            "<h2>"
            '<span data-hl="0" data-colors="tag-jurisdiction-light">'
            "heading text"
            "</span>"
            "</h2>"
        )
        latex = _run_pandoc_with_filter(html)

        assert r"\texorpdfstring{" in latex
        assert r"\highLight[tag-jurisdiction-light]{" in latex


class TestNoHlAttribute:
    """AC2.6: Spans without hl attribute pass through unchanged."""

    def test_no_highlight_wrapping_without_hl(self) -> None:
        html = '<p><span class="other">plain text</span></p>'
        latex = _run_pandoc_with_filter(html)

        assert r"\highLight" not in latex
        assert r"\underLine" not in latex

    def test_content_preserved_without_hl(self) -> None:
        html = '<p><span class="other">plain text</span></p>'
        latex = _run_pandoc_with_filter(html)

        assert "plain text" in latex


class TestEdgeCases:
    """Edge cases: empty colors, empty hl."""

    def test_empty_hl_no_crash(self) -> None:
        """Empty hl attribute should not crash and should not produce highlights."""
        html = '<p><span data-hl="">empty hl</span></p>'
        latex = _run_pandoc_with_filter(html)

        assert r"\highLight" not in latex
        assert r"\underLine" not in latex
        assert "empty hl" in latex

    def test_empty_colors_no_crash(self) -> None:
        """hl present but empty colors should not crash."""
        html = '<p><span data-hl="0" data-colors="">empty colors</span></p>'
        latex = _run_pandoc_with_filter(html)

        assert r"\highLight" not in latex
        assert r"\underLine" not in latex
        assert "empty colors" in latex
