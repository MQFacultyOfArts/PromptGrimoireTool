"""Tests for list_users/list_all_users, used by the admin CLI user listing.

These tests require a running PostgreSQL instance. Set DEV__TEST_DATABASE_URL.

The user table is shared across the test suite, so assertions filter the
returned list down to users created within each test (matched via a unique
tag embedded in the email) rather than asserting on the full table.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from promptgrimoire.config import get_settings

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


class TestListUsers:
    """Tests for list_users() (active-only by default) and list_all_users()."""

    @pytest.mark.asyncio
    async def test_excludes_users_who_never_logged_in_by_default(self) -> None:
        """list_users() without include_inactive omits users with no last_login."""
        from promptgrimoire.db.users import create_user, list_users, update_last_login

        tag = uuid4().hex[:8]
        never_logged_in = await create_user(
            email=f"aaa-{tag}@example.com", display_name="Never Logged In"
        )
        logged_in = await create_user(
            email=f"bbb-{tag}@example.com", display_name="Logged In"
        )
        await update_last_login(logged_in.id)

        users = await list_users()
        matched_ids = [u.id for u in users if tag in u.email]

        assert matched_ids == [logged_in.id]
        assert never_logged_in.id not in matched_ids

    @pytest.mark.asyncio
    async def test_include_inactive_returns_both_ordered_by_email(self) -> None:
        """list_users(include_inactive=True) includes never-logged-in users too."""
        from promptgrimoire.db.users import create_user, list_users, update_last_login

        tag = uuid4().hex[:8]
        # Created in reverse-alphabetical order so ORDER BY email is what
        # proves the sort, not insertion order.
        logged_in = await create_user(
            email=f"zzz-{tag}@example.com", display_name="Logged In"
        )
        await update_last_login(logged_in.id)
        never_logged_in = await create_user(
            email=f"aaa-{tag}@example.com", display_name="Never Logged In"
        )

        users = await list_users(include_inactive=True)
        matched_ids = [u.id for u in users if tag in u.email]

        assert matched_ids == [never_logged_in.id, logged_in.id]

    @pytest.mark.asyncio
    async def test_list_all_users_ordered_by_email(self) -> None:
        """list_all_users() returns every user, ordered by email ascending."""
        from promptgrimoire.db.users import create_user, list_all_users

        tag = uuid4().hex[:8]
        # Created in reverse-alphabetical order so ORDER BY email is what
        # proves the sort, not insertion order.
        second = await create_user(
            email=f"zzz-{tag}@example.com", display_name="Second"
        )
        first = await create_user(email=f"aaa-{tag}@example.com", display_name="First")

        users = await list_all_users()
        matched_ids = [u.id for u in users if tag in u.email]

        assert matched_ids == [first.id, second.id]
