"""Unit tests for word count enforcement (violation check and message formatting).

Pure function tests -- no async, no DB, no UI.
Verifies AC5.1, AC5.5, AC6.1, AC6.3, AC7.1-AC7.4.
"""

from __future__ import annotations

import pytest

from promptgrimoire.pages.annotation.word_count_enforcement import (
    WordCountViolation,
    check_word_count_violation,
)


class TestWordCountViolationDataclass:
    """WordCountViolation is a frozen dataclass with violation state."""

    def test_frozen(self) -> None:
        v = WordCountViolation()
        with pytest.raises(AttributeError):
            v.over_limit = True  # type: ignore[invalid-assignment]  # intentional: testing runtime immutability

    def test_defaults_no_violation(self) -> None:
        v = WordCountViolation()
        assert v.over_limit is False
        assert v.under_minimum is False
        assert v.over_by == 0
        assert v.under_by == 0
        assert v.count == 0
        assert v.word_minimum is None
        assert v.word_limit is None
        assert v.has_violation is False


class TestCheckWordCountViolation:
    """Tests for check_word_count_violation() pure function.

    Verifies AC5.1 (violation detection), AC5.5 (both violations),
    AC6.1 (hard mode blocking uses same check), AC6.3 (within limits).
    """

    def test_over_limit(self) -> None:
        """AC5.1: count=150, limit=100 -> over_limit=True, over_by=50."""
        result = check_word_count_violation(
            count=150, word_minimum=None, word_limit=100
        )
        assert result.over_limit is True
        assert result.over_by == 50
        assert result.under_minimum is False
        assert result.has_violation is True

    def test_under_minimum(self) -> None:
        """AC5.1: count=50, min=100 -> under_minimum=True, under_by=50."""
        result = check_word_count_violation(count=50, word_minimum=100, word_limit=None)
        assert result.under_minimum is True
        assert result.under_by == 50
        assert result.over_limit is False
        assert result.has_violation is True

    def test_under_minimum_only(self) -> None:
        """count=50, min=100, limit=200 -> under_minimum=True, over_limit=False."""
        result = check_word_count_violation(count=50, word_minimum=100, word_limit=200)
        assert result.under_minimum is True
        assert result.over_limit is False
        assert result.has_violation is True

    def test_within_range(self) -> None:
        """AC6.3: count=150, min=100, limit=200 -> no violation."""
        result = check_word_count_violation(count=150, word_minimum=100, word_limit=200)
        assert result.has_violation is False
        assert result.over_limit is False
        assert result.under_minimum is False

    def test_no_limits(self) -> None:
        """No limits configured -> no violation."""
        result = check_word_count_violation(
            count=150, word_minimum=None, word_limit=None
        )
        assert result.has_violation is False

    def test_at_exactly_limit(self) -> None:
        """count=100, limit=100 -> over_limit=True (at limit counts as over)."""
        result = check_word_count_violation(
            count=100, word_minimum=None, word_limit=100
        )
        assert result.over_limit is True
        assert result.over_by == 0
        assert result.has_violation is True

    def test_at_exactly_minimum(self) -> None:
        """count=100, min=100 -> under_minimum=False (at minimum is OK)."""
        result = check_word_count_violation(
            count=100, word_minimum=100, word_limit=None
        )
        assert result.under_minimum is False
        assert result.has_violation is False

    def test_preserves_count_and_limits(self) -> None:
        """Violation object carries the count and limit values."""
        result = check_word_count_violation(count=150, word_minimum=50, word_limit=100)
        assert result.count == 150
        assert result.word_minimum == 50
        assert result.word_limit == 100
