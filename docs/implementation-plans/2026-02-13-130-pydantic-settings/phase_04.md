# Pydantic-Settings Migration — Phase 4: Database and Export Module Migration

**Goal:** Migrate database engine, bootstrap, schema guard, and LaTeX export from `os.environ` to `get_settings()`. Update conftest bridge for new env var names.

**Architecture:** `db/engine.py` reads `database.url` and `dev.database_echo` from Settings. `db/bootstrap.py` reads `database.url` from Settings for its checks and error messages; subprocess env pass-through for Alembic is unchanged (Alembic subprocess still reads old-name env vars — deferred to Phase 6). `export/pdf.py` reads `app.latexmk_path` from Settings.

**Tech Stack:** pydantic-settings v2, SQLAlchemy async, asyncpg

**Scope:** 7 phases from original design (phase 4 of 7)

**Codebase verified:** 2026-02-14

---

## Acceptance Criteria Coverage

This phase implements and tests:

### 130-pydantic-settings.AC1: Type validation at startup
- **130-pydantic-settings.AC1.1 Success:** (partial) `Settings()` validates `database.url`, `dev.database_echo`, `app.latexmk_path` types correctly

### 130-pydantic-settings.AC6: load_dotenv elimination (partial)
- (Partial progress — db/ and export/ modules no longer use `os.environ`. Alembic deferred to Phase 6.)

### 130-pydantic-settings.AC10: Branch-specific database auto-creation (integration)
- **130-pydantic-settings.AC10.1 Success:** (integration) `run_alembic_upgrade()` auto-creates the database if missing via `ensure_database_exists()`

---

<!-- START_TASK_1 -->
### Task 1: Migrate db/engine.py to use Settings

**Verifies:** 130-pydantic-settings.AC1.1 (partial — database_echo bool coercion)

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/src/promptgrimoire/db/engine.py`
- Reference: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/src/promptgrimoire/config.py`

**Implementation:**

Update `src/promptgrimoire/db/engine.py`:

1. **Import changes** (top of file):
   - Remove: `import os` (line 9)
   - Add: `from promptgrimoire.config import get_settings`

2. **`get_database_url()` function** (lines 37-50):
   - Replace `url = os.environ.get("DATABASE_URL")` (line 46) with `url = get_settings().database.url`
   - Update error message: `"DATABASE_URL environment variable is required"` → `"DATABASE__URL is not configured. Set it in your .env file or as an environment variable."`

3. **`init_db()` function** (lines 64-87):
   - Replace `echo=bool(os.environ.get("DATABASE_ECHO", ""))` (line 72) with `echo=get_settings().dev.database_echo`
   - Note: `dev.database_echo` is already `bool` type in Settings — no manual bool() conversion needed. pydantic handles the coercion from string env var to bool.

**Verification:**
Run: `uv run ruff check src/promptgrimoire/db/engine.py`
Expected: No lint errors

Run: `uv run python -c "from promptgrimoire.db.engine import get_database_url; print('import ok')"`
Expected: Prints `import ok`

Verify no `os.environ` references remain:
Run: `grep -n "os.environ\|import os" src/promptgrimoire/db/engine.py`
Expected: No output (no matches)
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Migrate db/bootstrap.py to use Settings and integrate ensure_database_exists

**Verifies:** 130-pydantic-settings.AC10.1 (integration — auto-creation before migrations)

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/src/promptgrimoire/db/bootstrap.py`
- Reference: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/src/promptgrimoire/config.py`

**Implementation:**

Update `src/promptgrimoire/db/bootstrap.py`:

1. **Import changes** (top of file):
   - Keep `import os` — still needed for `dict(os.environ)` in `run_alembic_upgrade()` subprocess
   - Add: `from promptgrimoire.config import get_settings`

2. **`is_db_configured()` function** (lines 27-33):
   - Replace `return bool(os.environ.get("DATABASE_URL"))` (line 33) with `return bool(get_settings().database.url)`
   - Update docstring: `"Check if DATABASE_URL environment variable is set."` → `"Check if database URL is configured in Settings."`

3. **`run_alembic_upgrade()` function** (lines 36-65):
   - Line 45: `is_db_configured()` already migrated in step 2
   - **NEW: Call `ensure_database_exists()` before running the Alembic subprocess.** This means ANY caller of `run_alembic_upgrade()` automatically gets database creation before migrations:
     ```python
     def run_alembic_upgrade() -> None:
         if not is_db_configured():
             raise RuntimeError("DATABASE__URL not configured — cannot run migrations")

         # Auto-create the database if it doesn't exist (e.g., branch-specific DB)
         db_url = get_settings().database.url
         ensure_database_exists(db_url)

         # ... existing subprocess code ...
     ```
   - Line 57: `env=dict(os.environ)` — **KEEP AS-IS**. The Alembic subprocess (alembic/env.py) still reads `os.environ["DATABASE_URL"]` with old name. This pass-through ensures the subprocess inherits the parent environment including any bridge values set by conftest. Will be revisited in Phase 6 when alembic/env.py is migrated.
   - Update error message at line 46: `"DATABASE_URL not set"` → `"DATABASE__URL not configured — cannot run migrations"`

4. **`verify_schema()` function** (lines 82-115):
   - Replace `database_url = os.environ.get("DATABASE_URL", "<unset>")` (line 107) with `database_url = get_settings().database.url or "<unset>"`
   - Update error message at line 114: `"DATABASE_URL={masked_url}"` → `"DATABASE__URL={masked_url}"`

**Verification:**
Run: `uv run ruff check src/promptgrimoire/db/bootstrap.py`
Expected: No lint errors

Verify only the subprocess env pass-through uses `os.environ`:
Run: `grep -n "os.environ" src/promptgrimoire/db/bootstrap.py`
Expected: Only one match — `env=dict(os.environ)` in `run_alembic_upgrade()`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Migrate db/schema_guard.py to use Settings

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/src/promptgrimoire/db/schema_guard.py`
- Reference: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/src/promptgrimoire/config.py`

**Implementation:**

Update `src/promptgrimoire/db/schema_guard.py`:

1. **Import changes** (top of file):
   - Remove: `import os` (line 5)
   - Add: `from promptgrimoire.config import get_settings`

2. **`verify_db_schema()` function** (line 46):
   - Replace `database_url = os.environ.get("DATABASE_URL", "<unset>")` with `database_url = get_settings().database.url or "<unset>"`
   - Update error message: `"DATABASE_URL={database_url}"` → `"DATABASE__URL={database_url}"`

**Verification:**
Run: `uv run ruff check src/promptgrimoire/db/schema_guard.py`
Expected: No lint errors

Verify no `os.environ` references remain:
Run: `grep -n "os.environ\|import os" src/promptgrimoire/db/schema_guard.py`
Expected: No output

**Commit (Tasks 1-3):** `refactor: migrate db module from os.environ to Settings`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Migrate export/pdf.py to use Settings

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/src/promptgrimoire/export/pdf.py`
- Reference: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/src/promptgrimoire/config.py`

**Implementation:**

Update `src/promptgrimoire/export/pdf.py`:

1. **Import changes** (top of file):
   - Remove: `import os` (line 9)
   - Add: `from promptgrimoire.config import get_settings`

2. **`get_latexmk_path()` function** (lines 31-62):
   - Replace `env_path = os.environ.get("LATEXMK_PATH")` (line 47) with `env_path = get_settings().app.latexmk_path`
   - The rest of the function logic is unchanged — check existence, fall back to TinyTeX, raise if not found
   - Update error message: `"LATEXMK_PATH set to"` → `"APP__LATEXMK_PATH set to"`
   - Update docstring resolution order: `"LATEXMK_PATH env var"` → `"APP__LATEXMK_PATH (via Settings)"`

**Verification:**
Run: `uv run ruff check src/promptgrimoire/export/pdf.py`
Expected: No lint errors

Verify no `os.environ` references remain:
Run: `grep -n "os.environ\|import os" src/promptgrimoire/export/pdf.py`
Expected: No output

**Commit:** `refactor: migrate export/pdf.py from os.environ to Settings`
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Update conftest.py bridge for new DATABASE__URL env var name

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/tests/conftest.py`
  - `db_schema_guard` fixture (updated in Phase 2 Task 3)

**Implementation:**

The Phase 2 bridge pattern sets `os.environ["DATABASE_URL"]` for un-migrated code. Now that db/engine.py is migrated to use Settings (which reads `DATABASE__URL`), the bridge must ALSO set the new-name env var.

In the `db_schema_guard` fixture, after the existing bridge line, add the new-name setting:

```python
# Bridge: set env vars so both migrated and un-migrated code reads the test URL
test_url = get_settings().dev.test_database_url
os.environ["DATABASE__URL"] = test_url   # For migrated code via Settings
os.environ["DATABASE_URL"] = test_url    # Bridge for un-migrated code (alembic/env.py)
get_settings.cache_clear()               # Force Settings to re-read with new env var
```

In the fixture teardown, also clean up the new-name env var:

```python
# Teardown: remove bridge env vars and clear Settings cache
os.environ.pop("DATABASE__URL", None)
os.environ.pop("DATABASE_URL", None)
get_settings.cache_clear()
```

**Important:** The `get_settings.cache_clear()` after setting the env var is critical — without it, Settings would return the cached instance that doesn't know about the test database URL. The `cache_clear()` must happen AFTER `os.environ[...]` is set, not before, so that the next `get_settings()` call picks up the new value.

**Verification:**
Run: `uv run test-all`
Expected: All 2354+ tests pass

Run: `uv run ruff check tests/conftest.py`
Expected: No lint errors

**Commit:** `test: update conftest bridge for DATABASE__URL Settings compatibility`
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Update db tests for Settings-based configuration

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/tests/unit/test_db_schema.py` (if it uses `monkeypatch.setenv("DATABASE_URL", ...)`)

**Implementation:**

Check `tests/unit/test_db_schema.py` for any tests that use `monkeypatch.setenv("DATABASE_URL", ...)` or `monkeypatch.delenv("DATABASE_URL", ...)`. These tests were written for the old `os.environ` pattern and need to be updated for Settings.

For tests that check `is_db_configured()`:
- Old pattern: `monkeypatch.setenv("DATABASE_URL", "...")`
- New pattern: patch `get_settings()` to return a Settings instance with `database.url` set or unset

Example:
```python
from unittest.mock import patch
from promptgrimoire.config import DatabaseConfig, Settings

# Test db configured
settings_with_db = Settings(_env_file=None, database=DatabaseConfig(url="postgresql://test"))
with patch("promptgrimoire.db.bootstrap.get_settings", return_value=settings_with_db):
    assert is_db_configured() is True

# Test db not configured
settings_no_db = Settings(_env_file=None)
with patch("promptgrimoire.db.bootstrap.get_settings", return_value=settings_no_db):
    assert is_db_configured() is False
```

Also update `test_run_alembic_upgrade_fails_without_database_url` (line 91): the `match` string changes from `"DATABASE_URL not set"` to `"DATABASE__URL not configured"` to match the updated error message from Task 2.

**Note:** Only update tests that directly test functions migrated in this phase. Leave integration tests that use the db_schema_guard fixture unchanged — they work through the bridge.

**Verification:**
Run: `uv run pytest tests/unit/test_db_schema.py -v`
Expected: All tests pass

Run: `uv run test-all`
Expected: All 2354+ tests pass

**Commit:** `test: update db schema tests for Settings-based configuration`
<!-- END_TASK_6 -->
