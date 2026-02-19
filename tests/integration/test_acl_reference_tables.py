"""Tests for ACL reference table seed data and constraints.

These tests require a running PostgreSQL instance. Set DEV__TEST_DATABASE_URL.

Verifies that the Alembic migration correctly creates and seeds the Permission
and CourseRoleRef (course_role) reference tables with CHECK and UNIQUE
constraints.

Acceptance Criteria:
- AC1.1: Permission table has owner/30, editor/20, peer/15, viewer/10
- AC1.2: CourseRoleRef has coordinator/40, instructor/30, tutor/20,
  student/10
- AC1.3: Seed data exists from migration (no seed-data script)
- AC1.4: Duplicate name INSERT rejected (PK constraint)
- AC1.5: Level CHECK (1-100) and UNIQUE constraints enforced
- workspace-sharing-97.AC1.1: peer permission with level 15
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from promptgrimoire.config import get_settings

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


class TestSeedDataFromMigration:
    """Verify seed data comes from Alembic migration, not seed-data script.

    AC1.3: Reference table rows are created by the migration, not seed-data script.

    Proof strategy: the integration test database is set up by running Alembic
    migrations ONLY — the seed-data CLI is never invoked. If reference table
    data exists in these tests, it came from the migration. This test makes
    that implicit guarantee explicit by verifying the seed-data CLI source
    code does not mention the reference table model names.
    """

    def test_seed_data_cli_does_not_touch_permission_table(self) -> None:
        """The seed-data CLI function source doesn't reference Permission model."""
        import inspect

        from promptgrimoire.cli import seed_data

        source = inspect.getsource(seed_data)
        assert "Permission" not in source

    def test_seed_data_cli_does_not_touch_course_role_table(self) -> None:
        """The seed-data CLI function source doesn't reference CourseRoleRef model."""
        import inspect

        from promptgrimoire.cli import seed_data

        source = inspect.getsource(seed_data)
        assert "CourseRoleRef" not in source


class TestPermissionSeedData:
    """Verify Permission table seed data from migration.

    AC1.1: owner/30, editor/20, peer/15, viewer/10.
    AC1.3: Data present without running seed-data script.
    """

    @pytest.mark.asyncio
    async def test_contains_exactly_four_rows(self) -> None:
        """Permission table has exactly 4 seeded rows."""
        from sqlmodel import select

        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Permission

        async with get_session() as session:
            rows = (await session.exec(select(Permission))).all()

        assert len(rows) == 4

    @pytest.mark.asyncio
    async def test_owner_permission(self) -> None:
        """Permission 'owner' exists with level 30."""
        from sqlmodel import select

        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Permission

        async with get_session() as session:
            row = (
                await session.exec(select(Permission).where(Permission.name == "owner"))
            ).one_or_none()

        assert row is not None
        assert row.level == 30

    @pytest.mark.asyncio
    async def test_editor_permission(self) -> None:
        """Permission 'editor' exists with level 20."""
        from sqlmodel import select

        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Permission

        async with get_session() as session:
            row = (
                await session.exec(
                    select(Permission).where(Permission.name == "editor")
                )
            ).one_or_none()

        assert row is not None
        assert row.level == 20

    @pytest.mark.asyncio
    async def test_viewer_permission(self) -> None:
        """Permission 'viewer' exists with level 10."""
        from sqlmodel import select

        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Permission

        async with get_session() as session:
            row = (
                await session.exec(
                    select(Permission).where(Permission.name == "viewer")
                )
            ).one_or_none()

        assert row is not None
        assert row.level == 10


class TestPeerPermission:
    """Verify peer permission row exists from migration.

    workspace-sharing-97.AC1.1: Permission table contains 'peer' with level 15.
    """

    @pytest.mark.asyncio
    async def test_peer_permission_exists(self) -> None:
        """Permission 'peer' exists with level 15."""
        from sqlmodel import select

        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Permission

        async with get_session() as session:
            row = (
                await session.exec(select(Permission).where(Permission.name == "peer"))
            ).one_or_none()

        assert row is not None
        assert row.level == 15

    @pytest.mark.asyncio
    async def test_peer_level_uniqueness(self) -> None:
        """Level 15 is unique — inserting another row with level 15 fails."""
        from sqlalchemy.exc import IntegrityError

        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Permission

        with pytest.raises(IntegrityError):
            async with get_session() as session:
                dup = Permission(name="dup_peer_level", level=15)
                session.add(dup)
                await session.flush()


class TestCourseRoleRefSeedData:
    """Verify CourseRoleRef (course_role) table seed data from migration.

    AC1.2: coordinator/40, instructor/30, tutor/20, student/10.
    AC1.3: Data present without running seed-data script.
    """

    @pytest.mark.asyncio
    async def test_contains_exactly_four_rows(self) -> None:
        """CourseRoleRef table has exactly 4 seeded rows."""
        from sqlmodel import select

        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import CourseRoleRef

        async with get_session() as session:
            rows = (await session.exec(select(CourseRoleRef))).all()

        assert len(rows) == 4

    @pytest.mark.asyncio
    async def test_coordinator_role(self) -> None:
        """CourseRoleRef 'coordinator' exists with level 40."""
        from sqlmodel import select

        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import CourseRoleRef

        async with get_session() as session:
            row = (
                await session.exec(
                    select(CourseRoleRef).where(CourseRoleRef.name == "coordinator")
                )
            ).one_or_none()

        assert row is not None
        assert row.level == 40

    @pytest.mark.asyncio
    async def test_instructor_role(self) -> None:
        """CourseRoleRef 'instructor' exists with level 30."""
        from sqlmodel import select

        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import CourseRoleRef

        async with get_session() as session:
            row = (
                await session.exec(
                    select(CourseRoleRef).where(CourseRoleRef.name == "instructor")
                )
            ).one_or_none()

        assert row is not None
        assert row.level == 30

    @pytest.mark.asyncio
    async def test_tutor_role(self) -> None:
        """CourseRoleRef 'tutor' exists with level 20."""
        from sqlmodel import select

        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import CourseRoleRef

        async with get_session() as session:
            row = (
                await session.exec(
                    select(CourseRoleRef).where(CourseRoleRef.name == "tutor")
                )
            ).one_or_none()

        assert row is not None
        assert row.level == 20

    @pytest.mark.asyncio
    async def test_student_role(self) -> None:
        """CourseRoleRef 'student' exists with level 10."""
        from sqlmodel import select

        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import CourseRoleRef

        async with get_session() as session:
            row = (
                await session.exec(
                    select(CourseRoleRef).where(CourseRoleRef.name == "student")
                )
            ).one_or_none()

        assert row is not None
        assert row.level == 10


class TestPermissionDuplicateNameRejected:
    """Verify PK constraint rejects duplicate Permission names.

    AC1.4: Duplicate name INSERT into Permission is rejected.
    """

    @pytest.mark.asyncio
    async def test_duplicate_name_raises_integrity_error(
        self,
    ) -> None:
        """INSERT of duplicate 'owner' name raises IntegrityError."""
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Permission

        with pytest.raises(IntegrityError):
            async with get_session() as session:
                dup = Permission(name="owner", level=99)
                session.add(dup)
                await session.flush()


class TestCourseRoleRefDuplicateNameRejected:
    """Verify PK constraint rejects duplicate CourseRoleRef names.

    AC1.4: Duplicate name INSERT into CourseRoleRef is rejected.
    """

    @pytest.mark.asyncio
    async def test_duplicate_name_raises_integrity_error(
        self,
    ) -> None:
        """INSERT of duplicate 'student' raises IntegrityError."""
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import CourseRoleRef

        with pytest.raises(IntegrityError):
            async with get_session() as session:
                dup = CourseRoleRef(name="student", level=99)
                session.add(dup)
                await session.flush()


class TestPermissionLevelConstraints:
    """Verify CHECK and UNIQUE constraints on Permission.level.

    AC1.5: Level BETWEEN 1 AND 100 (CHECK) and UNIQUE.
    """

    @pytest.mark.asyncio
    async def test_level_below_range_raises_integrity_error(
        self,
    ) -> None:
        """Permission with level 0 violates CHECK constraint."""
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Permission

        with pytest.raises(IntegrityError):
            async with get_session() as session:
                bad = Permission(name="below_range", level=0)
                session.add(bad)
                await session.flush()

    @pytest.mark.asyncio
    async def test_level_above_range_raises_integrity_error(
        self,
    ) -> None:
        """Permission with level 101 violates CHECK constraint."""
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Permission

        with pytest.raises(IntegrityError):
            async with get_session() as session:
                bad = Permission(name="above_range", level=101)
                session.add(bad)
                await session.flush()

    @pytest.mark.asyncio
    async def test_duplicate_level_raises_integrity_error(
        self,
    ) -> None:
        """Permission with level 30 (=owner) violates UNIQUE."""
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Permission

        with pytest.raises(IntegrityError):
            async with get_session() as session:
                dup = Permission(name="dup_level", level=30)
                session.add(dup)
                await session.flush()


class TestCourseRoleRefLevelConstraints:
    """Verify CHECK and UNIQUE constraints on CourseRoleRef.level.

    AC1.5: Level BETWEEN 1 AND 100 (CHECK) and UNIQUE.
    """

    @pytest.mark.asyncio
    async def test_level_below_range_raises_integrity_error(
        self,
    ) -> None:
        """CourseRoleRef with level 0 violates CHECK constraint."""
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import CourseRoleRef

        with pytest.raises(IntegrityError):
            async with get_session() as session:
                bad = CourseRoleRef(name="below_range", level=0)
                session.add(bad)
                await session.flush()

    @pytest.mark.asyncio
    async def test_level_above_range_raises_integrity_error(
        self,
    ) -> None:
        """CourseRoleRef with level 101 violates CHECK."""
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import CourseRoleRef

        with pytest.raises(IntegrityError):
            async with get_session() as session:
                bad = CourseRoleRef(name="above_range", level=101)
                session.add(bad)
                await session.flush()

    @pytest.mark.asyncio
    async def test_duplicate_level_raises_integrity_error(
        self,
    ) -> None:
        """CourseRoleRef with level 40 (=coordinator) violates UNIQUE."""
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import CourseRoleRef

        with pytest.raises(IntegrityError):
            async with get_session() as session:
                dup = CourseRoleRef(name="dup_level", level=40)
                session.add(dup)
                await session.flush()
