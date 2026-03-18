# Investigation: Firefox E2E CI Failures

*Written: 2026-03-18*
*Status: Structural mechanisms identified in-repo; external CI corroboration still needs attached artifacts or retrieval commands before this should be treated as a closed incident record.*

## Evidence Boundary

- Confirmed in this repo copy: `tests/e2e/test_card_layout.py`, `src/promptgrimoire/static/annotation-card-sync.js`, `src/promptgrimoire/static/annotation-highlight.js`, `src/promptgrimoire/cli/e2e/_parallel.py`, `src/promptgrimoire/cli/e2e/_retry.py`, `tests/unit/test_cli_parallel.py`, `tests/unit/test_cli_e2e_runner.py`, and `git log d5f1d5ae..7ade6540`.
- External corroboration not preserved in this repo copy: GitHub Actions run IDs and timestamps, the cited `retry/pytest.log`, and the runner image string `ubuntu24/20260309.50`.
- Peer-review consequence: claims backed only by those external artifacts are marked below as corroborated or inferred, not locally confirmed.

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

**Claim:** The test helper is not causally coupled to the postcondition it needs. It waits for one `requestAnimationFrame`, but the test assertion depends on `positionCards()` having already assigned numeric `style.top` values.

**Evidence:**

The SPA-navigation portion of `tests/e2e/test_card_layout.py` waits for highlights, then waits one rAF, then reads `style.top`:

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

The helper itself is only:

```python
page.wait_for_function("new Promise(r => requestAnimationFrame(r))")
```

`src/promptgrimoire/static/annotation-highlight.js` marks highlights as ready before dispatching the event:

```javascript
window._highlightsReady = true;
document.dispatchEvent(new Event('highlights-ready'));
```

`src/promptgrimoire/static/annotation-card-sync.js` reacts to that event by scheduling `positionCards()` on a separate rAF:

```javascript
function onHighlightsReady() {
  // ...
  requestAnimationFrame(positionCards);
}
```

`_get_card_top()` then does `parseFloat(el.style.top)`. In the current tree, `positionCards()` is the only code path that assigns annotation-card `style.top`.

**What this proves:** `window._highlightsReady === true` and "cards have numeric `style.top` values" are distinct states. The helper waits on a timing proxy, not on the actual observable effect the test asserts against.

**Falsification:**

| # | Claim | Evidence | Experiment | Result |
|---|-------|----------|------------|--------|
| 1 | The ready flag is set before the `highlights-ready` event is dispatched | `src/promptgrimoire/static/annotation-highlight.js:162-164` | Read source | Confirmed |
| 2 | `onHighlightsReady()` schedules `positionCards()` on an independent rAF | `src/promptgrimoire/static/annotation-card-sync.js:98-107` | Read source | Confirmed |
| 3 | `_wait_for_position_cards()` waits on only one independent rAF | `tests/e2e/test_card_layout.py:49-51` | Read source | Confirmed |
| 4 | `_get_card_top()` parses inline `style.top`, so an unset value can surface as `NaN` | `tests/e2e/test_card_layout.py:31-45` plus JS semantics of `parseFloat("")` | Read source and language semantics | Confirmed |
| 5 | `positionCards()` is the only current annotation-card `style.top =` assignment | `src/promptgrimoire/static/annotation-card-sync.js:78`; `rg -n "style\\.top" src/promptgrimoire/static` | Source search | Confirmed |
| 6 | `_wait_for_position_cards()` is reused by non-SPA and multi-card tests too | `tests/e2e/test_card_layout.py:115,174,188,198,264,453,461` | Read source | Confirmed |
| 7 | No relevant files changed in `d5f1d5ae..7ade6540` | `git diff --name-only d5f1d5ae..7ade6540 -- tests/e2e/test_card_layout.py src/promptgrimoire/static/annotation-card-sync.js src/promptgrimoire/static/annotation-highlight.js src/promptgrimoire/cli/e2e/_parallel.py src/promptgrimoire/cli/e2e/_retry.py` | Run command | Confirmed |
| 8 | Firefox CI kept passing the non-SPA variant while the SPA variant failed | GitHub Actions logs for run `23221063582` | Not reproducible from this repo copy | Corroborated only |

**Epistemic boundary:**

- High confidence: the helper is structurally insufficient. It does not guarantee the state the assertion actually needs.
- Moderate confidence: this structural race is the main explanation for the Firefox-only `NaN` symptom.
- Inference, not local proof: Firefox and CI timing characteristics made the race observable more often. The code proves the race exists; it does not, by itself, prove a Firefox engine defect.
- Unverified in this repo copy: any claim tied to runner-image changes or exact GitHub Actions timing.

### Defect 2: the retry path drops `browser` before re-running failed files

**Claim:** When the parallel Firefox lane retries a failed file, the retry path drops `browser` and falls back to Chromium-default behaviour.

**Evidence (call-chain audit):**

```text
run_lane_files(browser=browser)
  -> _run_all_workers(..., browser=browser)
     -> _run_worker_for_lane(..., browser=browser)
  -> _finalise_parallel_results(...)
     -> _retry_parallel_failures(...)
        -> retry_failed_files_in_isolation(...)
           -> run_worker_for_lane(...)  # browser no longer present
```

The initial worker path is correct: `_run_worker_for_lane()` accepts `browser` and forwards it to the Playwright worker when the lane needs a server.

The retry path is not:

- `run_lane_files()` accepts `browser` at `src/promptgrimoire/cli/e2e/_parallel.py:475-483`.
- `run_lane_files()` forwards `browser` into `_run_all_workers()` / `_run_fail_fast_workers()` at `src/promptgrimoire/cli/e2e/_parallel.py:515-539`.
- `_run_worker_for_lane()` accepts and forwards `browser` at `src/promptgrimoire/cli/e2e/_parallel.py:78-96`.
- `run_lane_files()` then calls `_finalise_parallel_results()` without `browser` at `src/promptgrimoire/cli/e2e/_parallel.py:541-550`.
- `_finalise_parallel_results()` does not accept `browser` at `src/promptgrimoire/cli/e2e/_parallel.py:416-425`.
- `_retry_parallel_failures()` does not accept `browser` at `src/promptgrimoire/cli/e2e/_parallel.py:331-339`.
- `retry_failed_files_in_isolation()` calls `run_worker_for_lane()` without `browser` at `src/promptgrimoire/cli/e2e/_retry.py:203-210`.

**Why this escaped tests:**

- `tests/unit/test_cli_e2e_runner.py:598-767` verifies that `run_playwright_file()` and serial Playwright execution insert `--browser firefox` when asked.
- `tests/unit/test_cli_parallel.py:214-309` and `tests/unit/test_cli_e2e_runner.py:240-297` cover retry classification, but their fakes do not accept or assert a `browser` argument.
- The worker subprocess contract therefore had coverage; the retry orchestration contract did not.

**Falsification:**

| # | Claim | Evidence | Experiment | Result |
|---|-------|----------|------------|--------|
| 1 | `_run_worker_for_lane()` accepts `browser` and forwards it to Playwright workers | `src/promptgrimoire/cli/e2e/_parallel.py:78-96` | Read source | Confirmed |
| 2 | `_finalise_parallel_results()` does not accept `browser` | `src/promptgrimoire/cli/e2e/_parallel.py:416-425` | Read source | Confirmed |
| 3 | `_retry_parallel_failures()` does not accept `browser` | `src/promptgrimoire/cli/e2e/_parallel.py:331-339` | Read source | Confirmed |
| 4 | `retry_failed_files_in_isolation()` does not pass `browser` to `run_worker_for_lane()` | `src/promptgrimoire/cli/e2e/_retry.py:203-210` | Read source | Confirmed |
| 5 | Existing retry/finalise tests do not lock in browser propagation | `tests/unit/test_cli_parallel.py:214-309`; `tests/unit/test_cli_e2e_runner.py:240-297` | Read source | Confirmed |
| 6 | Firefox CI retries actually launched Chromium | Cited `retry/pytest.log` artifact | Not reproducible from this repo copy | Corroborated only |

**Epistemic boundary:**

- High confidence: the retry path is structurally broken for non-default browsers in the current tree.
- Moderate confidence: this defect contributed directly to the lane staying red, because an intermittent Firefox failure would be retried under the wrong browser.
- Unverified in this repo copy: the exact external retry log contents and browser executable path.

## Interaction Between the Defects

Defect 1 is the likely trigger for the `NaN` assertion. Defect 2 does not create `NaN`; it corrupts the retry/classification path after the initial Firefox failure occurs.

If Defect 1 is intermittent, Defect 2 can turn that intermittency into a consistently red lane because the retry never re-executes under the original browser. That is stronger, and more defensible, than saying Defect 2 "caused" the original card-positioning failure.

## Proposed Fixes

### Fix 1: wait for the actual postcondition, not for one frame

Replace the single-rAF wait with a poll that checks whether all currently rendered cards have numeric `style.top` values:

```python
def _wait_for_position_cards(page: Page) -> None:
    """Wait until rendered annotation cards have numeric ``style.top`` values."""
    page.wait_for_function(
        """() => {
            const cards = Array.from(
                document.querySelectorAll('[data-testid="annotation-card"]')
            );
            return cards.length > 0
                && cards.every(card => Number.isFinite(parseFloat(card.style.top)));
        }""",
        timeout=10000,
    )
```

This waits on the observable effect the tests actually use. It is also safer than checking only the first card, because `_wait_for_position_cards()` is reused by multi-card tests in the same file.

### Fix 2: thread `browser` through the retry chain and add missing regression tests

Add `browser: str | None = None` to `_finalise_parallel_results()`, `_retry_parallel_failures()`, and `retry_failed_files_in_isolation()`. Pass it through each call site until `_run_worker_for_lane(..., browser=browser)`.

Add regression tests before or with the implementation:

- In `tests/unit/test_cli_parallel.py`, assert that `_finalise_parallel_results(..., browser="firefox")` forwards `browser` to `_retry_parallel_failures()`.
- In `tests/unit/test_cli_e2e_runner.py`, assert that `retry_failed_files_in_isolation(..., browser="firefox")` forwards `browser` to `run_worker_for_lane()`.

## Fastest Next Tests

1. Patch only `_wait_for_position_cards()` and run `uv run grimoire e2e run -k "test_race_condition_highlights_ready" --browser firefox` repeatedly.
   Prediction if Defect 1 is the real trigger: the `NaN` assertion disappears without touching retry code.
   Prediction if Defect 1 is incomplete: Firefox still fails, which means `positionCards()` is sometimes not running or is returning early for another reason.

2. Add the two retry-path unit tests above, then patch browser threading.
   Prediction if Defect 2 is real: the new tests fail on the current tree and pass once `browser` is threaded end-to-end.

## Impact

- Fix 1 should remove the specific `NaN` path evidenced here by waiting on numeric card positions rather than on a timing proxy.
- Fix 2 should restore retry fidelity for non-default browsers and make flaky-vs-genuine classification meaningful again.
- If Firefox remains red after both fixes, treat that as evidence for a third issue rather than stretching either current defect beyond what the evidence supports.
