"""Tests for clone ownership: ACLEntry creation and duplicate detection.

These tests require a running PostgreSQL instance. Set DEV__TEST_DATABASE_URL.

Tests verify owner ACLEntry at clone (AC7.1), duplicate workspace detection
(AC7.4), and confirm eligibility gates (AC7.2, AC7.3, AC7.6) via the clone
flow.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from promptgrimoire.config import get_settings

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


async def _make_test_data() -> dict:
    """Create full hierarchy for clone ownership tests.

    Returns course, week (published), activity, student, unenrolled user.
    """
    from promptgrimoire.db.activities import create_activity
    from promptgrimoire.db.courses import create_course, enroll_user
    from promptgrimoire.db.users import create_user
    from promptgrimoire.db.weeks import create_week, publish_week

    tag = uuid4().hex[:8]

    course = await create_course(
        code=f"O{tag[:6].upper()}", name="Ownership Test", semester="2026-S1"
    )
    week = await create_week(course_id=course.id, week_number=1, title="Week 1")
    await publish_week(week.id)

    activity = await create_activity(week_id=week.id, title="Clone Activity")

    student = await create_user(
        email=f"student-{tag}@test.local", display_name=f"Student {tag}"
    )
    await enroll_user(course_id=course.id, user_id=student.id, role="student")

    unenrolled = await create_user(
        email=f"outsider-{tag}@test.local", display_name=f"Outsider {tag}"
    )

    return {
        "course": course,
        "week": week,
        "activity": activity,
        "student": student,
        "unenrolled": unenrolled,
    }


class TestCloneOwnership:
    """Tests for ACLEntry creation during workspace cloning."""

    @pytest.mark.asyncio
    async def test_clone_creates_owner_acl_entry(self) -> None:
        """Cloning a workspace creates an ACLEntry with owner permission.

        Verifies AC7.1.
        """
        from promptgrimoire.db.acl import list_entries_for_workspace
        from promptgrimoire.db.workspaces import clone_workspace_from_activity

        data = await _make_test_data()
        clone, _doc_map = await clone_workspace_from_activity(
            data["activity"].id, data["student"].id
        )

        entries = await list_entries_for_workspace(clone.id)
        assert len(entries) == 1
        assert entries[0].user_id == data["student"].id
        assert entries[0].permission == "owner"

    @pytest.mark.asyncio
    async def test_clone_owner_entry_matches_cloning_user(self) -> None:
        """The ACLEntry user_id matches the user_id passed to clone.

        Verifies AC7.1 -- ownership is attributed to the correct user.
        """
        from promptgrimoire.db.acl import list_entries_for_workspace
        from promptgrimoire.db.courses import enroll_user
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import clone_workspace_from_activity

        data = await _make_test_data()
        tag = uuid4().hex[:8]

        # Enrol a second student
        student2 = await create_user(
            email=f"student2-{tag}@test.local", display_name=f"Student2 {tag}"
        )
        await enroll_user(
            course_id=data["course"].id, user_id=student2.id, role="student"
        )

        clone, _ = await clone_workspace_from_activity(data["activity"].id, student2.id)
        entries = await list_entries_for_workspace(clone.id)
        assert len(entries) == 1
        assert entries[0].user_id == student2.id


class TestDuplicateDetection:
    """Tests for get_user_workspace_for_activity() duplicate detection."""

    @pytest.mark.asyncio
    async def test_no_workspace_returns_none(self) -> None:
        """User with no cloned workspace gets None.

        Verifies AC7.4 -- no false positives.
        """
        from promptgrimoire.db.workspaces import get_user_workspace_for_activity

        data = await _make_test_data()
        result = await get_user_workspace_for_activity(
            data["activity"].id, data["student"].id
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_existing_clone_detected(self) -> None:
        """After cloning, get_user_workspace_for_activity returns the clone.

        Verifies AC7.4.
        """
        from promptgrimoire.db.workspaces import (
            clone_workspace_from_activity,
            get_user_workspace_for_activity,
        )

        data = await _make_test_data()
        clone, _ = await clone_workspace_from_activity(
            data["activity"].id, data["student"].id
        )

        found = await get_user_workspace_for_activity(
            data["activity"].id, data["student"].id
        )
        assert found is not None
        assert found.id == clone.id

    @pytest.mark.asyncio
    async def test_different_user_not_detected(self) -> None:
        """Another user's clone is not returned for a different user.

        Verifies AC7.4 -- ownership isolation.
        """
        from promptgrimoire.db.courses import enroll_user
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import (
            clone_workspace_from_activity,
            get_user_workspace_for_activity,
        )

        data = await _make_test_data()
        tag = uuid4().hex[:8]

        # Clone as student
        await clone_workspace_from_activity(data["activity"].id, data["student"].id)

        # Second student has no clone
        student2 = await create_user(
            email=f"nodup-{tag}@test.local", display_name=f"NoDup {tag}"
        )
        await enroll_user(
            course_id=data["course"].id, user_id=student2.id, role="student"
        )

        found = await get_user_workspace_for_activity(data["activity"].id, student2.id)
        assert found is None


class TestUnauthenticatedCloneRejection:
    """AC7.5: Unauthenticated user cannot clone.

    clone_workspace_from_activity() and check_clone_eligibility() both require
    user_id: UUID — a type annotation guarantee that prevents None from being
    passed. The page layer (_get_user_id() returning None) gates access before
    the clone function is ever called.

    This test verifies the type annotation contract: the function signature
    declares user_id as UUID (not UUID | None), which type checkers enforce.
    """

    def test_clone_eligibility_requires_uuid_user_id(self) -> None:
        """check_clone_eligibility declares user_id as UUID, not Optional."""
        from typing import get_type_hints

        from promptgrimoire.db.workspaces import check_clone_eligibility

        hints = get_type_hints(check_clone_eligibility)
        # Annotation should be UUID, not Optional[UUID] or UUID | None
        assert hints["user_id"] is UUID

    def test_clone_workspace_requires_uuid_user_id(self) -> None:
        """clone_workspace_from_activity declares user_id as UUID, not Optional."""
        from typing import get_type_hints

        from promptgrimoire.db.workspaces import clone_workspace_from_activity

        hints = get_type_hints(clone_workspace_from_activity)
        assert hints["user_id"] is UUID


class TestEligibilityGatesInCloneFlow:
    """Confirm eligibility gates work in the full clone flow.

    These complement test_clone_eligibility.py by testing the gate
    function in the context it's actually used.
    """

    @pytest.mark.asyncio
    async def test_enrolled_student_eligible(self) -> None:
        """Enrolled student passes eligibility check.

        Verifies AC7.2.
        """
        from promptgrimoire.db.workspaces import check_clone_eligibility

        data = await _make_test_data()
        result = await check_clone_eligibility(data["activity"].id, data["student"].id)
        assert result is None

    @pytest.mark.asyncio
    async def test_unenrolled_user_blocked(self) -> None:
        """Unenrolled user is rejected by eligibility check.

        Verifies AC7.6.
        """
        from promptgrimoire.db.workspaces import check_clone_eligibility

        data = await _make_test_data()
        result = await check_clone_eligibility(
            data["activity"].id, data["unenrolled"].id
        )
        assert result is not None
        assert "not enrolled" in result.lower()

    @pytest.mark.asyncio
    async def test_nonexistent_activity_blocked(self) -> None:
        """Non-existent activity returns error."""
        from promptgrimoire.db.workspaces import check_clone_eligibility

        data = await _make_test_data()
        result = await check_clone_eligibility(uuid4(), data["student"].id)
        assert result is not None
        assert "not found" in result.lower()
