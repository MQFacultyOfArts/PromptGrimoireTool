# Pydantic-Settings Migration — Phase 6: App Startup, CLI, and Remaining Pages

**Goal:** Migrate the application entry point, CLI commands, remaining page modules, and Alembic to use Settings. Eliminate all `load_dotenv()` calls and remaining `os.environ` access from application code.

**Architecture:** `__init__.py` replaces `load_dotenv()` + env vars with `get_settings()`. `cli.py` reads from Settings and sets `DATABASE__URL` env var for Alembic subprocess inheritance. `alembic/env.py` replaces `load_dotenv()` with `get_settings()` — reads inherited env vars when run as subprocess, reads `.env` natively when run directly. Pages use Settings for feature flags and DB availability checks.

**Tech Stack:** pydantic-settings v2, NiceGUI, Alembic, typer

**Scope:** 7 phases from original design (phase 6 of 7)

**Codebase verified:** 2026-02-14

---

## Acceptance Criteria Coverage

This phase implements and tests:

### 130-pydantic-settings.AC6: load_dotenv elimination
- **130-pydantic-settings.AC6.1 Success:** Zero `load_dotenv()` calls in application code, test code, or Alembic
- **130-pydantic-settings.AC6.2 Success:** Zero `os.environ.get()` or `os.environ[]` calls in application code
- **130-pydantic-settings.AC6.3 Success:** pydantic-settings reads `.env` natively without explicit `load_dotenv()`

---

<!-- START_TASK_1 -->
### Task 1: Migrate __init__.py — remove load_dotenv, use Settings for startup

**Verifies:** 130-pydantic-settings.AC6.1, 130-pydantic-settings.AC6.2, 130-pydantic-settings.AC6.3

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/src/promptgrimoire/__init__.py`
- Reference: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/src/promptgrimoire/config.py`

**Implementation:**

Update `src/promptgrimoire/__init__.py` — the `main()` function (lines 77-114):

1. **Remove `load_dotenv` import and call** (lines 79, 82):
   - Delete: `from dotenv import load_dotenv`
   - Delete: `load_dotenv()`

2. **Add Settings import** (inside `main()` to avoid circular imports):
   ```python
   from promptgrimoire.config import get_settings
   settings = get_settings()
   ```

3. **Replace DATABASE_URL check** (line 88):
   - Replace: `if os.environ.get("DATABASE_URL"):`
   - With: `if settings.database.url:`

4. **Replace port and storage_secret** (lines 104-105):
   - Replace: `port = int(os.environ.get("PROMPTGRIMOIRE_PORT", "8080"))`
   - With: `port = settings.app.port`
   - Replace: `storage_secret = os.environ.get("STORAGE_SECRET", "dev-secret-change-me")`
   - With: `storage_secret = settings.app.storage_secret.get_secret_value()`

5. **Keep `import os`** — still needed for `os.getpid()` in `_setup_logging()` (line 45). Only the `load_dotenv` import and the `os.environ` calls are removed.

**Verification:**
Run: `uv run ruff check src/promptgrimoire/__init__.py`
Expected: No lint errors

Verify no `os.environ` or `load_dotenv` references remain:
Run: `grep -n "os.environ\|load_dotenv" src/promptgrimoire/__init__.py`
Expected: No output

**Commit:** `refactor: migrate app entry point from load_dotenv to Settings`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Complete cli.py migration — remaining functions and bridge cleanup

**Verifies:** 130-pydantic-settings.AC6.1, 130-pydantic-settings.AC6.2

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/src/promptgrimoire/cli.py`
- Reference: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/src/promptgrimoire/config.py`

**Implementation:**

`_pre_test_db_cleanup()` was already partially migrated in Phase 2 (Task 3) to use `get_settings()` + `ensure_database_exists()`. This task completes the remaining cli.py migration.

Update `src/promptgrimoire/cli.py`:

1. **`_pre_test_db_cleanup()` — remove the `DATABASE_URL` bridge:**
   - Phase 2 set BOTH `os.environ["DATABASE__URL"]` and `os.environ["DATABASE_URL"]` as a bridge. Now that alembic/env.py is migrated (Task 4 in this phase), remove the old-name bridge:
     ```python
     # REMOVE: os.environ["DATABASE_URL"] = test_database_url  # no longer needed
     # KEEP:  os.environ["DATABASE__URL"] = test_database_url
     ```

2. **`set_admin()` function** (lines 255-):
   - Remove: `from dotenv import load_dotenv` (line 261) and `load_dotenv()` (line 263)
   - Replace: `if not os.environ.get("DATABASE_URL"):` (line 271) with:
     ```python
     if not get_settings().database.url:
     ```
   - Update error message: `"DATABASE_URL not set"` → `"DATABASE__URL not configured"`

3. **`seed_data()` function** (lines 387-):
   - Remove: `from dotenv import load_dotenv` (line 396) and `load_dotenv()` (line 398)
   - Replace: `if not os.environ.get("DATABASE_URL"):` (line 400) with:
     ```python
     if not get_settings().database.url:
     ```
   - Update error message: `"DATABASE_URL not set"` → `"DATABASE__URL not configured"`

**Note:** The `get_settings` import and `ensure_database_exists` import were already added to `_pre_test_db_cleanup()` in Phase 2. For `set_admin()` and `seed_data()`, `get_settings` is already available at module level (added in Phase 2). No new imports needed.

**Verification:**
Run: `uv run ruff check src/promptgrimoire/cli.py`
Expected: No lint errors

Verify no `load_dotenv` references remain:
Run: `grep -n "load_dotenv" src/promptgrimoire/cli.py`
Expected: No output

Run: `uv run test-debug`
Expected: Test runner works (exercises _pre_test_db_cleanup path)

**Commit:** `refactor: complete CLI migration to Settings, remove DATABASE_URL bridge`
<!-- END_TASK_2 -->

<!-- START_SUBCOMPONENT_A (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: Migrate pages/courses.py and pages/layout.py to Settings

**Verifies:** 130-pydantic-settings.AC6.2

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/src/promptgrimoire/pages/courses.py`
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/src/promptgrimoire/pages/layout.py`
- Reference: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/src/promptgrimoire/config.py`

**Implementation:**

**pages/courses.py:**

1. **Import changes:**
   - Remove: `import os` (if not used elsewhere)
   - Add: `from promptgrimoire.config import get_settings`

2. **`_is_db_available()` function** (lines 93-95):
   - Replace: `return bool(os.environ.get("DATABASE_URL"))` (line 95)
   - With: `return bool(get_settings().database.url)`

**pages/layout.py:**

1. **Import changes:**
   - Remove: `import os` (if not used elsewhere)
   - Add: `from promptgrimoire.config import get_settings`

2. **`demos_enabled()` function** (lines 25-31):
   - Replace entire function body:
     ```python
     def demos_enabled() -> bool:
         """Check if demo pages are enabled via feature flag."""
         return get_settings().dev.enable_demo_pages
     ```
   - Note: `dev.enable_demo_pages` is already `bool` type in Settings — pydantic handles the `true`/`false`/`1`/`0` coercion. No manual string comparison needed.

**Verification:**
Run: `uv run ruff check src/promptgrimoire/pages/courses.py src/promptgrimoire/pages/layout.py`
Expected: No lint errors

Verify no `os.environ` references remain:
Run: `grep -rn "os.environ" src/promptgrimoire/pages/courses.py src/promptgrimoire/pages/layout.py`
Expected: No output
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Migrate alembic/env.py — remove load_dotenv, use Settings

**Verifies:** 130-pydantic-settings.AC6.1, 130-pydantic-settings.AC6.3

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/alembic/env.py`
- Reference: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/src/promptgrimoire/config.py`

**Implementation:**

Update `alembic/env.py`:

1. **Remove load_dotenv** (lines 13-16):
   - Delete: `from dotenv import load_dotenv`
   - Delete: `# Load .env file before reading DATABASE_URL`
   - Delete: `load_dotenv()`

2. **Add Settings import** (replace load_dotenv import location):
   ```python
   from promptgrimoire.config import get_settings
   ```

3. **Replace DATABASE_URL reading** (lines 41-44):
   - Replace:
     ```python
     # Set the database URL from environment variable
     database_url = os.environ.get("DATABASE_URL")
     if database_url:
         config.set_main_option("sqlalchemy.url", database_url)
     ```
   - With:
     ```python
     # Set the database URL from Settings
     database_url = get_settings().database.url
     if database_url:
         config.set_main_option("sqlalchemy.url", database_url)
     ```

4. **Remove `import os`** (line 9) — no longer needed

**How it works in subprocess context:**
- When `cli.py` runs Alembic as subprocess, it sets `os.environ["DATABASE__URL"]` before spawning
- The subprocess inherits this env var
- `get_settings()` in `alembic/env.py` reads `DATABASE__URL` from the inherited environment
- Result: Alembic uses the test database URL

**How it works standalone:**
- When running `alembic upgrade head` directly from the CLI
- `get_settings()` reads `.env` file natively (pydantic-settings built-in)
- Result: Alembic uses the production/dev database URL from `.env`

**Verification:**
Run: `uv run ruff check alembic/env.py`
Expected: No lint errors

Verify no `os.environ` or `load_dotenv` references remain:
Run: `grep -n "os.environ\|load_dotenv\|import os" alembic/env.py`
Expected: No output

**Commit (Tasks 3-4):** `refactor: migrate remaining pages and alembic to Settings`
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_5 -->
### Task 5: Update conftest bridge — remove old-name DATABASE_URL, use only new name

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/tests/conftest.py`

**Implementation:**

Now that alembic/env.py uses Settings (reads `DATABASE__URL`), the conftest bridge no longer needs to set the old-name `DATABASE_URL`. Update the `db_schema_guard` fixture:

1. Remove: `os.environ["DATABASE_URL"] = test_url` (bridge for un-migrated code — no longer needed)
2. Keep: `os.environ["DATABASE__URL"] = test_url` (for migrated code via Settings)
3. Keep: `get_settings.cache_clear()` (force Settings re-read)

In teardown:
1. Remove: `os.environ.pop("DATABASE_URL", None)` (no longer set)
2. Keep: `os.environ.pop("DATABASE__URL", None)`
3. Keep: `get_settings.cache_clear()`

**Also update `db_canary` and `db_session` fixtures** (lines 196, 215, 247) — these create their own `create_async_engine()` instances using `os.environ["DATABASE_URL"]`. After removing the old-name bridge, they would break.

Replace `os.environ["DATABASE_URL"]` in these fixtures with `get_settings().database.url`:

```python
# In db_canary (lines 196 and 214):
engine = create_async_engine(
    get_settings().database.url,
    poolclass=NullPool,
    connect_args={"timeout": 10, "command_timeout": 30},
)

# In db_session (line 247):
engine = create_async_engine(
    get_settings().database.url,
    poolclass=NullPool,
    connect_args={"timeout": 10, "command_timeout": 30},
)
```

These fixtures depend on `db_schema_guard` (which sets `DATABASE__URL` and calls `cache_clear()`), so `get_settings().database.url` will return the test database URL.

**Verification:**
Run: `uv run test-all`
Expected: All 2354+ tests pass

Verify no old-name bridge references remain:
Run: `grep -n '"DATABASE_URL"' tests/conftest.py`
Expected: No matches (only `"DATABASE__URL"` with double underscore)

Verify no bare `os.environ["DATABASE_URL"]` in conftest fixtures:
Run: `grep -n 'os.environ\["DATABASE_URL"\]' tests/conftest.py`
Expected: No matches

**Commit:** `test: simplify conftest bridge to use only DATABASE__URL`
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Verify zero os.environ and load_dotenv in application code

**Verifies:** 130-pydantic-settings.AC6.1, 130-pydantic-settings.AC6.2

**Files:**
- No modifications — verification only

**Implementation:**

Run comprehensive codebase sweep:

```bash
# Check for any remaining os.environ in application code
grep -rn "os.environ" src/promptgrimoire/

# Check for any remaining load_dotenv in ALL code
grep -rn "load_dotenv" src/ tests/ alembic/

# Check for any remaining os.getenv in application code
grep -rn "os.getenv" src/promptgrimoire/
```

Expected results:
- `os.environ` in `src/`: Zero matches
- `load_dotenv` in `src/`, `tests/`, `alembic/`: Zero matches
- `os.getenv` in `src/`: Zero matches

**Note:** `os.environ` may still appear in:
- `tests/conftest.py` — the bridge pattern (sets `DATABASE__URL` env var) — this is expected
- `cli.py` — sets `DATABASE__URL` for Alembic subprocess — this is expected
- `bootstrap.py` — `dict(os.environ)` for subprocess env pass-through — this is expected

These are legitimate uses of `os.environ` for subprocess communication, not configuration reading.

**Verification:**
Run: `uv run test-all`
Expected: All tests pass

Run: `uv run ruff check .`
Expected: No lint errors

**Commit:** No commit needed — verification task only
<!-- END_TASK_6 -->
