"""Unit tests for the pure selection-event validation logic in text_selection.py.

_validate_selection_args was extracted from the text_selected event handler
to bring text_selection_demo_page's cognitive complexity under the project
threshold. It is pure (no NiceGUI/UI side effects), so it is unit-testable
in isolation.
"""

from __future__ import annotations

from promptgrimoire.pages.text_selection import (
    MAX_DISPLAY_LENGTH,
    _validate_selection_args,
)


class TestValidateSelectionArgs:
    """Tests for _validate_selection_args."""

    def test_valid_short_selection_returns_quoted_display(self) -> None:
        """A short valid selection returns the parsed tuple with a quoted display."""
        result = _validate_selection_args("hello", 0, 5)
        assert result == ("hello", 0, 5, '"hello"')

    def test_long_text_is_truncated_in_display(self) -> None:
        """Text longer than MAX_DISPLAY_LENGTH is truncated with an ellipsis."""
        text = "x" * (MAX_DISPLAY_LENGTH + 10)
        result = _validate_selection_args(text, 0, len(text))
        assert result is not None
        _text, _start, _end, display = result
        assert display == f'"{text[:MAX_DISPLAY_LENGTH]}..."'

    def test_text_at_exact_max_length_is_not_truncated(self) -> None:
        """Text exactly MAX_DISPLAY_LENGTH long is shown in full."""
        text = "x" * MAX_DISPLAY_LENGTH
        result = _validate_selection_args(text, 0, len(text))
        assert result is not None
        assert result[3] == f'"{text}"'

    def test_non_string_text_is_rejected(self) -> None:
        """A non-str text argument (unexpected client payload) is rejected."""
        assert _validate_selection_args(123, 0, 3) is None

    def test_non_int_start_is_rejected(self) -> None:
        """A non-int start argument is rejected."""
        assert _validate_selection_args("hi", "0", 2) is None

    def test_non_int_end_is_rejected(self) -> None:
        """A non-int end argument is rejected."""
        assert _validate_selection_args("hi", 0, "2") is None

    def test_negative_start_is_rejected(self) -> None:
        """A negative start offset is rejected."""
        assert _validate_selection_args("hi", -1, 2) is None

    def test_negative_end_is_rejected(self) -> None:
        """A negative end offset is rejected."""
        assert _validate_selection_args("hi", 0, -1) is None

    def test_start_after_end_is_rejected(self) -> None:
        """An inverted range (start > end) is rejected."""
        assert _validate_selection_args("hi", 5, 2) is None

    def test_empty_text_is_rejected(self) -> None:
        """Empty selected text is rejected even with a valid range."""
        assert _validate_selection_args("", 0, 0) is None

    def test_start_equals_end_is_accepted(self) -> None:
        """A zero-width but non-inverted range (start == end) is accepted."""
        assert _validate_selection_args("a", 3, 3) == ("a", 3, 3, '"a"')
