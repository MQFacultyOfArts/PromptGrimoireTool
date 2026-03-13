"""Integration tests for list_enrollment_rows() joined query.

AC1.2 structural guarantee: list_enrollment_rows() executes a single joined
query (SELECT ... JOIN) rather than N+1 queries.  This is guaranteed by the
implementation which issues one ``select(CourseEnrollment, User).join(...)``
call and assembles dicts from the result rows in a single pass.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from promptgrimoire.config import get_settings

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


async def _make_course(suffix: str):
    """Create a unique course for enrollment-row tests."""
    from promptgrimoire.db.courses import create_course

    code = f"ER{uuid4().hex[:6].upper()}"
    return await create_course(
        code=code,
        name=f"Enrol Rows {suffix}",
        semester="2026-S1",
    )


async def _make_user(
    email: str,
    display_name: str = "Test User",
    *,
    student_id: str | None = None,
):
    """Create a user with optional student_id."""
    from promptgrimoire.db.engine import get_session
    from promptgrimoire.db.models import User
    from promptgrimoire.db.users import create_user

    user = await create_user(email=email, display_name=display_name)
    if student_id is not None:
        async with get_session() as session:
            db_user = await session.get(User, user.id)
            assert db_user is not None
            db_user.student_id = student_id
            session.add(db_user)
            await session.flush()
    return user


_EXPECTED_KEYS = frozenset(
    {
        "email",
        "display_name",
        "student_id",
        "role",
        "created_at",
        "user_id",
    }
)


class TestListEnrollmentRows:
    """AC1: list_enrollment_rows() returns correct dicts for the roster table."""

    @pytest.mark.asyncio
    async def test_returns_correct_keys_and_values(self) -> None:
        """AC1.1: each dict has all expected keys with correct values."""
        from promptgrimoire.db.courses import enroll_user, list_enrollment_rows

        course = await _make_course("keys-vals")
        sid = _unique_sid()
        alice_email = _unique_email("alice")
        bob_email = _unique_email("bob")
        alice = await _make_user(alice_email, "Alice Smith", student_id=sid)
        bob = await _make_user(bob_email, "Bob Jones")

        await enroll_user(course.id, alice.id, role="student")
        await enroll_user(course.id, bob.id, role="tutor")

        rows = await list_enrollment_rows(course.id)

        assert len(rows) == 2

        # All rows have exactly the expected keys
        for row in rows:
            assert set(row.keys()) == _EXPECTED_KEYS

        # Find Alice's row by email
        by_email = {r["email"]: r for r in rows}
        alice_row = by_email[alice_email.lower()]
        assert alice_row["display_name"] == "Alice Smith"
        assert alice_row["student_id"] == sid
        assert alice_row["role"] == "student"
        assert alice_row["user_id"] == str(alice.id)
        # created_at should be a non-empty ISO string
        assert isinstance(alice_row["created_at"], str)
        assert len(alice_row["created_at"]) > 0

        bob_row = by_email[bob_email.lower()]
        assert bob_row["display_name"] == "Bob Jones"
        assert bob_row["role"] == "tutor"
        assert bob_row["user_id"] == str(bob.id)

    @pytest.mark.asyncio
    async def test_empty_course_returns_empty_list(self) -> None:
        """AC1.3: course with zero enrollments returns []."""
        from promptgrimoire.db.courses import list_enrollment_rows

        course = await _make_course("empty")
        rows = await list_enrollment_rows(course.id)
        assert rows == []

    @pytest.mark.asyncio
    async def test_student_id_empty_string_not_none(self) -> None:
        """Edge case: user with no student_id returns "" not None."""
        from promptgrimoire.db.courses import enroll_user, list_enrollment_rows

        course = await _make_course("no-sid")
        charlie_email = _unique_email("charlie")
        charlie = await _make_user(charlie_email, "Charlie No-SID")

        await enroll_user(course.id, charlie.id)

        rows = await list_enrollment_rows(course.id)
        assert len(rows) == 1
        assert rows[0]["student_id"] == ""
        assert rows[0]["student_id"] is not None
