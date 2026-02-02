# Database Module Fixes (Code Review Issues)

Addresses CRIT-7, HIGH-7, HIGH-8, HIGH-9 from the code review in `/home/brian/.claude/plans/iterative-baking-crane.md`.

**Constraint:** No quick hacks. Every fix must be a proper solution.

**Key insight:** SQLAlchemy's `create_async_engine` already provides production-grade connection pooling via `AsyncAdaptedQueuePool`. No custom manager needed.

---

## Issues to Fix

| ID | Severity | Issue | Actual Fix |
|----|----------|-------|------------|
| CRIT-7 | Critical | `sys.modules` hack for test access | Add `get_engine()` function |
| HIGH-7 | High | No logging on session rollback | Add `logger.exception()` |
| HIGH-8 | High | Missing pool_recycle/timeouts | Add params to `create_async_engine()` |
| HIGH-9 | High | No CASCADE DELETE on FKs | Alembic migration |

---

## Implementation Plan

### 1. Fix CRIT-7: Remove `sys.modules` Hack

**Current code (bad):**
```python
_engine: AsyncEngine | None = None

async def init_db() -> None:
    _state.engine = create_async_engine(...)
    sys.modules[__name__]._engine = _state.engine  # type: ignore
```

**Fixed code:**
```python
def get_engine() -> AsyncEngine | None:
    """Get the database engine for direct access (e.g., tests)."""
    return _state.engine
```

Remove the `sys.modules` manipulation entirely. Tests use `get_engine()` instead of `db_engine._engine`.

### 2. Fix HIGH-7: Add Logging to Session Rollback

**Current code:**
```python
except Exception:
    await session.rollback()
    raise  # No logging!
```

**Fixed code:**
```python
except Exception:
    logger.exception("Database session error, rolling back transaction")
    await session.rollback()
    raise
```

### 3. Fix HIGH-8: Add Pool Configuration

**Current code:**
```python
_state.engine = create_async_engine(
    get_database_url(),
    echo=bool(os.environ.get("DATABASE_ECHO", "")),
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
)
```

**Fixed code:**
```python
_state.engine = create_async_engine(
    get_database_url(),
    echo=bool(os.environ.get("DATABASE_ECHO", "")),
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=3600,  # Recycle stale connections after 1 hour
    connect_args={
        "timeout": 10,         # Connection timeout
        "command_timeout": 30,  # Query timeout
    },
)
```

### 4. Fix HIGH-9: CASCADE DELETE Migration

Create migration to drop and recreate FK constraints with `ondelete="CASCADE"`:

```bash
uv run alembic revision -m "add cascade delete to foreign keys"
```

FKs to update:
- `class.owner_id` → `user.id`
- `conversation.class_id` → `class.id`
- `conversation.owner_id` → `user.id`

### 5. Update Existing Tests

**Integration test fixture** - change:
```python
engine = db_engine._engine  # Old hack
```
to:
```python
from promptgrimoire.db.engine import get_engine
engine = get_engine()
```

### 6. Add New Tests

**A. Unit test: Session logging** (`tests/unit/test_db_engine.py` - new file)

```python
@pytest.mark.asyncio
async def test_session_logs_on_exception(caplog) -> None:
    """Session context manager logs exceptions before re-raising."""
    # Mock session factory to raise on commit
    # Verify logger.exception() was called
    # Verify rollback was called
    assert "rolling back" in caplog.text.lower()
```

**B. Unit test: Pool configuration** (`tests/unit/test_db_engine.py`)

```python
@pytest.mark.asyncio
async def test_pool_configuration() -> None:
    """Engine is created with correct pool settings."""
    # After init_db(), verify:
    # - pool_recycle = 3600
    # - connect_args contains timeout
```

**C. Integration test: Cascade delete** (`tests/integration/test_db_async.py`)

```python
@pytest.mark.asyncio
@pytest.mark.usefixtures("setup_db")
async def test_cascade_delete_removes_dependent_records() -> None:
    """Deleting a User cascades to Class and Conversation."""
    # Create user → class → conversation
    # Delete user
    # Assert class and conversation are gone
```

### 7. Fix Existing Test Quality Issues

**D. HIGH-11: Replace arbitrary waits** (`tests/e2e/test_two_tab_sync.py`)

Change:
```python
page.wait_for_timeout(200)  # Flaky!
```
to:
```python
expect(some_element).to_be_visible()  # Auto-retry
```

**E. HIGH-12: Strengthen version assertion** (`tests/unit/test_example.py`)

Change:
```python
assert len(parts) >= 2  # Allows "1.2.3.4.5"
```
to:
```python
assert len(parts) == 3  # Semantic versioning: major.minor.patch
```

---

## Files to Modify

| File | Change |
|-------|--------|
| `src/promptgrimoire/db/engine.py` | Add `get_engine()`, logging, pool config |
| `src/promptgrimoire/db/__init__.py` | Export `get_engine` |
| `tests/unit/test_db_engine.py` | **New file** - unit tests for engine |
| `tests/integration/test_db_async.py` | Use `get_engine()`, add cascade test |
| `tests/e2e/test_two_tab_sync.py` | Replace `wait_for_timeout` with `expect()` |
| `tests/unit/test_example.py` | Fix version assertion |
| `alembic/versions/XXXX_add_cascade_delete.py` | New migration |

---

## Implementation Order (TDD)

**Phase 1: Fix CRIT-7 (sys.modules hack)**

1. Add `get_engine()` function to `engine.py`
2. Remove `sys.modules` manipulation and `_engine` module var
3. Update `db/__init__.py` exports
4. Update integration test fixture to use `get_engine()`
5. Run tests - verify nothing breaks

**Phase 2: Fix HIGH-7 (logging) + HIGH-8 (pool config)**

6. Write `test_session_logs_on_exception` (fail)
7. Add `logger.exception()` to `get_session()` (pass)
8. Write `test_pool_configuration` (fail)
9. Add `pool_recycle` and `connect_args` to engine (pass)

**Phase 3: Fix HIGH-9 (CASCADE DELETE)**

10. Write `test_cascade_delete_removes_dependent_records` (fail)
11. Create Alembic migration for CASCADE
12. Run migration on test DB (pass)

**Phase 4: Fix test quality issues**

13. Fix HIGH-11: Replace `wait_for_timeout` in E2E tests
14. Fix HIGH-12: Strengthen version assertion

**Phase 5: Verify**

15. Run full test suite
16. Commit

---

## Verification

```bash
# Type checking
uvx ty check

# Linting
uv run ruff check .

# Unit tests
uv run pytest tests/unit/test_db_models.py -v

# Integration tests
uv run pytest tests/integration/test_db_async.py -v

# Run migration
uv run alembic upgrade head

# Start app
uv run python -m promptgrimoire
```

---

## Why NOT a Custom DatabaseManager

SQLAlchemy already handles:
- Thread-safe connection pooling (`AsyncAdaptedQueuePool`)
- Concurrent access via `asyncio.Queue` internally
- Connection health checks (`pool_pre_ping`)
- Stale connection recycling (`pool_recycle`)

Writing a custom manager would duplicate this functionality and likely introduce bugs. The only changes needed are:
1. Expose engine via a function instead of a hack
2. Add logging
3. Configure existing pool parameters
