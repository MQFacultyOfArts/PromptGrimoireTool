# Database Test NullPool Migration - Phase 1

**Goal:** Add shared `db_session` fixture with NullPool to main conftest.

**Architecture:** NullPool disables connection caching. Each test gets a fresh TCP connection to PostgreSQL that is closed when the test ends. This eliminates event loop binding issues with asyncpg.

**Tech Stack:** SQLAlchemy asyncio, pytest-asyncio, NullPool

**Scope:** Phase 1 of 7

**Codebase verified:** 2026-02-04

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->

<!-- START_TASK_1 -->
### Task 1: Add NullPool imports to tests/conftest.py

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool/tests/conftest.py:14-21`

**Step 1: Add the imports**

After the existing imports (approximately line 14, after `from unittest.mock import MagicMock, patch`), add the following imports:

```python
from collections.abc import AsyncIterator, Generator
from uuid import uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
```

Note: `Generator` is already imported via TYPE_CHECKING block but we need it at runtime for `db_schema_guard`. The existing code has `from typing import TYPE_CHECKING, Any` - we need `Generator` outside of TYPE_CHECKING.

**Step 2: Verify imports work**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool && uv run python -c "from tests.conftest import *; print('imports ok')"
```

Expected: `imports ok` with no errors

**Step 3: Commit**

```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool && git add tests/conftest.py && git commit -m "$(cat <<'EOF'
chore(tests): add NullPool imports to conftest

Preparation for db_session fixture migration.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add db_canary fixture

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool/tests/conftest.py`

Insert after line 398 (after `db_schema_guard` fixture's `yield`):

**Step 1: Add canary UUID constant**

At the top of the file after imports (around line 23, after `load_dotenv()`), add:

```python
# Canary UUID for database rebuild detection
# If this row disappears during a test run, the database was rebuilt
_DB_CANARY_ID = uuid4()
```

**Step 2: Add db_canary fixture**

Insert after `db_schema_guard` fixture (after line 398, before `mock_stytch_client`):

```python
@pytest_asyncio.fixture(scope="session")
async def db_canary(db_schema_guard: None) -> AsyncIterator[str]:  # noqa: ARG001
    """Insert canary row at session start. If DB rebuilds, canary disappears.

    This fixture:
    1. Creates a fresh NullPool engine
    2. Inserts a User with known UUID and email
    3. Returns the canary email for verification

    The canary check in db_session verifies ~1ms PK lookup.
    """
    from promptgrimoire.db import User

    canary_email = f"canary-{_DB_CANARY_ID}@test.local"

    engine = create_async_engine(
        os.environ["DATABASE_URL"],
        poolclass=NullPool,
        connect_args={"timeout": 10, "command_timeout": 30},
    )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        canary_user = User(email=canary_email, display_name="DB Canary")
        session.add(canary_user)
        await session.commit()

    await engine.dispose()
    yield canary_email


```

**Step 3: Verify type checks pass**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool && uvx ty check tests/conftest.py
```

Expected: No errors (warnings OK)

**Step 4: Commit**

```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool && git add tests/conftest.py && git commit -m "$(cat <<'EOF'
feat(tests): add db_canary fixture for rebuild detection

Inserts a canary row at session start. If this row disappears during
tests, the database was rebuilt (violating isolation requirements).

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add db_session fixture with NullPool

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool/tests/conftest.py`

**Step 1: Add db_session fixture**

Insert after `db_canary` fixture:

```python
@pytest_asyncio.fixture
async def db_session(db_canary: str) -> AsyncIterator[AsyncSession]:
    """Database session with NullPool - safe for xdist parallelism.

    Each test gets a fresh TCP connection to PostgreSQL.
    Connection closes when test ends. No pooling, no event loop binding.

    Verifies canary row exists - fails fast if database was rebuilt.
    Canary check uses email lookup (indexed column, ~1ms).
    Note: Email lookup is safer than UUID because User.id is auto-generated.
    """
    from sqlmodel import select

    from promptgrimoire.db import User

    engine = create_async_engine(
        os.environ["DATABASE_URL"],
        poolclass=NullPool,
        connect_args={"timeout": 10, "command_timeout": 30},
    )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        # Verify canary exists - fails if DB was rebuilt
        result = await session.execute(select(User).where(User.email == db_canary))
        canary = result.scalar_one_or_none()
        if canary is None:
            pytest.fail(
                f"DATABASE WAS REBUILT - canary row missing (email: {db_canary})"
            )

        yield session

    await engine.dispose()


```

**Step 2: Verify type checks pass**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool && uvx ty check tests/conftest.py
```

Expected: No errors

**Step 3: Run a quick test to verify fixture works**

Create a temporary test file:
```bash
cat > /tmp/test_db_session_fixture.py << 'EOF'
"""Verify db_session fixture works with NullPool."""
import pytest

@pytest.mark.asyncio
async def test_db_session_fixture_works(db_session):
    """Verify fixture provides working session."""
    from promptgrimoire.db import User
    from sqlmodel import select

    # Should be able to query without errors
    result = await db_session.execute(select(User).limit(1))
    # Just verify query executes, don't care about result
    _ = result.scalar_one_or_none()
EOF
```

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool && uv run pytest /tmp/test_db_session_fixture.py -v
```

Expected: Test passes

**Step 4: Clean up temp file**

```bash
rm /tmp/test_db_session_fixture.py
```

**Step 5: Commit**

```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool && git add tests/conftest.py && git commit -m "$(cat <<'EOF'
feat(tests): add db_session fixture with NullPool

NullPool disables connection caching. Each test gets a fresh TCP
connection that closes when test ends. This eliminates event loop
binding issues with asyncpg and allows xdist parallelism.

Canary verification ensures DB wasn't rebuilt between tests.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_3 -->

<!-- END_SUBCOMPONENT_A -->

---

## Phase 1 Verification

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool && uvx ty check tests/conftest.py && echo "Phase 1 complete"
```

Expected: Type checks pass, "Phase 1 complete" printed
