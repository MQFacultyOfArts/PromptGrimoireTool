# Database Test NullPool Migration - Phase 0

**Goal:** Ensure clean database state at pytest startup, before xdist workers spawn.

**Architecture:** Use `pytest_configure` hook which runs once in the main process before workers start. This guarantees schema correctness and no leftover data, regardless of parallelism.

**Tech Stack:** Alembic, SQLAlchemy (sync for simplicity in hook), pytest

**Scope:** Phase 0 of 7 (inserted before original Phase 1)

**Codebase verified:** 2026-02-04

---

<!-- START_TASK_1 -->
### Task 1: Add pytest_configure hook for clean database state

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool/tests/conftest.py`

**Step 1: Add the pytest_configure hook**

Add near the top of conftest.py, after imports but before fixtures:

```python
def pytest_configure(config: pytest.Config) -> None:  # noqa: ARG001
    """Ensure clean database state before xdist workers spawn.

    Runs once in the main process at pytest startup:
    1. Run Alembic migrations to ensure schema is correct
    2. Truncate all tables to remove leftover data from previous runs

    This runs BEFORE xdist spawns workers, so no race conditions.
    """
    import subprocess

    from sqlalchemy import create_engine, text

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return  # Skip if no database configured (non-DB tests)

    # Run migrations to ensure schema is up to date
    result = subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd="/home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool",
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.exit(f"Alembic migration failed: {result.stderr}", returncode=1)

    # Convert async URL to sync for this one-time operation
    sync_url = database_url.replace("postgresql+asyncpg://", "postgresql://")

    engine = create_engine(sync_url)
    with engine.begin() as conn:
        # Get all table names from public schema (except alembic_version)
        result = conn.execute(
            text("""
                SELECT tablename FROM pg_tables
                WHERE schemaname = 'public'
                AND tablename != 'alembic_version'
            """)
        )
        tables = [row[0] for row in result.fetchall()]

        if tables:
            # Truncate all tables with CASCADE to handle foreign keys
            conn.execute(
                text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE")
            )

    engine.dispose()
```

**Step 2: Verify type checks pass**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool && uvx ty check tests/conftest.py
```

Expected: No errors

**Step 3: Run a quick test to verify hook works**

```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool && uv run pytest tests/unit/test_env_vars.py::test_env_example_has_all_used_vars -v 2>&1 | head -20
```

Expected: Test runs (hook executes silently at startup)

**Step 4: Commit**

```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool && git add tests/conftest.py && git commit -m "$(cat <<'EOF'
feat(tests): add pytest_configure hook for clean DB state

Runs Alembic migrations and truncates all tables at pytest startup,
before xdist workers spawn. This ensures every test run begins with
correct schema and no leftover data from previous runs.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add canary cleanup to db_canary fixture

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool/tests/conftest.py`

**Step 1: Add cleanup after yield in db_canary**

Find the `db_canary` fixture and add cleanup logic after the yield:

```python
@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def db_canary(db_schema_guard: None) -> AsyncIterator[str]:  # noqa: ARG001
    """Insert canary row at session start. If DB rebuilds, canary disappears.

    ... existing docstring ...
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

    # Cleanup: remove canary row after session ends
    cleanup_engine = create_async_engine(
        os.environ["DATABASE_URL"],
        poolclass=NullPool,
        connect_args={"timeout": 10, "command_timeout": 30},
    )
    cleanup_factory = async_sessionmaker(cleanup_engine, class_=AsyncSession, expire_on_commit=False)

    async with cleanup_factory() as session:
        from sqlmodel import delete
        await session.execute(delete(User).where(User.email == canary_email))
        await session.commit()

    await cleanup_engine.dispose()
```

**Step 2: Verify type checks pass**

```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool && uvx ty check tests/conftest.py
```

**Step 3: Commit**

```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool && git add tests/conftest.py && git commit -m "$(cat <<'EOF'
feat(tests): add canary row cleanup after test session

Removes the canary user row when tests complete, preventing database
pollution from repeated test runs.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_2 -->

---

## Phase 0 Verification

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool && uvx ty check tests/conftest.py && echo "Phase 0 complete"
```

Expected: Type checks pass, "Phase 0 complete" printed
