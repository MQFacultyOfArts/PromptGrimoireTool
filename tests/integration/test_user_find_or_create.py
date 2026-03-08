"""Tests for find_or_create_user and its session-aware helper.

These tests require a running PostgreSQL instance. Set DEV__TEST_DATABASE_URL.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlmodel import select

from promptgrimoire.config import get_settings

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


def _unique_email(prefix: str = "find-or-create") -> str:
    """Generate a unique email address for shared integration test DBs."""
    return f"{prefix}-{uuid4().hex[:8]}@example.com"


class TestFindOrCreateUser:
    """Tests for the public find_or_create_user contract."""

    @pytest.mark.asyncio
    async def test_first_call_creates_user(self) -> None:
        """First call creates a user and reports created=True."""
        from promptgrimoire.db.users import find_or_create_user

        email = _unique_email("first-call")

        user, created = await find_or_create_user(
            email=email,
            display_name="First Caller",
        )

        assert created is True
        assert user.email == email.lower()
        assert user.display_name == "First Caller"

    @pytest.mark.asyncio
    async def test_second_call_reuses_existing_user(self) -> None:
        """Second call reuses the existing row and reports created=False."""
        from promptgrimoire.db.users import find_or_create_user

        email = _unique_email("second-call")
        first_user, first_created = await find_or_create_user(
            email=email,
            display_name="First Name",
        )

        second_user, second_created = await find_or_create_user(
            email=email,
            display_name="Second Name",
        )

        assert first_created is True
        assert second_created is False
        assert second_user.id == first_user.id
        assert second_user.display_name == "First Name"

    @pytest.mark.asyncio
    async def test_mixed_case_email_reuses_lowercased_user(self) -> None:
        """Mixed-case input still reuses the stored lowercased user."""
        from promptgrimoire.db.users import find_or_create_user

        unique = uuid4().hex[:8]
        mixed_case_email = f"Case-{unique}@Example.COM"
        first_user, first_created = await find_or_create_user(
            email=mixed_case_email,
            display_name="Case Tester",
        )

        second_user, second_created = await find_or_create_user(
            email=mixed_case_email.lower(),
            display_name="Different Name",
        )

        assert first_created is True
        assert second_created is False
        assert second_user.id == first_user.id
        assert second_user.email == mixed_case_email.lower()

    @pytest.mark.asyncio
    async def test_second_call_preserves_original_display_name(self) -> None:
        """Second call does not overwrite the stored display_name."""
        from promptgrimoire.db.users import find_or_create_user

        email = _unique_email("display-name")
        first_user, first_created = await find_or_create_user(
            email=email,
            display_name="Original Name",
        )

        second_user, second_created = await find_or_create_user(
            email=email,
            display_name="Updated Name",
        )

        assert first_created is True
        assert second_created is False
        assert second_user.id == first_user.id
        assert second_user.display_name == "Original Name"


class TestFindOrCreateUserWithSession:
    """Tests for the caller-owned session helper seam."""

    @pytest.mark.asyncio
    async def test_helper_reuses_user_within_one_session(self) -> None:
        """Helper composes inside one session and persists only one row."""
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import User
        from promptgrimoire.db.users import _find_or_create_user_with_session

        email = _unique_email("session-helper")

        async with get_session() as session:
            first_user, first_created = await _find_or_create_user_with_session(
                session,
                email=email.upper(),
                display_name="Session Name",
            )
            second_user, second_created = await _find_or_create_user_with_session(
                session,
                email=email.lower(),
                display_name="Different Name",
            )
            rows = (
                await session.exec(select(User).where(User.email == email.lower()))
            ).all()

        assert first_created is True
        assert second_created is False
        assert second_user.id == first_user.id
        assert second_user.display_name == "Session Name"
        assert len(rows) == 1
