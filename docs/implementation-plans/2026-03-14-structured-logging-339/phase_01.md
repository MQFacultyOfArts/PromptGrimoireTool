# Structured Logging Implementation Plan

**Goal:** Replace PromptGrimoire's plain-text logging with structured JSON logging via structlog, with automatic request context and Discord alerting.

**Architecture:** structlog's ProcessorFormatter intercepts all stdlib logging calls and renders them as JSON. New code uses `structlog.get_logger()`. Per-request context (`user_id`, `workspace_id`) via `structlog.contextvars`. Discord webhook processor fires on ERROR/CRITICAL.

**Tech Stack:** structlog 25.x, Python stdlib logging, pydantic-settings, Discord webhooks (httpx)

**Scope:** 7 phases from original design (phases 1-7)

**Codebase verified:** 2026-03-14

---

## Acceptance Criteria Coverage

This phase implements and tests:

### structured-logging-339.AC6: Log file operations
- **structured-logging-339.AC6.1 Success:** Single log file per instance (isolated by branch slug via `_branch_db_suffix()`), append mode, rotated at 10MB with 5 backups
- **structured-logging-339.AC6.2 Success:** Log file permissions are `0644` (owner-writable, world-readable)
- **structured-logging-339.AC6.3 Success:** Each line is valid JSON parseable by `jq`
- **structured-logging-339.AC6.4 Edge:** Application restart appends to existing log file (no clobbering)
- **structured-logging-339.AC6.5 Success:** Production instance writes to `logs/promptgrimoire.jsonl`; branch instance writes to `logs/promptgrimoire-{slug}.jsonl`

### structured-logging-339.AC7: Traceback policy
- **structured-logging-339.AC7.1 Success:** DEBUG and INFO log lines contain no traceback even when called inside an `except` block
- **structured-logging-339.AC7.2 Success:** WARNING, ERROR, and CRITICAL log lines include full traceback when an exception is active
- **structured-logging-339.AC7.3 Success:** Context fields (`user_id`, `workspace_id`, `request_path`) are logged as `null` when unavailable, never silently omitted

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: Add structlog dependency and AlertingConfig

**Files:**
- Modify: `pyproject.toml` (dependencies section, ~line 19)
- Modify: `src/promptgrimoire/config.py` (add AlertingConfig sub-model, add to Settings)

**Implementation:**

Add `structlog>=25.0` to the `[project.dependencies]` list in `pyproject.toml`.

In `src/promptgrimoire/config.py`, add a new `AlertingConfig` sub-model following the existing pattern (e.g. `StytchConfig`, `DatabaseConfig`):

```python
class AlertingConfig(BaseModel):
    """Error alerting configuration."""
    discord_webhook_url: str = ""
```

Add it to the `Settings` class alongside the existing sub-models:

```python
alerting: AlertingConfig = AlertingConfig()
```

Update `AppConfig.log_dir` default from `Path("logs/sessions")` to `Path("logs")` to match the structured logging design.

**Verification:**

Run: `uv sync`
Expected: Dependencies install without errors, structlog is available.

Run: `uv run python -c "import structlog; print(structlog.__version__)"`
Expected: Version 25.x printed.

Run: `uv run ruff check src/promptgrimoire/config.py`
Expected: No lint errors.

**Commit:** `feat: add structlog dependency and AlertingConfig`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Rewrite _setup_logging() with structlog

**Verifies:** structured-logging-339.AC6.1, structured-logging-339.AC6.2, structured-logging-339.AC6.3, structured-logging-339.AC6.4, structured-logging-339.AC6.5, structured-logging-339.AC7.1, structured-logging-339.AC7.2, structured-logging-339.AC7.3

**Files:**
- Modify: `src/promptgrimoire/__init__.py` (replace `_setup_logging()` at lines 41-74)

**Implementation:**

Replace the existing `_setup_logging()` function with a structlog-based implementation. The function should:

1. Import structlog and configure it with `structlog.configure()`.

2. Create a custom processor `add_global_fields` that injects `pid` (from `os.getpid()`), `branch` (from `get_current_branch()`), and `commit` (from `get_git_commit()`) into every event dict. These are computed once at startup and closed over.

3. Create a level-gated traceback processor: for DEBUG and INFO events, strip any `exc_info` key from the event dict. For WARNING and above, let `structlog.processors.format_exc_info` handle it normally. This enforces AC7.1 and AC7.2.

4. Derive the log file path using `settings.app.log_dir` and `_branch_db_suffix()`:
   - Import `get_settings` and `_branch_db_suffix`, `get_current_branch`
   - `suffix = _branch_db_suffix(get_current_branch())`
   - If suffix is empty: `log_dir / "promptgrimoire.jsonl"`
   - If suffix exists: `log_dir / f"promptgrimoire-{suffix}.jsonl"`

5. Create the log directory with `log_dir.mkdir(parents=True, exist_ok=True)`.

6. Set up two stdlib logging handlers:
   - **File handler:** `RotatingFileHandler` with `maxBytes=10*1024*1024`, `backupCount=5`, `encoding="utf-8"`, level DEBUG. Use `structlog.stdlib.ProcessorFormatter` with `structlog.processors.JSONRenderer()` as the processor. Set `foreign_pre_chain` to handle third-party library logs.
   - **Console handler:** `StreamHandler(sys.stderr)` with level INFO. Use `structlog.stdlib.ProcessorFormatter` with `structlog.dev.ConsoleRenderer()` as the processor.

7. Set file permissions to 0o644 after handler creation: `os.chmod(log_file_path, 0o644)`.

8. Configure the root stdlib logger with both handlers, level DEBUG.

9. Call `structlog.configure()` with processor chain:
   - `structlog.contextvars.merge_contextvars` (first — for per-request context in later phases)
   - `structlog.stdlib.add_log_level`
   - `structlog.processors.TimeStamper(fmt="iso", utc=True)`
   - `add_global_fields` (custom processor)
   - Traceback policy processor
   - `structlog.stdlib.ProcessorFormatter.wrap_for_formatter()` (last — hands off to formatter)

   Set `logger_factory=structlog.stdlib.LoggerFactory()` and `cache_logger_on_first_use=True`.

10. Ensure null context fields: The `merge_contextvars` processor naturally omits unbound vars. To satisfy AC7.3 (context fields logged as `null` when unavailable), add a processor after `merge_contextvars` that sets `user_id`, `workspace_id`, `request_path` to `None` if not already present in the event dict.

The existing `main()` call to `_setup_logging()` at line 83 remains unchanged.

**Testing:**

Tests must verify each AC listed above:
- structured-logging-339.AC6.1: Test that log file path is branch-isolated and uses RotatingFileHandler with correct maxBytes/backupCount
- structured-logging-339.AC6.2: Test that log file has 0o644 permissions after setup
- structured-logging-339.AC6.3: Test that a log call produces valid JSON output (parse with `json.loads`)
- structured-logging-339.AC6.4: Test that calling `_setup_logging()` twice doesn't clobber existing content (append mode)
- structured-logging-339.AC6.5: Test file naming: empty suffix -> `promptgrimoire.jsonl`, branch suffix -> `promptgrimoire-{slug}.jsonl`
- structured-logging-339.AC7.1: Test that INFO-level log inside an except block has no traceback in output
- structured-logging-339.AC7.2: Test that ERROR-level log inside an except block includes traceback
- structured-logging-339.AC7.3: Test that log output includes `user_id: null`, `workspace_id: null`, `request_path: null` when no context is bound

Follow project testing patterns. Task-implementor generates actual test code at execution time.

**Verification:**

Run: `uv run grimoire test all`
Expected: All tests pass

Run: `uv run ruff check src/promptgrimoire/__init__.py && uvx ty check`
Expected: No lint or type errors

**Commit:** `feat: rewrite _setup_logging() with structlog ProcessorFormatter`

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Verify end-to-end JSON output

**Verifies:** structured-logging-339.AC6.3, structured-logging-339.AC6.5, structured-logging-339.AC7.3

**Files:**
- Test: `tests/unit/test_structured_logging.py` (unit)

**Implementation:**

Write an integration-style unit test that:
1. Calls `_setup_logging()` with a temporary directory as log_dir (use `tmp_path` fixture and monkeypatch `get_settings()`)
2. Gets a stdlib logger via `logging.getLogger("test.module")`
3. Calls `logger.info("test event", extra={"custom_key": "value"})`
4. Reads the log file
5. Parses each line as JSON
6. Asserts presence of: `pid`, `branch`, `commit`, `level`, `timestamp`, `event`
7. Asserts `user_id`, `workspace_id`, `request_path` are `null` (AC7.3)

Also test that a structlog logger (`structlog.get_logger()`) produces the same JSON format with the same fields.

**Testing:**

- structured-logging-339.AC6.3: Parse output line as JSON — `json.loads(line)` must not raise
- structured-logging-339.AC6.5: Verify filename matches expected pattern
- structured-logging-339.AC7.3: Assert `parsed["user_id"] is None` etc.

Follow project testing patterns. Task-implementor generates actual test code at execution time.

**Verification:**

Run: `uv run grimoire test run tests/unit/test_structured_logging.py`
Expected: All tests pass

**Commit:** `test: verify structured logging JSON output and null context fields`

<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->

## UAT Steps

1. Start the app: `uv run run.py`
2. Navigate to any page (e.g. login page)
3. Run: `ls logs/promptgrimoire*.jsonl` — verify log file exists
4. Run: `tail -1 logs/promptgrimoire*.jsonl | python -m json.tool` — verify valid JSON
5. Verify JSON contains: `pid`, `branch`, `commit`, `level`, `timestamp`, `event`
6. Verify JSON contains: `user_id: null`, `workspace_id: null`, `request_path: null` (no context bound yet)
7. Stop the app, start it again. Run: `wc -l logs/promptgrimoire*.jsonl` — verify line count increased (append mode, not clobbered)
8. Run: `stat -c '%a' logs/promptgrimoire*.jsonl` — verify permissions are `644`
