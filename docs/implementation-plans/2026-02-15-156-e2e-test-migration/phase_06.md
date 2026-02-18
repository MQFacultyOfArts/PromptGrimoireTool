# E2E Test Migration Implementation Plan — Phase 6

**Goal:** Create persona-based E2E test for two history students collaborating in a tutorial.

**Architecture:** New `test_history_tutorial.py` with narrative subtests covering bidirectional real-time sync. Uses `two_authenticated_contexts` fixture from `conftest.py` which provides two separate browser contexts with distinct authenticated users viewing the same workspace. Sync verification uses annotation card visibility and text content assertions (not CSS property checks on char-index elements — those don't exist). Replaces skipped `test_annotation_sync.py` and `test_annotation_collab.py`.

**Tech Stack:** Playwright, pytest, pytest-subtests

**Scope:** Phase 6 of 8 from design plan

**Codebase verified:** 2026-02-15

---

## Acceptance Criteria Coverage

This phase implements and tests:

### 156-e2e-test-migration.AC3: Persona-based narrative tests (DoD 3, 4)
- **156-e2e-test-migration.AC3.4 Success:** `test_history_tutorial.py` exists and passes, covering bidirectional sync, comments, tag changes, concurrent edits, user count through user-leaves with subtests
- **156-e2e-test-migration.AC3.6 Success:** Each persona test uses `pytest-subtests` for discrete checkpoints

### 156-e2e-test-migration.AC4: E2E tests only verify user-visible outcomes (DoD 5)
- **156-e2e-test-migration.AC4.1 Success:** No persona test file contains `CSS.highlights` assertions (mechanism verification)
- **156-e2e-test-migration.AC4.2 Success:** No persona test file contains `page.evaluate()` calls that inspect internal DOM state (as opposed to user-visible text content)

### 156-e2e-test-migration.AC5: Parallelisable under xdist (DoD 6)
- **156-e2e-test-migration.AC5.1 Success:** Each test function creates its own workspace (no shared workspace state between tests)
- **156-e2e-test-migration.AC5.2 Success:** No test depends on database state created by another test

---

<!-- START_TASK_1 -->
### Task 1: Create test_history_tutorial.py

**Verifies:** 156-e2e-test-migration.AC3.4, 156-e2e-test-migration.AC3.6, 156-e2e-test-migration.AC4.1, 156-e2e-test-migration.AC4.2, 156-e2e-test-migration.AC5.1, 156-e2e-test-migration.AC5.2

**Files:**
- Create: `tests/e2e/test_history_tutorial.py`

**Implementation:**

Create a single narrative test class with one test method using `pytest-subtests` for discrete checkpoints. The test uses the `two_authenticated_contexts` fixture which provides two browser contexts with distinct authenticated users viewing the same workspace, pre-populated with content "Collaboration test word1 word2 word3 word4 word5".

**Fixture:** `two_authenticated_contexts` from `conftest.py` yields `(page1, page2, workspace_id, user1_email, user2_email)`. Both pages are authenticated and viewing the same workspace. Content is already loaded (Phase 1 fixes the `_textNodes` readiness wait in this fixture).

**Sync verification pattern:** When one user creates a highlight, the other user should see the annotation card appear within 10 seconds. Use `expect(page.locator("[data-testid='annotation-card']")).to_be_visible(timeout=10000)`. Do NOT verify sync via `CSS.highlights` or `page.evaluate()` on internal DOM state — use annotation card visibility (user-visible outcome per AC4).

**Narrative flow with subtests:**

1. **`subtest: student_a_highlights_text`** — Student A (page1) uses `select_chars(page1, 0, 4)` and `create_highlight_with_tag(page1, 0, 4, tag_index=0)` to highlight "Coll" with the first tag. Verify annotation card appears on page1: `expect(page1.locator("[data-testid='annotation-card']").first).to_be_visible()`.

2. **`subtest: highlight_syncs_to_student_b`** — Wait for Student B (page2) to see the annotation card: `expect(page2.locator("[data-testid='annotation-card']").first).to_be_visible(timeout=10000)`.

3. **`subtest: student_b_highlights_different_text`** — Student B (page2) highlights a different range (e.g. `create_highlight_with_tag(page2, 18, 23, tag_index=1)` — "word1") with a different tag. Verify annotation card count on page2 is 2.

4. **`subtest: second_highlight_syncs_to_student_a`** — Wait for Student A to see 2 annotation cards: `expect(page1.locator("[data-testid='annotation-card']")).to_have_count(2, timeout=10000)`.

5. **`subtest: student_a_adds_comment`** — Generate a UUID string. On page1, find the first annotation card, locate the comment input (`input[placeholder*='comment']`), fill with UUID string, click Post button. Verify comment text appears on page1's card.

6. **`subtest: comment_syncs_to_student_b`** — Wait for the UUID comment text to appear on page2's annotation card: `expect(page2.locator("[data-testid='annotation-card']").first).to_contain_text(uuid_string, timeout=10000)`.

7. **`subtest: student_a_changes_tag`** — On page1, find the first annotation card's tag dropdown (`.q-select` or `select` or `[role='combobox']`). Click to open, select a different tag option via `page1.get_by_role("option", name=re.compile("procedural", re.IGNORECASE))`. Wait briefly for CRDT sync.

8. **`subtest: tag_change_syncs_to_student_b`** — On page2, verify the annotation card shows the new tag name. Use `expect(page2.locator("[data-testid='annotation-card']").first).to_contain_text("Procedural", timeout=10000)` (or match the tag name used in subtest 7).

9. **`subtest: concurrent_highlights`** — Both students create highlights simultaneously:
   - Student A: `select_chars(page1, 24, 29)` then click tag button on page1
   - Student B: `select_chars(page2, 30, 35)` then click tag button on page2
   - Wait 2 seconds for sync. Verify both pages show the expected total card count (previous cards + 2 new ones): `expect(page1.locator("[data-testid='annotation-card']")).to_have_count(4, timeout=10000)` and same for page2.

10. **`subtest: user_count_shows_two`** — Verify user count badge shows 2 on both pages: `expect(page1.locator("[data-testid='user-count']")).to_contain_text("2", timeout=10000)` and same for page2.

11. **`subtest: student_b_leaves`** — Close page2's context (the fixture handles cleanup, but we can close page2 early). Wait briefly. Verify page1's user count drops to 1: `expect(page1.locator("[data-testid='user-count']")).to_contain_text("1", timeout=10000)`.

**Isolation:** The `two_authenticated_contexts` fixture creates its own workspace with unique user emails per test invocation. No shared database state.

**Constraints from AC4:** No `CSS.highlights` assertions. All sync verification uses Playwright `expect()` on annotation cards (user-visible text and visibility). No CSS property checks on highlight rendering.

**AC4.2 `page.evaluate()` guidance:** Calls that read user-visible content are permitted (e.g. `textContent`, `innerText`). Prohibited: inspecting `CSS.highlights`, `getComputedStyle()` for highlight colours, `window._textNodes`, `window._crdt*`, or other internal framework state.

**Testing:**
- 156-e2e-test-migration.AC3.4: `test_history_tutorial.py` exists and all subtests pass covering bidirectional sync, comments, tag changes, concurrent edits, user count, user-leaves
- 156-e2e-test-migration.AC3.6: Test uses `subtests.test(msg=...)` for each checkpoint
- 156-e2e-test-migration.AC4.1: `grep "CSS.highlights" tests/e2e/test_history_tutorial.py` returns no matches
- 156-e2e-test-migration.AC4.2: `grep "page.evaluate" tests/e2e/test_history_tutorial.py` returns no matches
- 156-e2e-test-migration.AC5.1: Fixture creates its own workspace per test
- 156-e2e-test-migration.AC5.2: Random auth emails, no cross-test DB dependency

**Verification:**
Run: `uv run pytest tests/e2e/test_history_tutorial.py -v -x --timeout=120 -m e2e`
Expected: All subtests pass; bidirectional sync works for highlights, comments, tag changes; concurrent edits preserved; user count updates on join/leave

**Commit:** `feat(e2e): add test_history_tutorial.py persona test (AC3.4)`
<!-- END_TASK_1 -->
