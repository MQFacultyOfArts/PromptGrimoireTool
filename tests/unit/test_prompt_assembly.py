"""Tests for prompt assembly with lorebook injection."""

import pytest

from promptgrimoire.llm.prompt import (
    build_messages,
    build_system_prompt,
    substitute_placeholders,
)
from promptgrimoire.models import Character, LorebookEntry, Turn


class TestSubstitutePlaceholders:
    """Tests for {{char}}/{{user}} placeholder substitution."""

    def test_substitutes_char(self) -> None:
        """{{char}} is replaced with character name."""
        text = "{{char}} walks into the room."
        result = substitute_placeholders(text, char_name="Becky", user_name="Jordan")
        assert result == "Becky walks into the room."

    def test_substitutes_user(self) -> None:
        """{{user}} is replaced with user name."""
        text = "{{user}} asks a question."
        result = substitute_placeholders(text, char_name="Becky", user_name="Jordan")
        assert result == "Jordan asks a question."

    def test_substitutes_multiple(self) -> None:
        """Multiple placeholders are all replaced."""
        text = "{{char}} tells {{user}} about {{char}}'s experience."
        result = substitute_placeholders(text, char_name="Becky", user_name="Jordan")
        assert result == "Becky tells Jordan about Becky's experience."

    def test_case_insensitive(self) -> None:
        """Placeholders are case-insensitive."""
        text = "{{CHAR}} and {{User}} talk."
        result = substitute_placeholders(text, char_name="Becky", user_name="Jordan")
        assert result == "Becky and Jordan talk."

    def test_no_placeholders_unchanged(self) -> None:
        """Text without placeholders is returned unchanged."""
        text = "Just regular text."
        result = substitute_placeholders(text, char_name="Becky", user_name="Jordan")
        assert result == "Just regular text."


class TestBuildSystemPrompt:
    """Tests for building the system prompt with lorebook injection."""

    @pytest.fixture
    def character(self) -> Character:
        """Sample character for testing."""
        return Character(
            name="Becky Bennett",
            description="{{char}} is in her late 30s with brown hair.",
            personality="{{char}} is introverted and detail-oriented.",
            scenario="{{char}} is seeking legal advice from {{user}}.",
            system_prompt="You are {{char}}. Keep responses under 30 words.",
        )

    @pytest.fixture
    def lorebook_entries(self) -> list[LorebookEntry]:
        """Sample activated lorebook entries."""
        return [
            LorebookEntry(
                keys=["accident"],
                content="{{char}} was injured in a workplace accident.",
                insertion_order=100,
            ),
            LorebookEntry(
                keys=["employer"],
                content="{{char}}'s employer was Mr Reynolds.",
                insertion_order=90,
            ),
        ]

    def test_includes_character_info(self, character: Character) -> None:
        """System prompt includes character description, personality, scenario."""
        prompt = build_system_prompt(character, [], user_name="Jordan")

        assert "Becky Bennett" in prompt  # From description
        assert "late 30s" in prompt
        assert "introverted" in prompt
        assert "legal advice" in prompt

    def test_includes_system_instructions(self, character: Character) -> None:
        """System prompt includes the character's system_prompt."""
        prompt = build_system_prompt(character, [], user_name="Jordan")

        assert "30 words" in prompt

    def test_substitutes_placeholders(self, character: Character) -> None:
        """All {{char}} and {{user}} placeholders are substituted."""
        prompt = build_system_prompt(character, [], user_name="Jordan")

        assert "{{char}}" not in prompt
        assert "{{user}}" not in prompt
        assert "Becky Bennett" in prompt
        assert "Jordan" in prompt

    def test_injects_lorebook_before_character(
        self, character: Character, lorebook_entries: list[LorebookEntry]
    ) -> None:
        """Lorebook entries appear before character definition."""
        prompt = build_system_prompt(character, lorebook_entries, user_name="Jordan")

        # Find positions
        accident_pos = prompt.find("workplace accident")
        employer_pos = prompt.find("Mr Reynolds")
        description_pos = prompt.find("late 30s")

        # Lorebook entries should come before character description
        assert accident_pos < description_pos
        assert employer_pos < description_pos

    def test_lorebook_sorted_by_order(
        self, character: Character, lorebook_entries: list[LorebookEntry]
    ) -> None:
        """Lorebook entries are ordered by insertion_order (descending)."""
        prompt = build_system_prompt(character, lorebook_entries, user_name="Jordan")

        # Entry with order 100 should come before entry with order 90
        accident_pos = prompt.find("workplace accident")
        employer_pos = prompt.find("Mr Reynolds")

        assert accident_pos < employer_pos

    def test_lorebook_placeholders_substituted(
        self, character: Character, lorebook_entries: list[LorebookEntry]
    ) -> None:
        """Lorebook entry placeholders are substituted."""
        prompt = build_system_prompt(character, lorebook_entries, user_name="Jordan")

        assert "{{char}}" not in prompt
        # "Becky Bennett was injured" should appear
        assert "Becky Bennett was injured" in prompt


class TestBuildMessages:
    """Tests for building the messages array from turns."""

    def test_empty_turns_returns_empty(self) -> None:
        """Empty turn list returns empty messages."""
        messages = build_messages([])
        assert messages == []

    def test_user_turn_is_user_role(self) -> None:
        """User turns become 'user' role messages."""
        turns = [Turn(name="Jordan", content="Hello", is_user=True)]

        messages = build_messages(turns)

        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello"

    def test_character_turn_is_assistant_role(self) -> None:
        """Character turns become 'assistant' role messages."""
        turns = [Turn(name="Becky Bennett", content="Hi there", is_user=False)]

        messages = build_messages(turns)

        assert len(messages) == 1
        assert messages[0]["role"] == "assistant"
        assert messages[0]["content"] == "Hi there"

    def test_alternating_conversation(self) -> None:
        """Alternating turns create proper message sequence."""
        turns = [
            Turn(name="Jordan", content="Hello", is_user=True),
            Turn(name="Becky Bennett", content="Hi", is_user=False),
            Turn(name="Jordan", content="How are you?", is_user=True),
        ]

        messages = build_messages(turns)

        assert len(messages) == 3
        assert [m["role"] for m in messages] == ["user", "assistant", "user"]
