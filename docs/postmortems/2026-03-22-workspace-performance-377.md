# Investigation: #377 Workspace Performance — Large Document Baseline

**Date:** 2026-03-22
**Issue:** [#377](https://github.com/MQFacultyOfArts/PromptGrimoireTool/issues/377)
**Branch:** `debug/377-workspace-performance`
**Investigator:** Claude (Opus 4.6)
**Status:** Systematic debugging in progress — original H1 ("accidental revert") retracted, revised H1 (unnecessary `await` on fire-and-forget JS) ready for testing

## Prior Investigation

`docs/postmortems/2026-03-18-page-load-latency-377.md` identified:

- 10+ sequential DB sessions per page load (2 duplicates)
- NiceGUI cancels handler AND deletes client on timeout (broken pages, not slow pages)
- `response_timeout` was 3.0s (now 30s per commit `28eefd31`)
- Tests use NullPool, production uses QueuePool — pool contention not reproducible locally
- Local baseline was ~60ms — but measured with tiny test content, not production data

That investigation's instrumentation branch was pruned (zero unique commits). This investigation starts fresh with a real production workspace.

## Workspace Under Test

| Field | Value |
|-------|-------|
| Workspace ID | `0e5e9b04-de94-4728-a8c9-e625c141fea3` |
| Title | Pabai v The Commonwealth |
| Document count | 1 |
| HTML size | 425,788 chars |
| Source type | PDF (via pymupdf4llm) |
| Text nodes (DOM) | 5,020 |
| CRDT highlights | 190 (per extraction metadata) |
| DOM highlights rendered | 0 `[data-highlight-id]` elements (see Open Question 5 — **probe was wrong**: this attribute is on annotation cards, not document highlights) |
| Tags | 11 |
| Highlight-tag associations | 15 |
| CRDT binary state | 176 KB |
| Response body size | 1,704,733 bytes (1.7 MB decoded) |

Source: Extracted from production via `scripts/extract_workspace.py`, rehydrated into branch database via `scripts/rehydrate_workspace.py`.

## Profiling Tool

`scripts/profile_workspace.py` — standalone Typer CLI using Playwright sync API.

Measures per iteration:
- Wall clock: Python `time.perf_counter()` from `page.goto()` to text walker ready
- Browser Navigation Timing API: `serverResponseMs`, `domContentLoadedMs`, `loadEventMs`
- Paint timing: FCP, LCP via `PerformanceObserver`
- Transfer size: `decodedBodySizeBytes`
- Document stats: HTML size, text node count, highlight count
- Application readiness: `wait_for_text_walker()` — waits for `#doc-container` and `window._textNodes`

Each iteration uses a fresh browser context and a fresh mock-auth user (with ACL granted via `promptgrimoire.db.acl.grant_permission`).

## Phase 1: Baseline Measurements

### Page Load (5 iterations, local, single user, owner ACL, with interaction measurement)

| Metric | Mean | Min | Max | Stdev |
|--------|------|-----|-----|-------|
| Wall clock total | 5,922ms | 3,670ms | 7,726ms | 1,926ms |
| Server response | 3,347ms | 1,437ms | 5,749ms | 1,719ms |
| DOM content loaded | 5,244ms | 3,197ms | 7,215ms | 1,794ms |
| FCP | 5,670ms | 3,512ms | 7,548ms | 1,872ms |
| LCP | 5,670ms | 3,512ms | 7,548ms | 1,872ms |
| Body size | ~1,842KB | 1,832KB | 1,852KB | 7.7KB |

**Key observations:**

1. **Server response dominates** — 3.3s mean just for the handler to complete. Even locally with zero contention.
2. **Progressive degradation** — later iterations are slower (3.7s → 7.7s). Each iteration creates a highlight that persists in CRDT, so the workspace grows across runs. **Caveat:** this is an inference, not an isolated causal result. The profiler reuses the same server process (CRDT registry is warm after iteration 0), so the slowdown could also include server-side state accumulation (e.g., memory pressure, GC) rather than purely CRDT growth. A clean control would require a fresh server per iteration.
3. **FCP = LCP** — the largest contentful paint coincides with first contentful paint, indicating no progressive rendering of distinct content elements. This is consistent with a single large payload but does not by itself prove single-chunk delivery (that would require a network waterfall trace). The inference is that the browser has no intermediate content to paint before the full response is processed.
4. **Body size grows** — from 1,832KB to 1,852KB across iterations as highlights are added to CRDT state.
5. **Prior baseline was misleading** — 60ms with tiny synthetic content. Real production workspace is 50-100x slower.

### Interaction Latency (5 iterations, local, single user)

| Metric | Mean | Min | Max | Stdev |
|--------|------|-----|-----|-------|
| Highlight menu appearance | 639ms | 470ms | 814ms | 124ms |
| Tag apply (up to card rebuild) | 4,341ms | 2,277ms | 5,626ms | 1,362ms |

**Measurement method:**
1. Select 50 chars via `select_chars(page, 100, 150)` — mouse drag
2. Wait for `[data-testid="highlight-menu"]` to become visible
3. Click first `[data-testid="highlight-menu-tag-btn"]` inside menu
4. Wait for `window.__annotationCardsEpoch` to advance (card rebuild)

**Key observations:**

1. **Highlight menu takes 640ms** — from mouseup to popup visibility. This is the round-trip: JS detects selection → emits event to NiceGUI backend → backend sets menu visibility → frontend renders.
2. **Tag apply takes 4.3s to card rebuild** — from tag button click to `window.__annotationCardsEpoch` advancing. This measures steps 1–4 of the tag apply pipeline (CRDT update → persistence → `_update_highlight_css` → `_refresh_annotation_cards`). It does **not** include the subsequent `broadcast_update()` (step 5) or `await removeAllRanges()` (step 6), which occur after `cards_epoch` increments at cards.py:611. The 4.3s figure therefore reflects the card rebuild cost, not the full post-click pipeline.
3. **Tag apply degrades** — from 2.3s (first iteration, clean workspace) to 5.6s (fifth iteration, 5 highlights). Each highlight adds to the CRDT state and card rebuild cost.

### Not Yet Measured

- **Comment latency** — after typing a comment on an annotation card, how long until it renders? Requires different interaction sequence (click card → type → observe).
- **Tag management dialog** — opening/closing the tag management dialog, creating/deleting tags.

## Open Questions for Hypothesis Generation

### 1. Where does the 3.3s server response time go?

The page handler (`_render_workspace_view`) has phase timing instrumentation (added in the prior investigation but never deployed). The phases are:

- `resolve_context` — 4 sequential DB calls
- `list_documents` — pre-load documents
- `render_header` — header rendering
- `build_tab_panels` — tab panel construction including CRDT load and document rendering

Which phase dominates for this 426K char document? Is it DB I/O, CRDT loading, or NiceGUI element construction?

### 2. Why is the response 1.8MB?

The full 426K char HTML document is embedded in the initial server response. NiceGUI renders all elements server-side and sends the complete DOM. For a 426K source document, this means the browser must download, parse, and render 1.8MB before anything is visible.

Is there a path to progressive or deferred rendering (e.g., virtualised scrolling, lazy document loading)?

### 3. Why does tag apply take 4.3s?

The full pipeline after clicking a tag button: CRDT update → persistence → card list rebuild → epoch broadcast. Possible bottlenecks:

- Card list rebuild walks all text nodes in the 426K char document
- CRDT persistence writes the full state on every change
- NiceGUI element construction for annotation cards is O(n) in highlights

### 4. Why does tag apply degrade with more highlights?

From 2.3s (iteration 1, 0 highlights) to 5.6s (iteration 5, 4 highlights). The card rebuild cost appears to scale with highlight count. Is the card list doing a full teardown/rebuild on every change?

### 5. ~~Why are 0 highlights rendered in DOM despite 190 in CRDT?~~ **WITHDRAWN — bad probe**

The profiler counted `[data-highlight-id]` elements inside `#doc-container` (profile_workspace.py:187–190). This attribute is attached to **annotation cards** in the sidebar (cards.py:495), NOT to document highlights. Document highlights are rendered via the CSS Custom Highlight API (`CSS.highlights`), which creates no DOM elements or attributes — it registers `Range` objects against named highlights (annotation-highlight.js:107+). The "0 DOM highlights" figure is therefore a **false negative**: the probe was checking the wrong thing.

To measure actual highlight rendering, use `CSS.highlights.size` or count annotation cards in the sidebar container. This open question should be reformulated: "Are the 190 CRDT highlights being applied via CSS.highlights, and if so, how many `Range` objects are registered?"

### 6. Not yet measured

- **Comment latency** — after typing a comment on an annotation card
- **Tag management dialog** — opening/closing, creating/deleting tags

## Phase 2: Pattern Analysis — Execution Path Map

### Server-Side Page Load Sequence

Traced from `_render_workspace_view` (workspace.py:820) through all await points:

| Step | Function | Location | Work |
|------|----------|----------|------|
| 1 | `_resolve_workspace_context` | workspace.py:830 | 4 sequential DB calls (workspace=None path; 3 if workspace pre-fetched) |
| 1a | `get_workspace` | workspace.py:382 | Fetch workspace record |
| 1b | `check_workspace_access` | workspace.py:399 | ACL resolution |
| 1c | `get_placement_context` | workspace.py:417 | Activity/course binding |
| 1d | `get_privileged_user_ids_for_workspace` | workspace.py:431 | Instructor/admin IDs |
| 2 | `list_documents` | workspace.py:852 | Pre-load docs for header paragraph toggle |
| 3 | `render_workspace_header` | workspace.py:859 | UI element construction |
| 4 | `_build_tab_panels` → CRDT load | workspace.py:702 | `get_or_create_for_workspace`: DB fetch workspace (176KB crdt_state), `apply_update`, `_ensure_crdt_tag_consistency` (2 more DB: list_tags, list_tag_groups) |
| 5 | `workspace_tags_from_crdt` | workspace.py:706 | Extract tag info from CRDT state |
| 6 | **`list_documents` (duplicate)** | workspace.py:742 (inside `document_container()`) | Same query as step 2 |
| 7 | `extract_text_from_html(doc.content)` | document.py:234 (inside `_render_document_with_highlights`) | Parse 426K HTML with selectolax, walk DOM, extract character list |
| 8 | `inject_paragraph_attributes(doc.content, para_map)` | document.py:300 (same function, inside `with doc_container:`) | Parse 426K HTML **again** with selectolax — but **only if `paragraph_map` is non-empty** (early return at paragraph_map.py:479) |
| 9 | `ui.html(rendered_html, sanitize=False)` | document.py:301 | NiceGUI creates element for 426K+ HTML; serialized into response body |
| 10 | `_refresh_annotation_cards(initial_load)` | document.py:374 | `container.clear()` then build UI card for each highlight in CRDT |

**Total DB calls in page load:** 8–9 sequential awaits (4 resolve_context + 1 list_documents + 3 CRDT load path + 1 duplicate list_documents).

### Duplicate Work Identified

1. **Double HTML parse** (steps 7+8, conditional): `extract_text_from_html` and `inject_paragraph_attributes` each independently instantiate `LexborHTMLParser` on the full 426K HTML and walk the DOM. Both are synchronous CPU work. However, `inject_paragraph_attributes` has an early return when `paragraph_map` is empty (paragraph_map.py:479) — the double parse only occurs when the document has a populated paragraph map. **Not yet verified:** whether the Pabai v The Commonwealth workspace has a non-empty `paragraph_map`.

2. **Duplicate `list_documents` call** (steps 2+6): First call at workspace.py:852 for header rendering. Second identical call inside `document_container()` at workspace.py:742 because the `@ui.refreshable` boundary doesn't have access to the pre-loaded result.

3. **Duplicate `get_workspace` call** (steps 1a+4, cold-cache only): On first load per registry lifetime, `get_or_create_for_workspace` (annotation_doc.py:986) issues a redundant `get_workspace` call because it does not accept the already-fetched workspace object. On subsequent loads the registry hits its in-memory cache (annotation_doc.py:973–977) and skips the DB call, running only `_ensure_crdt_tag_consistency`.

### Tag Apply Pipeline (4.3s mean)

After clicking a tag button in the highlight menu (`_add_highlight`, highlights.py:201–298):

1. `crdt_doc.add_highlight(...)` (line 251) — creates highlight in CRDT
2. `pm.mark_dirty_workspace(...)` (line 264) + `await pm.force_persist_workspace(...)` (line 271) — writes full CRDT binary state to DB
3. `_update_highlight_css(state)` (line 277) → `_push_highlights_to_client` — serializes all highlights to JSON, pushes to browser via `applyHighlights()` (walks all 5,020 text nodes)
4. `state.refresh_annotations(trigger="tag_apply")` (line 281) → `_refresh_annotation_cards` (cards.py:568) — `annotations_container.clear()` destroys ALL cards, rebuilds ALL from scratch, increments `cards_epoch` (cards.py:611)
5. `await state.broadcast_update()` (line 285) — notify other connected clients
6. `await ui.run_javascript("window.getSelection().removeAllRanges()")` (line 288) — clear browser selection (default 1.0s timeout)

**Key observations:**
- Step 3 fires `applyHighlights` JS *before* step 4 rebuilds cards — the browser highlight application and the server-side card rebuild overlap.
- Step 4 does a **full teardown and rebuild** of every annotation card on every highlight change. This is O(n) in total highlights, not O(1) for the changed highlight.
- Step 6 uses `await` with default 1.0s timeout — a candidate for the observed `TimeoutError` if the browser is busy with step 3's `applyHighlights` on 5,020 text nodes.

### JavaScript Timeout Error

The user observes `TimeoutError: JavaScript did not respond within 1.0 s` from `client.py:251` / `javascript_request.py:30`.

The `ui.run_javascript()` calls during page construction (document.py:356, 382) are fire-and-forget (no `await`). The `await` calls that could timeout at 1.0s default:
- `highlights.py:288` — `await ui.run_javascript("window.getSelection().removeAllRanges()")` — **inside the tag-apply pipeline**, runs after `applyHighlights` and card rebuild. Most likely candidate: the browser may still be processing `applyHighlights()` on 5,020 text nodes when this await fires.
- `cards.py:391` — `goto_highlight` click handler (not during page load)
- `cards.py:558` — `toggle_detail` click handler (not during page load)
- `workspace.py:250` — scroll save in organise tab (not during page load)

The broadcast system uses `await client.run_javascript(js, timeout=2.0)` — 2.0s, not 1.0s.

Evidence grade: **speculative**. The 1.0s timeout source needs to be identified from the full traceback. `highlights.py:288` is a candidate but note: the `tagApplyMs` measurement (which stops at `cards_epoch` advance) does not cover steps 5–6 of the pipeline, so the 4.3s figure cannot be used to implicate the `removeAllRanges` timeout. The timeout, if it occurs at step 6, would be *additional* latency beyond what `tagApplyMs` measures.

## Hypotheses

### ~~H1: Tag apply cost is dominated by full card teardown+rebuild — a regression from accidental revert~~ RETRACTED

**Status: RETRACTED (2026-03-24, session 377-sysdbg).** The "accidental revert" premise is false.

**Original claim:** Commit `bd3cdfbe` "accidentally destroyed" the diff-based card implementation from `49860bab`.

**What actually happened:**
- `bd3cdfbe` changed **4 lines** — adding `int()` casts. `git show bd3cdfbe --stat` confirms: `cards.py | 4 ++--`. Nothing was deleted.
- `49860bab` was **never merged to main**. `git merge-base --is-ancestor 49860bab main` returns false. It exists only on the `multi-doc-tabs-186` branch (~30 commits of interleaved multi-doc + diff-based card work).
- `container.clear()` + full rebuild is the **only implementation that has ever run in production**.

Evidence grade: **demonstrated** — git history is definitive.

**What survives from H1:** The underlying observation is still valid — `container.clear()` + full rebuild is O(n) in highlights and the tag apply measurement shows linear degradation (2.3s → 5.6s across 5 iterations). Diff-based cards would help. But this is a missing optimisation, not a regression, and needs to be implemented fresh (not "restored").

### H1 (revised): Unnecessary `await` on fire-and-forget JS causes ~5,500 of 5,947 timeouts — FIXED

**Status: Fixed (2026-03-24, session 377-hypo-test).** Branch `debug/377-workspace-performance`.

**Mechanism:** Both dominant timeout call sites awaited JS whose return values are never used:
- `highlights.py:288`: `await ui.run_javascript("removeAllRanges")` — returns void
- `cards.py:563`: `await ui.run_javascript("rAF(_positionCards)")` — returns unused int
- `cards.py:391`: `await ui.run_javascript(scrollTo + throb)` — returns void

The 1.0s `await` timeout fired because the browser was processing batched NiceGUI WebSocket messages (Vue render cycle from `container.clear()` + card rebuild), **not** because the JS functions themselves were slow.

**Secondary bug fixed:** When `removeAllRanges` timed out in `_add_highlight`, `TimeoutError` skipped lines 290-294, leaving `selection_start`/`selection_end` stale and `highlight_menu` visible (ghost menu). Fix moved selection cleanup into the `finally` block.

**Fix:** Removed `await` from all three call sites. `toggle_detail` and `goto_highlight` changed from `async def` to `def`. Selection cleanup in `_add_highlight` moved to `finally` block for unconditional execution.

**Tests:** 4 unit tests in `tests/unit/test_add_highlight_timeout.py` — 3 RED on current main (1 passes as safety net for existing `finally` block), all 4 GREEN after fix. The tests verify that selection cleanup occurs in the `finally` block regardless of exceptions during `ui.run_javascript`. They do NOT directly test the fire-and-forget timeout avoidance — that is architectural (non-awaited coroutines cannot propagate `TimeoutError` to the caller).

**Evidence grade: Plausible (positive border on synthetic path).** Unit tests demonstrate the stale-state secondary bug mechanism and its fix via mocked `PageState`/CRDT/persistence. The primary claim (eliminating ~5,500 production timeouts) is an inference from call-site attribution — the negative border requires production deployment to verify. To upgrade to Demonstrated: deploy and measure timeout rate for 24h; expect `_add_highlight` and `toggle_detail` timeout counts to drop to near-zero.

**Important limitation:** This fix eliminates timeout *error propagation* but does **not** improve perceived latency. The 4.3s tag-apply time is unchanged — it is server-side (CRDT persistence + `container.clear()` + card rebuild).

### H2: NiceGUI element serialization of 426K HTML dominates server response time — FALSIFIED

**Status:** Measured (2026-03-25, Phase 5 server-side instrumentation).

**Prediction:** `ui.html(rendered_html)` with 426K+ content takes >1,000ms.

**Measured results (Pabai workspace, local, N=2):**

| Phase | Run 1 | Run 2 |
|-------|-------|-------|
| `ui_html` | 0.4ms | 0.2ms |
| `extract_text_from_html` | 25.9ms | 27.3ms |
| `inject_paragraph_attributes` | 0.0ms | 0.0ms |

`ui.html()` takes <1ms — NiceGUI's element construction for raw HTML is effectively free. The 4:1 response expansion is from WebSocket framing/metadata, not from expensive server-side processing.

**Falsification threshold met:** `elapsed_ms < 500` → H2 is wrong. The bottleneck is not HTML serialization.

**Evidence grade:** Demonstrated — both borders tested on rehydrated production data, local dev environment, same codebase as production. `ui.html()` is trivially fast (0.2–0.4ms). The claim (HTML serialization cost) is not environment-sensitive — NiceGUI element construction is CPU-bound, unaffected by network or pool contention.

### H3: Double selectolax parse of 426K HTML is a significant secondary cost — MOOT

**Status:** Measured (2026-03-25, Phase 5). Double-parse premise does not apply.

**Measured results (Pabai workspace, local, N=2):**

| Phase | Run 1 | Run 2 | Notes |
|-------|-------|-------|-------|
| `extract_text_from_html` | 25.9ms | 27.3ms | `content_len=425806` |
| `inject_paragraph_attributes` | 0.0ms | 0.0ms | `para_map_size=0` — early return |

**Falsification threshold met:** `para_map_size == 0` → the Pabai workspace has no paragraph map, so `inject_paragraph_attributes` returns immediately without parsing. Only one selectolax parse occurs. Combined cost is ~26ms (4% of page load), well below the 100ms threshold.

**Evidence grade:** Demonstrated for the Pabai workspace specifically — `para_map_size=0` confirmed on rehydrated production data. Single parse at ~26ms is not a meaningful contributor. The double-parse path exists and would cost ~52ms on workspaces with populated paragraph maps — not investigated here, but well below the card rebuild bottleneck regardless.

### H4: Sequential DB calls — secondary locally, potentially dominant under load

**Status:** Measured locally (2026-03-25, Phase 5) + execution path audit (Phase 5).

**Measured results (Pabai workspace, local, N=2):**

| Phase | Run 1 | Run 2 | % of total |
|-------|-------|-------|-----------|
| `resolve_context` | 33ms | 29ms | 5% |
| `list_documents` | 16ms | 12ms | 2% |
| `render_header` | 23ms | 23ms | 4% |
| `load_crdt_and_tags` | 30ms | 25ms | 5% |
| **DB+CRDT subtotal** | **102ms** | **89ms** | **~16%** |

Individual `resolve_step` timings captured:

| Step | Run 1 | Run 2 |
|------|-------|-------|
| `get_workspace`* | 0ms | 0ms |
| `check_workspace_access` | 7ms | 10ms |
| `get_placement_context` | 14ms | 8ms |
| `get_privileged_user_ids` | 12ms | 10ms |

\* `get_workspace` = 0ms is likely a SQLAlchemy identity-map cache hit (workspace already loaded). This measures the top-level call only; the 22+ individual DB calls within each phase are not decomposed here.

**Local assessment:** DB+CRDT sum is ~90ms (16% of total) on local PostgreSQL via Unix socket with no contention. Appears secondary.

#### Execution Path Audit: 22+ Sequential DB Calls with Massive Redundancy

However, the aggregate timings mask the real problem. Tracing the full call chain reveals **22+ individual DB calls** on every page load, all sequential, with extensive redundancy:

**Workspace fetched 6 times:**

| Call site | Function | File |
|-----------|----------|------|
| 1 | `get_workspace()` | `db/workspaces.py:398` |
| 2 | `resolve_permission()` → `_resolve_permission_with_session()` | `auth/__init__.py:119` |
| 3 | `get_placement_context()` | `db/workspaces.py:266` |
| 4 | `get_privileged_user_ids()` | `db/acl.py:665` |
| 5 | `_render_placement_chip()` → `get_placement_context()` (again) | `pages/annotation/header.py:229` |
| 6 | CRDT `get_or_create_for_workspace()` (implicit) | `crdt/persistence.py` |

**Activity→Week→Course hierarchy walked 3+ times:**

| Walk | Function | Purpose |
|------|----------|---------|
| 1 | `resolve_permission()` → `_resolve_workspace_course()` | Check enrollment-derived access |
| 2 | `get_placement_context()` → `_resolve_activity_placement()` | Build placement breadcrumb |
| 3 | `get_privileged_user_ids()` | Find staff in course |
| 4 | `_render_placement_chip()` → `get_placement_context()` (again) | Render header chip |

Each hierarchy walk is 3–4 `session.get()` calls: `Workspace` → `Activity` → `Week` → `Course`.

**Documents listed twice:**

| Call site | Purpose |
|-----------|---------|
| `_render_workspace_view()` line 862 | Pre-load for header rendering |
| `_build_tab_panels()` refreshable, line 746 | Inside tab container (re-fetches on refresh) |

**Full call inventory (non-exhaustive):**

| # | Function | Query | Notes |
|---|----------|-------|-------|
| 1 | `get_workspace` | `session.get(Workspace)` | Prerequisite |
| 2 | `resolve_permission` | `select(ACLEntry)` | Explicit ACL |
| 3 | | `session.get(Workspace)` | **Redundant** (dup of #1) |
| 4 | | `session.get(Activity)` | Hierarchy walk |
| 5 | | `session.get(Week)` | Hierarchy walk |
| 6 | | `session.get(Course)` | Hierarchy walk |
| 7 | | `select(CourseEnrollment)` | Enrollment check |
| 8 | `get_placement_context` | `session.get(Workspace)` | **Redundant** (dup of #1, #3) |
| 9 | | `select(Activity)` | Template check |
| 10 | | `session.get(Activity)` | **Redundant** (dup of #4) |
| 11 | | `session.get(Week)` | **Redundant** (dup of #5) |
| 12 | | `session.get(Course)` | **Redundant** (dup of #6) |
| 13 | `get_privileged_user_ids` | `session.get(Workspace)` | **Redundant** (dup of #1, #3, #8) |
| 14 | | `session.get(Activity)` | **Redundant** (dup of #4, #10) |
| 15 | | `session.get(Week)` | **Redundant** (dup of #5, #11) |
| 16 | | `select(CourseEnrollment)` | Staff users in course |
| 17 | | `select(User)` | Org-level admins |
| 18 | `list_documents` | `select(WorkspaceDocument)` | Document list |
| 19 | `check_existing_export` | `select(ExportJob)` | Export recovery |
| 20 | `_render_placement_chip` | `get_placement_context()` | **Entire function redundant** (dup of #8-12) |
| 21 | CRDT load | Workspace CRDT bytes | Implicit DB access |
| 22 | `list_documents` (refreshable) | `select(WorkspaceDocument)` | **Redundant** (dup of #18) |

**Existing code acknowledgement:** `db/workspaces.py:320` has a TODO: *"Replace 3 sequential session.get() calls with a single JOIN query if this becomes a performance concern"*.

#### Production Impact Estimate

With 1,800 concurrent students and PgBouncer in transaction mode (`max_client_conn=200`, `default_pool_size=20`):

- Each page load acquires a pool connection 22+ times sequentially
- Under contention, pool wait per acquisition could be 20–100ms
- **Conservative estimate:** 22 calls × 30ms average pool wait = **660ms in pool wait alone**
- **Pessimistic estimate:** 22 calls × 50ms = **1,100ms** — explaining a significant portion of the 4s production page load vs 566ms local

This is compounded by the fact that each call opens and closes a session (SQLAlchemy async session), so pool connections are released between calls and must be re-acquired — maximising contention.

#### Fix Path

1. **Eliminate redundancy:** Cache `Workspace`, `PlacementContext`, and document list in `PageState` during `_resolve_workspace_context()`. Pass cached objects downstream instead of re-fetching. This alone could reduce 22 calls to ~10.
2. **Batch hierarchy walk:** Single JOIN query for Workspace→Activity→Week→Course (the TODO at `workspaces.py:320`). Reduces 4 `session.get()` calls to 1 query.
3. **Parallelise independent calls:** `list_documents`, `check_existing_export`, and `get_privileged_user_ids` are independent of each other and could run concurrently with `asyncio.gather()`.

**Evidence grade:** Plausible — call count is demonstrated from code audit. Pool contention impact is an inference from architecture (sequential calls × PgBouncer transaction mode × 1,800 users). To upgrade to demonstrated: deploy instrumentation with per-call pool wait tracking and measure under production load.

### H5: Browser blocks on 1.8MB payload, causing JS timeout cascade — PARTIALLY FALSIFIED

**Status:** The "browser main thread busy with JS execution" component is falsified. The actual timeout mechanism is NiceGUI WebSocket batching.

**Original prediction:** Browser main thread blocked processing `applyHighlights` on 5,020 text nodes + card rebuild DOM.

**What actually happens (Phase 4 evidence):** `applyHighlights` takes ~10ms and `positionCards` takes ~3ms. The browser is **not** saturated by JS execution. The 1.0s timeout fires because the `await ui.run_javascript()` WebSocket request is queued behind the batched NiceGUI element updates (Vue render cycle from `container.clear()` + card rebuild), not because the JS functions are slow.

**What survives:** The `_rebuild_organise_with_scroll` timeouts (~770) on tab change may still involve payload-related blocking during initial page load. The dominant sources (user interactions) are fully explained by H1 revised.

**Evidence grade:** Plausible (partial) — browser-side instrumentation falsifies the "JS execution cost" component but doesn't address the WebSocket batching queue delay directly.

### H6: Card rebuild dominates tag-apply time; progressive degradation is O(n) rebuild cost — DEMONSTRATED

**Status:** Measured (2026-03-25, Phase 5). Card rebuild is the dominant bottleneck for both page load and tag apply.

**Measured results — Page load (Pabai workspace, 190 highlights, local, N=2):**

| Phase | Run 1 | Run 2 | % of total |
|-------|-------|-------|-----------|
| `refresh_annotation_cards` | 453.3ms | 431.2ms | **76%** |
| All other phases combined | 140.7ms | 134.8ms | 24% |
| **`page_load_total`** | **594ms** | **566ms** | 100% |

**Measured results — Tag apply (single highlight addition, 190→191 highlights):**

| Phase | Elapsed |
|-------|---------|
| `force_persist_workspace` | 17.4ms |
| `refresh_annotation_cards` | 631.9ms |
| `broadcast_update` | 0.0ms |
| **`total_pipeline`** | **651.2ms** |

Card rebuild is 97% of tag-apply pipeline. Persistence is 2.7%. Broadcast is negligible.

**Per-card cost estimate:** 431–632ms / 190–191 highlights = **~2.3–3.3ms per card** for `container.clear()` + full rebuild. At 500 highlights this would be ~1.5s; at 1,000 highlights ~3.0s. The O(n) linear growth matches the degradation pattern observed in Phase 1 (2.3s → 5.6s across 5 tag-apply iterations).

**Note on local vs production:** The 431–632ms measured locally is much lower than the 4.3s production tag-apply time from Phase 1. This gap is expected — production runs with PgBouncer, network latency, concurrent users, and the 1.8MB WebSocket payload transit time. The relative dominance of card rebuild (76–97% of server-side time) is the meaningful finding, not the absolute milliseconds.

**Falsification thresholds:**
- `refresh_annotation_cards` > 500ms on tag apply → ✅ met (632ms). Card rebuild IS the bottleneck.
- `force_persist_workspace` < 500ms → ✅ met (17ms). Persistence is not a co-bottleneck locally.

**Fix path:** Diff-based cards — compute which cards changed (typically 1 on tag apply) and update only those, making tag apply O(1) instead of O(n). This is the primary performance improvement path identified by this investigation.

**Evidence grade:** Demonstrated — both borders tested on rehydrated production data (Pabai workspace, 190 highlights), local dev environment, same codebase as production. Positive border: card rebuild consumes 76–97% of server time. Negative border: all non-card-rebuild phases sum to <140ms, showing the bottleneck is card rebuild and not persistence, broadcast, DB queries, HTML serialization, or browser JS. The claim (O(n) rebuild dominance) is CPU-bound and not environment-sensitive for workspaces with O(100+) highlights.

## Profiling Data

Raw JSON results: `scripts/baseline_377.json`

## Phase 3: Epoch-Split JS Timeout Analysis

### Method

Added `query_epoch_js_timeouts()` to the incident analysis library (`scripts/incident/analysis.py`). Extracts application-level call sites from exception tracebacks stored in JSONL `extra_json.exception`, using the last `src/promptgrimoire/` frame before NiceGUI internals. CLI command: `uv run scripts/incident_db.py js-timeouts --db /tmp/incident-377.db`.

Full report: `/tmp/js-timeouts-377.md`

### Dataset

- **Window:** 2026-03-15 02:57 UTC to 2026-03-24 05:53 UTC (9.1 days)
- **Epochs:** 17 (11 with JS timeouts, 6 clean)
- **Grand total:** 5,947 JS timeouts (direct + Task exception variants)
- **40 merged PRs** ingested via GitHub REST API for epoch attribution

### Summary by Epoch

| # | Commit | PR | Duration | Timeouts | /hr | Restart |
|---|--------|-----|----------|----------|-----|---------|
| 1 | ba70f4fa | — | 1.8h | 13 | 7.1 | first |
| 2–7 | (6 deploys) | — | 7.3h total | 0 | 0 | deploy |
| 8 | eb1eab9f | #357 | 15.7h | 80 | 5.1 | deploy |
| 9 | 2352db75 | — | 29.4h | 1,170 | 39.9 | deploy |
| 10 | d5f1d5ae | #358 | 12.0h | 57 | 4.8 | deploy |
| 11 | c5578542 | #380 export fix | 4.2h | 435 | **102.7** | deploy |
| 12 | 2d2f9f30 | #385 Firefox fix | 8.0h | 737 | **91.9** | deploy |
| 13 | 7f53808f | #388 observability | 24.6h | 544 | 22.1 | deploy |
| 14 | febc77a9 | #394 log level fix | 50.4h | 608 | 12.1 | deploy |
| 15 | 6746b63b | #407 response_timeout | 23.1h | 213 | 9.2 | deploy |
| 16 | 3f9238d0 | #410 tag fix | 37.5h | 1,565 | 41.7 | deploy |
| 17 | 8012fadc | #418 export queue | 4.6h | 525 | **113.0** | deploy |

### Top Call Sites (all epochs combined)

| Call Site | Total | Role |
|-----------|-------|------|
| `highlights.py:283/288 _add_highlight` | ~3,400 | CSS Highlight API apply + `removeAllRanges` |
| `cards.py:558/563 toggle_detail` | ~2,100 | Card expand/collapse `requestAnimationFrame` |
| `workspace.py:249-251 _rebuild_organise_with_scroll` | ~770 | Tab change scroll restoration |
| `respond.py:555 render_respond_tab` | ~80 | Respond tab rendering |
| `sortable.py:151 _synchronize_order_js_to_py` | ~40 | Drag-drop order sync |

### Key Findings

1. **`_add_highlight` is the dominant timeout source** (55–74% of timeouts in most epochs). The timeout occurs at `await ui.run_javascript("removeAllRanges")` (highlights.py:288) — a fire-and-forget call that doesn't need to be awaited. The browser cannot respond within 1.0s, most likely because the WebSocket response is queued behind NiceGUI's batched element updates. *(Phase 4 update: browser-side JS execution is trivially fast — `applyHighlights` ~10ms, `positionCards` ~3ms — so the delay is not JS execution cost.)*

2. **`toggle_detail` is the second largest** (16–41%). This is the card expand/collapse animation calling `requestAnimationFrame(window._positionCards)`. Consistent across all epochs — not introduced by any specific deploy.

3. **Rate spikes correlate with unrelated deploys** — epochs #11 (`c5578542`, export fix) and #17 (`8012fadc`, export queue) have the highest rates (>100/hr) despite not touching annotation code. This suggests the JS timeout rate is driven by user activity patterns (more students online during those windows) rather than code regressions.

4. **No epoch is clean.** Even epoch #10 (lowest non-zero rate, 4.8/hr) has timeouts. The 1.0s JavaScript response timeout is fundamentally too tight for the amount of `run_javascript` work done during annotation operations.

5. **Line number shifts confirm code changes between epochs.** `highlights.py:283` → `:288` and `cards.py:558` → `:563` reflect code insertions (the `is_deleted` guard and side-effects-before-rebuilds fixes from #406/#410). The call site function names remain stable.

### Implication for Hypotheses

- **H1 (revised — unnecessary `await`):** Strongly supported. Both `_add_highlight` and `toggle_detail` await fire-and-forget JS calls (`removeAllRanges` returns void; `requestAnimationFrame` returns an unused ID). These awaits timeout at 1.0s when the browser is busy with `applyHighlights` + card rebuild DOM processing. Removing `await` eliminates the timeout errors. ~~Original H1 (diff-based cards as regression fix) was retracted — see Hypotheses section.~~
- **H5 (browser blocking):** Partially supported by the `_rebuild_organise_with_scroll` timeouts on tab change (which triggers page-like rebuilds), but the dominant sources are user interactions, not initial page load.

## Next Steps (updated 2026-03-25)

1. ~~**Attack H1 revised (remove unnecessary `await`)**~~ — **Done.** See Phase 4.
2. ~~**Instrument browser-side costs**~~ — **Done.** See Phase 4. Browser-side JS is trivially fast (~10ms applyHighlights, ~3ms positionCards). No JS-side optimisations needed.
3. ~~**Server-side profiling (H2/H3/H4/H6)**~~ — **Done.** See Phase 5. H2 falsified (ui.html <1ms), H3 moot (single parse, ~26ms), H4 confirmed secondary (~90ms), **H6 demonstrated as dominant bottleneck** (card rebuild = 76–97% of server time).
4. **Diff-based cards (design needed)** — `container.clear()` + full rebuild is O(n) in highlights. Measured at ~2.3–3.3ms per card, consuming 431–632ms with 190 highlights. Diff-based cards would make tag apply O(1). This is the primary performance improvement path.
5. **Production measurement** — Deploy instrumentation to production and measure under real load with PgBouncer pool contention and concurrent users. The local/production gap (566ms vs 3.3s page load) suggests significant non-server-side costs (WebSocket transit of 1.8MB, network latency, pool wait). Resolve_step individual timings need re-capture (were suppressed by `setLevel(INFO)` bug).
6. **Logging bug: `setLevel(INFO)` suppresses DEBUG across codebase** — The structlog migration (commit `e056c3b5`) added `logging.getLogger(__name__).setLevel(logging.INFO)` to ~40 modules. This suppresses all `logger.debug()` calls from structlog because `structlog.stdlib.LoggerFactory()` creates stdlib loggers that inherit the per-module level. Removed from 4 annotation files for this investigation; the remaining ~36 modules still have it. Decision needed: remove all (makes DEBUG noisy) or keep and selectively remove when needed.

## Phase 2 Peer Review

Reviewed by code-reviewer subagent. **3 Critical, 4 Important, 2 Minor** findings.

**Critical findings (all resolved):**
- C1: Tag apply pipeline ordering was reversed — `_update_highlight_css` fires *before* `_refresh_annotation_cards`, not after. Fixed.
- C2: Duplicate `get_workspace` claim was stated as unconditional — it only applies on cold cache (first load per registry lifetime). Qualified.
- C3: "~2.6s window" was an incorrect derivation from mean data (actual: 2,323ms). Corrected to show arithmetic.

**Important findings (all resolved):**
- I1: Steps 7–8 are in the same function, not separate call sites. Clarified location column.
- I2: `inject_paragraph_attributes` has early return when `paragraph_map` is empty — double parse is conditional. Added qualification throughout.
- I3: "~15-20 NiceGUI elements" was an estimate, not measured. Changed to "multiple NiceGUI elements (exact count not yet measured)".
- I4: Growth rate derivation assumed min/max correspond to iteration order (not verified against raw data). Added qualification.

**Minor findings (all resolved):**
- M1: Step 1 DB call count is conditional on `workspace` parameter. Noted.
- M2: `highlights.py:288` (`await ui.run_javascript(removeAllRanges, timeout=1.0s)`) was missing from JS timeout analysis — added as most likely candidate.

### External Review (proleptic-challenger)

**2 Critical, 2 Important, 1 Open Question** — all resolved.

**Critical findings:**
- The "0 DOM highlights" probe was wrong: `[data-highlight-id]` is on annotation cards, not document highlights (which use CSS Custom Highlight API with no DOM mutation). Open Question 5 rewritten as withdrawn/bad-probe. Need `CSS.highlights.size` or card count instead.
- `tagApplyMs` measures up to `cards_epoch` advance (step 4), not the full post-click pipeline. The 4.3s figure reflects card rebuild cost; it cannot implicate the `removeAllRanges` timeout at step 6. Measurement description corrected throughout.

**Important findings:**
- FCP=LCP proves no progressive rendering but does not prove single-chunk delivery without a network waterfall trace. Downgraded to inference.
- H4 (originally promoted to H1) claimed a design/implementation mismatch. The architecture doc does specify diff-based cards, but the implementation (`49860bab`) was never merged — it lives only on `multi-doc-tabs-186`. **The "accidental revert" claim was retracted in session 377-sysdbg (2026-03-24).** See revised H1 in Hypotheses section.

**Open Question:**
- Degradation narrative lacks a clean control — server process stays alive across iterations, so CRDT registry warmth and server-side state accumulation are confounded with CRDT growth. Caveat added to observation 2.

## Phase 4: H2a Fix and Browser-Side Instrumentation

### Session: 377-hypo-test (2026-03-24)

### H1 revised (unnecessary `await`) — Fixed

**Changes (branch `debug/377-workspace-performance`):**

1. **`highlights.py:288`** — `_add_highlight`: removed `await` from `ui.run_javascript("removeAllRanges")`. Moved selection cleanup (lines 290-294) into `finally` block for unconditional execution. Fixes ghost highlight menu on timeout.
2. **`cards.py:563`** — `toggle_detail`: removed `await` from `ui.run_javascript("rAF(_positionCards)")`. Changed `async def` → `def`.
3. **`cards.py:391`** — `goto_highlight`: removed `await` from `ui.run_javascript(scrollTo + throb)`. Changed `async def` → `def`.

**Tests:** `tests/unit/test_add_highlight_timeout.py` — 4 tests:
- `test_timeout_does_not_propagate` — TimeoutError must not escape
- `test_selection_cleared_on_timeout` — selection_start/end reset to None
- `test_highlight_menu_hidden_on_timeout` — menu hidden
- `test_processing_highlight_released_on_timeout` — lock released (safety net, passes on current main)

3 RED tests fail on main (1 safety net passes on both), all 4 GREEN after fix. No regressions (3,566 unit tests pass).

### Browser-Side Instrumentation (H2b/H2c) — FALSIFIED

**Method:** Added `console.time`/`console.timeEnd` guards (gated behind `window.__perfInstrumented`) to `applyHighlights` (annotation-highlight.js) and `positionCards` (annotation-card-sync.js). E2E test (`tests/e2e/test_browser_perf_377.py`) enables the flag via `page.add_init_script()`, captures console output, loads the Pabai workspace (190 highlights, 5,020 text nodes).

**Results (Pabai workspace, local Chromium):**

| Timer | Page load (ms) | Tag apply (ms) |
|-------|---------------|----------------|
| applyHighlights (total) | 10.7 | 9.9 |
| applyHighlights:walkTextNodes | 6.8 | 8.7 |
| applyHighlights:rangeCreation | 3.3 | 0.9 |
| positionCards | 2.8 | 2.2 |

**Conclusion:** Both `applyHighlights` (~10ms) and `positionCards` (~3ms) are trivially fast on the Pabai workspace (single E2E run, N=1 — treat as indicative, not statistically robust). Browser-side JS execution is **not** the performance bottleneck. Binary search in `charOffsetToRange` and incremental highlight updates are **not needed**.

**H2b (positionCards linear scan):** Falsified — 2.8ms with 190 cards × 5,020 text nodes.
**H2c (applyHighlights full re-registration):** Falsified — 10.7ms with 190 highlights × 5,020 text nodes.

The 1.0s JS timeouts were not caused by expensive JS execution (~10ms). The most likely mechanism is the `await` queueing behind NiceGUI's batched WebSocket element updates, but this specific queue delay was not directly measured.

### Remaining Performance Bottleneck (updated 2026-03-25)

The entire server-side page load time is dominated by a single operation:

- **`refresh_annotation_cards`** — 431–632ms (76–97% of server time)
- ~~CRDT persistence~~ — 17ms (negligible locally)
- ~~NiceGUI element serialisation of 426K HTML~~ — 0.2–0.4ms (falsified)
- ~~Double selectolax parse~~ — moot (single parse, 26ms)
- DB + CRDT load — ~90ms (secondary)

**Primary fix path:** Diff-based cards (O(1) tag apply instead of O(n) full rebuild).

### Phase 4 Peer Review

Reviewed by clean Opus 4.6 subagent (critical-peer-review protocol). **3 High, 4 Medium, 4 Low** findings.

**High findings (all resolved):**
- H1: Unit tests verify `finally`-block cleanup, not the fire-and-forget timeout avoidance mechanism directly. Clarified in test description and evidence grade.
- H2: RED/GREEN count inconsistent (claimed "4 RED" but 4th test passes on main). Fixed to "3 RED, 1 safety net."
- H3: Evidence grade overclaimed as "Demonstrated" — synthetic path only, negative border (production deployment) untested. Downgraded to "Plausible (positive border on synthetic path)."

**Medium findings (all resolved):**
- M1: "caused entirely by await queueing" stated as fact, is inference. Softened to "most likely mechanism... not directly measured."
- M2: `toggle_detail` async→sync change has unexamined NiceGUI batching interaction. Noted as untested but low risk (NiceGUI handles both).
- M3: Browser timing results are N=1 from single E2E run. Noted as "indicative, not statistically robust."
- M4: `document.py:251 handle_tag_click` (2,987 raw timeouts) not addressed by fix — needs clarification of call-site aggregation. Deferred: the raw counts are from epoch-split analysis before aggregation by function; `handle_tag_click` calls `_add_highlight` which contained the timeout at :288.

**Low findings (all resolved):**
- L1: 6,258 vs 5,947 vs 12,205 count discrepancy between handoff and postmortem — different aggregation methods (direct vs Task exception variants). Pre-existing from Phase 3.
- L2: Code comments cite "browser busy with applyHighlights" — updated to "queued behind NiceGUI element batch."
- L3: Phase 3 finding #1 text not updated for Phase 4 falsification — added inline update note.
- L4: `window.__perfInstrumented` flag persists across SPA navigations — harmless in E2E (fresh context), documented.

## Phase 5: Server-Side Instrumentation and Measurement

### Session: 377-server-timing (2026-03-25)

### Infrastructure Changes

1. **`e2e perf` CLI command** — Moved `grimoire test perf` to `grimoire e2e perf`. The perf tests are E2E tests that need a managed NiceGUI server subprocess (with `test-e2e-server.log` lifecycle and `E2E_BASE_URL`). The old `test perf` ran via bare pytest, bypassing the server management and producing no structlog JSONL output.

2. **`ServerLogReader` path fix** — The reader was globbing `Path("logs")` for JSONL files, but the actual log directory is `logs/sessions/` (configured via `APP__LOG_DIR` in `.env`). Fixed to parse the absolute path from `test-e2e-server.log` line 2 (which prints `"Log file: <path>"`), falling back to recursive glob.

3. **`setLevel(INFO)` bug discovered** — The structlog migration (commit `e056c3b5`) added `logging.getLogger(__name__).setLevel(logging.INFO)` to ~40 modules. This suppresses `logger.debug()` calls because `structlog.stdlib.LoggerFactory()` creates stdlib loggers named after each module. The per-module stdlib logger inherits level INFO from the hierarchy, and DEBUG events (level 10) are filtered before reaching the file handler (which is set to DEBUG). Removed from 4 instrumented files: `annotation/__init__.py`, `workspace.py`, `cards.py`, `highlights.py`.

### Measurement Results

**Page load (Pabai workspace, 190 highlights, 425K HTML, local dev, N=2):**

| Phase | Run 1 | Run 2 | % of total |
|-------|-------|-------|-----------|
| `resolve_context` | 33ms | 29ms | 5% |
| `list_documents` | 16ms | 12ms | 2% |
| `render_header` | 23ms | 23ms | 4% |
| `load_crdt_and_tags` | 30ms | 25ms | 5% |
| `extract_text_from_html` | 25.9ms | 27.3ms | 5% |
| `inject_paragraph_attributes` | 0.0ms | 0.0ms | 0% |
| `ui_html` | 0.4ms | 0.2ms | 0% |
| **`refresh_annotation_cards`** | **453.3ms** | **431.2ms** | **76%** |
| `render_document_container` | 481ms | 465ms | 82% |
| `build_tab_panels` | 522ms | 503ms | 89% |
| **`page_load_total`** | **594ms** | **566ms** | **100%** |

**Tag apply (single highlight addition, 190→191 highlights):**

| Phase | Elapsed | % of total |
|-------|---------|-----------|
| `force_persist_workspace` | 17.4ms | 2.7% |
| `refresh_annotation_cards` | 631.9ms | 97.0% |
| `broadcast_update` | 0.0ms | 0.0% |
| **`total_pipeline`** | **651.2ms** | **100%** |

**Browser-side (captured in same run):**

| Timer | Page load | Tag apply |
|-------|-----------|-----------|
| `applyHighlights` | 13.0ms | 47.8ms |
| `positionCards` | 4.0ms | 12.2ms |

### Hypothesis Verdicts

| Hypothesis | Verdict | Evidence grade |
|---|---|---|
| H1 revised (unnecessary await) | Fixed (Phase 4) | Plausible |
| H2 (ui.html serialization) | **Falsified** — 0.2–0.4ms | Demonstrated |
| H2b/H2c (browser JS cost) | Falsified (Phase 4) — ~10ms | Plausible (N=1, local Chromium) |
| H3 (double selectolax parse) | **Moot** — para_map empty, single parse 26ms | Demonstrated |
| H4 (sequential DB calls) | **Secondary locally, potentially dominant under load** — 22+ calls, 90ms local | Plausible |
| H5 (browser payload blocking) | Partially falsified (Phase 4) | Plausible |
| **H6 (card rebuild O(n))** | **Dominant bottleneck locally for O(100+) highlights** — 76–97% of server time | **Demonstrated** |

### Conclusion

**Two bottlenecks identified, dominant under different conditions:**

1. **Card rebuild (H6) — dominant locally for workspaces with O(100+) highlights.** `refresh_annotation_cards` with `container.clear()` + full rebuild consumes 431–632ms for 190 highlights (~2.3–3.3ms per card), 76–97% of server time. This is O(n) in highlights and explains the progressive degradation observed in Phase 1. For workspaces with few highlights, H4 (DB call overhead) may dominate instead. Fix: diff-based cards (O(1) tag apply).

2. **Sequential redundant DB calls (H4) — secondary locally but potentially dominant under production load.** 22+ sequential DB calls per page load, with Workspace fetched 6 times and the Activity→Week→Course hierarchy walked 3+ times. On local PostgreSQL via Unix socket (no contention), this totals ~90ms. Under production load with 1,800 concurrent students and PgBouncer transaction pooling, sequential pool-wait accumulation could contribute 660–1,100ms — explaining a significant portion of the 4s production page load vs 566ms local. Fix: eliminate redundancy (cache Workspace/PlacementContext in PageState), batch hierarchy walks into JOINs, parallelise independent calls with `asyncio.gather()`.

Both bottlenecks require design work before implementation.
