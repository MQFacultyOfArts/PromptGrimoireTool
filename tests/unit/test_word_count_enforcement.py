"""Unit tests for word count enforcement (violation check and message formatting).

Pure function tests -- no async, no DB, no UI.
Verifies AC5.1, AC5.5, AC6.1, AC6.3, AC7.1-AC7.4.
"""

from __future__ import annotations

import pytest

from promptgrimoire.pages.annotation.word_count_enforcement import (
    WordCountViolation,
    check_word_count_violation,
    format_violation_message,
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


class TestFormatViolationMessage:
    """Tests for format_violation_message().

    Verifies AC5.1 (dialog message text) and AC5.5 (both violations message).
    """

    def test_over_limit_message(self) -> None:
        """AC5.1: Over limit message includes word limit and current count."""
        violation = check_word_count_violation(
            count=150, word_minimum=None, word_limit=100
        )
        msg = format_violation_message(violation)
        assert msg == (
            "Your response is 50 words over the 100-word limit (current count: 150)."
        )

    def test_under_minimum_message(self) -> None:
        """AC5.1: Under minimum message includes word minimum and current count."""
        violation = check_word_count_violation(
            count=50, word_minimum=100, word_limit=None
        )
        msg = format_violation_message(violation)
        assert msg == (
            "Your response is 50 words under the 100-word minimum (current count: 50)."
        )

    def test_both_violated_message(self) -> None:
        """AC5.5: Both violated message mentions over and under.

        Constructs a WordCountViolation directly since this state is
        unreachable through check_word_count_violation() with validated data
        (word_minimum < word_limit). Tests the formatting code path.
        """
        violation = WordCountViolation(
            over_limit=True,
            under_minimum=True,
            over_by=50,
            under_by=30,
            count=250,
            word_minimum=280,
            word_limit=200,
        )
        msg = format_violation_message(violation)
        assert msg == (
            "Your response is 50 words over the limit and 30 words under the minimum."
        )

    def test_over_limit_large_count_has_comma_formatting(self) -> None:
        """Large counts use comma-separated formatting."""
        violation = check_word_count_violation(
            count=1567, word_minimum=None, word_limit=1500
        )
        msg = format_violation_message(violation)
        assert "(current count: 1,567)" in msg

    def test_no_violation_returns_empty_string(self) -> None:
        """Guard case: returns '' when has_violation is False.

        Prevents nonsense like 'Your response is 0 words under the
        None-word minimum (current count: 0).' on a clean violation.
        """
        violation = WordCountViolation()
        msg = format_violation_message(violation)
        assert msg == ""

    def test_within_range_returns_empty_string(self) -> None:
        """Format on a within-range violation also returns empty string."""
        violation = check_word_count_violation(
            count=150, word_minimum=100, word_limit=200
        )
        assert not violation.has_violation
        msg = format_violation_message(violation)
        assert msg == ""


class TestViolationEdgeCases:
    """Edge case tests for check_word_count_violation().

    Verifies AC6.3 (within limits proceeds normally) and boundary conditions.
    """

    def test_zero_count_no_limits(self) -> None:
        """count=0 with no limits -> no violation."""
        result = check_word_count_violation(count=0, word_minimum=None, word_limit=None)
        assert result.has_violation is False

    def test_zero_count_with_limit_only(self) -> None:
        """count=0, limit=100, no minimum -> not over limit."""
        result = check_word_count_violation(count=0, word_minimum=None, word_limit=100)
        assert result.over_limit is False
        assert result.under_minimum is False
        assert result.has_violation is False

    def test_zero_count_with_minimum(self) -> None:
        """count=0, min=100 -> under minimum by 100."""
        result = check_word_count_violation(count=0, word_minimum=100, word_limit=None)
        assert result.under_minimum is True
        assert result.under_by == 100
        assert result.over_limit is False

    def test_large_count_over_limit(self) -> None:
        """count=10000, limit=5000 -> over_by=5000."""
        result = check_word_count_violation(
            count=10000, word_minimum=None, word_limit=5000
        )
        assert result.over_limit is True
        assert result.over_by == 5000


class TestAC7NonBlockingBehaviour:
    """AC7.1-AC7.4: Word count enforcement does NOT block save, edit, or share.

    These tests verify that the word_count_enforcement module is only used
    by export-related code. If someone adds an import of enforcement symbols
    to a save/edit/share module, these tests will fail as a regression guard.
    """

    def test_ac7_1_save_does_not_import_enforcement(self) -> None:
        """AC7.1: CRDT save path does not import word count enforcement."""
        import importlib

        mod = importlib.import_module("promptgrimoire.crdt")
        assert not hasattr(mod, "WordCountViolation")
        assert not hasattr(mod, "check_word_count_violation")

    def test_ac7_2_edit_does_not_import_enforcement(self) -> None:
        """AC7.2: Respond/edit module does not import word count enforcement."""
        import importlib

        mod = importlib.import_module("promptgrimoire.pages.annotation.respond")
        assert not hasattr(mod, "WordCountViolation")
        assert not hasattr(mod, "check_word_count_violation")

    def test_ac7_3_share_does_not_import_enforcement(self) -> None:
        """AC7.3: ACL/share module does not import word count enforcement."""
        import importlib

        mod = importlib.import_module("promptgrimoire.db.acl")
        assert not hasattr(mod, "WordCountViolation")
        assert not hasattr(mod, "check_word_count_violation")

    def test_ac7_4_only_export_uses_enforcement(self) -> None:
        """AC7.4: Enforcement is only imported by export-related modules.

        Negative controls: respond and acl must NOT have enforcement symbols.
        Positive control: pdf_export WILL import enforcement after Task 4.
        The positive control is marked as a TODO since Task 4 adds the import.
        """
        import importlib

        # Negative controls (must always pass)
        respond = importlib.import_module("promptgrimoire.pages.annotation.respond")
        assert not hasattr(respond, "check_word_count_violation")

        acl = importlib.import_module("promptgrimoire.db.acl")
        assert not hasattr(acl, "check_word_count_violation")

        # Positive control: pdf_export imports enforcement (wired in Task 4).
        pdf_export = importlib.import_module(
            "promptgrimoire.pages.annotation.pdf_export"
        )
        assert hasattr(pdf_export, "check_word_count_violation")
