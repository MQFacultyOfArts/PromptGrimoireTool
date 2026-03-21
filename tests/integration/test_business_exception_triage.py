"""Integration tests for get_session() BusinessLogicError triage.

Verifies that domain exceptions raised inside get_session() produce
WARNING-level "Business logic error" log events (not ERROR-level
"Database session error" events).

AC2.6: grant_share() with sharing_allowed=False
AC2.7: delete_workspace() by non-owner
"""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest

from promptgrimoire.config import get_settings
from promptgrimoire.db.exceptions import OwnershipError, SharePermissionError

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


async def _make_sharing_data() -> dict:
    """Create owner, recipient, and workspace with sharing disabled."""
    from promptgrimoire.db.activities import create_activity
    from promptgrimoire.db.courses import (
        create_course,
        enroll_user,
        update_course,
    )
    from promptgrimoire.db.users import create_user
    from promptgrimoire.db.weeks import create_week, publish_week
    from promptgrimoire.db.workspaces import clone_workspace_from_activity

    tag = uuid4().hex[:8]

    course = await create_course(
        code=f"B{tag[:6].upper()}",
        name="Triage Test",
        semester="2026-S1",
    )
    await update_course(course.id, default_allow_sharing=False)

    week = await create_week(course_id=course.id, week_number=1, title="Week 1")
    await publish_week(week.id)

    activity = await create_activity(week_id=week.id, title="Triage Activity")

    owner = await create_user(
        email=f"owner-{tag}@test.local",
        display_name=f"Owner {tag}",
    )
    await enroll_user(course_id=course.id, user_id=owner.id, role="student")

    recipient = await create_user(
        email=f"recip-{tag}@test.local",
        display_name=f"Recipient {tag}",
    )
    await enroll_user(course_id=course.id, user_id=recipient.id, role="student")

    clone, _ = await clone_workspace_from_activity(activity.id, owner.id)

    return {
        "owner": owner,
        "recipient": recipient,
        "workspace_id": clone.id,
    }


class TestBusinessExceptionTriage:
    """Verify get_session() triages domain exceptions correctly."""

    @pytest.mark.asyncio
    async def test_grant_share_rejected_logs_business_error(self) -> None:
        """grant_share with sharing disabled produces WARNING (AC2.6).

        Must call logger.warning with "Business logic error",
        NOT logger.exception with "Database session error".
        """
        from promptgrimoire.db.acl import grant_share

        data = await _make_sharing_data()

        with (
            patch("promptgrimoire.db.engine.logger") as mock_logger,
            pytest.raises(SharePermissionError),
        ):
            await grant_share(
                data["workspace_id"],
                data["owner"].id,
                data["recipient"].id,
                "editor",
                sharing_allowed=False,
            )

        mock_logger.warning.assert_called_once()
        event = mock_logger.warning.call_args[0][0]
        assert event == "Business logic error, rolling back transaction"
        assert mock_logger.warning.call_args[1]["exc_class"] == "SharePermissionError"
        mock_logger.exception.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_workspace_non_owner_logs_business_error(
        self,
    ) -> None:
        """delete_workspace by non-owner produces WARNING (AC2.7).

        Must call logger.warning with "Business logic error",
        NOT logger.exception with "Database session error".
        """
        from promptgrimoire.db.workspaces import delete_workspace

        data = await _make_sharing_data()

        with (
            patch("promptgrimoire.db.engine.logger") as mock_logger,
            pytest.raises(OwnershipError),
        ):
            await delete_workspace(
                data["workspace_id"],
                user_id=data["recipient"].id,
            )

        mock_logger.warning.assert_called_once()
        event = mock_logger.warning.call_args[0][0]
        assert event == "Business logic error, rolling back transaction"
        assert mock_logger.warning.call_args[1]["exc_class"] == "OwnershipError"
        mock_logger.exception.assert_not_called()
