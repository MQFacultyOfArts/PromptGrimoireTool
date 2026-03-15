"""Integration tests for bulk student enrolment."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from sqlmodel import select

from promptgrimoire.config import get_settings

if TYPE_CHECKING:
    from uuid import UUID

from promptgrimoire.db.models import (
    Course,
    CourseEnrollment,
    StudentGroup,
    StudentGroupMembership,
    User,
)

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


def _unique_email(name: str) -> str:
    """Generate a globally unique test email to avoid xdist collisions."""
    return f"{name}-{uuid4().hex[:8]}@test.local"


def _unique_sid() -> str:
    """Generate a globally unique student ID."""
    return uuid4().hex[:10].upper()


async def _make_course(suffix: str) -> Course:
    """Create a unique course for bulk-enrolment tests."""
    from promptgrimoire.db.courses import create_course

    code = f"BE{uuid4().hex[:6].upper()}"
    return await create_course(
        code=code,
        name=f"Bulk Enrol {suffix}",
        semester="2026-S1",
    )


async def _make_user(email: str, *, student_id: str | None = None) -> User:
    """Create a user with optional student_id."""
    from promptgrimoire.db.engine import get_session
    from promptgrimoire.db.users import create_user

    user = await create_user(email=email, display_name="Pre-existing")
    if student_id is not None:
        async with get_session() as session:
            db_user = await session.get(User, user.id)
            assert db_user is not None
            db_user.student_id = student_id
            session.add(db_user)
            await session.flush()
    return user


async def _count_enrolments(course_id: UUID) -> int:
    """Count course enrolments."""
    from promptgrimoire.db.engine import get_session

    async with get_session() as session:
        result = await session.exec(
            select(CourseEnrollment).where(CourseEnrollment.course_id == course_id)
        )
        return len(list(result.all()))


async def _count_users_by_email(emails: list[str]) -> int:
    """Count how many of the given emails exist as users."""
    from promptgrimoire.db.engine import get_session

    async with get_session() as session:
        result = await session.exec(
            select(User).where(
                User.email.in_([e.lower() for e in emails])  # type: ignore[arg-type]  -- SQLAlchemy in_
            )
        )
        return len(list(result.all()))


async def _count_groups(course_id: UUID) -> int:
    """Count student groups for a course."""
    from promptgrimoire.db.engine import get_session

    async with get_session() as session:
        result = await session.exec(
            select(StudentGroup).where(StudentGroup.course_id == course_id)
        )
        return len(list(result.all()))


async def _count_memberships(course_id: UUID) -> int:
    """Count group memberships for groups in a course."""
    from promptgrimoire.db.engine import get_session

    async with get_session() as session:
        result = await session.exec(
            select(StudentGroupMembership)
            .join(
                StudentGroup,
                StudentGroup.id == StudentGroupMembership.student_group_id,  # type: ignore[invalid-argument-type]  -- SQLAlchemy join expression
            )
            .where(StudentGroup.course_id == course_id)
        )
        return len(list(result.all()))


async def _get_user_by_email(email: str) -> User | None:
    """Fetch a user by email."""
    from promptgrimoire.db.engine import get_session

    async with get_session() as session:
        result = await session.exec(select(User).where(User.email == email.lower()))
        return result.first()


async def _list_group_names(course_id: UUID) -> list[str]:
    """List group names for a course, sorted."""
    from promptgrimoire.db.engine import get_session

    async with get_session() as session:
        result = await session.exec(
            select(StudentGroup.name)
            .where(StudentGroup.course_id == course_id)
            .order_by(StudentGroup.name)
        )
        return list(result.all())


async def _list_membership_pairs(course_id: UUID) -> list[tuple[str, str]]:
    """List (group_name, user_email) pairs for a course, sorted."""
    from promptgrimoire.db.engine import get_session

    async with get_session() as session:
        result = await session.exec(
            select(StudentGroup.name, User.email)
            .join(
                StudentGroupMembership,
                StudentGroupMembership.student_group_id == StudentGroup.id,  # type: ignore[invalid-argument-type]  -- SQLAlchemy join expression
            )
            .join(User, User.id == StudentGroupMembership.user_id)  # type: ignore[invalid-argument-type]  -- SQLAlchemy join expression
            .where(StudentGroup.course_id == course_id)
            .order_by(StudentGroup.name, User.email)
        )
        return list(result.all())


def _make_entries(
    *specs: tuple[str, str, str, tuple[str, ...]],
) -> list:
    """Build EnrolmentEntry list from spec tuples."""
    from promptgrimoire.enrol.xlsx_parser import EnrolmentEntry

    return [
        EnrolmentEntry(email=email, display_name=name, student_id=sid, groups=groups)
        for email, name, sid, groups in specs
    ]


class TestAC3UserCreationAndEnrolment:
    """AC3: user creation, student_id handling, enrolment creation."""

    @pytest.mark.asyncio
    async def test_new_user_created_with_display_name_and_student_id(self) -> None:
        """bulk_enrol creates new User with correct display_name and student_id."""
        from promptgrimoire.db.enrolment import bulk_enrol

        alice_email = _unique_email("alice")
        sid = _unique_sid()
        course = await _make_course("new-user")
        entries = _make_entries(
            (alice_email, "Alice Smith", sid, ()),
        )

        report = await bulk_enrol(entries, course.id)

        assert report.users_created == 1
        user = await _get_user_by_email(alice_email)
        assert user is not None
        assert user.display_name == "Alice Smith"
        assert user.student_id == sid

    @pytest.mark.asyncio
    async def test_existing_user_reused_student_id_set_if_null(self) -> None:
        """Pre-existing user with no student_id gets it set by bulk_enrol."""
        from promptgrimoire.db.enrolment import bulk_enrol

        alice_email = _unique_email("alice")
        sid = _unique_sid()
        await _make_user(alice_email)
        course = await _make_course("existing-user")
        entries = _make_entries(
            (alice_email, "Alice Smith", sid, ()),
        )

        report = await bulk_enrol(entries, course.id)

        assert report.users_created == 0
        assert report.users_existing == 1
        user = await _get_user_by_email(alice_email)
        assert user is not None
        assert user.student_id == sid

    @pytest.mark.asyncio
    async def test_enrolment_created_with_role(self) -> None:
        """CourseEnrollment created with specified role."""
        from promptgrimoire.db.enrolment import bulk_enrol

        alice_email = _unique_email("alice")
        course = await _make_course("enrolment-role")
        entries = _make_entries(
            (alice_email, "Alice Smith", _unique_sid(), ()),
        )

        await bulk_enrol(entries, course.id, role="student")

        count = await _count_enrolments(course.id)
        assert count == 1

        # Verify the actual role value (AC3.3)
        from promptgrimoire.db.engine import get_session

        async with get_session() as session:
            result = await session.exec(
                select(CourseEnrollment).where(CourseEnrollment.course_id == course.id)
            )
            enrollment = result.one()
            assert enrollment.role == "student"

    @pytest.mark.asyncio
    async def test_student_id_conflict_raises_error(self) -> None:
        """Conflicting student_id raises StudentIdConflictError."""
        from promptgrimoire.db.enrolment import (
            StudentIdConflictError,
            bulk_enrol,
        )

        alice_email = _unique_email("alice")
        bob_email = _unique_email("bob")
        old_sid = _unique_sid()
        await _make_user(alice_email, student_id=old_sid)
        course = await _make_course("conflict")
        entries = _make_entries(
            (alice_email, "Alice Smith", _unique_sid(), ()),
            (bob_email, "Bob Jones", _unique_sid(), ()),
        )

        with pytest.raises(StudentIdConflictError):
            await bulk_enrol(entries, course.id)

        # Zero new rows
        assert await _count_enrolments(course.id) == 0
        assert await _count_users_by_email([bob_email]) == 0

    @pytest.mark.asyncio
    async def test_force_overwrites_student_id(self) -> None:
        """force=True overwrites conflicting student_id."""
        from promptgrimoire.db.enrolment import bulk_enrol

        alice_email = _unique_email("alice")
        old_sid = _unique_sid()
        new_sid = _unique_sid()
        await _make_user(alice_email, student_id=old_sid)
        course = await _make_course("force-overwrite")
        entries = _make_entries(
            (alice_email, "Alice Smith", new_sid, ()),
        )

        report = await bulk_enrol(entries, course.id, force=True)

        assert report.student_ids_overwritten == 1
        user = await _get_user_by_email(alice_email)
        assert user is not None
        assert user.student_id == new_sid


class TestAC4IdempotentReimport:
    """AC4: idempotent re-import."""

    @pytest.mark.asyncio
    async def test_idempotent_reimport_creates_nothing(self) -> None:
        """Second import with same data has all zero created counts."""
        from promptgrimoire.db.enrolment import bulk_enrol

        alice_email = _unique_email("alice")
        bob_email = _unique_email("bob")
        course = await _make_course("idempotent")
        entries = _make_entries(
            (alice_email, "Alice Smith", _unique_sid(), ("Tut 1",)),
            (bob_email, "Bob Jones", _unique_sid(), ("Tut 1",)),
        )

        await bulk_enrol(entries, course.id)
        report2 = await bulk_enrol(entries, course.id)

        assert report2.users_created == 0
        assert report2.enrolments_created == 0
        assert report2.groups_created == 0
        assert report2.group_memberships_created == 0

    @pytest.mark.asyncio
    async def test_report_reflects_skipped_counts(self) -> None:
        """Second run shows users_existing and enrolments_skipped."""
        from promptgrimoire.db.enrolment import bulk_enrol

        alice_email = _unique_email("alice")
        course = await _make_course("skipped")
        entries = _make_entries(
            (alice_email, "Alice Smith", _unique_sid(), ()),
        )

        await bulk_enrol(entries, course.id)
        report2 = await bulk_enrol(entries, course.id)

        assert report2.users_existing == 1
        assert report2.enrolments_skipped == 1


class TestAC5Groups:
    """AC5: student group creation and membership."""

    @pytest.mark.asyncio
    async def test_groups_created_per_course(self) -> None:
        """Groups from entries are created as StudentGroup rows."""
        from promptgrimoire.db.enrolment import bulk_enrol

        alice_email = _unique_email("alice")
        bob_email = _unique_email("bob")
        course = await _make_course("groups")
        entries = _make_entries(
            (alice_email, "Alice Smith", _unique_sid(), ("Tutorial 1", "Lab A")),
            (bob_email, "Bob Jones", _unique_sid(), ("Tutorial 2", "Lab A")),
        )

        await bulk_enrol(entries, course.id)

        names = await _list_group_names(course.id)
        assert names == ["Lab A", "Tutorial 1", "Tutorial 2"]

    @pytest.mark.asyncio
    async def test_memberships_link_users_to_groups(self) -> None:
        """Memberships link correct users to correct groups."""
        from promptgrimoire.db.enrolment import bulk_enrol

        alice_email = _unique_email("alice")
        bob_email = _unique_email("bob")
        course = await _make_course("memberships")
        entries = _make_entries(
            (alice_email, "Alice Smith", _unique_sid(), ("Tutorial 1",)),
            (bob_email, "Bob Jones", _unique_sid(), ("Tutorial 2",)),
        )

        await bulk_enrol(entries, course.id)

        pairs = await _list_membership_pairs(course.id)
        assert len(pairs) == 2
        assert (pairs[0][0], pairs[0][1]) == ("Tutorial 1", alice_email.lower())
        assert (pairs[1][0], pairs[1][1]) == ("Tutorial 2", bob_email.lower())

    @pytest.mark.asyncio
    async def test_reimport_skips_existing_memberships(self) -> None:
        """Second import creates zero new group memberships."""
        from promptgrimoire.db.enrolment import bulk_enrol

        alice_email = _unique_email("alice")
        course = await _make_course("reimport-membership")
        entries = _make_entries(
            (alice_email, "Alice Smith", _unique_sid(), ("Tutorial 1",)),
        )

        await bulk_enrol(entries, course.id)
        report2 = await bulk_enrol(entries, course.id)

        assert report2.group_memberships_created == 0

    @pytest.mark.asyncio
    async def test_no_groups_entry_no_memberships(self) -> None:
        """Entry with empty groups creates no membership rows."""
        from promptgrimoire.db.enrolment import bulk_enrol

        alice_email = _unique_email("alice")
        course = await _make_course("no-groups")
        entries = _make_entries(
            (alice_email, "Alice Smith", _unique_sid(), ()),
        )

        await bulk_enrol(entries, course.id)

        assert await _count_memberships(course.id) == 0


class TestAtomicRollback:
    """Integration tests for atomicity guarantees."""

    @pytest.mark.asyncio
    async def test_failure_mid_enrolment_rolls_back_all_rows(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Failure mid-enrol rolls back users, enrolments, and groups."""
        import promptgrimoire.db.enrolment as enrolment_mod

        alice_email = _unique_email("alice")
        bob_email = _unique_email("bob")
        course = await _make_course("rollback")
        entries = _make_entries(
            (alice_email, "Alice Smith", _unique_sid(), ("Tut 1",)),
            (bob_email, "Bob Jones", _unique_sid(), ("Tut 2",)),
        )

        # Let the first enrolment succeed, then blow up
        original = enrolment_mod._create_enrolments
        call_count = 0

        async def _exploding_enrolments(
            session,
            resolved,
            course_id,
            role,
        ):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                msg = "injected failure for atomicity test"
                raise RuntimeError(msg)
            return await original(
                session,
                resolved,
                course_id,
                role,
            )

        monkeypatch.setattr(
            enrolment_mod,
            "_create_enrolments",
            _exploding_enrolments,
        )

        with pytest.raises(RuntimeError, match="injected failure"):
            await enrolment_mod.bulk_enrol(entries, course.id)

        # Nothing should have survived the rollback
        assert (
            await _count_users_by_email(
                [alice_email, bob_email],
            )
            == 0
        )
        assert await _count_enrolments(course.id) == 0
        assert await _count_groups(course.id) == 0
        assert await _count_memberships(course.id) == 0


class TestPublicAPIExport:
    """Smoke tests for public API surface."""

    def test_bulk_enrol_importable_from_db_package(self) -> None:
        """bulk_enrol, EnrolmentReport, StudentIdConflictError are importable."""
        from promptgrimoire.db import (
            EnrolmentReport,
            StudentIdConflictError,
            bulk_enrol,
        )

        assert callable(bulk_enrol)
        assert hasattr(EnrolmentReport, "entries_processed")
        assert hasattr(EnrolmentReport, "users_created")
        err = StudentIdConflictError([("a@b.c", "old", "new")])
        assert hasattr(err, "conflicts")


class TestEmptyStudentIdRegression:
    """Regression: empty student_id must not violate unique constraint.

    Moodle XLSX exports can have blank student_id fields. When two users
    both have empty student_id, the upsert must normalise '' to NULL
    (which the unique constraint allows duplicates of), not write ''
    (which collides on the second user).

    Regression test for 2026-03-15 production LAWS5000 enrolment failure.
    """

    @pytest.mark.asyncio
    async def test_multiple_users_with_empty_student_id(self) -> None:
        """Two users with empty student_id should both enrol successfully."""
        from promptgrimoire.db.enrolment import bulk_enrol

        course = await _make_course("empty-sid")
        alice_email = _unique_email("alice-emptysid")
        bob_email = _unique_email("bob-emptysid")

        entries = _make_entries(
            (alice_email, "Alice Empty", "", ()),
            (bob_email, "Bob Empty", "", ()),
        )

        # This must not raise IntegrityError
        report = await bulk_enrol(entries, course.id)

        assert report.entries_processed == 2
        assert report.users_created == 2

        # Verify neither user has empty string as student_id
        from promptgrimoire.db import get_session

        async with get_session() as session:
            for email in (alice_email, bob_email):
                result = await session.execute(
                    select(User).where(
                        User.email == email,
                    )
                )
                user = result.scalar_one()
                assert user.student_id is None, (
                    f"Empty student_id should be normalised to NULL, "
                    f"got {user.student_id!r} for {email}"
                )

    @pytest.mark.asyncio
    async def test_xlsx_fixture_with_empty_student_ids(self) -> None:
        """Full pipeline: XLSX parse → bulk_enrol with empty student_id cells.

        Uses the tests/fixtures/enrolment/empty_student_ids.xlsx fixture
        which has two rows with blank 'ID number' cells and one with a value.
        """
        from pathlib import Path

        from promptgrimoire.db.enrolment import bulk_enrol
        from promptgrimoire.enrol.xlsx_parser import parse_xlsx

        fixture = (
            Path(__file__).parent.parent
            / "fixtures"
            / "enrolment"
            / "empty_student_ids.xlsx"
        )
        xlsx_bytes = fixture.read_bytes()

        entries = parse_xlsx(xlsx_bytes)
        assert len(entries) == 3

        course = await _make_course("xlsx-empty-sid")
        report = await bulk_enrol(entries, course.id)

        assert report.entries_processed == 3
        assert report.users_created == 3

        # Verify: two users have NULL student_id, one has 'mq99999999'
        from promptgrimoire.db import get_session

        async with get_session() as session:
            for email in ("alice.noid@test.mq.edu.au", "bob.noid@test.mq.edu.au"):
                result = await session.execute(
                    select(User).where(
                        User.email == email,
                    )
                )
                user = result.scalar_one()
                assert user.student_id is None, (
                    f"Blank XLSX cell should produce NULL student_id, "
                    f"got {user.student_id!r} for {email}"
                )

            result = await session.execute(
                select(User).where(
                    User.email == "carol.hasid@test.mq.edu.au",
                )
            )
            carol = result.scalar_one()
            assert carol.student_id == "mq99999999"
