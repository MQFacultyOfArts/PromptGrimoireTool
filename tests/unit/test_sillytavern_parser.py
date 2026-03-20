"""Tests for SillyTavern chara_card_v3 parser."""

import json
from pathlib import Path

import pytest

from promptgrimoire.models import Character, LorebookEntry, SelectiveLogic
from promptgrimoire.parsers.sillytavern import parse_character_card


@pytest.fixture
def becky_bennett_path() -> Path:
    """Path to the Becky Bennett test fixture."""
    return Path(__file__).parent.parent / "fixtures" / "Becky Bennett (2).json"


class TestParseCharacterCard:
    """Tests for parse_character_card function."""

    def test_returns_character_and_entries(self, becky_bennett_path: Path) -> None:
        """Parser returns a Character and list of LorebookEntry."""
        character, entries = parse_character_card(becky_bennett_path)

        assert isinstance(character, Character)
        assert isinstance(entries, list)
        assert all(isinstance(e, LorebookEntry) for e in entries)

    def test_parses_character_name(self, becky_bennett_path: Path) -> None:
        """Character name is extracted correctly."""
        character, _ = parse_character_card(becky_bennett_path)

        assert character.name == "Becky Bennett"

    def test_parses_character_description(self, becky_bennett_path: Path) -> None:
        """Character description contains appearance info."""
        character, _ = parse_character_card(becky_bennett_path)

        assert "late 30s" in character.description
        assert "light brown hair" in character.description

    def test_parses_character_personality(self, becky_bennett_path: Path) -> None:
        """Character personality contains traits."""
        character, _ = parse_character_card(becky_bennett_path)

        assert "community" in character.personality
        assert "hard work" in character.personality
        assert "introverted" in character.personality

    def test_parses_character_scenario(self, becky_bennett_path: Path) -> None:
        """Character scenario describes the roleplay situation."""
        character, _ = parse_character_card(becky_bennett_path)

        assert "legal" in character.scenario.lower()
        assert "accident" in character.scenario.lower()

    def test_parses_first_message(self, becky_bennett_path: Path) -> None:
        """First message is the opening dialogue."""
        character, _ = parse_character_card(becky_bennett_path)

        assert "Wallaby, Wombat & Wattle" in character.first_mes
        assert "Thanks for making time" in character.first_mes

    def test_parses_system_prompt(self, becky_bennett_path: Path) -> None:
        """System prompt contains roleplay instructions."""
        character, _ = parse_character_card(becky_bennett_path)

        assert "Legal Training Simulation" in character.system_prompt
        assert "30 words" in character.system_prompt
        assert "Law Society" in character.system_prompt

    def test_parses_five_lorebook_entries(self, becky_bennett_path: Path) -> None:
        """All five lorebook entries are parsed."""
        _, entries = parse_character_card(becky_bennett_path)

        assert len(entries) == 5

    def test_lorebook_entry_has_keywords(self, becky_bennett_path: Path) -> None:
        """Lorebook entries have keyword lists."""
        _, entries = parse_character_card(becky_bennett_path)

        # Find the workplace accident entry
        accident_entry = next(e for e in entries if "accident" in e.keys)

        assert "injury" in accident_entry.keys
        assert "horse" in accident_entry.keys
        assert "employer" in accident_entry.keys

    def test_lorebook_entry_has_content(self, becky_bennett_path: Path) -> None:
        """Lorebook entries have content text."""
        _, entries = parse_character_card(becky_bennett_path)

        accident_entry = next(e for e in entries if "accident" in e.keys)

        assert "Harvey" in accident_entry.content  # The horse's name
        assert "Mr Reynolds" in accident_entry.content  # The employer

    def test_lorebook_entry_has_insertion_order(self, becky_bennett_path: Path) -> None:
        """Lorebook entries have insertion_order for priority sorting."""
        _, entries = parse_character_card(becky_bennett_path)

        # All entries should have insertion_order between 85-100
        for entry in entries:
            assert 85 <= entry.insertion_order <= 100

    def test_lorebook_entry_has_scan_depth(self, becky_bennett_path: Path) -> None:
        """Lorebook entries have scan_depth (default 4)."""
        _, entries = parse_character_card(becky_bennett_path)

        for entry in entries:
            assert entry.scan_depth == 4

    def test_lorebook_entry_comments_are_names(self, becky_bennett_path: Path) -> None:
        """Entry comments contain human-readable names."""
        _, entries = parse_character_card(becky_bennett_path)

        comments = {e.comment for e in entries}

        assert "Work Place Accident" in comments
        assert "pancreatitis" in comments
        assert "employer" in comments

    def test_lorebook_selective_logic_defaults(self, becky_bennett_path: Path) -> None:
        """Selective logic defaults to AND_ANY (0)."""
        _, entries = parse_character_card(becky_bennett_path)

        for entry in entries:
            assert entry.selective_logic == SelectiveLogic.AND_ANY

    def test_file_not_found_raises(self, tmp_path: Path) -> None:
        """Missing file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            parse_character_card(tmp_path / "nonexistent.json")

    def test_invalid_json_raises(self, tmp_path: Path) -> None:
        """Invalid JSON raises ValueError."""
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not valid json {{{")

        with pytest.raises(ValueError, match="Invalid JSON"):
            parse_character_card(bad_file)

    def test_missing_name_raises(self, tmp_path: Path) -> None:
        """Missing character name raises ValueError."""
        incomplete = tmp_path / "incomplete.json"
        incomplete.write_text('{"description": "test"}')

        with pytest.raises(ValueError, match="name"):
            parse_character_card(incomplete)

    def test_becky_bennett_mes_example_is_empty(self, becky_bennett_path: Path) -> None:
        """Becky Bennett card has empty mes_example."""
        character, _ = parse_character_card(becky_bennett_path)

        assert character.mes_example == ""

    def test_becky_bennett_post_history_instructions_is_empty(
        self, becky_bennett_path: Path
    ) -> None:
        """Becky Bennett card has empty post_history_instructions."""
        character, _ = parse_character_card(becky_bennett_path)

        assert character.post_history_instructions == ""

    def test_becky_bennett_lorebook_positions_are_before_char(
        self, becky_bennett_path: Path
    ) -> None:
        """All 5 Becky Bennett lorebook entries have position 'before_char'."""
        _, entries = parse_character_card(becky_bennett_path)

        assert len(entries) == 5
        for entry in entries:
            assert entry.position == "before_char"

    def test_mes_example_extracted(self, tmp_path: Path) -> None:
        """Non-empty mes_example is extracted from the data block."""
        card = tmp_path / "card.json"
        card.write_text(
            json.dumps(
                {
                    "name": "Test",
                    "data": {"mes_example": "<START>\n{{char}}: Hello there!"},
                }
            )
        )

        character, _ = parse_character_card(card)

        assert character.mes_example == "<START>\n{{char}}: Hello there!"

    def test_post_history_instructions_extracted(self, tmp_path: Path) -> None:
        """Non-empty post_history_instructions is extracted from the data block."""
        card = tmp_path / "card.json"
        card.write_text(
            json.dumps(
                {
                    "name": "Test",
                    "data": {
                        "post_history_instructions": "Remember to stay in character."
                    },
                }
            )
        )

        character, _ = parse_character_card(card)

        assert character.post_history_instructions == "Remember to stay in character."

    def test_lorebook_position_after_char(self, tmp_path: Path) -> None:
        """Lorebook entry with extensions.position 1 produces 'after_char'."""
        card = tmp_path / "card.json"
        card.write_text(
            json.dumps(
                {
                    "name": "Test",
                    "data": {
                        "character_book": {
                            "entries": [
                                {
                                    "keys": ["test"],
                                    "content": "Test content",
                                    "extensions": {"position": 1},
                                }
                            ]
                        }
                    },
                }
            )
        )

        _, entries = parse_character_card(card)

        assert len(entries) == 1
        assert entries[0].position == "after_char"

    def test_lorebook_position_defaults_to_before_char(self, tmp_path: Path) -> None:
        """Lorebook entry with no extensions.position defaults to 'before_char'."""
        card = tmp_path / "card.json"
        card.write_text(
            json.dumps(
                {
                    "name": "Test",
                    "data": {
                        "character_book": {
                            "entries": [
                                {
                                    "keys": ["test"],
                                    "content": "Test content",
                                    "extensions": {},
                                }
                            ]
                        }
                    },
                }
            )
        )

        _, entries = parse_character_card(card)

        assert len(entries) == 1
        assert entries[0].position == "before_char"
