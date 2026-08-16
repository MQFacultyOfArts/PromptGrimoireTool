# Dead End: Moving First `get_document(...)` Outside `with client:`

**Date:** 2026-04-23
**Investigation:** `docs/investigations/2026-04-19-independent-workspace-load.md`
**Branch:** `investigate/nicegui-perf`
**Status:** Abandoned

## Problem

After the privilege-read collapse in Phase 21, the clean `50`-way
`QueuePool(20+10)` path was still around `11.4 s` browser-observed. The named
document-path hot read was still `get_document(...)`, and the server logs showed
an awkward split:

- `session_connection_profile(get_document).total_ms avg = 594.6`
- `tab_panels_profile.doc_fetch_ms avg = 998.4`

That suggested the first source-document fetch might be happening in a bad page
phase rather than being intrinsically slow in isolation.

## Hypothesis

If the initial `get_document(...)` read was moved out of the `with client:`
section and prefetched during DB resolve, the page should spend less time in
the UI/tab-panels phase and the browser-observed load should improve.

## Approach Tried

The experiment changed the first-load path only:

1. `_resolve_db_context(...)` fetched the first full document outside
   `with client:`
2. `_load_workspace_content(...)` threaded that prefetched document into
   `_build_tab_panels(...)`
3. `_build_tab_panels(...)` stopped doing the initial `get_document(...)`
   itself
4. the temporary instrumentation split `annotation_db_resolve_profile` into
   `first_document_ms` and `crdt_registry_ms` so the moved fetch did not get
   hidden inside the wrong bucket

The change was then measured and fully reverted.

## Evidence

- baseline `/tmp/iw-50-db-profile-6-privileged-union.json`
- experiment `/tmp/iw-50-db-profile-7-prefetch-outside-client.json`
- browser results from the E2E perf harness
- event-level server timings from
  `logs/sessions/promptgrimoire-investigate_nicegui_perf.jsonl`

Command run:

- `PROMPTGRIMOIRE_PROFILE_DB_CONNECTIONS=1 DEV__TEST_DATABASE_URL='postgresql+asyncpg://brian@/promptgrimoire_test_investigate_nicegui_perf?host=/var/run/postgresql' DATABASE__URL='postgresql+asyncpg://brian@/promptgrimoire_investigate_nicegui_perf?host=/var/run/postgresql' E2E_FORCE_QUEUEPOOL=1 DATABASE__POOL_SIZE=20 DATABASE__MAX_OVERFLOW=10 DATABASE__POOL_PRE_PING=false E2E_INDEPENDENT_WORKSPACES_DIAG_PATH=/tmp/iw-50-db-profile-7-prefetch-outside-client.json E2E_INDEPENDENT_WORKSPACES_SESSIONS=50 uv run grimoire e2e perf -k "test_concurrent_independent_pabai_loads"`

## What Improved

The experiment hit the seam it targeted:

- `session_connection_profile(get_document).hold_ms avg`:
  `523.9 -> 251.0`
- `session_connection_profile(get_document).total_ms avg`:
  `594.6 -> 299.3`
- `tab_panels_profile.doc_fetch_ms avg`:
  `998.4 -> 0.0`
- `page_load_profile.tab_panels_ms avg`:
  `1032.6 -> 33.2`

So the page really was doing a large first-document read inside the tab-panels
phase, and moving it earlier removed that specific server-side cost.

## Why It Still Failed

The improvement did **not** translate into a browser win:

- browser average:
  `11409.8 -> 11493.5`
- `page_load_profile.total_ms avg`:
  `2067.6 -> 2002.7`

At the same time, the cost simply reappeared elsewhere:

- `annotation_db_resolve_profile.total_ms avg`:
  `543.8 -> 1109.3`
- temporary `annotation_db_resolve_profile.first_document_ms avg`:
  `538.5`
- `page_load_profile.header_ms avg`:
  `490.0 -> 858.8`
- `session_connection_profile(get_active_job_for_user).total_ms avg`:
  `275.8 -> 497.8`

The most plausible mechanism is that moving the first document read earlier did
not remove mixed-workload contention. It shortened `get_document(...)` and
collapsed `tab_panels_ms`, but it pushed more concurrent DB pressure into the
header/export-recovery phase, especially `get_active_job_for_user(...)`. The
user-visible path therefore stayed effectively flat.

## Caveats

- This was `n=1` per condition.
- The baseline and experiment were separate runs, so normal machine-state or
  cache drift can affect the exact magnitudes.
- Those caveats do not rescue the idea: the targeted seam improved strongly,
  but the browser-observed outcome did not.

## What Not To Try Again

1. A standalone “move the first document fetch earlier” patch that only changes
   page-phase ordering.
2. Treating `tab_panels_profile.doc_fetch_ms` as if collapsing it is enough on
   its own to improve browser readiness.

## What This Ruled In Instead

This falsifier clarified the live thread:

- `get_document(...)` is still a real hot read, but phase reordering alone is
  not enough
- the remaining user-visible delay is still a mixed-path contention problem,
  not just a badly placed first fetch
- the better next targets remain the named hot reads themselves, especially
  `get_document(...)` and `list_document_headers(...)`, rather than more UI
  phase reshuffling
