"""Regression test for the cold-cache nested-session deadlock class.

The pathology: ``get_staff_roles()`` (and ``get_all_roles()``,
``has_student_workspaces()``) used to open a fresh session for their
cold-load query. When dozens of concurrent requests each held an outer
``get_session()`` transaction and then called these helpers without
threading their session down, every inner checkout blocked waiting for
a pool connection that would only free when an outer transaction
released — which it could not, because its continuation was waiting on
the inner checkout. The pool timeout fires after ~30 s and every caller
fails.

This test reproduces both sides of the boundary under a tight pool so a
regression would surface within seconds:

- positive path: callers pass ``session=session`` — no nested checkout,
  all concurrent calls succeed under ``pool_size=4`` / ``max_overflow=0``
  with 8 concurrent tasks.

- negative path: callers do NOT pass ``session=`` — the nested checkout
  pattern returns, and under the same constrained pool the run must
  fail with an operational or timeout error within a bounded window.

Hardcoded pool-capacity ratio (4 connections, 8 concurrent callers) makes
the deadlock structurally inevitable without patience tuning.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from promptgrimoire.config import get_settings
from promptgrimoire.db import engine as engine_module

if TYPE_CHECKING:
    import pytest_asyncio as _pytest_asyncio_type

    _ = _pytest_asyncio_type  # keep import marker happy under TYPE_CHECKING


pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)

_POOL_SIZE = 4
_CONCURRENT_CALLERS = 8
_DEADLOCK_WAIT_BUDGET_SECONDS = 15.0


async def _swap_in_constrained_pool() -> engine_module._DatabaseState:
    """Replace the module-level engine with a tight QueuePool and return the
    original state so it can be restored during teardown.

    The replacement engine points at the same database URL the integration
    lane already uses; only the pool class + size differ.
    """
    original = engine_module._state

    settings = get_settings()
    url = settings.database.url
    assert url, "DATABASE__URL must be configured for this test to run"

    engine = create_async_engine(
        url,
        pool_size=_POOL_SIZE,
        max_overflow=0,
        pool_pre_ping=False,
        pool_timeout=_DEADLOCK_WAIT_BUDGET_SECONDS,
        connect_args={"timeout": 10, "command_timeout": 30},
    )
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    engine_module._state = engine_module._DatabaseState(
        engine=engine,
        session_factory=session_factory,
    )
    return original


async def _restore(original: engine_module._DatabaseState) -> None:
    """Dispose the test pool and restore the original engine state."""
    replacement = engine_module._state
    engine_module._state = original
    if replacement.engine is not None:
        await replacement.engine.dispose()


async def _outer_session_then_threaded_helper() -> None:
    """Open a session, touch it (forcing a real checkout), then call the
    helper with ``session=`` — the deadlock-safe pattern."""
    from promptgrimoire.db.engine import get_session
    from promptgrimoire.db.roles import get_staff_roles

    async with get_session() as session:
        await session.connection()  # force pool checkout
        roles = await get_staff_roles(session=session)
        assert "instructor" in roles


async def _outer_session_then_bare_helper() -> None:
    """Open a session, touch it, then call the helper WITHOUT ``session=`` —
    the deadlock-unsafe pattern. Forces a second, nested pool checkout."""
    from promptgrimoire.db.engine import get_session
    from promptgrimoire.db.roles import get_staff_roles

    async with get_session() as session:
        await session.connection()  # force pool checkout
        roles = await get_staff_roles()  # nested checkout — will deadlock
        assert "instructor" in roles


@pytest.mark.asyncio
async def test_threaded_session_survives_pool_saturation() -> None:
    """Positive path: 8 concurrent callers with session= complete under a
    4-connection pool. The absence of nested checkouts means at most 4
    connections are in flight at a time and the wave drains quickly."""
    from promptgrimoire.db.roles import (
        _reset_all_roles_cache,
        _reset_staff_roles_cache,
    )

    original = await _swap_in_constrained_pool()
    try:
        _reset_staff_roles_cache()
        _reset_all_roles_cache()

        await asyncio.wait_for(
            asyncio.gather(
                *(
                    _outer_session_then_threaded_helper()
                    for _ in range(_CONCURRENT_CALLERS)
                )
            ),
            timeout=_DEADLOCK_WAIT_BUDGET_SECONDS * 2,
        )
    finally:
        await _restore(original)


@pytest.mark.asyncio
async def test_bare_caller_deadlocks_under_pool_saturation() -> None:
    """Negative path: 8 concurrent callers WITHOUT session= must fail under
    a 4-connection pool. The inner cache-fill checkouts wait forever on
    outer transactions that cannot release. Pool timeout fires inside
    the budget and we observe either a SQLAlchemy TimeoutError or the
    wrapping pytest asyncio.TimeoutError."""
    from promptgrimoire.db.roles import (
        _reset_all_roles_cache,
        _reset_staff_roles_cache,
    )

    original = await _swap_in_constrained_pool()
    try:
        _reset_staff_roles_cache()
        _reset_all_roles_cache()

        with pytest.raises((SQLAlchemyTimeoutError, TimeoutError)):
            await asyncio.wait_for(
                asyncio.gather(
                    *(
                        _outer_session_then_bare_helper()
                        for _ in range(_CONCURRENT_CALLERS)
                    )
                ),
                timeout=_DEADLOCK_WAIT_BUDGET_SECONDS * 2,
            )
    finally:
        # Reset caches so subsequent tests do not observe half-populated state.
        _reset_staff_roles_cache()
        _reset_all_roles_cache()
        await _restore(original)
