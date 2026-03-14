# Phase 1 Characterisation Test Audit — Codex Prompt

Audit the characterisation tests written in Phase 1 of the multi-document tabbed workspace feature (issue #186). These tests lock down existing card rendering behaviour before Phases 2–7 refactor and extend it. The tests must actually catch regressions — a characterisation test that passes both before AND after a breaking change is worse than no test.

## Context

- **Branch:** `multi-doc-tabs-186` (git worktree at `.worktrees/multi-doc-tabs-186/`)
- **Base commit:** `24cb2d50` (before Phase 1)
- **HEAD commit:** `f47b5868` (after Phase 1 + review fixes)
- **Total suite:** 3,914 tests pass in 13.4s (xdist, 8 cores). 2 skipped.
- **New tests added:** 45 tests across 6 files (1,739 lines inserted)
- **Production code changes:** Zero — Phase 1 is test-only
- **Test docs:** `docs/testing.md`, `docs/implementation-plans/2026-03-14-multi-doc-tabs-186-plan-a/phase_01_coverage.md`
- **Design plan:** `docs/design-plans/2026-03-14-multi-doc-tabs-186.md`

## New Test Files

| File | Test count | Layer | What it tests |
|------|-----------|-------|---------------|
| `tests/unit/test_card_functions.py` | 18 | unit | `_author_initials()`, `anonymise_author()`, `group_highlights_by_tag()` |
| `tests/unit/test_annotation_doc.py` | 5 new (95 total) | unit | `get_highlights_for_document()` filtering, ordering, cross-contamination |
| `tests/integration/test_annotation_cards_charac.py` | 7 | integration (nicegui_ui) | Annotate tab card rendering: ordering, truncation, badges, buttons |
| `tests/integration/test_organise_charac.py` | 7 | integration (nicegui_ui) | Organise tab: snippet truncation (100 chars), locate button, tag grouping |
| `tests/integration/test_respond_charac.py` | 6 | integration (nicegui_ui) | Respond tab: reference cards, truncation, author anonymisation gap |
| `tests/e2e/test_organise_respond_flow.py` | 2 | e2e (Playwright) | Cross-tab flow: highlight visible on all 3 tabs, comment visible on Respond |

## Known Issues (identified during code review, already fixed)

1. **`_find_all_by_testid` was copy-pasted** into all three NiceGUI integration files. Fixed: extracted to `tests/integration/nicegui_helpers.py`.
2. **`test_respond_shows_raw_author_to_viewer`** originally tested as same user (own highlights always show real name). Fixed: now uses a second viewer user with explicit ACL.
3. **Bare `asyncio.sleep(0.1)`** in `test_expandable_text_truncated`. Fixed: replaced with `wait_for()` retry pattern.
4. **DB fixture duplication** across three integration files (~200 lines each of `_create_course`, `_enroll`, `_create_week`, etc.). Documented as tech debt for Phase 3 extraction.

## Your Tasks

### 1. Validate characterisation test effectiveness

For each test file, answer: **will these tests actually break when the Phase 2–7 changes they're supposed to guard against occur?**

Specific concerns:
- Phase 2 changes Organise/Respond snippet truncation from 100-char static to 80-char expandable text. Do `test_organise_charac.py` and `test_respond_charac.py` assert the 100-char threshold specifically enough that changing to 80 chars would cause failure?
- Phase 2 adds `anonymise_author()` to respond.py. Does `test_respond_shows_raw_author_to_viewer` actually assert the raw name in a way that returning a pseudonym would fail?
- Phase 3 extracts functions from `cards.py` to `card_shared.py`. Would moving a function break any import paths in the tests?
- Phase 5 replaces clear-and-rebuild with diff-based card updates. Do the integration tests depend on rebuild semantics (e.g. `cards_epoch` incrementing) that would detect if diff-based updates skip the epoch bump?

### 2. Check for vacuous or tautological assertions

Read each test's assertions. Flag any that:
- Assert only that something is not None / not empty (tells you nothing about correctness)
- Assert a condition that is always true regardless of the code under test
- Use overly broad matching (e.g. `"text" in page_content` where "text" appears in multiple unrelated places)
- Skip the actual behaviour and test setup code instead

### 3. Evaluate test isolation

The three NiceGUI integration files each create their own workspace + document + CRDT state via ~200 lines of helper functions. Check:
- Do tests within a file share state that could cause order-dependent failures?
- Are workspace IDs, course codes, and email addresses unique enough to avoid collisions under xdist?
- Does the CRDT state setup (creating highlights with specific `start_char`, tags, comments) match what the production code actually reads?

### 4. Assess the cross-user anonymisation test

`test_respond_shows_raw_author_to_viewer` (in `test_respond_charac.py`) is the most critical characterisation test — it documents the known bug that respond.py doesn't call `anonymise_author()`. Verify:
- The second viewer is actually authenticated as a different user (not the highlight author)
- The viewer sees the workspace through a code path that would invoke `anonymise_author()` if it existed in respond.py
- The assertion would fail if `anonymise_author()` were added to respond.py's card rendering

### 5. List 3–5 highest-risk gaps

What card rendering behaviours are NOT covered by these characterisation tests but WILL change in Phases 2–7? Cross-reference with `phase_01_coverage.md` — does the coverage doc accurately reflect what's missing?

## Production Code Under Test

Read these to understand what the tests should be characterising:

- `src/promptgrimoire/pages/annotation/cards.py` — Annotate tab card rendering (80-char `_build_expandable_text`, `_author_initials`, `cards_epoch`)
- `src/promptgrimoire/pages/annotation/organise.py` — Organise tab (100-char `_SNIPPET_MAX_CHARS` static truncation, tag grouping)
- `src/promptgrimoire/pages/annotation/respond.py` — Respond tab (100-char truncation, `group_highlights_by_tag`, **missing `anonymise_author()`**)
- `src/promptgrimoire/auth/anonymise.py` — `anonymise_author()` function
- `src/promptgrimoire/crdt/annotation_doc.py` — `get_highlights_for_document()`, `AnnotationDocument`

## Output

Write findings to `.codex/phase1-charac-test-audit.md`. Be specific — cite file paths, line numbers, and quote assertion lines. Claude will peer-review your findings.
