"""Tests for sharing controls: grant_share() validation and PlacementContext resolution.

These tests require a running PostgreSQL instance. Set DEV__TEST_DATABASE_URL.

Tests verify sharing permission grants (AC8.1, AC8.2), tri-state inheritance
(AC8.3-AC8.5), staff bypass (AC8.6), and rejection cases (AC8.7-AC8.9).
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from promptgrimoire.config import get_settings

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


async def _make_sharing_data(
    *,
    course_sharing: bool = True,
    activity_sharing: bool | None = None,
) -> dict:
    """Create hierarchy for sharing tests.

    Returns course, activity, owner (student with clone), recipient,
    staff (instructor), and the cloned workspace_id.
    """
    from promptgrimoire.db.activities import create_activity, update_activity
    from promptgrimoire.db.courses import create_course, enroll_user, update_course
    from promptgrimoire.db.users import create_user
    from promptgrimoire.db.weeks import create_week, publish_week
    from promptgrimoire.db.workspaces import clone_workspace_from_activity

    tag = uuid4().hex[:8]

    course = await create_course(
        code=f"S{tag[:6].upper()}", name="Sharing Test", semester="2026-S1"
    )
    await update_course(course.id, default_allow_sharing=course_sharing)

    week = await create_week(course_id=course.id, week_number=1, title="Week 1")
    await publish_week(week.id)

    activity = await create_activity(week_id=week.id, title="Shared Activity")
    await update_activity(activity.id, allow_sharing=activity_sharing)

    owner = await create_user(
        email=f"owner-{tag}@test.local", display_name=f"Owner {tag}"
    )
    await enroll_user(course_id=course.id, user_id=owner.id, role="student")

    recipient = await create_user(
        email=f"recip-{tag}@test.local", display_name=f"Recipient {tag}"
    )
    await enroll_user(course_id=course.id, user_id=recipient.id, role="student")

    staff = await create_user(
        email=f"instr-{tag}@test.local", display_name=f"Instructor {tag}"
    )
    await enroll_user(course_id=course.id, user_id=staff.id, role="instructor")

    clone, _ = await clone_workspace_from_activity(activity.id, owner.id)

    return {
        "course": course,
        "activity": activity,
        "owner": owner,
        "recipient": recipient,
        "staff": staff,
        "workspace_id": clone.id,
    }


class TestGrantShareSuccess:
    """Tests for successful sharing operations."""

    @pytest.mark.asyncio
    async def test_owner_shares_as_editor(self) -> None:
        """Owner can share workspace as editor when sharing allowed.

        Verifies AC8.1.
        """
        from promptgrimoire.db.acl import grant_share

        data = await _make_sharing_data()
        entry = await grant_share(
            data["workspace_id"],
            data["owner"].id,
            data["recipient"].id,
            "editor",
            sharing_allowed=True,
        )
        assert entry.permission == "editor"
        assert entry.user_id == data["recipient"].id

    @pytest.mark.asyncio
    async def test_owner_shares_as_viewer(self) -> None:
        """Owner can share workspace as viewer when sharing allowed.

        Verifies AC8.2.
        """
        from promptgrimoire.db.acl import grant_share

        data = await _make_sharing_data()
        entry = await grant_share(
            data["workspace_id"],
            data["owner"].id,
            data["recipient"].id,
            "viewer",
            sharing_allowed=True,
        )
        assert entry.permission == "viewer"

    @pytest.mark.asyncio
    async def test_staff_bypasses_sharing_flag(self) -> None:
        """Staff can share regardless of sharing_allowed flag.

        Verifies AC8.6.
        """
        from promptgrimoire.db.acl import grant_share

        data = await _make_sharing_data()
        entry = await grant_share(
            data["workspace_id"],
            data["staff"].id,
            data["recipient"].id,
            "editor",
            sharing_allowed=False,
            grantor_is_staff=True,
        )
        assert entry.permission == "editor"

    @pytest.mark.asyncio
    async def test_share_updates_existing_entry(self) -> None:
        """Re-sharing updates the existing ACLEntry (upsert)."""
        from promptgrimoire.db.acl import grant_share, list_entries_for_workspace

        data = await _make_sharing_data()

        await grant_share(
            data["workspace_id"],
            data["owner"].id,
            data["recipient"].id,
            "editor",
            sharing_allowed=True,
        )
        await grant_share(
            data["workspace_id"],
            data["owner"].id,
            data["recipient"].id,
            "viewer",
            sharing_allowed=True,
        )

        entries = await list_entries_for_workspace(data["workspace_id"])
        recipient_entries = [e for e in entries if e.user_id == data["recipient"].id]
        assert len(recipient_entries) == 1
        assert recipient_entries[0].permission == "viewer"


class TestGrantShareRejection:
    """Tests for sharing rule violations."""

    @pytest.mark.asyncio
    async def test_non_owner_cannot_share(self) -> None:
        """Editor/viewer cannot share workspace.

        Verifies AC8.7.
        """
        from promptgrimoire.db.acl import grant_permission, grant_share

        data = await _make_sharing_data()
        # Give recipient editor access first
        await grant_permission(data["workspace_id"], data["recipient"].id, "editor")

        another_tag = uuid4().hex[:8]
        from promptgrimoire.db.users import create_user

        another = await create_user(
            email=f"another-{another_tag}@test.local",
            display_name=f"Another {another_tag}",
        )

        with pytest.raises(PermissionError, match="only workspace owners can share"):
            await grant_share(
                data["workspace_id"],
                data["recipient"].id,
                another.id,
                "viewer",
                sharing_allowed=True,
            )

    @pytest.mark.asyncio
    async def test_sharing_disabled_blocks_owner(self) -> None:
        """Owner cannot share when sharing is not allowed.

        Verifies AC8.8.
        """
        from promptgrimoire.db.acl import grant_share

        data = await _make_sharing_data()
        with pytest.raises(PermissionError, match="sharing is not allowed"):
            await grant_share(
                data["workspace_id"],
                data["owner"].id,
                data["recipient"].id,
                "editor",
                sharing_allowed=False,
            )

    @pytest.mark.asyncio
    async def test_cannot_grant_owner_permission(self) -> None:
        """Cannot grant owner permission via sharing.

        Verifies AC8.9.
        """
        from promptgrimoire.db.acl import grant_share

        data = await _make_sharing_data()
        with pytest.raises(PermissionError, match="cannot grant owner permission"):
            await grant_share(
                data["workspace_id"],
                data["owner"].id,
                data["recipient"].id,
                "owner",
                sharing_allowed=True,
            )

    @pytest.mark.asyncio
    async def test_cannot_downgrade_owner_via_sharing(self) -> None:
        """Sharing cannot overwrite an existing owner ACLEntry.

        Owner shares to themselves (or staff shares to the owner)
        with a lower permission — must be rejected.
        """
        from promptgrimoire.db.acl import grant_share

        data = await _make_sharing_data()
        with pytest.raises(
            PermissionError, match="cannot modify owner permission via sharing"
        ):
            await grant_share(
                data["workspace_id"],
                data["owner"].id,
                data["owner"].id,
                "viewer",
                sharing_allowed=True,
            )

    @pytest.mark.asyncio
    async def test_staff_cannot_downgrade_owner_via_sharing(self) -> None:
        """Staff bypass does not allow downgrading an owner."""
        from promptgrimoire.db.acl import grant_share

        data = await _make_sharing_data()
        with pytest.raises(
            PermissionError, match="cannot modify owner permission via sharing"
        ):
            await grant_share(
                data["workspace_id"],
                data["staff"].id,
                data["owner"].id,
                "editor",
                sharing_allowed=True,
                grantor_is_staff=True,
            )


class TestSharingInheritance:
    """Tests for allow_sharing tri-state resolution in PlacementContext."""

    @pytest.mark.asyncio
    async def test_activity_inherits_from_course_true(self) -> None:
        """Activity with allow_sharing=None inherits course default (True).

        Verifies AC8.3.
        """
        from promptgrimoire.db.workspaces import get_placement_context

        data = await _make_sharing_data(course_sharing=True, activity_sharing=None)
        ctx = await get_placement_context(data["workspace_id"])
        assert ctx.allow_sharing is True

    @pytest.mark.asyncio
    async def test_activity_inherits_from_course_false(self) -> None:
        """Activity with allow_sharing=None inherits course default (False).

        Verifies AC8.3.
        """
        from promptgrimoire.db.workspaces import get_placement_context

        data = await _make_sharing_data(course_sharing=False, activity_sharing=None)
        ctx = await get_placement_context(data["workspace_id"])
        assert ctx.allow_sharing is False

    @pytest.mark.asyncio
    async def test_activity_overrides_course_true(self) -> None:
        """Activity allow_sharing=True overrides course default=False.

        Verifies AC8.4.
        """
        from promptgrimoire.db.workspaces import get_placement_context

        data = await _make_sharing_data(course_sharing=False, activity_sharing=True)
        ctx = await get_placement_context(data["workspace_id"])
        assert ctx.allow_sharing is True

    @pytest.mark.asyncio
    async def test_activity_overrides_course_false(self) -> None:
        """Activity allow_sharing=False overrides course default=True.

        Verifies AC8.5.
        """
        from promptgrimoire.db.workspaces import get_placement_context

        data = await _make_sharing_data(course_sharing=True, activity_sharing=False)
        ctx = await get_placement_context(data["workspace_id"])
        assert ctx.allow_sharing is False
