# Dead End: Export-Recovery Timer Deferral

**Date:** 2026-04-24
**Investigation:** `docs/investigations/2026-04-19-independent-workspace-load.md`
**Branch:** `investigate/nicegui-perf`
**Status:** Abandoned

## Problem

After the privilege-read collapse in Phase 21, clean `50`-way
`QueuePool(20+10)` loads were still around `11.4 s` browser-observed. One
remaining page-load cost was export-state recovery in the header:

- baseline `page_load_profile.header_ms avg = 490.0`
- baseline `session_connection_profile(get_active_job_for_user).total_ms avg = 275.8`

The export-job query itself looked cheap under `EXPLAIN (ANALYZE, BUFFERS)`, so
the working hypothesis was that removing it from the synchronous header path
might improve annotation readiness.

## Hypothesis

If `check_existing_export()` was deferred off the inline header render path,
annotation readiness would improve because the page would stop waiting on export
recovery before showing itself as ready.

## Approach Tried

The experiment changed only the timing of export recovery:

1. `render_workspace_header(...)` stopped awaiting `check_existing_export(state)`
   inline
2. it instead scheduled recovery via `ui.timer(0.01, _recover, once=True)`
3. the export button still rendered immediately
4. export recovery still ran on page load, just after the initial header build

The change was measured twice, then fully reverted.

## Evidence

- baseline `/tmp/iw-50-db-profile-6-privileged-union.json`
- deferred run 1 `/tmp/iw-50-db-profile-8-export-recovery-deferred.json`
- deferred run 2 `/tmp/iw-50-db-profile-9-export-recovery-deferred-rerun.json`
- browser readiness predicate in
  `tests/e2e/test_independent_workspace_load.py`
- page load signalling in
  `src/promptgrimoire/pages/annotation/workspace.py`

Commands run:

- `PROMPTGRIMOIRE_PROFILE_DB_CONNECTIONS=1 DEV__TEST_DATABASE_URL='postgresql+asyncpg://brian@/promptgrimoire_test_investigate_nicegui_perf?host=/var/run/postgresql' DATABASE__URL='postgresql+asyncpg://brian@/promptgrimoire_investigate_nicegui_perf?host=/var/run/postgresql' E2E_FORCE_QUEUEPOOL=1 DATABASE__POOL_SIZE=20 DATABASE__MAX_OVERFLOW=10 DATABASE__POOL_PRE_PING=false E2E_INDEPENDENT_WORKSPACES_DIAG_PATH=/tmp/iw-50-db-profile-8-export-recovery-deferred.json E2E_INDEPENDENT_WORKSPACES_SESSIONS=50 uv run grimoire e2e perf -k "test_concurrent_independent_pabai_loads"`
- `PROMPTGRIMOIRE_PROFILE_DB_CONNECTIONS=1 DEV__TEST_DATABASE_URL='postgresql+asyncpg://brian@/promptgrimoire_test_investigate_nicegui_perf?host=/var/run/postgresql' DATABASE__URL='postgresql+asyncpg://brian@/promptgrimoire_investigate_nicegui_perf?host=/var/run/postgresql' E2E_FORCE_QUEUEPOOL=1 DATABASE__POOL_SIZE=20 DATABASE__MAX_OVERFLOW=10 DATABASE__POOL_PRE_PING=false E2E_INDEPENDENT_WORKSPACES_DIAG_PATH=/tmp/iw-50-db-profile-9-export-recovery-deferred-rerun.json E2E_INDEPENDENT_WORKSPACES_SESSIONS=50 uv run grimoire e2e perf -k "test_concurrent_independent_pabai_loads"`

## What Improved

The server-side page-load buckets improved sharply:

- run 1 `page_load_profile.total_ms avg`: `2067.6 -> 1672.0`
- run 2 `page_load_profile.total_ms avg`: `2067.6 -> 1639.4`
- run 1 `header_ms avg`: `490.0 -> 1.3`
- run 2 `header_ms avg`: `490.0 -> 1.2`
- run 2 `session_connection_profile(get_active_job_for_user).total_ms avg`:
  `275.8 -> 110.3`

So the deferral did remove export recovery from the synchronous `header_ms`
bucket.

## Why It Failed

The browser-observed result did not improve:

- baseline browser avg: `11409.8 ms`
- deferred run 1 browser avg: `11864.0 ms`
- deferred run 2 browser avg: `11744.9 ms`

This was not just noise in the measurement framing. The harness waits for
`window.__loadComplete === true`, only falling back to the hidden
`annotation-ready` marker when that JS flag is still undefined. The page raises
both signals at the end of `_load_workspace_content(...)`, after the
synchronous `with client:` build has finished.

That means the timer deferral did **not** move export recovery past the real
browser readiness boundary in a reliable way. Instead, it moved the work into a
post-yield async queue at the worst possible moment:

1. the synchronous `with client:` block stages a large backlog of UI updates
2. then it yields back to the event loop
3. at that boundary, the outbox flush tasks and the `ui.timer(...)` recovery
   callbacks become runnable together
4. the `check_existing_export()` callbacks issue `get_active_job_for_user()`
   DB round-trips into the same pool while the outbox still needs CPU time to
   serialise and deliver the staged updates and `__loadComplete`

So the patch improved a server metric by reclassifying work out of the
synchronous header window, but it did not remove work from browser readiness.
It simply relocated it into a post-yield event-loop / websocket-outbox / DB
stampede.

## Pattern Match

This dead end matches an earlier repeated failure shape in this investigation:

- prewarmed first-document fetch reduced a named server slice without improving
  browser time
- first-document phase reordering reduced `tab_panels_ms` without improving
  browser time
- this export-recovery deferral reduced `header_ms` without improving browser
  time

The shared lesson is: moving work between server buckets is not the same as
removing it from browser readiness.

## Caveats

- This experiment was `n=2` deferred runs against one earlier clean baseline,
  not a full matched `3x/3x` matrix.
- The direction was still clear enough to reject the patch:
  browser time failed to improve in both deferred runs while the server-side
  gain was entirely explained by shifted attribution.

## What Not To Try Again

1. A `ui.timer(...)` deferral whose only win is removing work from
   `page_load_profile` while leaving the browser readiness predicate unchanged.
2. Treating `header_ms` reductions as meaningful if the work still lands before
   or during delivery of `window.__loadComplete`.

## What This Ruled In Instead

This falsifier narrowed the live thread:

- the main investigation should score “defer to post-yield” ideas against the
  browser-ready boundary first, not just server-phase timing
- `get_document(...)` and `list_document_headers(...)` remain better live
  targets than export-recovery timer reshuffling
- any future export-state optimisation needs either a real fast path that
  avoids the DB work or a browser-readiness contract that genuinely excludes it
