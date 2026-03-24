"""Regression: active-query cancellation does not permanently shrink QueuePool.

#403 falsification guard. CancelledError during a server-side query
(the production-shaped case) triggers INVALIDATE but the pool self-heals
and maintains full pool_size capacity.

If a future SQLAlchemy or asyncpg upgrade breaks this self-healing
behaviour, this test will catch it.

Requires DATABASE__URL (PostgreSQL with asyncpg). Skipped otherwise.
"""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

if TYPE_CHECKING:
    from sqlalchemy.pool import QueuePool


@pytest.fixture
def db_url() -> str:
    """Get database URL, skip if unavailable."""
    url = os.environ.get("DATABASE__URL", "")
    if not url:
        pytest.skip("DATABASE__URL not set")
    if "asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://")
    return url


@pytest_asyncio.fixture
async def pool_engine(db_url):
    """Create a fresh engine with a small QueuePool per test."""
    engine = create_async_engine(
        db_url,
        pool_size=5,
        max_overflow=2,
        pool_pre_ping=True,
    )

    invalidations: list[str] = []

    @event.listens_for(engine.sync_engine.pool, "invalidate")
    def _on_invalidate(_dbapi_conn, _rec, exception, _soft=False):
        invalidations.append(type(exception).__name__ if exception else "None")

    yield engine, invalidations

    await engine.dispose()


def _pool_snapshot(pool: QueuePool) -> dict[str, int]:
    """Capture pool state as a dict for diagnostics."""
    return {
        "size": pool.size(),
        "checked_in": pool.checkedin(),
        "checked_out": pool.checkedout(),
        "overflow": pool.overflow(),
    }


async def test_active_query_cancellation_self_heals(pool_engine):
    """Cancelling tasks during active pg_sleep triggers INVALIDATE,
    but the pool still serves full pool_size simultaneous connections.

    This merges the single-cancel and repeated-cancel cases from the
    original #403 investigation into one test that asserts both:
    1. INVALIDATE events fire (the production-observed behaviour)
    2. Pool capacity is fully preserved afterward
    """
    engine, invalidations = pool_engine
    pool: QueuePool = engine.sync_engine.pool
    sf = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # Cancel 5 active server-side queries sequentially
    for _ in range(5):

        async def active_query():
            async with sf() as session:
                await session.execute(text("SELECT pg_sleep(30)"))
                await session.commit()

        task = asyncio.create_task(active_query())
        await asyncio.sleep(0.3)  # Let query start on server
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.sleep(0.5)  # Let cleanup propagate

    after_cancels = _pool_snapshot(pool)

    # Assert 1: INVALIDATE events fired (production-shaped behaviour).
    # Active-query cancellation should invalidate the connection.
    assert len(invalidations) > 0, (
        f"Expected INVALIDATE events from active-query cancellation. "
        f"Pool: {after_cancels}"
    )

    # Assert 2: pool still serves full pool_size simultaneous connections.
    # This is the discriminating test — if capacity were lost, this fails.
    sessions_held: list[tuple] = []
    try:
        for _ in range(5):
            ctx = sf()
            session = await ctx.__aenter__()
            await session.execute(text("SELECT 1"))
            sessions_held.append((ctx, session))

        mid = _pool_snapshot(pool)
        assert mid["checked_out"] == 5, (
            f"Expected 5 simultaneous checkouts after 5 active-query cancels. "
            f"Pool: {mid}, After cancels: {after_cancels}, "
            f"Invalidations ({len(invalidations)}): {invalidations}"
        )
    finally:
        for ctx, session in sessions_held:
            await session.commit()
            await ctx.__aexit__(None, None, None)

    final = _pool_snapshot(pool)
    assert final["checked_out"] == 0, f"All connections should be returned. {final}"
