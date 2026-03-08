"""Integration tests for wargame team ACL services."""

from __future__ import annotations

from uuid import uuid4

import pytest

from promptgrimoire.config import get_settings
from promptgrimoire.db.models import ACLEntry, Activity, Course, User, WargameTeam, Week

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


async def _make_course_and_week(suffix: str) -> tuple[Course, Week]:
    """Create a unique course/week pair for team ACL tests."""
    from promptgrimoire.db.courses import create_course
    from promptgrimoire.db.weeks import create_week

    code = f"WA{uuid4().hex[:6].upper()}"
    course = await create_course(
        code=code,
        name=f"Wargame ACL {suffix}",
        semester="2026-S1",
    )
    week = await create_week(course_id=course.id, week_number=1, title="Week 1")
    return course, week


async def _make_wargame_activity(suffix: str) -> Activity:
    """Create a persisted wargame activity for one ACL test."""
    from promptgrimoire.db.engine import get_session

    _, week = await _make_course_and_week(suffix)

    async with get_session() as session:
        activity = Activity(
            week_id=week.id,
            type="wargame",
            title=f"Wargame ACL {suffix}",
        )
        session.add(activity)
        await session.flush()
        await session.refresh(activity)
        return activity


async def _make_team(
    suffix: str,
    codename: str = "ALPHA",
) -> tuple[Activity, WargameTeam]:
    """Create a persisted team for one ACL test."""
    from promptgrimoire.db.wargames import create_team

    activity = await _make_wargame_activity(suffix)
    team = await create_team(activity.id, codename=codename)
    return activity, team


async def _make_user(email_prefix: str, display_name: str) -> User:
    """Create a unique persisted user through the public service."""
    from promptgrimoire.db.users import create_user

    return await create_user(
        email=f"{email_prefix}-{uuid4().hex[:8]}@test.local",
        display_name=display_name,
    )


class TestResolveTeamPermission:
    """Service-level tests for resolve_team_permission."""

    @pytest.mark.asyncio
    async def test_resolve_team_permission_returns_none_when_no_team_acl_entry_exists(
        self,
    ) -> None:
        """AC4.2: missing team ACL entries resolve to None."""
        from promptgrimoire.db.wargames import resolve_team_permission

        _, team = await _make_team("resolve-none")
        user = await _make_user("resolve-none", "Missing Member")

        assert await resolve_team_permission(team.id, user.id) is None

    @pytest.mark.asyncio
    async def test_resolve_team_permission_returns_exact_stored_permission(
        self,
    ) -> None:
        """AC4.2: exact stored team permission is returned unchanged."""
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.wargames import resolve_team_permission

        _, team = await _make_team("resolve-editor")
        user = await _make_user("resolve-editor", "Editor Member")

        async with get_session() as session:
            entry = ACLEntry(
                workspace_id=None,
                team_id=team.id,
                user_id=user.id,
                permission="editor",
            )
            session.add(entry)
            await session.flush()

        assert await resolve_team_permission(team.id, user.id) == "editor"

    @pytest.mark.asyncio
    async def test_resolve_team_permission_owner_permission_round_trips_unchanged(
        self,
    ) -> None:
        """Direct owner ACL rows prove the service uses real permission names."""
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.wargames import resolve_team_permission

        _, team = await _make_team("resolve-owner")
        user = await _make_user("resolve-owner", "Owner Member")

        async with get_session() as session:
            entry = ACLEntry(
                workspace_id=None,
                team_id=team.id,
                user_id=user.id,
                permission="owner",
            )
            session.add(entry)
            await session.flush()

        assert await resolve_team_permission(team.id, user.id) == "owner"


class TestListTeamMembers:
    """Service-level tests for list_team_members."""

    @pytest.mark.asyncio
    async def test_list_team_members_returns_deterministic_member_order(
        self,
    ) -> None:
        """AC4.3: members are ordered by editability, level, name, then email."""
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.wargames import list_team_members

        _, team = await _make_team("list-members")
        owner = await _make_user("list-owner", "Alpha User")
        editor = await _make_user("list-editor", "Zulu User")
        viewer_a = await _make_user("list-viewer-a", "Beta User")
        viewer_b = await _make_user("list-viewer-b", "Beta User")

        async with get_session() as session:
            session.add(
                ACLEntry(
                    workspace_id=None,
                    team_id=team.id,
                    user_id=viewer_b.id,
                    permission="viewer",
                )
            )
            session.add(
                ACLEntry(
                    workspace_id=None,
                    team_id=team.id,
                    user_id=editor.id,
                    permission="editor",
                )
            )
            session.add(
                ACLEntry(
                    workspace_id=None,
                    team_id=team.id,
                    user_id=owner.id,
                    permission="owner",
                )
            )
            session.add(
                ACLEntry(
                    workspace_id=None,
                    team_id=team.id,
                    user_id=viewer_a.id,
                    permission="viewer",
                )
            )
            await session.flush()

        members = await list_team_members(team.id)

        assert [(user.display_name, permission) for user, permission in members] == [
            ("Alpha User", "owner"),
            ("Zulu User", "editor"),
            ("Beta User", "viewer"),
            ("Beta User", "viewer"),
        ]
        assert [permission for _, permission in members] == [
            "owner",
            "editor",
            "viewer",
            "viewer",
        ]
        assert members[2][0].email < members[3][0].email
