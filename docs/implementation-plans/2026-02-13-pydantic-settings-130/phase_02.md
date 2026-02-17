# Pydantic-Settings Migration — Phase 2: Test Infrastructure Migration

**Goal:** Update test fixtures to use Settings, rewrite `test_env_vars.py` to introspect Settings schema, add unit tests for Settings validation and per-worktree database isolation, and early-migrate `_pre_test_db_cleanup()` in `cli.py`.

**Architecture:** `conftest.py` removes `load_dotenv()` and reads config from `get_settings()`. Bridge pattern: conftest still sets `os.environ["DATABASE_URL"]` for un-migrated code during transition. `test_env_vars.py` introspects `Settings.model_fields` to derive expected env var names and cross-references against `.env.example`. `cli.py._pre_test_db_cleanup()` is early-migrated to use `get_settings()` + `ensure_database_exists()` so it uses the same suffixed URLs as conftest.

**Tech Stack:** pydantic-settings v2, pytest, pytest-asyncio, psycopg (sync)

**Scope:** 7 phases from original design (phase 2 of 7)

**Codebase verified:** 2026-02-14

---

## Acceptance Criteria Coverage

This phase implements and tests:

### 130-pydantic-settings.AC1: Type validation at startup
- **130-pydantic-settings.AC1.1 Success:** `Settings()` accepts valid `.env` with correct types and populates all fields
- **130-pydantic-settings.AC1.2 Success:** Bool fields accept `true`/`false`/`1`/`0`/`yes`/`no` case-insensitively
- **130-pydantic-settings.AC1.3 Success:** Int fields (`port`, `thinking_budget`, `lorebook_token_budget`) coerce from string
- **130-pydantic-settings.AC1.4 Failure:** Non-integer string for int field raises `ValidationError`
- **130-pydantic-settings.AC1.5 Failure:** Missing `.env` file and no env vars produces Settings with all defaults (app still boots)

### 130-pydantic-settings.AC2: Startup validation for cross-field rules
- **130-pydantic-settings.AC2.1 Success:** `StytchConfig` with `sso_connection_id` and `public_token` both set passes validation
- **130-pydantic-settings.AC2.2 Failure:** `StytchConfig` with `sso_connection_id` set but `public_token` empty raises `ValidationError`
- **130-pydantic-settings.AC2.3 Success:** `StytchConfig` with neither `sso_connection_id` nor `public_token` passes (both optional)

### 130-pydantic-settings.AC5: .env.example sync
- **130-pydantic-settings.AC5.1 Success:** Every field in Settings model schema has a corresponding entry in `.env.example`
- **130-pydantic-settings.AC5.2 Success:** Every variable in `.env.example` corresponds to a Settings field
- **130-pydantic-settings.AC5.3 Success:** All env var names use double-underscore convention

### 130-pydantic-settings.AC7: Worktree .env fallback
- **130-pydantic-settings.AC7.1 Success:** Settings loads `.env` from current project root in main worktree
- **130-pydantic-settings.AC7.2 Success:** Settings loads main worktree `.env` as fallback when running in `.worktrees/<branch>/`
- **130-pydantic-settings.AC7.3 Success:** Local `.env` in worktree overrides main worktree `.env` values
- **130-pydantic-settings.AC7.4 Success:** `get_settings()` logs which `.env` file(s) were loaded at `INFO` level on first call

### 130-pydantic-settings.AC8: Test isolation
- **130-pydantic-settings.AC8.1 Success:** Tests construct `Settings(_env_file=None, ...)` without reading `.env` or env vars
- **130-pydantic-settings.AC8.2 Success:** `get_settings.cache_clear()` resets singleton for test isolation
- **130-pydantic-settings.AC8.3 Success:** Unit tests for pure functions pass config values as parameters (no Settings dependency)

### 130-pydantic-settings.AC9: Per-worktree database isolation
- **130-pydantic-settings.AC9.1 Success:** On main branch, `database.url` is unchanged after Settings construction
- **130-pydantic-settings.AC9.2 Success:** On branch `130-pydantic-settings`, database name `promptgrimoire` becomes `promptgrimoire_130_pydantic_settings`
- **130-pydantic-settings.AC9.3 Success:** Both `database.url` and `dev.test_database_url` are suffixed
- **130-pydantic-settings.AC9.4 Success:** Branch detection reads `.git/HEAD` (no subprocess, pure filesystem)
- **130-pydantic-settings.AC9.5 Success:** Detached HEAD results in no suffix applied
- **130-pydantic-settings.AC9.6 Success:** Special characters (`/`, `.`, `-`) in branch names are sanitised to underscores
- **130-pydantic-settings.AC9.7 Success:** Long branch names are truncated with deterministic hash suffix (PostgreSQL 63-char identifier limit)
- **130-pydantic-settings.AC9.8 Success:** Suffixing is idempotent — no double-suffix when database URL passes through a subprocess
- **130-pydantic-settings.AC9.9 Success:** URL query parameters are preserved after suffixing
- **130-pydantic-settings.AC9.10 Success:** Setting `DEV__BRANCH_DB_SUFFIX=false` disables suffixing

### 130-pydantic-settings.AC10: Branch-specific database auto-creation
- **130-pydantic-settings.AC10.1 Success:** `ensure_database_exists()` creates a missing database via the `postgres` maintenance database
- **130-pydantic-settings.AC10.2 Success:** `ensure_database_exists()` is idempotent — no error if the database already exists
- **130-pydantic-settings.AC10.3 Success:** `ensure_database_exists()` uses a sync psycopg connection with AUTOCOMMIT isolation

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Rewrite test_env_vars.py to introspect Settings schema

**Verifies:** 130-pydantic-settings.AC5.1, 130-pydantic-settings.AC5.2, 130-pydantic-settings.AC5.3

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/tests/unit/test_env_vars.py`
- Reference: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/src/promptgrimoire/config.py` (created in Phase 1)
- Reference: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/.env.example` (updated in Phase 1)

**Implementation:**

Completely rewrite `test_env_vars.py`. The current implementation (233 lines) scans source code with regex for `os.environ.get()` patterns. Replace with Settings schema introspection.

The core logic: iterate `Settings.model_fields` to find sub-models, then iterate each sub-model's `model_fields` to derive the expected env var name. For `env_nested_delimiter='__'`, field `stytch.project_id` becomes `STYTCH__PROJECT_ID`.

Helper function `_derive_env_var_names(settings_cls)` should:
1. For each field in `Settings.model_fields`: check if field type is a `BaseModel` subclass
2. If sub-model: iterate its `model_fields`, generating `{SUB_MODEL_NAME}__{FIELD_NAME}` (all uppercase)
3. If direct field on Settings: just uppercase the field name
4. Return a set of expected env var names

`_extract_env_vars_from_env_example()` remains similar: parse `.env.example` for non-comment lines with `=`, extract the variable name.

Tests:
- `test_all_settings_fields_in_env_example`: every derived env var name must appear in `.env.example`
- `test_all_env_example_vars_in_settings`: every `.env.example` var name must correspond to a Settings field
- `test_env_var_names_use_double_underscore`: all derived names for nested fields contain `__`
- `test_env_example_has_comments`: each variable in `.env.example` has a comment line above it (preserve existing quality gate)
- Preserve `TestEnvFileSync` class (tests .env matches .env.example) — update var name patterns if needed

**Testing:**
- AC5.1: `test_all_settings_fields_in_env_example` — add a field to Settings, test should fail until .env.example is updated
- AC5.2: `test_all_env_example_vars_in_settings` — add a var to .env.example, test should fail until Settings field exists
- AC5.3: `test_env_var_names_use_double_underscore` — all nested field env vars contain `__` separator

**Verification:**
Run: `uv run pytest tests/unit/test_env_vars.py -v`
Expected: All tests pass

**Commit:** `test: rewrite test_env_vars.py to introspect Settings schema`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add Settings unit tests for validation, isolation, and branch DB isolation

**Verifies:** 130-pydantic-settings.AC1.1, 130-pydantic-settings.AC1.2, 130-pydantic-settings.AC1.3, 130-pydantic-settings.AC1.4, 130-pydantic-settings.AC1.5, 130-pydantic-settings.AC2.1, 130-pydantic-settings.AC2.2, 130-pydantic-settings.AC2.3, 130-pydantic-settings.AC7.1, 130-pydantic-settings.AC7.2, 130-pydantic-settings.AC7.3, 130-pydantic-settings.AC7.4, 130-pydantic-settings.AC8.1, 130-pydantic-settings.AC8.2, 130-pydantic-settings.AC8.3, 130-pydantic-settings.AC9.1, 130-pydantic-settings.AC9.2, 130-pydantic-settings.AC9.3, 130-pydantic-settings.AC9.4, 130-pydantic-settings.AC9.5, 130-pydantic-settings.AC9.6, 130-pydantic-settings.AC9.7, 130-pydantic-settings.AC9.8, 130-pydantic-settings.AC9.9, 130-pydantic-settings.AC9.10, 130-pydantic-settings.AC10.1, 130-pydantic-settings.AC10.2, 130-pydantic-settings.AC10.3

**Files:**
- Create: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/tests/unit/test_settings.py`
- Reference: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/src/promptgrimoire/config.py`
- Reference: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/src/promptgrimoire/db/bootstrap.py`

**Implementation:**

Create `tests/unit/test_settings.py` with test classes organised by AC:

**Class `TestTypeValidation` (AC1):**
- All tests construct `Settings(_env_file=None, ...)` to avoid reading real `.env`
- Test AC1.1: construct with valid typed values, verify all fields populated
- Test AC1.2: construct `DevConfig(auth_mock=v)` for each of `"true"`, `"false"`, `"1"`, `"0"`, `"yes"`, `"no"`, `"True"`, `"FALSE"` — verify bool coercion
- Test AC1.3: construct `AppConfig(port="9090")`, `LlmConfig(thinking_budget="2048")`, `LlmConfig(lorebook_token_budget="500")` — verify int coercion from string
- Test AC1.4: construct `AppConfig(port="not-a-number")` — expect `ValidationError`
- Test AC1.5: construct `Settings(_env_file=None)` with no env vars — verify all defaults are populated, no error

**Class `TestCrossFieldValidation` (AC2):**
- Test AC2.1: `StytchConfig(sso_connection_id="test-id", public_token="test-token")` — passes
- Test AC2.2: `StytchConfig(sso_connection_id="test-id", public_token="")` — raises `ValidationError`
- Test AC2.3: `StytchConfig()` — passes (both None/empty)

**Class `TestWorktreeEnvPaths` (AC7):**
- Test AC7.1: verify `_PROJECT_ROOT / ".env"` is in `Settings.model_config["env_file"]`
- Test AC7.2: verify `_MAIN_WORKTREE_ENV` is in `Settings.model_config["env_file"]`
- Test AC7.3: verify the local `.env` tuple position is AFTER the main worktree position (later overrides earlier)
- Test AC7.4: verify `get_settings()` logs at INFO level — use `caplog` fixture, construct Settings, check log output contains ".env" reference

**Class `TestTestIsolation` (AC8):**
- Test AC8.1: `Settings(_env_file=None, app=AppConfig(port=1234))` — verify `port == 1234`, not read from any env
- Test AC8.2: call `get_settings()` twice — same instance. Call `get_settings.cache_clear()`, call again — different instance
- Test AC8.3: demonstrate pattern — a pure function `def compute_base_url(base_url: str, port: int) -> str` doesn't need Settings. Test it with direct args. (This is a documentation test — shows the pattern.)

**Class `TestBranchDbIsolation` (AC9):**

These tests exercise the pure functions `_current_branch()`, `_branch_db_suffix()`, `_suffix_db_url()`, and the `_apply_branch_db_suffix` model validator. They use `unittest.mock.patch` to mock `_current_branch()` for the validator tests (since the real branch depends on runtime git state).

**Branch detection tests (AC9.4, AC9.5):**
- Test AC9.4: mock `_PROJECT_ROOT / ".git"` as a file containing `gitdir: /some/path` with a HEAD file containing `ref: refs/heads/feature-branch`. Verify `_current_branch()` returns `"feature-branch"`. (Use `tmp_path` to create a fake git structure.)
- Test AC9.4 (main worktree): mock `.git` as a directory with `HEAD` containing `ref: refs/heads/main`. Verify returns `"main"`.
- Test AC9.5: mock HEAD containing a raw SHA (detached). Verify `_current_branch()` returns `None`.

**Suffix derivation tests (AC9.1, AC9.2, AC9.6, AC9.7):**
- Test AC9.1: `_branch_db_suffix("main")` returns `""`. Also test `"master"` and `None`.
- Test AC9.2: `_branch_db_suffix("130-pydantic-settings")` returns `"130_pydantic_settings"`
- Test AC9.6: `_branch_db_suffix("feature/my.branch-name")` returns `"feature_my_branch_name"`
- Test AC9.7: `_branch_db_suffix("a" * 60)` returns a string of at most 40 chars ending with an 8-char hash

**URL suffixing tests (AC9.8, AC9.9):**
- Test basic: `_suffix_db_url("postgresql://u:p@h/mydb", "feature")` returns `"postgresql://u:p@h/mydb_feature"`
- Test AC9.8 (idempotent): `_suffix_db_url("postgresql://u:p@h/mydb_feature", "feature")` returns unchanged
- Test AC9.9 (query params): `_suffix_db_url("postgresql://u:p@h/mydb?host=/tmp", "feature")` preserves `?host=/tmp`
- Test None URL: `_suffix_db_url(None, "feature")` returns `None`
- Test empty suffix: `_suffix_db_url("postgresql://u:p@h/mydb", "")` returns unchanged

**Settings validator tests (AC9.3, AC9.10):**
- Test AC9.3: patch `_current_branch` to return `"130-pydantic-settings"`. Construct `Settings(_env_file=None, database=DatabaseConfig(url="postgresql://u:p@h/pg"), dev=DevConfig(test_database_url="postgresql://u:p@h/pg_test"))`. Verify BOTH URLs are suffixed.
- Test AC9.1 (main): patch `_current_branch` to return `"main"`. Verify URLs unchanged.
- Test AC9.10: patch `_current_branch` to return `"feature"`. Construct `Settings(_env_file=None, dev=DevConfig(branch_db_suffix=False), database=DatabaseConfig(url="postgresql://u:p@h/pg"))`. Verify URL unchanged (opt-out).

**Class `TestEnsureDatabaseExists` (AC10):**

These tests require a real PostgreSQL connection. Use the `TEST_DATABASE_URL` environment variable to determine connectivity. **Skip if no database is available** — these are integration-grade tests in a unit test file.

- Test AC10.1: Generate a unique database name (e.g., `test_ensure_db_{uuid}`). Call `ensure_database_exists()` with a URL pointing to that name. Verify the database was created by connecting to `postgres` and querying `pg_database`. Clean up by dropping the database afterwards.
- Test AC10.2: Call `ensure_database_exists()` twice with the same URL. Verify no error on second call.
- Test AC10.3: Verify the function uses psycopg (sync). This is a code inspection test — verify `ensure_database_exists` imports `psycopg` (not `asyncpg`). Alternatively, just confirm the function completes without an event loop.
- Test no-op: `ensure_database_exists(None)` returns without error. `ensure_database_exists("")` returns without error.

**Testing:**
Each test maps to a specific AC case. Tests must use `Settings(_env_file=None, ...)` — never read from `.env` or `os.environ`. Branch detection tests use `tmp_path` for fake git structures. Validator tests use `unittest.mock.patch` on `_current_branch`. DB creation tests require PostgreSQL and are skipped if unavailable.

**Verification:**
Run: `uv run pytest tests/unit/test_settings.py -v`
Expected: All tests pass (DB creation tests may be skipped if no PostgreSQL)

**Commit:** `test: add Settings unit tests for validation, isolation, and branch DB isolation`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_3 -->
### Task 3: Update conftest.py and early-migrate _pre_test_db_cleanup() in cli.py

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/tests/conftest.py`
  - Line 18: remove `from dotenv import load_dotenv` import
  - Line 25: remove `load_dotenv()` call
  - Lines 146-178: update `db_schema_guard` fixture to use `get_settings()`
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/src/promptgrimoire/cli.py`
  - Lines 23-77: early-migrate `_pre_test_db_cleanup()` to use Settings + ensure_database_exists

**Implementation:**

**conftest.py changes:**

1. Remove `from dotenv import load_dotenv` (line 18) and `load_dotenv()` (line 25)
2. Add `from promptgrimoire.config import get_settings` import
3. Update `db_schema_guard` fixture:
   - Replace `os.environ.get("TEST_DATABASE_URL")` with `get_settings().dev.test_database_url`
   - **Bridge pattern (transitional):** Continue setting `os.environ["DATABASE_URL"]` from the test URL so un-migrated code (db/engine.py, db/bootstrap.py, etc.) still reads it during Phases 3-6
   - Add `get_settings.cache_clear()` in the fixture teardown so test isolation is maintained
4. The `_SERVER_SCRIPT` subprocess code (lines 291-314) still uses old env var names — this is expected, it will be updated in Phase 6 when all app code is migrated

**Important:** Do NOT change the integration test `pytestmark` skip guards (`os.environ.get("TEST_DATABASE_URL")`) — those files read from os.environ which is still set by the bridge. They'll be migrated when their respective modules are migrated.

**cli.py _pre_test_db_cleanup() early migration:**

**WHY early migration:** `_pre_test_db_cleanup()` runs BEFORE pytest (called by `_run_pytest()` at line 86). If it uses unsuffixed URLs while conftest uses suffixed URLs, Alembic migrates the wrong database. The two must use the same URL derivation from Phase 2 onwards.

Update `_pre_test_db_cleanup()` (lines 23-77):

1. Remove: `from dotenv import load_dotenv` (line 32) and `load_dotenv()` (line 34)
2. Add at top of function:
   ```python
   from promptgrimoire.config import get_settings
   from promptgrimoire.db.bootstrap import ensure_database_exists
   ```
3. Replace `test_database_url = os.environ.get("TEST_DATABASE_URL")` (line 36) with:
   ```python
   test_database_url = get_settings().dev.test_database_url
   ```
   Note: `get_settings()` triggers the `_apply_branch_db_suffix` validator, so `test_database_url` is already suffixed with the branch name if applicable.
4. After getting `test_database_url`, call `ensure_database_exists(test_database_url)` to auto-create the branch-specific database if it doesn't exist yet.
5. Replace `os.environ["DATABASE_URL"] = test_database_url` (line 41) with:
   ```python
   # Set BOTH env vars for bridge: DATABASE__URL (for Settings) and
   # DATABASE_URL (for Alembic pre-Phase 6 — alembic/env.py still uses old name)
   os.environ["DATABASE__URL"] = test_database_url
   os.environ["DATABASE_URL"] = test_database_url
   get_settings.cache_clear()  # Force Settings to re-read with new env var
   ```
6. Keep `import os` — still needed for `os.environ` assignment.

**Verification:**
Run: `uv run test-all`
Expected: All 2354+ tests pass. No `load_dotenv` import in conftest.py. `_pre_test_db_cleanup()` uses `get_settings()`.

Run: `uv run ruff check tests/conftest.py src/promptgrimoire/cli.py`
Expected: No lint errors

**Commit:** `refactor: remove load_dotenv from conftest, early-migrate _pre_test_db_cleanup to Settings`
<!-- END_TASK_3 -->
