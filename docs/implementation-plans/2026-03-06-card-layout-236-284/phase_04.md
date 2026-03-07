# Annotation Card Layout — Phase 4: Sleep Removal in Card-Touching Tests

**Goal:** Replace all arbitrary `page.wait_for_timeout()` calls in card-touching E2E test files with state-based waits, following test-audit branch patterns.

**Architecture:** Three replacement strategies: (1) remove entirely where a subsequent `expect()` or `wait_for()` already provides adequate timeout, (2) replace with `element.wait_for(state="visible")`, `page.wait_for_function()`, or `expect(locator)` retry patterns, (3) for truly irreplaceable waits (tooltip fade-out, scroll animation), keep with an explanatory comment documenting why.

**Tech Stack:** Playwright sync API

**Scope:** Phase 4 of 4 from original design (phases 1-4)

**Codebase verified:** 2026-03-07

---

## Acceptance Criteria Coverage

This phase implements and tests:

### card-layout-236-284.AC5: Sleep removal in card-touching tests
- **card-layout-236-284.AC5.1 Success:** No `page.wait_for_timeout()` calls remain in card-touching test files
- **card-layout-236-284.AC5.2 Success:** All card-touching tests still pass after sleep replacement with state-based waits
- **card-layout-236-284.AC5.3 Success:** Waits use `element.wait_for(state="visible")`, `page.wait_for_function()`, or `expect(locator)` retry patterns

---

## Sleep Inventory

**57 total `wait_for_timeout()` calls across 8 files + annotation_helpers.py:**

| File | Count | Primary patterns |
|------|-------|-----------------|
| `test_annotation_drag.py` | 19 | Tab switches, CRDT propagation, drag settling |
| `test_instructor_workflow.py` | 14 | Tab switches, blur-save, import processing |
| `test_law_student.py` | 7 | Keyboard shortcuts, organise tab, locate button |
| `test_history_tutorial.py` | 5 | CRDT sync, tag change propagation |
| `test_empty_tag_ux.py` | 4 | Dialog dismiss, tooltip fade |
| `test_anonymous_sharing.py` | 1 | Card visibility after highlight |
| `test_organise_perf.py` | 1 | Between highlight creates |
| `annotation_helpers.py` | 7 | Setup, scroll, paste, share toggle |

**Files with zero sleeps (no work needed):** `test_annotation_canvas.py`, `test_happy_path_workflow.py`, `test_translation_student.py`

## Replacement Strategy Reference

The task-implementor should apply these patterns based on what the sleep guards:

| Sleep guards | Replacement pattern |
|-------------|-------------------|
| DOM element appearing | `locator.wait_for(state="visible", timeout=N)` |
| DOM element disappearing | `locator.wait_for(state="hidden", timeout=N)` |
| Text content appearing | `expect(locator).to_contain_text(text, timeout=N)` |
| Element count changing | `expect(locator).to_have_count(N, timeout=N)` |
| JS state becoming true | `page.wait_for_function("expression", timeout=N)` |
| Tab switch completing | `expect(tab_panel_locator).to_be_visible(timeout=N)` |
| CRDT sync between users | `expect(page2_locator).to_contain_text(expected, timeout=N)` |
| Animation frame | `page.wait_for_function("new Promise(r => requestAnimationFrame(r))")` |
| Tooltip fade-out | `expect(tooltip_locator).to_be_hidden(timeout=N)` or mouse move + `wait_for(state="hidden")` |
| Blur-save round trip | `expect(locator).to_have_value(expected, timeout=N)` or verify server state |
| Highlight creation | `page.locator("[data-testid='annotation-card']").nth(idx).wait_for(state="visible", timeout=N)` |

**Key principle:** Every sleep should be replaced by waiting for the *specific condition* the sleep was guarding. The timeout value on the replacement should be generous (5000-10000ms) since Playwright retries rapidly and only hits the timeout on genuine failure.

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->

<!-- START_TASK_1 -->
### Task 1: Remove sleeps from `annotation_helpers.py`

**Verifies:** card-layout-236-284.AC5.1, card-layout-236-284.AC5.3

**Files:**
- Modify: `tests/e2e/annotation_helpers.py` — 7 `wait_for_timeout()` calls

**Implementation:**

The 7 calls in `annotation_helpers.py` are in shared helpers used by many tests. Each must be replaced carefully:

1. **`scroll_to_char` (line 719):** `page.wait_for_timeout(500)` after `page.evaluate()` scroll. Guards scroll animation + card positioning update. Replace with animation frame wait:
   ```python
   page.wait_for_function("new Promise(r => requestAnimationFrame(r))")
   ```

2. **`select_text_range` (line 860):** `page.wait_for_timeout(200)` after `evaluate()` that creates selection and dispatches mouseup. Guards event propagation. Replace with waiting for tag toolbar to appear (mouseup triggers selection handler which shows toolbar):
   ```python
   page.locator("[data-testid='tag-toolbar']").wait_for(state="visible", timeout=5000)
   ```

3. **`_load_fixture_via_paste` (line 922):** `page.wait_for_timeout(100)` after clipboard write, before Ctrl+V. Guards clipboard write completing. Replace by removing — the `page.evaluate()` for clipboard write is synchronous from Playwright's perspective (it awaits the Promise).

4. **`_load_fixture_via_paste` (line 927):** `page.wait_for_timeout(500)` after Ctrl+V, before "Content pasted" check. Guards paste event processing. Remove — the following `expect(editor).to_contain_text("Content pasted", timeout=5000)` already retries with adequate timeout.

5. **`setup_workspace_with_content` (line 811):** `page.wait_for_timeout(200)` after `wait_for_text_walker`. Guards text walker fully ready. Remove — `wait_for_text_walker` already waits for `walkTextNodes` to be available, which is the actual readiness signal.

6. **`navigate_home_via_drawer` (line 693):** `page.wait_for_timeout(500)` after drawer button click. Guards drawer animation. Replace the sleep with `expect(home_link).to_be_visible(timeout=5000)` — keep the existing `expect()` assertion (it retries automatically and produces a clear assertion trace) and just remove the sleep that preceded it. If the `expect()` already exists on the next line, simply delete the sleep line.

7. **`toggle_share_with_class` (line 1017):** `page.wait_for_timeout(500)` after toggle click. Guards WebSocket propagation of share state. The function checks `aria-checked` before clicking and only clicks if not already `"true"`. Replace the sleep with verifying the toggle reached the expected state:
   ```python
   # The function already checks aria-checked before clicking, so after
   # clicking we know the expected state is "true"
   expect(toggle).to_have_attribute("aria-checked", "true", timeout=5000)
   ```
   Note: If `toggle_share_with_class` is ever extended to toggle *off*, the expected value would need to be parameterised. Currently the function only toggles on.

**Verification:**
Run: `uv run grimoire e2e run`
Expected: All E2E tests still pass (helpers are used broadly).

**Commit:** `refactor(e2e): replace sleeps with state-based waits in annotation helpers`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Remove sleeps from light files (≤7 calls each)

**Verifies:** card-layout-236-284.AC5.1, card-layout-236-284.AC5.2, card-layout-236-284.AC5.3

**Files:**
- Modify: `tests/e2e/test_history_tutorial.py` — 5 calls
- Modify: `tests/e2e/test_law_student.py` — 7 calls
- Modify: `tests/e2e/test_empty_tag_ux.py` — 4 calls
- Modify: `tests/e2e/test_organise_perf.py` — 1 call
- Modify: `tests/e2e/test_anonymous_sharing.py` — 1 call

**Implementation:**

For each file, the task-implementor should:
1. Read the file
2. Find every `wait_for_timeout()` call
3. Identify what it guards by reading surrounding code (2-3 lines before and after)
4. Apply the appropriate replacement from the strategy reference table above
5. Run the file's tests to verify

**Per-file guidance:**

**`test_history_tutorial.py` (5 calls):**
- CRDT sync waits (page2 seeing page1's changes): Replace with `expect(page2_locator).to_contain_text(expected, timeout=10000)`
- Tag change propagation: Replace with `expect(tag_select).to_contain_text("Procedural History", timeout=10000)`

**`test_law_student.py` (7 calls):**
- After keyboard shortcut (Ctrl+C): Replace with clipboard content verification or `page.wait_for_function()` checking clipboard state
- Before/after no-highlight checks: Replace with `expect(card_locator).to_have_count(expected, timeout=5000)`
- After letter key press (toolbar dismiss): Replace with `expect(toolbar).to_be_hidden(timeout=5000)`
- Before organise card check: Replace with `expect(organise_card_locator).to_have_count(expected, timeout=5000)`
- After locate button click: Replace with `page.wait_for_function("new Promise(r => requestAnimationFrame(r))")` for scroll animation

**`test_empty_tag_ux.py` (4 calls):**
- After dialog cancel before card count: Replace with dialog `wait_for(state="hidden")` then `expect(cards).to_have_count(0, timeout=5000)`
- Tooltip dismiss (2 calls): Replace with `page.mouse.move(0, 0)` then `expect(tooltip_locator).to_be_hidden(timeout=5000)`
- Between operations: Remove if followed by expect with timeout

**`test_organise_perf.py` (1 call):**
- Between highlight creates (line 87): Replace with `page.locator("[data-testid='annotation-card']").nth(i).wait_for(state="visible", timeout=5000)` — wait for the card to appear before creating the next highlight

**`test_anonymous_sharing.py` (1 call):**
- After highlight creation: Replace with card visibility wait

**Verification:**
Run: `uv run grimoire e2e cards`
Expected: All tests in these files pass.

**Commit:** `refactor(e2e): replace sleeps with state-based waits in light test files`

<!-- END_TASK_2 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->

<!-- START_TASK_3 -->
### Task 3: Remove sleeps from `test_annotation_drag.py` (19 calls)

**Verifies:** card-layout-236-284.AC5.1, card-layout-236-284.AC5.2, card-layout-236-284.AC5.3

**Files:**
- Modify: `tests/e2e/test_annotation_drag.py`

**Implementation:**

This file has the highest sleep count. Common patterns:

1. **Tab switch sleeps** (~6 calls): After clicking Organise/Annotate tab, sleep before interacting. Replace with waiting for the target tab panel content to be visible:
   ```python
   # Instead of: page.wait_for_timeout(500)
   expect(page.get_by_test_id("organise-panel")).to_be_visible(timeout=5000)
   ```

2. **After highlight creation** (~4 calls): Sleep before checking card count or creating next highlight. Replace with card count/visibility wait:
   ```python
   page.locator("[data-testid='annotation-card']").nth(expected).wait_for(state="visible", timeout=5000)
   ```

3. **After drag operation** (~5 calls): Sleep for CRDT propagation between users. Replace with verifying the expected state on page2:
   ```python
   expect(page2.locator("[data-testid='organise-card']").first).to_contain_text(expected_tag, timeout=10000)
   ```

4. **After reorder drag** (~4 calls): Sleep for sort order to update. Replace with verifying the new order:
   ```python
   expect(page.locator("[data-testid='organise-card']").first).to_contain_text(expected_first_tag, timeout=5000)
   ```

The task-implementor should read each sleep's context carefully — some guard multi-user CRDT propagation which needs generous timeouts (10000ms).

**Verification:**
Run: `uv run grimoire e2e cards -k "drag"`
Expected: All drag tests pass.

**Commit:** `refactor(e2e): replace sleeps with state-based waits in drag tests`

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Remove sleeps from `test_instructor_workflow.py` (14 calls)

**Verifies:** card-layout-236-284.AC5.1, card-layout-236-284.AC5.2, card-layout-236-284.AC5.3

**Files:**
- Modify: `tests/e2e/test_instructor_workflow.py`

**Implementation:**

Common patterns in this file:

1. **Tab switch sleeps** (~4 calls): After clicking Activity/Week/Course tabs. Replace with target panel visibility:
   ```python
   expect(page.get_by_test_id("target-panel")).to_be_visible(timeout=5000)
   ```

2. **Blur-save round trip** (~3 calls): After blurring an input that triggers WebSocket save. Replace with verifying the value persisted — either by re-reading the input value or checking a status indicator:
   ```python
   # After blur, verify the value is still there (confirms save completed)
   expect(input_locator).to_have_value(expected_value, timeout=5000)
   ```

3. **Import processing** (~2 calls): After importing content, sleep before checking results. Replace with waiting for the imported content to appear:
   ```python
   expect(page.locator("[data-testid='expected-element']")).to_be_visible(timeout=10000)
   ```

4. **After navigation** (~3 calls): Sleep after page navigation. Replace with waiting for target content:
   ```python
   page.wait_for_url(expected_url_pattern, timeout=10000)
   ```

5. **After student highlight creation** (~2 calls): Sleep before checking tag-select. Replace with card visibility wait + expand:
   ```python
   card.wait_for(state="visible", timeout=5000)
   expand_card(student_page, card_index)
   ```

**Verification:**
Run: `uv run grimoire e2e cards -k "instructor"`
Expected: All instructor workflow tests pass.

**Commit:** `refactor(e2e): replace sleeps with state-based waits in instructor workflow test`

<!-- END_TASK_4 -->

<!-- END_SUBCOMPONENT_B -->

<!-- START_TASK_5 -->
### Task 5: Verify zero sleeps remain and all tests pass

**Verifies:** card-layout-236-284.AC5.1, card-layout-236-284.AC5.2

**Files:**
- No file changes — verification only

**Implementation:**

1. Search for remaining `wait_for_timeout` calls:
   ```bash
   grep -rn "wait_for_timeout" tests/e2e/test_annotation_canvas.py tests/e2e/test_happy_path_workflow.py tests/e2e/test_history_tutorial.py tests/e2e/test_law_student.py tests/e2e/test_empty_tag_ux.py tests/e2e/test_organise_perf.py tests/e2e/test_translation_student.py tests/e2e/test_annotation_drag.py tests/e2e/test_instructor_workflow.py tests/e2e/test_anonymous_sharing.py tests/e2e/annotation_helpers.py
   ```
   Expected: Zero matches.

2. Run full card test suite:
   ```bash
   uv run grimoire e2e cards
   ```
   Expected: All tests pass.

3. Run full E2E suite to verify no regressions in non-card tests:
   ```bash
   uv run grimoire e2e run
   ```
   Expected: All tests pass.

**Commit:** No commit — verification only.

<!-- END_TASK_5 -->

---

## UAT Steps

1. [ ] Run: `grep -rn "wait_for_timeout" tests/e2e/test_annotation_canvas.py tests/e2e/test_happy_path_workflow.py tests/e2e/test_history_tutorial.py tests/e2e/test_law_student.py tests/e2e/test_empty_tag_ux.py tests/e2e/test_organise_perf.py tests/e2e/test_translation_student.py tests/e2e/test_annotation_drag.py tests/e2e/test_instructor_workflow.py tests/e2e/test_anonymous_sharing.py tests/e2e/annotation_helpers.py` — verify zero matches
2. [ ] Run: `uv run grimoire e2e cards` — verify all card-touching tests pass
3. [ ] Run: `uv run grimoire e2e run` — verify full E2E suite passes (no regressions)
4. [ ] Run: `uv run complexipy src/promptgrimoire/pages/annotation/cards.py --max-complexity-allowed 15` — verify all functions ≤ 15 cognitive complexity (card-layout-236-284.AC6.1, AC6.3). This checks that Phase 1 spike code meets complexity requirements.
5. [ ] Run: `uv run complexipy src/promptgrimoire/pages/annotation/ --max-complexity-allowed 15` — verify no function in any annotation page file exceeds 15 (card-layout-236-284.AC6.2)

## Evidence Required
- [ ] grep output showing zero `wait_for_timeout` matches
- [ ] `uv run grimoire e2e cards` output showing all tests pass
- [ ] `uv run grimoire e2e run` output showing no regressions
- [ ] complexipy output showing all functions in `cards.py` ≤ 15 cognitive complexity
