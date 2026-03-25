# Annotation Deferred Load Design

**GitHub Issue:** #377

## Summary

The annotation page blocks the NiceGUI event loop for 3+ seconds during page load, performing 10+ sequential DB round-trips with extensive redundancy (workspace fetched 4×, hierarchy walked 3×, documents listed 2×). With PgBouncer NullPool migration pending, each round-trip becomes a real connection acquire, compounding the problem.

This design eliminates the blocking by (1) returning a skeleton page immediately via `background_tasks.create()`, and (2) batching the redundant DB calls into a unified context resolver with JOINed queries. Experimental measurement shows the skeleton renders in <15ms vs 400ms+ for the current blocking approach.

## Definition of Done

1. **Annotation page handler returns immediately** — renders page skeleton with a loading state (spinner/skeleton), then kicks off DB work as an async background task. Eliminates "Response not ready after 3.0 seconds" warnings.

2. **Unified DB context resolution** — single session, JOINed queries, at most 3 DB sessions total (context resolution, documents, CRDT load). Reduces current 10 DB calls / 4× workspace fetch / 3× hierarchy walk to minimal round-trips.

3. **Progressive hydration** — once DB work completes, populate the UI (header, document, toolbar, cards). Page transitions from loading state to fully rendered.

4. **Remove `setLevel(INFO/WARNING)`** from all 41 remaining modules across the codebase (#391, #359).

5. **Minimal annotation UI module changes** — only `__init__.py` (page handler skeleton) and `workspace.py` (entry point restructure) are modified in `pages/annotation/`. All other annotation UI modules (`cards.py`, `document.py`, `highlights.py`, `organise.py`, `respond.py`) are untouched. DB/auth/crdt layer changes avoid conflicts with #186 (multi-doc tabs).

6. **All existing tests pass + measurable improvement** via `grimoire e2e perf`.

## Architecture

### Current State: 10 Sequential DB Sessions

The annotation page handler (`annotation_page()` → `_render_workspace_view()`) blocks on the following DB calls in order, each opening its own async session:

| # | Function | Tables | Session | Redundancy |
|---|----------|--------|---------|------------|
| 1 | `get_workspace(workspace_id)` | workspace | Own | — |
| 2 | `check_workspace_access()` → `resolve_permission()` | acl_entry, workspace, activity, week, course, course_enrollment, permission | Own | Workspace re-fetched; hierarchy re-walked |
| 3 | `get_placement_context(workspace_id)` | workspace, activity, week, course | Own | Workspace re-fetched (3rd); hierarchy re-walked (2nd) |
| 4 | `get_privileged_user_ids_for_workspace()` | workspace, activity, week, course_enrollment, user | Own | Workspace re-fetched (4th); hierarchy re-walked (3rd) |
| 5 | `list_documents(workspace_id)` | workspace_document | Own | — |
| 6 | `get_or_create_for_workspace()` (CRDT registry) | workspace | Own | Workspace re-fetched (5th — for crdt_state only) |
| 7 | `list_tags_for_workspace()` (CRDT consistency) | tag | Own | — |
| 8 | `list_tag_groups_for_workspace()` (CRDT consistency) | tag_group | Own | — |
| 9 | Conditional: `save_workspace_crdt_state()` | workspace | Own | Write if CRDT reconciliation changed state |
| 10 | `list_documents(workspace_id)` (inside `@ui.refreshable`) | workspace_document | Own | Exact duplicate of #5 |

**Source:** Code audit of main branch, 2026-03-25. Functions in `db/workspaces.py`, `db/acl.py`, `auth/__init__.py`, `db/workspace_documents.py`, `db/tags.py`, `crdt/annotation_doc.py`.

**Redundancy totals:**
- Workspace row: fetched **4–5×** (calls 1, 2, 3, 4; call 6 only on cold CRDT registry — returning visitors hit the in-memory cache)
- Activity → Week → Course hierarchy: walked **3×** (calls 2, 3, 4)
- `list_documents`: called **2×** (calls 5, 10)

Each session is `async with get_session()` — independent connection acquire + release. Under NullPool (pending), each is a real PgBouncer connection.

### Proposed State: Skeleton + 3 DB Sessions

#### Phase 1: Immediate Skeleton (< 15ms)

The page handler renders a skeleton and returns:

```
annotation_page()
├── _setup_page_styles()          # CSS, no DB
├── page_layout(heading, ...)     # Shell with drawer, footer
├── render loading spinner        # Visible immediately
└── background_tasks.create(_load_workspace_content(workspace_id, client))
    # Returns immediately — handler done
```

Uses NiceGUI's `background_tasks.create()` (not raw `asyncio.create_task`) — this is the official API for background work. It handles GC prevention and graceful shutdown cancellation. See #314 for the broader migration; this design uses the correct API from the start.

The browser receives the skeleton in <15ms (measured). The spinner animates via CSS — no event loop involvement.

#### Phase 2: Background Task — Unified Context Resolution (1 session)

A single async function runs in a background task with `with client:` context:

```
_load_workspace_content(workspace_id, client)
├── Session 1: _resolve_full_context(workspace_id, user_id)
│   ├── SELECT workspace with crdt_state         # 1 query (was 5)
│   ├── SELECT acl_entry for (workspace, user)    # 1 query
│   ├── SELECT activity JOIN week JOIN course     # 1 JOIN query (was 3× sequential)
│   │   WHERE activity.id = workspace.activity_id
│   ├── SELECT course_enrollment for (course, user) # 1 query (permission)
│   ├── SELECT privileged user IDs                # 1 query (staff + admins)
│   ├── SELECT tag, tag_group for workspace       # 1 query (was 2)
│   └── Returns: FullContext(workspace, permission, placement, priv_ids, tags, crdt_state)
│
├── Session 2: list_documents(workspace_id)       # 1 query (was 2)
│   └── Result cached on PageState for refreshable reuse
│
├── CRDT hydration (in-memory, no DB — uses pre-fetched data)
│   └── _ensure_crdt_tag_consistency(doc, workspace_id, tags=tags, tag_groups=groups)
│   │   Current signature: (doc, workspace_id) — fetches tags internally
│   │   New signature adds optional tags/tag_groups kwargs — when provided,
│   │   skips the internal fetch. Callers without pre-fetched data are unaffected.
│   └── Conditional Session 3: save_workspace_crdt_state() if changed
│
└── Populate UI (with client: context)
    ├── render_workspace_header(...)
    ├── build_tabs(...)
    ├── _build_tab_panels(...)
    └── Hide spinner, show content
```

**Query reduction:** 10 sessions → 2–3 sessions. 14+ round-trips → ~7 queries in 2 sessions.

#### The Unified Context Resolver

New function in `db/workspaces.py`:

```python
async def resolve_annotation_context(
    workspace_id: UUID,
    user_id: UUID,
) -> AnnotationContext:
    """Resolve all data needed for annotation page load in a single session.

    Replaces 5 separate functions that each opened their own session:
    - get_workspace()
    - check_workspace_access() → resolve_permission()
    - get_placement_context()
    - get_privileged_user_ids_for_workspace()
    - list_tags_for_workspace() + list_tag_groups_for_workspace()
    """
```

Returns a dataclass/NamedTuple with all resolved data. The hierarchy walk uses a JOIN that handles both placement paths:

```sql
-- Activity-placed: workspace.activity_id → activity → week → course
-- Course-placed:   workspace.course_id → course (no activity/week)
-- Standalone:      both NULL
SELECT w.*,
       a.id AS activity_id_resolved, a.title AS activity_title,
       a.template_workspace_id,
       wk.id AS week_id, wk.number AS week_number,
       COALESCE(c_via_week.id, c_direct.id) AS course_id,
       COALESCE(c_via_week.code, c_direct.code) AS course_code,
       COALESCE(c_via_week.name, c_direct.name) AS course_name,
       COALESCE(c_via_week.copy_protection, c_direct.copy_protection) AS copy_protection,
       COALESCE(c_via_week.allow_sharing, c_direct.allow_sharing) AS allow_sharing,
       COALESCE(c_via_week.allow_tag_creation, c_direct.allow_tag_creation) AS allow_tag_creation,
       COALESCE(c_via_week.anonymous_sharing, c_direct.anonymous_sharing) AS anonymous_sharing
FROM workspace w
LEFT JOIN activity a ON a.id = w.activity_id
LEFT JOIN week wk ON wk.id = a.week_id
LEFT JOIN course c_via_week ON c_via_week.id = wk.course_id
LEFT JOIN course c_direct ON c_direct.id = w.course_id AND w.activity_id IS NULL
WHERE w.id = :workspace_id
```

Two JOIN paths cover all three workspace states:
- **Activity-placed:** `w.activity_id` → `a` → `wk` → `c_via_week` (c_direct is NULL because activity_id IS NOT NULL)
- **Course-placed:** `w.course_id` → `c_direct` (a/wk/c_via_week are NULL)
- **Standalone:** all JOINs return NULL

Template detection is included: `a.template_workspace_id` in the result set. The resolver checks `template_workspace_id == workspace_id` to set `is_template`. Additionally, standalone workspaces need a reverse lookup (`SELECT activity WHERE template_workspace_id = :workspace_id`) to detect whether they *are* a template — this is a second query in the same session.

### Deferred Loading: Experimental Results

Three approaches were tested with a NiceGUI experiment simulating 400ms of async DB work:

| Metric | create_task (A) | timer(0) (B) | blocking (C) |
|---|---:|---:|---:|
| **Response to browser** | 12ms | 4ms | 403ms |
| **DOM Interactive** | 75ms | 25ms | 432ms |
| **Spinner visible during load** | Yes | Yes | N/A |
| **Spinner hidden after** | Yes | Yes | N/A |
| **Total time to content** | 402ms | 481ms | 400ms |
| **Needs `with client:` context** | Yes | No | N/A |

**Methodology:** NiceGUI 3.9.0 running locally on port 8091. Each approach renders a skeleton page, then runs `asyncio.sleep()` to simulate DB round-trips. Playwright measures `Performance.getEntriesByType('navigation')` timing and `window.__loadComplete` signal. Single run per approach — these are order-of-magnitude comparisons, not statistical benchmarks.

**Selected: Approach A (`background_tasks.create`).**

Uses NiceGUI's official `background_tasks.create()` API ([NiceGUI docs: Background Tasks](https://nicegui.io/documentation/section_configuration_deployment)) rather than raw `asyncio.create_task`. This handles GC prevention and graceful shutdown automatically — aligns with #314 migration target.

Rationale:
- `background_tasks.create()` returns a task handle for cancellation on client disconnect
- `with client:` pattern established in codebase (`annotation/__init__.py:127-129` via `_RemotePresence.invoke_callback`)
- Aligns with #314 (migrate to official `background_tasks` API)
- The `with client:` requirement is additional complexity but it's a one-line wrapper

**Unverified assumption:** `background_tasks.create()` wrapping an async function that uses `with client:` for UI updates has not been tested in this codebase. The combination works in theory (both are documented NiceGUI patterns) but needs a spike in Phase 2 before committing to the architecture. If it fails, fall back to `ui.timer(0, once=True)` which runs in the client context automatically.

Rejected alternatives:
- **timer(0):** Simpler (no manual client context). Single-run measurements showed similar total-time performance — the apparent 80ms gap is within noise for a single measurement. However, timer(0) provides no cancellation handle for client disconnect, which is the primary reason for preferring `background_tasks.create()`.
- **Blocking (current):** No change to event loop architecture. Only the query batching would help, but the page handler still blocks for the full DB duration.
- **Raw `asyncio.create_task`:** Works but requires manual `_background_tasks` set for GC prevention — `background_tasks.create()` is the NiceGUI-blessed wrapper.

### Interaction with #186 (Multi-Doc Tabs)

This design deliberately avoids annotation UI modules that #186 rewrites:
- `workspace.py` — both designs touch this, but this design only modifies the entry point (`_render_workspace_view`) to render skeleton + schedule task. The tab building, document rendering, and card management remain in #186's domain.
- `cards.py`, `document.py`, `highlights.py`, `tab_bar.py` — not touched.
- `db/workspaces.py`, `db/acl.py`, `auth/__init__.py`, `crdt/annotation_doc.py` — these are the target files. #186 does not modify them.

After #186 merges, the deferred loading pattern (`create_task` → `_load_workspace_content`) wraps whatever tab/document structure #186 introduces. The interface is: "here's all the resolved context, render the workspace."

### setLevel Cleanup

The structlog migration added `logging.getLogger(__name__).setLevel(logging.INFO)` (or `WARNING`) across the codebase. Current count on this branch: **41 files** (verified via `grep -r 'logging.getLogger(__name__).setLevel' src/ --count`).

Breakdown:
- 36 modules with `setLevel(logging.INFO)` — suppresses `logger.debug()` calls
- 5 modules with `setLevel(logging.WARNING)` (`db/engine.py`, `crdt/annotation_doc.py`, `crdt/persistence.py`, `db/tags.py`, `db/wargames.py`) — suppresses `logger.debug()` AND `logger.info()` calls

This is a mechanical one-line removal per file. No behavioural change — structlog's level filtering is configured globally via `structlog.configure()`, making per-module stdlib level overrides both redundant and harmful.

Addresses #391 (structlog context missing from logs) and #359 (Discord alerting misses stdlib errors).

## Existing Patterns Followed

- **Background tasks:** NiceGUI provides `background_tasks.create()` ([docs](https://nicegui.io/documentation/section_configuration_deployment)) for GC-safe fire-and-forget tasks. Codebase currently uses manual `_background_tasks` set (`annotation/__init__.py:198`) — #314 tracks migration to the official API
- **`with client:` for deferred UI updates:** `annotation/__init__.py:127-129` via `_RemotePresence.invoke_callback()` — enters client context manager so `ui.run_javascript()` and element updates route to the correct browser tab
- **Deferred tab rendering:** `workspace.py:891` — `state.initialised_tabs` tracks which tabs have rendered; content built on first visit via `_make_tab_change_handler()`
- **`@ui.refreshable` for document container:** `workspace.py:730` — refreshes when documents added; result cache avoids re-query
- **Single-session pattern in db/ layer:** All DB functions use `async with get_session() as session:` — the unified resolver follows the same pattern but does more work per session

## Implementation Phases

### Phase 1: Unified Context Resolver

Create `resolve_annotation_context()` in `db/workspaces.py`. Single session, JOINed hierarchy query, returns `AnnotationContext` dataclass with workspace, permission, placement context, privileged IDs, tags, and tag groups. Add `accept_workspace` parameter to CRDT registry's `get_or_create_for_workspace()` to accept pre-fetched workspace. Add optional `tags`/`tag_groups` kwargs to `_ensure_crdt_tag_consistency()` so callers with pre-fetched data skip the internal fetch (existing callers without these kwargs are unaffected). Write unit tests against the new function. Does not change page behavior yet — existing callers continue to work.

**Files:** `db/workspaces.py`, `db/acl.py`, `crdt/annotation_doc.py`, `db/tags.py`, `tests/unit/`

### Phase 2: Deferred Page Load

Modify `annotation_page()` to render skeleton and schedule background task. `_render_workspace_view()` becomes `_load_workspace_content()` using the unified resolver. The background task populates UI via `with client:`. Wire `client.on_disconnect` handler to cancel the background task if the client navigates away during loading. Spike: verify `background_tasks.create()` + `with client:` combination works before committing to the architecture (fallback: `ui.timer(0, once=True)`). Write E2E test verifying skeleton appears before content.

**Files:** `pages/annotation/__init__.py`, `pages/annotation/workspace.py`, `tests/e2e/`

### Phase 3: setLevel Cleanup + Documents Cache

Remove `setLevel()` from all 41 remaining modules. Cache `list_documents()` result on PageState to eliminate the duplicate call in `@ui.refreshable`. Add guard test enforcing no `setLevel()` calls in `src/promptgrimoire/`. Run full test suite.

**Files:** 41 modules across `src/promptgrimoire/`, `pages/annotation/workspace.py`, `tests/unit/`

### Phase 4: Measurement and Verification

Run `grimoire e2e perf` before/after. Compare responseEnd timing. Verify no "Response not ready" warnings in local test. Update #377 issue with results.

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Background task fails after skeleton renders — user sees spinner forever | User stuck on loading screen | Wrap task in try/except, show error notification on failure, hide spinner |
| User interacts with skeleton before content loads (e.g., clicks non-existent buttons) | Confusing UX | Skeleton has no interactive elements — just spinner and grey header text |
| `with client:` fails if client disconnects during DB work | Orphaned task, potential errors | `background_tasks.create()` handles shutdown cancellation; `client._deleted` guard in `with` block |
| JOIN query returns different results than sequential queries (e.g., LEFT JOIN nulls) | Incorrect permission/placement resolution | Test with workspaces in all states: activity-placed, course-placed, standalone, template |
| #186 merge creates conflicts in workspace.py entry point | Merge pain | Phase 2 changes are localised to `_render_workspace_view` → `_load_workspace_content` rename. #186's tab building is called from within the task, not restructured. |

## Acceptance Criteria

### DoD 1: Page handler returns immediately

- **annotation-deferred-load-377.AC1.1:** `annotation_page()` handler completes in <50ms (measured via responseEnd in Performance API)
- **annotation-deferred-load-377.AC1.2:** Loading spinner is visible to the user before DB work begins (Playwright: spinner element visible before `__loadComplete`)
- **annotation-deferred-load-377.AC1.3:** NiceGUI "Response not ready after 3.0 seconds" warning does not appear for annotation page loads under normal conditions

### DoD 2: Unified DB context resolution

- **annotation-deferred-load-377.AC2.1:** `resolve_annotation_context()` executes in a single DB session
- **annotation-deferred-load-377.AC2.2:** Workspace row is fetched exactly once per page load (verified by query count instrumentation or mock)
- **annotation-deferred-load-377.AC2.3:** Activity → Week → Course hierarchy is resolved via JOIN, not sequential selects
- **annotation-deferred-load-377.AC2.4:** Function returns correct results for all workspace states: activity-placed, course-placed, standalone (no parent), template
- **annotation-deferred-load-377.AC2.5:** CRDT registry accepts pre-fetched workspace on cold-cache path (no redundant fetch for crdt_state on first load; warm-cache path already skips the fetch)

### DoD 3: Progressive hydration

- **annotation-deferred-load-377.AC3.1:** After background task completes, spinner is hidden and workspace content is visible
- **annotation-deferred-load-377.AC3.2:** If background task fails (DB error, timeout), user sees error notification — not infinite spinner
- **annotation-deferred-load-377.AC3.3:** If client disconnects during DB work, background task is cancelled via `client.on_disconnect` handler (no orphaned queries). Note: `background_tasks.create()` handles server shutdown cancellation, but client disconnect requires an explicit handler that cancels the task — this must be wired in Phase 2

### DoD 4: setLevel cleanup

- **annotation-deferred-load-377.AC4.1:** No `logging.getLogger(__name__).setLevel()` calls remain in `src/promptgrimoire/` (guard test)
- **annotation-deferred-load-377.AC4.2:** `logger.debug()` calls in annotation modules produce output when structlog is configured at DEBUG level

### DoD 5: Minimal UI module changes

- **annotation-deferred-load-377.AC5.1:** Only `__init__.py` and `workspace.py` are modified in `pages/annotation/`
- **annotation-deferred-load-377.AC5.2:** `cards.py`, `document.py`, `highlights.py`, `organise.py`, `respond.py`, `tab_bar.py` (if present from #186) are unchanged

### DoD 6: Tests pass + measurable improvement

- **annotation-deferred-load-377.AC6.1:** `uv run grimoire test all` passes (3,573+ tests)
- **annotation-deferred-load-377.AC6.2:** `grimoire e2e perf` shows responseEnd improvement (before/after comparison documented)

## Glossary

| Term | Definition |
|------|-----------|
| **Skeleton** | Minimal page structure (header placeholder, spinner, empty tab panels) rendered by the page handler before DB work begins |
| **Progressive hydration** | Pattern where the skeleton is populated incrementally as data becomes available from background tasks |
| **Unified context resolver** | Single function (`resolve_annotation_context`) that replaces 5+ separate DB functions, each of which opened their own session |
| **Hierarchy walk** | The chain of sequential single-row SELECTs: Workspace → Activity → Week → Course. Currently performed 3× per page load. |
| **NullPool** | SQLAlchemy pool strategy where no connections are held — each operation acquires and releases a real connection. Required for PgBouncer transaction mode. |
| **`with client:`** | NiceGUI context manager that routes server-side UI updates to the correct browser tab. Required when updating UI elements from background tasks. |
| **Fire-and-forget** | Async task created without awaiting its result. Must be stored in `_background_tasks` set to prevent garbage collection. |
