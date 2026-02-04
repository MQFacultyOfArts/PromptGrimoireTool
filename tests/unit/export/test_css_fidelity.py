"""Tests for CSS-to-LaTeX fidelity via Pandoc Lua filters.

These tests validate that the Lua filters in src/promptgrimoire/export/filters/
correctly translate CSS properties to their LaTeX equivalents.

See: https://github.com/MQFacultyOfArts/PromptGrimoireTool/issues/76
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from promptgrimoire.export.latex import convert_html_to_latex
from tests.conftest import load_conversation_fixture

# Filter paths
FILTERS_DIR = (
    Path(__file__).parents[3] / "src" / "promptgrimoire" / "export" / "filters"
)
LIBREOFFICE_FILTER = FILTERS_DIR / "libreoffice.lua"
LEGAL_FILTER = FILTERS_DIR / "legal.lua"


def _has_pandoc() -> bool:
    return shutil.which("pandoc") is not None


requires_pandoc = pytest.mark.skipif(not _has_pandoc(), reason="Pandoc not installed")


class TestAsyncErrorHandling:
    """Verify subprocess errors propagate correctly from async convert_html_to_latex."""

    @pytest.mark.asyncio
    async def test_pandoc_failure_raises_called_process_error(self) -> None:
        """When Pandoc fails (non-zero exit), CalledProcessError raised with stderr."""
        # Create a mock process that simulates Pandoc failure
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(
            return_value=(b"", b"pandoc: Error parsing HTML input")
        )

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with pytest.raises(subprocess.CalledProcessError) as exc_info:
                await convert_html_to_latex("<html><body>test</body></html>")

            # Verify stderr is captured in the exception
            assert "pandoc: Error parsing HTML input" in str(exc_info.value.output)
            assert exc_info.value.returncode == 1


class TestTableColumnWidths:
    """Table column widths from HTML width attributes → proportional LaTeX widths."""

    @requires_pandoc
    @pytest.mark.asyncio
    async def test_table_with_width_attributes(self) -> None:
        """Cells with width="N" become proportional p{X\\textwidth} columns."""
        html = """
        <table>
            <tr>
                <td width="100">Column A</td>
                <td width="200">Column B</td>
            </tr>
        </table>
        """
        result = await convert_html_to_latex(html, filter_path=LIBREOFFICE_FILTER)

        # Should use longtable with proportional widths
        assert "\\begin{longtable}" in result
        # 100/(100+200) * 0.97 ≈ 0.32, 200/(100+200) * 0.97 ≈ 0.65
        assert "\\textwidth" in result
        # Should have two p{} column specs
        assert result.count("p{") == 2

    @requires_pandoc
    @pytest.mark.asyncio
    async def test_table_without_widths_unchanged(self) -> None:
        """Tables without width attributes are handled by Pandoc defaults."""
        html = """
        <table>
            <tr>
                <td>Column A</td>
                <td>Column B</td>
            </tr>
        </table>
        """
        result = await convert_html_to_latex(html, filter_path=LIBREOFFICE_FILTER)

        # Without widths, filter doesn't intervene - Pandoc handles it
        # Just verify it produces something reasonable
        assert "Column A" in result
        assert "Column B" in result


class TestMarginLeft:
    """margin-left CSS property → adjustwidth environment."""

    @requires_pandoc
    @pytest.mark.asyncio
    async def test_div_with_margin_left(self) -> None:
        """Div with margin-left style becomes adjustwidth environment."""
        html = """
        <div style="margin-left: 0.5in">
            <p>Indented paragraph</p>
        </div>
        """
        result = await convert_html_to_latex(html, filter_path=LIBREOFFICE_FILTER)

        assert "\\begin{adjustwidth}{0.5in}{}" in result
        assert "\\end{adjustwidth}" in result
        assert "Indented paragraph" in result

    @requires_pandoc
    @pytest.mark.asyncio
    async def test_margin_left_various_values(self) -> None:
        """Various margin-left values are preserved."""
        html = """
        <div style="margin-left: 1.25in">
            <p>More indented</p>
        </div>
        """
        result = await convert_html_to_latex(html, filter_path=LIBREOFFICE_FILTER)

        assert "\\begin{adjustwidth}{1.25in}{}" in result

    @requires_pandoc
    @pytest.mark.asyncio
    async def test_margin_left_centimeters(self) -> None:
        """LibreOffice outputs cm units which must be handled."""
        html = """
        <div style="margin-left: 2.38cm">
            <p>Indented quote from judgment</p>
        </div>
        """
        result = await convert_html_to_latex(html, filter_path=LIBREOFFICE_FILTER)

        assert "\\begin{adjustwidth}{2.38cm}{}" in result

    @requires_pandoc
    @pytest.mark.asyncio
    async def test_paragraph_with_margin_left_wrapped(self) -> None:
        """Paragraphs with margin-left are wrapped in divs for Pandoc processing.

        The normalise_styled_paragraphs preprocessor wraps styled <p> tags
        so the Lua filter can process the style attribute.
        """
        html = """
        <p style="margin-left: 0.75in">Styled paragraph</p>
        """
        result = await convert_html_to_latex(html, filter_path=LIBREOFFICE_FILTER)

        # Preprocessor wraps in div, filter creates adjustwidth
        assert "\\begin{adjustwidth}{0.75in}{}" in result
        assert "Styled paragraph" in result


class TestOrderedListStart:
    """Ordered list start attribute → \\setcounter{enumi}{N-1}."""

    @requires_pandoc
    @pytest.mark.asyncio
    async def test_ol_with_start_attribute(self) -> None:
        """Ordered list with start="N" injects setcounter before list."""
        html = """
        <ol start="5">
            <li>Item five</li>
            <li>Item six</li>
        </ol>
        """
        result = await convert_html_to_latex(html, filter_path=LEGAL_FILTER)

        # start=5 means first displayed number is 5, so counter = 4
        assert "\\setcounter{enumi}{4}" in result
        assert "Item five" in result

    @requires_pandoc
    @pytest.mark.asyncio
    async def test_ol_start_one_no_setcounter(self) -> None:
        """Ordered list with start=1 (or no start) doesn't need setcounter."""
        html = """
        <ol start="1">
            <li>Item one</li>
        </ol>
        """
        result = await convert_html_to_latex(html, filter_path=LEGAL_FILTER)

        # start=1 is default, no setcounter needed
        assert "\\setcounter" not in result
        assert "Item one" in result

    @requires_pandoc
    @pytest.mark.asyncio
    async def test_ol_without_start(self) -> None:
        """Ordered list without start attribute works normally."""
        html = """
        <ol>
            <li>First</li>
            <li>Second</li>
        </ol>
        """
        result = await convert_html_to_latex(html, filter_path=LEGAL_FILTER)

        assert "\\setcounter" not in result
        assert "First" in result


class TestListValueNormalization:
    """Convert <li value="N"> to <ol start="N"> for Pandoc compatibility."""

    def test_li_value_converted_to_ol_start(self) -> None:
        """First li value becomes ol start attribute."""
        from promptgrimoire.export.list_normalizer import normalize_list_values

        html = '<ol><li value="5">Para 5</li><li value="6">Para 6</li></ol>'
        result = normalize_list_values(html)

        assert 'start="5"' in result
        assert "Para 5" in result

    def test_li_value_one_no_start(self) -> None:
        """li value=1 doesn't need start (it's the default)."""
        from promptgrimoire.export.list_normalizer import normalize_list_values

        html = '<ol><li value="1">Para 1</li></ol>'
        result = normalize_list_values(html)

        # start=1 is default, shouldn't be added
        assert 'start="1"' not in result
        assert "Para 1" in result

    def test_multiple_ols_each_get_start(self) -> None:
        """Multiple OLs each get start from their first li."""
        from promptgrimoire.export.list_normalizer import normalize_list_values

        html = """
        <ol><li value="1">Para 1</li><li value="2">Para 2</li></ol>
        <ol><li value="3">Para 3</li></ol>
        <ol><li value="4">Para 4</li><li value="5">Para 5</li></ol>
        """
        result = normalize_list_values(html)

        # First ol: start=1 not needed
        # Second ol: start=3
        # Third ol: start=4
        assert 'start="3"' in result
        assert 'start="4"' in result

    def test_li_without_value_unchanged(self) -> None:
        """OL without li value attributes is unchanged."""
        from promptgrimoire.export.list_normalizer import normalize_list_values

        html = "<ol><li>Item</li></ol>"
        result = normalize_list_values(html)

        assert "start=" not in result
        assert "Item" in result

    @requires_pandoc
    @pytest.mark.asyncio
    async def test_normalized_list_produces_correct_latex(self) -> None:
        """Full pipeline: li value → ol start → setcounter."""
        from promptgrimoire.export.list_normalizer import normalize_list_values

        html = '<ol><li value="5">Para 5</li></ol>'
        normalized = normalize_list_values(html)
        result = await convert_html_to_latex(normalized, filter_path=LEGAL_FILTER)

        assert "\\setcounter{enumi}{4}" in result
        assert "Para 5" in result


class TestUnitConversion:
    """CSS unit conversion: em, rem, px → LaTeX equivalents."""

    @requires_pandoc
    @pytest.mark.asyncio
    async def test_margin_left_em_units(self) -> None:
        """margin-left with em units passes through to LaTeX."""
        html = """
        <div style="margin-left: 2em">
            <p>Em-indented paragraph</p>
        </div>
        """
        result = await convert_html_to_latex(html, filter_path=LIBREOFFICE_FILTER)

        assert "\\begin{adjustwidth}{2em}{}" in result
        assert "Em-indented paragraph" in result

    @requires_pandoc
    @pytest.mark.asyncio
    async def test_margin_left_rem_units(self) -> None:
        """margin-left with rem units converts to em (1:1 ratio)."""
        html = """
        <div style="margin-left: 1.5rem">
            <p>Rem-indented paragraph</p>
        </div>
        """
        result = await convert_html_to_latex(html, filter_path=LIBREOFFICE_FILTER)

        # rem converts to em at 1:1 ratio
        assert "\\begin{adjustwidth}{1.5em}{}" in result
        assert "Rem-indented paragraph" in result

    @requires_pandoc
    @pytest.mark.asyncio
    async def test_margin_left_px_units(self) -> None:
        """margin-left with px units converts to pt (x0.75)."""
        html = """
        <div style="margin-left: 40px">
            <p>Pixel-indented paragraph</p>
        </div>
        """
        result = await convert_html_to_latex(html, filter_path=LIBREOFFICE_FILTER)

        # 40px * 0.75 = 30pt
        assert "\\begin{adjustwidth}{30pt}{}" in result
        assert "Pixel-indented paragraph" in result

    @requires_pandoc
    @pytest.mark.asyncio
    async def test_margin_left_px_decimal_result(self) -> None:
        """px conversion produces clean decimal when needed."""
        html = """
        <div style="margin-left: 20px">
            <p>Small indent</p>
        </div>
        """
        result = await convert_html_to_latex(html, filter_path=LIBREOFFICE_FILTER)

        # 20px * 0.75 = 15pt
        assert "\\begin{adjustwidth}{15pt}{}" in result


class TestSpeakerDetection:
    """Platform detection and speaker label injection."""

    def test_detect_claude_platform(self) -> None:
        """Claude platform detected by font-user-message class."""
        from promptgrimoire.export.platforms import get_handler

        html = '<div class="font-user-message">Hello</div>'
        handler = get_handler(html)
        assert handler is not None
        assert handler.name == "claude"

    def test_detect_openai_platform(self) -> None:
        """OpenAI platform detected by agent-turn class."""
        from promptgrimoire.export.platforms import get_handler

        html = '<div class="agent-turn">Response</div>'
        handler = get_handler(html)
        assert handler is not None
        assert handler.name == "openai"

    def test_detect_gemini_platform(self) -> None:
        """Gemini platform detected by user-query element."""
        from promptgrimoire.export.platforms import get_handler

        html = "<user-query>What is CRDT?</user-query>"
        handler = get_handler(html)
        assert handler is not None
        assert handler.name == "gemini"

    def test_detect_scienceos_platform(self) -> None:
        """ScienceOS platform detected by tabler-icon-robot-face class."""
        from promptgrimoire.export.platforms import get_handler

        html = '<i class="tabler-icon tabler-icon-robot-face"></i>'
        handler = get_handler(html)
        assert handler is not None
        assert handler.name == "scienceos"

    def test_detect_unknown_platform(self) -> None:
        """Unknown platform when no patterns match."""
        from promptgrimoire.export.platforms import get_handler

        html = "<p>Just some text</p>"
        assert get_handler(html) is None

    def test_inject_labels_claude(self) -> None:
        """Claude turns get User:/Assistant: labels injected."""
        from promptgrimoire.export.platforms import preprocess_for_export

        # Use realistic Claude HTML patterns
        html = """
        <div class="font-user-message" data-testid="user-message">Hello</div>
        <div class="font-claude-response relative leading-[1.65rem]">Hi!</div>
        """
        result = preprocess_for_export(html)

        # Check data attributes are injected (Lua filter converts to LaTeX labels)
        assert 'data-speaker="user"' in result
        assert 'data-speaker="assistant"' in result
        assert "Hello" in result
        assert "Hi!" in result

    def test_inject_labels_gemini(self) -> None:
        """Gemini turns get User:/Assistant: labels injected."""
        from promptgrimoire.export.platforms import preprocess_for_export

        html = """
        <user-query>What is CRDT?</user-query>
        <model-response>CRDT stands for...</model-response>
        """
        result = preprocess_for_export(html)

        # Check data attributes are injected (Lua filter converts to LaTeX labels)
        assert 'data-speaker="user"' in result
        assert 'data-speaker="assistant"' in result


class TestSpeakerDetectionWithFixtures:
    """Test speaker detection against real fixture files."""

    def _load_fixture(self, name: str) -> str:
        return load_conversation_fixture(name)

    def test_detect_claude_fixture(self) -> None:
        """Claude fixture detected as Claude platform."""
        from promptgrimoire.export.platforms import get_handler

        html = self._load_fixture("claude_cooking.html")
        handler = get_handler(html)
        assert handler is not None
        assert handler.name == "claude"

    def test_detect_openai_fixture(self) -> None:
        """OpenAI fixture detected as OpenAI platform."""
        from promptgrimoire.export.platforms import get_handler

        html = self._load_fixture("openai_biblatex.html")
        handler = get_handler(html)
        assert handler is not None
        assert handler.name == "openai"

    def test_detect_gemini_fixture(self) -> None:
        """Gemini fixture detected as Gemini platform."""
        from promptgrimoire.export.platforms import get_handler

        html = self._load_fixture("google_gemini_debug.html")
        handler = get_handler(html)
        assert handler is not None
        assert handler.name == "gemini"

    def test_detect_aistudio_fixture(self) -> None:
        """AI Studio fixture detected as AI Studio platform."""
        from promptgrimoire.export.platforms import get_handler

        html = self._load_fixture("google_aistudio_ux_discussion.html")
        handler = get_handler(html)
        assert handler is not None
        assert handler.name == "aistudio"

    def test_inject_labels_claude_fixture(self) -> None:
        """Claude fixture gets labels injected."""
        from promptgrimoire.export.platforms import preprocess_for_export

        html = self._load_fixture("claude_cooking.html")
        result = preprocess_for_export(html)

        # Check data attributes are injected (Lua filter converts to LaTeX labels)
        assert 'data-speaker="user"' in result
        assert 'data-speaker="assistant"' in result

    def test_inject_labels_gemini_fixture(self) -> None:
        """Gemini fixture gets labels injected."""
        from promptgrimoire.export.platforms import preprocess_for_export

        html = self._load_fixture("google_gemini_debug.html")
        result = preprocess_for_export(html)

        # Check data attributes are injected (Lua filter converts to LaTeX labels)
        assert 'data-speaker="user"' in result
        assert 'data-speaker="assistant"' in result


# Note: TestUIChromeRemoval and TestChromeRemovalInFullPipeline classes removed.
# Chrome removal functionality is now tested in:
# - tests/unit/export/platforms/test_base.py (common chrome removal)
# - tests/unit/export/platforms/test_pipeline.py (integration tests)
# - Individual platform handler tests
