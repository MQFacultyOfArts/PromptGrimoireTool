"""Integration tests for async database operations.

These tests require a running PostgreSQL instance. Set DEV__TEST_DATABASE_URL
environment variable to point to a test database.

Example:
    DEV__TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/promptgrimoire_test

Note: Schema is created by Alembic migrations in conftest.py (db_schema_guard).
Tests use UUID-based isolation - no table drops or truncations.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlmodel import select

from promptgrimoire.config import get_settings
from promptgrimoire.db import User

# Skip all tests if no test database URL is configured
pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


@pytest.mark.asyncio
async def test_insert_user(db_session) -> None:
    """Async insert operation works for User model."""
    user = User(
        email=f"test-insert-{uuid4()}@example.com",
        display_name="Test Insert User",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    assert user.id is not None
    assert user.created_at is not None


@pytest.mark.asyncio
async def test_query_user(db_session) -> None:
    """Async query operation works for User model."""
    test_email = f"test-query-{uuid4()}@example.com"

    # Insert a user
    user = User(email=test_email, display_name="Test Query User")
    db_session.add(user)
    await db_session.commit()

    # Query the user back (same session, same transaction)
    stmt = select(User).where(User.email == test_email)
    result = await db_session.execute(stmt)
    found = result.scalar_one_or_none()

    assert found is not None
    assert found.email == test_email
    assert found.display_name == "Test Query User"
