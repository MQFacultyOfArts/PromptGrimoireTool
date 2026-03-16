"""Tests for 2026-03-16 incident: tag/group creation race condition.

Two test classes:

1. TestTagCreationRaceCondition — reproduces the current broken behaviour.
   These document the failure mode and will be updated once the fix lands.

2. TestGracefulDuplicateHandling — target-state tests defining what "fixed"
   looks like. These currently FAIL (xfail) because the fix hasn't been
   implemented yet. The acceptance criterion is:
   - Duplicate tag/group name raises DuplicateNameError (domain exception)
   - IntegrityError does NOT propagate through get_session()
   - The generic "Database session error" logger at engine.py:300 does NOT fire

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
    course = await create_course(code=code, name="RaceTest", semester="2026-S1")
    week = await create_week(course_id=course.id, week_number=1, title="Week 1")
    activity = await create_activity(week_id=week.id, title="Race Activity")
    assert activity.template_workspace_id is not None
    return activity.template_workspace_id


class TestTagCreationRaceCondition:
    """Reproduce the 2026-03-16 incident: concurrent duplicate tag INSERTs."""

    @pytest.mark.asyncio
    async def test_duplicate_tag_name_raises_integrity_error(self) -> None:
        """Two sequential create_tag calls with the same name hit the
        unique constraint. The IntegrityError propagates through
        get_session() which logs "Database session error" before
        re-raising.
        """
        from promptgrimoire.db.tags import create_tag

        ws_id = await _make_workspace()

        tag1 = await create_tag(ws_id, name="test", color="#1f77b4")
        assert tag1.name == "test"

        with pytest.raises(IntegrityError, match="uq_tag_workspace_name"):
            await create_tag(ws_id, name="test", color="#ff0000")

    @pytest.mark.asyncio
    async def test_duplicate_group_name_raises_integrity_error(
        self,
    ) -> None:
        """Two create_tag_group calls with same name hit the unique
        constraint. Reproduces the "New group" hardcode bug.
        """
        from promptgrimoire.db.tags import create_tag_group

        ws_id = await _make_workspace()

        group1 = await create_tag_group(ws_id, name="New group")
        assert group1.name == "New group"

        with pytest.raises(
            IntegrityError,
            match="uq_tag_group_workspace_name",
        ):
            await create_tag_group(ws_id, name="New group")

    @pytest.mark.asyncio
    async def test_concurrent_tag_creation_race(self) -> None:
        """Concurrent create_tag calls with same name produce at least
        one IntegrityError.
        """
        from promptgrimoire.db.tags import create_tag

        ws_id = await _make_workspace()

        errors: list[Exception] = []

        async def _create_and_catch() -> None:
            try:
                await create_tag(
                    ws_id,
                    name="race-tag",
                    color="#1f77b4",
                )
            except IntegrityError as exc:
                errors.append(exc)

        await asyncio.gather(
            _create_and_catch(),
            _create_and_catch(),
        )

        assert len(errors) >= 1, (
            "Expected at least one IntegrityError from concurrent duplicate INSERT"
        )
        assert "uq_tag_workspace_name" in str(errors[0])

    @pytest.mark.asyncio
    async def test_concurrent_group_creation_race(self) -> None:
        """Concurrent create_tag_group with "New group" produces at
        least one IntegrityError.
        """
        from promptgrimoire.db.tags import create_tag_group

        ws_id = await _make_workspace()

        errors: list[Exception] = []

        async def _create_and_catch() -> None:
            try:
                await create_tag_group(ws_id, name="New group")
            except IntegrityError as exc:
                errors.append(exc)

        await asyncio.gather(
            _create_and_catch(),
            _create_and_catch(),
        )

        assert len(errors) >= 1, (
            "Expected at least one IntegrityError from concurrent"
            " duplicate group INSERT"
        )
        assert "uq_tag_group_workspace_name" in str(errors[0])

    @pytest.mark.asyncio
    async def test_cascade_effect_multiple_concurrent_tags(
        self,
    ) -> None:
        """5 concurrent create_tag calls with same name produce
        exactly 1 success and 4 IntegrityErrors.
        """
        from promptgrimoire.db.tags import create_tag

        ws_id = await _make_workspace()

        errors: list[Exception] = []
        successes: list[object] = []

        async def _create_and_track() -> None:
            try:
                tag = await create_tag(
                    ws_id,
                    name="Name",
                    color="#1f77b4",
                )
                successes.append(tag)
            except IntegrityError as exc:
                errors.append(exc)

        await asyncio.gather(
            *[_create_and_track() for _ in range(5)],
        )

        assert len(successes) == 1, f"Expected 1 success, got {len(successes)}"
        assert len(errors) == 4, f"Expected 4 IntegrityErrors, got {len(errors)}"


class TestGracefulDuplicateHandling:
    """Target-state tests: what "fixed" looks like.

    Acceptance criteria:
    1. Duplicate tag/group name raises DuplicateNameError (domain exception)
    2. IntegrityError does NOT propagate through get_session()
    3. The generic "Database session error" logger at engine.py:300 does NOT fire
    4. Works for both tags and groups (including concurrent "New group")

    These tests are xfail until the fix is implemented.
    """

    @pytest.mark.asyncio
    @pytest.mark.xfail(
        reason="Fix not implemented: create_tag raises IntegrityError",
        raises=IntegrityError,
        strict=True,
    )
    async def test_duplicate_tag_raises_domain_error(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Duplicate tag name raises DuplicateNameError and does NOT
        trigger the generic session error logger.
        """
        from promptgrimoire.db.tags import DuplicateNameError, create_tag

        ws_id = await _make_workspace()
        await create_tag(ws_id, name="dup", color="#1f77b4")

        with (
            caplog.at_level(logging.ERROR, logger="promptgrimoire.db.engine"),
            pytest.raises(DuplicateNameError),
        ):
            await create_tag(ws_id, name="dup", color="#ff0000")

        assert "Database session error" not in caplog.text, (
            "DuplicateNameError must not trigger the generic session"
            " error logger (engine.py:300)"
        )

    @pytest.mark.asyncio
    @pytest.mark.xfail(
        reason="Fix not implemented: create_tag_group raises IntegrityError",
        raises=(IntegrityError, ImportError),
        strict=True,
    )
    async def test_duplicate_group_raises_domain_error(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Duplicate group name raises DuplicateNameError and does NOT
        trigger the generic session error logger.
        """
        from promptgrimoire.db.tags import (
            DuplicateNameError,
            create_tag_group,
        )

        ws_id = await _make_workspace()
        await create_tag_group(ws_id, name="New group")

        with (
            caplog.at_level(logging.ERROR, logger="promptgrimoire.db.engine"),
            pytest.raises(DuplicateNameError),
        ):
            await create_tag_group(ws_id, name="New group")

        assert "Database session error" not in caplog.text, (
            "DuplicateNameError must not trigger the generic session"
            " error logger (engine.py:300)"
        )

    @pytest.mark.asyncio
    @pytest.mark.xfail(
        reason="Fix not implemented: concurrent creates raise IntegrityError",
        raises=AssertionError,
        strict=True,
    )
    async def test_concurrent_tag_duplicates_no_integrity_error(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """5 concurrent same-name tag creates: exactly 1 succeeds,
        rest raise DuplicateNameError. No IntegrityError escapes.
        Generic session error logger does NOT fire.
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
            f"IntegrityError must not escape to get_session(); "
            f"got {len(integrity_errors)}"
        )
        assert len(successes) == 1
        assert len(domain_errors) == 4
        assert "Database session error" not in caplog.text

    @pytest.mark.asyncio
    @pytest.mark.xfail(
        reason="Fix not implemented: concurrent group creates raise IntegrityError",
        raises=AssertionError,
        strict=True,
    )
    async def test_concurrent_group_duplicates_no_integrity_error(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """5 concurrent "New group" creates: exactly 1 succeeds,
        rest raise DuplicateNameError. No IntegrityError escapes.
        Generic session error logger does NOT fire.

        Reproduces the worst offender from the incident: workspace
        ba1a8a16 had 8 "New group" collisions.
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
            f"IntegrityError must not escape to get_session(); "
            f"got {len(integrity_errors)}"
        )
        assert len(successes) == 1
        assert len(domain_errors) == 4
        assert "Database session error" not in caplog.text
