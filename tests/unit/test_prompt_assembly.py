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

    def test_slot_order_ac23(self) -> None:
        """AC2.3: System prompt has correct slot order.

        system_prompt < description < personality < scenario < mes_example.
        """
        character = Character(
            name="Test",
            system_prompt="SLOT_MAIN",
            description="SLOT_DESC",
            personality="SLOT_PERS",
            scenario="SLOT_SCEN",
            mes_example="SLOT_EXAMPLE",
        )

        prompt = build_system_prompt(character, [], user_name="User")

        main_pos = prompt.index("SLOT_MAIN")
        desc_pos = prompt.index("SLOT_DESC")
        pers_pos = prompt.index("SLOT_PERS")
        scen_pos = prompt.index("SLOT_SCEN")
        example_pos = prompt.index("SLOT_EXAMPLE")

        assert main_pos < desc_pos, "system_prompt must appear before description"
        assert desc_pos < pers_pos, "description must appear before personality"
        assert pers_pos < scen_pos, "personality must appear before scenario"
        assert scen_pos < example_pos, "scenario must appear before mes_example"

    def test_before_char_between_main_and_description_ac24(self) -> None:
        """AC2.4: before_char entries appear between system_prompt and description."""
        character = Character(
            name="Test",
            system_prompt="SLOT_MAIN",
            description="SLOT_DESC",
            scenario="SLOT_SCEN",
            mes_example="SLOT_EXAMPLE",
        )
        entries = [
            LorebookEntry(
                keys=["test"],
                content="LORE_BEFORE",
                insertion_order=100,
                position="before_char",
            ),
        ]

        prompt = build_system_prompt(character, entries, user_name="User")

        main_pos = prompt.index("SLOT_MAIN")
        lore_pos = prompt.index("LORE_BEFORE")
        desc_pos = prompt.index("SLOT_DESC")

        assert main_pos < lore_pos, "before_char must appear after system_prompt"
        assert lore_pos < desc_pos, "before_char must appear before description"

    def test_after_char_between_scenario_and_example_ac24(self) -> None:
        """AC2.4: after_char entries appear between scenario and mes_example."""
        character = Character(
            name="Test",
            system_prompt="SLOT_MAIN",
            description="SLOT_DESC",
            scenario="SLOT_SCEN",
            mes_example="SLOT_EXAMPLE",
        )
        entries = [
            LorebookEntry(
                keys=["test"],
                content="LORE_AFTER",
                insertion_order=100,
                position="after_char",
            ),
        ]

        prompt = build_system_prompt(character, entries, user_name="User")

        scen_pos = prompt.index("SLOT_SCEN")
        lore_pos = prompt.index("LORE_AFTER")
        example_pos = prompt.index("SLOT_EXAMPLE")

        assert scen_pos < lore_pos, "after_char must appear after scenario"
        assert lore_pos < example_pos, "after_char must appear before mes_example"

    def test_all_before_char_by_default_ac24(self) -> None:
        """AC2.4: All entries before_char by default (no after_char).

        When all entries have position='before_char', all lorebook content
        appears between system_prompt and description.
        """
        character = Character(
            name="Test",
            system_prompt="SLOT_MAIN",
            description="SLOT_DESC",
        )
        entries = [
            LorebookEntry(
                keys=["a"],
                content="LORE_A",
                insertion_order=100,
                position="before_char",
            ),
            LorebookEntry(
                keys=["b"],
                content="LORE_B",
                insertion_order=90,
                position="before_char",
            ),
        ]

        prompt = build_system_prompt(character, entries, user_name="User")

        main_pos = prompt.index("SLOT_MAIN")
        lore_a_pos = prompt.index("LORE_A")
        lore_b_pos = prompt.index("LORE_B")
        desc_pos = prompt.index("SLOT_DESC")

        assert main_pos < lore_a_pos < desc_pos
        assert main_pos < lore_b_pos < desc_pos

    def test_budget_sharing_before_exhausts_after_ac24(self) -> None:
        """AC2.4: Budget sharing — before_char entries consume the full budget.

        When before_char entries exhaust the lorebook token budget, after_char
        entries are excluded because the shared budget is fully consumed.
        """
        character = Character(
            name="Test",
            system_prompt="SLOT_MAIN",
            description="SLOT_DESC",
            scenario="SLOT_SCEN",
        )
        # Each entry is ~25 tokens (100 chars / 4)
        entries = [
            LorebookEntry(
                keys=["before"],
                content="B" * 100,
                insertion_order=100,
                position="before_char",
            ),
            LorebookEntry(
                keys=["after"],
                content="AFTER_CONTENT",
                insertion_order=100,
                position="after_char",
            ),
        ]

        # Budget of 25 tokens: before_char entry (~25 tokens) exactly fills it,
        # after_char entry cannot fit because budget is fully consumed
        prompt = build_system_prompt(
            character, entries, user_name="User", lorebook_budget=25
        )

        assert "B" * 100 in prompt, "before_char entry should be included"
        assert "AFTER_CONTENT" not in prompt, (
            "after_char entry should be excluded — budget exhausted by before_char"
        )

    def test_placeholder_substitution_in_mes_example_ac26(self) -> None:
        """AC2.6: Placeholder substitution applied to mes_example content."""
        character = Character(
            name="Becky",
            mes_example=(
                "<START>\n{{user}}: Hello {{char}}.\n"
                "{{char}}: Nice to meet you, {{user}}."
            ),
        )

        prompt = build_system_prompt(character, [], user_name="Jordan")

        assert "{{char}}" not in prompt
        assert "{{user}}" not in prompt
        assert "Jordan: Hello Becky." in prompt
        assert "Becky: Nice to meet you, Jordan." in prompt


class TestBuildMessages:
    """Tests for building the messages array from turns."""

    @pytest.fixture
    def character(self) -> Character:
        """Minimal character for build_messages tests."""
        return Character(name="Test")

    def test_empty_turns_returns_empty(self, character: Character) -> None:
        """Empty turn list returns empty messages."""
        messages = build_messages([], character, user_name="User")
        assert messages == []

    def test_user_turn_is_user_role(self, character: Character) -> None:
        """User turns become 'user' role messages."""
        turns = [Turn(name="Jordan", content="Hello", is_user=True)]

        messages = build_messages(turns, character, user_name="Jordan")

        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello"

    def test_character_turn_is_assistant_role(self, character: Character) -> None:
        """Character turns become 'assistant' role messages."""
        turns = [Turn(name="Becky Bennett", content="Hi there", is_user=False)]

        messages = build_messages(turns, character, user_name="Jordan")

        assert len(messages) == 1
        assert messages[0]["role"] == "assistant"
        assert messages[0]["content"] == "Hi there"

    def test_alternating_conversation(self, character: Character) -> None:
        """Alternating turns create proper message sequence."""
        turns = [
            Turn(name="Jordan", content="Hello", is_user=True),
            Turn(name="Becky Bennett", content="Hi", is_user=False),
            Turn(name="Jordan", content="How are you?", is_user=True),
        ]

        messages = build_messages(turns, character, user_name="Jordan")

        assert len(messages) == 3
        assert [m["role"] for m in messages] == ["user", "assistant", "user"]

    def test_post_history_instructions_appended_ac25(self) -> None:
        """AC2.5: post_history_instructions appended as final user message."""
        character = Character(
            name="Becky",
            post_history_instructions="Stay in character as {{char}}.",
        )
        turns = [
            Turn(name="Jordan", content="Hello", is_user=True),
            Turn(name="Becky", content="Hi there", is_user=False),
        ]

        messages = build_messages(turns, character, user_name="Jordan")

        assert len(messages) == 3
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] == "Stay in character as Becky."

    def test_empty_post_history_instructions_no_extra_message_ac25(self) -> None:
        """AC2.5: Empty post_history_instructions produces no extra message."""
        character = Character(name="Becky", post_history_instructions="")
        turns = [
            Turn(name="Jordan", content="Hello", is_user=True),
            Turn(name="Becky", content="Hi there", is_user=False),
        ]

        messages = build_messages(turns, character, user_name="Jordan")

        assert len(messages) == 2

    def test_whitespace_only_post_history_instructions_no_extra_message(self) -> None:
        """Whitespace-only post_history_instructions produces no extra message."""
        character = Character(name="Becky", post_history_instructions="   \n  ")
        turns = [
            Turn(name="Jordan", content="Hello", is_user=True),
        ]

        messages = build_messages(turns, character, user_name="Jordan")

        assert len(messages) == 1

    def test_post_history_instructions_placeholder_substitution_ac26(self) -> None:
        """AC2.6: Placeholder substitution applied to post_history_instructions."""
        character = Character(
            name="Becky",
            post_history_instructions="Remember: {{char}} is talking to {{user}}.",
        )
        turns = [
            Turn(name="Jordan", content="Hello", is_user=True),
        ]

        messages = build_messages(turns, character, user_name="Jordan")

        assert len(messages) == 2
        phi_message = messages[-1]
        assert phi_message["role"] == "user"
        assert "{{char}}" not in phi_message["content"]
        assert "{{user}}" not in phi_message["content"]
        assert "Becky" in phi_message["content"]
        assert "Jordan" in phi_message["content"]
        assert phi_message["content"] == "Remember: Becky is talking to Jordan."


class TestTokenEstimation:
    """Tests for token estimation and budget management."""

    def test_estimate_tokens_empty_string(self) -> None:
        """Empty string returns 0 tokens."""
        from promptgrimoire.llm.prompt import estimate_tokens

        assert estimate_tokens("") == 0

    def test_estimate_tokens_short_text(self) -> None:
        """Short text returns at least 1 token."""
        from promptgrimoire.llm.prompt import estimate_tokens

        assert estimate_tokens("Hi") == 1

    def test_estimate_tokens_longer_text(self) -> None:
        """Longer text returns roughly 1 token per 4 chars."""
        from promptgrimoire.llm.prompt import estimate_tokens

        # 400 chars should be ~100 tokens
        text = "x" * 400
        tokens = estimate_tokens(text)
        assert 90 <= tokens <= 110


class TestLorebookBudget:
    """Tests for lorebook token budget enforcement."""

    @pytest.fixture
    def character(self) -> Character:
        """Minimal character for budget tests."""
        return Character(name="Test", system_prompt="System")

    def test_no_budget_includes_all_entries(self, character: Character) -> None:
        """With no budget, all entries are included."""
        entries = [
            LorebookEntry(keys=["a"], content="A" * 100, insertion_order=100),
            LorebookEntry(keys=["b"], content="B" * 100, insertion_order=90),
            LorebookEntry(keys=["c"], content="C" * 100, insertion_order=80),
        ]

        prompt = build_system_prompt(character, entries, user_name="User")

        assert "A" * 100 in prompt
        assert "B" * 100 in prompt
        assert "C" * 100 in prompt

    def test_budget_limits_entries(self, character: Character) -> None:
        """Budget stops adding entries when exceeded."""
        # Each entry is ~25 tokens (100 chars / 4)
        entries = [
            LorebookEntry(keys=["a"], content="A" * 100, insertion_order=100),
            LorebookEntry(keys=["b"], content="B" * 100, insertion_order=90),
            LorebookEntry(keys=["c"], content="C" * 100, insertion_order=80),
        ]

        # Budget of 40 tokens should allow first entry (~25) but not second
        prompt = build_system_prompt(
            character, entries, user_name="User", lorebook_budget=40
        )

        assert "A" * 100 in prompt
        assert "B" * 100 not in prompt
        assert "C" * 100 not in prompt

    def test_budget_respects_insertion_order(self, character: Character) -> None:
        """Higher priority entries are included first when budget limited."""
        entries = [
            LorebookEntry(
                keys=["low"], content="LOW_PRIORITY_ENTRY", insertion_order=10
            ),
            LorebookEntry(
                keys=["high"], content="HIGH_PRIORITY_ENTRY", insertion_order=100
            ),
        ]

        # Budget of 5 tokens allows "HIGH_PRIORITY_ENTRY" (~5 tokens) but not both
        prompt = build_system_prompt(
            character, entries, user_name="User", lorebook_budget=5
        )

        # High priority should be included, low priority excluded
        assert "HIGH_PRIORITY_ENTRY" in prompt
        assert "LOW_PRIORITY_ENTRY" not in prompt
