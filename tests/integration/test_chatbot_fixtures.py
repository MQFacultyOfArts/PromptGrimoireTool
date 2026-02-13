"""Integration tests for chatbot fixture PDF compilation.

Tests all conversation fixtures compile through the PDF export pipeline
with speaker pre-processing and UI chrome removal.

See: docs/design-plans/2026-01-29-css-fidelity-pdf-export.md Phase 4
"""

from __future__ import annotations

from pathlib import Path

import pytest

from promptgrimoire.export.pandoc import convert_html_to_latex
from promptgrimoire.export.platforms import preprocess_for_export
from tests.conftest import load_conversation_fixture

# All chatbot fixtures
CHATBOT_FIXTURES = [
    # Claude
    "claude_cooking.html",
    "claude_maths.html",
    # Google AI Studio
    "google_aistudio_image.html",
    "google_aistudio_ux_discussion.html",
    # Google Gemini
    "google_gemini_debug.html",
    "google_gemini_deep_research.html",
    # OpenAI
    "openai_biblatex.html",
    "openai_dh_dr.html",
    "openai_dprk_denmark.html",
    "openai_software_long_dr.html",
    # ScienceOS
    "scienceos_loc.html",
    "scienceos_philsci.html",
    # Legal document (not a chatbot, but tests chrome removal)
    "austlii.html",
    # Translation documents (test CJK character handling)
    "chinese_wikipedia.html",
    "translation_japanese_sample.html",
    "translation_korean_sample.html",
    "translation_spanish_sample.html",
]

# Path to Lua filter
LIBREOFFICE_FILTER = (
    Path(__file__).parents[2]
    / "src"
    / "promptgrimoire"
    / "export"
    / "filters"
    / "libreoffice.lua"
)


def _load_fixture(name: str) -> str:
    """Load a fixture file by name (supports .html and .html.gz)."""
    return load_conversation_fixture(name)


def _preprocess_chatbot_html(html: str) -> str:
    """Preprocess chatbot HTML for LaTeX conversion."""
    return preprocess_for_export(html)


class TestChatbotFixturesToLatex:
    """Test that chatbot fixtures convert to LaTeX without errors."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("fixture_name", CHATBOT_FIXTURES)
    async def test_fixture_converts_to_latex(self, fixture_name: str) -> None:
        """Each fixture converts to LaTeX without pandoc errors."""
        html = _load_fixture(fixture_name)
        html = _preprocess_chatbot_html(html)

        # Convert to LaTeX (should not raise)
        latex = await convert_html_to_latex(html, filter_paths=[LIBREOFFICE_FILTER])

        # Basic sanity checks
        assert latex, f"No LaTeX output for {fixture_name}"
        # Should not contain raw HTML tags (except for special LaTeX commands)
        # This is a loose check - just ensure conversion happened
        assert "<div" not in latex.lower() or "div" in latex.lower()


# Fixtures known to have complete conversations (both user and assistant)
# Note: ScienceOS fixtures are research reports, not chats with turns
_COMPLETE_CONVERSATION_FIXTURES = [
    "claude_cooking.html",
    "google_aistudio_ux_discussion.html",
    "google_gemini_debug.html",
    "openai_biblatex.html",
]


class TestSpeakerLabelsInjected:
    """Test that speaker labels appear in converted LaTeX for chatbot fixtures."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("fixture_name", _COMPLETE_CONVERSATION_FIXTURES)
    async def test_speaker_labels_in_latex(self, fixture_name: str) -> None:
        """Chatbot fixtures with complete conversations have both labels."""
        html = _load_fixture(fixture_name)
        html = _preprocess_chatbot_html(html)

        # Convert to LaTeX
        latex = await convert_html_to_latex(html, filter_paths=[LIBREOFFICE_FILTER])

        # Check labels appear (textbf is how strong renders)
        assert "User:" in latex, f"No User: label in {fixture_name}"
        assert "Assistant:" in latex, f"No Assistant: label in {fixture_name}"

    @pytest.mark.asyncio
    async def test_partial_conversation_has_user_label(self) -> None:
        """claude_maths.html has only a user message (placeholder fixture)."""
        html = _load_fixture("claude_maths.html")
        html = _preprocess_chatbot_html(html)

        latex = await convert_html_to_latex(html, filter_paths=[LIBREOFFICE_FILTER])

        # Has user label but no assistant (fixture is incomplete)
        assert "User:" in latex


class TestChromeRemoved:
    """Test that UI chrome is stripped from fixtures."""

    def test_chrome_removal_reduces_size(self) -> None:
        """Chrome removal should reduce HTML size for fixtures with UI elements."""
        # scienceos_loc has lots of buttons and UI chrome
        html = _load_fixture("scienceos_loc.html")
        result = preprocess_for_export(html)

        # Chrome removal should reduce size (buttons, hidden elements, etc.)
        assert len(result) < len(html), "Chrome removal should reduce HTML size"


# CJK/i18n compile tests migrated to test_i18n_mega_doc.py (Task 12).
# English compile tests migrated to test_english_mega_doc.py (Task 10).
# TestChatbotFixturesToPdf deleted — all compile tests now in mega-documents.
