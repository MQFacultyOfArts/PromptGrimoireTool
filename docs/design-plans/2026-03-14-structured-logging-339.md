# Structured Logging with Discord Alerting

**GitHub Issue:** #339

## Summary

PromptGrimoire currently logs via Python's stdlib `logging` module in plain text, making production debugging slow: finding all events for a specific workspace requires grepping unstructured lines across multiple restarts. This design replaces that with structured JSON logging via `structlog`, so every log line is a machine-readable object carrying request context (`user_id`, `workspace_id`, `request_path`) automatically — without requiring manual field passing through every call site. The approach uses structlog's `ProcessorFormatter` to intercept the existing `logging.getLogger()` calls from third-party libraries and route everything through a single processor chain, meaning the 45+ existing modules can be migrated mechanically without touching their logic.

The implementation proceeds in seven phases: first plumbing structlog into the application's existing `_setup_logging()` function; then mechanically rewriting module-level logger declarations with `ast-grep`; then injecting per-request context via the existing `page_route` decorator and workspace setup points; then auditing exception handlers to eliminate silent swallowing; then instrumenting the PDF export pipeline with stage-level timing and error extraction; and finally adding a Discord webhook processor that fires on ERROR/CRITICAL events with rate-limited deduplication. The end state is a single append-mode JSONL file — readable by SSH users without `sudo` — where any production incident can be reconstructed by piping the log through `jq` with a workspace or export ID filter.

## Definition of Done

Replace PromptGrimoire's current text-format logging with structured JSON logging. Every log line carries `user_id`, `workspace_id`, `pid`, `branch`, `commit`, and `request_path` where available. The export pipeline emits stage progression events with per-stage timing, LaTeX error extraction, and font fallback tracking. ERROR/CRITICAL events fire a Discord webhook with actionable context. Logs land in a single rotated file (append mode, `0644` permissions) queryable via SSH + `jq`. Inconsistent exception handling (silent `ui.notify` without logging) is eliminated across the codebase.

**Success criteria:** SSH to server, `jq 'select(.workspace_id == "xxx")' /path/to/grimoire.jsonl` shows every event for that workspace. Production exceptions produce a Discord message with enough context to start debugging without touching the server.

**Out of scope:** Distributed tracing, request-level spans, performance dashboards, Logfire/Sentry/OpenTelemetry.

## Acceptance Criteria

### structured-logging-339.AC1: Log lines carry request context
- **structured-logging-339.AC1.1 Success:** Log line from an authenticated page handler contains `user_id`, `request_path`, `pid`, `branch`, `commit`
- **structured-logging-339.AC1.2 Success:** Log line from an annotation workspace handler additionally contains `workspace_id`
- **structured-logging-339.AC1.3 Success:** `jq 'select(.workspace_id == "XXX")' logs/promptgrimoire.jsonl` returns all events for that workspace
- **structured-logging-339.AC1.4 Edge:** Log line from unauthenticated page (e.g. login) has `user_id: null` but still has `pid`, `branch`, `commit`, `request_path`

### structured-logging-339.AC2: Module migration and print guard
- **structured-logging-339.AC2.1 Success:** All modules in `src/promptgrimoire/` use `structlog.get_logger()` with explicit log level set
- **structured-logging-339.AC2.2 Success:** Guard test fails if a `print()` call is added to any `.py` file under `src/promptgrimoire/`
- **structured-logging-339.AC2.3 Success:** Existing stdlib `logging.getLogger()` calls from third-party libraries (NiceGUI, SQLAlchemy) produce JSON output through ProcessorFormatter
- **structured-logging-339.AC2.4 Failure:** Guard test produces clear error message identifying file and line number of offending `print()`

### structured-logging-339.AC3: Export pipeline instrumentation
- **structured-logging-339.AC3.1 Success:** Successful PDF export produces log events for each stage (`pandoc_convert`, `tex_generate`, `latex_compile`, `pdf_validate`) with `export_id`, `export_stage`, `stage_duration_ms`
- **structured-logging-339.AC3.2 Success:** All stage events for one export share the same `export_id` and `workspace_id`
- **structured-logging-339.AC3.3 Failure:** LaTeX compilation failure produces log event with `latex_errors` containing extracted `!`-prefixed lines (not the full log)
- **structured-logging-339.AC3.4 Success:** Successful export includes `font_fallbacks` field with `detect_scripts()` result

### structured-logging-339.AC4: Exception handling consistency
- **structured-logging-339.AC4.1 Success:** Every `except` block in `src/promptgrimoire/pages/` that catches a user-facing error calls `log.exception()` before or alongside `ui.notify()`
- **structured-logging-339.AC4.2 Failure:** No `except` block silently swallows exceptions (catches without logging)

### structured-logging-339.AC5: Discord webhook alerting
- **structured-logging-339.AC5.1 Success:** ERROR-level log event sends Discord embed with severity colour, exception message, and context fields (`user_id`, `workspace_id` when available)
- **structured-logging-339.AC5.2 Success:** No Discord message sent when `ALERTING__DISCORD_WEBHOOK_URL` is empty/unconfigured
- **structured-logging-339.AC5.3 Edge:** Cascading failures (same exception type + module) produce at most one Discord message per 60-second window
- **structured-logging-339.AC5.4 Failure:** Discord webhook POST failure does not disrupt application logging

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

## Glossary

- **structlog**: Python structured logging library. Wraps stdlib `logging` with a processor chain that transforms log records into dicts before rendering. Processors are applied left-to-right, each receiving and returning the event dict.
- **ProcessorFormatter**: A structlog bridge class that installs as a stdlib `logging.Formatter`. Third-party libraries that call `logging.getLogger()` produce records that flow through ProcessorFormatter and are rendered as JSON, without any changes to the libraries.
- **contextvars**: Python standard library mechanism (`contextvars.ContextVar`) for async-safe per-task storage. structlog uses `contextvars` to store per-request fields (`user_id`, `workspace_id`) so any log call within that request automatically includes them.
- **bind_contextvars / clear_contextvars**: structlog functions that set and clear the context stored in `contextvars` for the current async task. Called at request entry points so all downstream log calls inherit the request context.
- **JSONRenderer / ConsoleRenderer**: structlog processors that produce final output. `JSONRenderer` emits compact JSON (for the log file); `ConsoleRenderer` emits colour-coded human-readable text (for the terminal).
- **RotatingFileHandler**: stdlib `logging.handlers.RotatingFileHandler`. Rotates the log file when it exceeds a size threshold. Used here at 10MB / 5 backups.
- **JSONL**: JSON Lines format — one complete JSON object per line. Makes the log file streamable and `jq`-queryable without loading the entire file.
- **jq**: Command-line JSON processor. Used to filter and query JSONL log files (e.g. `jq 'select(.workspace_id == "xxx")'`).
- **export_id**: A `uuid4()` generated per PDF export run. Correlation ID joining all stage events for that run.
- **export_stage**: Enumerated string identifying which phase of the PDF export pipeline produced a log event: `pandoc_convert`, `tex_generate`, `latex_compile`, `pdf_validate`.
- **detect_scripts()**: Existing function in the export pipeline that analyses document text to determine which Unicode script ranges are present, driving font fallback selection. Result logged as `font_fallbacks`.
- **LaTeX `!`-prefixed lines**: LaTeX compilation errors begin with `!` in the `.log` output. Only these lines are extracted into `latex_errors` rather than the full multi-megabyte log.
- **Discord webhook**: HTTP endpoint provided by Discord that accepts JSON and posts to a channel. Used for ERROR/CRITICAL alerting without requiring a bot token.
- **Discord embed**: Structured message format in Discord webhooks supporting colour coding, titles, and key-value fields.
- **AlertingConfig**: New pydantic-settings sub-model holding `discord_webhook_url`. Configured via `ALERTING__DISCORD_WEBHOOK_URL` environment variable.
- **page_route decorator**: Existing decorator in `src/promptgrimoire/pages/registry.py` that registers NiceGUI page handlers. Enhanced to inject per-request logging context.
- **ast-grep**: Structural code search and rewrite tool operating on AST patterns. Used to mechanically rewrite `logging.getLogger(__name__)` → `structlog.get_logger()`.
- **guard test**: AST-scanning test (same pattern as `test_async_fixture_safety.py`) that fails CI if prohibited patterns appear in source files.
- **PrivateTmp**: systemd service isolation feature giving the service a private `/tmp`. Previously made LaTeX logs inaccessible; Phase 5 captures them into structured log events instead.

## Architecture

### Logging Library: structlog with ProcessorFormatter

structlog wraps Python's stdlib `logging` module via `ProcessorFormatter`. Existing `logging.getLogger(__name__)` calls across 45+ files continue working unchanged — their output flows through structlog's processor chain and is rendered as JSON. New code uses `structlog.get_logger()` with per-module log levels for explicit control.

Three output destinations:

1. **JSON log file** — Rotated file at a configurable path, isolated per instance: `logs/promptgrimoire-{branch_slug}.jsonl` for worktree/branch instances, `logs/promptgrimoire.jsonl` for main/production. Derives the slug from the same `_branch_db_suffix()` mechanism used for database isolation. `0644` permissions, append mode. `RotatingFileHandler` (10MB, 5 backups). Every line is a complete JSON object with standard fields: `timestamp`, `level`, `logger`, `event`, `pid`, `branch`, `commit`, plus context fields (`user_id`, `workspace_id`, `request_path`) — logged as `null` when unavailable, never silently omitted.

2. **Console** — Human-readable coloured output via `structlog.dev.ConsoleRenderer()` at INFO level. For developer use during local development.

3. **Discord webhook processor** — Custom structlog processor that fires on ERROR/CRITICAL. Sends a Discord embed with severity colour, full traceback, and correlation fields (user_id, workspace_id, export_id). Webhook URL from `AlertingConfig` in pydantic-settings. Processor is a no-op when URL is unconfigured.

### Traceback Policy

Tracebacks are level-gated:

| Level | Traceback in log line | Traceback in Discord |
|-------|----------------------|---------------------|
| DEBUG, INFO | No | N/A (not sent) |
| WARNING | Yes (full) | N/A (not sent) |
| ERROR, CRITICAL | Yes (full) | Yes (full) |

DEBUG and INFO lines carry only `event`, context fields, and location (`logger`, `lineno`). WARNING and above include the full traceback when an exception is active. This keeps the log file compact for normal operations while preserving diagnostic detail where it matters.

### Context Propagation

`structlog.contextvars` provides async-safe context binding. Two injection layers:

- **Page-level context:** The `page_route` decorator in `src/promptgrimoire/pages/registry.py` is enhanced to call `clear_contextvars()` then `bind_contextvars(user_id=..., request_path=...)` after resolving `app.storage.user.get("auth_user")`. Every page handler gets automatic context without per-file changes.

- **Workspace-level context:** `bind_contextvars(workspace_id=...)` called in `_setup_client_sync()` (`src/promptgrimoire/pages/annotation/broadcast.py`) and equivalent resolution points in roleplay and export pages.

### Global Fields

`pid`, `branch`, and `commit` are bound once at startup via a custom structlog processor (not contextvars — these are process-global, not request-scoped). `branch` and `commit` are read from `get_current_branch()` and `get_git_commit()` which already exist in `src/promptgrimoire/__init__.py`.

### Export Pipeline Instrumentation

The export pipeline (`src/promptgrimoire/export/pdf_export.py`) gains structured log events at each stage boundary. Each export run generates a `uuid4()` `export_id` that correlates all stage events.

Fields per stage event:
- `export_id` — correlation ID for the run
- `export_stage` — `pandoc_convert`, `tex_generate`, `latex_compile`, `pdf_validate`
- `stage_duration_ms` — wall-clock milliseconds for that stage
- `workspace_id` — from contextvars (already bound by page handler)

On LaTeX failure: `latex_errors` field contains extracted `!`-prefixed error lines from the LaTeX log (not the full log). On success: `font_fallbacks` field contains the `detect_scripts()` result showing which script fallback fonts were loaded.

### Configuration

New `AlertingConfig` sub-model in `src/promptgrimoire/config.py`:

```python
class AlertingConfig(BaseModel):
    """Error alerting configuration."""
    discord_webhook_url: str = ""
```

Added to `Settings` alongside existing sub-models. Env var: `ALERTING__DISCORD_WEBHOOK_URL`.

Log file path moves from hardcoded `Path("logs")` in `_setup_logging()` to `AppConfig.log_dir` (which already exists but is unused).

### Guard Test

An AST-based guard test (same pattern as `tests/unit/test_async_fixture_safety.py`) scans all `.py` files under `src/promptgrimoire/` for bare `print()` calls. Enforces that all output goes through the structured logger.

### Per-Module Log Levels

Each module's logger is initialised with an explicit level appropriate to its role:

| Module category | Default level | Rationale |
|----------------|---------------|-----------|
| Background workers | INFO | Status + errors, no per-iteration noise |
| Export pipeline | INFO | Stage progression visible by default |
| CRDT sync | WARNING | High-frequency, only surface problems |
| Auth | INFO | Login events, access denials |
| Pages/UI | INFO | Page loads, user actions |
| Database | WARNING | Only surface connection/query problems |

Levels are set via `structlog.get_logger().setLevel()` or stdlib `logging.getLogger(__name__).setLevel()`. Easy to toggle per-module to DEBUG for troubleshooting.

## Existing Patterns

### Logging setup

`_setup_logging()` in `src/promptgrimoire/__init__.py` (lines 41-74) already configures `RotatingFileHandler` with console and file handlers. This function is replaced in-place — same location, same call site in `main()`, new implementation using structlog's `ProcessorFormatter`.

### Configuration

`src/promptgrimoire/config.py` uses pydantic-settings with nested sub-models (`StytchConfig`, `DatabaseConfig`, `LlmConfig`, etc.) accessed via `get_settings()`. `AlertingConfig` follows this pattern exactly. `AppConfig.log_dir` already exists (line 76) but is unused by the current `_setup_logging()` — this design connects them.

### Guard tests

`tests/unit/test_async_fixture_safety.py` scans test files for `@pytest.fixture` on async functions. The `print()` guard follows this pattern: AST parse, walk, assert no violations, clear error message pointing at the offending file and line.

### Exception handling

Background workers (`deadline_worker.py`, `search_worker.py`) use `logger.exception()` consistently — good pattern, preserved unchanged. Page handlers are inconsistent — some use `logger.exception()`, others silently `ui.notify()` without logging. The migration standardises on: always log the exception, optionally also notify the user.

### ast-grep migration

The `logging.getLogger(__name__)` → `structlog.get_logger()` rewrite is a mechanical ast-grep transformation. The `import logging` → `import structlog` change accompanies it. Files that only use stdlib logging and don't need structlog's API can be left unchanged (ProcessorFormatter handles them).

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Infrastructure — structlog + configuration

**Goal:** Replace `_setup_logging()` with structlog configuration. JSON file output working, console output preserved. No per-file changes yet.

**Components:**
- `structlog` added to `pyproject.toml`
- `_setup_logging()` rewritten in `src/promptgrimoire/__init__.py` — ProcessorFormatter with JSONRenderer (file) and ConsoleRenderer (console)
- Global fields processor for `pid`, `branch`, `commit`
- Per-instance log file path from `AppConfig.log_dir` + branch slug (via `_branch_db_suffix()`), `0644` permissions
- `AlertingConfig` sub-model in `src/promptgrimoire/config.py`

**Dependencies:** None (first phase)

**Done when:** Application starts, existing `logging.getLogger(__name__)` calls across the codebase produce JSON lines in the log file with `pid`, `branch`, `commit` fields. Log file is isolated per instance (branch slug). Console output remains human-readable. `uv sync` succeeds, `ruff check` and `ty check` clean.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: ast-grep migration + guard test

**Goal:** Mechanically rewrite all files from stdlib logging to structlog, set per-module log levels, add print guard test.

**Components:**
- ast-grep rule: `logger = logging.getLogger(__name__)` → `log = structlog.get_logger()` with level set
- ast-grep rule: `import logging` → `import structlog` (where logging is only used for getLogger)
- Per-module log level assignments based on module category
- Guard test in `tests/unit/` scanning `src/promptgrimoire/` for `print()` calls
- Fix existing `print()` calls in `src/promptgrimoire/__init__.py` (startup messages → logger)

**Dependencies:** Phase 1 (structlog configured)

**Done when:** All modules use `structlog.get_logger()` with explicit levels. Guard test passes (no `print()` in `src/promptgrimoire/`). All existing tests still pass. Covers `structured-logging-339.AC2.*`.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Context propagation

**Goal:** Automatic `user_id`, `workspace_id`, `request_path` on every log line within a request context.

**Components:**
- `structlog.contextvars.merge_contextvars` added to processor chain (Phase 1 config)
- `page_route` decorator in `src/promptgrimoire/pages/registry.py` enhanced to bind page-level context (user_id, request_path)
- `_setup_client_sync()` in `src/promptgrimoire/pages/annotation/broadcast.py` binds workspace_id
- Equivalent workspace_id binding in roleplay and export entry points

**Dependencies:** Phase 1 (structlog configured), Phase 2 (modules migrated)

**Done when:** Log lines from page handlers contain `user_id` and `request_path`. Log lines from annotation workspace contain `workspace_id`. Queryable: `jq 'select(.workspace_id == "xxx")' logs/promptgrimoire.jsonl` returns all events for that workspace. Covers `structured-logging-339.AC1.*`.
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Exception handling audit

**Goal:** Eliminate silent exception swallowing. Every `except` block that currently only does `ui.notify()` also logs the exception.

**Components:**
- Audit all `except` blocks in `src/promptgrimoire/pages/` for missing `log.exception()` calls
- Standardise pattern: `log.exception("description", ...)` then optionally `ui.notify()`
- Specific fix: `src/promptgrimoire/pages/roleplay.py` line 146 (silent catch)

**Dependencies:** Phase 2 (modules migrated to structlog)

**Done when:** No `except` block in `src/promptgrimoire/` swallows exceptions without logging. Covers `structured-logging-339.AC4.*`.
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: Export pipeline instrumentation

**Goal:** Structured stage-progression events for the PDF export pipeline with timing, error extraction, and font tracking.

**Components:**
- `export_id` (uuid4) generated at export entry point in `src/promptgrimoire/export/pdf_export.py`
- Stage boundary log events with `export_stage`, `stage_duration_ms`
- LaTeX `!` error line extraction on compilation failure → `latex_errors` field
- `detect_scripts()` result → `font_fallbacks` field on success
- LaTeX subprocess stdout/stderr captured into structured log (not left in PrivateTmp)

**Dependencies:** Phase 3 (context propagation — workspace_id available via contextvars)

**Done when:** A PDF export produces a sequence of log events queryable by `export_id`, each with stage name and duration. Failed exports include extracted LaTeX error lines. Covers `structured-logging-339.AC3.*`.
<!-- END_PHASE_5 -->

<!-- START_PHASE_6 -->
### Phase 6: Discord webhook alerting

**Goal:** ERROR/CRITICAL log events send a Discord embed with actionable context.

**Components:**
- Custom structlog processor that POSTs to Discord webhook URL on ERROR/CRITICAL
- Discord embed format: colour-coded severity, exception message, `user_id`, `workspace_id`, `export_id` (when available), timestamp
- Rate limiting / deduplication to avoid webhook spam during cascading failures
- No-op when `AlertingConfig.discord_webhook_url` is empty

**Dependencies:** Phase 1 (AlertingConfig), Phase 3 (context fields available)

**Done when:** An unhandled exception in production produces a Discord message with enough context to identify the user, workspace, and error. No message sent when webhook URL is unconfigured. Covers `structured-logging-339.AC5.*`.
<!-- END_PHASE_6 -->

<!-- START_PHASE_7 -->
### Phase 7: Documentation

**Goal:** Update user-facing and developer documentation to reflect the new logging system.

**Components:**
- Developer documentation on log format, querying with `jq`, configuring Discord webhook
- `.env.example` updated with `ALERTING__DISCORD_WEBHOOK_URL`
- `CLAUDE.md` updated with logging conventions and module log level table

**Dependencies:** All previous phases

**Done when:** `uv run grimoire docs build` succeeds. A developer can read the docs and know how to query logs, configure alerting, and set per-module log levels.
<!-- END_PHASE_7 -->

## Additional Considerations

**Rate limiting for Discord:** Cascading failures (e.g. database down) can produce hundreds of ERROR events per second. The Discord processor should deduplicate by exception type + module, sending at most one message per unique error per 60-second window.

**Log file permissions:** `0644` is set at file creation. The application runs as service user `promptgrimoire`; SSH users can read the logs without sudo. Verify the service user's umask doesn't override the intended permissions.

**Log file isolation:** Multiple instances on the same host (production, staging, worktree dev servers) write to separate log files derived from `_branch_db_suffix()`. This reuses the existing database isolation mechanism so log boundaries match data boundaries. Production (main/master) writes to `logs/promptgrimoire.jsonl`; branch `feature-foo` writes to `logs/promptgrimoire-feature-foo.jsonl`.

**Traceback toggle:** The level-gated traceback policy (WARNING+ only) is the default. Per-module log level can be toggled to DEBUG when needed — tracebacks on DEBUG lines can be enabled per-file during active debugging sessions by adjusting the module's level and the traceback processor's threshold.

**NiceGUI sync/async context caveat:** structlog's contextvars documentation notes that context set in sync context may not appear in async context and vice versa. Since `page_route` handlers are async and `bind_contextvars` is called in async context, this should not be an issue. If sync helper functions are called from async handlers, context propagation is inherited via Python's contextvars semantics (child tasks inherit parent context).
