# Database Test Connection Isolation Design

## Summary

This design addresses a performance bottleneck in database integration tests where all tests are forced onto a single pytest-xdist worker due to event loop binding issues with asyncpg connection pooling. Currently, the `xdist_group("db_integration")` marker prevents parallelism by clustering all database tests together to avoid "Future attached to different loop" errors.

The solution migrates to NullPool, a connection pooling strategy that disables connection caching entirely. Each test will open a fresh TCP connection to PostgreSQL, use it, and close it—eliminating event loop cross-contamination while preserving the existing UUID-based test isolation pattern. This allows database tests to distribute across xdist workers naturally, improving test suite performance without requiring database rebuilds between tests or changes to production code.

## Definition of Done

**Primary Deliverable:**
Database integration tests run with full xdist parallelism - no `xdist_group` clustering.

**Success Criteria:**
- `uv run test-all` passes with DB tests distributed across workers (not all on gw0)
- No "Future attached to different loop" errors
- No database rebuild between tests
- Tests remain isolated by UUID/workspace

**Key Exclusions:**
- E2E tests stay grouped (`xdist_group("e2e")`) - app_server sharing is separate scope
- RTF parser tests stay grouped - LibreOffice spawning is separate scope

## Glossary

- **asyncpg**: PostgreSQL driver for Python asyncio that binds database connections to specific event loops
- **NullPool**: SQLAlchemy pooling strategy that disables connection caching—each database operation opens a fresh connection and closes it when done
- **pytest-xdist**: pytest plugin for running tests in parallel across multiple worker processes (gw0, gw1, gw2, etc.)
- **xdist_group**: pytest-xdist marker that forces specific tests to run on the same worker, preventing parallelism
- **event loop**: asyncio's concurrency mechanism; pytest-asyncio creates function-scoped loops (new loop per test) for Playwright compatibility
- **Alembic**: SQLAlchemy's database migration tool for managing schema changes
- **AsyncSession**: SQLAlchemy's async database session class for executing queries
- **UUID-based isolation**: Test pattern where each test creates entities with unique UUIDs instead of cleaning up shared data
- **E2E tests**: End-to-end tests using Playwright that interact with the full application stack
- **connection pool**: Cache of database connections that can be reused across multiple operations to avoid TCP handshake overhead

## Research Findings

### The Event Loop Binding Problem

**Source:** SQLAlchemy asyncio docs (Context7)

> "If the same engine must be shared between different loops, it should be configured to disable pooling using NullPool, preventing the Engine from using any connection more than once."

asyncpg connections bind to the event loop that created them. With pytest-asyncio's function-scoped event loops (required for Playwright compatibility), pooled connections cannot be shared across tests.

### NullPool Solution

**Source:** SQLAlchemy asyncio docs (Context7)

> "Configure AsyncEngine with NullPool for Multiple Event Loops... Disable connection pooling in AsyncEngine using NullPool to safely share the same engine across multiple asyncio event loops. This prevents 'Task got Future attached to a different loop' errors by ensuring each connection is used only once."

NullPool = no connection caching. Each test opens a fresh TCP connection to PostgreSQL, uses it, closes it. PostgreSQL handles the connections. No event loop cross-contamination.

### Spike Test Verification

Spike tests confirmed:
1. Three async tests with function-scoped loops: PASSED
2. Same tests with `-n 3` xdist workers (gw0, gw1, gw2): PASSED
3. Insert in test_a, query in test_b: PASSED (database persists, not rebuilt)

## Architecture

### Current State (Bottlenecked)

```
tests/conftest.py::db_schema_guard       -> Alembic migrations (once per session)
tests/integration/conftest.py            -> reset_db_engine_per_test (disposes after EVERY test)
tests/integration/test_db_async.py       -> local db_engine fixture (init_db/close_db per test)
tests/integration/test_workspace_*.py    -> xdist_group("db_integration") marker
tests/integration/test_course_service.py -> xdist_group("db_integration") marker
```

Problem: `xdist_group("db_integration")` forces all DB tests onto single worker.

### Target State (Parallel)

```
tests/conftest.py::db_schema_guard  -> Alembic migrations (once per session) [unchanged]
tests/conftest.py::db_session       -> NullPool session fixture
                                       Each test: fresh connection -> use -> close
                                       No engine state between tests
                                       No xdist_group needed
```

### NullPool Fixture Contract

```python
# Session-scoped canary - inserted once, verified every test
_DB_CANARY_ID: UUID  # Generated at module load

@pytest_asyncio.fixture(scope="session")
async def db_canary(db_schema_guard) -> UUID:
    """Insert canary row at session start. If DB rebuilds, canary disappears."""
    # Insert canary user with known UUID
    return _DB_CANARY_ID

@pytest_asyncio.fixture
async def db_session(db_canary) -> AsyncIterator[AsyncSession]:
    """Database session with NullPool - safe for xdist parallelism.

    Each test gets a fresh TCP connection to PostgreSQL.
    Connection closes when test ends. No pooling, no event loop binding.

    Verifies canary row exists - fails fast if database was rebuilt.
    Canary check is single indexed PK lookup (~1ms).
    """
    engine = create_async_engine(
        os.environ["DATABASE_URL"],
        poolclass=NullPool,
        connect_args={"timeout": 10, "command_timeout": 30},
    )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        # Verify canary exists - fails if DB was rebuilt
        canary = await session.get(User, db_canary)
        if canary is None:
            pytest.fail("DATABASE WAS REBUILT - canary row missing")

        yield session

    await engine.dispose()
```

## Existing Patterns

Investigation found current patterns in `tests/integration/`:

**UUID-based test isolation:** Tests create workspaces/users with unique UUIDs. No cleanup needed between tests. This pattern is preserved.

**db_schema_guard fixture:** Session-scoped, runs Alembic migrations once. This pattern is preserved.

**reset_db_engine_per_test:** Autouse fixture that disposes engine after each async test. This will be removed - unnecessary with NullPool.

**xdist_group markers:** Force tests onto single worker to avoid connection pool conflicts. These will be removed - unnecessary with NullPool.

## Implementation Phases

<!-- START_PHASE_0 -->
### Phase 0: Clean Database State at Pytest Startup

**Goal:** Ensure clean database state before xdist workers spawn.

**Components:**
- `tests/conftest.py` - Add `pytest_configure` hook that runs Alembic migrations and truncates all tables
- Uses sync SQLAlchemy (simpler in hook context)
- Runs ONCE in main process before workers start

**Dependencies:** None

**Done when:** `pytest_configure` hook exists, truncates tables at startup

**NOTE (2026-02-04):** Added during implementation to address proleptic challenge feedback about implicit database state assumptions.
<!-- END_PHASE_0 -->

<!-- START_PHASE_1 -->
### Phase 1: Add NullPool Fixture

**Goal:** Add shared `db_session` fixture with NullPool to main conftest.

**Components:**
- `tests/conftest.py` - Add `db_session` fixture with `poolclass=NullPool`
- Import `NullPool` from `sqlalchemy.pool`
- Import `create_async_engine`, `async_sessionmaker` from `sqlalchemy.ext.asyncio`

**Dependencies:** None

**Done when:** Fixture exists, type checks pass
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Migrate test_db_async.py

**Goal:** Update core DB tests to use new fixture.

**Components:**
- `tests/integration/test_db_async.py` - Remove local `db_engine` fixture, use `db_session`
- Update test functions to receive `db_session` parameter

**Dependencies:** Phase 1

**Done when:** `uv run pytest tests/integration/test_db_async.py -n 4 -v` passes with tests on multiple workers
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Migrate Workspace Tests

**Goal:** Remove xdist_group clustering from workspace tests.

**Components:**
- `tests/integration/test_workspace_crud.py` - Remove `xdist_group("db_integration")`, use `db_session`
- `tests/integration/test_workspace_persistence.py` - Remove `xdist_group("db_integration")`, use `db_session`

**Dependencies:** Phase 2

**Done when:** `uv run pytest tests/integration/test_workspace_*.py -n 4 -v` passes with tests distributed
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Migrate Course Service Tests

**Goal:** Remove xdist_group clustering from course service tests.

**Components:**
- `tests/integration/test_course_service.py` - Remove `xdist_group("db_integration")`, use `db_session`

**Dependencies:** Phase 3

**Done when:** `uv run pytest tests/integration/test_course_service.py -n 4 -v` passes with tests distributed
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: Document Fixture Responsibilities (REVISED)

**Goal:** Document why `reset_db_engine_per_test` is still required.

**Components:**
- `tests/integration/conftest.py` - Update docstring to explain fixture's necessity

**Dependencies:** Phase 4

**Done when:** Docstring explains why fixture is required for service layer tests

**REVISION NOTE (2026-02-04):** Original design said to remove this fixture. Spike testing proved it's REQUIRED for service layer tests. Without it, pooled connections from closed event loops cause `RuntimeError: Event loop is closed`. The fixture disposes the shared engine after each test, ensuring fresh connections.
<!-- END_PHASE_5 -->

<!-- START_PHASE_6 -->
### Phase 6: Verify Full Parallelism

**Goal:** Confirm all DB tests distribute across xdist workers.

**Components:** No code changes - verification only

**Dependencies:** Phase 5

**Done when:**
- `uv run test-all` passes
- `uv run pytest tests/integration/test_db_async.py tests/integration/test_workspace_*.py tests/integration/test_course_service.py -n 4 -v 2>&1 | grep -E "^\[gw"` shows tests on gw0, gw1, gw2, gw3
<!-- END_PHASE_6 -->

## Additional Considerations

**Connection limits:** With NullPool, each concurrent test opens a connection. PostgreSQL default max_connections is 100. With `-n auto` creating ~24 workers and tests running in parallel, connection count stays well under limit.

**Production code unchanged:** This design only affects test fixtures. Production `init_db()` retains connection pooling (`pool_size=5, max_overflow=10`).

**Future E2E work:** E2E tests remain grouped due to app_server sharing complexity (the failed branch problem). That's separate scope requiring different solution.
