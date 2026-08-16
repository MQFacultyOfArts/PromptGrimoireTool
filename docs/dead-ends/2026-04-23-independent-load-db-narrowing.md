# Dead End: Independent Load DB Narrowing Falsifiers

**Date:** 2026-04-23
**Investigation:** `docs/investigations/2026-04-19-independent-workspace-load.md`
**Branch:** `investigate/nicegui-perf`
**Status:** Abandoned

## Problem

The clean post-deadlock `50`-way `QueuePool(20+10)` path was still taking about
`11.5 s` browser-observed and several hundred milliseconds of DB time in
`resolve_annotation_context(...)` and `list_document_headers(...)`.

Before changing schema or query shape more aggressively, two "obvious narrowing"
ideas were tested:

1. split `workspace_template_lookup` into metadata now and `crdt_state` later
2. narrow `list_document_headers(...)` further by deferring `paragraph_map`

Both were plausible enough to test. Neither earned a place on the live path.

## Approaches Tried (Both Failed)

### 1. Metadata-First Workspace Lookup, `crdt_state` Later

`resolve_annotation_context(...)` was narrowed so the initial workspace query
loaded only metadata needed for placement and permission resolution. A second
read fetched `Workspace.crdt_state` immediately before CRDT hydration.

**Evidence:**

- baseline `/tmp/iw-50-db-profile-3.json`
- split experiment `/tmp/iw-50-db-profile-4.json`

**What improved:**

- `workspace_lookup_ms avg`: `74.7 -> 55.9`
- `workspace_template_lookup_statement_total_ms max`: `554.0 -> 103.2`
- `resolve_annotation_context_ms avg`: `429.9 -> 368.3`

**Why it failed overall:**

- new `workspace_crdt_state_ms avg = 411.9`
- page DB total worsened: `726.9 -> 1024.9`
- browser average worsened: `11496.4 -> 12129.2`

The experiment did reduce the width and tail of the initial workspace lookup,
but it simply moved the cost into a second checked-out read. Since the page
still needs `crdt_state` moments later, splitting the read without changing the
broader pipeline just added queueing and hold time.

### 2. Deferring `paragraph_map` on `list_document_headers(...)`

`list_document_headers(...)` was narrowed further so `paragraph_map` was
explicitly deferred alongside `content`, with a guard test asserting
headers-only rows should raise on `.paragraph_map`.

**Evidence:**

- baseline `/tmp/iw-50-db-profile-3.json`
- deferral experiment `/tmp/iw-50-db-profile-5-headers.json`

**What was expected:**

- less row width on the document-header path
- lower `list_document_headers_ms`

**What happened instead:**

- browser average worsened: `11496.4 -> 12171.6`
- `list_document_headers_ms avg`: `296.1 -> 301.7`
- `session_connection_profile(list_document_headers).hold_ms avg`:
  `102.2 -> 125.4`

**Most likely reason:**

The PABAI clone’s `paragraph_map` was already tiny enough that deferring it did
not buy a meaningful row-width reduction. That means the experiment probably
added ORM/deferred-loading overhead without removing a real cost centre. The
measured regression was therefore enough reason to revert even though the exact
magnitude is subject to normal run-to-run drift.

## Caveats

- Both experiments were `n=1` per condition.
- Both were compared to the earlier clean profiled baseline
  `/tmp/iw-50-db-profile-3.json`, so cache or machine-state drift could affect
  exact deltas.
- Those caveats do not rescue either idea:
  the workspace split clearly lost because it introduced a large second read,
  and the paragraph-map deferral failed to show any positive signal on the
  targeted read.

## What Not To Try Again

1. A naive "metadata now, `crdt_state` later" split that adds a second
   checked-out read to the annotation hot path.
2. A standalone `paragraph_map` deferral on `list_document_headers(...)` as if
   it were the dominant source of header-read width.

## What This Ruled In Instead

These failures helped narrow the live thread:

- workspace row-shape work is at best a second-order seam unless it avoids the
  second-read penalty entirely
- the better next DB target is the remaining document-path reads themselves,
  especially `get_document(...)` and `list_document_headers(...)`
- the privilege-read collapse that followed was a genuine positive win, so the
  investigation should keep favouring falsifiable, bounded hot-path edits over
  broader speculative rewrites
