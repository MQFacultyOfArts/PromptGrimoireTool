"""Async database engine and session management.

Provides async PostgreSQL connections via SQLModel and asyncpg.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from promptgrimoire.config import get_settings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)


@dataclass
class _DatabaseState:
    """Internal state holder for database engine and session factory."""

    engine: AsyncEngine | None = field(default=None)
    session_factory: async_sessionmaker[AsyncSession] | None = field(default=None)


# Module-level state (initialized on startup)
_state = _DatabaseState()


def get_database_url() -> str:
    """Get database URL from Settings.

    Returns:
        PostgreSQL connection string with asyncpg driver.

    Raises:
        ValueError: If DATABASE__URL is not configured.
    """
    url = get_settings().database.url
    if not url:
        msg = (
            "DATABASE__URL is not configured. "
            "Set it in your .env file or as an environment variable."
        )
        raise ValueError(msg)
    return url


def get_engine() -> AsyncEngine | None:
    """Get the database engine for direct access.

    Primarily for test fixtures that need to call create_all/drop_all.

    Returns:
        The async engine if initialized, None otherwise.
    """
    return _state.engine


async def init_db() -> None:
    """Initialize database engine and session factory.

    Call this on application startup (e.g., NiceGUI @app.on_startup).
    Creates the async engine with connection pooling configured.
    """
    _state.engine = create_async_engine(
        get_database_url(),
        echo=get_settings().dev.database_echo,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=3600,  # Recycle stale connections after 1 hour
        connect_args={
            "timeout": 10,  # Connection timeout in seconds
            "command_timeout": 30,  # Query timeout in seconds
        },
    )

    _state.session_factory = async_sessionmaker(
        _state.engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def close_db() -> None:
    """Close database connections.

    Call this on application shutdown (e.g., NiceGUI @app.on_shutdown).
    Disposes of the engine and clears module state.
    """
    if _state.engine:
        await _state.engine.dispose()
        _state.engine = None
        _state.session_factory = None


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Get an async database session.

    Yields a session that auto-commits on success and rolls back on error.
    Exceptions are logged before re-raising.

    Lazily initializes the database engine on first use if not already
    initialized. This ensures the engine is created in the current
    event loop context.

    Usage:
        async with get_session() as session:
            user = await session.exec(select(User).where(User.id == id))

    Yields:
        AsyncSession: Database session for executing queries.

    Raises:
        ValueError: If DATABASE__URL is not configured.
    """
    # Lazy init: create engine in the current event loop if not yet created
    if _state.session_factory is None:
        await init_db()

    # After init_db(), session_factory is guaranteed to be set
    session_factory = _state.session_factory
    assert session_factory is not None  # For type narrowing

    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            logger.exception("Database session error, rolling back transaction")
            await session.rollback()
            raise
