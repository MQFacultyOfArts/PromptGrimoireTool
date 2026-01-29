"""Integration tests for async database operations.

These tests require a running PostgreSQL instance. Set TEST_DATABASE_URL
environment variable to point to a test database.

Example:
    TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/promptgrimoire_test

Note: Schema is created by Alembic migrations in conftest.py (db_schema_guard).
Tests use UUID-based isolation - no table drops or truncations.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from sqlmodel import select

from promptgrimoire.db import User
from promptgrimoire.db.engine import close_db, get_engine, get_session, init_db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

# Skip all tests if no test database URL is configured
pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set - skipping database integration tests",
)


@pytest.fixture
async def db_engine() -> AsyncIterator[None]:
    """Initialize database engine for each test.

    Schema already exists from Alembic migrations (db_schema_guard in conftest).
    This fixture only manages the engine connection.
    """
    await init_db()
    engine = get_engine()
    assert engine is not None, "Engine should be initialized after init_db()"

    yield

    await close_db()


@pytest.mark.asyncio
@pytest.mark.usefixtures("db_engine")
async def test_insert_user() -> None:
    """Async insert operation works for User model."""
    async with get_session() as session:
        user = User(
            email=f"test-insert-{uuid4()}@example.com",
            display_name="Test Insert User",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        assert user.id is not None
        assert user.created_at is not None


@pytest.mark.asyncio
@pytest.mark.usefixtures("db_engine")
async def test_query_user() -> None:
    """Async query operation works for User model."""
    test_email = f"test-query-{uuid4()}@example.com"

    # Insert a user
    async with get_session() as session:
        user = User(email=test_email, display_name="Test Query User")
        session.add(user)
        await session.commit()

    # Query the user back
    async with get_session() as session:
        stmt = select(User).where(User.email == test_email)
        result = await session.exec(stmt)
        found = result.first()

        assert found is not None
        assert found.email == test_email
        assert found.display_name == "Test Query User"


@pytest.mark.asyncio
@pytest.mark.usefixtures("db_engine")
async def test_connection_pool_configured() -> None:
    """Connection pooling is properly configured."""
    from promptgrimoire.db.engine import get_engine

    engine = get_engine()
    assert engine is not None
    # AsyncAdaptedQueuePool has size() method
    assert engine.pool.size() == 5  # type: ignore[union-attr]
    # Verify pool_recycle is set (HIGH-8 fix)
    assert engine.pool._recycle == 3600
