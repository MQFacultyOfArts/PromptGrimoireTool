"""Unit tests for word count model fields on Activity and Course.

Pure model instantiation tests -- no database required.
"""

from __future__ import annotations

from uuid import uuid4

from promptgrimoire.db.models import Activity, Course

_WEEK_ID = uuid4()
_TEMPLATE_WS_ID = uuid4()


def _make_activity(**overrides: object) -> Activity:
    """Create an Activity with required fields pre-filled."""
    defaults: dict[str, object] = {
        "week_id": _WEEK_ID,
        "template_workspace_id": _TEMPLATE_WS_ID,
        "title": "Test Activity",
    }
    defaults.update(overrides)
    return Activity(**defaults)  # type: ignore[arg-type]


def _make_course(**overrides: object) -> Course:
    """Create a Course with required fields pre-filled."""
    defaults: dict[str, object] = {
        "code": "TEST101",
        "name": "Test Course",
        "semester": "2026S1",
    }
    defaults.update(overrides)
    return Course(**defaults)  # type: ignore[arg-type]


class TestActivityWordCountFields:
    """Tests for word count fields on the Activity model."""

    def test_defaults_to_none(self) -> None:
        """AC2.6: All word count fields default to None (no limits)."""
        activity = _make_activity()
        assert activity.word_minimum is None
        assert activity.word_limit is None
        assert activity.word_limit_enforcement is None

    def test_accepts_positive_integers(self) -> None:
        """AC2.1: word_minimum and word_limit accept positive integers."""
        activity = _make_activity(word_minimum=500, word_limit=1000)
        assert activity.word_minimum == 500
        assert activity.word_limit == 1000

    def test_enforcement_tri_state(self) -> None:
        """AC2.2: word_limit_enforcement accepts True, False, or None."""
        for value in (True, False, None):
            activity = _make_activity(word_limit_enforcement=value)
            assert activity.word_limit_enforcement is value


class TestCourseWordCountFields:
    """Tests for word count fields on the Course model."""

    def test_default_enforcement_is_false(self) -> None:
        """AC2.3: Course default_word_limit_enforcement defaults to False."""
        course = _make_course()
        assert course.default_word_limit_enforcement is False

    def test_enforcement_can_be_set_true(self) -> None:
        """Course default_word_limit_enforcement can be set to True."""
        course = _make_course(default_word_limit_enforcement=True)
        assert course.default_word_limit_enforcement is True
