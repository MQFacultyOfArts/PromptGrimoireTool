"""Async database engine and session management.

Provides async PostgreSQL connections via SQLModel and asyncpg.
Includes connection pool instrumentation for diagnostics.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from promptgrimoire.config import get_settings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncEngine
    from sqlalchemy.pool import _ConnectionRecord

logger = logging.getLogger(__name__)
_pool_logger = logging.getLogger(f"{__name__}.pool")


def _pool_status(pool: object) -> str:
    """Format current pool status for logging."""

    # QueuePool exposes these as methods; NullPool does not have them
    def _get(name: str) -> object:
        attr = getattr(pool, name, None)
        if attr is None:
            return "?"
        return attr() if callable(attr) else attr

    size = _get("size")
    checked_in = _get("checkedin")
    checked_out = _get("checkedout")
    overflow = _get("overflow")
    max_overflow = _get("_max_overflow")
    return (
        f"size={size} checked_in={checked_in} checked_out={checked_out}"
        f" overflow={overflow}/{max_overflow}"
    )


def _install_pool_listeners(engine: AsyncEngine) -> None:
    """Attach event listeners to the connection pool for diagnostics.

    Logs checkout, checkin, overflow, and invalidation events with
    current pool status so we can detect connection leaks and exhaustion.
    """
    pool = engine.sync_engine.pool

    @event.listens_for(pool, "checkout")
    def _on_checkout(
        _dbapi_conn: object, _rec: _ConnectionRecord, _proxy: object
    ) -> None:
        _pool_logger.debug("CHECKOUT %s", _pool_status(pool))

    @event.listens_for(pool, "checkin")
    def _on_checkin(_dbapi_conn: object, _rec: _ConnectionRecord) -> None:
        _pool_logger.debug("CHECKIN  %s", _pool_status(pool))

    @event.listens_for(pool, "connect")
    def _on_connect(_dbapi_conn: object, _rec: _ConnectionRecord) -> None:
        _pool_logger.info("NEW_CONN %s", _pool_status(pool))

    @event.listens_for(pool, "invalidate")
    def _on_invalidate(
        _dbapi_conn: object,
        _rec: _ConnectionRecord,
        exception: BaseException | None,
        _soft: bool,
    ) -> None:
        _pool_logger.warning(
            "INVALIDATE soft=%s exception=%s %s",
            _soft,
            type(exception).__name__ if exception else None,
            _pool_status(pool),
        )

    @event.listens_for(pool, "close")
    def _on_close(_dbapi_conn: object, _rec: _ConnectionRecord) -> None:
        _pool_logger.debug("CLOSE    %s", _pool_status(pool))

    _pool_logger.info("Pool listeners installed. Initial: %s", _pool_status(pool))


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

    _install_pool_listeners(_state.engine)

    _state.session_factory = async_sessionmaker(
        _state.engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def log_pool_and_pg_stats() -> None:
    """Log current pool status and PostgreSQL connection statistics.

    Queries pg_stat_activity for connection counts by state and
    pg_stat_database for session_busy_ratio (Cybertec formula).
    Safe to call at any time; logs warnings on failure rather than raising.
    """
    if _state.engine is None:
        return

    pool = _state.engine.sync_engine.pool
    _pool_logger.info("POOL_SNAPSHOT %s", _pool_status(pool))

    try:
        async with _state.engine.connect() as conn:
            # Connection counts by state
            result = await conn.execute(
                text(
                    "SELECT state, count(*) FROM pg_stat_activity"
                    " WHERE datname = current_database()"
                    " GROUP BY state ORDER BY count DESC"
                )
            )
            rows = result.fetchall()
            parts = [f"{state or 'NULL'}={count}" for state, count in rows]
            _pool_logger.info("PG_CONNECTIONS %s", " ".join(parts))

            # Session busy ratio (PostgreSQL 14+)
            result = await conn.execute(
                text(
                    "SELECT active_time,"
                    " idle_in_transaction_time,"
                    " CASE WHEN (active_time + idle_in_transaction_time) > 0"
                    " THEN active_time::float"
                    "   / (active_time + idle_in_transaction_time)"
                    " ELSE 0 END AS session_busy_ratio,"
                    " numbackends"
                    " FROM pg_stat_database"
                    " WHERE datname = current_database()"
                )
            )
            row = result.fetchone()
            if row:
                _pool_logger.info(
                    "PG_STATS active_time=%.1fms idle_in_tx=%.1fms"
                    " busy_ratio=%.3f backends=%d",
                    row[0],
                    row[1],
                    row[2],
                    row[3],
                )
    except Exception:
        _pool_logger.warning("Failed to query pg_stat views", exc_info=True)


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
