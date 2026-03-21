# Investigation: #377 Page Load Latency

**Date:** 2026-03-18
**Issue:** [#377](https://github.com/MQFacultyOfArts/PromptGrimoireTool/issues/377)
**Branch:** `incident-analysis-tools`
**Status:** Instrumentation prepared, root cause under test — awaiting production telemetry

## Source Inventory

### Production Data (from issue #377)

| Field | Value |
|-------|-------|
| Source | structlog JSONL (production) |
| Window | 2026-03-15 15:00 – 2026-03-17 18:25 AEDT |
| Timezone | UTC (ISO 8601 with Z suffix) |
| Event | `Response for {path} not ready after 3.0 seconds` |
| Count | 18,665 total (18,482 `/annotation`, 183 `/`) — **Unverified split**: the SQL below has no time predicate; these counts are from the full JSONL file, not the stated window. The per-route split needs re-running with a windowed query before the impact claim at Finding 5 can be promoted to Confirmed. |
| Provenance | `SELECT event, count(*) FROM jsonl_events WHERE level='warning' AND event LIKE 'Response for%not ready%' GROUP BY event` [incident_db.py, **no time filter** — covers full file, not just Mar 15–17 window] |

### Local Measurement Data

| Field | Value |
|-------|-------|
| Source | `logs/sessions/promptgrimoire-incident_analysis_tools.jsonl` |
| Timezone | UTC |
| Method | E2E tests (`test_organise_perf.py`, `test_page_load_concurrency.py`) |
| Pool type | NullPool (test environment — no connection pooling) |
| DB location | localhost PostgreSQL |

## Finding 1: Local page load is ~60ms (well under 3s threshold)

**Hypothesis:** The annotation page handler completes in <100ms under single-user local load.

**Evidence:**
- Source: `logs/sessions/promptgrimoire-incident_analysis_tools.jsonl` [UTC, E2E test run]
- Command: `jq 'select(.event == "page_load_total") | .elapsed_ms' promptgrimoire-incident_analysis_tools.jsonl`
- Result: 52 page loads, range 44–113ms, avg 61ms

**Falsification attempts:**
- Ran 52 page loads across 8 connected clients — no single load exceeded 113ms
- No "not ready" warnings generated locally

**Confidence:** Confirmed [local measurement, correct source, positive control passed (page loads succeed)]

**Scope:** In-window confirmed fact — but only for local environment with NullPool and localhost DB

## Finding 2: Idle connected clients do not degrade sequential page loads locally

**Hypothesis:** Sequential page load time does not increase when more NiceGUI clients are idly connected on localhost.

**Evidence:**
- Source: `logs/sessions/promptgrimoire-incident_analysis_tools.jsonl` [UTC, `test_page_load_concurrency.py`]
- Method: Created 8 workspaces **sequentially** (one at a time), each with a new browser context. Measured page reload time for each after creation. Earlier sessions remain idly connected during later measurements. **This is not a concurrent load test** — it measures whether idle connected clients add overhead to a single active page load.
- Result: Load #0 = 60ms, Load #51 = 51ms. No monotonic increase. Max spike = 113ms (noise).

**What this test discriminates:**
- It shows that idle connected clients (with their presence handlers, broadcast subscriptions, and CRDT state) do not measurably degrade a single sequential page load locally.
- It does **not** test concurrent page loads competing for the event loop or pool. That requires production telemetry or a QueuePool-based load test (not yet built).

**What this test cannot discriminate:**
- Event loop contention under truly concurrent page loads (multiple handlers running simultaneously)
- Pool contention (tests use NullPool — structurally impossible to reproduce)
- CRDT broadcast amplification under concurrent user actions

**Confidence:** Confirmed for the narrow claim (idle clients don't degrade sequential loads locally). Does NOT address concurrent load or pool contention.

**Scope:** In-window confirmed fact for local only

## Finding 3: 10+ sequential DB sessions per page load

**Hypothesis:** The annotation page handler acquires ~10 database sessions sequentially (not in parallel), each via `get_session()`.

**Evidence:**
- Source: Code trace of `_render_workspace_view` in `src/promptgrimoire/pages/annotation/workspace.py`
- Method: Followed every `await` call from `_render_workspace_view` entry to return, counting `get_session()` acquisitions

| # | Call site | File:Line | Session |
|---|-----------|-----------|---------|
| 1 | `get_workspace` | `workspace.py:382` via `workspaces.py` | New |
| 2 | `check_workspace_access` → `resolve_permission` | `workspace.py:399` via `acl.py` | New |
| 3 | `get_placement_context` | `workspace.py:417` via `workspaces.py` | New |
| 4 | `get_privileged_user_ids_for_workspace` | `workspace.py:431` via `acl.py` | New |
| 5 | `list_documents` (pre-load for header) | `workspace.py:828` via `workspace_documents.py` | New |
| 6 | `get_placement_context` (duplicate, in header) | `header.py:174` via `workspaces.py` | New |
| 7 | `get_or_create_for_workspace` (CRDT load) | `workspace.py:678` via workspace registry | New |
| 8 | `list_tags_for_workspace` (inside CRDT consistency) | via `tags.py` | New |
| 9 | `list_tag_groups_for_workspace` (inside CRDT consistency) | via `tags.py` | New |
| 10 | `list_documents` (duplicate, inside `document_container`) | `workspace.py:718` via `workspace_documents.py` | New |

**Falsification attempts:**
- Per-step timing confirms sequential execution: `resolve_step` events show `get_workspace` (0ms), `check_workspace_access` (6ms), `get_placement_context` (5-8ms), `get_privileged_user_ids` (6-7ms) — these add up to the total `resolve_context` phase time (18-22ms).
- If they were parallel, the total would equal the max, not the sum.

**Confidence:** Confirmed [code trace verified against timing data]

## Finding 4: Two duplicate DB calls per page load

**Hypothesis:** `get_placement_context` and `list_documents` are each called twice per page load with identical arguments.

**Evidence:**
- `get_placement_context`: called at `workspace.py:417` (inside `_resolve_workspace_context`) AND `header.py:174` (inside `_render_placement_chip`). Both pass `workspace_id`. Both open new sessions.
- `list_documents`: called at `workspace.py:828` (pre-load for header paragraph toggle) AND inside `document_container()` at line 718 (inside `@ui.refreshable`). Both pass `workspace_id`.

**Falsification attempts:**
- Could they serve different purposes? The `list_documents` in the header provides `first_doc` for paragraph toggle visibility. The one in `document_container` provides the doc list for rendering. Same query, same result, but consumed at different points.
- Could the data change between calls? No — both are called within the same page handler execution, before any user interaction.

**Confidence:** Confirmed [code-verified, identical function calls with identical arguments]

## Finding 5: NiceGUI cancels the handler AND deletes the client on timeout

**Hypothesis:** When a page handler exceeds `response_timeout` (default 3.0s), NiceGUI doesn't just log a warning — it cancels the task and deletes the client, resulting in a broken page for the user.

**Evidence:**
- Source: `.venv/lib/python3.14/site-packages/nicegui/page.py:179-186`
- Code:
  ```python
  done, _ = await asyncio.wait([task, task_wait_for_connection],
                                timeout=self.response_timeout,
                                return_when=asyncio.FIRST_COMPLETED)
  if not done:
      task.cancel()
      log.warning(f'Response for {client.page.path} not ready after {self.response_timeout} seconds')
      client.delete()
  ```

**Confidence:** Confirmed [NiceGUI source, version 3.8.0]

**Implication:** Production annotation page loads that exceed 3s result in broken pages, not just slow pages. The production count (18,482) is from the issue's unwindowed query and needs re-verification with a time-filtered command before being cited as a confirmed impact figure.

## Finding 6: `page_route` uses default 3.0s timeout

**Hypothesis:** Our `page_route` decorator does not override NiceGUI's default `response_timeout`.

**Evidence:**
- Source: `src/promptgrimoire/pages/registry.py:175`
- Code: `return ui.page(route)(_with_log_context)` — no `response_timeout` kwarg

**Confidence:** Confirmed [code-verified]

## Finding 7: Tests use NullPool, production uses QueuePool

**Hypothesis:** Pool contention cannot be reproduced in E2E tests because they use a fundamentally different connection strategy.

**Evidence:**
- Source: `src/promptgrimoire/db/engine.py:149-179`
- Test: `_PROMPTGRIMOIRE_USE_NULL_POOL=1` env var → `NullPool` (fresh connection per request)
- Production: `QueuePool(pool_size=80, max_overflow=15)` — connections are reused from a fixed pool

**Confidence:** Confirmed [code-verified]

**Implication:** With 10 sequential session acquisitions per page load and QueuePool, concurrent page loads compete for pool connections. Under NullPool, each request gets a fresh connection with no queuing.

## Inference: Production latency is caused by factors absent from local testing

**What differs between local (60ms) and production (>3000ms):**

| Factor | Local | Production |
|--------|-------|------------|
| DB pool | NullPool (no contention) | QueuePool (80+15 connections shared) |
| DB location | localhost | Same server but through asyncpg |
| Connected clients | 1-8 (test) | 30+ (class of 50 students) |
| CRDT state size | ~500 bytes (test content) | Unknown (could be large) |
| Broadcast handlers | 1-8 clients | 30+ clients per workspace |
| Event loop work | Test only | Presence, FTS worker, deadline worker, CRDT persistence |

**What additional evidence would help:**
1. Production `resolve_step` timing (which DB calls are slow under load)
2. Production `session_acquire_slow` events (pool contention direct measurement)
3. Production CRDT state sizes (bytes loaded per workspace)

## Instrumentation Deployed (this branch)

| Instrument | Event name | Level | What it measures |
|------------|-----------|-------|-----------------|
| Phase timing | `page_phase` | DEBUG | Wall time per phase: `resolve_context`, `list_documents`, `render_header`, `build_tab_panels` |
| Total timing | `page_load_total` | DEBUG | Total wall time for `_render_workspace_view` |
| Step timing | `resolve_step` | DEBUG | Per-call timing within `_resolve_workspace_context`: `get_workspace`, `check_workspace_access`, `get_placement_context`, `get_privileged_user_ids` |
| Session acquisition | `session_acquire_slow` | WARNING (>5ms) | Time to acquire a DB session from pool, with pool status snapshot |
| Session acquisition | `session_acquire` | DEBUG (<=5ms) | Normal session acquisition timing |
| Card rebuild | `card_rebuild` | DEBUG | Trigger source and epoch for every card list rebuild |

**To enable in production:** Set workspace.py and cards.py log levels to DEBUG (currently INFO). The `session_acquire_slow` fires at WARNING regardless of module level.

## Next Tests (production telemetry required)

The root cause is not yet confirmed. The instrumentation on this branch is designed to discriminate between competing hypotheses when deployed to production:

1. **Pool contention hypothesis:** If `session_acquire_slow` (WARNING >5ms) events appear frequently under load, pool wait time is a contributing factor. The pool status snapshot in each event shows checked-out vs available connections.
2. **Event loop saturation hypothesis:** If `page_load_total` shows high elapsed_ms but individual `resolve_step` times remain low, the latency is between steps (event loop yielding to other coroutines), not within DB calls.
3. **CRDT state size hypothesis:** If `build_tab_panels` phase dominates, the CRDT load (`get_or_create_for_workspace`) is the bottleneck. Compare against workspace CRDT state sizes.

### Why `asyncio.gather` is NOT recommended yet

The 4 sequential calls in `_resolve_workspace_context` (Finding 3, items 1–4) could theoretically be parallelised with `asyncio.gather`. However, **this is inconsistent with the leading pool contention hypothesis**: if production latency is caused by concurrent requests exhausting the QueuePool, then parallelising 4 sequential acquisitions into 4 simultaneous acquisitions per request would increase peak pool demand per request from 1 to 4. Under contention, this is a plausible regression, not an optimisation.

**Decision depends on production data:**
- If `session_acquire_slow` events are rare → pool contention is not the mechanism → `asyncio.gather` is safe and beneficial
- If `session_acquire_slow` events are frequent → pool contention is confirmed → parallelisation makes it worse; the fix is reducing total session count (e.g., combining queries into fewer sessions)

## Safe Actions (no hypothesis dependency)

1. **Deploy instrumentation to production** — merge this branch, set annotation module log levels to DEBUG temporarily. The `session_acquire_slow` fires at WARNING regardless of module level.
2. **Eliminate duplicate `get_placement_context`** — pass `ctx` from `_resolve_workspace_context` result through to header renderer. Saves 1 session per load regardless of root cause.
3. **Eliminate duplicate `list_documents`** — pass pre-loaded document list to `_build_tab_panels`. Saves 1 session per load regardless of root cause.
4. **Consider `response_timeout` increase** — 3.0s → 10.0s as stopgap to prevent client deletion (Finding 5). This does not fix latency but prevents the user-facing breakage.

## Peer Review Response Log

### Review 1: Codex (2026-03-18)

| # | Severity | Issue | Response |
|---|----------|-------|----------|
| 1 | High | `asyncio.gather` recommendation inconsistent with pool contention hypothesis | Replaced with "Next Tests" section explaining why parallelisation decision depends on production data |
| 2 | Medium | Finding 2 overstates what a sequential test discriminates | Narrowed claim to "idle connected clients don't degrade sequential loads locally"; added explicit "cannot discriminate" section |
| 3 | Medium | "Investigation complete" contradicts listed unknowns | Changed status to "Instrumentation prepared, root cause under test" |
| 4 | Medium | Production count not reproducible (no time predicate in SQL) | Marked count as Unverified in source inventory; weakened impact claim at Finding 5 |
