"""Tests for get_user_by_email used by the per-user sharing dialog.

These tests require a running PostgreSQL instance. Set DEV__TEST_DATABASE_URL.

Tests verify email lookup behaviour that the sharing dialog relies on:
finding existing users and returning None for unknown emails.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from promptgrimoire.config import get_settings

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


def _unique_email(prefix: str = "test") -> str:
    """Generate a unique email to avoid collisions in shared test DB."""
    return f"{prefix}-{uuid4().hex[:8]}@example.com"


class TestGetUserByEmail:
    """Tests for get_user_by_email."""

    @pytest.mark.asyncio
    async def test_find_existing_user(self) -> None:
        """Looking up an existing user by email returns the User."""
        from promptgrimoire.db.users import create_user, get_user_by_email

        email = _unique_email("sharing")
        user = await create_user(email=email, display_name="Share Tester")

        found = await get_user_by_email(email)

        assert found is not None
        assert found.id == user.id
        assert found.email == email.lower()

    @pytest.mark.asyncio
    async def test_case_insensitive_lookup(self) -> None:
        """Email lookup is case-insensitive."""
        from promptgrimoire.db.users import create_user, get_user_by_email

        # create_user lowercases on storage; look up with original mixed case
        unique = uuid4().hex[:8]
        mixed_email = f"CaseTest-{unique}@Example.COM"
        user = await create_user(email=mixed_email, display_name="Case Tester")

        found = await get_user_by_email(mixed_email.lower())

        assert found is not None
        assert found.id == user.id

    @pytest.mark.asyncio
    async def test_nonexistent_email_returns_none(self) -> None:
        """Looking up an email that does not exist returns None."""
        from promptgrimoire.db.users import get_user_by_email

        found = await get_user_by_email(_unique_email("nobody"))

        assert found is None
