"""Tests for PageState word count limit fields.

Verifies:
- word-count-limits-47.AC4: Word count fields exist on PageState with correct defaults
"""

from uuid import uuid4

from promptgrimoire.pages.annotation import PageState


class TestPageStateWordCountDefaults:
    """Verify default values for word count fields."""

    def test_default_word_minimum_is_none(self) -> None:
        state = PageState(workspace_id=uuid4())
        assert state.word_minimum is None

    def test_default_word_limit_is_none(self) -> None:
        state = PageState(workspace_id=uuid4())
        assert state.word_limit is None

    def test_default_word_limit_enforcement_is_false(self) -> None:
        state = PageState(workspace_id=uuid4())
        assert state.word_limit_enforcement is False

    def test_default_word_count_badge_is_none(self) -> None:
        state = PageState(workspace_id=uuid4())
        assert state.word_count_badge is None


class TestPageStateWordCountExplicit:
    """Verify word count fields accept explicit values."""

    def test_word_minimum_set_explicitly(self) -> None:
        state = PageState(workspace_id=uuid4(), word_minimum=500)
        assert state.word_minimum == 500

    def test_word_limit_set_explicitly(self) -> None:
        state = PageState(workspace_id=uuid4(), word_limit=1500)
        assert state.word_limit == 1500

    def test_word_limit_enforcement_set_true(self) -> None:
        state = PageState(workspace_id=uuid4(), word_limit_enforcement=True)
        assert state.word_limit_enforcement is True

    def test_all_word_fields_set_together(self) -> None:
        state = PageState(
            workspace_id=uuid4(),
            word_minimum=200,
            word_limit=1000,
            word_limit_enforcement=True,
        )
        assert state.word_minimum == 200
        assert state.word_limit == 1000
        assert state.word_limit_enforcement is True
        assert state.word_count_badge is None  # UI element, not set at init
