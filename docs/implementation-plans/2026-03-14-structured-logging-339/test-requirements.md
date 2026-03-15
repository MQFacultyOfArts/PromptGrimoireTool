# Test Requirements — Structured Logging (#339)

Generated from the Acceptance Criteria in the [design plan](../../design-plans/2026-03-14-structured-logging-339.md).

---

## AC1: Log lines carry request context

**Implementation phase:** Phase 3 (Context propagation)

### structured-logging-339.AC1.1

- **AC text:** Log line from an authenticated page handler contains `user_id`, `request_path`, `pid`, `branch`, `commit`
- **Type:** Success
- **Test file:** `tests/unit/test_structured_logging.py`
- **Test approach:** Unit test. Configure structlog with temp log dir, bind contextvars with a test user_id and request_path, emit a log line, parse the JSON output.
- **Key assertions:**
  - Parsed JSON contains `user_id` equal to the bound value (not `null`)
  - Parsed JSON contains `request_path` equal to the bound route
  - Parsed JSON contains `pid` (integer, matches `os.getpid()`)
  - Parsed JSON contains `branch` (string, non-null)
  - Parsed JSON contains `commit` (string, non-null)

### structured-logging-339.AC1.2

- **AC text:** Log line from an annotation workspace handler additionally contains `workspace_id`
- **Type:** Success
- **Test file:** `tests/unit/test_structured_logging.py`
- **Test approach:** Unit test. Bind `workspace_id` via `bind_contextvars()`, emit a log line, parse JSON output.
- **Key assertions:**
  - Parsed JSON contains `workspace_id` equal to the bound UUID string
  - `user_id` and `request_path` are also present (from prior binding)

### structured-logging-339.AC1.3

- **AC text:** `jq 'select(.workspace_id == "XXX")' logs/promptgrimoire.jsonl` returns all events for that workspace
- **Type:** Success
- **Test file:** `tests/unit/test_structured_logging.py`
- **Test approach:** Unit test. Bind a workspace_id, emit multiple log lines, read all lines from the temp log file, filter by `workspace_id`, assert all matching lines share the same value.
- **Key assertions:**
  - Multiple log lines exist with the bound `workspace_id`
  - Filtering by `workspace_id` returns exactly the expected count
  - No lines with a different `workspace_id` appear in the filtered set

### structured-logging-339.AC1.4

- **AC text:** Log line from unauthenticated page (e.g. login) has `user_id: null` but still has `pid`, `branch`, `commit`, `request_path`
- **Type:** Edge
- **Test file:** `tests/unit/test_structured_logging.py`
- **Test approach:** Unit test. Call `clear_contextvars()`, then `bind_contextvars(request_path="/login")` without binding `user_id`, emit a log line, parse JSON.
- **Key assertions:**
  - `user_id` is `null` (None)
  - `request_path` equals `"/login"`
  - `pid`, `branch`, `commit` are present and non-null

---

## AC2: Module migration and print guard

**Implementation phase:** Phase 2 (ast-grep migration + guard test)

### structured-logging-339.AC2.1

- **AC text:** All modules in `src/promptgrimoire/` use `structlog.get_logger()` with explicit log level set
- **Type:** Success
- **Test file:** N/A (verified by ast-grep scan during Phase 2 Task 2, spot-checked by PR reviewer)
- **Test approach:** Manual verification. After migration, run ast-grep to confirm no remaining `logging.getLogger(__name__)` calls outside `__init__.py`. PR reviewer spot-checks 3-5 files for `setLevel()` calls matching the module category table.
- **Key assertions:**
  - `sg --pattern 'logging.getLogger($$$)' --lang python src/promptgrimoire/` returns only `__init__.py` and files that re-import `logging` for `setLevel()`
  - Each migrated file has a `setLevel()` call at module level

### structured-logging-339.AC2.2

- **AC text:** Guard test fails if a `print()` call is added to any `.py` file under `src/promptgrimoire/`
- **Type:** Success
- **Test file:** `tests/unit/test_print_usage_guard.py`
- **Test approach:** Guard test (AST-scanning). Parses all `.py` files under `src/promptgrimoire/` (excluding `cli/`), walks AST for `ast.Call` nodes where `func` is `ast.Name` with `id == "print"`.
- **Key assertions:**
  - Zero violations found across all scanned files
  - The test itself IS the verification -- passing means no `print()` calls exist

### structured-logging-339.AC2.3

- **AC text:** Existing stdlib `logging.getLogger()` calls from third-party libraries (NiceGUI, SQLAlchemy) produce JSON output through ProcessorFormatter
- **Type:** Success
- **Test file:** `tests/unit/test_structured_logging.py`
- **Test approach:** Unit test. Configure `_setup_logging()` with temp dir, create a stdlib logger simulating a third-party library (`logging.getLogger("nicegui.helpers")`), emit a warning, read and parse the log file.
- **Key assertions:**
  - Output line is valid JSON (`json.loads()` succeeds)
  - JSON contains standard fields: `level`, `timestamp`, `event`, `pid`, `branch`, `commit`
  - JSON structure matches structlog-originated events

### structured-logging-339.AC2.4

- **AC text:** Guard test produces clear error message identifying file and line number of offending `print()`
- **Type:** Failure
- **Test file:** `tests/unit/test_print_usage_guard.py`
- **Test approach:** Guard test error format verification. Temporarily add a `print()` to a source file, run the guard test, inspect the assertion error message, then remove the test line.
- **Key assertions:**
  - Error message contains the file path of the offending file
  - Error message contains the line number of the `print()` call
  - Error message format matches `"{relative_path}:{line_number} -- print() call; use structlog logger instead"`

---

## AC3: Export pipeline instrumentation

**Implementation phase:** Phase 5 (Export pipeline instrumentation)

### structured-logging-339.AC3.1

- **AC text:** Successful PDF export produces log events for each stage (`pandoc_convert`, `tex_generate`, `latex_compile`, `pdf_validate`) with `export_id`, `export_stage`, `stage_duration_ms`
- **Type:** Success
- **Test file:** `tests/unit/test_structured_logging.py` or `tests/unit/test_export_logging.py`
- **Test approach:** Unit test. Mock or control the export pipeline to produce log events. Parse all log lines, filter by `export_id`.
- **Key assertions:**
  - Exactly 4 stage events exist for the export run
  - Each event has `export_stage` matching one of: `pandoc_convert`, `tex_generate`, `latex_compile`, `pdf_validate`
  - Each event has `export_id` (UUID string, non-null)
  - Each event has `stage_duration_ms` (integer >= 0)

### structured-logging-339.AC3.2

- **AC text:** All stage events for one export share the same `export_id` and `workspace_id`
- **Type:** Success
- **Test file:** `tests/unit/test_structured_logging.py` or `tests/unit/test_export_logging.py`
- **Test approach:** Unit test. Same test as AC3.1 -- verify correlation across stage events.
- **Key assertions:**
  - All 4 stage events have identical `export_id` values
  - All 4 stage events have identical `workspace_id` values
  - `export_id` is a valid UUID string

### structured-logging-339.AC3.3

- **AC text:** LaTeX compilation failure produces log event with `latex_errors` containing extracted `!`-prefixed lines (not the full log)
- **Type:** Failure
- **Test file:** `tests/unit/test_structured_logging.py` or `tests/unit/test_export_logging.py`
- **Test approach:** Unit test. Provide a LaTeX log file containing `!`-prefixed error lines mixed with other content. Trigger the error extraction path in `compile_latex()`. Parse the resulting log event.
- **Key assertions:**
  - Log event has `latex_errors` field (list of strings)
  - Each string in `latex_errors` starts with `!`
  - `latex_errors` does not contain non-error lines from the full log
  - `export_stage` equals `"latex_compile"`

### structured-logging-339.AC3.4

- **AC text:** Successful export includes `font_fallbacks` field with `detect_scripts()` result
- **Type:** Success
- **Test file:** `tests/unit/test_structured_logging.py` or `tests/unit/test_export_logging.py`
- **Test approach:** Unit test. Run or mock the export pipeline with known document content, parse the final log event.
- **Key assertions:**
  - Final stage log event contains `font_fallbacks` field
  - `font_fallbacks` is a list (sorted `frozenset` result from `detect_scripts()`)
  - Value reflects the script ranges present in the test document content

---

## AC4: Exception handling consistency

**Implementation phase:** Phase 4 (Exception handling audit)

### structured-logging-339.AC4.1

- **AC text:** Every `except` block in `src/promptgrimoire/pages/` that catches a user-facing error calls `log.exception()` before or alongside `ui.notify()`
- **Type:** Success
- **Test file:** `tests/unit/test_exception_logging_guard.py`
- **Test approach:** Guard test (AST-scanning). Parses all `.py` files under `src/promptgrimoire/` (excluding `cli/`), finds `ast.ExceptHandler` nodes, checks each handler body for a logging call.
- **Key assertions:**
  - Every `except` handler body contains at least one call to `logger.exception()`, `logger.error()`, `logger.warning()`, `log.exception()`, `log.error()`, or `log.warning()`
  - Exception: handlers that only `raise` (re-raise) are excluded from the check

### structured-logging-339.AC4.2

- **AC text:** No `except` block silently swallows exceptions (catches without logging)
- **Type:** Failure
- **Test file:** `tests/unit/test_exception_logging_guard.py`
- **Test approach:** Guard test (AST-scanning). Same test as AC4.1 -- the guard test itself IS the verification. Passing means no silent swallowing exists.
- **Key assertions:**
  - Zero violations found across all scanned files (excluding `cli/`)
  - Violations report includes file path and line number for each offending `except` block
  - Handlers that only `raise` are not flagged as violations
  - Handlers that call `continue` in a retry loop where the retry is logged are not flagged

---

## AC5: Discord webhook alerting

**Implementation phase:** Phase 6 (Discord webhook alerting)

### structured-logging-339.AC5.1

- **AC text:** ERROR-level log event sends Discord embed with severity colour, exception message, and context fields (`user_id`, `workspace_id` when available)
- **Type:** Success
- **Test file:** `tests/unit/test_discord_alerting.py`
- **Test approach:** Unit test. Instantiate the Discord processor with a test webhook URL, invoke it with an ERROR-level event dict containing `user_id` and `workspace_id`. Mock `httpx.AsyncClient.post` to capture the payload.
- **Key assertions:**
  - `httpx.AsyncClient.post` is called exactly once
  - Payload contains `embeds` list with one embed
  - Embed has `color` field (15548997 for ERROR, 10040115 for CRITICAL)
  - Embed has `title` containing the log event message
  - Embed `fields` include `user_id` and `workspace_id` values
  - Embed has `timestamp` in ISO 8601 format

### structured-logging-339.AC5.2

- **AC text:** No Discord message sent when `ALERTING__DISCORD_WEBHOOK_URL` is empty/unconfigured
- **Type:** Success
- **Test file:** `tests/unit/test_discord_alerting.py`
- **Test approach:** Unit test. Instantiate the Discord processor with `webhook_url=""`, invoke it with an ERROR-level event dict. Mock `httpx.AsyncClient.post`.
- **Key assertions:**
  - `httpx.AsyncClient.post` is never called
  - The processor returns the event dict unchanged (logging continues normally)

### structured-logging-339.AC5.3

- **AC text:** Cascading failures (same exception type + module) produce at most one Discord message per 60-second window
- **Type:** Edge
- **Test file:** `tests/unit/test_discord_alerting.py`
- **Test approach:** Unit test. Instantiate the processor, invoke it twice with the same `(exc_type, logger_name)` within 60 seconds. Mock `httpx.AsyncClient.post`.
- **Key assertions:**
  - First invocation triggers a POST
  - Second invocation (within 60s window) does NOT trigger a POST
  - A third invocation after advancing time past the 60s window DOES trigger a POST
  - Different `(exc_type, logger_name)` pairs are deduped independently

### structured-logging-339.AC5.4

- **AC text:** Discord webhook POST failure does not disrupt application logging
- **Type:** Failure
- **Test file:** `tests/unit/test_discord_alerting.py`
- **Test approach:** Unit test. Instantiate the processor, mock `httpx.AsyncClient.post` to raise `httpx.TimeoutException` (or similar). Invoke the processor with an ERROR-level event.
- **Key assertions:**
  - No exception propagates from the processor
  - The processor returns the event dict (logging pipeline continues)
  - The application log line is still written to the file handler

---

## AC6: Log file operations

**Implementation phase:** Phase 1 (Infrastructure -- structlog + configuration)

### structured-logging-339.AC6.1

- **AC text:** Single log file per instance (isolated by branch slug via `_branch_db_suffix()`), append mode, rotated at 10MB with 5 backups
- **Type:** Success
- **Test file:** `tests/unit/test_structured_logging.py`
- **Test approach:** Unit test. Call `_setup_logging()` with a temp directory, inspect the `RotatingFileHandler` on the root logger.
- **Key assertions:**
  - Root logger has exactly one `RotatingFileHandler`
  - Handler `maxBytes` equals `10 * 1024 * 1024` (10MB)
  - Handler `backupCount` equals `5`
  - Handler `mode` is `"a"` (append)
  - Log file path contains the branch slug from `_branch_db_suffix()`

### structured-logging-339.AC6.2

- **AC text:** Log file permissions are `0644` (owner-writable, world-readable)
- **Type:** Success
- **Test file:** `tests/unit/test_structured_logging.py`
- **Test approach:** Unit test. Call `_setup_logging()` with a temp directory, check file permissions via `os.stat()`.
- **Key assertions:**
  - `stat.S_IMODE(os.stat(log_path).st_mode)` equals `0o644`

### structured-logging-339.AC6.3

- **AC text:** Each line is valid JSON parseable by `jq`
- **Type:** Success
- **Test file:** `tests/unit/test_structured_logging.py`
- **Test approach:** Unit test. Emit several log lines at different levels, read the file, parse each line with `json.loads()`.
- **Key assertions:**
  - `json.loads(line)` succeeds for every line (no `JSONDecodeError`)
  - Each parsed object is a dict with at least `event`, `level`, `timestamp` keys

### structured-logging-339.AC6.4

- **AC text:** Application restart appends to existing log file (no clobbering)
- **Type:** Edge
- **Test file:** `tests/unit/test_structured_logging.py`
- **Test approach:** Unit test. Call `_setup_logging()`, emit a log line, count lines. Call `_setup_logging()` again (simulating restart), emit another line, count lines again.
- **Key assertions:**
  - Line count after second setup is strictly greater than after first setup
  - First log line is still present in the file (not overwritten)

### structured-logging-339.AC6.5

- **AC text:** Production instance writes to `logs/promptgrimoire.jsonl`; branch instance writes to `logs/promptgrimoire-{slug}.jsonl`
- **Type:** Success
- **Test file:** `tests/unit/test_structured_logging.py`
- **Test approach:** Unit test. Monkeypatch `_branch_db_suffix()` to return empty string, call `_setup_logging()`, verify filename. Then monkeypatch to return `"feature-foo"`, call again, verify filename.
- **Key assertions:**
  - Empty suffix produces file named `promptgrimoire.jsonl`
  - Non-empty suffix produces file named `promptgrimoire-feature-foo.jsonl`

---

## AC7: Traceback policy

**Implementation phase:** Phase 1 (Infrastructure -- structlog + configuration)

### structured-logging-339.AC7.1

- **AC text:** DEBUG and INFO log lines contain no traceback even when called inside an `except` block
- **Type:** Success
- **Test file:** `tests/unit/test_structured_logging.py`
- **Test approach:** Unit test. Inside a `try/except` block with an active exception, call `logger.info("test")`. Parse the JSON log output.
- **Key assertions:**
  - Parsed JSON does not contain `exc_info`, `exception`, or `traceback` keys with non-null values
  - The `event` field is present and correct

### structured-logging-339.AC7.2

- **AC text:** WARNING, ERROR, and CRITICAL log lines include full traceback when an exception is active
- **Type:** Success
- **Test file:** `tests/unit/test_structured_logging.py`
- **Test approach:** Unit test. Inside a `try/except` block, call `logger.warning("test")`, `logger.error("test")`, and `logger.exception("test")`. Parse each JSON log line.
- **Key assertions:**
  - Each parsed JSON contains traceback information (exception type and message present)
  - Traceback includes the exception class name and message text

### structured-logging-339.AC7.3

- **AC text:** Context fields (`user_id`, `workspace_id`, `request_path`) are logged as `null` when unavailable, never silently omitted
- **Type:** Success
- **Test file:** `tests/unit/test_structured_logging.py`
- **Test approach:** Unit test. Emit a log line without binding any contextvars. Parse the JSON output.
- **Key assertions:**
  - `parsed["user_id"]` is `None` (JSON `null`)
  - `parsed["workspace_id"]` is `None` (JSON `null`)
  - `parsed["request_path"]` is `None` (JSON `null`)
  - These keys are PRESENT in the dict, not absent

---

## Summary Matrix

| AC | Type | Phase | Test File | Approach |
|----|------|-------|-----------|----------|
| AC1.1 | Success | 3 | `tests/unit/test_structured_logging.py` | Unit test |
| AC1.2 | Success | 3 | `tests/unit/test_structured_logging.py` | Unit test |
| AC1.3 | Success | 3 | `tests/unit/test_structured_logging.py` | Unit test |
| AC1.4 | Edge | 3 | `tests/unit/test_structured_logging.py` | Unit test |
| AC2.1 | Success | 2 | N/A | Manual verification (ast-grep + PR review) |
| AC2.2 | Success | 2 | `tests/unit/test_print_usage_guard.py` | Guard test |
| AC2.3 | Success | 2 | `tests/unit/test_structured_logging.py` | Unit test |
| AC2.4 | Failure | 2 | `tests/unit/test_print_usage_guard.py` | Guard test (error format) |
| AC3.1 | Success | 5 | `tests/unit/test_export_logging.py` | Unit test |
| AC3.2 | Success | 5 | `tests/unit/test_export_logging.py` | Unit test |
| AC3.3 | Failure | 5 | `tests/unit/test_export_logging.py` | Unit test |
| AC3.4 | Success | 5 | `tests/unit/test_export_logging.py` | Unit test |
| AC4.1 | Success | 4 | `tests/unit/test_exception_logging_guard.py` | Guard test |
| AC4.2 | Failure | 4 | `tests/unit/test_exception_logging_guard.py` | Guard test |
| AC5.1 | Success | 6 | `tests/unit/test_discord_alerting.py` | Unit test |
| AC5.2 | Success | 6 | `tests/unit/test_discord_alerting.py` | Unit test |
| AC5.3 | Edge | 6 | `tests/unit/test_discord_alerting.py` | Unit test |
| AC5.4 | Failure | 6 | `tests/unit/test_discord_alerting.py` | Unit test |
| AC6.1 | Success | 1 | `tests/unit/test_structured_logging.py` | Unit test |
| AC6.2 | Success | 1 | `tests/unit/test_structured_logging.py` | Unit test |
| AC6.3 | Success | 1 | `tests/unit/test_structured_logging.py` | Unit test |
| AC6.4 | Edge | 1 | `tests/unit/test_structured_logging.py` | Unit test |
| AC6.5 | Success | 1 | `tests/unit/test_structured_logging.py` | Unit test |
| AC7.1 | Success | 1 | `tests/unit/test_structured_logging.py` | Unit test |
| AC7.2 | Success | 1 | `tests/unit/test_structured_logging.py` | Unit test |
| AC7.3 | Success | 1 | `tests/unit/test_structured_logging.py` | Unit test |
