# Investigation: Firefox E2E CI Failures

*Written: 2026-03-18*
*Status: Investigated. Two defects fixed (PR #385). Residual intermittent failure under investigation. Float leak identified.*

## Evidence Boundary

- **In-repo evidence:** Defect descriptions cite code as it existed before the fix commits. The broken code is accessible via `git show` at the pinned commits below; current HEAD contains the fixed versions.
- **CI diagnostics:** The JSON diagnostic outputs embedded in this document (§ Diagnostic Run, § Differential Diagnostic) are the preserved artifacts. They were captured from CI pytest logs downloaded via `gh run download`. The original GitHub Actions artifacts have a 90-day retention and may expire.
- **Confidence markers:** Claims derived from embedded JSON or `git show` are marked "Confirmed". Claims that depend on external CI state not preserved here are marked "Corroborated only".

### Key Commits

| Commit | Description |
|--------|-------------|
| `9c25516b` | fix(cli): thread browser through E2E retry chain |
| `fed92bc4` | fix(e2e): wait for positioned cards instead of single rAF |
| `e2737758` | test: add Biome JS lint gate, fix correctness errors |

## Symptom

External symptom report: the `e2e-playwright (firefox)` CI job started failing on `main` at approximately 2026-03-17 12:27 UTC, always on `tests/e2e/test_card_layout.py::TestCardPositioning::test_race_condition_highlights_ready`, while Chromium kept passing. That exact onset depends on GitHub Actions history that is not stored in this repository copy.

The locally confirmable failure mechanism is narrower: `test_race_condition_highlights_ready` reads `parseFloat(el.style.top)` and can therefore assert on `NaN` if card positioning has not yet run.

### Error

```text
tests/e2e/test_card_layout.py:270: in test_race_condition_highlights_ready
    assert top >= 0, f"Card top is negative after SPA navigation: {top}"
E   AssertionError: Card top is negative after SPA navigation: nan
E   assert nan >= 0
```

### Externally Reported Affected Runs

| Run ID | Branch | Firefox card_layout | Notes |
|--------|--------|---------------------|-------|
| 23186954765 | main (09:17 UTC) | PASS | Last known passing |
| 23194153933 | main (12:27 UTC) | FAIL | First observed failure |
| 23194737668 | main (12:43 UTC) | FAIL | |
| 23221063582 | main (23:21 UTC) | FAIL | Artifacts analysed below |

All run IDs, timestamps, and browser pass/fail summaries in this table are external corroboration. This repo copy does not preserve the underlying logs or the commands used to retrieve them.

## Contributing Factors

**Working causal chain:** a structurally racy test wait can produce `NaN` after SPA navigation, and a separate retry-path defect can then misclassify or harden Firefox failures by retrying under Chromium instead of Firefox.

### Defect 1: `_wait_for_position_cards` waits on an independent rAF, not on positioned cards

*Code as it existed before fix commit `fed92bc4`. View with `git show fed92bc4^:tests/e2e/test_card_layout.py`.*

**Claim:** The test helper is not causally coupled to the postcondition it needs. It waits for one `requestAnimationFrame`, but the test assertion depends on `positionCards()` having already assigned numeric `style.top` values.

**Evidence:**

The SPA-navigation portion of the test waits for highlights, then waits one rAF, then reads `style.top`:

```python
# SPA navigate away then back
page.goto(f"{app_server}/")
page.goto(f"{app_server}/annotation?workspace_id={workspace_id}")

# Wait for the highlights-ready flag set by annotation-highlight.js
page.wait_for_function("() => window._highlightsReady === true", timeout=10000)

# Cards must be positioned without any manual scroll
_wait_for_position_cards(page)

top = _get_card_top(page, 0)
assert top >= 0, f"Card top is negative after SPA navigation: {top}"
```

The helper (before `fed92bc4`) was:

```python
page.wait_for_function("new Promise(r => requestAnimationFrame(r))")
```

`annotation-highlight.js:162-164` marks highlights as ready before dispatching the event:

```javascript
window._highlightsReady = true;
document.dispatchEvent(new Event('highlights-ready'));
```

`annotation-card-sync.js:98-107` reacts to that event by scheduling `positionCards()` on a separate rAF:

```javascript
function onHighlightsReady() {
  // ...
  requestAnimationFrame(positionCards);
}
```

`_get_card_top()` does `parseFloat(el.style.top)`. `positionCards()` is the only code path that assigns annotation-card `style.top` (confirmed: `annotation-card-sync.js:78` is the sole assignment; `rg -n "style\\.top" src/promptgrimoire/static` finds no others).

**What this proves:** `window._highlightsReady === true` and "cards have numeric `style.top` values" are distinct states. The helper waits on a timing proxy, not on the actual observable effect the test asserts against.

**Falsification:**

| # | Claim | Evidence | Experiment | Result |
|---|-------|----------|------------|--------|
| 1 | The ready flag is set before the `highlights-ready` event is dispatched | `annotation-highlight.js:162-164` | Read source | Confirmed |
| 2 | `onHighlightsReady()` schedules `positionCards()` on an independent rAF | `annotation-card-sync.js:98-107` | Read source | Confirmed |
| 3 | `_wait_for_position_cards()` waits on only one independent rAF | `git show fed92bc4^:tests/e2e/test_card_layout.py` line 49-51 | Read source at pre-fix commit | Confirmed |
| 4 | `_get_card_top()` parses inline `style.top`, so an unset value can surface as `NaN` | `test_card_layout.py:35-46` plus JS semantics of `parseFloat("")` | Read source and language semantics | Confirmed |
| 5 | `positionCards()` is the only current annotation-card `style.top =` assignment | `annotation-card-sync.js:78` | Source search | Confirmed |
| 6 | `_wait_for_position_cards()` is reused by non-SPA and multi-card tests too | `test_card_layout.py:115,174,188,198,264,453,461` | Read source | Confirmed |
| 7 | No relevant files changed in `d5f1d5ae..7ade6540` | `git diff --name-only d5f1d5ae..7ade6540 -- tests/e2e/test_card_layout.py src/promptgrimoire/static/annotation-card-sync.js src/promptgrimoire/static/annotation-highlight.js src/promptgrimoire/cli/e2e/_parallel.py src/promptgrimoire/cli/e2e/_retry.py` | Run command | Confirmed |
| 8 | Firefox CI kept passing the non-SPA variant while the SPA variant failed | GitHub Actions logs for run `23221063582` | Not reproducible from this repo copy | Corroborated only |

**Epistemic boundary:**

- High confidence: the helper is structurally insufficient. It does not guarantee the state the assertion actually needs.
- Moderate confidence: this structural race is the main explanation for the Firefox-only `NaN` symptom.
- Inference, not local proof: Firefox and CI timing characteristics made the race observable more often. The code proves the race exists; it does not, by itself, prove a Firefox engine defect.
- Unverified in this repo copy: any claim tied to runner-image changes or exact GitHub Actions timing.

### Defect 2: the retry path drops `browser` before re-running failed files

*Code as it existed before fix commit `9c25516b`. View with `git show 9c25516b^:src/promptgrimoire/cli/e2e/_parallel.py` and `git show 9c25516b^:src/promptgrimoire/cli/e2e/_retry.py`.*

**Claim:** When the parallel Firefox lane retries a failed file, the retry path drops `browser` and falls back to Chromium-default behaviour.

**Evidence (call-chain audit at pre-fix commit):**

```text
run_lane_files(browser=browser)
  -> _run_all_workers(..., browser=browser)
     -> _run_worker_for_lane(..., browser=browser)
  -> _finalise_parallel_results(...)       # browser NOT accepted
     -> _retry_parallel_failures(...)      # browser NOT accepted
        -> retry_failed_files_in_isolation(...)
           -> run_worker_for_lane(...)     # browser NOT passed
```

**Falsification:**

| # | Claim | Evidence | Experiment | Result |
|---|-------|----------|------------|--------|
| 1 | `_run_worker_for_lane()` accepts `browser` and forwards it | `git show 9c25516b^:src/promptgrimoire/cli/e2e/_parallel.py` line 78-96 | Read source at pre-fix commit | Confirmed |
| 2 | `_finalise_parallel_results()` does not accept `browser` (pre-fix) | `git show 9c25516b^:src/promptgrimoire/cli/e2e/_parallel.py` line 416-425 | Read source at pre-fix commit | Confirmed |
| 3 | `_retry_parallel_failures()` does not accept `browser` (pre-fix) | `git show 9c25516b^:src/promptgrimoire/cli/e2e/_parallel.py` line 331-339 | Read source at pre-fix commit | Confirmed |
| 4 | `retry_failed_files_in_isolation()` does not pass `browser` (pre-fix) | `git show 9c25516b^:src/promptgrimoire/cli/e2e/_retry.py` line 203-210 | Read source at pre-fix commit | Confirmed |
| 5 | Existing retry/finalise tests do not lock in browser propagation (pre-fix) | AST analysis of test fakes | Automated analysis | Confirmed |
| 6 | Firefox CI retries actually launched Chromium | Cited `retry/pytest.log` artifact | Not reproducible from this repo copy | Corroborated only |

**Epistemic boundary:**

- High confidence: the retry path was structurally broken for non-default browsers at the pre-fix commit.
- Moderate confidence: this defect contributed directly to the lane staying red, because an intermittent Firefox failure would be retried under the wrong browser.
- Unverified in this repo copy: the exact external retry log contents and browser executable path.

## Interaction Between the Defects

Defect 1 is the likely trigger for the `NaN` assertion. Defect 2 does not create `NaN`; it corrupts the retry/classification path after the initial Firefox failure occurs.

If Defect 1 is intermittent, Defect 2 can turn that intermittency into a consistently red lane because the retry never re-executes under the original browser. That is stronger, and more defensible, than saying Defect 2 "caused" the original card-positioning failure.

## Applied Fixes (PR #385, merged 2026-03-18)

### Fix A: wait for the actual postcondition, not for one frame

`_wait_for_position_cards` now polls for numeric `style.top` on all cards instead of a single rAF. Commit `fed92bc4`.

### Fix B: thread `browser` through the retry chain

`browser=` now propagates through `_finalise_parallel_results` → `_retry_parallel_failures` → `retry_failed_files_in_isolation` → `run_worker_for_lane`. Two regression tests added. Commit `9c25516b`.

## Post-Fix Investigation: residual timeout on CI Firefox

Fixes A and B were merged. PR #384 (which rebased onto #385) still failed Firefox CI. Fix A changed the symptom from `NaN` to a 10-second timeout — `style.top` is never set within the poll window. Fix B was confirmed working: the retry now runs under Firefox (64s execution time, not 6s chromium crash).

### First Diagnostic Run (CI run 23227857034, Firefox only)

Instrumented `test_race_condition_highlights_ready` with read-only diagnostic capture. This run did NOT include `typeof setupCardPositioning` (a gap identified during review). Diagnostic JSON preserved below:

```json
{
  "viewport": { "w": 1280, "h": 720 },
  "docContainer": { "id": "doc-container", "rect": { "x": 92.8, "y": 220, "width": 738.3, "height": 470 } },
  "annContainer": { "id": "annotations-container", "rect": { "x": 855.1, "y": 220, "width": 332.1, "height": 470 } },
  "cardCount": 1,
  "cards": [{ "startChar": "4.0", "top": "", "offsetH": 26, "display": "", "position": "" }],
  "textNodes": { "length": 1, "firstAttached": true },
  "highlightsReady": true,
  "positionCardsFn": "undefined",
  "charOffsetRect": { "startChar": 4, "x": 185, "y": 247.1, "w": 8.8, "h": 18 }
}
```

Notable: `positionCardsFn: "undefined"`. This was initially interpreted as evidence that `setupCardPositioning()` was never called or that the script failed to load. That interpretation was **superseded** by the differential run below.

### Differential Diagnostic (CI run 23229612224, both browsers)

A deliberate-failure diagnostic captured state from both Chromium and Firefox in the same CI run. This run included `typeof setupCardPositioning` (closing the gap) and float integrity checks. Diagnostic JSON for both browsers preserved below.

**Firefox:**
```json
{
  "viewport": { "w": 1280, "h": 720 },
  "docContainer": { "id": "doc-container", "rect": { "x": 92.8, "y": 220, "width": 738.3, "height": 470 } },
  "annContainer": { "id": "annotations-container", "rect": { "x": 855.1, "y": 220, "width": 332.1, "height": 470 } },
  "cardCount": 1,
  "cards": [{ "startChar": "4.0", "top": "", "offsetH": 26, "display": "", "position": "" }],
  "textNodes": { "length": 1, "firstAttached": true },
  "highlightsReady": true,
  "setupCardPosFnDefined": "function",
  "positionCardsFn": "function",
  "charOffsetRect": { "startChar": 4, "x": 185, "y": 247.1, "w": 8.8, "h": 18 },
  "floatLeaks": [{ "attr": "startChar", "val": "4.0" }, { "attr": "endChar", "val": "21.0" }]
}
```

**Chromium:**
```json
{
  "viewport": { "w": 1280, "h": 720 },
  "docContainer": { "id": "doc-container", "rect": { "x": 92.8, "y": 220, "width": 738.3, "height": 470 } },
  "annContainer": { "id": "annotations-container", "rect": { "x": 855.1, "y": 220, "width": 332.1, "height": 470 } },
  "cardCount": 1,
  "cards": [{ "startChar": "4.0", "top": "27.3281px", "offsetH": 26, "display": "", "position": "absolute" }],
  "textNodes": { "length": 1, "firstAttached": true },
  "highlightsReady": true,
  "setupCardPosFnDefined": "function",
  "positionCardsFn": "function",
  "charOffsetRect": { "startChar": 4, "x": 185.0, "y": 247.3, "w": 8.8, "h": 16 },
  "floatLeaks": [{ "attr": "startChar", "val": "4.0" }, { "attr": "endChar", "val": "21.0" }]
}
```

### Cross-browser differential

| Property | Firefox | Chromium |
|----------|---------|----------|
| `setupCardPosFnDefined` | `"function"` | `"function"` |
| `positionCardsFn` | `"function"` | `"function"` |
| `cards[0].top` | `""` (empty) | `"27.3281px"` |
| `cards[0].position` | `""` (empty) | `"absolute"` |
| All other properties | Identical | Identical |

### What the differential proves

| # | Claim | Evidence | Confidence |
|---|-------|----------|------------|
| 1 | Scripts loaded on both browsers | `setupCardPosFnDefined: "function"` on both | Confirmed (embedded JSON) |
| 2 | `setupCardPositioning()` was called on both browsers | `positionCardsFn: "function"` on both — `window._positionCards` is assigned at `annotation-card-sync.js:91` inside `setupCardPositioning()` | Confirmed (embedded JSON + source read) |
| 3 | On Chromium, `positionCards()` has already run by the diagnostic sampling point | `top: "27.3281px"`, `position: "absolute"` | Confirmed (embedded JSON) |
| 4 | On Firefox, `positionCards()` has NOT run by the same sampling point | `top: ""`, `position: ""` | Confirmed (embedded JSON) |
| 5 | Card exists in DOM with non-zero height on both | `cardCount: 1`, `offsetH: 26` on both | Confirmed (embedded JSON) |
| 6 | `charOffsetToRect()` returns valid non-zero rect on both | Non-zero x, y, w, h on both | Confirmed (embedded JSON) |

### What the differential does NOT prove

- **That the difference is "purely rAF timing".** The differential shows that by the sampling point Chromium had run `positionCards()` and Firefox had not. It does not isolate whether the catch-up path in `onHighlightsReady()` fired, whether the `highlights-ready` event listener ran, or whether some other scheduling condition intervened. `window._positionCards` is assigned at `annotation-card-sync.js:91` *before* the listener registration at line 110 and the catch-up check at line 114, so its presence proves `setupCardPositioning()` executed past line 91 but does not prove lines 110-116 executed or that `onHighlightsReady()` was reached.
- **Why `positionCardsFn` was `"undefined"` in the first diagnostic run but `"function"` in the differential run.** Both ran on CI Firefox. Code changed between runs (Biome `parseInt` radix fixes in `annotation-card-sync.js`). Without reproducing the `"undefined"` state, the first run's finding is superseded by the differential.
- **Whether the failure is deterministic.** Across diagnostic runs: 2 failed (timeout), 2 passed. Intermittent.
- **Whether the timing difference is Firefox-specific or CI-load-specific.** The test passes locally on Firefox. Cannot distinguish browser behaviour from CI runner load without controlled experiments.
- **Whether production users are affected.** 700 students live, no card rendering reports. Production users navigate via NiceGUI routing, not Playwright's `page.goto()`.

### What the differential falsifies

**Falsified:** The first-run interpretation that `setupCardPositioning()` was never called or that `annotation-card-sync.js` failed to load on Firefox.

### Candidate mechanisms (not proven)

Given that `setupCardPositioning()` executed (setting `_positionCards`) but `positionCards()` has not run on Firefox by the sampling point:

1. **rAF deferral in headless Firefox.** Headless browsers may throttle `requestAnimationFrame` more aggressively than headed browsers, especially when no repaints are pending.
2. **Event listener registration race.** `setupCardPositioning()` registers its `highlights-ready` listener at line 110. The catch-up check at line 114 fires `onHighlightsReady()` immediately if `_highlightsReady` is already `true`. The diagnostic shows `_highlightsReady: true`, so the catch-up *should* have fired. But the presence of `_positionCards` only proves execution reached line 91, not line 114.
3. **MutationObserver not triggering.** The MutationObserver on the annotations container (line 103-104) also triggers `positionCards()` via rAF when cards are added. If NiceGUI adds the card to the DOM after the catch-up check, the MutationObserver's rAF may not have fired yet on Firefox.

## Float Leaks

Both Chromium and Firefox show `data-start-char="4.0"` and `data-end-char="21.0"` in the DOM. This is a cross-browser type fidelity issue originating in the Python→CRDT→DOM pipeline.

**Source chain:**

1. Client-side JS (`annotation-highlight.js:358-397`): `rangePointToCharOffset()` uses `tn.startChar + countCollapsed(...)` — integer arithmetic on integer fields from `walkTextNodes`. The `selection_made` event emits integer values.
2. NiceGUI event delivery (`document.py:30`): `e.args.get("start_char")` receives the value. JSON transport preserves integer types.
3. `_add_highlight()` (`highlights.py:246`): forwards `start_char=start` to `crdt/annotation_doc.py:225` which accepts `start_char: int`.
4. pycrdt stores the value in a CRDT Map.
5. On read, `highlight.get("start_char", 0)` at `cards.py:461` retrieves the value.
6. `f'data-start-char="{start_char}"'` at `cards.py:496` renders it into the DOM.

**Narrowed finding:** Steps 1-3 produce and transport integers. The float (`4.0` instead of `4`) most likely originates from pycrdt CRDT Map deserialisation (step 4→5). This has not been confirmed by runtime type check, but the client-side hypothesis is largely excluded by source analysis of steps 1-3.

**Impact:** `parseInt("4.0", 10)` returns `4` (correct). No current bug, but strict string comparison (`"4.0" !== "4"`) would fail. Defensive `int()` cast at `cards.py:461` would close this.

## Proposed Next Steps

1. **Float coercion fix** (independent, low-risk): add `int()` cast at `cards.py:461`.
2. **Investigate the rAF/catch-up path**: add diagnostic between lines 91 and 114 of `annotation-card-sync.js` to determine whether the catch-up path fires on Firefox CI.
3. **JS quality gate**: Biome lint added to pre-commit on branch `firefox-e2e-diag` (commit `e2737758`). `parseInt` radix and `Number.isNaN` correctness errors fixed. See #387 for JS unit test coverage.
