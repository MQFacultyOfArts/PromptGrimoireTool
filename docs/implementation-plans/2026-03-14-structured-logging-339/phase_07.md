# Structured Logging Implementation Plan — Phase 7

**Goal:** Update developer documentation to reflect the new structured logging system.

**Architecture:** Developer-facing documentation in `docs/logging.md` + CLAUDE.md conventions section. No user-facing guide changes.

**Tech Stack:** Markdown documentation, MkDocs

**Scope:** 7 phases from original design (phases 1-7)

**Codebase verified:** 2026-03-14

---

## Acceptance Criteria Coverage

This phase is an infrastructure/documentation phase. **Verifies: None** — no functional ACs. Done when `uv run grimoire docs build` succeeds and documentation is accurate.

---

<!-- START_TASK_1 -->
### Task 1: Create docs/logging.md

**Files:**
- Create: `docs/logging.md`

**Implementation:**

Create a developer-facing guide covering:

1. **Log format**: JSON Lines format, one object per line. Example log line with all fields annotated.

2. **Standard fields**: Table of fields present on every log line:
   - `timestamp` (ISO 8601 UTC)
   - `level` (debug/info/warning/error/critical)
   - `event` (log message)
   - `logger` (module name)
   - `pid` (process ID)
   - `branch` (git branch)
   - `commit` (git short hash)
   - `user_id` (UUID or null)
   - `workspace_id` (UUID or null)
   - `request_path` (route or null)

3. **Log file location**:
   - Production: `logs/promptgrimoire.jsonl`
   - Branch instance: `logs/promptgrimoire-{slug}.jsonl`
   - Rotation: 10MB, 5 backups

4. **Querying with jq**: Example commands:
   - Filter by workspace: `jq 'select(.workspace_id == "UUID")' logs/promptgrimoire.jsonl`
   - Filter by user: `jq 'select(.user_id == "UUID")' logs/promptgrimoire.jsonl`
   - Errors only: `jq 'select(.level == "error" or .level == "critical")' logs/promptgrimoire.jsonl`
   - Export events: `jq 'select(.export_id != null)' logs/promptgrimoire.jsonl`
   - Last N lines: `tail -100 logs/promptgrimoire.jsonl | jq .`

5. **Per-module log levels**: Table of module categories and default levels (from design doc).

6. **Discord alerting**: How to configure `ALERTING__DISCORD_WEBHOOK_URL`, what triggers alerts (ERROR/CRITICAL), rate limiting (60s dedup window).

7. **Adding logging to new modules**: Pattern for new code:
   ```python
   import structlog
   logger = structlog.get_logger()
   ```

**Verification:**

Run: `uv run grimoire docs build`
Expected: Build succeeds

**Commit:** `docs: add structured logging developer guide`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add logging conventions to CLAUDE.md

**Files:**
- Modify: `CLAUDE.md` (add `## Logging` section after `## Authentication & Access Control`)

**Implementation:**

Add a `## Logging` section covering:

1. **Logger convention**: `logger = structlog.get_logger()` at module level. All modules use structlog, not stdlib logging.

2. **Exception handling rule**: Every `except` block must call `logger.exception()` (unexpected) or `logger.warning()` (expected business logic). No silent swallowing.

3. **Context propagation**: `page_route` decorator auto-binds `user_id` and `request_path`. Workspace handlers bind `workspace_id` via `structlog.contextvars.bind_contextvars()`.

4. **Log levels by module category**: Brief reference table (full details in `docs/logging.md`).

5. **Print guard**: No `print()` calls in `src/promptgrimoire/` (except `cli/`). Guard test enforces this.

6. **Cross-reference**: Point to `docs/logging.md` for full details on log format, jq queries, and Discord alerting.

Keep it concise — CLAUDE.md is for quick reference, `docs/logging.md` is the full guide.

**Verification:**

Run: `uv run grimoire docs build`
Expected: Build succeeds

**Commit:** `docs: add logging conventions to CLAUDE.md`

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Update docs/ reference table in CLAUDE.md

**Files:**
- Modify: `CLAUDE.md` (update the Documentation table)

**Implementation:**

Add `logging.md` to the documentation reference table in CLAUDE.md (around the `## Documentation` section):

```markdown
| [logging.md](docs/logging.md) | Structured logging, log format, jq queries, Discord alerting |
```

**Verification:**

Run: `uv run grimoire docs build`
Expected: Build succeeds

**Commit:** `docs: add logging.md to documentation reference table`

<!-- END_TASK_3 -->

## UAT Steps

1. Run: `uv run grimoire docs build` — should succeed without errors
2. Open `docs/logging.md` — verify it covers: JSON format, standard fields, log file location, jq query examples, per-module levels, Discord alerting config
3. Open `CLAUDE.md` — verify `## Logging` section exists with conventions (structlog, exception handling, context propagation, print guard)
4. Verify documentation reference table in CLAUDE.md includes `logging.md`

**Note:** This phase does not update `using_promptgrimoire.py` because structured logging is developer-infrastructure with no user-facing behaviour. The flight-rules guide is exempted.
