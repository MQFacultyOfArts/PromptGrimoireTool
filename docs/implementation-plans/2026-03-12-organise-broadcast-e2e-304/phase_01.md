# Organise Broadcast E2E Test Implementation Plan

**Goal:** Add an E2E test proving broadcast auto-refresh on the Organise tab, and refactor the existing concurrent drag test to use broadcast instead of tab-switching workarounds.

**Architecture:** Test-only changes to `tests/e2e/test_annotation_drag.py`. New `TestBroadcastDrag` class for the broadcast test; refactor `TestConcurrentDrag` to remove polling loops. No production code changes.

**Tech Stack:** Playwright (sync API), pytest, existing `two_annotation_contexts` fixture

**Scope:** 1 phase from original design (phase 1 of 1)

**Codebase verified:** 2026-03-12

---

## Acceptance Criteria Coverage

This phase implements and tests:

### organise-broadcast-e2e-304.AC1: New broadcast drag test (DoD item 1)

- **organise-broadcast-e2e-304.AC1.1 Success:** Two browser contexts open to the same workspace, both on the Organise tab. Client A drags a highlight from Tag X's column to Tag Y's column. Client B sees the card appear in Tag Y's column within 10 seconds without any tab switch or page reload.
- **organise-broadcast-e2e-304.AC1.2 Success:** After the broadcast refresh, Client B's Tag X column no longer contains the dragged card.
- **organise-broadcast-e2e-304.AC1.3 Failure:** If the broadcast does not deliver within 10 seconds, the test fails with a clear timeout message identifying which client and which column.

### organise-broadcast-e2e-304.AC2: Refactor existing concurrent drag test (DoD item 2)

- **organise-broadcast-e2e-304.AC2.1 Success:** The two tab-switching polling loops in `test_concurrent_drag_produces_consistent_result` (lines 411-420 and 439-450) are replaced with direct `expect` assertions on column card visibility.
- **organise-broadcast-e2e-304.AC2.2 Success:** The refactored test still verifies the same invariant: both clients show consistent final state after concurrent cross-column drags.
- **organise-broadcast-e2e-304.AC2.3 Failure:** If the refactored test becomes flaky (fails >1 in 10 runs), revert and investigate whether the auto-refresh has a timing gap for concurrent operations.

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->

<!-- START_TASK_1 -->
### Task 1: Add TestBroadcastDrag.test_organise_auto_refreshes_on_remote_drag

**Verifies:** organise-broadcast-e2e-304.AC1.1, organise-broadcast-e2e-304.AC1.2, organise-broadcast-e2e-304.AC1.3

**Files:**
- Modify: `tests/e2e/test_annotation_drag.py` (append new class after `TestConcurrentDrag` at end of file)

**Implementation:**

Add a new `TestBroadcastDrag` class after the existing `TestConcurrentDrag` class (after line 470). The test uses the existing `two_annotation_contexts` fixture which provides `(page1, page2, workspace_id)` — two separate browser contexts authenticated to the same workspace.

**Test flow:**

1. Create one highlight on `page1` with tag Jurisdiction (index 0) using `create_highlight_with_tag(page1, *find_text_range(page1, "Alpha"), tag_index=0)` — "Alpha" is the first token in `_DRAG_CONTENT_HTML` (line 36)
2. Wait for broadcast to `page2`: `expect(page2.locator("[data-testid='annotation-card']")).to_have_count(1, timeout=10000)`
3. Both pages switch to Organise tab: `_switch_to_organise(page1)` and `_switch_to_organise(page2)`
4. Verify the card is in Jurisdiction column on both pages (use `_get_card_ids_in_column`)
5. On `page1`: get the card and its `data-highlight-id`, then drag it to the "Procedural History" column using `_get_sortable_for_tag(page1, "Procedural History")` and `card.drag_to(sortable)`
6. Wait for optimistic update on `page1`: `expect(proc_col_p1.locator(f'[data-highlight-id="{highlight_id}"]')).to_be_visible(timeout=5000)`
7. **Key assertion (AC1.1):** On `page2`, assert the card appears in Procedural History via broadcast auto-refresh — NO tab switching: `expect(proc_col_p2.locator(f'[data-highlight-id="{highlight_id}"]')).to_be_visible(timeout=10000)`
8. **Key assertion (AC1.2):** On `page2`, assert the card is gone from Jurisdiction: `expect(jurisdiction_col_p2.locator(f'[data-highlight-id="{highlight_id}"]')).to_be_hidden(timeout=5000)`

**Testing:**

Tests must verify each AC listed above:
- organise-broadcast-e2e-304.AC1.1: `page2` sees the card in Procedural History column within 10 seconds, without any tab switch or page reload
- organise-broadcast-e2e-304.AC1.2: `page2`'s Jurisdiction column no longer contains the dragged card after the broadcast
- organise-broadcast-e2e-304.AC1.3: Playwright's `expect().to_be_visible(timeout=10000)` raises `TimeoutError` with locator details if broadcast doesn't deliver within 10 seconds — this provides the clear timeout message

Use adjacent columns (Jurisdiction and Procedural History) to avoid horizontal scroll issues with Playwright's `drag_to()` — this pattern is already established in `TestDragBetweenColumns.test_drag_between_columns_changes_tag` (line 216).

The `two_annotation_contexts` fixture (conftest.py:248-302) creates a workspace via `_create_workspace_via_db()` which seeds the default tag set (Jurisdiction, Procedural History, Decision, Legal Issues, etc.) — the same tags used by `TestConcurrentDrag`. This ensures the Organise tab columns match the test's tag references.

Apply the `@pytestmark_db` decorator (defined at line 42) to skip when no test database is configured.

**Key patterns from existing tests (follow these exactly):**
- Column locator: `page.locator('[data-testid="tag-column"][data-tag-name="Jurisdiction"]')`
- Card in column: `column.locator(f'[data-highlight-id="{highlight_id}"]')`
- Sortable target: `_get_sortable_for_tag(page, "Procedural History")`

**Verification:**

Run: `uv run grimoire e2e run -k test_organise_auto_refreshes_on_remote_drag`
Expected: Test passes

**Commit:** `test: add broadcast auto-refresh E2E test for Organise tab (#304)`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Run new broadcast test 5x for flakiness

**Verifies:** organise-broadcast-e2e-304.AC1.1, organise-broadcast-e2e-304.AC1.2, organise-broadcast-e2e-304.AC1.3 (reliability)

**Files:**
- None (verification only)

**Implementation:**

No code changes. Run the new test 5 times to check for flakiness before proceeding to the refactor.

**Verification:**

Run: `uv run grimoire e2e run -k test_organise_auto_refreshes_on_remote_drag --count 5`
Expected: All 5 runs pass. If any fail, investigate before proceeding to Task 3.

If `--count` is not available, run the test 5 times manually:
```bash
for i in 1 2 3 4 5; do uv run grimoire e2e run -k test_organise_auto_refreshes_on_remote_drag || break; done
```

**Commit:** None (no code changes)

<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-5) -->

<!-- START_TASK_3 -->
### Task 3: Refactor test_concurrent_drag_produces_consistent_result

**Verifies:** organise-broadcast-e2e-304.AC2.1, organise-broadcast-e2e-304.AC2.2

**Files:**
- Modify: `tests/e2e/test_annotation_drag.py:406-450` (replace polling loops with expect assertions)

**Implementation:**

Replace the two `while True` tab-switching polling loops with direct `expect` assertions. The broadcast auto-refresh path works (proven by the new test in Task 1).

**Change 1 — First polling loop (lines 406-420):**

Remove lines 406-420 (the comment, `import time`, and the `while True` loop that switches page2's tabs). Replace with direct `expect` assertions:

```python
# Wait for broadcast to Page 2 (auto-refresh via broadcast path)
decision_col_p2 = page2.locator(
    '[data-testid="tag-column"][data-tag-name="Decision"]'
)
expect(
    decision_col_p2.locator(f'[data-highlight-id="{card_x_id}"]')
).to_be_visible(timeout=10000)
```

**Change 2 — Second polling loop (lines 438-450):**

Remove lines 438-450 (the second `while True` loop that switches page1's tabs). Replace with direct `expect` assertions:

```python
# Wait for broadcast to Page 1 (auto-refresh via broadcast path)
proc_history_col_p1 = page1.locator(
    '[data-testid="tag-column"][data-tag-name="Procedural History"]'
)
expect(
    proc_history_col_p1.locator(f'[data-highlight-id="{card_y_id}"]')
).to_be_visible(timeout=10000)
```

**Change 3 — Remove dead code:**

The `import time` statement at line 409 is only used by the polling loops. After removing both loops, `import time` becomes dead code. Remove it.

Also remove the incorrect comment at line 407: _"The Organise tab doesn't auto-refresh for remote drags, so we must switch tabs to trigger a re-render from the CRDT state."_

**Preserved invariant (AC2.2):** The consistency assertions at lines 452-470 remain unchanged — both pages must agree on card positions in Jurisdiction, Decision, and Procedural History columns.

**Testing:**

Tests must verify each AC listed above:
- organise-broadcast-e2e-304.AC2.1: No `while True` loops, no `_switch_to_annotate`/`_switch_to_organise` tab-switching calls remain in the test method, no `import time` — only direct `expect` assertions
- organise-broadcast-e2e-304.AC2.2: The final consistency assertions (lines 452-470) are unchanged, verifying both clients show the same final state

**Verification:**

Run: `uv run grimoire e2e run -k test_concurrent_drag_produces_consistent_result`
Expected: Test passes

**Commit:** `refactor: replace tab-switching polling with broadcast expect in concurrent drag test (#304)`

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Run refactored concurrent drag test 5x for flakiness

**Verifies:** organise-broadcast-e2e-304.AC2.3 (flakiness check)

**Files:**
- None (verification only)

**Implementation:**

No code changes. Run the refactored concurrent drag test 5 times to verify it is not flaky per AC2.3.

**Verification:**

Run: `uv run grimoire e2e run -k test_concurrent_drag_produces_consistent_result --count 5`
Expected: All 5 runs pass.

If `--count` is not available:
```bash
for i in 1 2 3 4 5; do uv run grimoire e2e run -k test_concurrent_drag_produces_consistent_result || break; done
```

**If any run fails (AC2.3 failure):** Revert the refactor from Task 3 (`git checkout -- tests/e2e/test_annotation_drag.py` or `git revert`), report the failure pattern, and investigate whether the auto-refresh has a timing gap for concurrent operations. Do not proceed to Task 5 until the issue is resolved.

**Commit:** None (no code changes)

<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Run full E2E suite for regression check

**Verifies:** No regressions introduced

**Files:**
- None (verification only)

**Implementation:**

No code changes. Run the full E2E suite to verify no regressions.

**Verification:**

Run: `uv run grimoire e2e run`
Expected: All E2E tests pass. No tests should fail that weren't already failing before this work.

**Commit:** None (no code changes)

<!-- END_TASK_5 -->
<!-- END_SUBCOMPONENT_B -->

---

## UAT

UAT for this test-only work is the E2E test output itself. No manual browser testing is required — the automated tests exercise the exact user flow (two clients, broadcast drag, auto-refresh).

**Evidence required before PR:**
- `uv run grimoire test all` output showing all unit + integration tests pass
- `uv run grimoire e2e all` output showing all lanes pass (unit + NiceGUI + E2E)
- 5x flakiness runs for both the new test and the refactored test
- Present results to Brian for sign-off
