# Structured Logging

*Last updated: 2026-03-15*

PromptGrimoire uses [structlog](https://www.structlog.org/) for structured JSON logging. All application output flows through structlog's `ProcessorFormatter`, producing machine-readable JSON lines in log files and human-readable coloured output on the console.

## Log Format

Log files use JSON Lines format (one JSON object per line):

```json
{"timestamp": "2026-03-15T08:42:17.123456Z", "level": "info", "event": "app_starting", "logger": "promptgrimoire", "pid": 12345, "branch": "main", "commit": "a1b2c3d", "user_id": null, "workspace_id": null, "request_path": null, "version": "0.1.0+a1b2c3d", "host": "0.0.0.0", "port": 8080}
```

Console output is a condensed, coloured form that strips `pid`, `branch`, `commit`, `timestamp`, and null context fields. The JSON file retains everything.

## Standard Fields

Every log line includes these fields:

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | string | ISO 8601 UTC (e.g. `2026-03-15T08:42:17.123456Z`) |
| `level` | string | `debug`, `info`, `warning`, `error`, or `critical` |
| `event` | string | Log message / event name |
| `logger` | string | Module name (e.g. `promptgrimoire.pages.annotation`) |
| `pid` | int | Process ID |
| `branch` | string | Git branch name at startup |
| `commit` | string | Git short hash at startup |
| `user_id` | string\|null | Authenticated user UUID (bound per-request by `page_route`) |
| `workspace_id` | string\|null | Workspace UUID (bound by workspace handlers) |
| `request_path` | string\|null | NiceGUI route (bound per-request by `page_route`) |

Additional context fields (e.g. `export_id`, `operation`) appear when bound by specific code paths.

## Log File Location

Configured via `APP__LOG_DIR` (default: `logs/`). Files are isolated per instance using the same branch slug as database isolation.

| Instance | File |
|----------|------|
| Production (main/master) | `{log_dir}/promptgrimoire.jsonl` |
| Branch (e.g. `feature-foo`) | `{log_dir}/promptgrimoire-feature-foo.jsonl` |

**Rotation:** 10 MB max size, 5 backup files. File permissions: `0644` (readable by SSH users without sudo).

## Querying with jq

```bash
# Filter by workspace
jq 'select(.workspace_id == "UUID")' logs/promptgrimoire.jsonl

# Filter by user
jq 'select(.user_id == "UUID")' logs/promptgrimoire.jsonl

# Errors and criticals only
jq 'select(.level == "error" or .level == "critical")' logs/promptgrimoire.jsonl

# Export events (have export_id context)
jq 'select(.export_id != null)' logs/promptgrimoire.jsonl

# Pretty-print last 100 lines
tail -100 logs/promptgrimoire.jsonl | jq .

# Events from a specific module
jq 'select(.logger == "promptgrimoire.export.pdf_export")' logs/promptgrimoire.jsonl

# Count events by level
jq -s 'group_by(.level) | map({level: .[0].level, count: length})' logs/promptgrimoire.jsonl
```

## Per-Module Log Levels

Each module sets an explicit log level appropriate to its role. The root logger is DEBUG (file handler captures everything); the console handler is INFO.

| Module category | Default level | Rationale |
|----------------|---------------|-----------|
| Background workers (`search_worker`, `deadline_worker`) | INFO | Status + errors, no per-iteration noise |
| Export pipeline (`export/`) | INFO | Stage progression visible by default |
| CRDT sync (`crdt/`) | WARNING | High-frequency, only surface problems |
| Auth (`auth/`) | INFO | Login events, access denials |
| Pages/UI (`pages/`) | INFO | Page loads, user actions |
| Database (`db/engine`, `db/wargames`, `db/tags`) | WARNING | Only surface connection/query problems |
| Configuration (`config`) | INFO | Settings resolution |

**Do not** use per-module `logging.getLogger(__name__).setLevel()` calls. Level filtering is configured globally via structlog; per-module overrides suppress debug output and are redundant. A guard test (`tests/unit/test_setlevel_guard.py`) enforces this. To adjust log verbosity, change the global structlog level configuration.

## Discord Alerting

The Discord webhook processor fires on every ERROR and CRITICAL log event, sending a Discord embed with severity colour, event name, exception info, and correlation context fields.

### Configuration

Set `ALERTING__DISCORD_WEBHOOK_URL` in `.env`:

```
ALERTING__DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/XXXXX/YYYYY
```

Leave empty to disable alerting (the processor becomes a no-op).

### What Triggers Alerts

- All `logger.error()` and `logger.critical()` calls
- All `logger.exception()` calls (which log at ERROR level)

### Rate Limiting

Alerts are deduplicated by `(exception_type, logger_name)` within a 60-second window. During cascading failures (e.g. database down), only the first error of each type per module is sent. Webhook POSTs are fire-and-forget and never block the logging pipeline.

### Testing the Webhook

```bash
uv run grimoire admin webhook
```

This sends a test alert to the configured webhook and reports the HTTP response status.

## Adding Logging to New Modules

Every module should use structlog at module level:

```python
import structlog

logger = structlog.get_logger()
```

Key rules:

1. **Every `except` block must log.** Use `logger.exception()` for unexpected errors, `logger.warning()` for expected business logic errors. No silent exception swallowing.

2. **Bind context where available.** Workspace handlers should bind `workspace_id`:
   ```python
   from structlog.contextvars import bind_contextvars
   bind_contextvars(workspace_id=str(workspace.id))
   ```

3. **No `print()` in `src/promptgrimoire/`** (except `cli/`). A guard test enforces this.

## Traceback Policy

- **ERROR/CRITICAL:** Full traceback included in the JSON log line (`exc_info` preserved)
- **WARNING:** Traceback included only when explicitly passed via `logger.warning(..., exc_info=True)`
- **DEBUG/INFO:** Tracebacks stripped (no `exc_info` in output, even if accidentally passed)
