# Structured Logging Implementation Plan — Phase 6

**Goal:** ERROR/CRITICAL log events send a Discord embed with actionable context, rate-limited to avoid webhook spam during cascading failures.

**Architecture:** Custom structlog processor that POSTs to Discord webhook URL on ERROR/CRITICAL. Deduplication by `(exception_type, module_name)` with 60-second window. No-op when webhook URL is unconfigured.

**Tech Stack:** structlog, httpx (async HTTP client), Discord webhook API

**Scope:** 7 phases from original design (phases 1-7)

**Codebase verified:** 2026-03-14

---

## Acceptance Criteria Coverage

This phase implements and tests:

### structured-logging-339.AC5: Discord webhook alerting
- **structured-logging-339.AC5.1 Success:** ERROR-level log event sends Discord embed with severity colour, exception message, and context fields (`user_id`, `workspace_id` when available)
- **structured-logging-339.AC5.2 Success:** No Discord message sent when `ALERTING__DISCORD_WEBHOOK_URL` is empty/unconfigured
- **structured-logging-339.AC5.3 Edge:** Cascading failures (same exception type + module) produce at most one Discord message per 60-second window
- **structured-logging-339.AC5.4 Failure:** Discord webhook POST failure does not disrupt application logging

---

<!-- START_TASK_1 -->
### Task 1: Add httpx dependency

**Files:**
- Modify: `pyproject.toml` (dependencies section)

**Implementation:**

Add `httpx>=0.27` to the `[project.dependencies]` list in `pyproject.toml`.

**Verification:**

Run: `uv sync`
Expected: Dependencies install without errors

Run: `uv run python -c "import httpx; print(httpx.__version__)"`
Expected: Version printed

**Commit:** `deps: add httpx for Discord webhook alerting`

<!-- END_TASK_1 -->

<!-- START_SUBCOMPONENT_A (tasks 2-3) -->
<!-- START_TASK_2 -->
### Task 2: Discord webhook processor

**Verifies:** structured-logging-339.AC5.1, structured-logging-339.AC5.2, structured-logging-339.AC5.3, structured-logging-339.AC5.4

**Files:**
- Create: `src/promptgrimoire/logging_discord.py`
- Modify: `src/promptgrimoire/__init__.py` (add processor to chain in `_setup_logging()`)

**Implementation:**

Create a structlog processor class that sends Discord webhook embeds on ERROR/CRITICAL events.

The processor should:

1. **Init:** Accept `webhook_url: str` and `dedup_window_seconds: float = 60.0`. Store a dict `_recent: dict[tuple[str, str], float]` for deduplication (key: `(exc_type, logger_name)`, value: last send timestamp).

2. **__call__:** The processor callable `(logger, method_name, event_dict) -> event_dict`:
   - If `webhook_url` is empty, return `event_dict` immediately (no-op, AC5.2)
   - If `event_dict.get("level")` is not "error" or "critical", return `event_dict`
   - Check deduplication: compute key from exception type + logger name. If sent within `dedup_window_seconds`, return `event_dict` (AC5.3)
   - Build Discord embed payload:
     - Title: `f"[{level.upper()}] {event_dict.get('event', 'unknown')}"` (truncate to 256 chars)
     - Description: exception message or traceback (truncate to 4096 chars)
     - Colour: ERROR = 15548997 (red), CRITICAL = 10040115 (dark red)
     - Fields: `user_id`, `workspace_id`, `export_id`, `request_path`, `logger`, `pid` — include only if present and not None
     - Timestamp: ISO 8601
   - Fire-and-forget: attempt `asyncio.get_running_loop().create_task()` to POST without blocking the log pipeline. If no event loop is running (e.g. during app startup in sync context, or in tests), fall back to `threading.Thread(target=asyncio.run, args=(self._send_webhook(...),), daemon=True).start()`. This handles the chicken-egg problem where `_setup_logging()` is called before NiceGUI's event loop starts.
   - Update dedup timestamp
   - Always return `event_dict` — never disrupt logging (AC5.4)

3. **_send_webhook:** Async method that POSTs to Discord:
   - Use `httpx.AsyncClient(timeout=10.0)`
   - Catch ALL exceptions — webhook failures must never propagate (AC5.4)
   - On 429 (rate limited), log a warning to stderr (not through structlog to avoid recursion)

4. **Truncation:** All embed fields must respect Discord limits:
   - Title: 256 chars
   - Description: 4096 chars
   - Field value: 1024 chars
   - Total embed: 6000 chars

**Integration with _setup_logging():**

In `__init__.py`'s `_setup_logging()`, after creating the processor chain:
- Import `get_settings` to get `settings.alerting.discord_webhook_url`
- Create the Discord processor instance
- Add it to the processor chain BEFORE `ProcessorFormatter.wrap_for_formatter()` (the last processor)
- The processor receives the structured event dict with all context fields already injected

**Testing:**

Tests must verify:
- structured-logging-339.AC5.1: An ERROR-level log triggers a webhook POST with correct embed format
- structured-logging-339.AC5.2: Empty webhook URL results in no POST attempt
- structured-logging-339.AC5.3: Two ERROR events with same `(exc_type, module)` within 60s produce only one webhook call
- structured-logging-339.AC5.4: A failing webhook POST (e.g. timeout) does not raise an exception or block logging

Use `monkeypatch` or `unittest.mock.patch` to mock `httpx.AsyncClient.post` in tests. Do NOT make real Discord API calls in tests.

Follow project testing patterns. Task-implementor generates actual test code at execution time.

**Verification:**

Run: `uv run ruff check src/promptgrimoire/logging_discord.py src/promptgrimoire/__init__.py && uvx ty check`
Expected: No lint or type errors

Run: `uv run grimoire test all`
Expected: All tests pass

**Commit:** `feat: add Discord webhook alerting processor with deduplication`

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Update .env.example with alerting config

**Files:**
- Modify: `.env.example` (add ALERTING__ section after BROWSERSTACK section, ~line 189)

**Implementation:**

Add a new section to `.env.example`:

```bash
# =============================================================================
# Error Alerting (ALERTING__)
# Discord webhook for ERROR/CRITICAL event notifications.
# Leave empty to disable alerting.
# =============================================================================

# Discord webhook URL — create via Server Settings → Integrations → Webhooks
ALERTING__DISCORD_WEBHOOK_URL=
```

**Verification:**

Run: `uv run ruff check . && uvx ty check`
Expected: No errors

**Commit:** `docs: add ALERTING__DISCORD_WEBHOOK_URL to .env.example`

<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->

## UAT Steps

1. Set `ALERTING__DISCORD_WEBHOOK_URL=` (empty) in `.env`, start app, trigger an error — verify NO Discord message sent
2. Set `ALERTING__DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN` in `.env`, start app
3. Trigger an error (e.g. navigate to an invalid workspace) — verify Discord channel receives an embed with severity colour, error message, and context fields
4. Rapidly trigger 10 identical errors within 5 seconds — verify only 1 Discord message sent (deduplication)
5. Wait 61 seconds, trigger the same error — verify a second Discord message is sent
6. Temporarily set webhook URL to an invalid URL, trigger an error — verify app logs still work (no crash from webhook failure)
