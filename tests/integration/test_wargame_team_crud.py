"""Integration tests for wargame team CRUD services."""

from __future__ import annotations

from uuid import uuid4

import pytest

from promptgrimoire.config import get_settings
from promptgrimoire.db.models import Activity, Course, Week

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


async def _make_course_and_week(suffix: str) -> tuple[Course, Week]:
    """Create a unique course/week pair for team CRUD tests."""
    from promptgrimoire.db.courses import create_course
    from promptgrimoire.db.weeks import create_week

    code = f"WT{uuid4().hex[:6].upper()}"
    course = await create_course(
        code=code,
        name=f"Wargame Team {suffix}",
        semester="2026-S1",
    )
    week = await create_week(course_id=course.id, week_number=1, title="Week 1")
    return course, week


async def _make_wargame_activity(suffix: str) -> Activity:
    """Create a persisted wargame activity for one CRUD test."""
    from promptgrimoire.db.engine import get_session

    _, week = await _make_course_and_week(suffix)

    async with get_session() as session:
        activity = Activity(
            week_id=week.id,
            type="wargame",
            title=f"Wargame {suffix}",
        )
        session.add(activity)
        await session.flush()
        await session.refresh(activity)
        return activity


class TestCreateAndGetTeam:
    """Service-level tests for create_team and get_team."""

    @pytest.mark.asyncio
    async def test_create_team_persists_generated_codename_and_get_team_round_trips(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """AC3.1: create_team persists through the public service boundary."""
        from promptgrimoire.db.wargames import create_team, get_team

        activity = await _make_wargame_activity("create-team")
        monkeypatch.setattr(
            "promptgrimoire.db.wargames.generate_codename",
            lambda _existing: "RED-FOX",
        )

        created = await create_team(activity.id)
        fetched = await get_team(created.id)

        assert created.id is not None
        assert created.activity_id == activity.id
        assert created.codename == "RED-FOX"
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.activity_id == activity.id
        assert fetched.codename == "RED-FOX"

    @pytest.mark.asyncio
    async def test_get_team_returns_none_for_missing_team(self) -> None:
        """Missing teams return None rather than raising."""
        from promptgrimoire.db.wargames import get_team

        assert await get_team(uuid4()) is None
