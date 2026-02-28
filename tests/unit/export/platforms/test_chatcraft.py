"""Unit tests for ChatCraft platform handler — speaker classification."""

from __future__ import annotations

from promptgrimoire.export.platforms.chatcraft import _classify_speaker


class TestClassifySpeaker:
    """Tests for _classify_speaker heuristic."""

    def test_system_prompt(self) -> None:
        """'System Prompt' maps to 'system'."""
        assert _classify_speaker("System Prompt") == "system"

    def test_model_identifier_with_hyphens(self) -> None:
        """Model names like 'claude-sonnet-4' (hyphens, no spaces) are assistant."""
        assert _classify_speaker("claude-sonnet-4") == "assistant"
        assert _classify_speaker("gpt-4") == "assistant"
        assert _classify_speaker("gpt-4o-mini") == "assistant"

    def test_human_name_with_spaces(self) -> None:
        """Human names with spaces are user."""
        assert _classify_speaker("John Smith") == "user"
        assert _classify_speaker("Alice B") == "user"

    def test_single_word_no_hyphen(self) -> None:
        """Single word without hyphen is user (default)."""
        assert _classify_speaker("Alice") == "user"
