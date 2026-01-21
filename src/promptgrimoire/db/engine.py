"""Async database engine and session management.

Provides async PostgreSQL connections via SQLModel and asyncpg.
"""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncEngine


@dataclass
class _DatabaseState:
    """Internal state holder for database engine and session factory."""

    engine: AsyncEngine | None = field(default=None)
    session_factory: async_sessionmaker[AsyncSession] | None = field(default=None)


# Module-level state (initialized on startup)
_state = _DatabaseState()

# Expose engine for direct access (e.g., in tests)
_engine: AsyncEngine | None = None  # Updated by init_db/close_db


def get_database_url() -> str:
    """Get database URL from environment.

    Returns:
        PostgreSQL connection string with asyncpg driver.

    Raises:
        ValueError: If DATABASE_URL is not set.
    """
    url = os.environ.get("DATABASE_URL")
    if not url:
        msg = "DATABASE_URL environment variable is required"
        raise ValueError(msg)
    return url


async def init_db() -> None:
    """Initialize database engine and session factory.

    Call this on application startup (e.g., NiceGUI @app.on_startup).
    Creates the async engine with connection pooling configured.
    """
    _state.engine = create_async_engine(
        get_database_url(),
        echo=bool(os.environ.get("DATABASE_ECHO", "")),
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
    )

    _state.session_factory = async_sessionmaker(
        _state.engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # Update module-level reference for direct access
    sys.modules[__name__]._engine = _state.engine  # type: ignore[attr-defined]


async def close_db() -> None:
    """Close database connections.

    Call this on application shutdown (e.g., NiceGUI @app.on_shutdown).
    Disposes of the engine and clears module state.
    """
    if _state.engine:
        await _state.engine.dispose()
        _state.engine = None
        _state.session_factory = None
        sys.modules[__name__]._engine = None  # type: ignore[attr-defined]


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Get an async database session.

    Yields a session that auto-commits on success and rolls back on error.

    Usage:
        async with get_session() as session:
            user = await session.exec(select(User).where(User.id == id))

    Yields:
        AsyncSession: Database session for executing queries.

    Raises:
        RuntimeError: If database has not been initialized via init_db().
    """
    if _state.session_factory is None:
        msg = "Database not initialized. Call init_db() first."
        raise RuntimeError(msg)

    async with _state.session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
