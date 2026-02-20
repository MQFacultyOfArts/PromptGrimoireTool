# Test Requirements — tags-qa-95

Maps each acceptance criterion to its required automated test(s).

Note on AC counts: the design plan lists 9 previously-broken E2E files but phase_01.md corrects this to 10. The phase files are authoritative; AC1.1 uses 10.

---

## tags-qa-95.AC1: Broken E2E tests fixed

### tags-qa-95.AC1.1 Success: All 10 previously-broken E2E test files pass with tag seeding enabled

- **Type:** E2E
- **Location:** `tests/e2e/` (all 10 annotation E2E test files)
- **Verification:** Run `uv run test-e2e`. All 10 previously-broken test files pass after `seed_tags=True` is wired into `setup_workspace_with_content()` and `_load_fixture_via_paste()`. The suite must reach 0 failures/errors.
- **Phase:** 1, Task 2

### tags-qa-95.AC1.2 Success: `create_highlight_with_tag()` finds toolbar buttons at expected indices after seeding

- **Type:** E2E
- **Location:** `tests/e2e/` (any test that calls `create_highlight_with_tag()`)
- **Verification:** The helper selects toolbar buttons by numeric index (0–9). With 10 seeded tags present, every index from 0 to 9 resolves to a real button. Any test that previously failed because the toolbar was empty now passes — this is confirmed by the overall E2E suite result from AC1.1.
- **Phase:** 1, Task 2

### tags-qa-95.AC1.3 Success: Seeding is idempotent — calling `_seed_tags_for_workspace` twice does not create duplicate tags

- **Type:** E2E (operational verification via the suite, not a dedicated idempotency unit test)
- **Location:** `tests/e2e/annotation_helpers.py` — `_seed_tags_for_workspace()` uses `ON CONFLICT (id) DO NOTHING` SQL. The E2E tests themselves exercise this implicitly when Phase 2 instructor tests create tags on a workspace that already has seeded tags.
- **Verification:** After running `uv run test-e2e -k test_full_course_setup`, no duplicate tag rows exist for any workspace. Tag count in the toolbar does not exceed the expected number. No `UNIQUE` constraint errors appear in the server log.
- **Phase:** 1, Task 1

### tags-qa-95.AC1.4 Success: `setup_workspace_with_content(seed_tags=False)` creates workspace without tags

- **Type:** E2E
- **Location:** Any test that explicitly passes `seed_tags=False` to `setup_workspace_with_content()` or `_load_fixture_via_paste()`.
- **Verification:** Assert that the tag toolbar contains zero tag buttons (or that no tag toolbar is rendered) immediately after workspace creation with `seed_tags=False`. This can be a targeted Playwright assertion in the infrastructure smoke test or validated in headed mode during UAT. If no dedicated test file exists for this, it must be added as a short subtest in an appropriate E2E test file.
- **Phase:** 1, Task 2

---

## tags-qa-95.AC2: Instructor tag flow tested E2E

### tags-qa-95.AC2.1 Success: Instructor creates tag via quick-create ("+"), tag appears in toolbar

- **Type:** E2E
- **Location:** `tests/e2e/test_instructor_workflow.py::TestInstructorWorkflow::test_full_course_setup` — subtest `instructor_creates_tag_via_quick_create`
- **Verification:** Playwright clicks the "+" button, fills tag name "Jurisdiction", selects a colour, clicks "Create". Then asserts `expect(page.locator("[data-testid='tag-toolbar']")).to_contain_text("Jurisdiction")`.
- **Phase:** 2, Task 2

### tags-qa-95.AC2.2 Success: Instructor adds tags via management dialog, tags persist after dialog close

- **Type:** E2E
- **Location:** `tests/e2e/test_instructor_workflow.py::TestInstructorWorkflow::test_full_course_setup` — subtest `instructor_adds_tags_via_management`
- **Verification:** Playwright opens the management dialog, adds "Facts" and "Holding" via blur-save, closes the dialog. Asserts both tag names appear in the toolbar after the dialog closes.
- **Phase:** 2, Task 2

### tags-qa-95.AC2.3 Success: Instructor locks a tag, lock icon visible in management dialog

- **Type:** E2E
- **Location:** `tests/e2e/test_instructor_workflow.py::TestInstructorWorkflow::test_full_course_setup` — subtest `instructor_locks_tag`
- **Verification:** Playwright opens the management dialog, clicks the lock toggle on "Jurisdiction", asserts the lock icon changes to locked state, closes and reopens the dialog, asserts the lock icon is still visible on "Jurisdiction".
- **Phase:** 2, Task 2

### tags-qa-95.AC2.4 Success: Instructor reorders tag groups, new order persists across dialog close/reopen

- **Type:** E2E
- **Location:** `tests/e2e/test_instructor_workflow.py::TestInstructorWorkflow::test_full_course_setup` — subtest `instructor_reorders_tag_groups`
- **Verification:** Playwright uses `drag_sortable_item()` to move a group to a new position within the management dialog. Closes the dialog. Reopens it. Asserts groups appear in the new order (e.g., the moved group's header is at the expected DOM position).
- **Phase:** 2, Task 2

### tags-qa-95.AC2.5 Success: Instructor imports tags into a second activity's template workspace

- **Type:** E2E
- **Location:** `tests/e2e/test_instructor_workflow.py::TestInstructorWorkflow::test_full_course_setup` — subtest `instructor_imports_tags`
- **Verification:** Playwright creates a second activity, opens its template workspace's management dialog, uses the import section to select the first activity and clicks "Import". Asserts that the imported tag names appear in the second workspace's toolbar.
- **Phase:** 2, Task 2

---

## tags-qa-95.AC3: Student clone verification tested E2E

### tags-qa-95.AC3.1 Success: Student toolbar shows cloned tags with correct names after workspace clone

- **Type:** E2E
- **Location:** `tests/e2e/test_instructor_workflow.py::TestInstructorWorkflow::test_full_course_setup` — subtest `student_sees_cloned_tags`
- **Verification:** Student browser context navigates to the cloned workspace. Playwright asserts the tag toolbar contains the expected tag names (matching the instructor's configuration) and the correct number of tag buttons.
- **Phase:** 2, Task 3

### tags-qa-95.AC3.2 Success: Locked tag shows lock icon and disabled fields in student management dialog

- **Type:** E2E
- **Location:** `tests/e2e/test_instructor_workflow.py::TestInstructorWorkflow::test_full_course_setup` — subtest `student_locked_tag_readonly`
- **Verification:** Student opens the management dialog. Playwright asserts that the "Jurisdiction" tag row (locked by instructor) shows a lock icon (`[data-testid='tag-lock-icon-{id}']` visible) and that the name input is disabled or readonly.
- **Phase:** 2, Task 3

### tags-qa-95.AC3.3 Success: Student edits unlocked tag name, change persists via blur-save

- **Type:** E2E
- **Location:** `tests/e2e/test_instructor_workflow.py::TestInstructorWorkflow::test_full_course_setup` — subtest `student_edits_unlocked_tag`
- **Verification:** Student opens management dialog, clears the "Facts" name input, types "Key Facts", clicks away to trigger blur-save, closes the dialog, reopens it, and asserts the name field shows "Key Facts".
- **Phase:** 2, Task 3

### tags-qa-95.AC3.4 Success: Student reorders tags, new order persists across dialog close/reopen

- **Type:** E2E
- **Location:** `tests/e2e/test_instructor_workflow.py::TestInstructorWorkflow::test_full_course_setup` — subtest `student_reorders_tags`
- **Verification:** Student opens management dialog, uses `drag_sortable_item()` to move "Holding" above "Key Facts" within the group. Closes and reopens the dialog. Asserts "Holding" appears before "Key Facts" in the DOM order.
- **Phase:** 2, Task 3

### tags-qa-95.AC3.5 Success: Keyboard shortcut `2` creates highlight with tag at reordered position 2

- **Type:** E2E
- **Location:** `tests/e2e/test_instructor_workflow.py::TestInstructorWorkflow::test_full_course_setup` — subtest `student_highlights_with_keyboard_shortcuts`
- **Verification:** After the student reorders tags, Playwright selects text in the document using `select_chars()`, presses key "2", and asserts that a highlight is created using the tag now at position 2 (which should be "Holding" after reorder — verified by the highlight card showing the correct tag label or colour).
- **Phase:** 2, Task 3

### tags-qa-95.AC3.6 Success: Keyboard shortcut `3` creates highlight with tag at reordered position 3

- **Type:** E2E
- **Location:** `tests/e2e/test_instructor_workflow.py::TestInstructorWorkflow::test_full_course_setup` — subtest `student_highlights_with_keyboard_shortcuts`
- **Verification:** Same subtest as AC3.5. After creating the highlight for key "2", Playwright selects different text, presses "3", and asserts that a highlight is created with the tag at position 3 (should be "Key Facts" after reorder).
- **Phase:** 2, Task 3

---

## tags-qa-95.AC4: Keyboard shortcut isolation tested E2E

### tags-qa-95.AC4.1 Success: Typing `1` in comment input inserts the character "1" into the field

- **Type:** E2E
- **Location:** `tests/e2e/test_law_student.py::TestLawStudent::test_austlii_annotation_workflow` — subtest `keyboard_shortcut_in_input_field` (new subtest inserted after existing subtest #8)
- **Verification:** Playwright clicks a comment input to focus it, presses "1", and asserts `expect(comment_input).to_have_value("1")` (or that "1" appears in the field content).
- **Phase:** 3, Task 1

### tags-qa-95.AC4.2 Failure: Typing `1` in comment input does NOT create a new highlight

- **Type:** E2E
- **Location:** `tests/e2e/test_law_student.py::TestLawStudent::test_austlii_annotation_workflow` — subtest `keyboard_shortcut_in_input_field` (same subtest as AC4.1)
- **Verification:** Before pressing "1" in the comment input, Playwright records the current annotation card count. After pressing "1" and waiting 500 ms for any async highlight creation, it re-counts and asserts the count is unchanged.
- **Phase:** 3, Task 1

### tags-qa-95.AC4.3 Failure: Pressing `a` with text selected does NOT create a highlight

- **Type:** E2E
- **Location:** `tests/e2e/test_law_student.py::TestLawStudent::test_austlii_annotation_workflow` — subtest `letter_key_no_highlight` (new subtest inserted after `keyboard_shortcut_in_input_field`)
- **Verification:** Playwright records the current annotation card count, uses `select_chars()` to select text in the document, presses "a", waits 500 ms, and asserts the annotation card count is unchanged. (The JS handler only responds to digit keys '1234567890'.)
- **Phase:** 3, Task 1

### tags-qa-95.AC4.4 Success: Organise tab has no "Untagged" column header

- **Type:** E2E
- **Location:** `tests/e2e/test_law_student.py::TestLawStudent::test_austlii_annotation_workflow` — subtest `no_untagged_column_in_organise` (new subtest inserted after the existing `organise_tab` subtest)
- **Verification:** While the Organise tab is visible (from the preceding `organise_tab` subtest), Playwright asserts `expect(page.locator("[data-testid='organise-columns']").get_by_text("Untagged")).not_to_be_visible()`. All existing highlights have tags so the conditional "Untagged" column must not render.
- **Phase:** 3, Task 1

---

## tags-qa-95.AC5: Race condition fixed

### tags-qa-95.AC5.1 Success: `workspace` table has `next_tag_order` and `next_group_order` columns

- **Type:** Schema
- **Location:** `alembic/versions/{hash}_add_workspace_tag_order_counters.py` (Alembic migration) and `src/promptgrimoire/db/models.py` (Workspace model fields)
- **Verification:** Run `uv run alembic upgrade head`. Then query `SELECT next_tag_order, next_group_order FROM workspace LIMIT 1` — both columns exist and return integer values. The Workspace SQLModel class must define both fields. No dedicated schema test file is required for this AC; the migration's clean application and the model field declarations are the verification.
- **Phase:** 4, Task 1

### tags-qa-95.AC5.2 Success: `create_tag` atomically claims order index via counter column UPDATE+RETURNING

- **Type:** Integration
- **Location:** `tests/integration/test_tag_crud.py` — within `TestConcurrentTagCreation` class, method `test_concurrent_create_tag_distinct_order` (sequential aspect: two sequential `create_tag()` calls must each return a distinct `order_index`)
- **Verification:** Create a workspace. Call `create_tag()` twice in sequence. Assert that the returned tags have `order_index` 0 and 1 respectively. Confirm via the `UPDATE ... RETURNING next_tag_order - 1` pattern in `tags.py` that no `SELECT max(order_index)` remains.
- **Phase:** 4, Task 2

### tags-qa-95.AC5.3 Success: `create_tag_group` atomically claims order index via counter column UPDATE+RETURNING

- **Type:** Integration
- **Location:** `tests/integration/test_tag_crud.py` — within `TestConcurrentTagCreation` class, method `test_concurrent_create_tag_group_distinct_order`
- **Verification:** Create a workspace. Call `create_tag_group()` twice in sequence. Assert the returned groups have `order_index` 0 and 1 respectively.
- **Phase:** 4, Task 2

### tags-qa-95.AC5.4 Success: Two concurrent `create_tag` calls produce distinct `order_index` values

- **Type:** Integration
- **Location:** `tests/integration/test_tag_crud.py::TestConcurrentTagCreation::test_concurrent_create_tag_distinct_order`
- **Verification:** Use `asyncio.gather(create_tag(..., name="A"), create_tag(..., name="B"))` to issue two concurrent calls. Assert that `{tag_a.order_index, tag_b.order_index} == {0, 1}` — no duplicate indices. This is the primary regression test for the race condition.
- **Phase:** 4, Task 5

### tags-qa-95.AC5.5 Success: Counter correct after `reorder_tags` — subsequent create uses next available index

- **Type:** Integration
- **Location:** `tests/integration/test_tag_crud.py::TestConcurrentTagCreation::test_counter_correct_after_reorder_then_create`
- **Verification:** Create 3 tags (order_index 0, 1, 2). Call `reorder_tags()` with a new ordering. Call `create_tag()` for a 4th tag. Assert the 4th tag gets `order_index == 3` (the counter was synced to `len(tag_ids)` by the reorder function).
- **Phase:** 4, Task 3 (reorder sync) + Task 5 (integration test)

---

## tags-qa-95.AC6: Integration test gaps filled

### tags-qa-95.AC6.1 Success: `tag_group.color` CHECK constraint rejects invalid hex

- **Type:** Integration
- **Location:** `tests/integration/test_tag_schema.py::TestTagGroupColorConstraint::test_invalid_hex_rejected`
- **Verification:** Attempt to create a `TagGroup` with `color="red"` (or any non-hex value). Assert that `sqlalchemy.exc.IntegrityError` is raised (PostgreSQL CHECK constraint violation). The constraint is `ck_tag_group_color_hex`: `color IS NULL OR color ~ '^#[0-9a-fA-F]{6}$'`.
- **Phase:** 5, Task 2

### tags-qa-95.AC6.2 Success: `tag_group.color` CHECK constraint allows NULL

- **Type:** Integration
- **Location:** `tests/integration/test_tag_schema.py::TestTagGroupColorConstraint::test_null_color_allowed`
- **Verification:** Create a `TagGroup` with `color=None`. Assert it is created successfully (no exception). Optionally add a `test_valid_hex_accepted` companion to confirm `color="#FF0000"` also works.
- **Phase:** 5, Task 2

### tags-qa-95.AC6.3 Success: `update_tag` with `bypass_lock=True` succeeds on locked tag

- **Type:** Integration
- **Location:** `tests/integration/test_tag_crud.py::TestLockEnforcement::test_update_locked_tag_with_bypass_lock`
- **Verification:** Create a locked tag. Call `update_tag(tag.id, name="New Name", bypass_lock=True)`. Assert the return value is the updated `Tag` object with `name == "New Name"` (not `None`, no exception raised).
- **Phase:** 5, Task 3

### tags-qa-95.AC6.4 Success: `delete_tag` with `bypass_lock=True` succeeds on locked tag

- **Type:** Integration
- **Location:** `tests/integration/test_tag_crud.py::TestLockEnforcement::test_delete_locked_tag_with_bypass_lock`
- **Verification:** Create a locked tag. Call `delete_tag(tag.id, bypass_lock=True)`. Assert the return value is `True`. Verify the tag no longer exists by calling `get_tag(tag.id)` and asserting it returns `None`.
- **Phase:** 5, Task 3

### tags-qa-95.AC6.5 Success: `delete_tag` with nonexistent UUID returns False

- **Type:** Integration
- **Location:** `tests/integration/test_tag_crud.py::TestDeleteTag::test_delete_nonexistent_returns_false`
- **Verification:** Call `delete_tag(uuid4())` with a freshly generated UUID that was never inserted. Assert the return value is `False`.
- **Phase:** 5, Task 4

### tags-qa-95.AC6.6 Failure: `import_tags_from_activity` with nonexistent activity raises ValueError

- **Type:** Integration
- **Location:** `tests/integration/test_tag_crud.py::TestImportTagsFromActivity::test_import_nonexistent_activity_raises_value_error`
- **Verification:** Create a workspace (target). Call `import_tags_from_activity(uuid4(), workspace_id)` with a source activity UUID that does not exist. Assert `ValueError` is raised and that the message contains "not found" (or equivalent).
- **Phase:** 5, Task 4

### tags-qa-95.AC6.7 Success: `update_tag_group(color=None)` clears group colour

- **Type:** Integration
- **Location:** `tests/integration/test_tag_crud.py::TestUpdateTagGroup::test_update_color_to_none_clears`
- **Verification:** Create a `TagGroup` with `color="#FF0000"`. Call `update_tag_group(group.id, color=None)`. Reload the group from the database. Assert `group.color is None`.
- **Phase:** 5, Task 4

### tags-qa-95.AC6.8 Success: `update_tag_group` without `color` preserves existing colour

- **Type:** Integration
- **Location:** `tests/integration/test_tag_crud.py::TestUpdateTagGroup::test_update_without_color_preserves`
- **Verification:** Create a `TagGroup` with `color="#FF0000"`. Call `update_tag_group(group.id, name="New Name")` (no `color` argument). Reload the group from the database. Assert `group.color == "#FF0000"` (the sentinel pattern distinguishes "not passed" from `None`).
- **Phase:** 5, Task 4

### tags-qa-95.AC6.9 Failure: `reorder_tags` with unknown tag UUID raises ValueError

- **Type:** Integration
- **Location:** `tests/integration/test_tag_crud.py::TestReorderTags::test_reorder_with_unknown_tag_raises_value_error`
- **Verification:** Create 2 real tags. Call `reorder_tags([tag1.id, uuid4()])` where the second UUID does not exist. Assert `ValueError` is raised with "Tag" and "not found" (or equivalent) in the message.
- **Phase:** 5, Task 5

### tags-qa-95.AC6.10 Failure: `reorder_tag_groups` with unknown group UUID raises ValueError

- **Type:** Integration
- **Location:** `tests/integration/test_tag_crud.py::TestReorderTagGroups::test_reorder_with_unknown_group_raises_value_error`
- **Verification:** Create 2 real groups. Call `reorder_tag_groups([group1.id, uuid4()])` where the second UUID does not exist. Assert `ValueError` is raised with "TagGroup" and "not found" (or equivalent) in the message.
- **Phase:** 5, Task 5

---

## tags-qa-95.AC7: Refactor complete

### tags-qa-95.AC7.1 Success: `tag_management.py` split into 5 files, no file exceeds ~400 lines

- **Type:** Operational verification
- **Location:** `src/promptgrimoire/pages/annotation/` — the 5 files after the split: `tag_quick_create.py` (~165 lines), `tag_import.py` (~60 lines), `tag_management_rows.py` (~370 lines), `tag_management_save.py` (~130 lines), `tag_management.py` (~335 lines)
- **Verification:** Run `wc -l src/promptgrimoire/pages/annotation/tag_management*.py src/promptgrimoire/pages/annotation/tag_import.py src/promptgrimoire/pages/annotation/tag_quick_create.py`. Confirm no file exceeds approximately 400 lines. No automated test enforces this; it is a code review checkpoint.
- **Phase:** 6, Task 2

### tags-qa-95.AC7.2 Success: Import graph between tag management files is one-way

- **Type:** Operational verification
- **Location:** `src/promptgrimoire/pages/annotation/tag_management*.py`, `tag_import.py`, `tag_quick_create.py`
- **Verification:** Run `grep -r "from.*tag_management_save import\|from.*tag_management_rows import\|from.*tag_import import\|from.*tag_quick_create import\|from.*tag_management import" src/promptgrimoire/pages/annotation/tag_*.py` and confirm no cycles: `tag_management_save.py` must not import from any other tag_management file; `tag_management_rows.py` and `tag_import.py` import only from `tag_management_save.py`; `tag_quick_create.py` imports `_PRESET_PALETTE` from `tag_management.py` and `_refresh_tag_state` from `tag_management_save.py`; `tag_management.py` (orchestrator) imports from rows, save, and import only. No automated test enforces this; it is a code review and grep-verification checkpoint.
- **Phase:** 6, Task 2

### tags-qa-95.AC7.3 Success: `regionPriority()` dead code removed from `annotation-highlight.js`

- **Type:** Operational verification
- **Location:** `src/promptgrimoire/static/annotation-highlight.js`
- **Verification:** Run `grep -r "regionPriority" src/promptgrimoire/static/`. Assert no matches. The function body (lines 166-172) and its call site (line 156) must both be gone. The replacement inline expression `tagIdx !== undefined ? tagIdx : 0` takes its place. The existing `test_annotation_highlight_api` E2E test provides regression coverage that highlight rendering is unchanged.
- **Phase:** 6, Task 1

### tags-qa-95.AC7.4 Success: All existing tests pass after refactor

- **Type:** E2E + Integration + Unit (full suite)
- **Location:** `tests/` (all test files)
- **Verification:** Run `uv run test-all && uv run test-e2e`. Both commands must exit with 0 failures. Because the refactor is a pure move with no logic changes, all tests written in Phases 1-5 serve as regression coverage. No new tests are written for this AC specifically.
- **Phase:** 6, Tasks 1-4 (verified after each task)

### tags-qa-95.AC7.5 Success: Module count in `__init__.py` and package structure test updated

- **Type:** Unit
- **Location:** `tests/unit/test_annotation_package_structure.py::test_all_authored_modules_exist`
- **Verification:** Run `uv run pytest tests/unit/test_annotation_package_structure.py -v`. The test must pass with 17 authored modules listed in `_AUTHORED_MODULES` (13 original + 4 new: `tag_import.py`, `tag_management_rows.py`, `tag_management_save.py`, `tag_quick_create.py`). The `__init__.py` docstring must also be updated to state "17 authored modules".
- **Phase:** 6, Task 4
