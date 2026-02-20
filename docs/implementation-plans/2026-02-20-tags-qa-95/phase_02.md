# Annotation Tags QA Pass — Phase 2: Instructor Workflow E2E Subtests

**Goal:** Exercise the full instructor-creates-tags -> student-clones-and-uses flow via Playwright.

**Architecture:** New subtests appended to `test_instructor_workflow.py::TestInstructorWorkflow::test_full_course_setup`, leveraging the existing course/activity/student setup. Instructor creates tags via quick-create and management dialog, locks and reorders them. Student clones workspace and verifies tags work by using them — highlights, keyboard shortcuts at correct positions. SortableJS drag reorder tested via JS event injection (allowed exception to no-JS rule).

**Tech Stack:** Playwright, pytest-subtests, NiceGUI, SortableJS

**Scope:** Phase 2 of 6 from original design

**Codebase verified:** 2026-02-20

---

## Acceptance Criteria Coverage

This phase implements and tests:

### tags-qa-95.AC2: Instructor tag flow tested E2E
- **tags-qa-95.AC2.1 Success:** Instructor creates tag via quick-create ("+"), tag appears in toolbar
- **tags-qa-95.AC2.2 Success:** Instructor adds tags via management dialog, tags persist after dialog close
- **tags-qa-95.AC2.3 Success:** Instructor locks a tag, lock icon visible in management dialog
- **tags-qa-95.AC2.4 Success:** Instructor reorders tag groups, new order persists across dialog close/reopen
- **tags-qa-95.AC2.5 Success:** Instructor imports tags into a second activity's template workspace

### tags-qa-95.AC3: Student clone verification tested E2E
- **tags-qa-95.AC3.1 Success:** Student toolbar shows cloned tags with correct names after workspace clone
- **tags-qa-95.AC3.2 Success:** Locked tag shows lock icon and disabled fields in student management dialog
- **tags-qa-95.AC3.3 Success:** Student edits unlocked tag name, change persists via blur-save
- **tags-qa-95.AC3.4 Success:** Student reorders tags, new order persists across dialog close/reopen
- **tags-qa-95.AC3.5 Success:** Keyboard shortcut `2` creates highlight with tag at reordered position 2
- **tags-qa-95.AC3.6 Success:** Keyboard shortcut `3` creates highlight with tag at reordered position 3

---

## UAT

After this phase is complete, verify manually:

1. Run `uv run test-e2e -k test_full_course_setup --headed` and observe:
   - Instructor creates a tag via quick-create "+", tag appears in toolbar
   - Instructor opens management dialog, adds tags, locks one, reorders groups
   - Student navigates to cloned workspace, sees tags in toolbar
   - Student opens management dialog: locked tag shows lock icon and disabled fields
   - Student edits unlocked tag name, change persists on blur
   - Student uses keyboard shortcuts `2` and `3` — highlights created with correct tags at reordered positions
2. Confirm SortableJS drag reorder visually moves elements in `--headed` mode
3. Run `uv run test-e2e -k test_full_course_setup` (headless) — all subtests pass

---

<!-- START_TASK_1 -->
### Task 1: Add SortableJS drag helper to E2E test infrastructure

**Verifies:** None (infrastructure for AC2.4, AC3.4)

**Files:**
- Modify: `tests/e2e/annotation_helpers.py` — add `drag_sortable_item()` helper

**Implementation:**

Create a helper function that fires synthetic drag events for SortableJS reordering. SortableJS listens for `dragstart`, `dragenter`, `dragover`, and `drop` HTML5 drag events. The helper:

1. Locates source and target elements
2. Dispatches `dragstart` on source with `dataTransfer` set
3. Dispatches `dragenter` + `dragover` on target
4. Dispatches `drop` on target
5. Dispatches `dragend` on source

```python
async def drag_sortable_item(page: Page, source_locator: Locator, target_locator: Locator) -> None:
    """Simulate SortableJS drag-and-drop via synthetic JS events (allowed exception)."""
    # Get bounding boxes for coordinate calculation
    source_box = await source_locator.bounding_box()
    target_box = await target_locator.bounding_box()
    assert source_box and target_box

    await page.evaluate("""([sourceSelector, targetSelector]) => {
        const source = document.querySelector(sourceSelector);
        const target = document.querySelector(targetSelector);
        if (!source || !target) throw new Error('Elements not found');

        const dt = new DataTransfer();
        source.dispatchEvent(new DragEvent('dragstart', {bubbles: true, dataTransfer: dt}));
        target.dispatchEvent(new DragEvent('dragenter', {bubbles: true, dataTransfer: dt}));
        target.dispatchEvent(new DragEvent('dragover', {bubbles: true, dataTransfer: dt}));
        target.dispatchEvent(new DragEvent('drop', {bubbles: true, dataTransfer: dt}));
        source.dispatchEvent(new DragEvent('dragend', {bubbles: true, dataTransfer: dt}));
    }""", [await _to_selector(source_locator), await _to_selector(target_locator)])
```

The exact JS may need adjustment based on SortableJS's event handling. The implementor should test with `--headed` mode to verify the drag visually works.

**Fallback strategy:** If synthetic HTML5 drag events do not trigger SortableJS's reorder (SortableJS may use pointer events or touch events internally), fall back to:
1. Try Playwright's native `drag_to()` method with `force=True`
2. If still failing, use `page.evaluate()` to call SortableJS's programmatic API directly: `Sortable.get(el).sort(newOrder)` and dispatch the `end` event manually

Note: need a way to convert Playwright Locator to a CSS selector string for `page.evaluate()`. Options:
- Use `data-testid` selectors (Phase 1 adds these)
- Pass element handles via `evaluate_handle`

Preferred approach: use `data-testid` selectors directly in the evaluate call, not Locator conversion.

**Verification:**

Run: `uv run pytest tests/e2e/annotation_helpers.py --co -q` (confirm no import errors)

**Commit:** `feat: add SortableJS drag helper for E2E tests`
<!-- END_TASK_1 -->

<!-- START_SUBCOMPONENT_A (tasks 2-3) -->
<!-- START_TASK_2 -->
### Task 2: Instructor tag subtests — create, lock, reorder, import

**Verifies:** tags-qa-95.AC2.1, tags-qa-95.AC2.2, tags-qa-95.AC2.3, tags-qa-95.AC2.4, tags-qa-95.AC2.5

**Files:**
- Modify: `tests/e2e/test_instructor_workflow.py` — add subtests after existing subtest #9

**Implementation:**

Append new subtests to `test_full_course_setup()` after the existing `student_clones_and_sees_content` subtest. At this point:
- Instructor browser context is authenticated
- Course exists with 1 week, 1 activity ("Annotate Becky")
- Template workspace has content
- Student is enrolled

**Note:** The template workspace currently has the 10 seeded tags from Phase 1's `seed_tags=True` default. The instructor subtests will add MORE tags beyond the seeded set, creating a custom tag configuration for the clone verification.

New subtests (each wrapped in `with subtests.test(msg="..."):`):

**Subtest: `instructor_opens_template_workspace`**
- Navigate to template workspace (click "Edit Template" button on the activity)
- Wait for `tag-toolbar` to be visible

**Subtest: `instructor_creates_tag_via_quick_create`** (AC2.1)
- Click the "+" button: `page.locator("[data-testid='tag-toolbar']").get_by_role("button").filter(has_text="add")` or locate by tooltip "Create new tag"
- Fill tag name "Jurisdiction" in the quick-create dialog
- Select a color from preset palette
- Click "Create"
- Assert tag appears in toolbar: `expect(page.locator("[data-testid='tag-toolbar']")).to_contain_text("Jurisdiction")`

**Subtest: `instructor_adds_tags_via_management`** (AC2.2)
- Click gear icon: locate by tooltip "Manage tags"
- In management dialog (`[data-testid='tag-management-dialog']`):
  - Click "+ Add tag" within Ungrouped section
  - Fill "Facts" in the new tag name input
  - Click away (blur-save)
  - Click "+ Add tag" again
  - Fill "Holding" in the new tag name input
  - Click away (blur-save)
- Click "Done"
- Assert both tags appear in toolbar

**Subtest: `instructor_locks_tag`** (AC2.3)
- Open management dialog (gear icon)
- Find the "Jurisdiction" tag row
- Click lock toggle button
- Assert lock icon changes to locked state
- Click "Done"
- Reopen management dialog
- Assert "Jurisdiction" still shows lock icon

**Subtest: `instructor_reorders_tag_groups`** (AC2.4)
- Open management dialog
- Use `drag_sortable_item()` to move a group to a new position
- Click "Done"
- Reopen management dialog
- Assert groups appear in new order

**Subtest: `instructor_imports_tags`** (AC2.5)
- Navigate back to course page
- Add a second activity: `add_activity(page, title="Second Activity")`
- Click "Create Template" for the second activity
- Fill template workspace with content
- Open management dialog on the second activity's template
- Use import section: select first activity from dropdown, click "Import"
- Assert imported tags appear in toolbar

**Testing:**

Each subtest is a `with subtests.test()` checkpoint — Playwright assertions via `expect()`. If a subtest fails, subsequent subtests still attempt to run (pytest-subtests behaviour).

**Verification:**

Run: `uv run test-e2e -k test_full_course_setup`
Expected: All existing + new instructor subtests pass

**Commit:** `test: add instructor tag E2E subtests (create, lock, reorder, import)`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Student clone verification subtests

**Verifies:** tags-qa-95.AC3.1, tags-qa-95.AC3.2, tags-qa-95.AC3.3, tags-qa-95.AC3.4, tags-qa-95.AC3.5, tags-qa-95.AC3.6

**Files:**
- Modify: `tests/e2e/test_instructor_workflow.py` — add student subtests after instructor subtests

**Implementation:**

After the instructor subtests, create a new student browser context to verify the clone. The student was already enrolled in the course by existing subtest #8.

**Context setup:**
- Create new browser context for student
- Authenticate as student via mock auth
- Navigate to `/courses/{course_id}`
- Click "Start Activity" on "Annotate Becky" activity
- Wait for redirect to `/annotation?workspace_id=...`
- Wait for tag toolbar to be visible

**Subtest: `student_sees_cloned_tags`** (AC3.1)
- Assert tag toolbar contains expected tag names from the instructor's configuration
- Assert correct number of tag buttons

**Subtest: `student_locked_tag_readonly`** (AC3.2)
- Open management dialog (gear icon)
- Find "Jurisdiction" tag row (which instructor locked)
- Assert lock icon visible
- Assert name input is disabled/readonly
- Click "Done"

**Subtest: `student_edits_unlocked_tag`** (AC3.3)
- Open management dialog
- Find "Facts" tag row (unlocked)
- Clear name input, type "Key Facts"
- Click away (blur-save)
- Click "Done"
- Reopen management dialog
- Assert name is "Key Facts" (persisted via blur-save)
- Click "Done"

**Subtest: `student_reorders_tags`** (AC3.4)
- Open management dialog
- Use `drag_sortable_item()` to move "Holding" above "Key Facts" within the group
- Click "Done"
- Reopen management dialog
- Assert "Holding" appears before "Key Facts"
- Click "Done"

**Subtest: `student_highlights_with_keyboard_shortcuts`** (AC3.5, AC3.6)
- Select some text in the document using `select_chars()` helper
- Press key "2" on keyboard
- Assert a highlight is created with the tag at reordered position 2 (should be "Holding" after reorder)
- Select different text
- Press key "3"
- Assert highlight uses tag at position 3 (should be "Key Facts" after reorder)

The keyboard shortcut mapping is index-based: `state.tag_info_list[1]` → key "2", `state.tag_info_list[2]` → key "3". After reordering, the tag at position 2 in the toolbar should map to key "2".

**Testing:**

Each subtest uses `expect()` assertions for visibility, text content, and element state. Student context cleanup: close browser context after all subtests.

**Verification:**

Run: `uv run test-e2e -k test_full_course_setup`
Expected: All subtests pass including new student verification subtests

**Commit:** `test: add student clone verification E2E subtests`
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->
