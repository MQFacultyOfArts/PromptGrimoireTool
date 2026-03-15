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

_LIBREOFFICE_FILTER_PATH = (
    Path(__file__).parents[2]
    / "src"
    / "promptgrimoire"
    / "export"
    / "filters"
    / "libreoffice.lua"
)


def _run_pandoc_with_filter(
    html: str, *, filter_paths: list[Path] | None = None
) -> str:
    """Run Pandoc with Lua filter(s) on an HTML input string.

    Writes *html* to a temporary file, invokes Pandoc as a subprocess,
    and returns the LaTeX output.

    Args:
        html: HTML content to convert.
        filter_paths: Lua filter paths. Defaults to [_FILTER_PATH] if not given.

    Returns:
        LaTeX string produced by Pandoc with the filter(s) applied.

    Raises:
        subprocess.CalledProcessError: If Pandoc exits with non-zero status.
    """
    if filter_paths is None:
        filter_paths = [_FILTER_PATH]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=True) as tmp:
        tmp.write(html)
        tmp.flush()
        cmd = [
            "pandoc",
            "-f",
            "html+native_divs",
            "-t",
            "latex",
            "--no-highlight",
        ]
        for fp in filter_paths:
            cmd.extend(["--lua-filter", str(fp)])
        cmd.append(tmp.name)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    return result.stdout


def _run_pandoc_with_both_filters(html: str) -> str:
    """Run Pandoc with highlight.lua then libreoffice.lua (production order)."""
    return _run_pandoc_with_filter(
        html, filter_paths=[_FILTER_PATH, _LIBREOFFICE_FILTER_PATH]
    )


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


class TestAnnotInTable:
    """annot-in-tables-cjk-crash-351: annotation splitting inside table cells.

    The Table callback in highlight.lua replaces \\annot{colour}{content}
    with \\annotref{colour} inline and defers \\annotendnote after the table.
    """

    def test_table_no_annotations_unchanged(self) -> None:
        """AC1.4: Table with no annotations passes through unchanged."""
        html = "<table><tr><td>plain cell</td><td>another cell</td></tr></table>"
        latex = _run_pandoc_with_both_filters(html)

        assert r"\annotref" not in latex
        assert r"\annotendnote" not in latex
        assert "plain cell" in latex

    def test_annotref_inside_longtable(self) -> None:
        """AC2.1: Annotated table cell gets \\annotref inside the table."""
        html = (
            "<table>"
            "<tr>"
            '<td><span data-hl="0" data-colors="tag-issue-light"'
            r' data-annots="\annot{tag-issue-dark}{Alice: Test comment}">'
            "annotated text</span></td>"
            "<td>plain text</td>"
            "</tr>"
            "</table>"
        )
        latex = _run_pandoc_with_both_filters(html)

        # Find longtable boundaries
        lt_start = latex.find(r"\begin{longtable}")
        lt_end = latex.find(r"\end{longtable}")
        # Fall back to checking for @{} pattern if \begin{longtable} not found verbatim
        if lt_start == -1:
            lt_start = latex.find("longtable")
            lt_end = latex.find(r"\endlastfoot") or latex.find(r"\end{longtable")

        assert lt_start != -1, f"Expected longtable in output, got:\n{latex}"

        # annotref should appear inside the table
        annotref_pos = latex.find(r"\annotref{")
        assert annotref_pos != -1, f"Expected \\annotref in output, got:\n{latex}"
        assert lt_start < annotref_pos < lt_end, (
            "\\annotref should appear inside longtable"
        )

    def test_annotendnote_after_longtable(self) -> None:
        """AC2.2: Annotation content appears after the table as \\annotendnote."""
        html = (
            "<table>"
            "<tr>"
            '<td><span data-hl="0" data-colors="tag-issue-light"'
            r' data-annots="\annot{tag-issue-dark}{Alice: Test comment}">'
            "annotated text</span></td>"
            "<td>plain text</td>"
            "</tr>"
            "</table>"
        )
        latex = _run_pandoc_with_both_filters(html)

        lt_end = latex.find(r"\end{longtable}")
        if lt_end == -1:
            # Try to find the end of the table environment
            lt_end = latex.rfind(r"\endlastfoot")
        assert lt_end != -1, f"Expected longtable end in output, got:\n{latex}"

        endnote_pos = latex.find(r"\annotendnote{")
        assert endnote_pos != -1, f"Expected \\annotendnote in output, got:\n{latex}"
        assert endnote_pos > lt_end, "\\annotendnote should appear after longtable"

        # Verify the endnote content
        assert "Alice: Test comment" in latex

    def test_sequential_numbering_across_table(self) -> None:
        """AC2.3: Annotation numbering is sequential across table and non-table.

        Structure: annotation before table (1), annotation in table (2),
        annotation after table (3). All should use sequential \\stepcounter.
        """
        annot_before = r"\annot{tag-issue-dark}{Before: First comment}"
        annot_in_table = r"\annot{tag-evidence-dark}{InTable: Second comment}"
        annot_after = r"\annot{tag-ratio-dark}{After: Third comment}"
        html = (
            "<p>"
            '<span data-hl="0" data-colors="tag-issue-light"'
            f' data-annots="{annot_before}">before table</span>'
            "</p>"
            "<table><tr>"
            '<td><span data-hl="0" data-colors="tag-evidence-light"'
            f' data-annots="{annot_in_table}">in table</span></td>'
            "</tr></table>"
            "<p>"
            '<span data-hl="0" data-colors="tag-ratio-light"'
            f' data-annots="{annot_after}">after table</span>'
            "</p>"
        )
        latex = _run_pandoc_with_both_filters(html)

        # The before-table annotation should use \annot (unchanged)
        # The in-table annotation should be split to \annotref + \annotendnote
        # The after-table annotation should use \annot (unchanged)
        assert r"\annot{tag-issue-dark}" in latex, "Before-table annot preserved"
        assert r"\annotref{tag-evidence-dark}" in latex, "In-table annot split"
        assert r"\annotendnote{tag-evidence-dark}" in latex, "In-table endnote emitted"
        assert r"\annot{tag-ratio-dark}" in latex, "After-table annot preserved"

    def test_multiple_annotations_in_table(self) -> None:
        """AC2.4: Multiple annotations in the same table each get their own ref."""
        annot1 = r"\annot{tag-issue-dark}{Alice: First}"
        annot2 = r"\annot{tag-evidence-dark}{Bob: Second}"
        html = (
            "<table><tr>"
            '<td><span data-hl="0" data-colors="tag-issue-light"'
            f' data-annots="{annot1}">cell one</span></td>'
            '<td><span data-hl="0" data-colors="tag-evidence-light"'
            f' data-annots="{annot2}">cell two</span></td>'
            "</tr></table>"
        )
        latex = _run_pandoc_with_both_filters(html)

        # Both annotations should be split
        assert latex.count(r"\annotref{") == 2, f"Expected 2 \\annotref, got:\n{latex}"
        assert latex.count(r"\annotendnote{") == 2, (
            f"Expected 2 \\annotendnote, got:\n{latex}"
        )
        assert r"\annotref{tag-issue-dark}" in latex
        assert r"\annotref{tag-evidence-dark}" in latex

    def test_no_annot_inside_longtable_regression(self) -> None:
        """AC4.1: No \\annot{ inside longtable (only \\annotref allowed)."""
        annot = r"\annot{tag-issue-dark}{Alice: Test}"
        html = (
            "<table><tr>"
            '<td><span data-hl="0" data-colors="tag-issue-light"'
            f' data-annots="{annot}">text</span></td>'
            "</tr></table>"
        )
        latex = _run_pandoc_with_both_filters(html)

        # Find table boundaries
        lt_start = latex.find("longtable")
        lt_end = latex.rfind("longtable")
        assert lt_start != -1, f"Expected longtable in output, got:\n{latex}"

        # Extract content between table boundaries
        table_content = latex[lt_start:lt_end]

        # Must not contain \annot{ (only \annotref{ is allowed)
        # Use a careful check: \annot{ but not \annotref{ or \annotendnote{
        import re

        bare_annot = re.findall(r"\\annot\{(?!ref|endnote)", table_content)
        assert bare_annot == [], (
            f"Found bare \\annot inside longtable: {bare_annot}\n"
            f"Table content:\n{table_content}"
        )
