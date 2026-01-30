"""Tests for CSS-to-LaTeX fidelity via Pandoc Lua filters.

These tests validate that the Lua filters in src/promptgrimoire/export/filters/
correctly translate CSS properties to their LaTeX equivalents.

See: https://github.com/MQFacultyOfArts/PromptGrimoireTool/issues/76
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from promptgrimoire.export.latex import convert_html_to_latex

# Filter paths
FILTERS_DIR = (
    Path(__file__).parents[3] / "src" / "promptgrimoire" / "export" / "filters"
)
LIBREOFFICE_FILTER = FILTERS_DIR / "libreoffice.lua"
LEGAL_FILTER = FILTERS_DIR / "legal.lua"


def _has_pandoc() -> bool:
    return shutil.which("pandoc") is not None


requires_pandoc = pytest.mark.skipif(not _has_pandoc(), reason="Pandoc not installed")


class TestTableColumnWidths:
    """Table column widths from HTML width attributes → proportional LaTeX widths."""

    @requires_pandoc
    def test_table_with_width_attributes(self) -> None:
        """Cells with width="N" become proportional p{X\\textwidth} columns."""
        html = """
        <table>
            <tr>
                <td width="100">Column A</td>
                <td width="200">Column B</td>
            </tr>
        </table>
        """
        result = convert_html_to_latex(html, filter_path=LIBREOFFICE_FILTER)

        # Should use longtable with proportional widths
        assert "\\begin{longtable}" in result
        # 100/(100+200) * 0.97 ≈ 0.32, 200/(100+200) * 0.97 ≈ 0.65
        assert "\\textwidth" in result
        # Should have two p{} column specs
        assert result.count("p{") == 2

    @requires_pandoc
    def test_table_without_widths_unchanged(self) -> None:
        """Tables without width attributes are handled by Pandoc defaults."""
        html = """
        <table>
            <tr>
                <td>Column A</td>
                <td>Column B</td>
            </tr>
        </table>
        """
        result = convert_html_to_latex(html, filter_path=LIBREOFFICE_FILTER)

        # Without widths, filter doesn't intervene - Pandoc handles it
        # Just verify it produces something reasonable
        assert "Column A" in result
        assert "Column B" in result


class TestMarginLeft:
    """margin-left CSS property → adjustwidth environment."""

    @requires_pandoc
    def test_div_with_margin_left(self) -> None:
        """Div with margin-left style becomes adjustwidth environment."""
        html = """
        <div style="margin-left: 0.5in">
            <p>Indented paragraph</p>
        </div>
        """
        result = convert_html_to_latex(html, filter_path=LIBREOFFICE_FILTER)

        assert "\\begin{adjustwidth}{0.5in}{}" in result
        assert "\\end{adjustwidth}" in result
        assert "Indented paragraph" in result

    @requires_pandoc
    def test_margin_left_various_values(self) -> None:
        """Various margin-left values are preserved."""
        html = """
        <div style="margin-left: 1.25in">
            <p>More indented</p>
        </div>
        """
        result = convert_html_to_latex(html, filter_path=LIBREOFFICE_FILTER)

        assert "\\begin{adjustwidth}{1.25in}{}" in result

    @requires_pandoc
    def test_margin_left_centimeters(self) -> None:
        """LibreOffice outputs cm units which must be handled."""
        html = """
        <div style="margin-left: 2.38cm">
            <p>Indented quote from judgment</p>
        </div>
        """
        result = convert_html_to_latex(html, filter_path=LIBREOFFICE_FILTER)

        assert "\\begin{adjustwidth}{2.38cm}{}" in result

    @requires_pandoc
    def test_paragraph_with_margin_left_wrapped(self) -> None:
        """Paragraphs with margin-left are wrapped in divs for Pandoc processing.

        The normalise_styled_paragraphs preprocessor wraps styled <p> tags
        so the Lua filter can process the style attribute.
        """
        html = """
        <p style="margin-left: 0.75in">Styled paragraph</p>
        """
        result = convert_html_to_latex(html, filter_path=LIBREOFFICE_FILTER)

        # Preprocessor wraps in div, filter creates adjustwidth
        assert "\\begin{adjustwidth}{0.75in}{}" in result
        assert "Styled paragraph" in result


class TestOrderedListStart:
    """Ordered list start attribute → \\setcounter{enumi}{N-1}."""

    @requires_pandoc
    def test_ol_with_start_attribute(self) -> None:
        """Ordered list with start="N" injects setcounter before list."""
        html = """
        <ol start="5">
            <li>Item five</li>
            <li>Item six</li>
        </ol>
        """
        result = convert_html_to_latex(html, filter_path=LEGAL_FILTER)

        # start=5 means first displayed number is 5, so counter = 4
        assert "\\setcounter{enumi}{4}" in result
        assert "Item five" in result

    @requires_pandoc
    def test_ol_start_one_no_setcounter(self) -> None:
        """Ordered list with start=1 (or no start) doesn't need setcounter."""
        html = """
        <ol start="1">
            <li>Item one</li>
        </ol>
        """
        result = convert_html_to_latex(html, filter_path=LEGAL_FILTER)

        # start=1 is default, no setcounter needed
        assert "\\setcounter" not in result
        assert "Item one" in result

    @requires_pandoc
    def test_ol_without_start(self) -> None:
        """Ordered list without start attribute works normally."""
        html = """
        <ol>
            <li>First</li>
            <li>Second</li>
        </ol>
        """
        result = convert_html_to_latex(html, filter_path=LEGAL_FILTER)

        assert "\\setcounter" not in result
        assert "First" in result
