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
from sqlmodel import col, select

from promptgrimoire.db import Class, Conversation, User
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
@pytest.mark.usefixtures("db_engine")
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


@pytest.mark.asyncio
@pytest.mark.usefixtures("db_engine")
async def test_cascade_delete_removes_dependent_records() -> None:
    """Deleting a User cascades to Class and Conversation (HIGH-9 fix)."""
    from sqlmodel import delete, select

    async with get_session() as session:
        # Create user
        user = User(
            email=f"cascade-test-{uuid4()}@example.com",
            display_name="Cascade Test User",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        user_id = user.id

        # Create class owned by user
        cls = Class(
            name="Cascade Test Class",
            owner_id=user_id,
            invite_code=f"CSC{uuid4().hex[:8].upper()}",
        )
        session.add(cls)
        await session.commit()
        await session.refresh(cls)
        class_id = cls.id

        # Create conversation in that class
        conv = Conversation(
            class_id=class_id,
            owner_id=user_id,
            raw_text="Cascade test conversation",
        )
        session.add(conv)
        await session.commit()
        conv_id = conv.id

    # Delete the user - should cascade
    # Use col() for proper type inference with SQLModel
    async with get_session() as session:
        stmt = delete(User).where(col(User.id) == user_id)
        await session.exec(stmt)
        await session.commit()

    # Verify cascade deleted dependent records
    async with get_session() as session:
        # Class should be gone
        cls_result = await session.exec(select(Class).where(Class.id == class_id))
        assert cls_result.first() is None, "Class should be cascade deleted"

        # Conversation should be gone
        conv_result = await session.exec(
            select(Conversation).where(Conversation.id == conv_id)
        )
        assert conv_result.first() is None, "Conversation should be cascade deleted"
