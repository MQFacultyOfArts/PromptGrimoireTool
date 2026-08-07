# Log Policy and Audit Design

**GitHub Issue:** #391 (Bug: structlog user_id/workspace_id context missing from all log entries) — this design closes #391 and addresses the broader noise problem that surfaced it.

## Summary
<!-- TO BE GENERATED after body is written -->

## Definition of Done

### DoD-1: Env-driven log levels function

- **Observable**: `APP__LOG_FILE_LEVEL`, `APP__LOG_CONSOLE_LEVEL`, `APP__LOG_DEBUG_MODULES` env vars exist as `pydantic-settings` fields; setting each produces the documented filtering behaviour at runtime.
- **Falsifiable**: tests assert (a) defaults give file=INFO/console=WARNING; (b) `APP__LOG_DEBUG_MODULES=promptgrimoire.export` makes only that subtree's DEBUG land in file; (c) `APP__LOG_FILE_LEVEL=DEBUG` opens the file firehose globally.
- **Scoped**: three env vars, file + console handlers only. Excludes: changing the formatter chain, changing Discord alerting thresholds.

### DoD-2: src/promptgrimoire/ uses structlog exclusively for logging

- **Observable**: `grep -rn "^import logging\|^from logging" src/promptgrimoire/` returns only `logging_config.py`; no `logger = _logging.getLogger(__name__)` anywhere else.
- **Falsifiable**: a guard test (extending or paralleling `test_setlevel_guard.py`) fails if any file outside `logging_config.py` imports stdlib `logging` or calls `logging.getLogger()`.
- **Scoped**: src/promptgrimoire/ only. Excludes tests/, scripts/, deploy/, and the existing `print()` carve-out for `cli/`.

### DoD-3: File output is strict JSON

- **Observable**: every line of `logs/sessions/promptgrimoire-*.jsonl` parses with `json.loads` without raising.
- **Falsifiable**: a test invokes `setup_logging()`, emits one entry at every level and one with an exception attached, reads back the file, asserts every line is valid JSON and contains no ANSI escape sequences or box-drawing characters.
- **Scoped**: file handler only. TTY console may stay Rich.

### DoD-4: Production rotation rate drops materially at comparable load

- **Observable**: post-deploy, the bytes/hour written to `promptgrimoire.jsonl` (computed from rotation mtimes) at the same load profile as the 50 MB/day baseline observed on 2026-04-29.
- **Falsifiable**: target ≥75% reduction (baseline 50 MB/day → ≤12 MB/day at equivalent low-load conditions); measured in a UAT step at least 24h after deploy.
- **Scoped**: rotation rate only. Excludes the multi-process race that's causing `.3`/`.4` mtime inversion (separate concern, noted but not fixed here).

### DoD-5: Call-site audit recorded with rationale

- **Observable**: a table in this design plan (and reproduced in the PR description) listing every previously-DEBUG/INFO call site in src/promptgrimoire/ with its disposition: KEEP at level / DEMOTE to / PROMOTE to / DELETE / NEW (added for coverage). 102 + 43 = 145 baseline rows minimum, plus any NEW entries.
- **Falsifiable**: reviewer can re-grep the codebase against the table and verify the actual call sites match the disposition column. Each KEEP-INFO row passes the question "would this help replay an error or measure usage?". Each KEEP-WARNING row passes "would I want to see this live in journalctl?".
- **Scoped**: src/promptgrimoire/ only. Excludes content/format changes to event payloads beyond level reclassification — those are coverage additions covered by DoD-7, not reclassifications.

### DoD-6: Documentation updated and builds

- **Observable**: `docs/logging.md` reflects the new policy table, env vars, examples, and per-module DEBUG escalation pattern.
- **Falsifiable**: `uv run grimoire docs build` exits zero; the new env vars appear in `docs/configuration.md` (or wherever pydantic-settings vars are documented).
- **Scoped**: `docs/logging.md` + configuration docs. Excludes design-plan doc (this file is its own deliverable).

### DoD-7: Logging context bubbles through async/background boundaries (closes #391)

- **Observable**: in a sample of post-deploy log entries from a real session, `user_id` is non-null on ≥75% of entries originating from page handlers and their downstream async callbacks, upload handlers, and user-initiated background jobs.
- **Falsifiable**: a test exercises the `page_route → async callback → executor/background-worker` pipeline and asserts `structlog.contextvars` survive every hop; a one-shot count against a sample session log file confirms the 75% rate is met.
- **Scoped**: src/promptgrimoire/. Excludes startup, healthz, system-tick, and other entries that genuinely have no user context.

## Acceptance Criteria
<!-- TO BE GENERATED and validated before glossary -->

## Glossary
<!-- TO BE GENERATED after body is written -->
