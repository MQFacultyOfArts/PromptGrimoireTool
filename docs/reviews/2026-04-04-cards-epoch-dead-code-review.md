# Critical Peer Review: `cards_epoch` Dead Code Analysis

Reviewer: Claude Opus 4.6 (1M context)
Date: 2026-04-04
Document reviewed: Informal analysis (provided in user prompt) claiming `cards_epoch` is dead code

## Hidden Assumptions

1. **Load-bearing: grep coverage is sufficient to find all production consumers.**
   The analysis assumes that text grep for `cards_epoch` catches all access. This is valid here -- Python dataclass fields are accessed by name (no `getattr` with computed strings, no `__dict__` iteration, no `asdict()` calls on `PageState` or `DocumentTabState`). Verified: `grep` for `asdict|__dict__|vars(state|dataclasses.fields|getattr.*cards` across `src/` returns zero hits on these classes.

2. **Load-bearing: the Vue-side epoch (`window.__annotationCardsEpoch`) and the Python-side field (`state.cards_epoch`) are independent after commit 23e03cca.**
   True. Before that commit, `sidebar.py` incremented `state.cards_epoch` and pushed the value to the browser. After, the Python field is never incremented and the browser value is managed solely by the Vue `watch`. These are now decoupled -- the Python field is frozen at whatever value it was initialised to (default `0`), and the browser counter runs independently.

3. **Non-critical: removing a dataclass field with a default value cannot break serialisation.**
   `PageState` and `DocumentTabState` are plain `@dataclass` instances, not Pydantic models or SQLModel tables. They are never serialised to JSON, database, or wire format. Removal is safe from a serialisation standpoint.

## ACH Matrix

| Evidence | H1: `cards_epoch` is dead code | H2: `cards_epoch` serves a functional purpose |
|---|---|---|
| No `+= 1` on `cards_epoch` in any `.py` file under `src/` | + | - (strong) |
| `sidebar.py:147` logs `cards_epoch="vue-managed"` (static string, not the field value) | + | ? |
| `tab_bar.py:366,397` copies field between `PageState` and `DocumentTabState` | + (copy of zero is a no-op) | ? (copy alone is not consumption) |
| `__init__.py:253` declares field with default `0` and stale comment | + | ? |
| `tab_state.py:30` declares field with default `0` | + | ? |
| Vue watch (`annotationsidebar.js:273`) increments `window.__annotationCardsEpoch` without reading Python field | + | - |
| E2E tests read `window.__annotationCardsEpoch` from browser, never `state.cards_epoch` | + | - |
| Integration test (`test_vue_sidebar_broadcast.py`) checks structlog output, not `state.cards_epoch` value | + | ? |
| Unit tests (`test_tab_bar_deferred.py`) test the copy operation itself, not downstream consumption | + | ? |
| `docs/testing.md:100` still documents the old `state.cards_epoch += 1` pattern | + (stale doc, not functional code) | ? |

**Decision:** H1 has zero contradictions. H2 has two strong contradictions (no increment anywhere, Vue epoch is independent). H1 wins decisively.

## Findings

### High (count: 0)

No high-severity findings. The analysis's core claim is correct.

### Medium (count: 2)

- **Issue**: Stale comment on `PageState.cards_epoch` field
  **Evidence**: `__init__.py:253` reads `cards_epoch: int = 0  # Incremented on every Vue prop push`. Nothing increments this field anywhere in `src/`. The comment describes behaviour that was removed in commit 23e03cca.
  **Ripple**: A developer reading this comment would believe the field is actively used and incremented, and would hesitate to remove it. This is the exact kind of misleading documentation that keeps dead code alive.
  **Corrected language**: If the field is kept temporarily, the comment should say `# DEAD: formerly incremented by refresh_from_state; epoch now Vue-managed (window.__annotationCardsEpoch)`. Better: remove the field entirely per the analysis recommendation.
  **Location**: `src/promptgrimoire/pages/annotation/__init__.py:253`

- **Issue**: `docs/testing.md:100` documents the old epoch pattern as current
  **Evidence**: Line 100 reads: `Server: state.cards_epoch += 1 and ui.run_javascript(f"window.__annotationCardsEpoch = {state.cards_epoch}")` -- this exact code was removed in commit 23e03cca. The documentation now describes a pattern that no longer exists in the codebase.
  **Ripple**: The original analysis did not flag this stale documentation. Any developer following `testing.md` to implement a new epoch pattern would write code that increments a dead field. Line 105 also references `cards.py` which was deleted in commit f568ea18.
  **Corrected language**: The Rebuild Epoch Race section should describe the current pattern: the Vue `watch` on `items` (annotationsidebar.js:268-283, `flush: 'post'`) is the sole epoch source. Tests capture `window.__annotationCardsEpoch` before the action and `wait_for_function` until it advances. No Python-side increment is needed.
  **Location**: `docs/testing.md:100-105`

### Low (count: 1)

- **Issue**: The analysis's claim #4 says "logged as a sentinel string 'vue-managed' in sidebar.py:147" -- this is accurate but slightly misleading. The log line is `cards_epoch="vue-managed"`, which is a structlog keyword argument. It is not logging the `state.cards_epoch` field value; it is logging a hardcoded string. This distinction matters: it means the log line would not change if the field were removed.
  **Location**: Analysis claim #4

## Verification

All claims verified by direct file reads and grep:

1. **"Nothing increments it in production code"** -- VERIFIED. `grep 'cards_epoch\s*\+='` across the entire worktree returns hits only in `docs/` (implementation plan, testing.md) -- zero hits in `src/`. `grep 'cards_epoch\s*=\s*[^0]'` in `src/` returns only `sidebar.py:147` (the log string "vue-managed") and `tab_bar.py:366,397` (copy operations that propagate the never-incremented value).

2. **"The real epoch lives entirely client-side"** -- VERIFIED. `annotationsidebar.js:268-283` shows a Vue `watch` on `props.items` with `{ deep: true, flush: 'post' }` that increments `window.__annotationCardsEpoch` and sets per-document `window.__cardEpochs`. No Python code writes to either of these browser globals after commit 23e03cca.

3. **"The field is only declared, copied, and logged"** -- VERIFIED. Complete enumeration of all `cards_epoch` references in `src/`:
   - `__init__.py:253`: field declaration (default `0`)
   - `tab_state.py:30`: field declaration (default `0`)
   - `tab_bar.py:366`: save copy (`doc_tab.cards_epoch = state.cards_epoch`)
   - `tab_bar.py:397`: restore copy (`state.cards_epoch = doc_tab.cards_epoch`)
   - `sidebar.py:147`: structlog keyword (`cards_epoch="vue-managed"`)

4. **"Commit 23e03cca removed the Python-side epoch push"** -- VERIFIED. The diff shows removal of `state.cards_epoch += 1` and the `ui.run_javascript(f"window.__annotationCardsEpoch = {epoch};...")` block from `refresh_from_state()`, replaced by a comment `# Epoch increment is handled by the Vue watch on items`.

5. **"No production code reads it for any functional purpose"** -- VERIFIED. The copy in `tab_bar.py` propagates a value that is always `0` (never incremented). No conditional logic, no comparison, no use in any computation. The log emits a hardcoded string, not the field value.

6. **No dynamic access patterns** -- VERIFIED. `grep` for `asdict|__dict__|vars(state|dataclasses.fields|getattr.*cards` across `src/` returns zero hits involving `PageState` or `DocumentTabState`.

7. **Vue watch does what is claimed** -- VERIFIED by reading `annotationsidebar.js:268-283`. The watch callback increments the global epoch monotonically and sets the per-document epoch keyed by `props.doc_container_id`.

8. **E2E tests read browser-side only** -- VERIFIED. `card_helpers.py:153` reads `window.__annotationCardsEpoch` via `page.evaluate()`. `test_vue_sidebar_cross_tab.py` and `test_browser_perf_377.py` use `page.wait_for_function` on `window.__annotationCardsEpoch`. None of these access `state.cards_epoch`.

## Strongest Hypothesis

H1: `cards_epoch` on both `PageState` and `DocumentTabState` is dead code. All evidence is consistent; no contradictions found.

## Weakest Hypothesis

H2 (that the field serves a functional purpose) is definitively refuted. There is no increment, no conditional read, and no consumer beyond copy-propagation of a constant zero.

## Pre-Mortem

Assume the analysis is wrong and `cards_epoch` is not dead code. What would that mean?

1. **A plugin or monkey-patch reads it at runtime.** Refuted -- the field is on an internal `@dataclass` not exposed via any public API. NiceGUI does not introspect arbitrary dataclass fields.

2. **A future commit on this branch re-introduces the increment.** Possible but not current state. The analysis is about current code, not planned code.

3. **The tab-switch copy matters for some subtle ordering reason.** Refuted -- the value copied is always `0` because nothing increments it. Copying `0` to `0` is a no-op regardless of ordering.

No alternative scenario is consistent with the evidence. The pre-mortem confirms the analysis.

## Fastest Next Test

Remove the `cards_epoch` field from both `PageState` and `DocumentTabState`, remove the copy lines in `tab_bar.py:366,397`, change the log line in `sidebar.py:147` to drop the kwarg, update the unit tests, and run `uv run grimoire test all && uv run grimoire e2e run`. If all tests pass, the field is confirmed dead. If any test fails, the failure will identify the hidden consumer.

This is low-risk because the field is never incremented and all known consumers either copy a constant or log a hardcoded string.

## Overall Assessment

**The analysis is correct. `cards_epoch` is dead code.**

All six claims in the analysis are verified against the actual codebase. The field is declared, copied between dataclasses during tab switches (propagating the constant `0`), and referenced in a log line as a hardcoded sentinel string. Nothing increments it. Nothing reads it for conditional logic. The real epoch lives entirely in `window.__annotationCardsEpoch`, managed by the Vue `watch` on `items`.

**Recommendation: proceed with removal.** Additionally fix the two medium findings:
- Update `docs/testing.md:100-105` to describe the current Vue-managed epoch pattern and remove the stale `cards.py` reference.
- Remove the stale field comment or the field itself.
