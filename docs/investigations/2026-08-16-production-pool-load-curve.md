# Production-Pool Large-Document Load Curve

Date: 2026-08-16
Status: Reproduced; unacceptable latency growth and readiness failure unresolved
Harness: `tests/e2e/test_independent_workspace_load.py`

## Question

What fails as concurrent students cold-load independent clones of the large
PABAI document, and is the current PostgreSQL pooling topology the cause?

This investigation covers initial document loading only. Typing, scrolling,
seeking, annotation creation, tab switching, and sustained mixed activity are
deliberately deferred until initial-load readiness is trustworthy.

## Setup

- One managed PromptGrimoire/NiceGUI server pinned to CPUs 0-7.
- Chromium load generators pinned to CPUs 8-31.
- Application QueuePool: 20 connections + 10 overflow.
- Local PgBouncer: transaction mode, default pool 40 + reserve 10,
  `max_client_conn=120`.
- PostgreSQL ran on the same host but was not CPU-pinned. This does not fully
  reproduce production's co-located 8-core contention.
- Every browser authenticated independently and loaded a distinct clone of the
  PABAI workspace.
- A loaded browser waited at a barrier so the server could snapshot all clients
  concurrently.

The perf lane's ordinary NullPool remains the default. `--queue-pool` opts into
configured pooling, and `E2E_PERF_DATABASE_URL` repoints only the managed app
server after direct test-database migration and cleanup. This avoids running
schema and cloning operations through a transaction pool.

### Methodology correction

Sequential 100-browser waves on this shared host showed substantial
run-position variation even when each run began below the original load
threshold. A low load sample prevents overlap; it does not prove the host has
recovered from the preceding Chromium wave. Cross-run browser deltas below are
therefore provisional unless reproduced with order control. Structural counts,
payload sizes, and within-run server instrumentation remain valid.

The perf command now holds a host-wide file lock and requires four consecutive
15-second samples at load 4 or below before starting. Comparative runs must use
an ABBA order (baseline, candidate, candidate, baseline), record their run
position, and report server-side and browser-side verdicts separately. A
separate browser-generator host is still required before treating browser
timings as a production client latency curve.

## Results

| Sessions | Median ready | Mean ready | Max ready | During RSS | Boundary |
| ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 435 ms | 435 ms | 435 ms | 290 MB | pass |
| 10 | 1.22 s | 1.22 s | 1.31 s | 399 MB | pass |
| 25 | 2.81 s | 2.81 s | 3.01 s | 574 MB | pass |
| 50 | 5.67 s | 5.17 s | 6.45 s | 842 MB | pass |
| 75 | 8.31 s | 7.13 s | 9.19 s | 1.03 GB | pass |
| 100 | 11.44 s | 9.74 s | 13.33 s | 1.19 GB | **fail: 97/100 present** |

At 50 sessions:

- server-side page construction averaged 2.39 s;
- the context/DB-resolution slice averaged 746.9 ms and peaked at 1.86 s; and
- document rendering averaged 34.6 ms and peaked at 159.9 ms.

At 100 sessions all 100 browser workers reached the existing
`annotation-ready` boundary. The simultaneous server snapshot contained:

- 100 WebSocket ASGI tasks;
- 100 WebSocket writer/wait tasks;
- 97 NiceGUI clients;
- 97 Outbox loops;
- 97 CRDT documents;
- 97 presence workspaces and clients; and
- 97 application WebSocket registry entries.

There were no browser-worker errors. The test failed because visible annotation
readiness did not imply that all collaboration machinery was ready.

PgBouncer's overlapping 60-second statistics reported zero pool wait, about
0.6 ms/query, and about 168 ms/transaction. The test app's QueuePool was full
but had no connections checked out at the simultaneous snapshot.

Raw snapshots are retained in `perf-results/prod-pool-*.json`.

## Interpretation

The primary failure is the nonlinear student-visible latency: 5.67-second
median readiness at 50 sessions and 11.44 seconds at 100 are unacceptable even
if every client eventually becomes collaboration-ready. The 97/100 presence
result is a second correctness failure, not the sole reason the 100-way point
failed.

### Supported

1. The student-visible cold-load curve bends substantially between 25 and 100
   concurrent sessions on an 8-core app allocation.
2. Document rendering is not the dominant server-side cost in this probe.
3. At 100-way load, page visibility can precede NiceGUI Outbox, CRDT registry,
   and collaboration-presence readiness.
4. Application transaction duration and page/WebSocket orchestration are
   stronger candidates than PgBouncer queueing.

### Weakened or ruled out

- **PgBouncer saturation as the immediate cause:** no measured pool wait and
  sub-millisecond query time during the load window.
- **PgDog as the next fix:** changing poolers would move the queue without
  addressing the demonstrated readiness gap or transaction duration.
- **Large-document render CPU as the immediate server bottleneck:** the
  measured render slice remained small relative to end-to-end readiness.
- **A sleep in the test:** it would conceal the fact that the UI claims ready
  before collaboration is ready.

### Not yet established

- Whether the three missing clients eventually register or remain stranded.
- Which transition is delayed: WebSocket connection, NiceGUI client creation,
  Outbox start, CRDT registry insertion, or presence registration.
- The contribution of fully co-located PostgreSQL CPU contention.
- Behaviour under sustained student actions after initial load.

## Next falsifiable experiment

Add timestamps, keyed by NiceGUI client ID and workspace ID, at exactly four
boundaries:

1. annotation page handler complete;
2. WebSocket connected / NiceGUI client established;
3. Outbox loop started; and
4. CRDT and presence registration complete.

Repeat 75 and 100 sessions several times. At the loaded barrier, record each
client's last completed boundary; then keep the connections open briefly and
take a second snapshot.

- If all clients reach boundary 4 later, this is delayed collaboration
  readiness and the product readiness contract is wrong.
- If some never reach boundary 4, this is a reproducible lifecycle defect.
- If the missing boundary varies between runs, profile the earliest shared
  stalled transition before changing database or UI architecture.

Only after this boundary is understood should the scenario add human-speed
typing, scrolling, seeking, annotation creation, tab switching, and sustained
10/50/100-user activity.

For the next run, treat p95 full collaboration readiness below 3 seconds at 100
sessions on an 8-core app allocation as the provisional performance target.
Revise that target only from production user-experience evidence, not to make
the current curve pass.

## Phase 2: per-wave attribution and duplicate CRDT work

The diagnostic endpoint was extended to drain the existing bounded load
metrics at the before/during/after snapshots. Page phases and presence
registration now contribute to the same wave. This avoids relying on the
30-second production diagnostic interval for a load wave shorter than 30
seconds.

### Baseline attribution

At 75 sessions, browser mean/p95 readiness was 6.37/8.29 seconds. Server-side
page construction averaged 3.45 seconds (p95 5.61):

- context/DB resolution: 1.50 seconds average, 3.99 seconds p95;
- tab panels: 1.54 seconds average, 2.93 seconds p95;
- DB connection holds: 979 samples, 100 ms average, 291 ms p95; and
- event-loop lag: 18.5 ms average, 100 ms p95, 146 ms max.

At 100 sessions, browser mean/p95 readiness was 8.56/11.26 seconds. Server page
construction averaged 4.89 seconds (p95 7.66), context/DB resolution averaged
2.24 seconds, and tab panels averaged 2.09 seconds. Event-loop lag reached
107 ms p95 and 232 ms max.

The existing `tab_panels_profile` logs split that apparent UI cost at 100 into
1.48 seconds of CRDT loading, 579 ms of document fetch, and only 33 ms of first
panel rendering. The measured growth is overwhelmingly asynchronous DB/CRDT
work delayed under load, not document-render CPU.

### Duplicate CRDT consistency removal

The initial path performed tag/group consistency three times:

1. registry hydration queried tags and groups itself;
2. the caller immediately repeated consistency with already-prefetched tags;
3. the tab builder hit the registry and repeated consistency again.

The registry now accepts the prefetched tags/groups, and the tab builder reuses
the document hydrated earlier in the same page load.

At 100 sessions this reduced:

- DB connection uses from 1305 to 905;
- server page mean from 4.89 to 3.84 seconds;
- server page p95 from 7.66 to 6.55 seconds;
- context/DB mean from 2.24 to 1.82 seconds; and
- tab/CRDT mean from 2.09 to 1.01 seconds.

It did **not** improve the student boundary: browser p95 remained 11.27 seconds
and mean worsened from 8.56 to 9.21 seconds in the single A/B run. Event-loop
lag p95 also rose from 107 to 132 ms. Retain the change because it removes 400
real DB connection uses and duplicate authoritative-state reconciliation, but
do not claim it fixes the load curve.

### Lifecycle boundary refined

The attributed 100-way baseline happened to retain 100/100 presence clients.
The post-dedup 100-way run retained only 87/100. In the latter run the wave
metric recorded all 100 presence registrations before the snapshot. Therefore
the missing clients registered successfully and were then removed from
NiceGUI, CRDT, presence, and application registries while their browser workers
still reported the annotation-ready boundary.

The next lifecycle experiment must instrument client disconnect/delete time
and reason after successful presence registration. It should also A/B NiceGUI
3.15 against 3.16 in a separate dependency-only change: 3.16 contains upstream
client-disconnect and deleted-client lifecycle fixes, but mixing that upgrade
into this application A/B would destroy attribution.

## Phase 3: production reconnect grace

The managed E2E server used NiceGUI's `reconnect_timeout=0.5`, while production
uses 15 seconds. At 100-way load, brief Socket.IO disconnects therefore became
permanent test-client deletions 30 times faster than production. This explains
the intermittent 97/100 and 87/100 presence snapshots; they are not valid
production-lifecycle results.

The perf command now sets `E2E_RECONNECT_TIMEOUT=15`; ordinary E2E retains the
0.5-second cleanup setting. With production grace, the 100-way probe retained
100/100 presence clients, but performance remained unacceptable:

- browser mean/p95/max: 9.53/12.35/12.62 seconds;
- server page mean/p95: 3.80/6.76 seconds;
- event-loop lag p95/max: 109/378 ms; and
- RSS during the wave: 1.27 GB.

The snapshot contained 269 NiceGUI `Client` objects for 100 annotation
presence clients, and still contained 200 immediately after the browsers
navigated away. These include earlier authentication/navigation clients kept
alive for the 15-second reconnect grace. This is expected lifecycle retention,
not yet proof of a leak, but it amplifies memory and per-client server state
during a cold-login wave.

The current probe is therefore specifically a **cold login followed by a
simultaneous cold document load**. Add an already-authenticated-session control
before generalising the 269-client multiplier to ordinary classroom navigation.
The annotation architecture remains suspect independently: even after removing
duplicate CRDT work, 100 active annotation pages retain about 1.2 GB and push
event-loop lag past 100 ms p95.

Architectural candidates, in order of reversibility:

1. move tag/group consistency from page reads to clone/import/mutation paths,
   retaining an explicit repair operation for exceptional drift;
2. collapse remaining context/header/document reads into fewer, shorter
   transactions rather than wrapping async DB work in threads;
3. serve the initial document/tags/permissions snapshot through a REST endpoint
   and render the large read surface in the browser, while keeping CRDT edits,
   presence, cursors, and broadcasts on WebSocket; and
4. distribute clients across app processes only after defining workspace
   affinity or shared collaboration state.

NiceGUI slot-bound UI construction cannot safely be moved to a worker thread.
The architectural way to remove it from the Python event loop is to stop
constructing that initial surface as a per-client server-side element tree.

## Phase 4: permission-query easy wins

Two existing permission paths did avoidable work on every annotation load:

- enrollment resolution loaded the cached staff-role set separately from the
  user's enrollment; and
- privileged-user resolution queried staff enrollments and administrators
  separately.

Both now use the persisted `course_role_ref.is_staff` classifier directly, and
privileged users are selected by one union query. An explicit owner ACL also
short-circuits the remaining enrollment lookup because no derived permission
can exceed owner. The annotation-context query budget for the owner fixture
fell from nine to six statements.

At 100 sessions with production reconnect grace, the combined changes moved
browser mean/p95/max from 9.53/12.27/12.62 seconds to
9.02/11.02/11.14 seconds. All 100 clients reached and retained presence.
Server page mean remained effectively flat (3.80 to 3.79 seconds), event-loop
lag p95 remained 108 ms, DB connection uses remained 905, and RSS remained
about 1.27 GB.

Retain this bounded improvement: it removes redundant permission queries and
improves the observed student boundary by about 0.5 seconds mean and 1.25
seconds p95. It does not change the architectural scaling limit. The next
low-risk experiment is an already-authenticated cold-document wave; moving the
initial read surface out of NiceGUI remains a separate architectural change.

## Phase 5: authenticated-session control

The performance probe can now navigate its authenticated warm-up pages to
`about:blank` and wait out the 15-second production reconnect grace before
releasing the document-load barrier. This retains each browser session cookie
while removing the preceding login/navigation NiceGUI client from the wave.

Two 100-session controls with a 16-second settle produced:

| Run | Browser mean | Browser p95 | Server mean | Lag p95 | NiceGUI clients | RSS |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Unsettled | 9.02 s | 11.02 s | 3.79 s | 108 ms | 281 | 1.27 GB |
| Settled 1 | 10.10 s | 11.59 s | 3.67 s | 88 ms | 119 | 1.19 GB |
| Settled 2 | 10.35 s | 11.92 s | 3.71 s | 73 ms | 129 | 1.19 GB |

All runs retained 100/100 annotation presence clients. Removing warm-up clients
reliably saved about 83 MB and reduced event-loop lag p95, but did not improve
the student readiness boundary. Login/navigation retention is therefore a
real transient memory amplifier, not the cause of the document-load latency.

The settled controls leave roughly 6.4 seconds between measured server page
completion and browser readiness. The next measurement should split that gap
with browser-visible milestones for initial response, NiceGUI connection,
outbox application, document/sidebar mount, and collaboration readiness. Do
not attempt another server query optimisation on the assumption that the full
remaining delay is in the database.

## Phase 6: browser readiness milestones

The independent-workspace probe now records browser-visible milestones without
adding production logging. In a 100-session settled-authentication wave, mean
times from navigation start were:

- DOM content loaded: 0.92 seconds;
- annotation WebSocket observed: 0.93 seconds;
- document container mounted: 12.76 seconds;
- highlights ready: 12.92 seconds; and
- final annotation readiness: 12.93 seconds.

The server page-build mean was 3.82 seconds (p95 6.53 seconds). Highlight
application added about 157 ms after the document appeared, and the final
readiness boundary added about 16 ms. The dominant interval is therefore after
the WebSocket connects and before the generated document UI mounts. It is not
authentication, initial HTTP/WebSocket establishment, highlight range
construction, or the final collaboration-ready signal.

The next probe records WebSocket frame count and payload bytes through document
readiness. Use that result to distinguish a large generated-UI payload from
outbox/event-loop scheduling delay; do not begin a client-render rewrite until
that distinction is measured.

That probe measured about 730 KB per client across 12--16 received WebSocket
frames, or 73 MB fanned out for the 100-session wave. The final frame was
observed an average 4.40 seconds before the document mount (median 5.36 seconds,
p95 8.59 seconds). Server page construction remained 3.68 seconds mean and
highlight application remained about 171 ms. Because all 100 Chromium clients
share the load-generator CPUs, this post-frame interval combines real browser
DOM/application cost with synthetic client CPU and Playwright scheduling
contention. It is not directly a production student-latency measurement.

The document renderer currently sends the full paragraph-injected source as a
NiceGUI `ui.html` element property; no existing authenticated document-content
endpoint can replace that path. A one-session frame-size follow-up will show
whether one document frame dominates the 730 KB. The host-load guard correctly
refused that follow-up at load 20.6 after the 100-session wave. Do not override
the guard merely to complete this measurement.

After load fell naturally, the one-session follow-up showed that one 665 KB
frame accounts for 91% of the 730 KB total. With no browser-generator
contention, the final frame arrived at 169 ms, the document mounted at 691 ms,
and annotation readiness completed at 725 ms. The 100-session browser curve
therefore overstates production client-side degradation. The server boundary
is still unacceptable: at 100 sessions the final-frame p95 was about 13.83
seconds while server page-build p95 was 6.49 seconds. Next investigate the
server event-loop/outbox interval and socket backpressure; use distributed
browser generators before asserting a production browser-mount curve.

## Phase 7: NiceGUI outbox timing

Perf-server-only instrumentation measured the boundary around NiceGUI update
preparation and `socketio.emit`. At 100 settled-authentication sessions there
were 267 update batches (about 2.7 per annotation page):

- time from the final element enqueue through update preparation: 215 ms mean,
  623 ms p95, 1.19 seconds max;
- `socketio.emit` duration: 134 ms mean, 282 ms p95, 451 ms max; and
- update batch size: 38 elements mean, 82 elements p95, 98 max.

Final-frame p95 remained 13.62 seconds while page-build p95 was 6.48 seconds.
Update preparation is material, but neither it nor `socketio.emit` blocks for
the multi-second tail. Engine.IO's `send` merely places packets on its
per-client queue; the Socket.IO timing does not measure the subsequent ASGI
WebSocket writer or downstream backpressure.

The next perf-only timer wraps the Engine.IO ASGI WebSocket send and separately
records frames at least 100 KB. This is the last useful in-process transport
boundary before the browser/load-generator split.

The queued 100-session run began only after one-minute host load fell below 4.
Engine.IO recorded 1,976 WebSocket sends at 0.97 ms mean and 15.7 ms p95. The
100 large document frames averaged 662 KB and their actual ASGI WebSocket send
took 17.2 ms mean, 20.2 ms p95, and 31.6 ms max. Server-side socket backpressure
is therefore not the multi-second mechanism.

In the same run, page construction was 3.77 seconds mean (6.52 seconds p95),
outbox preparation was 241 ms mean (737 ms p95, 2.63 seconds max), and
`socketio.emit` was 137 ms mean (301 ms p95). Final-frame arrival was 10.25
seconds mean and 16.28 seconds p95. The remaining server-side tail is the
aggregate single-event-loop work before the ASGI writer: concurrent page
construction, NiceGUI element serialization, Socket.IO packet encoding, and
per-client outbox scheduling. The post-receipt mount interval remains partly a
shared-browser-generator artifact.

Further transport instrumentation has diminishing value. The smallest
architectural experiment now justified by evidence is to deliver the single
large document HTML payload outside NiceGUI's element/outbox serialization,
while leaving permissions, CRDT edits, presence, highlights, and sidebar
interaction unchanged.

## Phase 8: annotation-load round-trip collapse

Three folds with one mechanism removed round-trips and pool checkouts from
the cold annotation read path:

1. `resolve_annotation_context` now fetches workspace, template flag, the
   viewer's explicit ACL entry, and the Activity→Week→Course placement chain
   in one LEFT-JOIN statement. The workspace entity still carries
   `crdt_state` in that same read; no second checked-out read was introduced
   (the constraint extracted from the falsified 2026-04-23 metadata/CRDT
   split).
2. The active-export-job read rides the same session and returns on
   `AnnotationContext.active_export_job`; the header applies recovery from
   the prefetched value with no DB await inside the client slot. This is the
   "real fast path that avoids the DB work" named as the surviving option by
   the falsified 2026-04-24 export-recovery deferral note.
3. `list_documents_with_first_content` fetches the document headers and the
   full first document in one session; `_build_tab_panels` consumes the
   prefetched document instead of a `get_document` checkout inside the
   client slot.

For the single-document owner fixture the whole page load now executes 8 SQL
statements over 3 checkouts (previously ~10 over 5). Regression gates:
`test_annotation_context_query_count` ≤5, the new
`TestFirstDocumentFetchEfficiency` pair, and the page-load ceiling tightened
from 25 to 10.

### Measurement: six runs, two pools, alternating arms

All runs: 100 settled-authentication sessions, settle 16 s, server pinned to
CPUs 0-7, QueuePool direct to PostgreSQL (no PgBouncer), harness load gate
≤4. Baseline = HEAD with the change stashed; collapse = the change applied.
Runs 3-6 form an alternating B-A-B-A sequence at the production 20+10 pool.

| Pos | Arm | Pool | Page-build avg/p95 | Lag avg/p95 | Checkouts | Browser avg/p95 |
| --- | --- | --- | --- | --- | ---: | --- |
| 1 | baseline | 5+5 | 4610 / 7792 | 14 / 68 | 908 | 9019 / 12342 |
| 2 | collapse | 5+5 | 3876 / 7013 | 17 / 67 | 709 | 9733 / 13065 |
| 3 | baseline | 20+10 | 4154 / 7232 | 22 / 114 | 909 | 13647 / 16168 |
| 4 | collapse | 20+10 | 2764 / 5778 | 28 / 129 | 711 | 17729 / 21892 |
| 5 | baseline | 20+10 | 3685 / 6257 | 17 / 97 | 908 | 11425 / 13419 |
| 6 | collapse | 20+10 | 2589 / 4767 | 19 / 108 | 709 | 12819 / 14849 |

RSS during the wave was 1.09-1.18 GB in every run. Raw snapshots:
`perf-results/collapse-baseline-100*.json` and
`perf-results/round-trip-collapse-100*.json`.

### Supported

- **Server page construction improved robustly.** At 20+10 the collapse arm
  is 2589-2764 ms mean against a baseline arm of 3685-4154 ms (−32%); the
  between-arm gap is several times either arm's spread, and the direction
  replicates at 5+5. Header and tab-panel phases fell to 2 ms and ~44 ms.
- **Demand reduction is deterministic.** 709-711 checkouts per wave against
  908-909, every run, matching the designed −2 checkouts per load.

### Unresolved

- **The student-visible boundary did not measurably move.** Collapse browser
  means {17.7 s, 12.8 s} against baseline {13.6 s, 11.4 s}: the collapse
  arm's within-arm spread (4.9 s) exceeds the between-arm difference
  (2.7 s). Position 4's 17.7 s did not replicate. No improvement and no
  regression is resolvable at n=2 per arm on co-located browser generators.
- **Weak burst signal.** WebSocket-observed time is the one browser metric
  where both collapse legs (1451/1621 ms mean) sit above both baseline legs
  (990/1055 ms). A plausible mechanism: the baseline's serial DB awaits
  staggered per-client page completion, and removing them lands more
  serialization bursts on the event loop together. This is consistent with
  the Phase 7 finding that the tail is aggregate single-loop serialization,
  and is evidence for, not proof of, arrival sharpening.

### Methodology rule extracted

Browser-side numbers on this host vary by >2 s between identically
configured runs even under the load gate, and drift is not monotonic.
**Future performance claims require alternating or interleaved A/B legs
(B-A-B-A at minimum), reported per leg with within-arm spread; a single-order
pair is not evidence.** The Phase 7 same-process-HTTP conclusion should be
treated as provisional until reproduced under an order-reversed control.

### Housekeeping

- The `47a07fa6` "conditional transplant" flag in the design-note salvage
  ledger is closed: bab4218e is a line-for-line superset plus the owner
  shortcut. Only the statement-profile instrumentation (245e6ce6) remains
  untransplanted, deliberately.
- The three falsified load-experiment notes (db narrowing, prefetch outside
  client, export-recovery deferral) were branch-only in
  `nicegui-perf-investigation` and are now copied into `docs/dead-ends/`.
- Out of scope but surfaced for a human decision, ranked: `pool_pre_ping`
  costs one extra round-trip per checkout; `get_session` COMMITs read-only
  transactions; `is_user_banned` queries per page navigation with no cache;
  `user(is_admin)` has no index on the privileged union path (0.33 ms at
  2.2k users — likely never worth a migration).

Retain the collapse for the demand reduction and the server-side headroom it
returns to the event loop; do not cite it as a student-visible latency fix.
The student boundary remains owned by the Phase 6/7 line of work: delivery
of the large generated payload outside per-client element serialization.

## Phase 9: provisional in-process HTTP delivery result

A feature-gated experiment staged each already-authorized rendered document
behind a one-use 60-second token and fetched it from a raw HTTP endpoint in the
same NiceGUI process. The real one-session document/highlight/readiness boundary
passed. WebSocket bytes fell from about 730 KB to 294 KB, the largest frame
fell from 665 KB to 228 KB, and one-session readiness improved from 725 ms to
638 ms.

In one forward-order 100-session comparison, the candidate was substantially
worse:

| Metric | NiceGUI payload | Same-process HTTP |
| --- | ---: | ---: |
| Browser readiness mean | 13.73 s | 20.94 s |
| Browser readiness p95 | 16.60 s | 22.87 s |
| Server page-build mean | 3.77 s | 8.31 s |
| Server page-build p95 | 6.52 s | 15.45 s |
| Event-loop lag p95 | 75 ms | 224 ms |
| Event-loop lag max | 244 ms | 693 ms |
| RSS during wave | 1.18 GB | 1.11 GB |

All 100 clients still reached presence, and payload/memory reductions were
real. The timing comparison is order-confounded by the host variation described
in Phase 8 and must not be treated as a confirmed regression until an
order-reversed control reproduces it. The feature implementation was removed
because it did not satisfy the architectural goal of moving work off the
NiceGUI event loop; only its raw evidence is retained.

Any successor must prepare and serve the bundled initial snapshot from a
separate process (or native static/object service). The NiceGUI process may
issue a short-lived authorization token, but it must not build or transmit the
document, highlight, tag, and sidebar snapshot itself. One bundle is preferred
to several lazy requests; NiceGUI/WebSocket should carry only incremental CRDT,
presence, cursor, and interaction deltas after the initial mount.

## 2026-08-17 addendum: assessment-cram interaction ramp

Harness: `tests/e2e/test_assessment_cram_load.py` (clone-per-student chassis
plus a case-brief annotation pass: 10 highlights across the 10 tags, 3
comments, jittered 2 s think time) on the Narayan v R assessment template
(47 KB document, 14x smaller than PABAI). Flag off. One leg per step, no ABBA
— this is a load-shape curve, not a comparative claim. Co-located Chromium
generators; browser timings are not production client latencies. Raw evidence:
`perf-data/cram_n{25,50,75,100}.json`.

| n | page load p50 | highlight round-trip p50 / p90 | no-op retries | hard failures | RSS |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 25 | 1.3 s | 177 ms / 5.3 s* | 28/250 (11%) | 0 | 423 MB |
| 50 | 2.6 s | 178 ms / 1.3 s | 45/500 (9%) | 0 | 548 MB |
| 75 | 4.3 s | 199 ms / 2.4 s | 81/750 (11%) | 2 | 613 MB |
| 100 | 6.1 s | 1970 ms / 4.0 s | 69/1000 (7%) | 1 | 688 MB |

*p90 at n=25 is retry-inflated (5 s per-attempt wait); the underlying
successful round trip is sub-second at 25-75.

Findings:

1. **No crash by n=100.** All students loaded and reached readiness at every
   step (the small document avoids PABAI's 100-way readiness failure). RSS
   stayed under 700 MB.
2. **Interaction knee between 75 and 100:** highlight round-trip p50 jumps
   199 ms to 1970 ms. Page load grows linearly (~60 ms per session)
   throughout.
3. **Silent tag-click no-op at every load level (~7-11% of highlight
   actions).** The tag click depends on server-side `selection_start` set by
   a separate `selection_made` socket event (`document.py:35`); when the
   click is processed first, `_add_highlight` early-returns "No selection"
   (`highlights.py:215`) with no user feedback. Mechanism is plausible from
   code reading but not instrumented-confirmed (the annotation debug logger
   does not reach `test-perf.log`). Same event-reordering class as the
   value-capture pattern; the harness re-selects and clicks again (up to 3
   attempts), mirroring real student behaviour, and reports the retry count.
   Hard failures above are students whose three attempts all no-op'd during
   the load burst.
