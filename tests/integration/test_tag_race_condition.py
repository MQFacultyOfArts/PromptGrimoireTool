"""Tests for 2026-03-16 incident: tag/group creation race condition.

Two test classes:

1. TestTagCreationRaceCondition — verifies duplicate names raise
   DuplicateNameError (not IntegrityError).

2. TestGracefulDuplicateHandling — acceptance boundary tests verifying
   that duplicate tag/group names:
   - Raise DuplicateNameError (domain exception)
   - Do NOT propagate IntegrityError through get_session()
   - Do NOT trigger the generic "Database session error" logger

See: docs/postmortems/2026-03-16-investigation.md
"""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from promptgrimoire.config import get_settings

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


async def _make_workspace() -> UUID:
    """Create a minimal course/week/activity and return the template workspace ID."""
    from promptgrimoire.db.activities import create_activity
    from promptgrimoire.db.courses import create_course
    from promptgrimoire.db.weeks import create_week

    code = f"T{uuid4().hex[:6].upper()}"
    course = await create_course(
        code=code,
        name="RaceTest",
        semester="2026-S1",
    )
    week = await create_week(
        course_id=course.id,
        week_number=1,
        title="Week 1",
    )
    activity = await create_activity(
        week_id=week.id,
        title="Race Activity",
    )
    assert activity.template_workspace_id is not None
    return activity.template_workspace_id


class TestTagCreationRaceCondition:
    """Verify duplicate tag/group names raise DuplicateNameError."""

    @pytest.mark.asyncio
    async def test_duplicate_tag_name_raises_domain_error(self) -> None:
        """Sequential duplicate tag name raises DuplicateNameError."""
        from promptgrimoire.db.tags import DuplicateNameError, create_tag

        ws_id = await _make_workspace()
        await create_tag(ws_id, name="test", color="#1f77b4")

        with pytest.raises(DuplicateNameError, match="already exists"):
            await create_tag(ws_id, name="test", color="#ff0000")

    @pytest.mark.asyncio
    async def test_duplicate_group_name_raises_domain_error(
        self,
    ) -> None:
        """Sequential duplicate group name raises DuplicateNameError."""
        from promptgrimoire.db.tags import (
            DuplicateNameError,
            create_tag_group,
        )

        ws_id = await _make_workspace()
        await create_tag_group(ws_id, name="New group")

        with pytest.raises(DuplicateNameError, match="already exists"):
            await create_tag_group(ws_id, name="New group")

    @pytest.mark.asyncio
    async def test_concurrent_tag_creation_one_wins(self) -> None:
        """Concurrent duplicate tags: one succeeds, rest get
        DuplicateNameError.
        """
        from promptgrimoire.db.tags import DuplicateNameError, create_tag

        ws_id = await _make_workspace()

        results = await asyncio.gather(
            create_tag(ws_id, name="race-tag", color="#1f77b4"),
            create_tag(ws_id, name="race-tag", color="#00ff00"),
            return_exceptions=True,
        )

        successes = [r for r in results if not isinstance(r, Exception)]
        failures = [r for r in results if isinstance(r, DuplicateNameError)]

        assert len(successes) == 1
        assert len(failures) == 1

    @pytest.mark.asyncio
    async def test_concurrent_group_creation_one_wins(self) -> None:
        """Concurrent duplicate groups: one succeeds, rest get
        DuplicateNameError.
        """
        from promptgrimoire.db.tags import (
            DuplicateNameError,
            create_tag_group,
        )

        ws_id = await _make_workspace()

        results = await asyncio.gather(
            create_tag_group(ws_id, name="race-group"),
            create_tag_group(ws_id, name="race-group"),
            return_exceptions=True,
        )

        successes = [r for r in results if not isinstance(r, Exception)]
        failures = [r for r in results if isinstance(r, DuplicateNameError)]

        assert len(successes) == 1
        assert len(failures) == 1

    @pytest.mark.asyncio
    async def test_cascade_multiple_concurrent_tags(self) -> None:
        """5 concurrent same-name tags: 1 success, 4 DuplicateNameError."""
        from promptgrimoire.db.tags import DuplicateNameError, create_tag

        ws_id = await _make_workspace()

        results = await asyncio.gather(
            *[create_tag(ws_id, name="Name", color="#1f77b4") for _ in range(5)],
            return_exceptions=True,
        )

        successes = [r for r in results if not isinstance(r, Exception)]
        failures = [r for r in results if isinstance(r, DuplicateNameError)]

        assert len(successes) == 1, f"Expected 1 success, got {len(successes)}"
        assert len(failures) == 4, f"Expected 4 DuplicateNameError, got {len(failures)}"


class TestGracefulDuplicateHandling:
    """Acceptance boundary: no IntegrityError escapes, no generic
    session error log fires.
    """

    @pytest.mark.asyncio
    async def test_duplicate_tag_no_session_error_log(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Duplicate tag does NOT trigger 'Database session error'."""
        from promptgrimoire.db.tags import DuplicateNameError, create_tag

        ws_id = await _make_workspace()
        await create_tag(ws_id, name="dup", color="#1f77b4")

        with (
            caplog.at_level(
                logging.ERROR,
                logger="promptgrimoire.db.engine",
            ),
            pytest.raises(DuplicateNameError),
        ):
            await create_tag(ws_id, name="dup", color="#ff0000")

        assert "Database session error" not in caplog.text

    @pytest.mark.asyncio
    async def test_duplicate_group_no_session_error_log(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Duplicate group does NOT trigger 'Database session error'."""
        from promptgrimoire.db.tags import (
            DuplicateNameError,
            create_tag_group,
        )

        ws_id = await _make_workspace()
        await create_tag_group(ws_id, name="New group")

        with (
            caplog.at_level(
                logging.ERROR,
                logger="promptgrimoire.db.engine",
            ),
            pytest.raises(DuplicateNameError),
        ):
            await create_tag_group(ws_id, name="New group")

        assert "Database session error" not in caplog.text

    @pytest.mark.asyncio
    async def test_concurrent_tags_no_integrity_error(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """5 concurrent same-name tags: no IntegrityError escapes,
        no generic session error log.
        """
        from promptgrimoire.db.tags import DuplicateNameError, create_tag

        ws_id = await _make_workspace()

        integrity_errors: list[IntegrityError] = []
        domain_errors: list[Exception] = []
        successes: list[object] = []

        async def _create_and_track() -> None:
            try:
                tag = await create_tag(
                    ws_id,
                    name="concurrent",
                    color="#1f77b4",
                )
                successes.append(tag)
            except IntegrityError as exc:
                integrity_errors.append(exc)
            except DuplicateNameError as exc:
                domain_errors.append(exc)

        with caplog.at_level(
            logging.ERROR,
            logger="promptgrimoire.db.engine",
        ):
            await asyncio.gather(
                *[_create_and_track() for _ in range(5)],
            )

        assert len(integrity_errors) == 0, (
            f"IntegrityError must not escape; got {len(integrity_errors)}"
        )
        assert len(successes) == 1
        assert len(domain_errors) == 4
        assert "Database session error" not in caplog.text

    @pytest.mark.asyncio
    async def test_concurrent_groups_no_integrity_error(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """5 concurrent "New group" creates: no IntegrityError escapes,
        no generic session error log.
        """
        from promptgrimoire.db.tags import (
            DuplicateNameError,
            create_tag_group,
        )

        ws_id = await _make_workspace()

        integrity_errors: list[IntegrityError] = []
        domain_errors: list[Exception] = []
        successes: list[object] = []

        async def _create_and_track() -> None:
            try:
                group = await create_tag_group(
                    ws_id,
                    name="New group",
                )
                successes.append(group)
            except IntegrityError as exc:
                integrity_errors.append(exc)
            except DuplicateNameError as exc:
                domain_errors.append(exc)

        with caplog.at_level(
            logging.ERROR,
            logger="promptgrimoire.db.engine",
        ):
            await asyncio.gather(
                *[_create_and_track() for _ in range(5)],
            )

        assert len(integrity_errors) == 0, (
            f"IntegrityError must not escape; got {len(integrity_errors)}"
        )
        assert len(successes) == 1
        assert len(domain_errors) == 4
        assert "Database session error" not in caplog.text
