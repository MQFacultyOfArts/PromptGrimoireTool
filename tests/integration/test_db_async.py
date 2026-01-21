"""Integration tests for async database operations.

These tests require a running PostgreSQL instance. Set TEST_DATABASE_URL
environment variable to point to a test database.

Example:
    TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/promptgrimoire_test
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from sqlmodel import select

from promptgrimoire.db import Class, Conversation, User
from promptgrimoire.db.engine import close_db, get_session, init_db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

# Skip all tests if no test database URL is configured
pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set - skipping database integration tests",
)


@pytest.fixture(scope="function")
async def setup_db() -> AsyncIterator[None]:
    """Initialize test database connection and create tables.

    Sets DATABASE_URL from TEST_DATABASE_URL, initializes the engine,
    and creates all tables. Cleans up after each test.
    """
    from sqlmodel import SQLModel

    import promptgrimoire.db.engine as db_engine

    test_url = os.environ.get("TEST_DATABASE_URL")
    if not test_url:
        pytest.skip("TEST_DATABASE_URL not set")
        return  # Unreachable but helps type checker

    # Set DATABASE_URL for the engine
    os.environ["DATABASE_URL"] = test_url

    await init_db()

    # Access engine after init_db() has set it
    engine = db_engine._engine
    assert engine is not None, "Engine should be initialized"

    # Create tables for testing
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    yield

    # Drop tables after tests
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)

    await close_db()


@pytest.mark.asyncio
@pytest.mark.usefixtures("setup_db")
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
@pytest.mark.usefixtures("setup_db")
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
@pytest.mark.usefixtures("setup_db")
async def test_class_with_foreign_key() -> None:
    """Class correctly references User via foreign key."""
    async with get_session() as session:
        # Create owner user
        user = User(
            email=f"test-owner-{uuid4()}@example.com",
            display_name="Class Owner",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        # Create class owned by user
        cls = Class(
            name="Test Class",
            owner_id=user.id,
            invite_code=f"INV{uuid4().hex[:8].upper()}",
        )
        session.add(cls)
        await session.commit()
        await session.refresh(cls)

        assert cls.id is not None
        assert cls.owner_id == user.id


@pytest.mark.asyncio
@pytest.mark.usefixtures("setup_db")
async def test_conversation_crud() -> None:
    """Full CRUD cycle works for Conversation model."""
    async with get_session() as session:
        # Create owner and class
        user = User(
            email=f"test-conv-owner-{uuid4()}@example.com",
            display_name="Conversation Owner",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        cls = Class(
            name="Conversation Test Class",
            owner_id=user.id,
            invite_code=f"CNV{uuid4().hex[:8].upper()}",
        )
        session.add(cls)
        await session.commit()
        await session.refresh(cls)

        # Create conversation
        raw_text = "Human: Hello!\n\nAssistant: Hi there!"
        conv = Conversation(
            class_id=cls.id,
            owner_id=user.id,
            raw_text=raw_text,
        )
        session.add(conv)
        await session.commit()
        await session.refresh(conv)
        conv_id = conv.id

    # Read it back in a new session
    async with get_session() as session:
        stmt = select(Conversation).where(Conversation.id == conv_id)
        result = await session.exec(stmt)
        found = result.first()

        assert found is not None
        assert found.raw_text == raw_text

        # Update CRDT state
        found.crdt_state = b"crdt-update-data"
        session.add(found)
        await session.commit()

    # Verify update
    async with get_session() as session:
        stmt = select(Conversation).where(Conversation.id == conv_id)
        result = await session.exec(stmt)
        updated = result.first()

        assert updated is not None
        assert updated.crdt_state == b"crdt-update-data"


@pytest.mark.asyncio
@pytest.mark.usefixtures("setup_db")
async def test_connection_pool_configured() -> None:
    """Connection pooling is properly configured."""
    import promptgrimoire.db.engine as db_engine

    engine = db_engine._engine
    assert engine is not None
    # AsyncAdaptedQueuePool has size() method
    assert engine.pool.size() == 5  # type: ignore[union-attr]
