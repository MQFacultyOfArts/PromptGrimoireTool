# Large-document loading and annotation performance

Date: 2026-08-16
Status: design note; deliberately outside the deployment/testing hotfix

## User problem

Students struggled last semester with very large source documents. The two
important journeys are:

1. opening a large document and reaching an interactive Annotation view; and
2. adding, changing, locating, and commenting on annotations without one
   client's work degrading another client's session.

This is not hypothetical capacity planning. In the 16 March class, roughly 50
students uploaded the same supplied PDF at once. The service stalled for a few
minutes and recovered, but incident evidence recorded 36 upload requests in the
critical window: 15 succeeded, 14 returned 504, four returned 400, and three
returned 404 after session expiry/retry. The 10-connection application pool was
saturated alongside concurrent Annotation loads. The intended teaching shape
also includes up to five sources per workspace, one around 240 pages, with
about three collaborators per workspace.

The production-shaped fixture is *Pabai v The Commonwealth*: 425,788 HTML
characters, 5,020 text nodes, 190 CRDT highlights, 11 tags, a 176 KB CRDT
state, and an old initial response around 1.7 MB. Keep this fixture as the
minimum realistic boundary; tiny documents do not reproduce the problem.

## What is already known

- The old awaited browser round-trips were real failure amplifiers and have
  been removed. They caused timeouts and stale UI state, but removing them did
  not by itself remove annotation latency.
- The Python card tree was replaced by the Vue annotation sidebar. Lazy detail
  rendering and bulk HTML rendering removed substantial per-card NiceGUI work.
- Cold nested database sessions caused a structural QueuePool deadlock under a
  50-client wave. Optional session threading and startup cache warming fix that
  failure mode and have a dedicated constrained-pool regression test.
- Duplicate CRDT tag/group consistency work was removed. Hydrating the CRDT
  state itself was cheap (about 0.5 ms in the investigation); repeated database
  consistency reads were the material part.
- Loading Milkdown on every Annotation page was the largest demonstrated
  browser-readiness bottleneck. Deferring it until the Respond tab cut the
  independent 50-browser average from roughly 11.7 seconds to 5.8 seconds in
  the current hotfix rerun. This is a base-product improvement, not merely a
  test-runner optimisation.
- Parsing the Pabai HTML was about 26 ms locally. `ui.html()` construction was
  below 1 ms. Paragraph-marker injection is a second parse only when a
  paragraph map exists; Pabai's map was empty. These are not current primary
  targets.
- Browser `applyHighlights()` and `positionCards()` were around 10 ms and 3 ms
  in the earlier Pabai probe. Do not optimise them from intuition alone.
- PgBouncer, smaller QueuePool ceilings, splitting workspace metadata from the
  CRDT payload, header-query narrowing, and first-document phase reordering did
  not improve the measured end-to-end path. Preserve them as dead ends unless
  a new profile changes the premise.

## Smallest next discriminating performance probes

These are manually invoked investigation workloads for `grimoire e2e perf`.
They are not part of `e2e slow`, ordinary PR CI, or the nightly schedule. Their
purpose is to reproduce the load that forced admission queues, attribute event-
loop lag to a specific phase, and compare controlled fixes. Once a cause is
demonstrated, retain only the smallest cheap and deterministic regression
boundary in routine CI.

Do not begin with one mixed end-to-end storm. Establish three curves first:

1. **Cold-load curve:** barrier-release independent Pabai workspace loads;
   clients remain connected but idle after readiness.
2. **Connected-client curve:** preloaded Pabai clients remain connected and
   idle, separating per-client steady-state cost from page construction.
3. **Active-session curve:** preloaded clients continuously read, navigate, and
   write at controlled human rates. Include scrolling through the large source,
   selecting text, creating/changing highlights and tags, expanding cards,
   seeking/warping between cards and source text, switching documents and
   Source/Organise/Respond tabs, dragging Organise cards, typing and editing
   comments, typing in the Respond editor, pausing to read, and occasional
   disconnect/reconnect cycles.

Only after those curves identify their separate knees should the full student
journey combine them. This distinguishes a concurrency ceiling from an arrival-
burst ceiling and from a collaboration/write-amplification ceiling.

The active workload must use seeded action schedules so before/after runs are
reproducible. Model actions by rate and duration rather than fixed test sleeps:
typing should emit real key/input events at a configurable human characters-
per-second range; scrolling should use incremental wheel/scroll events with
reading pauses; seeking and tab changes should occur at recorded intervals.
Record the actual event/action counts completed by every client. Maintain at
least three mixes—read-heavy, annotate-heavy, and Respond-heavy—because one
average mix can conceal the expensive event family.

Run the diagnostic curves with admission disabled on an isolated test server
to expose the intrinsic knee. Then repeat the boundary region with the current
admission gate enabled. The second run answers whether the queue protects the
server before nonlinear lag/error growth while still admitting useful work; it
must not be used to hide the underlying curve.

Use one application server and one database. Increase client load against that
server; do not spin up a server per browser for these probes.

### 1. Large-document load baseline

Retain the existing Pabai performance lane and report separately:

- initial response end;
- DOMContentLoaded;
- NiceGUI socket/outbox readiness;
- Annotation-ready marker;
- event-loop p95/p99/max lag;
- database checkout wait and connection hold time; and
- browser resource timing and transferred bytes.

Measure an adaptive concurrency ramp rather than treating a few widths as pass/
fail gates. Start at 1, 10, 25, and 50 clients, then approach the historically
bad region at 75, 90, 100, 110, and 125. Once the knee is visible, repeat more
densely on either side of it. Stop increasing after the configured safety
boundary is crossed; a controlled overload result is sufficient and crashing
the test host adds no information.

At each width record throughput, latency percentiles, error/cancellation rate,
event-loop lag, CPU, RSS, database checkout/hold time, connection-pool state,
NiceGUI client/outbox state, and admission state. Plot each metric against both
concurrent clients and arrival rate. The useful result is the first nonlinear
change and which resource changes with it, not merely the largest completed
width.

### Diagnostic fields available for the probe

Run the application with `APP__DIAGNOSTIC_INTERVAL_SECONDS=1`. The ordinary
production interval is too coarse for a load curve. The diagnostic loop samples
event-loop scheduling drift every 100 ms and emits bounded per-interval
aggregates in `load_diagnostic`:

- `event_loop_lag_ms_count/avg/p95/max`;
- `db_connection_hold_ms_count/avg/p95/max`;
- `crdt_persist_ms_count/avg/p95/max`;
- `crdt_persist_bytes_count/avg/p95/max`;
- `crdt_broadcast_ms_count/avg/p95/max`; and
- `presence_broadcast_bytes_count/avg/p95/max`.

`memory_diagnostic` also carries numeric pool occupancy, total/max queued
NiceGUI outbox updates and messages, client/task/CRDT/presence counts, RSS, and
admission cap/admitted/queue/ticket state. CPU and request outcomes remain
external load-generator/host observations and must be correlated by timestamp.

The samples are bounded to 10,000 values per metric per interval, preventing
the observer from growing without limit. Do not add per-scroll or per-keystroke
server logs; the seeded load driver owns those counts.

### Initial cold-load curve (2026-08-16)

One managed application server and co-located Chromium clients, independent
cloned Pabai workspaces, admission disabled for routing but still observed,
test-environment NullPool:

| Clients | Browser readiness | Peak sampled lag | Peak connection hold | RSS during |
|---:|---:|---:|---:|---:|
| 1 | 414 ms | 6 ms | 22.6 ms | 294 MB |
| 10 | 1.06-1.24 s | 115 ms | 145 ms | 401 MB |
| 25 | 2.97-3.86 s (avg 3.46 s) | 224 ms | 753 ms | 572 MB |
| 50 | 6.40-9.99 s (avg 8.21 s) | 587 ms | 1.75 s | 825 MB |

All clients completed at every width. The curve is already nonlinear between
10 and 25 simultaneous cold loads, and every multi-client width crosses the
admission gate's 50 ms decrease threshold. At 25 clients the outbox reached 280
queued updates in aggregate and 82 for one client.

Limitations: the current test-environment guard forced NullPool even when the
probe requested QueuePool, so this is not yet a production pool curve. The 50
Chromium instances also shared the server host, inflating absolute latency.
Before increasing past 50, fix the explicit performance-probe QueuePool mode
and separate or constrain load-generator CPU. The event-loop lag signal remains
real for this host-level workload, but attribution between browser contention
and application work is not yet complete.

Absolute browser times from many co-located Chromium instances are contaminated
by browser CPU contention. Prefer load generators on another host while keeping
one application server under test. When co-location is unavoidable, report
server timings separately and constrain/measure generator CPU so client load is
not mistaken for server event-loop failure.

### 2. Large-document student workload

Build a phased Pabai performance workload using the same adaptive ramp. All
clients must be genuinely distinct browser contexts against one application
server and one database. The scenario should cover the actual student
lifecycle:

1. clone the Pabai template into a distinct workspace per student;
2. load the cloned workspace and wait for the real Annotation-ready boundary;
3. scroll and seek through the full source with reading pauses, including
   card-to-source and source-to-card navigation;
4. switch among documents and Source, Organise, and Respond tabs;
5. create a highlight, apply/change a tag, expand cards, add/edit/delete a
   comment, drag Organise cards, and verify the sidebar/document state;
6. type and edit Respond content through real browser input events at human
   typing speed;
7. reload, then disconnect/reconnect, and verify the persisted state; and
8. continue reading and writing after reconnection to exercise the path that
   the older read-only contamination probe omitted.

Keep phase timings and assertions separate even when a manual investigation
runs them end to end. A failure must say whether clone, initial load, a tab
swap, a CRDT mutation, persistence, broadcast, or reconnection crossed its
boundary; an opaque total-duration failure is not actionable.

Extend the existing `test_independent_workspace_load.py`, Pabai rehydration in
`card_helpers.py`, cross-tab tests, and shared page-interaction helpers. Do not
build a second fixture loader or a parallel browser orchestration framework.

For each mutation, assert the underlying CRDT/database transition and the
originating browser result, not merely a badge or timing marker. Record clone
latency, handler latency, sidebar serialisation/update time, persistence time,
event-loop lag, database checkout/hold time, and payload/outbox size.

Run a second adaptive ramp where clients share one Pabai workspace. Keep it
separate from the cloned-workspace ramp: independent-workspace interference
means process/resource coupling, while shared-workspace interference can also
be legitimate CRDT/broadcast fanout. In the shared case, assert that every
client converges on all committed annotations without identity or author
contamination.

The earlier Pabai contamination probe loaded ten browsers concurrently but was
read-only after navigation. It preserved identity under that load while also
showing genuine render contention. That is useful negative evidence, not an
annotation-write test: it did not exercise concurrent CRDT writes, comments,
sleep/reconnect, or the persistence path implicated by the student reports.

### 3. Large-document import baseline

Measure PDF and DOCX creation separately with a production-sized fixture using
the same adaptive ramp. The 50-way case must replay the observed class boundary:
all clients upload the same supplied PDF concurrently while their distinct
workspaces are also being opened.

Record:

- upload accepted to durable job creation;
- extraction/conversion time;
- sanitisation and paragraph-map construction;
- database/CRDT initialisation; and
- time until the document can be opened.

Assert success/failure and recovery for every client; aggregate throughput
alone would hide the observed 504/400/session-expiry failure chain. Preserve
the exact pool, cancellation, event-loop-lag, and HAProxy-equivalent request
outcomes needed to distinguish slow extraction from connection starvation.

This should become a background job only if the synchronous path breaches the
interactive request budget or blocks the loop. Return `202 Accepted` plus a job
resource; reuse the existing export-job/worker conventions before inventing a
new queue.

## Ranked implementation candidates

1. **Rebaseline after lazy Milkdown.** The old rankings predate the largest
   measured fix. Explain the remaining server-to-browser gap before changing
   another subsystem.
2. **Make annotation updates incremental only if the new annotation probe shows
   full-state cost.** The Vue sidebar still serialises and pushes the complete
   item list on refresh, while highlight CSS is re-registered from the complete
   highlight set. Earlier browser JS timings were small, so first separate
   Python serialisation, WebSocket payload, Vue reconciliation, and broadcast
   fanout. Fix the demonstrated dominant slice, not all four.
3. **Defer or batch tag-selection UI.** The 50-way profile attributed the
   largest remaining synchronous Annotation UI loops to per-tag toolbar and
   highlight-menu buttons/tooltips. Build the menu on interaction, or emit one
   browser-side/bulk component, if post-Milkdown profiling still ranks it high.
4. **Collapse the repeated privileged-user reads.** The stale performance
   branch has a measured candidate (`47a07fa6`): about 430 -> 329 ms for
   `resolve_annotation_context` and 727 -> 544 ms for its page DB slice at
   50-way. Browser average barely moved, so transplant only after rebasing and
   rerunning the current probe; it is a secondary database win, not the main
   student-visible fix.
5. **Shorten individual document-path reads.** `list_document_headers()` and
   `get_document()` remained material single reads under width. Change one
   query at a time and require an end-to-end improvement. The broad
   missing-index and row-splitting theories were weakened or falsified.
6. **Move document import CPU work out of the request path.** PDF/DOCX parsing,
   sanitisation, paragraph-map creation, and CRDT initialisation are sensible
   worker/job boundaries when the import baseline demonstrates blocking.
7. **Consider document viewport/windowing last.** Sending and mounting the full
   426K-character document may remain expensive for the browser after the
   resource and outbox costs are separated. Virtualisation would be a major
   editor/highlight-coordinate migration; require a profile showing document
   DOM/layout as the remaining dominant cost before starting it.

## REST/worker boundaries

Good candidates, subject to the measurements above:

- `POST /api/documents` -> `202` + import job for large PDF/DOCX/HTML input;
- workspace/template cloning -> job only when large-workspace cloning exceeds
  the request budget;
- bulk enrolment -> job only for measured large batches; and
- export, which already has the right job/worker shape.

Possible later boundary:

- a read-only initial annotation snapshot endpoint, if measurement shows the
  NiceGUI initial props/outbox is the bottleneck. This is a frontend migration,
  not a free REST wrapper.

Do not move ordinary CRUD, live CRDT updates, presence, or cursor traffic to
REST. REST does not remove synchronous CPU from the event loop by itself, and
polling would weaken the collaboration model. Keep live collaboration on the
existing CRDT/WebSocket path; isolate CPU-heavy preparation and durable jobs.

## Stale-worktree salvage ledger

### `nicegui-perf-investigation`

- **Keep as evidence:** the long independent-load investigation, its
  production-shaped QueuePool probe, falsified experiments, query timings, and
  the measured privileged-read collapse.
- **Already salvaged:** lazy Milkdown, the independent shared-server load
  harness, nested-session fixes, and duplicate CRDT consistency removal.
- **Do not transplant:** env-gated sysmon instrumentation and its dependency;
  it is diagnostic scaffolding, not a product fix. Do not transplant timing
  instrumentation wholesale.
- **Conditional transplant:** `47a07fa6`, after a clean rebase and current
  before/after run.

### `nicegui-perf-a1-a2`

The substantive nested-session/lazy-dialog work is already represented on the
current line. The remaining branch history is mostly later dependency updates
and unrelated annotation fixes. Do not merge the branch wholesale.

### `h11-http`

This is a four-line experiment forcing Uvicorn's h11 implementation to avoid a
suspected httptools pipeline leak. There is no retained result in the worktree.
Do not salvage it without an executable reproducer showing cross-client
contamination and an h11/httptools A/B result.

### `horizontal-scaling-466`

Keep the HAProxy and multi-instance notes as future capacity/failure-domain
work. Horizontal scaling can increase capacity, but it does not cure
per-instance event-loop blocking or large-document browser work. It is not the
next fix for this student journey.

### `infra-split`

The useful worker-isolation architecture has already landed for export. Keep
the historical plans/postmortem; do not revive the branch as a general-purpose
worker framework until a measured document-import job needs it.

## Production-pool baseline (2026-08-16)

One managed server was pinned to 8 CPUs. Chromium load generators used the
other 24 CPUs. The app used production's QueuePool 20+10 through a local
PgBouncer in transaction mode (40+10, 120 clients) to PostgreSQL. PostgreSQL
itself remained host-wide, so this isolates browser CPU from the app but does
not reproduce production's fully co-located 8-core contention.

| Sessions | Median ready | Mean ready | Max ready | During RSS | Result |
| ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 435 ms | 435 ms | 435 ms | 290 MB | pass |
| 10 | 1.22 s | 1.22 s | 1.31 s | 399 MB | pass |
| 25 | 2.81 s | 2.81 s | 3.01 s | 574 MB | pass |
| 50 | 5.67 s | 5.17 s | 6.45 s | 842 MB | pass |
| 75 | 8.31 s | 7.13 s | 9.19 s | 1.03 GB | pass |
| 100 | 11.44 s | 9.74 s | 13.33 s | 1.19 GB | fail: 97/100 present |

At 50 sessions, server-side page construction averaged 2.39 s (746.9 ms in
the context/DB-resolution slice), while document rendering averaged 34.6 ms.
At 100 sessions all 100 browser workers reached the annotation-ready boundary,
but only 97 had completed NiceGUI/outbox/presence registration at the immediate
snapshot. The server had 100 WebSocket ASGI tasks but only 97 Outbox loops.
This is evidence that visible document readiness can precede live
collaboration readiness under load; do not weaken the assertion into a sleep.
PgBouncer's overlapping 60-second stats reported zero pool wait, roughly
0.6 ms/query, and 168 ms/transaction. That weakens PgBouncer saturation as the
cause and instead points at time held inside application transactions and the
remaining page/WebSocket work.

Raw diagnostic snapshots are in `perf-results/prod-pool-*.json`.

## Decision rule

The next implementation should be the smallest change that improves both a
realistic large-document student action and the corresponding server-side
attribution. A faster internal bucket with unchanged browser readiness is
useful evidence, not sufficient reason to ship architectural complexity.

## Primary local evidence

- `docs/investigations/2026-08-16-production-pool-load-curve.md`
- `docs/postmortems/2026-03-22-workspace-performance-377.md`
- `docs/postmortems/2026-03-24-377-wip-handoff.md`
- `docs/investigations/2026-04-23-page-load-failure-modes.md`
- `docs/reviews/2026-04-04-event-loop-offload-review.md`
- `.worktrees/nicegui-perf-investigation/docs/investigations/2026-04-19-independent-workspace-load.md`
