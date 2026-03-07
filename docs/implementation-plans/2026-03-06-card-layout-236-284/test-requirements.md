# Test Requirements — Annotation Card Layout (#236, #284)

**Design:** `docs/design-plans/2026-03-06-card-layout-236-284.md`
**Implementation phases:** Phase 2 (E2E helpers/runner), Phase 3 (test refactoring), Phase 4 (sleep removal)
**Phase 1 (spike):** Implemented in prior session — collapsed card UI, JS fixes, complexity refactoring

---

## Mapping Legend

| Column | Meaning |
|--------|---------|
| AC | Acceptance criterion ID from design |
| Test type | `unit`, `integration`, `e2e`, or `human` |
| File path | Expected test file (automated) or verification approach (human) |
| Phase | Which implementation phase covers this |
| Notes | Rationale for test type or human verification |

---

## AC1: Bug fixes — race condition and solitaire collapse

| AC | Criterion | Test type | File / Approach | Phase | Notes |
|----|-----------|-----------|-----------------|-------|-------|
| AC1.1 | Cards render at correct vertical positions on initial page load (SPA navigation) without requiring user scroll | e2e | `tests/e2e/test_card_layout.py::test_initial_card_positioning` | 3 (Task 9) | Verify each card has a non-zero `top` style and cards have increasing `top` values. Requires live browser to test SPA navigation + JS positioning. |
| AC1.2 | `setupCardPositioning()` catches `highlights-ready` via `window._highlightsReady` check | e2e | `tests/e2e/test_card_layout.py::test_highlights_ready_race_condition` | 3 (Task 9) | Use `page.wait_for_function("() => window._highlightsReady === true")` then verify cards positioned. The race condition is between JS event listener registration and event dispatch — only observable in a real browser. |
| AC1.3 | Scrolling past all cards then scrolling back restores correct positions (no solitaire collapse) | e2e | `tests/e2e/test_card_layout.py::test_scroll_recovery_no_solitaire_collapse` | 3 (Task 9) | Record card `top` values, scroll down past all, scroll back, compare within 5px tolerance. Scroll behaviour requires real browser. |
| AC1.4 | Hidden cards use cached height from `data-cached-height` instead of 0 | e2e | `tests/e2e/test_card_layout.py::test_hidden_card_cached_height` | 3 (Task 9) | While cards are hidden (scrolled past), read `data-cached-height` attribute via Playwright locator, assert positive value. Attribute is set by JS in the browser DOM. |
| AC1.5 | Cards with no prior height measurement fall back to 80px default | e2e | `tests/e2e/test_card_layout.py::test_fallback_default_height` | 3 (Task 9) | Create a new highlight, immediately scroll past and back before height is cached. Verify card `top` is positive (fallback used). Timing-sensitive — requires real browser to exercise the race between creation and cache. |

**Rationale for all-E2E:** AC1 criteria are about JS positioning logic (`positionCards()`, `setupCardPositioning()`) running in the browser DOM. These functions operate on `offsetHeight`, `style.top`, `display`, `data-cached-height`, and browser scroll state. None of this is testable outside a real browser.

---

## AC2: Collapsed annotation cards

| AC | Criterion | Test type | File / Approach | Phase | Notes |
|----|-----------|-----------|-----------------|-------|-------|
| AC2.1 | Cards default to compact view (~28px) showing coloured dot, tag name, author initials, para_ref, comment count badge, chevron, locate button, delete button | e2e | `tests/e2e/test_card_layout.py::test_default_collapsed_state` | 3 (Task 10) | Verify `card-detail` is hidden by default. Verify compact header contains expected elements by `data-testid`. |
| AC2.2 | Clicking expand chevron reveals detail section | e2e | `tests/e2e/test_card_layout.py::test_expand_collapse_toggle` | 3 (Task 10) | Click `card-expand-btn`, assert `card-detail` visible, assert `tag-select` and `comment-input` present. |
| AC2.3 | Clicking collapse chevron hides detail section | e2e | `tests/e2e/test_card_layout.py::test_expand_collapse_toggle` | 3 (Task 10) | Same test as AC2.2 — toggle is tested as expand then collapse in sequence. |
| AC2.4 | Author initials derived correctly | unit + e2e | `tests/unit/test_author_initials.py` (unit), `tests/e2e/test_card_layout.py::test_author_initials` (e2e) | 3 (Task 10) | **Unit test** for the pure initials derivation function: "Brian Ballsun-Stanton" -> "B.B.S.", single name -> "B.", empty/None -> "A.". **E2E test** verifies initials render in the compact header. |
| AC2.5 | Cards below an expanding card push down smoothly via `positionCards()` re-run | e2e + human | `tests/e2e/test_card_layout.py::test_push_down_on_expand` (e2e) | 3 (Task 10) | E2E verifies position change. **Human verification** needed for visual smoothness (CSS transition quality). |
| AC2.6 | View-only users see static tag label (not dropdown) in both compact and expanded states | e2e | `tests/e2e/test_card_layout.py::test_view_only_static_tag_label` | 3 (Task 10) | Create workspace as user1, highlight, grant viewer to user2. As user2, verify `tag-select` count is 0. |
| AC2.7 | Comment input only visible in expanded state when `can_annotate` is true | e2e | `tests/e2e/test_card_layout.py::test_view_only_no_comment_input` | 3 (Task 10) | After expanding as viewer, verify `comment-input` count is 0. Tested together with AC2.6. |
| AC2.8 | Anonymous author renders as "A." initials without error | e2e | `tests/e2e/test_card_layout.py::test_anonymous_author_initials` | 3 (Task 10) | Under anonymous sharing, verify compact header shows "A." initials. |

---

## AC3: E2E card helpers and test updates

| AC | Criterion | Test type | File / Approach | Phase | Notes |
|----|-----------|-----------|-----------------|-------|-------|
| AC3.1 | `expand_card(page, card_index)` clicks expand button and waits for detail section visible | e2e | `tests/e2e/test_card_layout.py::test_expand_collapse_toggle` | 2+3 | Helper defined in Phase 2, validated implicitly by every test that uses it. |
| AC3.2 | `collapse_card(page, card_index)` clicks chevron and waits for detail section hidden | e2e | `tests/e2e/test_card_layout.py::test_expand_collapse_toggle` | 2+3 | Same rationale as AC3.1. |
| AC3.3 | All card-touching E2E tests pass after inserting `expand_card()` | e2e | All files listed in Phase 3 Tasks 3-7 | 3 | Validated by `uv run grimoire e2e cards` passing. |
| AC3.4 | Interacting with tag-select or comment-input without expanding first fails | **human** | Temporary removal of `expand_card()` in one test, run, observe Playwright timeout | 3 (Task 8) | Negative verification — confirming collapsed state prevents interaction. Not a permanent test. |

---

## AC4: `e2e cards` runner shortcut

| AC | Criterion | Test type | File / Approach | Phase | Notes |
|----|-----------|-----------|-----------------|-------|-------|
| AC4.1 | `uv run grimoire e2e cards` discovers and runs all `@pytest.mark.cards`-marked tests | e2e | Validated by running `uv run grimoire e2e cards` after Phase 3 marks tests | 2+3 | The runner *is* the test infrastructure. |
| AC4.2 | `cards` marker defined in `pyproject.toml` | unit | `uv run pytest --markers \| grep cards` | 2 (Task 4) | Verification command, not a persistent test file. |
| AC4.3 | Running with no marked tests exits cleanly | **human** | Run `uv run grimoire e2e cards` before Phase 3 marks any tests; verify exit code 5 | 2 (Task 5) | One-time verification during Phase 2 implementation. |

---

## AC5: Sleep removal in card-touching tests

| AC | Criterion | Test type | File / Approach | Phase | Notes |
|----|-----------|-----------|-----------------|-------|-------|
| AC5.1 | No `page.wait_for_timeout()` calls remain in card-touching test files | unit (static) | `grep -rn "wait_for_timeout" <file list>` — zero matches | 4 (Task 5) | Static code search. Consider adding a guard test (like `test_async_fixture_safety.py`) that greps test files and fails if `wait_for_timeout` appears. |
| AC5.2 | All card-touching tests still pass after sleep replacement | e2e | `uv run grimoire e2e cards` + `uv run grimoire e2e run` | 4 (Task 5) | Validated by full E2E suite passing. |
| AC5.3 | Waits use state-based patterns | **human** | Code review of Phase 4 changes | 4 | Verified by reviewing that each replaced sleep uses `wait_for`, `wait_for_function`, or `expect` patterns. |

---

## AC6: Complexity management

| AC | Criterion | Test type | File / Approach | Phase | Notes |
|----|-----------|-----------|-----------------|-------|-------|
| AC6.1 | All functions in `cards.py` have complexipy score <= 15 | unit (static) | `uv run complexipy src/promptgrimoire/pages/annotation/cards.py --max-complexity-allowed 15` | 1 (spike) + 4 UAT | Static analysis. Phase 4 UAT step 4 re-verifies. |
| AC6.2 | All functions in touched files have complexipy score <= 15 | unit (static) | `uv run complexipy src/promptgrimoire/pages/annotation/ --max-complexity-allowed 15` | 1 (spike) + 4 UAT | Same tool, broader scope. |
| AC6.3 | `_build_card_header` and `_build_comments_section` must not remain at current complexity | unit (static) | Same as AC6.1 — validated by AC6.1 passing | 1 (spike) | Anti-regression criterion. |

---

## Human Verification Summary

| AC | What | Why not automated | Verification approach |
|----|------|-------------------|----------------------|
| AC2.5 (smoothness) | CSS transition visual quality | Subjective visual assessment | Expand a card in a 3+ annotation workspace, observe cards below slide with `transition: top 0.15s`, no visible jump |
| AC3.4 | Collapsed card prevents inner-element interaction | Negative test (intentional failure) is an anti-pattern | Temporarily remove one `expand_card()` call, run test, confirm Playwright timeout, restore |
| AC4.3 | Runner exits cleanly with no marked tests | One-time edge case during Phase 2 | Run `uv run grimoire e2e cards` before marking tests, verify exit code 5 |
| AC5.3 | Replacement waits use correct patterns | Code quality / style criterion | Code review of Phase 4 diff |

---

## Recommendations

1. **Guard test for AC5.1:** Add a test that greps card-touching test files for `wait_for_timeout` and fails if found. Prevents sleep regression. Follow `test_async_fixture_safety.py` precedent.

2. **CI check for AC6:** Add `complexipy` to CI pipeline (or a guard test) to prevent complexity regression in `cards.py` and other annotation page files.

3. **AC2.4 unit test:** Extract the initials derivation as a pure function and unit-test independently. The E2E test validates rendering but the unit test validates algorithm edge cases (hyphens, single names, empty input, Unicode names) more thoroughly and faster.

---

## Test File Inventory

### New test files

| File | Type | ACs covered |
|------|------|-------------|
| `tests/e2e/test_card_layout.py` | e2e | AC1.1-AC1.5, AC2.1-AC2.8, AC3.1, AC3.2 |
| `tests/unit/test_author_initials.py` | unit | AC2.4 |

### Modified test files (Phase 3 — marker + expand)

| File | Changes |
|------|---------|
| `tests/e2e/annotation_helpers.py` | `expand_card`, `collapse_card` helpers; auto-expand in shared helpers |
| `tests/e2e/test_annotation_canvas.py` | `@pytest.mark.cards`, `expand_card` before tag-select |
| `tests/e2e/test_happy_path_workflow.py` | `@pytest.mark.cards`, `expand_card` before tag-select |
| `tests/e2e/test_history_tutorial.py` | `@pytest.mark.cards`, `expand_card` calls |
| `tests/e2e/test_law_student.py` | `@pytest.mark.cards`, `expand_card` calls |
| `tests/e2e/test_empty_tag_ux.py` | `@pytest.mark.cards` |
| `tests/e2e/test_organise_perf.py` | `@pytest.mark.cards` |
| `tests/e2e/test_translation_student.py` | `@pytest.mark.cards`, `expand_card` in local helper |
| `tests/e2e/test_annotation_drag.py` | `@pytest.mark.cards`, `expand_card` before sidebar tag-select |
| `tests/e2e/test_instructor_workflow.py` | `@pytest.mark.cards`, `expand_card` before tag-select |
| `tests/e2e/test_anonymous_sharing.py` | `@pytest.mark.cards` |

### Modified test files (Phase 4 — sleep removal)

All files in the Phase 3 list above, plus `tests/e2e/annotation_helpers.py`. See Phase 4 sleep inventory for per-file counts (57 total calls).
