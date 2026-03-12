"""Integration tests for the deadline polling worker (real database).

Verifies:
- AC2.1: Expired deadlines fire the callback
- AC2.2: Misfire recovery (server restart) fires for stale deadlines
- AC2.3: Cancelled deadlines (current_deadline=None) are ignored
- Idempotency: Already-locked teams are not reprocessed
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from promptgrimoire.config import get_settings

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


async def _make_wargame_with_team(
    suffix: str,
    *,
    current_deadline: datetime | None,
    round_state: str = "drafting",
) -> tuple[UUID, UUID]:
    """Create a wargame activity with one team, return (activity_id, team_id)."""
    from promptgrimoire.db.courses import create_course
    from promptgrimoire.db.engine import get_session
    from promptgrimoire.db.models import Activity, WargameTeam
    from promptgrimoire.db.weeks import create_week

    code = f"DW{uuid4().hex[:6].upper()}"
    course = await create_course(
        code=code, name=f"Deadline {suffix}", semester="2026-S1"
    )
    week = await create_week(course_id=course.id, week_number=1, title="Week 1")

    async with get_session() as session:
        activity = Activity(
            week_id=week.id,
            type="wargame",
            title=f"Deadline {suffix}",
        )
        session.add(activity)
        await session.flush()
        await session.refresh(activity)

        team = WargameTeam(
            activity_id=activity.id,
            codename=f"team-{uuid4().hex[:6]}",
            current_deadline=current_deadline,
            round_state=round_state,
        )
        session.add(team)
        await session.flush()
        await session.refresh(team)

        return activity.id, team.id


class TestDeadlineWorkerIntegration:
    """Integration tests for check_expired_deadlines against a real database."""

    @pytest.mark.asyncio
    async def test_ac2_1_fires_for_expired_deadline(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AC2.1: Expired deadline fires the callback."""
        past = datetime.now(UTC) - timedelta(minutes=1)
        activity_id, _team_id = await _make_wargame_with_team(
            "ac2.1", current_deadline=past
        )

        fired: list[UUID] = []

        async def mock_on_deadline_fired(aid: UUID) -> None:
            fired.append(aid)

        monkeypatch.setattr(
            "promptgrimoire.db.wargames.on_deadline_fired",
            mock_on_deadline_fired,
        )

        from promptgrimoire.deadline_worker import check_expired_deadlines

        result = await check_expired_deadlines()

        assert result >= 1
        assert activity_id in fired

    @pytest.mark.asyncio
    async def test_ac2_2_misfire_recovery(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AC2.2: Deadline from 1 hour ago still fires (server was down)."""
        stale = datetime.now(UTC) - timedelta(hours=1)
        activity_id, _team_id = await _make_wargame_with_team(
            "ac2.2", current_deadline=stale
        )

        fired: list[UUID] = []

        async def mock_on_deadline_fired(aid: UUID) -> None:
            fired.append(aid)

        monkeypatch.setattr(
            "promptgrimoire.db.wargames.on_deadline_fired",
            mock_on_deadline_fired,
        )

        from promptgrimoire.deadline_worker import check_expired_deadlines

        result = await check_expired_deadlines()

        assert result >= 1
        assert activity_id in fired

    @pytest.mark.asyncio
    async def test_ac2_3_cancelled_deadline_ignored(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AC2.3: current_deadline=None means no callback fires."""
        activity_id, _team_id = await _make_wargame_with_team(
            "ac2.3", current_deadline=None
        )

        fired: list[UUID] = []

        async def mock_on_deadline_fired(aid: UUID) -> None:
            fired.append(aid)

        monkeypatch.setattr(
            "promptgrimoire.db.wargames.on_deadline_fired",
            mock_on_deadline_fired,
        )

        from promptgrimoire.deadline_worker import check_expired_deadlines

        await check_expired_deadlines()

        assert activity_id not in fired

    @pytest.mark.asyncio
    async def test_idempotency_locked_teams_skipped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Already-locked teams are not reprocessed on next poll."""
        past = datetime.now(UTC) - timedelta(minutes=1)
        activity_id, _team_id = await _make_wargame_with_team(
            "idempotent",
            current_deadline=past,
            round_state="locked",
        )

        fired: list[UUID] = []

        async def mock_on_deadline_fired(aid: UUID) -> None:
            fired.append(aid)

        monkeypatch.setattr(
            "promptgrimoire.db.wargames.on_deadline_fired",
            mock_on_deadline_fired,
        )

        from promptgrimoire.deadline_worker import check_expired_deadlines

        await check_expired_deadlines()

        # The locked activity should not appear in fired list
        assert activity_id not in fired
