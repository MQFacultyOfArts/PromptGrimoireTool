"""Tests for lorebook keyword activation engine."""

import pytest

from promptgrimoire.llm.lorebook import (
    activate_entries,
    build_haystack,
    match_keyword,
)
from promptgrimoire.models import LorebookEntry, SelectiveLogic, Turn


class TestMatchKeyword:
    """Tests for single keyword matching."""

    def test_simple_match_case_insensitive(self) -> None:
        """Keywords match case-insensitively by default."""
        assert match_keyword("accident", "I had an ACCIDENT at work")
        assert match_keyword("ACCIDENT", "I had an accident at work")

    def test_simple_match_case_sensitive(self) -> None:
        """Case-sensitive matching when enabled."""
        assert match_keyword("accident", "I had an accident", case_sensitive=True)
        assert not match_keyword("accident", "I had an ACCIDENT", case_sensitive=True)

    def test_no_match_returns_false(self) -> None:
        """Non-matching keyword returns False."""
        assert not match_keyword("horse", "I had an accident at work")

    def test_partial_word_matches_by_default(self) -> None:
        """Partial word matches without whole_words flag."""
        assert match_keyword("work", "I was working hard")
        assert match_keyword("accident", "accidental injury")

    def test_whole_words_prevents_partial_match(self) -> None:
        """Whole word matching prevents partial matches."""
        assert not match_keyword("work", "I was working hard", match_whole_words=True)
        assert match_keyword("work", "I went to work today", match_whole_words=True)

    def test_wildcard_pattern(self) -> None:
        """Asterisk wildcard matches word variations."""
        # SillyTavern uses * for simple wildcards
        assert match_keyword("drink*", "I was drinking too much")
        assert match_keyword("drink*", "She drinks coffee")
        assert not match_keyword("drink*", "I had a meal")

    def test_empty_keyword_returns_false(self) -> None:
        """Empty keyword never matches."""
        assert not match_keyword("", "some text")

    def test_empty_text_returns_false(self) -> None:
        """Empty text never matches."""
        assert not match_keyword("accident", "")


class TestBuildHaystack:
    """Tests for building searchable text from turns."""

    def test_joins_recent_turns(self) -> None:
        """Haystack joins recent turn content."""
        turns = [
            Turn(name="User", content="Hello", is_user=True),
            Turn(name="Becky", content="Hi there", is_user=False),
            Turn(name="User", content="Tell me about the accident", is_user=True),
        ]

        haystack = build_haystack(turns, depth=2)

        assert "Hi there" in haystack
        assert "accident" in haystack
        # First turn should be excluded (depth=2)
        assert "Hello" not in haystack

    def test_depth_zero_returns_empty(self) -> None:
        """Depth of 0 returns empty string."""
        turns = [Turn(name="User", content="Hello", is_user=True)]

        assert build_haystack(turns, depth=0) == ""

    def test_depth_exceeds_turns(self) -> None:
        """Depth larger than turn count includes all turns."""
        turns = [
            Turn(name="User", content="First", is_user=True),
            Turn(name="Becky", content="Second", is_user=False),
        ]

        haystack = build_haystack(turns, depth=10)

        assert "First" in haystack
        assert "Second" in haystack

    def test_empty_turns_returns_empty(self) -> None:
        """Empty turn list returns empty string."""
        assert build_haystack([], depth=4) == ""


class TestActivateEntries:
    """Tests for activating lorebook entries based on conversation."""

    @pytest.fixture
    def sample_entries(self) -> list[LorebookEntry]:
        """Sample lorebook entries for testing."""
        return [
            LorebookEntry(
                id=0,
                keys=["accident", "injury", "horse"],
                content="Details about the workplace accident...",
                comment="Workplace Accident",
                insertion_order=90,
            ),
            LorebookEntry(
                id=1,
                keys=["alcohol", "drink*", "pancreatitis"],
                content="Details about pancreatitis...",
                comment="Pancreatitis",
                insertion_order=85,
            ),
            LorebookEntry(
                id=2,
                keys=["employer", "work", "safety"],
                content="Details about the employer...",
                comment="Employer",
                insertion_order=100,
            ),
        ]

    def test_activates_matching_entry(
        self, sample_entries: list[LorebookEntry]
    ) -> None:
        """Entry activates when keyword matches."""
        turns = [Turn(name="User", content="Tell me about the accident", is_user=True)]

        activated = activate_entries(sample_entries, turns)

        assert len(activated) == 1
        assert activated[0].comment == "Workplace Accident"

    def test_activates_multiple_entries(
        self, sample_entries: list[LorebookEntry]
    ) -> None:
        """Multiple entries can activate from same text."""
        turns = [
            Turn(
                name="User",
                content="What happened at work with the accident?",
                is_user=True,
            )
        ]

        activated = activate_entries(sample_entries, turns)

        comments = {e.comment for e in activated}
        assert "Workplace Accident" in comments
        assert "Employer" in comments

    def test_sorted_by_insertion_order(
        self, sample_entries: list[LorebookEntry]
    ) -> None:
        """Activated entries are sorted by insertion_order descending."""
        turns = [Turn(name="User", content="accident work employer", is_user=True)]

        activated = activate_entries(sample_entries, turns)

        # Order 100 > 90 > 85
        assert activated[0].insertion_order == 100
        assert activated[1].insertion_order == 90

    def test_respects_scan_depth(self, sample_entries: list[LorebookEntry]) -> None:
        """Only scans messages within entry's scan_depth."""
        # Set a shallow scan depth
        sample_entries[0].scan_depth = 1

        turns = [
            Turn(name="User", content="Tell me about the accident", is_user=True),
            Turn(name="Becky", content="It was terrible", is_user=False),
            Turn(name="User", content="How are you now?", is_user=True),
        ]

        activated = activate_entries(sample_entries, turns)

        # "accident" is 3 turns back, but scan_depth=1, so shouldn't match entry 0
        # Entry 2 has default depth=4 and "work" might not be in recent turns
        accident_entry = next(
            (e for e in activated if e.comment == "Workplace Accident"), None
        )
        assert accident_entry is None

    def test_disabled_entry_not_activated(
        self, sample_entries: list[LorebookEntry]
    ) -> None:
        """Disabled entries are skipped."""
        sample_entries[0].enabled = False

        turns = [Turn(name="User", content="Tell me about the accident", is_user=True)]

        activated = activate_entries(sample_entries, turns)

        assert len(activated) == 0

    def test_wildcard_keyword_activates(
        self, sample_entries: list[LorebookEntry]
    ) -> None:
        """Wildcard keywords like 'drink*' activate correctly."""
        turns = [Turn(name="User", content="Were you drinking?", is_user=True)]

        activated = activate_entries(sample_entries, turns)

        assert len(activated) == 1
        assert activated[0].comment == "Pancreatitis"

    def test_no_matches_returns_empty(
        self, sample_entries: list[LorebookEntry]
    ) -> None:
        """No matching keywords returns empty list."""
        turns = [Turn(name="User", content="Hello, nice weather", is_user=True)]

        activated = activate_entries(sample_entries, turns)

        assert activated == []


class TestSelectiveLogic:
    """Tests for secondary keyword selective logic."""

    def test_and_any_requires_primary_and_secondary(self) -> None:
        """AND_ANY: primary must match AND at least one secondary."""
        entry = LorebookEntry(
            keys=["accident"],
            secondary_keys=["horse", "car"],
            content="Details...",
            selective=True,
            selective_logic=SelectiveLogic.AND_ANY,
        )

        # Primary matches, secondary matches
        turns_match = [Turn(name="User", content="accident with horse", is_user=True)]
        activated = activate_entries([entry], turns_match)
        assert len(activated) == 1

        # Primary matches, no secondary
        turns_no_secondary = [
            Turn(name="User", content="accident at work", is_user=True)
        ]
        activated = activate_entries([entry], turns_no_secondary)
        assert len(activated) == 0

    def test_not_any_requires_no_secondary(self) -> None:
        """NOT_ANY: primary must match AND no secondary can match."""
        entry = LorebookEntry(
            keys=["accident"],
            secondary_keys=["horse", "car"],
            content="Details...",
            selective=True,
            selective_logic=SelectiveLogic.NOT_ANY,
        )

        # Primary matches, no secondary - should activate
        turns_no_secondary = [
            Turn(name="User", content="accident at work", is_user=True)
        ]
        activated = activate_entries([entry], turns_no_secondary)
        assert len(activated) == 1

        # Primary matches, secondary matches - should NOT activate
        turns_with_secondary = [
            Turn(name="User", content="accident with horse", is_user=True)
        ]
        activated = activate_entries([entry], turns_with_secondary)
        assert len(activated) == 0

    def test_selective_false_ignores_secondary(self) -> None:
        """When selective=False, secondary keywords are ignored."""
        entry = LorebookEntry(
            keys=["accident"],
            secondary_keys=["horse"],  # Would block if selective
            content="Details...",
            selective=False,
            selective_logic=SelectiveLogic.AND_ANY,
        )

        turns = [Turn(name="User", content="accident at work", is_user=True)]
        activated = activate_entries([entry], turns)

        # Should activate because selective=False
        assert len(activated) == 1
