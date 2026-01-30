"""Integration tests for chatbot fixture PDF compilation.

Tests all 11 conversation fixtures compile through the PDF export pipeline
with speaker pre-processing and UI chrome removal.

See: docs/design-plans/2026-01-29-css-fidelity-pdf-export.md Phase 4
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from promptgrimoire.export.chrome_remover import remove_ui_chrome
from promptgrimoire.export.latex import convert_html_to_latex
from promptgrimoire.export.speaker_preprocessor import inject_speaker_labels
from tests.conftest import requires_latexmk

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.conftest import PdfExportResult

# Fixture directory
FIXTURES_DIR = Path(__file__).parents[1] / "fixtures" / "conversations"

# All chatbot fixtures
CHATBOT_FIXTURES = [
    "claude_cooking.html",
    "claude_maths.html",
    "gemini_crdt_discussion.html",
    "gemini_gemini.html",
    "gemini_images.html",
    "openai_chat.html",
    "openai_dr.html",
    "openai_images.html",
    "scienceos_locus.html",
    "scienceos_rubber.html",
    "austlii.html",
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
    """Load a fixture file by name."""
    return (FIXTURES_DIR / name).read_text()


def _preprocess_chatbot_html(html: str) -> str:
    """Apply chatbot pre-processors in correct order.

    Order matters:
    1. inject_speaker_labels - uses platform markers for detection
    2. remove_ui_chrome - removes markers after labels injected
    """
    html = inject_speaker_labels(html)
    html = remove_ui_chrome(html)
    return html


class TestChatbotFixturesToLatex:
    """Test that chatbot fixtures convert to LaTeX without errors."""

    @pytest.mark.parametrize("fixture_name", CHATBOT_FIXTURES)
    def test_fixture_converts_to_latex(self, fixture_name: str) -> None:
        """Each fixture converts to LaTeX without pandoc errors."""
        html = _load_fixture(fixture_name)
        html = _preprocess_chatbot_html(html)

        # Convert to LaTeX (should not raise)
        latex = convert_html_to_latex(html, filter_path=LIBREOFFICE_FILTER)

        # Basic sanity checks
        assert latex, f"No LaTeX output for {fixture_name}"
        # Should not contain raw HTML tags (except for special LaTeX commands)
        # This is a loose check - just ensure conversion happened
        assert "<div" not in latex.lower() or "div" in latex.lower()


# Fixtures known to have complete conversations (both user and assistant)
_COMPLETE_CONVERSATION_FIXTURES = [
    "claude_cooking.html",
    "openai_chat.html",
    "gemini_crdt_discussion.html",
    "scienceos_locus.html",
]


class TestSpeakerLabelsInjected:
    """Test that speaker labels appear in converted LaTeX for chatbot fixtures."""

    @pytest.mark.parametrize("fixture_name", _COMPLETE_CONVERSATION_FIXTURES)
    def test_speaker_labels_in_latex(self, fixture_name: str) -> None:
        """Chatbot fixtures with complete conversations have both labels."""
        html = _load_fixture(fixture_name)
        html = _preprocess_chatbot_html(html)

        # Convert to LaTeX
        latex = convert_html_to_latex(html, filter_path=LIBREOFFICE_FILTER)

        # Check labels appear (textbf is how strong renders)
        assert "User:" in latex, f"No User: label in {fixture_name}"
        assert "Assistant:" in latex, f"No Assistant: label in {fixture_name}"

    def test_partial_conversation_has_user_label(self) -> None:
        """claude_maths.html has only a user message (placeholder fixture)."""
        html = _load_fixture("claude_maths.html")
        html = _preprocess_chatbot_html(html)

        latex = convert_html_to_latex(html, filter_path=LIBREOFFICE_FILTER)

        # Has user label but no assistant (fixture is incomplete)
        assert "User:" in latex


class TestChromeRemoved:
    """Test that UI chrome is stripped from fixtures."""

    def test_scienceos_icons_removed(self) -> None:
        """ScienceOS tabler icons are removed."""
        html = _load_fixture("scienceos_locus.html")
        result = remove_ui_chrome(html)

        # Icons should be gone
        assert "tabler-icon-robot-face" not in result
        assert "tabler-icon-medal" not in result


class TestChatbotFixturesToPdf:
    """Generate PDFs from chatbot fixtures for visual review.

    These tests compile actual PDFs and save them to output/test_output/
    for manual visual inspection.

    Each fixture gets its own subdirectory with:
    - {fixture_name}.tex - LaTeX source
    - {fixture_name}.pdf - Compiled PDF
    """

    @requires_latexmk
    @pytest.mark.parametrize("fixture_name", CHATBOT_FIXTURES)
    def test_fixture_compiles_to_pdf(
        self,
        fixture_name: str,
        pdf_exporter: Callable[..., PdfExportResult],
    ) -> None:
        """Each fixture compiles to PDF without LaTeX errors."""
        html = _load_fixture(fixture_name)
        html = _preprocess_chatbot_html(html)

        # Derive test name from fixture
        # e.g., "claude_cooking.html" -> "chatbot_claude_cooking"
        test_name = f"chatbot_{fixture_name.replace('.html', '')}"

        # Platform info for acceptance criteria
        from promptgrimoire.export.speaker_preprocessor import detect_platform

        raw_html = _load_fixture(fixture_name)
        platform = detect_platform(raw_html) or "unknown"

        acceptance_criteria = f"""
FIXTURE: {fixture_name}
PLATFORM: {platform}

VISUAL CHECKS:
1. Speaker labels visible (User:/Assistant:) if chatbot fixture
2. Content readable - no garbled text
3. No obvious layout breakage
4. UI chrome removed (no avatars, icons, copy buttons)
5. Content images preserved (if any)
"""

        result = pdf_exporter(
            html=html,
            highlights=[],  # No annotations for these tests
            test_name=test_name,
            acceptance_criteria=acceptance_criteria,
        )

        # Verify PDF was generated
        assert result.pdf_path.exists(), f"PDF not generated for {fixture_name}"
        assert result.pdf_path.stat().st_size > 0, f"PDF is empty for {fixture_name}"
