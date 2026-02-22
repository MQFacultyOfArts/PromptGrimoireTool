# Parallel E2E Test Runner - Phase 1: Database Cloning Infrastructure

**Goal:** Add template-based database cloning and teardown functions to `bootstrap.py`, enabling the parallel orchestrator (Phase 3) to create per-worker databases.

**Architecture:** Two new functions (`clone_database`, `drop_database`) follow the existing `ensure_database_exists()` pattern in `bootstrap.py` — sync psycopg with autocommit, `sql.SQL`+`sql.Identifier` for safe quoting, same name validation. A third helper (`terminate_connections`) forcibly disconnects sessions from a database before cloning or dropping.

**Tech Stack:** psycopg 3.3.2 (sync, dev dependency), PostgreSQL `CREATE DATABASE ... TEMPLATE`, `DROP DATABASE IF EXISTS`

**Scope:** 1 of 5 phases from original design (phase 1)

**Codebase verified:** 2026-02-20

---

## Acceptance Criteria Coverage

This phase implements and tests:

### parallel-e2e-runner-95.AC4: Database lifecycle
- **parallel-e2e-runner-95.AC4.1 Success:** Worker databases are created automatically via `CREATE DATABASE ... TEMPLATE` from the branch test database
- **parallel-e2e-runner-95.AC4.2 Success:** Worker databases are dropped after successful test completion

---

## Reference Files

The executor and its subagents should read these files for context:

- `src/promptgrimoire/db/bootstrap.py` — contains `ensure_database_exists()`, the pattern to follow
- `src/promptgrimoire/config.py` — contains `_suffix_db_url()` and `Settings` class
- `tests/unit/test_db_schema.py` — contains mock patterns for psycopg.connect
- `CLAUDE.md` — project conventions (TDD, async fixture rule, commit prefixes)
- `.ed3d/implementation-plan-guidance.md` — UAT requirements, test commands

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: `terminate_connections()` helper

**Verifies:** None (infrastructure helper for AC4.1 and AC4.2)

**Files:**
- Modify: `src/promptgrimoire/db/bootstrap.py` (add function after `ensure_database_exists`, around line 87)
- Test: `tests/unit/test_db_schema.py` (add test class)

**Implementation:**

Add `terminate_connections(url: str, db_name: str) -> None` to `bootstrap.py`. This function connects to the `postgres` maintenance database (same URL construction pattern as `ensure_database_exists`) and runs:

```sql
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = %s AND pid <> pg_backend_pid()
```

This is needed because PostgreSQL's `CREATE DATABASE ... TEMPLATE` requires no active connections on the source database, and `DROP DATABASE` requires no active connections on the target.

Follow the existing pattern:
- Accept a full database URL (same format as `ensure_database_exists`)
- Extract maintenance URL by replacing db name with `postgres`
- Strip `postgresql+asyncpg://` prefix to `postgresql://`
- Connect with `psycopg.connect(maintenance_url, autocommit=True)`
- Use parameterised query (`%s`) for the db_name, not `sql.Identifier` (this is a data value, not an identifier)

**Testing:**

Unit test with mocked psycopg.connect. Test that:
- The correct SQL is executed with the correct db_name parameter
- The function connects to the `postgres` maintenance database, not the target database

Follow the existing mock pattern in `test_db_schema.py`:
```python
mock_conn = MagicMock()
mock_conn.__enter__ = MagicMock(return_value=mock_conn)
mock_conn.__exit__ = MagicMock(return_value=False)
with patch("promptgrimoire.db.bootstrap.psycopg.connect", return_value=mock_conn):
    terminate_connections(url, db_name)
```

**Verification:**
Run: `uv run pytest tests/unit/test_db_schema.py -v`
Expected: All tests pass including new terminate_connections tests

**Commit:** `feat: add terminate_connections() helper to bootstrap.py`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: `clone_database()` function

**Verifies:** parallel-e2e-runner-95.AC4.1

**Files:**
- Modify: `src/promptgrimoire/db/bootstrap.py` (add function after `terminate_connections`)
- Test: `tests/unit/test_db_schema.py` (add test class)

**Implementation:**

Add `clone_database(source_url: str, target_name: str) -> str` to `bootstrap.py`.

Behaviour:
1. Validate `target_name` with the same `^[a-zA-Z0-9_]+$` regex as `ensure_database_exists`. Raise `ValueError` if invalid.
2. Extract source db name from `source_url` (same parsing as `ensure_database_exists` — split on `?`, then `rsplit("/", 1)[1]`).
3. Call `terminate_connections(source_url, source_db_name)` to ensure no active connections on the template.
4. Connect to `postgres` maintenance database (same URL construction as `ensure_database_exists`).
5. Execute: `CREATE DATABASE {target_name} TEMPLATE {source_db_name}` using `sql.SQL` + `sql.Identifier` for both names.
6. Return the target database URL (replace the db name in `source_url` with `target_name`).

The return value is a full database URL that can be passed to SQLAlchemy or environment variables.

**Testing:**

Unit tests with mocked psycopg.connect:
- **AC4.1 happy path:** Mock shows `CREATE DATABASE target TEMPLATE source` was executed with correct identifiers. Return value is the target URL.
- **Invalid target name:** `clone_database(url, "bad-name!")` raises `ValueError`.
- **terminate_connections called:** Verify `terminate_connections` is called before `CREATE DATABASE` (mock or patch).

**Verification:**
Run: `uv run pytest tests/unit/test_db_schema.py -v`
Expected: All tests pass

**Commit:** `feat: add clone_database() to bootstrap.py`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: `drop_database()` function

**Verifies:** parallel-e2e-runner-95.AC4.2

**Files:**
- Modify: `src/promptgrimoire/db/bootstrap.py` (add function after `clone_database`)
- Test: `tests/unit/test_db_schema.py` (add test class)

**Implementation:**

Add `drop_database(url: str) -> None` to `bootstrap.py`.

Behaviour:
1. Extract db name from `url` (same parsing as `ensure_database_exists`).
2. Validate db name with `^[a-zA-Z0-9_]+$`. Raise `ValueError` if invalid.
3. Call `terminate_connections(url, db_name)` to ensure no active connections.
4. Connect to `postgres` maintenance database.
5. Execute: `DROP DATABASE IF EXISTS {db_name}` using `sql.SQL` + `sql.Identifier`.

Use `IF EXISTS` so the function is idempotent — dropping a non-existent database is not an error.

**Testing:**

Unit tests with mocked psycopg.connect:
- **AC4.2 happy path:** Mock shows `DROP DATABASE IF EXISTS target` was executed with correct identifier.
- **Invalid db name in URL:** `drop_database("postgresql://host/bad-name!")` raises `ValueError`.
- **terminate_connections called:** Verify connections are terminated before drop.
- **Idempotent:** No error when database doesn't exist (the SQL uses `IF EXISTS`).

**Verification:**
Run: `uv run pytest tests/unit/test_db_schema.py -v`
Expected: All tests pass

**Commit:** `feat: add drop_database() to bootstrap.py`
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_4 -->
### Task 4: Integration test — clone and drop round-trip

**Verifies:** parallel-e2e-runner-95.AC4.1, parallel-e2e-runner-95.AC4.2

**Files:**
- Create: `tests/integration/test_db_cloning.py`

**Implementation:**

This task creates an integration test that verifies clone and drop work against a real PostgreSQL instance. The test:

1. Uses the branch test database (from `DEV__TEST_DATABASE_URL`) as the template source.
2. Clones it to a uniquely-named target (e.g., `pg_test_clone_{uuid_hex[:8]}`).
3. Verifies the cloned database exists and has the same tables as the source.
4. Drops the cloned database.
5. Verifies it no longer exists.

Follow the integration test pattern:
- Module-level `pytestmark` skip guard for `DEV__TEST_DATABASE_URL`
- `from __future__ import annotations` at top
- Imports inside test functions
- Use a unique name per test run to avoid collisions

The test should connect to the cloned database to verify schema presence (use psycopg directly, same as bootstrap.py). Clean up in a `finally` block to avoid leaving orphan databases even if assertions fail.

**Testing:**

This IS the test. It verifies the actual PostgreSQL behaviour end-to-end.

**Verification:**
Run: `uv run pytest tests/integration/test_db_cloning.py -v`
Expected: All tests pass (requires `DEV__TEST_DATABASE_URL` to be set)

**Commit:** `test: add integration test for database clone/drop round-trip`
<!-- END_TASK_4 -->
