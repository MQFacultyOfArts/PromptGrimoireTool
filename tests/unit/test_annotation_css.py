"""Unit tests for annotation page CSS rules.

Validates that _PAGE_CSS contains correct speaker role styling rules.
"""

from __future__ import annotations

from promptgrimoire.pages.annotation.css import _PAGE_CSS


class TestSpeakerCssRules:
    """Speaker role CSS pseudo-element rules in _PAGE_CSS."""

    def test_user_speaker_rule_exists(self) -> None:
        """User speaker rule should exist with blue colour scheme."""
        assert '[data-speaker="user"]::before' in _PAGE_CSS
        assert "#1a5f7a" in _PAGE_CSS  # user text colour

    def test_assistant_speaker_rule_exists(self) -> None:
        """Assistant speaker rule should exist with green colour scheme."""
        assert '[data-speaker="assistant"]::before' in _PAGE_CSS
        assert "#2e7d32" in _PAGE_CSS  # assistant text colour

    def test_system_speaker_rule_exists(self) -> None:
        """System speaker rule should exist with amber/orange colour scheme."""
        assert '[data-speaker="system"]::before' in _PAGE_CSS

    def test_system_speaker_content_label(self) -> None:
        """System speaker pseudo-element should display 'System:' label."""
        assert 'content: "System:"' in _PAGE_CSS

    def test_system_speaker_colour_distinct(self) -> None:
        """System colour (#e65100) is distinct from user and assistant."""
        assert "#e65100" in _PAGE_CSS  # system text colour (orange)
        # Verify it is distinct from user blue and assistant green
        user_colour = "#1a5f7a"
        assistant_colour = "#2e7d32"
        system_colour = "#e65100"
        assert system_colour != user_colour
        assert system_colour != assistant_colour

    def test_system_speaker_background(self) -> None:
        """System speaker should have an amber background."""
        assert "#fff3e0" in _PAGE_CSS  # system background colour (light amber)
