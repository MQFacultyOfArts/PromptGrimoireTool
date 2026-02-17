# Pydantic-Settings Migration — Phase 7: Cleanup and Dependency Removal

**Goal:** Remove direct python-dotenv usage from dependencies (if possible), perform codebase-wide sweep for stragglers, update test patterns for new env var names, and verify complete migration.

**Architecture:** After Phases 1-6, all `load_dotenv()` and `os.environ.get()` calls in application code are eliminated. This phase verifies completeness, cleans up test patterns that still reference old env var names, and handles the python-dotenv dependency decision.

**Tech Stack:** pydantic-settings v2 (python-dotenv is required transitive dependency)

**Scope:** 7 phases from original design (phase 7 of 7)

**Codebase verified:** 2026-02-13

---

## Acceptance Criteria Coverage

This phase verifies ALL acceptance criteria are met:

### 130-pydantic-settings.AC6: load_dotenv elimination (final verification)
- **130-pydantic-settings.AC6.1 Success:** Zero `load_dotenv()` calls in application code, test code, or Alembic
- **130-pydantic-settings.AC6.2 Success:** Zero `os.environ.get()` or `os.environ[]` calls in application code (excluding legitimate subprocess env inheritance)
- **130-pydantic-settings.AC6.3 Success:** pydantic-settings reads `.env` natively without explicit `load_dotenv()`

---

<!-- START_TASK_1 -->
### Task 1: Decide python-dotenv dependency status and update pyproject.toml

**Verifies:** 130-pydantic-settings.AC6.3

**Files:**
- Modify (potentially): `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/pyproject.toml`

**Implementation:**

python-dotenv is a **required** dependency of pydantic-settings (not optional). After migration, there are zero direct `from dotenv import load_dotenv` calls in the codebase. However, pydantic-settings imports python-dotenv internally for `.env` file reading.

**Decision: Keep `python-dotenv>=1.0` as a direct dependency in pyproject.toml.**

Rationale:
- pydantic-settings requires it — removing it would cause `uv sync` to still install it as transitive dependency
- Keeping it explicit documents the dependency chain (documentation-as-code)
- Prevents confusion when developers see `dotenv` used in pydantic-settings but not in our deps list
- Add a comment in pyproject.toml: `# Required by pydantic-settings for .env file reading`

**Verification:**
Run: `uv sync`
Expected: Success, python-dotenv still installed

Run: `grep -rn "from dotenv\|import dotenv" src/ tests/ alembic/`
Expected: Zero matches (no direct imports)
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Codebase-wide sweep for remaining os.environ, os.getenv, load_dotenv

**Verifies:** 130-pydantic-settings.AC6.1, 130-pydantic-settings.AC6.2

**Files:**
- Various (fix any stragglers found)

**Implementation:**

Run comprehensive sweep:

```bash
# Application code — should be zero
grep -rn "os\.environ\|os\.getenv\|load_dotenv" src/promptgrimoire/ --include="*.py"

# Test code — may have legitimate uses
grep -rn "os\.environ\|os\.getenv\|load_dotenv" tests/ --include="*.py"

# Alembic — should be zero
grep -rn "os\.environ\|os\.getenv\|load_dotenv" alembic/ --include="*.py"
```

**Expected legitimate matches (not to be removed):**
- `src/promptgrimoire/cli.py`: `os.environ["DATABASE__URL"] = ...` — subprocess env assignment
- `src/promptgrimoire/db/bootstrap.py`: `env=dict(os.environ)` — subprocess env pass-through
- `tests/conftest.py`: `os.environ["DATABASE__URL"] = ...` — test bridge pattern

**Unexpected matches to fix:**
- Any `os.environ.get("OLD_NAME")` patterns — replace with Settings access
- Any `load_dotenv()` calls — remove (Settings reads `.env` natively)
- Any old env var name references in error messages — update to new names

**Verification:**
Run: `uv run test-all`
Expected: All tests pass after any fixes
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Update integration test skipif patterns for new env var names

**Files:**
- Modify (potentially): Multiple integration test files in `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/tests/integration/`

**Implementation:**

Integration tests use `@pytest.mark.skipif` guards that check for env vars:

```python
pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set",
)
```

These patterns check environment variables directly. After migration, they should be updated to check Settings:

```python
from promptgrimoire.config import get_settings

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)
```

**Important:** The `skipif` decorator evaluates at import time (when pytest collects tests). Since `get_settings()` is cached and reads from `.env` file, this works correctly — it reads the `.env` file once and caches the result.

Scan all integration test files:

```bash
grep -rn "os.environ" tests/integration/ --include="*.py"
```

Update each match. Also update the `_SERVER_SCRIPT` subprocess environment setup in conftest.py (lines 291-314) to use new env var names if it sets old-name variables for the test server subprocess.

**Verification:**
Run: `uv run test-all`
Expected: All tests pass

Run: `grep -rn "os\.environ" tests/ --include="*.py"`
Expected: Only legitimate subprocess env operations (conftest bridge, _SERVER_SCRIPT)
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Update _SERVER_SCRIPT subprocess env vars in conftest.py

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/tests/conftest.py`
  - Lines 291-314: `_SERVER_SCRIPT` sets env vars for subprocess test server

**Implementation:**

The `_SERVER_SCRIPT` section in conftest.py sets environment variables using old names for the test server subprocess:
- `AUTH_MOCK` → should be `DEV__AUTH_MOCK`
- `STORAGE_SECRET` → should be `APP__STORAGE_SECRET`
- `STYTCH_SSO_CONNECTION_ID` → should be `STYTCH__SSO_CONNECTION_ID`
- `STYTCH_PUBLIC_TOKEN` → should be `STYTCH__PUBLIC_TOKEN`

Update all old-name env var references to new double-underscore names.

**Verification:**
Run: `grep -n "AUTH_MOCK\|STORAGE_SECRET\|STYTCH_" tests/conftest.py`
Expected: Only new-name patterns with double underscores

Run: `uv run test-all`
Expected: All tests pass

**Commit (Tasks 1-4):** `chore: complete pydantic-settings migration cleanup`
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Final verification — full test suite and lint

**Verifies:** All ACs (final gate)

**Files:**
- No modifications — verification only

**Implementation:**

Run the full verification battery:

1. **Test suite:**
   ```bash
   uv run test-all
   ```
   Expected: All 2354+ tests pass

2. **Linting:**
   ```bash
   uv run ruff check .
   ```
   Expected: No lint errors

3. **Type checking:**
   ```bash
   uvx ty check
   ```
   Expected: No type errors

4. **Settings construction smoke test:**
   ```bash
   uv run python -c "
   from promptgrimoire.config import Settings, get_settings
   s = Settings(_env_file=None)
   print(f'port={s.app.port}, model={s.llm.model}')
   print(f'secret masked: {s.stytch.secret}')
   print(f'secret value: {s.stytch.secret.get_secret_value()}')
   print('All defaults valid')
   "
   ```
   Expected: Prints defaults, secret is masked in str(), get_secret_value() returns empty string

5. **No old env var patterns:**
   ```bash
   grep -rn "ANTHROPIC_API_KEY\|CLAUDE_MODEL\|CLAUDE_THINKING_BUDGET\|ROLEPLAY_LOG_DIR\|PROMPTGRIMOIRE_PORT\|AUTH_MOCK[^_]\|DATABASE_ECHO[^_]\|DATABASE_URL[^_]" src/ --include="*.py"
   ```
   Expected: Zero matches (all old-name patterns replaced)

**Commit:** No commit needed — verification only
<!-- END_TASK_5 -->
