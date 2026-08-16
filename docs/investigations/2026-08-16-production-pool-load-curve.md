# Production-Pool Large-Document Load Curve

Date: 2026-08-16
Status: Reproduced; unacceptable latency growth and readiness failure unresolved
Branch: `large-document-performance-notes`
Harness commit: `c7589f56`

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
