# Pydantic-Settings Migration — Phase 5: LLM, Roleplay, and Logviewer Migration

**Goal:** Replace module-level env var constants in LLM client, prompt assembly, roleplay, and logviewer with Settings access at call sites. Apply functional core pattern: pure functions/classes take config values as parameters, page handlers (imperative shell) call `get_settings()` and inject.

**Architecture:** `ClaudeClient` drops its `os.environ` fallback — callers must pass `api_key`, `model`, `thinking_budget`, and `lorebook_budget`. `build_system_prompt()` already accepts `lorebook_budget` parameter — the module-level constant is removed. Page modules (`roleplay.py`, `logviewer.py`) read from `get_settings()` at function call time instead of module import time.

**Tech Stack:** pydantic-settings v2, anthropic SDK

**Scope:** 7 phases from original design (phase 5 of 7)

**Codebase verified:** 2026-02-13

---

## Acceptance Criteria Coverage

This phase implements and tests:

### 130-pydantic-settings.AC1: Type validation at startup
- **130-pydantic-settings.AC1.3 Success:** (partial) Int fields `thinking_budget` and `lorebook_token_budget` coerce from string via Settings

### 130-pydantic-settings.AC4: SecretStr for sensitive fields
- **130-pydantic-settings.AC4.2 Success:** (partial) `llm.api_key.get_secret_value()` passes actual API key to `ClaudeClient`

### 130-pydantic-settings.AC6: load_dotenv elimination (partial)
- No `os.environ` calls remain in llm/ or pages/roleplay.py or pages/logviewer.py

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Remove os.environ fallback from ClaudeClient, add lorebook_budget parameter

**Verifies:** 130-pydantic-settings.AC4.2 (partial — SecretStr for api_key)

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/src/promptgrimoire/llm/client.py`

**Implementation:**

Update `src/promptgrimoire/llm/client.py`:

1. **Import changes** (top of file):
   - Remove: `import os` (line 6)

2. **`ClaudeClient.__init__`** (lines 28-50):
   - Change `api_key` parameter from `str | None = None` to `str` (required, no default)
   - Remove the `os.environ.get("ANTHROPIC_API_KEY")` fallback (line 44)
   - Add `lorebook_budget: int = 0` parameter
   - Store as `self.lorebook_budget = lorebook_budget`
   - Update error message: `"API key required. Set ANTHROPIC_API_KEY or pass api_key."` → `"API key is required. Configure LLM__API_KEY in .env or pass api_key parameter."`
   - Update docstring to remove reference to `ANTHROPIC_API_KEY` env var

   Updated `__init__`:
   ```python
   def __init__(
       self,
       api_key: str,
       model: str = "claude-sonnet-4-20250514",
       thinking_budget: int = 0,
       lorebook_budget: int = 0,
   ) -> None:
       if not api_key:
           msg = "API key is required. Configure LLM__API_KEY in .env or pass api_key parameter."
           raise ValueError(msg)

       self.api_key = api_key
       self.model = model
       self.thinking_budget = thinking_budget
       self.lorebook_budget = lorebook_budget
       self._client = anthropic.AsyncAnthropic(api_key=self.api_key)
   ```

3. **`send_message` method** (lines 72-74):
   - Pass `lorebook_budget=self.lorebook_budget` to `build_system_prompt()`:
     ```python
     system_prompt = build_system_prompt(
         session.character, activated, user_name=session.user_name,
         lorebook_budget=self.lorebook_budget,
     )
     ```

4. **`stream_message` method** (if it also calls `build_system_prompt`):
   - Apply same change — pass `lorebook_budget=self.lorebook_budget`

**Testing:**
Existing `tests/unit/test_claude_client.py` tests will need updating:
- Tests that construct `ClaudeClient(project_id="...", secret="...")` must now pass `api_key="..."` as first positional arg
- Tests that rely on env var fallback (`monkeypatch.setenv("ANTHROPIC_API_KEY", ...)`) must switch to parameter injection

**Verification:**
Run: `uv run ruff check src/promptgrimoire/llm/client.py`
Expected: No lint errors

Verify no `os.environ` references remain:
Run: `grep -n "os.environ\|import os" src/promptgrimoire/llm/client.py`
Expected: No output
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Remove LOREBOOK_TOKEN_BUDGET module-level constant from prompt.py

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/src/promptgrimoire/llm/prompt.py`

**Implementation:**

Update `src/promptgrimoire/llm/prompt.py`:

1. **Import changes** (top of file):
   - Remove: `import os` (line 5)

2. **Remove module-level constant** (lines 15-17):
   - Delete: `# Token budget for lorebook entries ...`
   - Delete: `LOREBOOK_TOKEN_BUDGET = int(os.environ.get("LOREBOOK_TOKEN_BUDGET", "0"))`

3. **`build_system_prompt` function** (line 88):
   - Replace `budget = lorebook_budget or LOREBOOK_TOKEN_BUDGET` with `budget = lorebook_budget`
   - The `lorebook_budget` parameter already exists with default `0` (line 66)
   - With the constant removed, callers MUST pass the budget explicitly if they want a non-zero value. The ClaudeClient (updated in Task 1) passes `self.lorebook_budget` from its constructor.

**Verification:**
Run: `uv run ruff check src/promptgrimoire/llm/prompt.py`
Expected: No lint errors

Verify no `os.environ` references remain:
Run: `grep -n "os.environ\|import os\|LOREBOOK_TOKEN_BUDGET" src/promptgrimoire/llm/prompt.py`
Expected: No matches for `os.environ` or `import os`. `LOREBOOK_TOKEN_BUDGET` should not appear.

**Commit (Tasks 1-2):** `refactor: remove os.environ from llm module, require parameter injection`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_3 -->
### Task 3: Migrate pages/roleplay.py — module-level constants to get_settings()

**Verifies:** 130-pydantic-settings.AC1.3 (partial — thinking_budget, lorebook_token_budget int coercion)

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/src/promptgrimoire/pages/roleplay.py`
- Reference: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/src/promptgrimoire/config.py`

**Implementation:**

Update `src/promptgrimoire/pages/roleplay.py`:

1. **Import changes** (top of file):
   - Remove: `import os` (line 11)
   - Add: `from promptgrimoire.config import get_settings`

2. **Remove module-level constants** (lines 28-35):
   - Delete: `LOG_DIR = Path(os.environ.get("ROLEPLAY_LOG_DIR", "logs/sessions"))` (line 29)
   - Delete: `CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")` (line 32)
   - Delete: `THINKING_BUDGET = int(os.environ.get("CLAUDE_THINKING_BUDGET", "1024"))` (line 35)
   - Delete the associated comments

3. **Update `_setup_session` function** (around lines 147-168):
   - At the start of the function, read settings:
     ```python
     settings = get_settings()
     log_dir = settings.app.log_dir
     ```
   - Replace `LOG_DIR.mkdir(...)` (line 158) with `log_dir.mkdir(parents=True, exist_ok=True)`
   - Replace `LOG_DIR / generate_log_filename(session)` (line 159) with `log_dir / generate_log_filename(session)`
   - Replace the ClaudeClient construction (line 167):
     ```python
     client = ClaudeClient(
         api_key=settings.llm.api_key.get_secret_value(),
         model=settings.llm.model,
         thinking_budget=settings.llm.thinking_budget,
         lorebook_budget=settings.llm.lorebook_token_budget,
     )
     ```

**Verification:**
Run: `uv run ruff check src/promptgrimoire/pages/roleplay.py`
Expected: No lint errors

Verify no `os.environ` or module-level constants remain:
Run: `grep -n "os.environ\|import os\|LOG_DIR\|CLAUDE_MODEL\|THINKING_BUDGET" src/promptgrimoire/pages/roleplay.py`
Expected: No matches for env var patterns. `LOG_DIR`, `CLAUDE_MODEL`, `THINKING_BUDGET` as module-level constants should not appear.

**Commit:** `refactor: migrate roleplay page from env var constants to Settings`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Migrate pages/logviewer.py — module-level LOG_DIR to get_settings()

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/src/promptgrimoire/pages/logviewer.py`
- Reference: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/src/promptgrimoire/config.py`

**Implementation:**

Update `src/promptgrimoire/pages/logviewer.py`:

1. **Import changes** (top of file):
   - Remove: `import os` (line 13)
   - Add: `from promptgrimoire.config import get_settings`

2. **Remove module-level constant** (line 23):
   - Delete: `LOG_DIR = Path(os.environ.get("ROLEPLAY_LOG_DIR", "logs/sessions"))`

3. **Update all `LOG_DIR` references** to use local variable from Settings:
   - In `logs_page()` function (or wherever LOG_DIR is used), add at the start:
     ```python
     log_dir = get_settings().app.log_dir
     ```
   - Replace all `LOG_DIR` references with `log_dir` throughout the function

**Verification:**
Run: `uv run ruff check src/promptgrimoire/pages/logviewer.py`
Expected: No lint errors

Verify no `os.environ` references remain:
Run: `grep -n "os.environ\|import os\|^LOG_DIR" src/promptgrimoire/pages/logviewer.py`
Expected: No output

**Commit:** `refactor: migrate logviewer page from env var constant to Settings`
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Update LLM tests for parameter injection pattern

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/tests/unit/test_claude_client.py`

**Implementation:**

Update tests in `test_claude_client.py` that construct `ClaudeClient`:

1. **Tests that construct ClaudeClient directly:**
   - Find all `ClaudeClient(...)` constructions
   - Ensure `api_key` is passed as first positional arg (now required, was optional)
   - Example: `ClaudeClient(api_key="test-key", model="test-model", thinking_budget=1024)`

2. **Tests that use monkeypatch.setenv("ANTHROPIC_API_KEY", ...):**
   - Replace with direct parameter injection: pass `api_key="test-key"` in constructor
   - Remove `monkeypatch.setenv` calls for `ANTHROPIC_API_KEY`

3. **Tests for missing API key:**
   - Update to test that `ClaudeClient(api_key="")` or `ClaudeClient(api_key="")` raises `ValueError`
   - Remove tests that check env var fallback (no longer exists)

**Verification:**
Run: `uv run pytest tests/unit/test_claude_client.py -v`
Expected: All tests pass

Run: `uv run test-all`
Expected: All 2354+ tests pass

**Commit:** `test: update LLM tests for parameter injection pattern`
<!-- END_TASK_5 -->
