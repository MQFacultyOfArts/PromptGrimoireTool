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
