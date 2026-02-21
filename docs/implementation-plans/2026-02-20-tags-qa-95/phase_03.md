# Annotation Tags QA Pass — Phase 3: Law Student & Persona Subtests

**Goal:** Add keyboard shortcut isolation subtests and organise tab verification to existing persona tests.

**Architecture:** New subtests appended to `test_law_student.py::TestLawStudent::test_austlii_annotation_workflow`, placed after existing subtest #8 (`keyboard_shortcut_tag`) where browser context has highlights and comment inputs. Negative assertions use highlight count comparison with a wait to prove no highlight was created.

**Tech Stack:** Playwright, pytest-subtests

**Scope:** Phase 3 of 6 from original design

**Codebase verified:** 2026-02-20

**Status:** COMPLETE (2026-02-21). Task 1 delivered in `6e118c4`. Code review: zero issues. UAT: confirmed.

---

## Acceptance Criteria Coverage

This phase implements and tests:

### tags-qa-95.AC4: Keyboard shortcut isolation tested E2E
- **tags-qa-95.AC4.1 Success:** Typing `1` in comment input inserts the character "1" into the field
- **tags-qa-95.AC4.2 Failure:** Typing `1` in comment input does NOT create a new highlight
- **tags-qa-95.AC4.3 Failure:** Pressing `a` with text selected does NOT create a highlight
- **tags-qa-95.AC4.4 Success:** Organise tab has no "Untagged" column header

---

## UAT

After this phase is complete, verify manually:

1. Run `uv run test-e2e -k test_austlii_annotation_workflow --headed` and observe:
   - After highlights exist, click a comment input and type "1" — character appears in input, no new highlight created
   - Select text in document, press "a" — no highlight created (only digit keys 1-0 trigger highlights)
   - Navigate to Organise tab — no "Untagged" column header visible (all highlights have tags)
2. Run `uv run test-e2e -k test_austlii_annotation_workflow` (headless) — all 21 subtests pass

---

<!-- START_TASK_1 -->
### Task 1: Keyboard shortcut isolation subtests

**Verifies:** tags-qa-95.AC4.1, tags-qa-95.AC4.2, tags-qa-95.AC4.3, tags-qa-95.AC4.4

**Files:**
- Modify: `tests/e2e/test_law_student.py` — add subtests after existing subtest #8 (`keyboard_shortcut_tag`, line 197)

**Implementation:**

Insert new subtests after line 197 (end of `keyboard_shortcut_tag`). At this point:
- Workspace has content loaded (AustLII case)
- 10 seeded tags in toolbar (from Phase 1 `seed_tags=True`)
- 2 highlights exist (from subtests #3 and #5, both tagged)
- Comment input exists on annotation cards (from subtests #4 and #6)

**Subtest: `keyboard_shortcut_in_input_field`** (AC4.1 + AC4.2)

1. Count current highlights: `highlight_count = await page.locator("[data-testid='annotation-card']").count()`
2. Focus the first comment input: `comment_input = page.get_by_placeholder("Add comment").first`
3. Click the comment input to focus it
4. Type "1" via keyboard: `await comment_input.press("1")`
5. Assert character appears: `await expect(comment_input).to_have_value("1")` — but note the comment input may already have content from subtest #4. The implementor should check what state the input is in. If it already has a UUID comment, clear it first or use a different input.
6. Assert highlight count unchanged: `assert await page.locator("[data-testid='annotation-card']").count() == highlight_count`
7. Wait briefly to catch async highlight creation: `await page.wait_for_timeout(500)`
8. Re-assert count: `assert await page.locator("[data-testid='annotation-card']").count() == highlight_count`
9. Clear the input value for subsequent tests

**Subtest: `letter_key_no_highlight`** (AC4.3)

1. Count highlights
2. Select text in document using `select_chars()` helper (different range from existing selections)
3. Press "a" on keyboard: `await page.keyboard.press("a")`
4. Wait: `await page.wait_for_timeout(500)`
5. Assert highlight count unchanged — the JS handler only responds to digits '1234567890', not letters
6. Click elsewhere to deselect

**Subtest: `no_untagged_column_in_organise`** (AC4.4)

This can be verified within the existing subtest #9 (`organise_tab`) or as a separate subtest immediately after it. Add as a new subtest after line 212 (end of `organise_tab`):

1. The Organise tab is already visible (from subtest #9's navigation)
2. Assert no "Untagged" header: `await expect(page.locator("[data-testid='organise-columns']").get_by_text("Untagged")).not_to_be_visible()`
3. Both highlights have tags (indices 0 and 3), so the "Untagged" column (conditional at `organise.py:284`) should not render

**Exact subtest ordering after changes:**

| # | Subtest name | Source |
|---|-------------|--------|
| 1-8 | Existing subtests (#1 through `keyboard_shortcut_tag`) | Unchanged |
| 9 | `keyboard_shortcut_in_input_field` | NEW (AC4.1 + AC4.2) |
| 10 | `letter_key_no_highlight` | NEW (AC4.3) |
| 11 | `organise_tab` | Existing (was #9, now #11) |
| 12 | `no_untagged_column_in_organise` | NEW (AC4.4, needs Organise tab from #11) |
| 13-21 | Remaining existing subtests (was #10-#18, now shifted +3) | Unchanged |

The two keyboard subtests insert between existing #8 and #9. The `no_untagged_column_in_organise` subtest inserts immediately after the existing `organise_tab` subtest since it depends on the Organise tab being visible.

**Testing:**

All assertions use Playwright `expect()` for visibility/value checks and direct `count()` comparisons for highlight counts. The 500ms wait is a pragmatic buffer — NiceGUI's WebSocket roundtrip is typically <100ms.

**Verification:**

Run: `uv run test-e2e -k test_austlii_annotation_workflow`
Expected: All 21 subtests pass (18 existing + 3 new)

**Commit:** `test: add keyboard shortcut isolation E2E subtests`
<!-- END_TASK_1 -->
