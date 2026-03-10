"""Unit tests for filename policy module: name splitting and segment sanitisation.

Tests the pure helpers for PDF export filename construction:
- _split_owner_display_name: deterministic name parsing
- _safe_segment: ASCII-safe filename segment sanitisation

Verifies: AC2.1-AC2.6 (owner display name parsing and sanitisation)
"""

from __future__ import annotations

import pytest

from promptgrimoire.export.filename import _safe_segment, _split_owner_display_name


class TestSplitOwnerDisplayName:
    """Tests for _split_owner_display_name: AC2.1-AC2.4."""

    def test_two_token_name_splits_last_first(self) -> None:
        """AC2.1: Two-token display name maps to (last, first)."""
        last, first = _split_owner_display_name("Ada Lovelace")
        assert last == "Lovelace"
        assert first == "Ada"

    def test_multi_token_name_ignores_middle(self) -> None:
        """AC2.2: Multi-token name uses first and last tokens only."""
        last, first = _split_owner_display_name("Mary Jane Smith")
        assert last == "Smith"
        assert first == "Mary"

    def test_single_token_duplicated(self) -> None:
        """AC2.3: Single-token name fills both slots."""
        last, first = _split_owner_display_name("Plato")
        assert last == "Plato"
        assert first == "Plato"

    def test_none_returns_unknown(self) -> None:
        """None input yields (Unknown, Unknown)."""
        last, first = _split_owner_display_name(None)
        assert last == "Unknown"
        assert first == "Unknown"

    def test_blank_string_returns_unknown(self) -> None:
        """Blank/whitespace-only input yields (Unknown, Unknown)."""
        last, first = _split_owner_display_name("   ")
        assert last == "Unknown"
        assert first == "Unknown"

    def test_empty_string_returns_unknown(self) -> None:
        """Empty string yields (Unknown, Unknown)."""
        last, first = _split_owner_display_name("")
        assert last == "Unknown"
        assert first == "Unknown"

    def test_repeated_whitespace_collapsed(self) -> None:
        """Repeated whitespace between tokens is collapsed."""
        last, first = _split_owner_display_name("Ada   Lovelace")
        assert last == "Lovelace"
        assert first == "Ada"


class TestSafeSegment:
    """Tests for _safe_segment: AC2.4-AC2.6."""

    def test_diacritics_transliterated(self) -> None:
        """AC2.4: Non-ASCII Latin characters are transliterated."""
        assert _safe_segment("José") == "Jose"
        assert _safe_segment("Núñez") == "Nunez"

    def test_punctuation_replaced_with_underscore(self) -> None:
        """AC2.5: Unsafe punctuation replaced with underscores."""
        result = _safe_segment("draft: final!")
        assert result == "draft_final"

    def test_path_separators_replaced(self) -> None:
        """AC2.5: Path separators replaced with underscores."""
        result = _safe_segment("folder/name")
        assert result == "folder_name"

    def test_repeated_underscores_collapsed(self) -> None:
        """AC2.5: Repeated underscores are collapsed."""
        result = _safe_segment("a___b")
        assert result == "a_b"

    def test_leading_trailing_underscores_stripped(self) -> None:
        """AC2.5: Leading/trailing underscores are stripped."""
        result = _safe_segment("_hello_")
        assert result == "hello"

    @pytest.mark.parametrize(
        "value",
        ["\U0001f600", "\U0001f4a9\U0001f525", "\u2603"],
        ids=["grinning-face", "poop-fire", "snowman"],
    )
    def test_emoji_and_symbols_removed(self, value: str) -> None:
        """AC2.6: Emoji/symbols with no transliteration yield empty string."""
        assert _safe_segment(value) == ""

    def test_mixed_ascii_and_emoji(self) -> None:
        """AC2.6: Emoji removed but ASCII content preserved."""
        result = _safe_segment("hello\U0001f600world")
        assert result == "helloworld"

    def test_normal_text_passthrough(self) -> None:
        """Normal ASCII text passes through unchanged."""
        assert _safe_segment("MyTitle") == "MyTitle"

    def test_preserves_case(self) -> None:
        """Case is preserved in output."""
        assert _safe_segment("LAWS5000") == "LAWS5000"
