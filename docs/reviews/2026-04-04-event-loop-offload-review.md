# Critical Peer Review: event-loop-offload branch

Reviewer: Claude Opus 4.6 (1M context)
Date: 2026-04-04
Document reviewed: git log f91246726b32b6a98d974a8c57d83508fd929b65..HEAD (32 commits)

## Hidden Assumptions

1. **Load-bearing: Vue watch and Python epoch push do not race destructively.**
   The `sidebar.py:refresh_from_state()` sets `window.__annotationCardsEpoch = N` via fire-and-forget `ui.run_javascript()`, AND the Vue `watch` on `items` in `annotationsidebar.js:275` independently increments `(window.__annotationCardsEpoch || 0) + 1`. Both execute client-side but arrive via different WebSocket messages. The assumption is that E2E tests only check `> oldEpoch` so the exact value does not matter. True for now, but the double-write is a latent inconsistency. If any future code depends on exact epoch equality, this will break.

2. **Load-bearing: `cleanupIdleTracker()` and `initIdleTracker()` are globally available.**
   The idle E2E tests (`test_idle_tab_eviction.py`) call these functions via `page.evaluate()`. The assumption is that `idle-tracker.js` exposes both as globals and that `cleanupIdleTracker()` fully tears down the previous tracker (timers, event listeners, mutation observers). If cleanup is incomplete, the old tracker fires alongside the reconfigured one. Evidence: the functions exist in the code path (not verified by me reading `idle-tracker.js` directly), but the test design is sound.

3. **Non-critical: `test-pseudocode.md` is not machine-consumed.**
   Stale testid references in this file (`card-expand-btn`) are cosmetic because no test runner reads it. However, it serves as a human reference and will mislead developers.

4. **Load-bearing: `cards_container` on `DocumentTabState` correctly maps to `annotations_container` on `PageState`.**
   Tab switch logic in `tab_bar.py` does `state.annotations_container = doc_tab.cards_container`. The naming mismatch (cards_container vs annotations_container) is deliberate but undocumented. A future rename of either field without updating the other will break tab switching silently.

## ACH Matrix

No competing hypotheses to evaluate -- this is a code review, not an incident investigation. Skipping ACH per protocol.

## Findings

### High (count: 1)

- **Issue**: Double epoch increment creates non-deterministic epoch values
  **Evidence**: `sidebar.py:139-147` sets `window.__annotationCardsEpoch = {epoch}` (deterministic). `annotationsidebar.js:275` sets `window.__annotationCardsEpoch = (window.__annotationCardsEpoch || 0) + 1` (relative increment). Both fire on every `refresh_from_state()` call. The Vue watch triggers when `self.update()` pushes the new `items` prop; the `ui.run_javascript()` fires independently. Execution order on the client is non-deterministic.
  **GRADE factors**: Indirectness -- the problem is inferred from code reading, not observed in a failing test. Risk of bias -- no negative results (tests that fail due to wrong epoch) were sought. Downgrade from High to **Moderate** on indirectness.
  **Ripple**: `card_helpers.py:add_comment_to_highlight` (line 153) and all E2E tests that use epoch synchronisation. Currently non-fatal because all checks use `> oldEpoch`, but the Python-side epoch counter (`state.cards_epoch`) will diverge from the client-side value. If any code ever reads the client epoch and compares to the Python epoch, it will fail.
  **Corrected language**: The epoch should be set in exactly one place. Either remove the Vue-side `watch` increment (and rely solely on the Python `ui.run_javascript` push), or remove the Python-side push (and let the Vue watch be the sole source). The dual-write pattern is a bug waiting to surface.
  **Location**: `src/promptgrimoire/pages/annotation/sidebar.py:138-147` and `src/promptgrimoire/static/annotationsidebar.js:273-280`

### Medium (count: 5)

- **Issue**: Module count off-by-one in `__init__.py` docstring and `annotation-architecture.md`
  **Evidence**: Both claim "30 authored modules" but the docstring listing contains 31 entries (`__init__` + 30 submodules), matching 31 `.py` files on disk.
  **Ripple**: `docs/annotation-architecture.md:5` also says "30-module package".
  **Corrected language**: "31 authored modules" or "30 submodules plus __init__".
  **Location**: `src/promptgrimoire/pages/annotation/__init__.py:11`, `docs/annotation-architecture.md:5`

- **Issue**: Code docstrings say "7 standard lanes" but there are 8
  **Evidence**: `_run_all_lane_steps` (line 171) says "Execute all 7 standard lanes" and `run_all_lanes` (line 300) says "Run all 7 test lanes". Actual lanes: JS, BATS, Unit, Integration, Playwright, NiceGUI, Smoke, BLNS+Extra = 8. CLAUDE.md correctly says "8 lanes".
  **Ripple**: Developers reading the code docstring will be misled about lane count.
  **Corrected language**: "Execute all 8 standard lanes"
  **Location**: `src/promptgrimoire/cli/e2e/__init__.py:171,300`

- **Issue**: `e2e latexmk` subcommand not documented in CLAUDE.md Key Commands
  **Evidence**: Commit `d30577b0` adds the `latexmk` subcommand to `e2e_app` (line 744), but the Key Commands section of CLAUDE.md has no entry for `uv run grimoire e2e latexmk`.
  **Corrected language**: Add `# Run standalone latexmk lane (real PDF compilation)\nuv run grimoire e2e latexmk` to the Key Commands section.
  **Location**: `CLAUDE.md` Key Commands section (around line 147)

- **Issue**: Value-capture pattern documentation slightly overclaims after Vue migration
  **Evidence**: CLAUDE.md line 87 says "All submit buttons bound to text inputs must use this helper" (`on_submit_with_value`). The Vue sidebar's comment input (`annotationsidebar.js:428-434`) uses Vue's own `@input` + reactive state + `@keydown.enter` / `@click` pattern, not `on_submit_with_value`. This is correct design (Vue manages its own DOM), but the universal claim in the documentation is no longer accurate.
  **Corrected language**: "All Python-rendered submit buttons bound to text inputs must use this helper. Vue components manage their own DOM state and do not require it."
  **Location**: `CLAUDE.md:87`

- **Issue**: Stale fixture path in `test_browser_perf_377.py` docstring
  **Evidence**: Line 7 says "The fixture at tests/e2e/fixtures/pabai_workspace.json" but this file was deleted (renamed to `tests/fixtures/pabai_workspace_scrubbed.json`). The actual import at line 29-33 uses `card_helpers.ensure_pabai_workspace()` which points to the correct path.
  **Ripple**: Misleads developers reading the test file header. No runtime effect.
  **Corrected language**: "The fixture at tests/fixtures/pabai_workspace_scrubbed.json is a PII-sanitised copy..."
  **Location**: `tests/e2e/test_browser_perf_377.py:7-8`

### Low (count: 3)

- **Issue**: Stale `card-expand-btn` testid in `test-pseudocode.md` and design plan docs
  **Evidence**: `tests/test-pseudocode.md:5177` and `docs/design-plans/2026-03-06-card-layout-236-284.md` (3 occurrences) reference `card-expand-btn`. Production code and all E2E tests use `expand-btn`. These files are historical documentation, not executed code.
  **Location**: `tests/test-pseudocode.md:5177`, `docs/design-plans/2026-03-06-card-layout-236-284.md:51,117,162`

- **Issue**: `cards_container`/`annotations_container` naming inconsistency undocumented
  **Evidence**: `DocumentTabState.cards_container` maps to `PageState.annotations_container` via `tab_bar.py:396`. The rename happened implicitly during the Vue migration but the field names were not reconciled.
  **Location**: `src/promptgrimoire/pages/annotation/tab_state.py:29`, `src/promptgrimoire/pages/annotation/tab_bar.py:396`

- **Issue**: `positionCards` code duplication flagged but not resolved
  **Evidence**: `annotationsidebar.js:138` has a TODO comment: "TODO(#457): extract shared positionCards to annotation-utils.js, remove duplication with annotation-card-sync.js". Since `annotation-card-sync.js` no longer contains `positionCards` (it was removed), this TODO is stale -- there is no duplication to resolve.
  **Location**: `src/promptgrimoire/static/annotationsidebar.js:138`

## Verification

Commands and tools used:
- `git log f91246726b32b6a98d974a8c57d83508fd929b65..HEAD --oneline` -- confirmed 32 commits
- `git diff --stat` -- confirmed 86 files changed
- Read all key files cited in the audit brief
- `grep` for `card-expand-btn` across the entire worktree -- confirmed only in docs/design-plans and test-pseudocode.md (not in executable test code)
- `grep` for `expand-btn` -- confirmed consistent usage in all test code and production Vue template
- `grep` for `ensure_pabai_workspace` -- confirmed single canonical definition in `card_helpers.py`, no duplicates in other helper files
- `grep` for `pabai_workspace.json` -- confirmed old file deleted, only scrubbed version remains
- Module count: `ls *.py | wc -l` = 31; docstring listing cross-referenced = 31 entries
- Lane count in `_run_all_lane_steps`: manually counted 8 lanes (JS, BATS, Unit, Integration, Playwright, NiceGUI, Smoke, BLNS+Extra)
- `grep` for `IDLE__TIMEOUT_SECONDS` -- confirmed removal from server script, client-side reconfiguration pattern in test file
- `grep` for `on_submit_with_value` -- confirmed still used in sharing.py and tag_quick_create.py (Python forms), not used by Vue sidebar

## Strongest Hypothesis

The Vue sidebar migration is sound. The `cards.py` deletion (896 lines) was clean -- no dangling imports, all testid references in executable code were updated, event handlers were correctly extracted to module-level functions in `document.py`, and the epoch synchronisation mechanism works (despite the double-write redundancy). The Pabai fixture consolidation to `card_helpers.py` is complete with no remaining duplicated definitions.

## Weakest Hypothesis

The epoch double-write between Python and Vue is "harmless". It works today because all epoch consumers use inequality checks (`> oldEpoch`). But the Python-side `state.cards_epoch` counter will accumulate at +1 per refresh while the client-side counter accumulates at +2 per refresh (one from Python push, one from Vue watch). Any future feature that bridges these (e.g. server reading client epoch, or client sending epoch back to server for validation) will see mismatched values.

## Pre-Mortem

If the current conclusion ("the branch is ready to merge with minor fixes") is wrong, the next incident could reveal:

1. **Epoch-dependent E2E test flakiness**: A test that captures `old_epoch`, triggers an action, but the Vue watch fires before the Python push, resulting in epoch = old+1 momentarily, then the Python push resets it to old+1 (same value), and the `wait_for_function(epoch > old)` check succeeds on the watch increment but the DOM is not yet settled because `flush: 'post'` has not completed. This would manifest as intermittent locator-not-found errors after epoch sync.

2. **Idle tracker interaction with admission gate edge case**: The `_SHORT_IDLE_JS` reconfiguration runs after page load. If the page load itself is slow (e.g. Pabai workspace with 190 highlights), the default idle tracker may fire before `_SHORT_IDLE_JS` runs. Since admission gate is now disabled in the test server, this would navigate to `/paused` during test setup. The `cleanupIdleTracker()` call should prevent this, but if there is any timing gap between page load and `evaluate()`, the default tracker (30-minute timeout) would be active briefly.

3. **NiceGUI client lifecycle leak from Vue component**: The `AnnotationSidebar` registers event listeners in `onMounted` and removes them in `onBeforeUnmount`. But if NiceGUI's element lifecycle does not correctly trigger Vue's unmount (e.g. `element.delete()` bypasses Vue teardown), the scroll listener and `highlights-ready` listener would leak. Each leaked listener adds CPU cost on every scroll event.

## Fastest Next Test

**Remove the Vue-side epoch increment and run the full E2E suite.** This is the single test that resolves the most uncertainty (the double-write finding). Steps:
1. Comment out lines 274-280 of `annotationsidebar.js` (the epoch increment in the `watch` callback)
2. Run `uv run grimoire e2e run`
3. If all tests pass: the Python-side push is sufficient and the Vue-side increment is redundant. Remove it permanently.
4. If tests fail: the Python push arrives too late (after tests check the epoch) and the Vue-side increment is load-bearing. In that case, remove the Python-side push instead and let Vue be the sole epoch source. Update `state.cards_epoch` to be server-only bookkeeping (not pushed to client).

## Overall Assessment

**Ready to merge with minor fixes required.**

The branch is well-structured. The Vue sidebar migration is clean, the test infrastructure changes (admission gate, idle tracker, timeout values) are sound, and the Pabai fixture consolidation is complete. The findings are:

- 1 Moderate issue (double epoch write) -- should be resolved before merge to prevent future debugging headaches
- 5 Medium issues (module count, lane count docstrings, missing CLAUDE.md entry, value-capture docs, stale fixture path) -- should fix before merge
- 3 Low issues (stale pseudocode testids, naming inconsistency, stale TODO) -- fix if convenient

None of these are blocking defects. The code functions correctly today. The epoch double-write is the only item that could cause real problems in future development.
