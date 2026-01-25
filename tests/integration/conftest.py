"""Integration test configuration.

Provides fixtures specific to database integration tests.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


@pytest.fixture(autouse=True)
async def reset_db_engine_per_test() -> AsyncGenerator[None]:
    """Reset database engine after each async integration test.

    With function-scoped event loops, the async engine is bound to the
    test's event loop. After the test finishes and its loop closes,
    subsequent tests would fail trying to use the stale engine.

    This fixture ensures the engine is disposed after each test,
    allowing the next test to lazily create a fresh engine in its
    own event loop.

    Only runs cleanup if the engine was actually initialized during the test.
    """
    yield

    # Only dispose engine if it was actually used during this test
    from promptgrimoire.db.engine import _state, close_db

    if _state.engine is not None:
        await close_db()
