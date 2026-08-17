"""Unit tests for pure (non-DB) helpers extracted from cli_loadtest.py.

_build_course_students_map and _report_seeding_progress were pulled out of
_seed_acl_shares and _seed_student_workspaces during the ty-bump complexity
cleanup (both functions were flagged over the complexity-15 threshold).
Neither touches the database, so these are ordinary unit tests rather than
the DB-backed integration tests the other extracted helpers need.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from promptgrimoire.cli_loadtest import (
    _build_course_students_map,
    _report_seeding_progress,
)
from promptgrimoire.db.models import Course, User

if TYPE_CHECKING:
    import pytest


def _make_user(name: str) -> User:
    """An unsaved User instance -- construction only, no DB I/O."""
    return User(id=uuid4(), email=f"{name}@test.local", display_name=name)


def _make_course(code: str) -> Course:
    """An unsaved Course instance -- construction only, no DB I/O."""
    return Course(id=uuid4(), code=code, name=code, semester="2026-S1")


class TestBuildCourseStudentsMap:
    """Maps course_id -> enrolled student Users from the raw enrollment data."""

    def test_groups_students_by_every_enrolled_course(self) -> None:
        alice, bob = _make_user("alice"), _make_user("bob")
        course_a, course_b = _make_course("A"), _make_course("B")

        result = _build_course_students_map(
            all_students={"alice@test.local": alice, "bob@test.local": bob},
            student_courses={
                "alice@test.local": ["A", "B"],
                "bob@test.local": ["A"],
            },
            courses={"A": course_a, "B": course_b},
        )

        assert result[course_a.id] == [alice, bob]
        assert result[course_b.id] == [alice]

    def test_course_code_not_in_courses_mapping_is_skipped(self) -> None:
        """A stale/unknown course code must not raise or appear in the result."""
        alice = _make_user("alice")

        result = _build_course_students_map(
            all_students={"alice@test.local": alice},
            student_courses={"alice@test.local": ["UNKNOWN"]},
            courses={},
        )

        assert result == {}

    def test_no_students_produces_empty_map(self) -> None:
        result = _build_course_students_map(
            all_students={}, student_courses={}, courses={}
        )

        assert result == {}


class TestReportSeedingProgress:
    """Prints a progress line on every 100th student and the final student."""

    def test_prints_on_hundredth_student(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import promptgrimoire.cli_loadtest as loadtest_mod

        captured: list[str] = []
        monkeypatch.setattr(loadtest_mod.console, "print", captured.append)

        _report_seeding_progress(99, 250, activity_ws_count=10, loose_ws_count=5)

        assert len(captured) == 1
        assert "100/250" in captured[0]
        assert "10 activity ws" in captured[0]
        assert "5 loose ws" in captured[0]

    def test_prints_on_final_student_even_off_the_hundred_boundary(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import promptgrimoire.cli_loadtest as loadtest_mod

        captured: list[str] = []
        monkeypatch.setattr(loadtest_mod.console, "print", captured.append)

        _report_seeding_progress(42, 43, activity_ws_count=3, loose_ws_count=1)

        assert len(captured) == 1
        assert "43/43" in captured[0]

    def test_silent_between_boundaries(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import promptgrimoire.cli_loadtest as loadtest_mod

        captured: list[str] = []
        monkeypatch.setattr(loadtest_mod.console, "print", captured.append)

        _report_seeding_progress(5, 250, activity_ws_count=1, loose_ws_count=0)

        assert captured == []
