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
    def test_normalized_list_produces_correct_latex(self) -> None:
        """Full pipeline: li value → ol start → setcounter."""
        from promptgrimoire.export.list_normalizer import normalize_list_values

        html = '<ol><li value="5">Para 5</li></ol>'
        normalized = normalize_list_values(html)
        result = convert_html_to_latex(normalized, filter_path=LEGAL_FILTER)

        assert "\\setcounter{enumi}{4}" in result
        assert "Para 5" in result


class TestUnitConversion:
    """CSS unit conversion: em, rem, px → LaTeX equivalents."""

    @requires_pandoc
    def test_margin_left_em_units(self) -> None:
        """margin-left with em units passes through to LaTeX."""
        html = """
        <div style="margin-left: 2em">
            <p>Em-indented paragraph</p>
        </div>
        """
        result = convert_html_to_latex(html, filter_path=LIBREOFFICE_FILTER)

        assert "\\begin{adjustwidth}{2em}{}" in result
        assert "Em-indented paragraph" in result

    @requires_pandoc
    def test_margin_left_rem_units(self) -> None:
        """margin-left with rem units converts to em (1:1 ratio)."""
        html = """
        <div style="margin-left: 1.5rem">
            <p>Rem-indented paragraph</p>
        </div>
        """
        result = convert_html_to_latex(html, filter_path=LIBREOFFICE_FILTER)

        # rem converts to em at 1:1 ratio
        assert "\\begin{adjustwidth}{1.5em}{}" in result
        assert "Rem-indented paragraph" in result

    @requires_pandoc
    def test_margin_left_px_units(self) -> None:
        """margin-left with px units converts to pt (x0.75)."""
        html = """
        <div style="margin-left: 40px">
            <p>Pixel-indented paragraph</p>
        </div>
        """
        result = convert_html_to_latex(html, filter_path=LIBREOFFICE_FILTER)

        # 40px * 0.75 = 30pt
        assert "\\begin{adjustwidth}{30pt}{}" in result
        assert "Pixel-indented paragraph" in result

    @requires_pandoc
    def test_margin_left_px_decimal_result(self) -> None:
        """px conversion produces clean decimal when needed."""
        html = """
        <div style="margin-left: 20px">
            <p>Small indent</p>
        </div>
        """
        result = convert_html_to_latex(html, filter_path=LIBREOFFICE_FILTER)

        # 20px * 0.75 = 15pt
        assert "\\begin{adjustwidth}{15pt}{}" in result


class TestSpeakerDetection:
    """Platform detection and speaker label injection."""

    def test_detect_claude_platform(self) -> None:
        """Claude platform detected by font-user-message class."""
        from promptgrimoire.export.speaker_preprocessor import detect_platform

        html = '<div class="font-user-message">Hello</div>'
        assert detect_platform(html) == "claude"

    def test_detect_openai_platform(self) -> None:
        """OpenAI platform detected by agent-turn class."""
        from promptgrimoire.export.speaker_preprocessor import detect_platform

        html = '<div class="agent-turn">Response</div>'
        assert detect_platform(html) == "openai"

    def test_detect_gemini_platform(self) -> None:
        """Gemini platform detected by user-query element."""
        from promptgrimoire.export.speaker_preprocessor import detect_platform

        html = "<user-query>What is CRDT?</user-query>"
        assert detect_platform(html) == "gemini"

    def test_detect_scienceos_platform(self) -> None:
        """ScienceOS platform detected by tabler-icon-robot-face class."""
        from promptgrimoire.export.speaker_preprocessor import detect_platform

        html = '<i class="tabler-icon tabler-icon-robot-face"></i>'
        assert detect_platform(html) == "scienceos"

    def test_detect_unknown_platform(self) -> None:
        """Unknown platform when no patterns match."""
        from promptgrimoire.export.speaker_preprocessor import detect_platform

        html = "<p>Just some text</p>"
        assert detect_platform(html) is None

    def test_inject_labels_claude(self) -> None:
        """Claude turns get User:/Assistant: labels injected."""
        from promptgrimoire.export.speaker_preprocessor import inject_speaker_labels

        # Use realistic Claude HTML patterns
        html = """
        <div class="font-user-message" data-testid="user-message">Hello</div>
        <div class="font-claude-response relative leading-[1.65rem]">Hi!</div>
        """
        result = inject_speaker_labels(html)

        # Check data attributes are injected (Lua filter converts to LaTeX labels)
        assert 'data-speaker="user"' in result
        assert 'data-speaker="assistant"' in result
        assert "Hello" in result
        assert "Hi!" in result

    def test_inject_labels_gemini(self) -> None:
        """Gemini turns get User:/Assistant: labels injected."""
        from promptgrimoire.export.speaker_preprocessor import inject_speaker_labels

        html = """
        <user-query>What is CRDT?</user-query>
        <model-response>CRDT stands for...</model-response>
        """
        result = inject_speaker_labels(html)

        # Check data attributes are injected (Lua filter converts to LaTeX labels)
        assert 'data-speaker="user"' in result
        assert 'data-speaker="assistant"' in result


class TestSpeakerDetectionWithFixtures:
    """Test speaker detection against real fixture files."""

    def _load_fixture(self, name: str) -> str:
        return load_conversation_fixture(name)

    def test_detect_claude_fixture(self) -> None:
        """Claude fixture detected as Claude platform."""
        from promptgrimoire.export.speaker_preprocessor import detect_platform

        html = self._load_fixture("claude_cooking.html")
        assert detect_platform(html) == "claude"

    def test_detect_openai_fixture(self) -> None:
        """OpenAI fixture detected as OpenAI platform."""
        from promptgrimoire.export.speaker_preprocessor import detect_platform

        html = self._load_fixture("openai_biblatex.html")
        assert detect_platform(html) == "openai"

    def test_detect_gemini_fixture(self) -> None:
        """Gemini fixture detected as Gemini platform."""
        from promptgrimoire.export.speaker_preprocessor import detect_platform

        html = self._load_fixture("google_gemini_debug.html")
        assert detect_platform(html) == "gemini"

    def test_detect_aistudio_fixture(self) -> None:
        """AI Studio fixture detected as AI Studio platform."""
        from promptgrimoire.export.speaker_preprocessor import detect_platform

        html = self._load_fixture("google_aistudio_ux_discussion.html")
        assert detect_platform(html) == "aistudio"

    def test_inject_labels_claude_fixture(self) -> None:
        """Claude fixture gets labels injected."""
        from promptgrimoire.export.speaker_preprocessor import inject_speaker_labels

        html = self._load_fixture("claude_cooking.html")
        result = inject_speaker_labels(html)

        # Check data attributes are injected (Lua filter converts to LaTeX labels)
        assert 'data-speaker="user"' in result
        assert 'data-speaker="assistant"' in result

    def test_inject_labels_gemini_fixture(self) -> None:
        """Gemini fixture gets labels injected."""
        from promptgrimoire.export.speaker_preprocessor import inject_speaker_labels

        html = self._load_fixture("google_gemini_debug.html")
        result = inject_speaker_labels(html)

        # Check data attributes are injected (Lua filter converts to LaTeX labels)
        assert 'data-speaker="user"' in result
        assert 'data-speaker="assistant"' in result


class TestUIChromeRemoval:
    """UI chrome removal: strip avatars, icons, buttons from export."""

    def test_remove_avatar_images(self) -> None:
        """Images with avatar-related classes are removed."""
        from promptgrimoire.export.chrome_remover import remove_ui_chrome

        html = """
        <img class="avatar" src="user.png" alt="User">
        <p>Hello world</p>
        <img class="profile-pic" src="profile.jpg">
        """
        result = remove_ui_chrome(html)

        assert "avatar" not in result
        assert "profile-pic" not in result
        assert "Hello world" in result

    def test_remove_icon_elements(self) -> None:
        """Icon elements (tabler-icon, etc.) are removed."""
        from promptgrimoire.export.chrome_remover import remove_ui_chrome

        html = """
        <i class="tabler-icon tabler-icon-robot-face"></i>
        <span>Content here</span>
        <svg class="icon-copy"></svg>
        """
        result = remove_ui_chrome(html)

        assert "tabler-icon" not in result
        assert "icon-copy" not in result
        assert "Content here" in result

    def test_remove_action_buttons(self) -> None:
        """Action buttons (copy, share, etc.) are removed."""
        from promptgrimoire.export.chrome_remover import remove_ui_chrome

        html = """
        <button class="copy-button">Copy</button>
        <p>Important text</p>
        <button class="share-button">Share</button>
        """
        result = remove_ui_chrome(html)

        assert "copy-button" not in result
        assert "share-button" not in result
        assert "Important text" in result

    def test_remove_small_images(self) -> None:
        """Small images (< 32px) are removed as likely icons."""
        from promptgrimoire.export.chrome_remover import remove_ui_chrome

        html = """
        <img src="icon.png" width="16" height="16">
        <p>Real content</p>
        <img src="photo.jpg" width="400" height="300">
        """
        result = remove_ui_chrome(html)

        # Small icon removed
        assert 'width="16"' not in result
        # Large image preserved
        assert 'width="400"' in result
        assert "Real content" in result

    def test_remove_display_none_elements(self) -> None:
        """Elements with display:none are removed."""
        from promptgrimoire.export.chrome_remover import remove_ui_chrome

        html = """
        <div style="display: none">Hidden content</div>
        <p>Visible content</p>
        """
        result = remove_ui_chrome(html)

        assert "Hidden content" not in result
        assert "Visible content" in result

    def test_preserve_content_images(self) -> None:
        """Content images without chrome patterns are preserved."""
        from promptgrimoire.export.chrome_remover import remove_ui_chrome

        html = """
        <img src="diagram.png" alt="Architecture diagram" width="800">
        <p>Description of the diagram</p>
        """
        result = remove_ui_chrome(html)

        assert "diagram.png" in result
        assert "Architecture diagram" in result

    def test_remove_remote_url_images(self) -> None:
        """Images with remote URLs are removed (can't be included in LaTeX)."""
        from promptgrimoire.export.chrome_remover import remove_ui_chrome

        html = """
        <img src="https://example.com/image.png" alt="Remote image">
        <p>Content here</p>
        <img src="local.png" alt="Local image">
        """
        result = remove_ui_chrome(html)

        assert "https://example.com" not in result
        assert "Remote image" not in result
        assert "Content here" in result
        assert "local.png" in result

    def test_remove_svg_images(self) -> None:
        """SVG images are removed (need special LaTeX handling)."""
        from promptgrimoire.export.chrome_remover import remove_ui_chrome

        html = """
        <img src="logo.svg" alt="Logo">
        <svg><circle cx="50" cy="50" r="40"/></svg>
        <p>Content here</p>
        """
        result = remove_ui_chrome(html)

        assert "logo.svg" not in result
        assert "<svg" not in result
        assert "Content here" in result

    def test_remove_small_images_from_inline_style(self) -> None:
        """Small images detected from inline style dimensions."""
        from promptgrimoire.export.chrome_remover import remove_ui_chrome

        html = """
        <img src="icon.png" style="width: 16px; height: 16px;">
        <p>Content here</p>
        """
        result = remove_ui_chrome(html)

        assert "icon.png" not in result
        assert "Content here" in result


class TestChromeRemovalInFullPipeline:
    """Verify chrome_remover + convert_html_to_latex produce clean output."""

    @requires_pandoc
    def test_austlii_ribbon_removed_in_full_pipeline(self) -> None:
        """AustLII ribbon navigation is removed when full pipeline is used."""
        from promptgrimoire.export.chrome_remover import remove_ui_chrome

        html = """
        <div id="ribbon">Type | Jurisdiction | Database</div>
        <div id="page-content">
            <h1>Lawlis v R [2025] NSWCCA 183</h1>
            <p>This is the actual judgment content.</p>
        </div>
        """
        # Full pipeline: chrome removal then LaTeX conversion
        cleaned_html = remove_ui_chrome(html)
        result = convert_html_to_latex(cleaned_html, filter_path=LIBREOFFICE_FILTER)

        # Ribbon should be removed
        assert "ribbon" not in result.lower()
        assert "Type" not in result or "Jurisdiction" not in result
        # Content should be preserved
        assert "Lawlis" in result
        assert "judgment content" in result

    @requires_pandoc
    def test_page_header_removed_in_full_pipeline(self) -> None:
        """AustLII page-header is removed when full pipeline is used."""
        from promptgrimoire.export.chrome_remover import remove_ui_chrome

        html = """
        <header id="page-header">
            <img src="logo.svg" alt="AustLII">
            <h1>Supreme Court of NSW</h1>
        </header>
        <div id="page-content">
            <p>Judgment text here.</p>
        </div>
        """
        # Full pipeline: chrome removal then LaTeX conversion
        cleaned_html = remove_ui_chrome(html)
        result = convert_html_to_latex(cleaned_html, filter_path=LIBREOFFICE_FILTER)

        # Header chrome should be removed (logo definitely gone)
        assert "logo.svg" not in result
        # Content should be preserved
        assert "Judgment text" in result
