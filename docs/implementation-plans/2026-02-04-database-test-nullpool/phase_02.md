# Database Test NullPool Migration - Phase 2

**Goal:** Update core DB tests to use new `db_session` fixture.

**Architecture:** Migrate from local `db_engine` fixture (uses init_db/close_db with pooled connections) to shared `db_session` fixture (uses NullPool per-connection).

**Tech Stack:** SQLAlchemy asyncio, pytest-asyncio, NullPool

**Scope:** Phase 2 of 7

**Codebase verified:** 2026-02-04

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->

<!-- START_TASK_1 -->
### Task 1: Remove local db_engine fixture

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool/tests/integration/test_db_async.py:23-48`

**Step 1: Remove unused imports**

Remove lines 23-26 (the engine imports and TYPE_CHECKING block):

```python
# REMOVE these lines:
from promptgrimoire.db.engine import close_db, get_engine, get_session, init_db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
```

**Step 2: Remove db_engine fixture**

Remove lines 35-48 (the entire db_engine fixture):

```python
# REMOVE this entire fixture:
@pytest.fixture
async def db_engine(db_schema_guard: None) -> AsyncIterator[None]:  # noqa: ARG001
    """Initialize database engine for each test.

    Depends on db_schema_guard to ensure Alembic migrations have run.
    This fixture only manages the engine connection.
    """
    await init_db()
    engine = get_engine()
    assert engine is not None, "Engine should be initialized after init_db()"

    yield

    await close_db()
```

**Step 3: Verify file still parses**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool && uv run python -c "import tests.integration.test_db_async; print('parses ok')"
```

Expected: `parses ok`

**Step 4: Commit**

```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool && git add tests/integration/test_db_async.py && git commit -m "$(cat <<'EOF'
refactor(tests): remove local db_engine fixture from test_db_async

Preparation for migration to shared db_session fixture with NullPool.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Update test functions to use db_session

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool/tests/integration/test_db_async.py`

**Step 1: Update test_insert_user**

Replace the entire test function. Change from `usefixtures("db_engine")` with `get_session()` to direct `db_session` parameter:

```python
@pytest.mark.asyncio
async def test_insert_user(db_session) -> None:
    """Async insert operation works for User model."""
    user = User(
        email=f"test-insert-{uuid4()}@example.com",
        display_name="Test Insert User",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    assert user.id is not None
    assert user.created_at is not None
```

**Step 2: Update test_query_user**

Replace the entire test function:

```python
@pytest.mark.asyncio
async def test_query_user(db_session) -> None:
    """Async query operation works for User model."""
    test_email = f"test-query-{uuid4()}@example.com"

    # Insert a user
    user = User(email=test_email, display_name="Test Query User")
    db_session.add(user)
    await db_session.commit()

    # Query the user back (same session, same transaction)
    stmt = select(User).where(User.email == test_email)
    result = await db_session.execute(stmt)
    found = result.scalar_one_or_none()

    assert found is not None
    assert found.email == test_email
    assert found.display_name == "Test Query User"
```

**Step 3: Remove test_connection_pool_configured**

This test verified QueuePool settings which no longer apply with NullPool. Remove the entire test.

Note: We don't add a NullPool verification test because the canary check in db_session implicitly verifies NullPool behavior - if connections were being pooled across event loops, tests would fail with "Event loop is closed".

Remove:

```python
# REMOVE this test - no longer relevant with NullPool:
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
```

**Step 4: Verify tests run**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool && uv run pytest tests/integration/test_db_async.py -v
```

Expected: 2 tests pass

**Step 5: Commit**

```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool && git add tests/integration/test_db_async.py && git commit -m "$(cat <<'EOF'
refactor(tests): migrate test_db_async to db_session fixture

- Replace db_engine + get_session() pattern with direct db_session
- Remove test_connection_pool_configured (no longer relevant with NullPool)
- Tests now use shared NullPool fixture for xdist parallelism

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Verify xdist parallelism works

**Files:** No changes - verification only

**Step 1: Run with xdist parallelism**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool && uv run pytest tests/integration/test_db_async.py -n 2 -v 2>&1 | head -30
```

Expected: Tests pass, no "Future attached to different loop" errors

**Step 2: Verify tests distributed across workers**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool && uv run pytest tests/integration/test_db_async.py -n 2 -v 2>&1 | grep -E "^\[gw"
```

Expected: Output shows tests running on gw0 and/or gw1 (may vary based on scheduling)

<!-- END_TASK_3 -->

<!-- END_SUBCOMPONENT_A -->

---

## Phase 2 Verification

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool && uv run pytest tests/integration/test_db_async.py -n 4 -v && echo "Phase 2 complete"
```

Expected: Tests pass with xdist workers, "Phase 2 complete" printed

## API Note

The `db_session` fixture yields a SQLAlchemy `AsyncSession`, not a SQLModel session. This means:
- Use `db_session.execute(stmt)` with `result.scalar_one_or_none()` (SQLAlchemy pattern)
- The existing codebase uses `session.exec(stmt)` with `result.first()` (SQLModel pattern)

Both work, but tests using `db_session` should use the SQLAlchemy API for type consistency.

## Final test_db_async.py Structure

After Phase 2, the file should look like:

```python
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
from uuid import uuid4

import pytest
from sqlmodel import select

from promptgrimoire.db import User

# Skip all tests if no test database URL is configured
pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set - skipping database integration tests",
)


@pytest.mark.asyncio
async def test_insert_user(db_session) -> None:
    """Async insert operation works for User model."""
    user = User(
        email=f"test-insert-{uuid4()}@example.com",
        display_name="Test Insert User",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    assert user.id is not None
    assert user.created_at is not None


@pytest.mark.asyncio
async def test_query_user(db_session) -> None:
    """Async query operation works for User model."""
    test_email = f"test-query-{uuid4()}@example.com"

    # Insert a user
    user = User(email=test_email, display_name="Test Query User")
    db_session.add(user)
    await db_session.commit()

    # Query the user back (same session, same transaction)
    stmt = select(User).where(User.email == test_email)
    result = await db_session.execute(stmt)
    found = result.scalar_one_or_none()

    assert found is not None
    assert found.email == test_email
    assert found.display_name == "Test Query User"
```
