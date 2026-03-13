"""Tests for the personal_grimoire guide script module.

Verifies:
- personal-grimoire-guide-208.AC1: _SAMPLE_HTML is non-empty and well-formed HTML
- personal-grimoire-guide-208.AC1: GUIDE_OUTPUT_DIR resolves to docs/guides
- personal-grimoire-guide-208.AC2.1: _setup_loose_student delegates
  to seed_user_and_enrol
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from promptgrimoire.docs.scripts.personal_grimoire import (
    _SAMPLE_HTML,
    GUIDE_OUTPUT_DIR,
    _setup_loose_student,
)


class TestSampleHTML:
    """Tests for the _SAMPLE_HTML module-level constant."""

    def test_sample_html_is_non_empty(self) -> None:
        """_SAMPLE_HTML must contain content — not an empty string."""
        assert _SAMPLE_HTML

    def test_sample_html_starts_with_div(self) -> None:
        """_SAMPLE_HTML must begin with a <div> tag (well-formed root element)."""
        stripped = _SAMPLE_HTML.strip()
        assert stripped.startswith("<div"), (
            f"Expected _SAMPLE_HTML to start with '<div', got: {stripped[:40]!r}"
        )

    def test_sample_html_ends_with_closing_div(self) -> None:
        """_SAMPLE_HTML must end with a closing </div> tag."""
        stripped = _SAMPLE_HTML.strip()
        assert stripped.endswith("</div>"), (
            f"Expected _SAMPLE_HTML to end with '</div>', got: ...{stripped[-20:]!r}"
        )

    def test_sample_html_contains_user_turn(self) -> None:
        """_SAMPLE_HTML must contain a user/Human turn marker."""
        assert "Human:" in _SAMPLE_HTML

    def test_sample_html_contains_assistant_turn(self) -> None:
        """_SAMPLE_HTML must contain an assistant/AI turn marker."""
        assert "Assistant:" in _SAMPLE_HTML

    def test_sample_html_contains_japanese_legal_content(self) -> None:
        """_SAMPLE_HTML must reference Japanese legal translation content."""
        assert "good faith" in _SAMPLE_HTML


class TestGuideOutputDir:
    """Tests for the GUIDE_OUTPUT_DIR module-level constant."""

    def test_guide_output_dir_is_path_instance(self) -> None:
        """GUIDE_OUTPUT_DIR must be a pathlib.Path instance."""
        assert isinstance(GUIDE_OUTPUT_DIR, Path)

    def test_guide_output_dir_resolves_to_docs_guides(self) -> None:
        """GUIDE_OUTPUT_DIR must be Path('docs/guides')."""
        assert Path("docs/guides") == GUIDE_OUTPUT_DIR

    def test_guide_output_dir_parts(self) -> None:
        """GUIDE_OUTPUT_DIR must have exactly two parts: 'docs' and 'guides'."""
        assert GUIDE_OUTPUT_DIR.parts == ("docs", "guides")


class TestSetupLooseStudent:
    """Tests for the _setup_loose_student setup helper."""

    def test_calls_seed_user_and_enrol(self) -> None:
        """_setup_loose_student must delegate to seed_user_and_enrol."""
        with patch(
            "promptgrimoire.docs.scripts.personal_grimoire.seed_user_and_enrol"
        ) as mock_seed:
            _setup_loose_student()

        mock_seed.assert_called_once_with(
            "loose-student@test.example.edu.au", "Loose Student"
        )
