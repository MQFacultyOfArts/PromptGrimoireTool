"""Integration test configuration.

Provides fixtures specific to database integration tests.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest_asyncio

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


@pytest_asyncio.fixture(autouse=True)
async def reset_db_engine_per_test() -> AsyncGenerator[None]:
    """Dispose shared database engine after each test.

    REQUIRED for service layer tests that use get_session() from the shared
    engine module. The shared engine uses QueuePool, and pooled connections
    bind to the event loop that created them.

    Without this fixture:
    - Test A creates engine/connections bound to its event loop
    - Test A finishes, its event loop closes
    - Test B tries to reuse pooled connections → RuntimeError: Event loop is closed

    This fixture disposes the engine (closing all pooled connections) after
    each test. The next test lazily creates a fresh engine in its own loop.

    Note: Tests using the db_session fixture (NullPool) don't need this,
    but it doesn't hurt them either. Service layer tests REQUIRE it.
    """
    yield

    # Only dispose engine if it was actually used during this test
    from promptgrimoire.db.engine import _state, close_db

    if _state.engine is not None:
        await close_db()
