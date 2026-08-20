# Soak and Cram Load Evidence — Initial Snapshot Delivery

Date: 2026-08-19 (PgBouncer-fidelity series and thundering herd added the
same evening; document rebuilt 2026-08-20)
Status: Evidence record, campaign complete. The PgBouncer-fidelity series in
Part 1 is the authoritative result; the earlier NullPool series is retained
in Part 2 as superseded history.
Branch: `perf/soak-full-crud` (perf worktree, uncommitted), at `e6fd6b20`
on `origin/main f7b3c2de` — **pre-#570**; see §9.
Harnesses: `tests/e2e/test_soak_full_crud_load.py` (paced soak),
`tests/e2e/test_assessment_cram_load.py` (synchronised cram),
`tests/e2e/test_thundering_herd.py` (synchronised arrival + churn on a
heavyweight fixture)
Data: `perf-data/*.json` on the run machine, one file per run. The raw
JSONs are per-event telemetry (per-action timings, diagnostic samples,
server load profiles — no document content) and are **not committed**:
they are large, and the numbers they hold are superseded by any rerun.
Each is regenerable in kind, not in value, via the named harness and
knobs (`scripts/perf-run.sh`). The five NullPool-era cram files that
main already tracks remain tracked.

## How to read this document

Part 1 is the PgBouncer-fidelity results. Every figure in it is derived
from a diagnostic JSON named in the `Evidence file` column, by re-reading
that file. Where a metric is not present in the file, the cell is `—`.
Nothing is carried over from a terminal session.

Part 2 is the earlier NullPool series, retained because its wall at n=100
is itself a finding about the harness, and because two of its caveats
(§3, §4) were established on its runs.

Part 3 records what the numbers do not say, ordered by how much each
caveat constrains a reading of the tables.

---

## Part 1 — PgBouncer-fidelity series (authoritative)

### Environment

Every run in this part went through a local PgBouncer on `127.0.0.1:6433`,
configured exactly as `docs/deployment.md` §7a documents production:
transaction pooling, `default_pool_size 40` + `reserve_pool_size 10`,
`max_client_conn 500`, `reserve_pool_timeout 3`,
`max_prepared_statements 200`. The application side matched §7b:
`DATABASE__POOL_SIZE=20`, `DATABASE__MAX_OVERFLOW=10`,
`DATABASE__POOL_PRE_PING=false` (required with transaction pooling —
SQLAlchemy #10226), `DATABASE__POOL_RECYCLE=1800`.

The server ran QueuePool via the `_PROMPTGRIMOIRE_POOL_FIDELITY` opt-in in
`db/engine.py::_resolve_pool_mode`, set by `grimoire e2e perf
--queue-pool`. **Verification is per-leg and server-side**: every JSON's
`server_page_load.pool_mode` block, parsed from the server's own startup
log line, reads `mode=QueuePool, reason="pool_fidelity"`. (The `run_meta`
env block records `_PROMPTGRIMOIRE_POOL_FIDELITY="0"` — that is the pytest
subprocess's value, deliberately zeroed so test-lane engines stay on
NullPool; the flag applies to the spawned server, and the server-side
observation is the one that counts.)

Other constants across every leg: server pinned to CPUs 0–7
(`E2E_SERVER_CPU_LIST`), admission gate disabled, G3+settle harness
(post-#566 drag code with `wait_for_scroll_settled`), and server-side
`page_load_profile` capture via `tests/e2e/perf_reporting.py` — the
`Server p50/p95/max` column that Part 2 could not fill. Coverage is
verified per leg: `window_start_covered=true` on every row below (the
first n=150 attempt lost its startup line to 10 MB log rotation and was
discarded and rerun with a 20 MB × 15 rotation budget — the knobs are
now `LOGGING__MAX_BYTES` / `LOGGING__BACKUP_COUNT`).

### Soak ramp, n=2 → 200

Paced soak: 5× = 3.25 actions/min per student, 15 min, 300 s arrival
spread (the n=2 shakedown is shorter). Browser figures are
browser-observed `load_elapsed_ms`; server figures are the server's own
`page_load_profile.total_ms` over the same loads.

| Run | Evidence file | n | Loads ok/att | Browser p50/p95 (ms) | Server p50/p95/max (ms) | Max DB hold (ms) | Max loop lag (ms) | Whiffs / drags | Fatal students | Respond audit (landed/lost/never-typed) |
|---|---|---|---|---|---|---|---|---|---|---|
| shakedown | `soak_pgb_shakedown.json` | 2 | 2/2 | 250 / 260 | 20.1 / 25.9 / 25.9 | 46 | 22 | 0 / 19 | 0 | 5 / 0 / 0 |
| soak n=25 | `soak_n25_pgb.json` | 25 | 25/25 | 206 / 225 | 20.8 / 31.6 / 42.0 | 151 | 41 | 0 / 508 | 0 | 150 / 0 / 66 |
| soak n=50 | `soak_n50_pgb.json` | 50 | 50/50 | 204 / 234 | 20.8 / 43.0 / 90.9 | 280 | 339 | 0 / 1005 | 0 | 302 / 0 / 132 |
| soak n=75 | `soak_n75_pgb.json` | 75 | 75/75 | 204 / 240 | 21.2 / 33.1 / 111.1 | 289 | 456 | 0 / 1493 | 0 | 427 / 0 / 214 |
| soak n=100 | `soak_n100_pgb.json` | 100 | 100/100 | 205 / 240 | 20.6 / 30.2 / 111.8 | 521 | 758 | 0 / 1982 | 1 | 518 / 0 / 295 |
| soak n=100, snapshot on | `soak_n100_snap_pgb.json` | 100 | 100/100 | 200 / 282 | 20.5 / 29.7 / 34.8 | 330 | 757 | 0 / 1981 | 2 | 519 / 0 / 295 |
| soak n=150 | `soak_n150_pgb.json` | 150 | 150/150 | 205 / 276 | 21.3 / 37.8 / 368.4 | 271 | 889 | 0 / 2956 | 1 | 738 / 0 / 467 |
| soak n=200 | `soak_n200_pgb.json` | 200 | 200/200 | 208 / 274 | 20.8 / 40.6 / 214.5 | 971 | 1274 | 0 / 3917 | 1 | 918 / 0 / 661 |

Readings:

- **Server page-load p50 is flat at 20.5–21.3 ms from n=2 to n=200.** At
  paced arrival on the light fixture, the connection wall that voided the
  NullPool n=100 leg (Part 2 §1) is simply gone: 200/200 loads at every
  scale, no `TooManyConnectionsError` anywhere in the series.
- **Zero whiffs across 13,861 drags** in the whole soak series — the #562
  settle fix (§3) holding at scale after the n=10 falsification soak.
- **Respond audit: `ok_lost=0` on every leg** — no run in this series lost
  a typed sentence from the CRDT. The `degraded_never_typed` counts (66 →
  661, rising with n) are Milkdown mounts that never became interactable
  (#565); no text was typed, so none was lost. See §9 for why these should
  collapse on a rebased rerun.
- **Event-loop lag maxima grow with n** (41 → 1274 ms) while server load
  p50 stays flat; the spikes are GC pauses, §6.
- The snapshot-on n=100 leg recorded `snapshot_served=244` for 100
  students — the service was serving re-fetches during the run, not just
  initial loads. Recorded as an observation; not investigated.

### Cram A/B, order-controlled (ABBA)

Synchronised cram: every student loads at once, waits on a barrier, then
runs 10 highlights + 3 comments with 2000 ms think time. Each scale ran
**A (flag off), B (on), B (on), A (off)** back-to-back; order is confirmed
by `run_meta.started_utc` in the files. Snapshot state is corroborated
per-leg by the server-side `snapshot_served` count (0 on every A leg;
equal to loads served on every B leg).

| Run | Evidence file | n | Loads ok/att | Browser p50 (ms) | Server p50/p95 (ms) | Max DB hold (ms) | Whiffs | Fatal students |
|---|---|---|---|---|---|---|---|---|
| n=50 A1 | `cram_n50_pgb_a1.json` | 50 | 50/50 | 2212 | 802 / 1336 | 935 | 0 | 0 |
| n=50 B1 | `cram_n50_pgb_b1.json` | 50 | 50/50 | 2444 | 762 / 1250 | 482 | 0 | 1 |
| n=50 B2 | `cram_n50_pgb_b2.json` | 50 | 50/50 | 2312 | 764 / 1161 | 456 | 1 | 2 |
| n=50 A2 | `cram_n50_pgb_a2.json` | 50 | 50/50 | 2182 | 728 / 1301 | 536 | 0 | 3 |
| n=100 A1 | `cram_n100_pgb_a1.json` | 100 | 100/100 | 4405 | 1260 / 2604 | 962 | 12 | 22 |
| n=100 B1 | `cram_n100_pgb_b1.json` | 100 | 100/100 | 4698 | 1600 / 2352 | 633 | 16 | 25 |
| n=100 B2 | `cram_n100_pgb_b2.json` | 100 | 100/100 | 4717 | 1293 / 2301 | 546 | 15 | 20 |
| n=100 A2 | `cram_n100_pgb_a2.json` | 100 | 100/100 | 4472 | 1440 / 2956 | 740 | 23 | 25 |
| n=200 A1 | `cram_n200_pgb_a1.json` | 200 | 200/200 | 18353 | 2305 / 5839 | 950 | 2 | 3 |
| n=200 B1 | `cram_n200_pgb_b1.json` | 200 | **196/200** | 15156 | 2897 / 4942 | 724 | 0 | 200 (barrier) |
| n=200 B2 | `cram_n200_pgb_b2.json` | 200 | 200/200 | 13814 | 1692 / 4603 | 931 | 4 | 6 |
| n=200 A2 | `cram_n200_pgb_a2.json` | 200 | 200/200 | 13077 | 1597 / 5373 | 978 | 0 | 1 |
| n=100 control (INFO log) | `cram_n100_pgb_info_control.json` | 100 | 100/100 | 4421 | 1278 / 2600 | 822 | 22 | 23 |

Readings:

- **No server-side snapshot win at any scale.** Server p50 pairs
  (A legs vs B legs): n=50, 802/728 vs 762/764; n=100, 1260/1440 vs
  1600/1293; n=200, 2305/1597 vs 2897/1692. The differences are within
  leg-to-leg noise and carry no consistent sign. The browser-observed
  −14 % from the single-A-single-B NullPool comparison (Part 2 §2) **does
  not replicate under order control** — browser p50 with the snapshot on
  is equal-or-slower at n=50 and n=100.
- **Run position dominates the browser column at n=200**: 18353 → 15156 →
  13814 → 13077 ms monotonically across positions 1–4 regardless of flag,
  which is exactly the run-position effect the ABBA design was adopted to
  expose. Browser deltas at this scale should not be attributed to the
  flag at all.
- **B1's 196/200 is the snapshot init-load hang (#573)**: four students
  hit the 120 s annotation-load timeout (`load_elapsed_ms=-1`,
  `annotation_loaded=false`), matching `snapshot_served=196`; the other
  196 then broke on the arrival barrier (collateral, so the fatal column
  reads 200). B2 served 200/200 cleanly — the tail is intermittent, one
  leg in two at n=200.
- **Cram failures anti-correlate with n**: 20–25 fatal students per leg at
  n=100 against 1–6 at n=200 (B1's barrier break aside). §8 covers the
  control leg and the surviving explanation (co-located browser CPU,
  class G).
- **Whiffs persist under simultaneous load** (up to 23/leg at n=100, ~2 %
  of highlight attempts) despite the settle fix that took the paced soak
  to zero. This is the #562 residual: a server-triggered scroll arriving
  after settle but mid-drag. §3.

### Thundering herd, n=150 on the heavyweight fixture

`tests/e2e/test_thundering_herd.py`: 150 students, each on their own clone
of the pabai workspace (190 annotation cards), double-barrier synchronised
arrival, then 4 free-running cycles of reload → organise → locate ×2 →
respond with 2000 ms think time. `locate` and `respond` failures are
degraded-nonfatal by design; `organise` and reload failures are fatal.
This reproduces the shape that historically crashed the server:
everyone opens the annotated judgment at once, then browses.

| Metric | Value (`herd_n150.json`) |
|---|---|
| First loads completed | 150/150 (none failed; slowest within the 120 s budget) |
| Browser first-load p50 / p95 / max | 18042 / 20116 / 20265 ms |
| Server page-load p50 / p95 / max (896 profiles, loads + reloads) | 2824 / 9611 / 17450 ms |
| Reload p50 / max (600 completed cycles) | 39063 / 134245 ms |
| Gate failures | **81/150** students (gate was max(3, 15) = 15) |
| Fatal action errors | 98 organise opens timed out at 30 s waiting for the first `organise-card` |
| Degraded-nonfatal errors | 334 locate, 61 respond (30 s timeouts) |
| Max DB hold / max loop lag | 14549 / 5537 ms |
| GC pauses (drained per 10 s diag sample) | max 4737 ms; 21 of 46 samples had a pause > 50 ms |
| ASGI 500s in the server log | 184 × `KeyError: 'REQUEST_METHOD'`, 8 × `KeyError: 'Session is disconnected'` (#572 — disconnect noise, not an app failure; see the issue) |

The server **drowned but did not die**: it served every first load and
kept serving throughout, at page-load costs two orders of magnitude above
the light fixture (p50 2824 ms vs ~21 ms). The dominant failure is the
organise tab's synchronous per-card render — failure-mode class E, now
measured (#575) — compounded by GC pauses to 4.7 s (#574, §6). At paced
arrival (the soak table above) none of this fires; the burst/heavyweight
combination is the trigger.

---

## Part 2 — NullPool series, superseded (2026-08-18 → 19 morning)

Everything in this part ran before the PgBouncer environment existed:
`grimoire e2e perf` forced `_PROMPTGRIMOIRE_USE_NULL_POOL=1`, so the app
opened a fresh PostgreSQL connection per checkout against a 97-slot
server. Figures here are retained as history; where they conflict with
Part 1, Part 1 stands.

### Harness generations

The soak harness went through three generations, and the generation
determines how a browser-side failure is classified:

| Gen | Action fields in JSON | Classification |
|---|---|---|
| G1 | `error`, `retries` | Every browser-side failure is fatal. No degradation bucket. |
| G2 | `error`, `retries`, `degraded` | Bounced actions retried, then degraded. |
| G3 | `error`, `degraded` | Single attempt per action; a browser-side failure degrades, it is not retried. |

The whiff classifier (`Harness bug (#562)`, from #566) first appears in a
run recorded 2026-08-18 18:19. Every run before that carries **no whiff
labelling at all**, so those cells read `n/c` (not classified); their
unlabelled whiffs sit inside the `degraded` count (G2/G3) or the fatal
count (G1).

**Excluded as shakedown or superseded calibration:** `soak_n1*.json`
(single-student #562 diagnostics), `soak_mech*.json` (scratchpad
mechanism probes), `soak_n25_dragfatal.json` and `soak_n25.json`
(calibration), `soak_snap_shakedown*.json` and
`soak_audit_shakedown.json` (n=2 shakedowns; the audit shakedown is cited
in §4), the 2026-08-18 cram ramp (`cram_n25/50/75/100.json`,
`cram_n25_think8s.json` — pre-#566 drag code), and `budget_dryrun.json`.

### Results (NullPool environment)

No run in this part recorded a server-side `page_load_profile`; every
latency figure is browser-observed.

| Run | Evidence file | Gen | n | Pacing | Snapshot | Loads ok/att | Browser p50/p95 (ms) | Max DB hold (ms) | Whiffs | Fatal students |
|---|---|---|---|---|---|---|---|---|---|---|
| soak n=25, strict gate | `soak_n25_strict.json` | G1 | 25 | 5×, 15 min, 300 s spread | off | 25/25 | 213 / 294 | 163 | n/c | 20 |
| soak n=25, degradation counted | `soak_n25_tailfatal.json` | G2 | 25 | 5×, 15 min, 300 s spread | off | 25/25 | 197 / 241 | 114 | n/c | 1 |
| soak n=50 | `soak_n50.json` | G3 | 50 | 5×, 15 min, 300 s spread | off | 50/50 | 197 / 225 | 252 | n/c | 46 |
| soak n=75 | `soak_n75.json` | G3 | 75 | 5×, 15 min, 300 s spread | off | 75/75 | 200 / 254 | 356 | n/c | 65 |
| soak n=100 | `soak_n100.json` | G3 | 100 | 5×, 15 min, 300 s spread | off | 100/100 | 203 / 301 | 863 | n/c | 81 |
| soak n=100, snapshot on | `soak_n100_snap.json` | G3 | 100 | 5×, 15 min, 300 s spread | on (filename only) | 100/100 | 214 / 343 | 770 | 34 (1.7 % of 1979) | 6 |
| soak n=50, 10× pace | `soak_n50_r10.json` | G3 | 50 | 10×, 15 min, 300 s spread | not recorded | 50/50 | 199 / 320 | 230 | 23 (1.5 % of 1545) | 2 |
| soak n=50, 20× pace | `soak_n50_r20.json` | G3 | 50 | 20×, 15 min, 300 s spread | off (log-corroborated, partial) | 50/50 | 202 / 274 | 581 | 38 (1.8 % of 2142) | 1 |
| cram n=50, flag off | `cram_n50_off.json` | cram | 50 | think 2000 ms, 10 hl + 3 comments | off | 50/50 | 2997 / 3057 | 903 | 3 | 2 |
| cram n=50, snapshot on | `cram_n50_snap.json` | cram | 50 | think 2000 ms, 10 hl + 3 comments | on (log-corroborated) | 50/50 | 2577 / 2636 | 459 | 7 | 1 |
| cram n=100, flag off | `cram_n100_off.json` | cram | 100 | think 2000 ms, 10 hl + 3 comments | off | 99/100 | 6370 / 7109 | 2182 | 0 (no action ran) | 0 (99 aborted at barrier) |
| cram n=100, snapshot on | `cram_n100_snap.json` | cram | 100 | think 2000 ms, 10 hl + 3 comments | on (log-corroborated) | 99/100 | 6245 / 6377 | 1242 | 0 (no action ran) | 0 (99 aborted at barrier) |
| falsification soak n=10, settle fix | `soak_falsify_n10.json` | G3+settle | 10 | 5×, 30 min, 60 s spread | off | 10/10 | 197 / 235 | 91 | **0 of 354** (prediction: 0 — confirmed) | 1 |

---

## Part 3 — Honest caveats

### 1. The NullPool wall was the harness, and the rerun proves it

Part 2's n=100 cram legs both collapsed at a connection ceiling:
`grimoire e2e perf` forced NullPool, a hundred simultaneous cold loads
wanted a hundred PostgreSQL connections against 97 usable slots, one
student's load failed with `TooManyConnectionsError`, and the barrier
broke for the other 99 before any action ran. Those two files say nothing
about the snapshot in either direction.

The PgBouncer-fidelity rerun (Part 1) removes the wall exactly as the
production-shaped pooling predicts: transaction pooling turns refusal into
queueing, and 200/200 loads succeed at every scale in both harness
shapes, with cram n=200 server p50 around 1.6–2.9 s. Every figure quoted
from this campaign should come from Part 1.

### 2. The snapshot verdict reversed under order control

Part 2 §2 reported a browser-observed −14 % page-load win at n=50 from a
single A followed by a single B, and flagged run-position variation as the
reason to distrust it. The ABBA reruns settle it: **no server-side win at
any scale, and the browser-side win does not replicate** (snapshot-on legs
are equal-or-slower at n=50 and n=100; at n=200 run position swamps the
flag entirely). Against no measured win now sits a measured cost: the
intermittent init-load hang tail at n=200 (#573), four students in one leg
of two hanging past 120 s with `snapshot_served=196` confirming four
bundles never delivered. Whether the snapshot feature earns its place is a
design conversation, not a perf question, and it is parked in #573.

### 3. The #562 whiff race: harness side fixed and falsification-confirmed; app side remains

Established in `scratchpad/comment_562_repro.md` and
`scratchpad/whiff_repro_findings.md`, from an isolated perf-marked probe
with a single idle browser.

The whiff is a smooth scroll landing between `mouse.down()` and
`mouse.up()`. Once the viewport shifts mid-drag, the anchor is reset to
the focus on every pointer move and the selection never opens. The
evidence that fixes the mechanism is a pair of conditions differing only
in timing: the same `scrollBy` followed immediately by a drag whiffed 15
of 100, and the same scroll with a 700 ms settle whiffed 0 of 100. Two
standing suspects were refuted along the way — the candidate character
ranges whiffed 0 of 140 each when the page was already parked, and drags
at deliberately displaced coordinates (`dy` from −24 to +24 px, 147
drags) whiffed 0 of 147, selecting the *wrong* text rather than nothing.

It is reachable through shipped UI. The `locate-btn` on every annotation
card round-trips to the server, which answers with
`scrollToCharOffset(...)` → `window.scrollTo({behavior: 'smooth'})`.
Clicking that button and then dragging across body text whiffed 5 of 40
at a 60 ms delay, and 0 of 40 at both 0 ms and 900 ms — controls that
hold the click, the double-click window and the coordinates fixed.

It is **not silent**. `window._annotSel` stays null, the highlight menu
does not appear, and clicking a tag then trips
`_validate_highlight_state` → `ui.notify("No selection", warning)`. A
student loses a gesture and gets a confusing toast, not work.

The harness-side fix (`wait_for_scroll_settled()` in
`src/promptgrimoire/docs/helpers.py`, called from `scroll_to_char` and
`select_chars` before coordinates are re-read) was tested by
falsification: the mechanism predicts zero whiffs from harness-initiated
scrolls, and the n=10 falsification soak delivered **0 whiffs across 354
drags** (`soak_falsify_n10.json`); the PgBouncer soak series then held
**0 across 13,861 drags** at up to n=200. Against the 1.5–1.8 % G3 band,
those zeros are not flukes. Confirmed.

**The residual is the app side.** The PgBouncer cram legs still whiff —
up to 23 per leg (~2 % of highlight attempts) at n=100 — because under
simultaneous load a *server-triggered* scroll can arrive after the settle
check and land mid-drag, which no amount of harness waiting can exclude.
The app-side design call (cancel the smooth scroll on `mousedown`, or
switch `scrollToCharOffset` to `behavior: 'instant'`) has been raised and
not decided. Student incidence remains unmeasured, and all evidence is
Chromium-only.

### 4. Respond text was not lost; the Milkdown mount is a separate defect

The marker audit reads each student's workspace back out of the CRDT
after a run and classifies every typed marker. The falsification soak was
the first evidence run whose audit verdict is written into its JSON
(`ok_landed=78, ok_lost=0, degraded_never_typed=83`), and **every
PgBouncer soak leg carries one: `ok_lost=0` on all eight rows of Part 1**
(3,577 landed sentences across the series, zero lost). The earlier r20
run's audit verdict (325/325 landed) is documented in session notes only;
the artefact predates the JSON block.

The earlier appearance of "lost" text was an artefact of the audit
method: the harness clicked the centre of the editor before typing, so
the caret spliced new sentences into old ones and broke the marker being
counted. The `Control+End` caret fix in `_do_respond_type` removed the
splice.

The `degraded_never_typed` counts are the Milkdown mount defect (#565):
the editor's `[contenteditable]` never becomes interactable within 30 s,
no text is typed, so degraded responds are lost student time, not lost
work. In the NullPool runs the share rose with pace (37 % at n=100 5×,
52 % at n=50 10×, 66 % at n=50 20×); in the PgBouncer soak it rose with n
(66 of 216 at n=25 to 661 of 1579 at n=200). **PR #570 (merged
2026-08-19) is the fix for #565**, and it is *not* in the code under
test — see §9.

### 5. Throughput attainment replaced the stall assert

The old gate asserted that every student complete at least half its paced
budget, and fired on the 20× run exactly where it should not have: at 20×
pace, 30 s Milkdown timeouts eat real time, so a legitimate student
*should* fall short of budget. The assert measured the pace, not a fault.

The measurement is now per-student attainment against the paced budget,
reported every run as min/p50/max and never masked. Recomputed from the
NullPool JSONs (attempted = succeeded or degraded):

| Run | Budget | Attainment min / p50 / max |
|---|---|---|
| `soak_n25_tailfatal.json` | 49 | 72 % / 86 % / 103 % |
| `soak_n50.json` | 49 | 57 % / 82 % / 96 % |
| `soak_n75.json` | 49 | 57 % / 82 % / 101 % |
| `soak_n100.json` | 49 | 2 % / 82 % / 103 % |
| `soak_n100_snap.json` | 49 | 70 % / 88 % / 107 % |
| `soak_n50_r10.json` | 98 | 53 % / 74 % / 89 % |
| `soak_n50_r20.json` | 195 | 41 % / 50 % / 70 % |

`MIN_ACTION_FRACTION = 0.25` is a wedge guard, not a performance target:
a student under a quarter of budget is a browser that stopped recording.
The 2 % minimum in `soak_n100.json` is what such a wedge looks like. The
fatal-student gate is `max(3, n // 10)` — about spread, not run size —
and the cram gate was reshaped the same way during the campaign: failures
print as data (`reported, not fatal`) and only a collapse past the same
`max(3, n // 10)` boundary fails the run.

### 6. GC pauses are the event-loop stalls (#574)

Convicted by instrumentation added during the campaign: a `gc.callbacks`
pause recorder in the e2e server script, drained per diagnostic sample
via `/api/test/diagnostics`.

- **Herd n=150** (`herd_n150.json`): pauses to **4737 ms**, in lock-step
  with the lag series — gc 4475 ↔ lag 4720 ms, gc 4737 ↔ lag 5537 ms,
  gc 3848 ↔ lag 3953 ms; 21 of 46 samples carried a pause > 50 ms.
  Every lag spike above ~2 s sits on a same-sized GC pause. Below
  ~1.6 s the conviction narrows: five samples show 0.6–1.6 s lag maxima
  with no notable GC pause, a residual consistent with the synchronous
  per-card render work of §7.
- **Soak n=200** (`soak_n200_pgb.json`, light fixture): rarer spikes —
  13 samples above 200 ms in 21 min, maxima 594 → 887 → 1040 → 1274 ms,
  growing monotonically as RSS climbed 950 → 1235 MB. This run predates
  the GC instrumentation, so the mechanism is inferred from the herd's
  direct measurement plus the RSS correlation, not measured here.

During a pause every connected client freezes, and in production the
admission gate's AIMD would read the lag as overload and shrink the cap.
Candidate levers (generation thresholds, `gc.freeze()` after startup,
periodic `gc.collect(1)`) are in #574; any fix validates against the
`gc` block now present in perf diag JSONs.

### 7. Class E is now measured (#575)

CLAUDE.md's failure-mode class E — per-item synchronous UI loops during
initial render — was known-but-unmeasured since April. The herd measured
it: **98 organise-tab opens timed out at 30 s** waiting for the first
`organise-card` to render, the dominant fatal failure of the run (81/150
students), on a workspace of 190 cards under 150-way concurrency. Server
page loads for the same workspace cost p50 2.8 s / p95 9.6 s against
~21 ms for the light fixture. The April prescription (bulk `ui.html`
emission or interaction-deferred construction) is the direction; #575
carries it.

### 8. The n=100/n=200 failure anti-correlation is the co-located harness, not logging

Cram fatal students run 20–25 per leg at n=100 but 1–6 at n=200 — more
browsers, fewer failures. The n=100 legs ran under the old hardcoded
DEBUG file logging and the n=200 legs under the new INFO default, so
logging density was a live confound. The control leg
(`cram_n100_pgb_info_control.json`: n=100, flag off, INFO logging,
otherwise identical) came back at **23 fatal students — squarely in the
DEBUG band** — refuting the logging hypothesis.

The surviving explanation is failure-mode class G: 100 or 200 Chromium
instances share the host with the server, and the per-browser CPU
starvation profile differs with n in ways that move browser-side 30 s
action timeouts. This is stated as the best remaining hypothesis, not a
measured mechanism; the split rig (§10) is the instrument that would
test it.

### 9. Everything here describes pre-#570 code

The perf branch sits at `e6fd6b20` on `origin/main f7b3c2de`, and **PR
#570 — the #565 Milkdown mount fix — merged after the campaign's code was
frozen**. Every Milkdown-degradation figure in this document
(`degraded_never_typed` counts, the 30 s respond timeouts in the herd,
the pace/scale trends in §4) describes code without that fix and should
collapse on a rebased rerun. Treat those figures as the "before" of a
before/after pair whose "after" has not been run. The rebase decision
belongs to the PR conversation.

### 10. Harness caveats

**Co-located browsers (class G).** Every run put the Chromium load
generators, the application server and PostgreSQL on the same 32-core
host (server pinned to CPUs 0–7 in the PgBouncer series). Browser-observed
latency carries the browsers' own CPU contention — the herd's 18 s
browser-side first loads against 2.8 s server-side p50 is the clearest
case: the gap is mostly browser starvation, not server time. The server
columns in Part 1 are the production-magnitude claims; the browser
columns are not. A split rig (server on a separate box, harness-side
`E2E_PERF_SERVER_URL` support already built) is prepared but had not run
by the end of the campaign.

**The settle fix costs wall-clock.** `wait_for_scroll_settled` resolves
no sooner than two animation frames and is called twice per
`highlight_create`, so post-fix runs do strictly more waiting per drag
than pre-fix runs. The direction is certain; no magnitude was measured.

**Serialisation.** The perf lane holds a host-wide lock and requires four
consecutive 15-second samples at load ≤ 4.0 before starting, so runs did
not overlap. The PgBouncer cram legs additionally controlled order
(ABBA). No `act`/CI jobs ran on the host during any leg.

**Exit codes.** Historical exit-1s in Part 2 were the old cram boundary
assert and the old 20× stall assert (§5); both gates have since been
reshaped to report rather than fail below the collapse boundary.

---

## What would change the tables

1. **A rebased rerun on top of #570** — the Milkdown-degradation class
   (§4, §9) should collapse; if it does not, #565 is not fully fixed.
2. **The split rig** (server on the prepared second box) — removes class
   G from the browser columns, tests §8's hypothesis, and enables the
   knee hunt: step herd n by 25 until the server actually falls over.
3. **GC tuning** (#574) validated by the `gc` diag block — should flatten
   the lag maxima column of the soak table and cut the herd's multi-second
   stalls.
4. **Class E render work** (#575) — should turn the herd's 98 organise
   timeouts and the 0.6–1.6 s non-GC lag residual (§6) into measurable
   improvements at the same scale.
