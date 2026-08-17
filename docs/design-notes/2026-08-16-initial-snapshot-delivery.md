# Initial annotation snapshot delivery from a separate process

Date: 2026-08-16
Status: go/no-go design for the Phase 9 successor; spike in progress
Prior evidence: `docs/investigations/2026-08-16-production-pool-load-curve.md`
(Phases 6-9), `docs/design-notes/2026-08-16-large-document-performance.md`

## Decision

Serve the initial annotation snapshot (document HTML, highlights, tag
metadata, sidebar items) as one JSON bundle from a standalone FastAPI/uvicorn
process that follows the export-worker lifecycle pattern. The NiceGUI process
resolves permissions exactly as today, mints a short-lived HMAC token, and
renders a skeleton page whose bootstrap JS fetches and mounts the bundle. The
NiceGUI process neither constructs nor transmits the bundle.

This is the constraint extracted from Phase 9: same-process HTTP delivery cut
payload bytes but left bundle construction and transmission on the NiceGUI
event loop, and the 100-way run degraded. A Starlette threadpool endpoint does
not escape either: paragraph injection and JSON serialisation are CPU-bound
Python and contend for the GIL.

## Boundary

- New standalone service, same stack and codebase, zero new dependencies:
  FastAPI app served by uvicorn, entry point mirroring
  `export/worker_main.py` (setup_logging, init_db, sd_notify, SIGTERM).
- Production routing: HAProxy path route on the existing frontend. Dev and
  test: the service runs on its own port; the bundle endpoint sends CORS
  headers for the app origin.
- The service imports only NiceGUI-free modules. The pure annotation
  functional core (`TagInfo`, `workspace_tags*`, `serialise_items`,
  `author_initials`) is relocated out of `pages/annotation/` (whose package
  `__init__` imports NiceGUI) into a NiceGUI-free module; the old locations
  re-export so no caller churns.

## Token

- Minted by the NiceGUI process only after `resolve_annotation_context`
  succeeds, i.e. after the full existing permission resolution. The service
  never widens access: it verifies signature and expiry, nothing else.
- Payload: workspace_id, document_id, user_id, viewer_is_privileged,
  can_annotate, anonymous_sharing, expiry. HMAC-SHA256 (stdlib `hmac`) keyed
  from the existing `APP__STORAGE_SECRET`, which both processes already share
  via config. Encoding: base64(JSON) + signature.
- TTL 60 seconds, stateless verification (presigned-URL model). Replay within
  the TTL yields the same read the same user is already authorised for;
  single-use would require shared state between the processes and is not
  bought by the threat model. HTTPS covers interception in production.

## Bundle

One JSON response per (workspace, document):

- `document_html`: `inject_paragraph_attributes(doc.content, paragraph_map)`
  — the CPU work and the 665 KB payload that currently dominate the outbox.
- `highlights`: the by-tag map consumed by `applyHighlights()`.
- `items`, `tag_options`, `permissions`: exactly what
  `sidebar.refresh_from_state` currently pushes as Vue props, built by the
  same `serialise_items` functional core.
- Sources: document and tags from the DB (matching the page's own
  `context.tags` authority); highlights from the workspace's persisted
  `crdt_state` hydrated into a throwaway `AnnotationDocument`
  (`apply_update`), the same pattern as `db/crdt_extraction.py`.

Freshness: `_persist_and_broadcast` force-persists on every mutation, so the
persisted CRDT trails the live registry by at most an in-flight mutation, and
the server-push-wins rule below heals any race after mount.

## NiceGUI page changes (feature-gated)

`SNAPSHOT__ENABLED` (default false) in a `SnapshotConfig` sub-model that
also carries the service base URL, bind port, and CORS origin. When
enabled, `_render_document_with_highlights`:

- renders the empty `doc-container` skeleton with a loading indicator
  instead of the `ui.html` document payload;
- skips the initial `sidebar.refresh_from_state` push (later refreshes are
  unchanged);
- emits bootstrap JS carrying the token and bundle URL instead of the inline
  highlight JSON.

Everything else stays: `extract_text_from_html` for `state.document_chars`,
highlight pseudo-CSS style element, tag toolbar elements, header, tabs,
selection handlers, presence, broadcast registration, CRDT writes.

## Client mount

Bootstrap JS fetches the bundle, sets the document container's innerHTML,
then runs the existing init sequence (`walkTextNodes`, `applyHighlights`
with bundle highlights, `setupAnnotationSelection`). The Vue sidebar gains a
bundle hook: rendering uses bundle items until the first genuine server
props push arrives, after which the server is authoritative and bundle state
is discarded (server-push-wins; a stale bundle can never clobber a fresher
push). Bundle application bumps `window.__annotationCardsEpoch` and the
per-document epoch so the existing E2E epoch contract holds. The
`annotation-ready` marker semantics are preserved: readiness follows bundle
mount, not skeleton render.

## Preserved invariants

- Authentication and authorization: token minted only downstream of the
  existing resolution; the service adds no new grant surface.
- CRDT authority and collaboration semantics: all writes, presence, cursors
  and deltas remain on the NiceGUI/WebSocket path, untouched.
- Document ordering, annotation behaviour, export and recovery paths:
  untouched.
- DOM/test contracts: `doc-container`, `annotation-ready`, sidebar epochs,
  all `data-testid` surfaces unchanged.

## Go/no-go criteria

Go requires, in order:

1. The one-session E2E boundary (document, highlights, sidebar items,
   annotation-ready) passes on the Pabai fixture with the flag on.
2. A 100-session ABBA comparison under the codified evidence contract
   (`docs/testing.md` § Manual Performance Lane) shows the browser-side
   boundary improving beyond within-arm spread, with server-side and
   browser-side verdicts reported separately.

No-go: if the boundary cannot be established without breaking the DOM/test
contracts or forking the sidebar component, or if the ABBA comparison shows
no browser improvement beyond within-arm variation, stop, keep the evidence,
and remove the feature path (the Phase 9 discipline).

## Spike order (TDD)

1. Relocate the annotation functional core to a NiceGUI-free module;
   existing unit tests keep passing unchanged.
2. Token mint/verify with expiry and tamper tests.
3. Bundle builder against a seeded workspace (integration lane).
4. FastAPI service app tested in-process via httpx ASGI transport; process
   entry point reuses the worker lifecycle.
5. Feature gate, bootstrap JS, sidebar bundle hook (vitest for the JS
   contract: bundle apply bumps epoch, server push wins).
6. E2E with the service as a managed subprocess, flag on, Pabai fixture.
7. ABBA performance runs; verdict recorded in the load-curve investigation.

## Phase 10: ABBA verdict (2026-08-17)

Four legs run 13:03–13:16 AEST on a coordinated quiet host (other sessions
held all test/e2e invocations for the window), 100 sessions per leg,
`E2E_AUTH_CLIENT_SETTLE_SECONDS=16`, `E2E_SERVER_CPU_LIST=0-7`,
`--queue-pool`. Candidate legs ran the snapshot service pinned to the same
CPU set. Every leg loaded 100/100 sessions. Raw evidence:
`perf-results/snapshot-{baseline,candidate}-100-pos{1..4}.json`.

`highlights_ready_ms` is the comparison boundary (`document_mounted_ms`
fires at skeleton-attach in snapshot mode and is not comparable):

| leg | arm | p50 | p95 | max | ws bytes p50 |
|-----|-----|-----|-----|-----|--------------|
| pos1 | baseline  | 11 040 | 12 611 | 12 686 | 729 863 |
| pos2 | candidate |  8 961 | 10 108 | 10 327 |  74 139 |
| pos3 | candidate |  9 273 | 10 406 | 10 572 |  74 139 |
| pos4 | baseline  | 11 603 | 13 596 | 13 722 | 729 863 |

- Within-arm spread: baseline p50 563 ms / p95 985 ms; candidate p50
  312 ms / p95 298 ms.
- Cross-arm delta: p50 −2 204 ms (−19%), p95 −2 846 ms (−22%) — roughly
  4× the baseline within-arm spread at p50, 3× at p95.
- Ordering check: the later baseline (pos4) is the slower one, so host
  drift over the window ran against the candidate, not for it; the
  candidate legs sat between the two baselines and beat both.

Browser-side verdict: **improvement beyond within-arm variation** —
criterion 2 met. Per-client WebSocket payload fell 730 KB → 74 KB (the
document frame left the outbox), and the candidate arm is also more
consistent (spread roughly halved at p50, tripled-down at p95).

Server-side verdict (reported separately): the element-tree/outbox relief
was established structurally in the earlier phases (`cards_ms` → 0.0, the
665 KB `ui.html` property gone); this run's per-client payload reduction is
the transport-level confirmation. The run's `during` snapshot captures pool
state only, not an event-loop lag series, so no fresh lag claim is made.

Caveat (failure-mode class G): browsers co-located with server and DB, so
absolute magnitudes are not production client latency. The claim is the
relative cross-arm comparison under identical harness conditions.

Validity check: another session disclosed post-hoc that its test runs
finished ~03:25 UTC. The legs ran 03:03–03:16 UTC with gapless
boundaries (each leg started the second the prior ended), and the
UID-wide test-run flock makes concurrent grimoire execution impossible
while a leg holds it — interleaving would have appeared as inter-leg
gaps. The disclosed runs therefore post-date the window; and the leg
nearest them (pos4) is the slower baseline, an error direction that
works against the candidate. Verdict unaffected.

**Verdict: GO.** Both criteria met. Remaining before graduation: freshness
race hardening (currently argued/structurally tested only), flag-on soak of
the wider E2E suite, deployment wiring for the service unit, and Brian's
UAT.
