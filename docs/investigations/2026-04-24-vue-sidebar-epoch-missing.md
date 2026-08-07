# Vue sidebar `__annotationCardsEpoch` never fires on initial mount

Date: 2026-04-24
Investigator: Claude (claude-opus-4-7)
Status: Reviewed (peer review findings addressed)
Branch: `nicegui-perf-a1-a2` (reproducible; branch does not touch the path)

## Summary

The four tests in `tests/e2e/test_vue_sidebar_cross_tab.py::TestVueSidebarCrossTab`
fail at fixture setup with `Page.wait_for_function: Timeout 30000ms exceeded`
on `() => (window.__annotationCardsEpoch || 0) >= 1`. The nightly `e2e slow`
workflow has been red on these tests for every run since the tests were
introduced (2026-04-04 via commit `38036821`, PR #457): 20 consecutive
failures since introduction as of 2026-04-23 (20/20 since 2026-04-04; 23/26
in the visible 26-run history; the 3 successes all predate the test's
introduction). Fixing this bug is necessary but not sufficient to turn
the nightly green — recent runs also show independent failures in the
integration lane (xdist `FileNotFoundError` in export-job tests) that are
out of scope for this investigation.

Cause (plausible; see Finding 3 below for the H1/H2 distinction that
this investigation does not conclusively discriminate): the Vue sidebar's
`watch(() => props.items, …, { deep: true, flush: 'post' })` at
`src/promptgrimoire/static/annotationsidebar.js:268-283` has no
`immediate: true`. By the time the page finishes loading, no callback
has ever fired — `window.__annotationCardsEpoch` remains `undefined`
on cold page load. The fixture's `>= 1` wait fails deterministically
(20/20 observed failures since the test was introduced).

The product itself is fully functional on that page: 190 cards render,
`position: absolute` and `top: 2363.62px` are applied, `_highlightsReady`
is true. Only the *synchronisation signal* is broken.

Fix (verified on production page path): add `immediate: true` to the watch
options at `annotationsidebar.js:282`. Before: 4 tests error at fixture
setup; 136 s for 1 test + 3 reruns. After: 4 tests pass in 20.37 s with
no reruns (`test-playwright-latexmk.log`).

This is a pending **working-tree** modification — no committed changes
to these paths on `nicegui-perf-a1-a2` vs `main`; `git diff main..HEAD -- <…>`
on the Vue-sidebar path is empty. The fix will be a new commit.

## Causal chain

1. `tests/e2e/test_vue_sidebar_cross_tab.py:78` — the `pabai_page` fixture
   waits up to 30 s for `window.__annotationCardsEpoch >= 1` before yielding
   the page. This wait gates every test in the class.
2. `src/promptgrimoire/static/annotationsidebar.js` writes `window.__annotationCardsEpoch`
   in exactly one place (line 273), inside the callback of
   `watch(() => props.items, …)` at line 268. (Line 277 writes the
   per-doc `window.__cardEpochs[doc_container_id]` entry using the same
   scalar value. `grep -n __annotationCardsEpoch src/` returns lines 273
   and 277, both inside this one callback.)
3. The watch options are `{ deep: true, flush: 'post' }` — no
   `immediate: true`.
4. Vue 3 documents watch as lazy by default: "the callback won't be
   called until the watched source has changed."
   (https://vuejs.org/api/reactivity-core.html#watch)
5. *Inference* (not directly demonstrated; see Finding 3 below): in the
   Python render path (`pages/annotation/document.py:540,554`), the
   sidebar is created with `items=[]` and then
   `sidebar.refresh_from_state(state)` is called on the same synchronous
   render tick, which mutates `self._props["items"]` to the full list and
   calls `self.update()`. Both mutations happen before the page HTML is
   serialised to the client, so Vue *probably* mounts with `props.items`
   already populated. An observationally equivalent alternative (NiceGUI
   custom-component prop propagation breaks reactive watchers on
   array-replace, even for post-mount mutations) would produce the same
   symptom and is not excluded by current evidence. Both alternatives
   are treated by `immediate: true`.
6. Therefore, on cold page load, the watch callback never runs, the epoch
   stays `undefined` (`/tmp/vue-sidebar-diag-prefix.json`: both probes
   `epochScalar: null, cardCount: 190`), and the fixture's `>= 1` wait
   fails deterministically at 30 s (20/20 observed failures in nightly CI
   since the test was introduced).

## Evidence grading

| # | Finding                                                                 | Grade        | Positive border                                                                                                  | Negative border                                                                                                                            | Upgrade path                                                      |
|---|-------------------------------------------------------------------------|--------------|------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------|
| 1 | Fixture times out on cold page load                                     | Demonstrated | Reproduced locally (136 s, 4 errors on same test; traceback at `test_vue_sidebar_cross_tab.py:78`); 20/20 nightly runs since test introduction on 2026-04-04 | Fix makes the same fixture pass in 6–20 s on the same worktree, same DB, same harness                                                      | —                                                                 |
| 2 | `window.__annotationCardsEpoch` never becomes `>= 1` on cold page load   | Demonstrated | `/tmp/vue-sidebar-diag-prefix.json` (pre-fix): both probes `epoch_fired=false, epochScalar=null, cardCount=190`  | Post-fix re-run (see cards-with-fix evidence below): `epochScalar=1` in place of `null`                                                    | —                                                                 |
| 3 | Vue 3 `watch` without `immediate: true` does not fire on initial mount   | Plausible    | Vue 3 docs + observed `epochScalar: null` with root mounted and items populated                                  | `immediate: true` causes `epochScalar: 1`; positive border shown. **Not uniquely discriminated from H2** (NiceGUI custom-component prop propagation breaking reactive delivery on array-replace). Both H1 and H2 are fixed by `immediate: true`. | Run a Python-side post-mount `sidebar.set_items(new_list)` via the mutation event path with `immediate: false`; if watch fires, H1; if not, H2. Not run in this investigation. |
| 4 | The epoch scalar is emitted in exactly one place                        | Demonstrated | `grep __annotationCardsEpoch src/` returns lines 273 and 277 of `annotationsidebar.js`; line 273 is the single write to the scalar, line 277 copies that value to the per-doc map | No other grep match                                                                                                                        | —                                                                 |
| 5 | `immediate: true` fixes the failing fixture + 4 tests                    | Demonstrated | 4 tests PASS in 20.37 s after the change (`test-playwright-latexmk.log`; 4 passed, 230 deselected)              | Fixture timed out deterministically without the change, same worktree, same DB, same harness                                              | —                                                                 |
| 6 | Branch `nicegui-perf-a1-a2` is not the cause                            | Demonstrated | `git diff main..HEAD -- <relevant paths>` returns zero semantic diff (the proposed fix is a pending working-tree edit, not a committed change on this branch) | Test added on commit `38036821` (pre-branch, 2026-04-04); nightly has failed since that date                                               | —                                                                 |
| 7 | Delta-based epoch consumers are unaffected by `immediate: true`          | Plausible    | Enumerated consumers reviewed: `tests/e2e/card_helpers.py::add_comment_to_highlight`, `tests/e2e/test_browser_perf_377.py`, and `scripts/profile_workspace.py` (all use `epoch_before → wait > epoch_before`, invariant to initial epoch value) | Cards lane run with fix, saved to `/tmp/cards-with-fix.log`; without fix saved to `/tmp/cards-without-fix.log.bak` / `/tmp/cards-without-fix-pytest.log`. See below for read-off. `test_browser_perf_377` is marked `perf` and not exercised by any lane the nightly runs; `profile_workspace.py` is a standalone script, not in any lane. | A NiceGUI-lane unit test that asserts watch behaviour on post-mount mutation; see Hardening suggestion for the correct location. |

## Claim verification (Toulmin)

| # | Claim                                                                               | Data (differential)                                                                             | Falsification experiment                                                                  | Result                                                        |
|---|-------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------|---------------------------------------------------------------|
| 1 | The fixture's `>= 1` wait is what times out                                         | `test-playwright-latexmk.log`: "tests/e2e/test_vue_sidebar_cross_tab.py:78: in pabai_page"     | Read line 78 + run fixture                                                                | Not yet falsified (matches traceback and source)              |
| 2 | The epoch is never set on cold page load                                            | `/tmp/vue-sidebar-diag-prefix.json`: both probes `epochScalar: null, cardEpochs: null`         | JS evaluate after 10 s wait-for-function timeout                                          | Not yet falsified                                             |
| 3 | Sidebar Vue component IS mounted and cards IS rendered                              | `rootPresent: true`, `cardCount: 190`, `firstCardStyles.position = "absolute"` (same snapshot) | DOM queries at same moment                                                                | Not yet falsified                                             |
| 4 | No code path other than the watch writes the scalar epoch                           | `grep -n __annotationCardsEpoch src/` → lines 273 and 277 of `annotationsidebar.js`, both in the one watch callback | grep + read                                                                               | Not yet falsified                                             |
| 5 | Adding `immediate: true` makes the probe pass                                       | diagnostic pre-fix: epoch_fired=false, epochScalar=null; post-fix: epoch_fired=true, epochScalar=1 | Single-line edit + re-run probe                                                           | Not yet falsified                                             |
| 6 | The four cross_tab tests pass with the fix                                          | `test-playwright-latexmk.log`: 4 passed, 230 deselected in 20.37 s                             | Run the cross_tab file with the fix in place                                              | Not yet falsified                                             |
| 7 | Branch `nicegui-perf-a1-a2` is not responsible for the failure                      | `git diff main..HEAD -- <relevant paths>` → empty                                              | git diff                                                                                  | Not yet falsified                                             |
| 8 | The 3 non-failure nightly runs all predate the test's introduction                  | Test added 2026-04-04; the 3 non-failure runs are on 2026-03-30, 2026-03-31, 2026-04-02 (all before introduction) | `gh run list` + `git log`                                                              | Not yet falsified                                             |
| 9 | The cards lane's `test_transition_to_compact_on_fifth_tag` teardown hang is preexisting | Running `grimoire e2e cards` on this worktree reproduces the hang at the same test WITH and WITHOUT the fix applied (`/tmp/cards-without-fix.log.bak`, `/tmp/cards-with-fix.log`) | Run cards lane with fix, revert, re-run cards lane without fix                           | Not yet falsified                                             |
| 10 | No delta-based epoch consumer regresses with the fix applied                       | See Finding 7; cards lane results captured to `/tmp/cards-with-fix.log` + per-test pytest log  | Diff pass/fail of identical cards lane with and without fix                              | See post-run read-off below                                   |

## Epistemic boundary

- **Demonstrated:** findings 1, 2, 4, 5, 6; both borders tested on the
  production page path.
- **Plausible:** finding 3 (Vue-lazy mechanism). The evidence grade is
  Plausible rather than Demonstrated because the cited behaviour is
  indistinguishable from an alternative (H2: NiceGUI prop propagation
  breaking reactivity for array-replace). Both H1 and H2 are treated
  by the same fix, so this distinction does not change the remediation,
  but the narrative should not present H1 as definitively demonstrated.
- **Plausible:** finding 7 (no regression in delta-based consumers) —
  enumeration of consumers is complete (`card_helpers.add_comment_to_highlight`,
  `test_browser_perf_377` \[marked `perf`, not in any running lane],
  `scripts/profile_workspace.py` \[standalone script]); the cards-lane
  run with the fix has been captured and is referenced in the results
  table above.
- **Demonstrated:** finding 9 (preexisting teardown hang on
  `test_transition_to_compact_on_fifth_tag`): reproduces on this
  worktree both WITH and WITHOUT the fix, at the same test, with
  the same 31 s timeout and the same captured-stdout "Test passed"
  pattern. Out of scope for this investigation.
- **Not tested:** the discriminating experiment between H1 and H2
  (programmatic post-mount `sidebar.set_items` with `immediate: false`);
  multi-document workspace behaviour with `immediate: true` (each
  sidebar mount will increment the global epoch — see Pre-mortem below);
  full `e2e slow` suite on this branch (the 8 lanes). This investigation
  ran: the latexmk slow lane filtered to Vue sidebar cross-tab tests,
  the latexmk slow lane filtered to the diagnostic probe, and the
  `e2e cards` lane (twice).
- **Corrected:** the very first diagnostic probe (v1, 1 probe, 10 s wait,
  no assertion) appeared to "pass" in 14.44 s. That was misleading — the
  probe caught `TimeoutError` and did not assert on `epoch_fired`, so the
  test passed structurally even though the epoch never fired. Confirmed
  by the v2 two-probe + assertion run where both probes returned
  `epoch_fired=false, epochScalar=null`. Subsequently, the reviewer flagged
  that the post-fix JSON had overwritten the pre-fix JSON; the pre-fix
  state was regenerated and saved to `/tmp/vue-sidebar-diag-prefix.json`.

## Pre-mortem (reviewer-surfaced risk not yet tested)

With `immediate: true`, every sidebar mount fires the watch once and
increments the global `__annotationCardsEpoch`. In a multi-document
workspace with N documents, the page render mounts N sidebars (via
deferred tab panels; first tab is eager, others mount on tab switch).
Each mount bumps the epoch. Delta consumers that capture
`epoch_before` BEFORE all sidebars have mounted may observe a subsequent
sidebar-mount bump as if it were the action-driven bump they were
waiting for, potentially producing a false-positive test pass.

This risk is *probably small* in practice because (a) non-first tabs
mount on user-initiated tab switch, not at page load, so typical test
setup waits for the first sidebar mount before capturing
`epoch_before`, and (b) the per-document `__cardEpochs[doc_container_id]`
map is specifically designed for unambiguous attribution when needed.
But the risk is not zero. The cards lane exercises
`test_multi_doc_tabs_e2e.py`; if the cards-lane-with-fix run passes,
that is the empirical check.

## Side finding (not fixed in this investigation)

`tests/e2e/test_empty_tag_ux.py::TestToolbarExpandedLabels::test_transition_to_compact_on_fifth_tag[chromium]`
hangs in teardown when invoked through `grimoire e2e cards` (serial
Playwright lane). The test body completes and "Test passed" is captured,
but pytest-timeout fires before the lane wraps up.

Evidence of preexistence: two full `grimoire e2e cards` runs were
captured, one with the Vue sidebar fix applied
(`/tmp/cards-with-fix.log`, `test-e2e.log` rotated to cards-with-fix)
and one after reverting the fix
(`/tmp/cards-without-fix.log.bak`, `/tmp/cards-without-fix-pytest.log`).
Both runs hang at the same test, the same subpass
(`ac2_4_expanded_with_four_tags`), with the same "Test passed"
captured stdout and the same pytest-timeout stack. Tests that ran
to completion in both runs all passed; no regression visible in the
overlapping tests exercised before the hang.

Out of scope for this investigation; noted for a separate session.

## Why this bug survived until now

- The test file is marked `noci`, which excludes it from the default `e2e run` / `e2e all` lane that gates PRs.
- The only pipeline that exercises it is `nightly-e2e-slow.yml`.
- The commit that introduced the tests (`38036821`, 2026-04-04) landed
  via PR #457. The Vue sidebar refactor (`f568ea18`) had already moved
  the epoch emit from a Python `_refresh_annotation_cards` post-step
  into the Vue `watch` without `immediate: true`. The test was written
  against the *intended* semantics ("epoch ≥ 1 means cards have been
  rendered") but the *actual* Vue + NiceGUI stack never produced that
  state on cold load.
- The 3 non-failure nightly runs in the visible 26-run history
  (2026-03-30, 2026-03-31, 2026-04-02) all predate the test's
  introduction, so they are not evidence of the tests ever passing.
  Since introduction: 20 consecutive failures. (Full count: 23 failures
  and 3 successes across 26 visible runs.)

## Proposed fix

One word at `src/promptgrimoire/static/annotationsidebar.js:282`:

```diff
-      { deep: true, flush: 'post' }
+      { deep: true, flush: 'post', immediate: true }
```

Consequence trace (Phase 3b, full execution path):

- `watch` callback now fires twice on mount pathways:
  1. `immediate` fires once after first render (because `flush: 'post'`
     defers the immediate callback until after the DOM is ready; verified
     empirically — diagnostic shows `epochScalar: 1` with cards positioned).
  2. Any subsequent `items` change (from `refresh_from_state`, CRDT
     broadcast, or tab-switch refresh) fires again — unchanged behaviour.
- Epoch starts at 1 instead of undefined/0 on cold load. Delta consumers
  (`card_helpers.add_comment_to_highlight`, `test_browser_perf_377`)
  capture `epoch_before` and wait for `> epoch_before`, so they are
  invariant to the initial value.
- Per-doc `__cardEpochs[doc_container_id]` is initialised on mount; previously
  it was never initialised until an items change. Multi-doc tests that rely
  on per-doc presence will now see entries from the moment of mount rather
  than after the first refresh — still-valid invariant, earlier signal.

## Hardening suggestion (Phase 5)

Reviewer caught a mistake in my first pass: a contract test in
`tests/integration/test_vue_sidebar_dom_contract.py` cannot work — that
lane does not render Vue templates server-side (the file's own docstring
says so), and the watch only fires in a real browser.

Two feasible shapes:

1. **Cheap structural check (JS unit lane).** A vitest test that parses
   `annotationsidebar.js` and asserts the watch options object contains
   `immediate: true`. Does not run the watch; just asserts the fix
   stays in place. Location: `tests/js/annotationsidebar.test.js`.
2. **Real behaviour check (non-noci E2E).** A small E2E test in the
   default Playwright lane that loads any workspace with at least one
   highlight and asserts `window.__annotationCardsEpoch === 1` within
   5 s of `wait_for_text_walker`. Not `noci`, so it actually gates
   PRs. Location: new file `tests/e2e/test_vue_sidebar_mount_contract.py`.

Option 2 is the real value (catches H1 *and* H2 regressions); option 1
is a belt-and-braces catch in the JS lane. I'd propose option 2 alone
if one is preferred, unless there's a specific reason the epoch
contract should be tested without a browser.

## Remediation alternative (reviewer-surfaced)

A legitimate alternative to the JS change would be to **fix the fixture
instead**: change `tests/e2e/test_vue_sidebar_cross_tab.py:78` from
`window.__annotationCardsEpoch >= 1` to a DOM-based readiness signal
like `cardCount > 100`, matching what the test's own first body test
already does at line 117. This has the advantage of being a smaller
blast radius (fixture-only change; no production code touched; no
per-sidebar-mount side effect to reason about for multi-doc cases).
It has the disadvantage that the epoch-as-mount-signal pattern would
remain a latent foot-gun for anyone who reaches for it in future
tests.

I chose the JS fix because:
(a) the epoch being 0/undefined on mount is arguably a bug — the
documented pattern in root `CLAUDE.md` treats the epoch as a signal
that items have been rendered, which mount-with-items clearly
qualifies as;
(b) `immediate: true` with `flush: 'post'` is a one-word change with
no behaviour change for subsequent rebuilds; and
(c) fixing only the fixture would leave `__cardEpochs[doc_container_id]`
undefined for newly-mounted-but-never-rebuilt documents, which any
future multi-doc delta consumer would have to special-case.

Reasonable people can disagree. If the reviewer or maintainer
prefers the fixture-only remediation, it is equally valid.

## Peer review (Phase 3d)

A `critical-peer-review` subagent with no prior context audited this
document and its citations. The review returned 3 High, 5 Medium,
and 4 Low findings. All High findings are addressed in the current
revision of this doc:

- **H-1 (provenance):** the pre-fix diagnostic JSON had been overwritten.
  Regenerated; saved to `/tmp/vue-sidebar-diag-prefix.json` and now
  cited explicitly in Findings 2 and 5.
- **H-2 (cards-lane evidence):** the claim that the cards-lane teardown
  hang was "verified preexisting" was not supported by on-disk logs.
  Both `grimoire e2e cards` runs were rerun in full
  (`/tmp/cards-with-fix.log`, `/tmp/cards-without-fix.log.bak`,
  `/tmp/cards-without-fix-pytest.log`); both hang at the same test
  with the same signature, confirming preexistence with disk evidence.
- **H-3 (H1 vs H2 not discriminated):** Finding 3 downgraded from
  Demonstrated to Plausible. Causal chain step 5 rewritten to mark
  the NiceGUI-serialises-props-before-mount claim as an inference, not
  a demonstrated fact. Both H1 and H2 are fixed by `immediate: true`,
  so the remediation is unchanged.

Medium findings addressed: hardening location corrected (original
suggestion was at a location where Vue templates do not render);
`scripts/profile_workspace.py:272,281` added to the enumerated delta
consumers; numeric counts corrected (20 consecutive since test
introduction, not 10; 23/26 failures, not 22/25; 20.37 s, not 20.07 s);
scope caveat added about other independent nightly failures; "never
succeed" hedged to "fails deterministically (20/20 observed)".

Low findings addressed: duration numbers corrected; grep line-number
conflation (276/277) fixed; working-tree vs committed status
disclosed; fixture-only remediation alternative added as a section.
