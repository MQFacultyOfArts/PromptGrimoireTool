# Page-Load Failure Modes (Annotation Page, 50-way Independent Loads)

Date: 2026-04-23
Status: Distilled reference for CLAUDE.md warnings
Source: The full phase-by-phase investigation lives in
`.worktrees/nicegui-perf-investigation/docs/investigations/2026-04-19-independent-workspace-load.md`
(1443 lines, 19 phases). This document extracts the failure-mode
classes from that investigation and records their current status on
branch `nicegui-perf-a1-a2`.

## How to read this doc

Each section documents one class of failure mode the investigation
surfaced, not a single fix. Where a fix has landed on
`nicegui-perf-a1-a2`, the section says so and names the regression
test that locks the contract. Where no fix has landed, the section
records the symptom, the mechanism, and a pointer to the phase of
the investigation that characterised it.

CLAUDE.md carries one-line warnings that link here.

---

## A. Cold-cache nested-session deadlock

**Mechanism.** A cache-populating helper (e.g. `get_staff_roles`)
opens its own `async with get_session()` for the cold-load query. A
caller inside an outer `async with get_session()` (e.g. the
annotation page's `resolve_annotation_context`) invokes the helper
with a cold cache. Under pool saturation, every outer transaction
holds one connection; the inner checkout waits on a connection that
will not free until its outer transaction completes; the outer
transaction cannot complete because its continuation is the inner
checkout. All N concurrent callers deadlock until SQLAlchemy's
`pool_timeout` fires (~30 s) and everyone fails.

**Symptoms.**
- `QueuePool limit of size 20 overflow 10 reached` log events during
  wide concurrent page loads on a cold process.
- Browser `avg_elapsed_ms` around 30 s at 50-way.
- Zero `page_load_profile` events completed in the bad window
  because the exception fires before profiling frames close.

**Status.** Fixed on this branch.
- `db/roles.py::get_staff_roles` and `get_all_roles` accept an
  optional `session=` kwarg; callers thread an outer session
  through to skip the cold-load checkout.
- `db/workspaces.py::has_student_workspaces` gains the same kwarg.
- `db/{acl,activities,courses,weeks,workspaces}.py` callers
  updated to pass `session=session`.
- `warm_role_caches()` is awaited during `startup()` after
  `init_db()`, so the cold-cache precondition cannot occur in
  production after the first process start-up boundary.

**Evidence.** Phase 18 of the full investigation ran the same
50-way probe on the pre-fix commit vs the post-fix commit, with
only the deadlock tranche changed and no profiling instrumentation
active. Result: browser `avg_elapsed_ms 30856.6 → 15611.0`, a ~49%
reduction. Sample size `n=1` per condition, so read this as "major
local cause," not "sole cause."

**Regression tests.**
- `tests/integration/test_nested_session_deadlock.py` —
  pool-constrained QueuePool(4+0), 8 concurrent tasks, asserts
  threaded path succeeds and bare path times out within the
  SQLAlchemy `pool_timeout` budget.
- `tests/integration/test_course_role_normalisation.py::TestGetStaffRoles::test_can_reuse_existing_session`
  and `test_get_all_roles_can_reuse_existing_session`.
- `tests/integration/test_delete_guards.py::TestHasStudentWorkspaces::test_can_reuse_existing_session`.
- `tests/integration/test_course_role_normalisation.py::TestWarmRoleCaches`
  (warmup + idempotence).

**How to avoid regressions in new code.** Any future helper that
opens its own session MUST accept an optional `session=` kwarg and
document the threading rule. Reviewers should reject additions of
bare `async with get_session():` inside another `async with
get_session():` unless the inner call is genuinely independent and
limited to a fixed number of callers.

---

## B. Long transaction hold times amplify checkout queueing

**Mechanism.** Even without a deadlock, a single transaction that
holds a connection for ~1-2 s while doing several sequential queries
creates a queue of other connections waiting to check out. Under
50-way concurrent page loads with pool size 20+10, every new
request observes the full ceiling saturated and must wait.

**Symptoms.** In the clean-run profile after the deadlock fix:
- `resolve_annotation_context` sample: `checkout_wait_ms=649.5`,
  `hold_ms=1521.6`, `total_ms=2171.1`.
- `get_document` sample: `checkout_wait_ms=691.1`, `hold_ms=622.9`.
- Pool reaches full saturation during the load wave, even with
  correct session threading.

**Status.** Not fixed on this branch. The investigation did not
identify a clean single-variable reduction; Phase 19's attempted
split of `workspace_template_lookup` into metadata + CRDT state
reads made wall-clock worse, not better, because both reads share
the pool.

**Pointers.**
- Full investigation § Finding 7 and Phase 14.
- The next discriminating work (out of scope here): shorten the
  `workspace_lookup_ms` / `permission_ms` / `privileged_user_ids_ms`
  slices inside `resolve_annotation_context` without duplicating
  round-trips.

**How to avoid regressions in new code.** Treat connection hold
time as a first-class cost surface. Avoid adding sequential
`await session.exec(...)` chains inside a single transaction when
each query could stand alone; if you must, measure whether batching
into a single round-trip is feasible (JOIN, `IN`, CTE) before
landing.

---

## C. Duplicate CRDT tag/group consistency work

**Mechanism.** The annotation page touched the CRDT registry twice
on a single initial load: once in `_resolve_db_context` (cold load
with prefetched tags/groups available) and again in
`_load_crdt_for_workspace` (registry hit, but re-ran non-prefetched
tag consistency). The second pass re-queried tags and groups even
though the first pass already had them.

**Symptoms.** `crdt_registry_profile` showed two entries per page
load at 50-way; the second entry's `consistency_ms` was 90-194 ms on
the hit path where `apply_update_ms` was ~0.5 ms.

**Status.** Not fixed on this branch. The investigation fixed it in
Phase 4 of the sibling worktree; that change is not ported here.

**Pointers.**
- Full investigation § Finding 2, Finding 4, and Phase 4.
- The fix path: prefetch tags/groups, thread them through both
  `get_or_create_for_workspace(...)` calls, drop the second
  consistency pass.

**How to avoid regressions in new code.** A page that calls a
registry or cache-populating helper twice on the same render path
is a smell. If you see it, ask whether the second call is doing
different work or duplicating the first.

---

## D. Eager heavy-dialog or modal construction during page render

**Mechanism.** `ui.dialog()` / `ui.card()` / `ui.element("iframe")`
and their children are built during the synchronous page-render
pass even though most users never open the dialog. Each builder
call stages NiceGUI update messages; the dialog subtree can stage
dozens per page load, multiplied by the concurrency width.

**Symptoms.** `layout_help_mkdocs` phase bucket at 50-way was 4800
update enqueues before the fix, 1200 after. On the annotation
page specifically, the dominant remaining buckets at 50-way
(unchanged by A1/A2) are `document_toolbar_tag_button = 6050` and
`document_highlight_menu_tag_button = 5500` — see pattern E.

**Status.** Fixed on this branch for the MkDocs help dialog.
`_render_mkdocs_help()` now builds the dialog tree inside an
on-click closure and caches the constructed dialog in a closure
variable so subsequent opens reuse the instance.

**Regression tests.**
- `tests/unit/test_help_button.py::TestMkdocsHelpLazyConstruction::test_eager_render_creates_button_but_not_dialog`
  — mocks `ui.*` and asserts `ui.dialog`, `ui.card`, `ui.element`
  are NOT called on page render.
- `tests/e2e/test_help_button.py::TestHelpButton::test_help_dialog_reopens_after_close`
  — opens, closes, reopens, asserts a single cached iframe with
  the same `src`.

**How to avoid regressions in new code.** Any new dialog or modal
whose body is non-trivial (multiple elements, an iframe, a
scrollable list, a form with many fields) should build inside its
on-click closure, not at page-render time. Keep only the trigger
button eager. Cache the built dialog in a closure variable after
the first open so reopens are cheap.

This pattern is also recorded as the 7th E2E race-condition /
NiceGUI pattern in CLAUDE.md.

---

## E. Per-item O(N) synchronous UI loops during initial render

**Mechanism.** Rendering the annotation page constructs one
NiceGUI element per tag (toolbar + highlight menu), one per nav
drawer item, one per header cell, etc. Each element stages several
update enqueues; N tags × ~4 elements each × 50 concurrent clients
produces tens of thousands of synchronous UI-build events during
the page-load wave, on the event loop.

**Symptoms.**
- `document_toolbar_tag_button = 6050` at 50-way.
- `document_highlight_menu_tag_button = 5500` at 50-way.
- Page-level `total_ui_ms ≈ 1.3 s` even with a prewarmed document
  fetch.

**Status.** Not fixed on this branch. The investigation identified
this as the largest remaining annotation-page synchronous cost
after A1 + duplicate-CRDT removal.

**Pointers.** Full investigation § Phase 8, Ranked Conclusion #2,
Attack Order #2.

**How to avoid regressions in new code.** When adding a per-item
render loop that fires on every page load, ask: does every user
need every item visible up-front? If the answer is "no, only on
interaction," defer construction to the interaction handler. If
the answer is "yes," batch the construction into a single
`ui.html(...)` or similar bulk emission rather than one NiceGUI
element per item.

---

## F. Synchronous UI work amplifies event-loop lag, but does not
collapse the loop

**Mechanism.** Aggregate synchronous page-build work (all the
`ui.button(...)` / `ui.label(...)` / etc. calls) creates measurable
event-loop lag during concurrent page-load waves. The lag does not
become total loop collapse at 50-way; it manifests as p95 and p99
spikes.

**Symptoms.**
- 10-way clean: `p95_lag_ms = 35.8`, `max_lag_ms = 77.6`.
- 50-way clean: `p95_lag_ms = 94.97`, `p99_lag_ms = 209.5`,
  `max_lag_ms = 261.6`; `blocked_over_5000ms = 0`.

**Status.** Not fixed on this branch. It is a symptom of patterns
D and E rather than a separate mechanism. Fixing D and E shrinks
the synchronous window and thereby shrinks the lag.

**Pointers.** Full investigation § Finding 8, Finding 9, and
`independent-load-h-sync-ui-build-is-a-real-but-secondary-starvation-amplifier`.

**How to avoid regressions in new code.** Any page-render work
that runs on the event loop counts against every concurrent
client's responsiveness. Prefer async boundaries for non-trivial
work: `asyncio.to_thread(...)` for CPU-bound helpers, fire-and-
forget background tasks for post-render polish, and defer heavy
UI to interaction (pattern D).

---

## G. Co-located Playwright harness inflates E2E latency

**Mechanism.** The `test_concurrent_independent_pabai_loads` probe
runs N Chromium instances on the same host as the server and
database. At 50-way, the browsers themselves contend with the
server for CPU, inflating both browser-observed `elapsed_ms` and
server-side timings relative to what a remote-client or
lightweight-client probe would report.

**Symptoms.** At 50-way, browser `avg_elapsed_ms ≈ 11-12 s` while
server `page_load_profile.total_ms ≈ 2-3 s`. The gap is too large
to be wholly server-side.

**Status.** This is a harness artefact, not a production code
problem. The investigation acknowledges it as a measurement
caveat.

**Pointers.** Full investigation § Finding 11, hypothesis
`independent-load-h-co-located-browser-contention-inflates-e2e-latency`.

**How to avoid mistakes in new measurement work.** When using the
50-way probe to validate a production claim, report the server-
side `page_load_profile.total_ms` separately from browser-observed
`elapsed_ms`, and treat the ordering of server-side slices as the
durable signal, not the absolute numbers. Before making a
production magnitude claim, run a lightweight-client probe (e.g.
raw WebSocket + `httpx`) to cross-check.

---

## Cross-reference

| Class | Mechanism shorthand | Fixed here? | CLAUDE.md home |
|-------|---------------------|-------------|----------------|
| A | nested `get_session()` | ✅ A1 + M3 | Database Key Rules |
| B | long transaction hold | ❌ | Performance failure modes |
| C | duplicate registry pass | ❌ | Performance failure modes |
| D | eager heavy-dialog | ✅ A2 | E2E Race-Condition Patterns (pattern 7) |
| E | per-item O(N) UI loops | ❌ | Performance failure modes |
| F | sync UI → loop lag | ❌ (consequence of D/E) | Performance failure modes |
| G | co-located harness | n/a (harness artefact) | Performance failure modes |
