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

    @requires_pandoc
    def test_margin_left_em_units(self) -> None:
        """margin-left with em units converts to LaTeX em."""
        html = '<div style="margin-left: 2em"><p>Indented text</p></div>'
        latex = convert_html_to_latex(html, filter_path=LIBREOFFICE_FILTER)
        assert r"\begin{adjustwidth}{2em}{}" in latex
        assert "Indented text" in latex

    @requires_pandoc
    def test_margin_left_rem_units(self) -> None:
        """margin-left with rem units converts to LaTeX em (1:1 mapping)."""
        html = '<div style="margin-left: 1.5rem"><p>Indented text</p></div>'
        latex = convert_html_to_latex(html, filter_path=LIBREOFFICE_FILTER)
        # rem maps to em for LaTeX (no root font context)
        assert r"\begin{adjustwidth}{1.5em}{}" in latex
        assert "Indented text" in latex

    @requires_pandoc
    def test_margin_left_px_units(self) -> None:
        """margin-left with px units converts to pt (1px = 0.75pt)."""
        html = '<div style="margin-left: 40px"><p>Indented text</p></div>'
        latex = convert_html_to_latex(html, filter_path=LIBREOFFICE_FILTER)
        # 40px * 0.75 = 30pt (Lua outputs 30.0 for float)
        assert r"\begin{adjustwidth}{30.0pt}{}" in latex
        assert "Indented text" in latex


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


class TestPlatformDetection:
    """Tests for conversation platform detection."""

    def test_detect_claude_platform(self) -> None:
        """Detect Claude from font-user-message class."""
        html = '<div class="font-user-message">Hello</div>'
        from promptgrimoire.export.speaker_preprocessor import Platform, detect_platform

        assert detect_platform(html) == Platform.CLAUDE

    def test_detect_gemini_platform(self) -> None:
        """Detect Gemini from ng-version attribute."""
        html = (
            '<app-root ng-version="0.0.0">'
            '<div class="user-query-container">Hi</div>'
            "</app-root>"
        )
        from promptgrimoire.export.speaker_preprocessor import Platform, detect_platform

        assert detect_platform(html) == Platform.GEMINI

    def test_detect_openai_platform(self) -> None:
        """Detect OpenAI from agent-turn class."""
        html = '<div class="agent-turn"><p>Response</p></div>'
        from promptgrimoire.export.speaker_preprocessor import Platform, detect_platform

        assert detect_platform(html) == Platform.OPENAI

    def test_detect_scienceos_platform(self) -> None:
        """Detect ScienceOS from tabler-icon classes."""
        html = '<div><i class="tabler-icon-robot"></i>Bot response</div>'
        from promptgrimoire.export.speaker_preprocessor import Platform, detect_platform

        assert detect_platform(html) == Platform.SCIENCEOS

    def test_detect_austlii_platform(self) -> None:
        """Detect AustLII from the-document class."""
        html = '<div class="the-document"><p>Legal text</p></div>'
        from promptgrimoire.export.speaker_preprocessor import Platform, detect_platform

        assert detect_platform(html) == Platform.AUSTLII

    def test_detect_unknown_platform(self) -> None:
        """Unknown platform for unrecognized HTML."""
        html = "<html><body><p>Generic content</p></body></html>"
        from promptgrimoire.export.speaker_preprocessor import Platform, detect_platform

        assert detect_platform(html) == Platform.UNKNOWN

    def test_inject_claude_labels(self) -> None:
        """Claude conversations get User/Assistant labels."""
        html = """
        <div>
            <div class="font-user-message">Hello Claude</div>
            <div class="font-claude-response">Hello human</div>
        </div>
        """
        from promptgrimoire.export.speaker_preprocessor import preprocess_speakers

        result = preprocess_speakers(html)
        assert "<strong>User:</strong>" in result
        assert "<strong>Assistant:</strong>" in result
        assert "Hello Claude" in result
        assert "Hello human" in result

    def test_inject_gemini_labels(self) -> None:
        """Gemini conversations get User/Assistant labels."""
        html = """
        <div>
            <div class="user-query-container">What is Python?</div>
            <div class="model-response-container">Python is a language.</div>
        </div>
        """
        from promptgrimoire.export.speaker_preprocessor import preprocess_speakers

        result = preprocess_speakers(html)
        assert "<strong>User:</strong>" in result
        assert "<strong>Assistant:</strong>" in result
        assert "What is Python?" in result
        assert "Python is a language." in result

    def test_inject_openai_labels(self) -> None:
        """OpenAI conversations get User/Assistant labels."""
        html = """
        <div>
            <div class="items-end">What is 2+2?</div>
            <div class="agent-turn">The answer is 4.</div>
        </div>
        """
        from promptgrimoire.export.speaker_preprocessor import preprocess_speakers

        result = preprocess_speakers(html)
        assert "<strong>User:</strong>" in result
        assert "<strong>Assistant:</strong>" in result

    def test_inject_scienceos_labels(self) -> None:
        """ScienceOS conversations get User/Assistant labels."""
        html = """
        <div>
            <div><i class="tabler-icon-medal"></i>User question here</div>
            <div><i class="tabler-icon-robot"></i>Bot response here</div>
        </div>
        """
        from promptgrimoire.export.speaker_preprocessor import preprocess_speakers

        result = preprocess_speakers(html)
        assert "<strong>User:</strong>" in result
        assert "<strong>Assistant:</strong>" in result

    def test_austlii_no_injection(self) -> None:
        """AustLII legal documents don't get speaker labels."""
        html = '<div class="the-document"><p>Legal text here</p></div>'
        from promptgrimoire.export.speaker_preprocessor import preprocess_speakers

        result = preprocess_speakers(html)
        assert "<strong>User:</strong>" not in result
        assert "<strong>Assistant:</strong>" not in result
        assert "Legal text here" in result
