# Annotation Tag Configuration -- Test Requirements

**Design:** `docs/design-plans/2026-02-17-95-annotation-tags.md`
**Implementation plans:** `docs/implementation-plans/2026-02-18-95-annotation-tags/phase_01.md` through `phase_06.md`

Every acceptance criterion from the design plan is mapped below to either an automated test or documented human verification.

---

## Automated Tests

### 95-annotation-tags.AC1: Data model and migration

---

#### `95-annotation-tags.AC1.1`

**AC text:** TagGroup table exists with workspace_id FK (CASCADE), name, order_index, created_at

**Test type:** Unit

**Test file:** `tests/unit/test_tag_models.py`

**Phase/task:** Phase 1 / Task 6

**Tests:**
- TagGroup has default UUID PK
- TagGroup has `name` field
- TagGroup `order_index` defaults to 0
- TagGroup has `created_at` field with timestamp

**Additional coverage:** `tests/unit/test_db_schema.py` -- updated to include `"tag_group"` in expected tables set and bump count from 10 to 12 (Phase 1 / Task 6).

---

#### `95-annotation-tags.AC1.2`

**AC text:** Tag table exists with workspace_id FK (CASCADE), group_id FK (SET NULL), name, description, color, locked, order_index, created_at

**Test type:** Unit

**Test file:** `tests/unit/test_tag_models.py`

**Phase/task:** Phase 1 / Task 6

**Tests:**
- Tag has default UUID PK
- Tag has `workspace_id` field
- Tag `group_id` nullable, defaults to None
- Tag has `name` field
- Tag `description` nullable, defaults to None
- Tag `color` is required
- Tag `locked` defaults to False
- Tag `order_index` defaults to 0
- Tag has `created_at` field with timestamp

**Additional coverage:** `tests/unit/test_db_schema.py` -- updated to include `"tag"` in expected tables set (Phase 1 / Task 6).

---

#### `95-annotation-tags.AC1.3`

**AC text:** Seed data: one "Legal Case Brief" TagGroup and 10 Tags with colorblind-accessible palette exist after migration

**Test type:** Manual verification (seed-data script)

**Phase/task:** Phase 1 / Task 8

**Note:** Seed data requires a running database with workspaces created by the `seed-data` script. The implementation plan explicitly calls for verification via `uv run seed-data` and checking console output. No automated test is planned because the seed function depends on the full `_seed_enrolment_and_weeks()` workflow which creates courses, weeks, activities, and template workspaces -- this is infrastructure-level setup, not unit-testable in isolation. See Human Verification section below.

---

#### `95-annotation-tags.AC1.4`

**AC text:** Activity has `allow_tag_creation` nullable boolean; Course has `default_allow_tag_creation` boolean (default TRUE)

**Test type:** Unit

**Test file:** `tests/unit/test_tag_models.py`

**Phase/task:** Phase 1 / Task 6

**Tests:**
- `Activity.allow_tag_creation` defaults to None
- `Course.default_allow_tag_creation` defaults to True

---

#### `95-annotation-tags.AC1.5`

**AC text:** PlacementContext resolves `allow_tag_creation` via tri-state inheritance (Activity explicit -> Course default)

**Test type:** Integration

**Test file:** `tests/integration/test_tag_schema.py`

**Phase/task:** Phase 1 / Task 7

**Tests (class `TestPlacementContextTagCreation`):**
- Inherit: Course `default_allow_tag_creation=True`, Activity `allow_tag_creation=None` -> context resolves to `True`. Also asserts `ctx.course_id == course.id`.
- Override False: Same course, Activity `allow_tag_creation=False` -> context resolves to `False`. Also asserts `ctx.course_id == course.id`.
- Override True: Course `default_allow_tag_creation=False`, Activity `allow_tag_creation=True` -> context resolves to `True`. Also asserts `ctx.course_id == course.id`.

---

#### `95-annotation-tags.AC1.6`

**AC text:** Deleting a Workspace CASCADEs to its TagGroup and Tag rows

**Test type:** Integration

**Test file:** `tests/integration/test_tag_schema.py`

**Phase/task:** Phase 1 / Task 7

**Tests (class `TestTagCascadeOnWorkspaceDelete`):**
- Create a workspace with a TagGroup and a Tag. Delete the workspace. Verify both TagGroup and Tag rows are gone.

---

#### `95-annotation-tags.AC1.7`

**AC text:** Deleting a TagGroup sets `group_id=NULL` on its Tags (SET NULL), does not delete Tags

**Test type:** Integration

**Test file:** `tests/integration/test_tag_schema.py`

**Phase/task:** Phase 1 / Task 7

**Tests (class `TestTagGroupSetNullOnDelete`):**
- Create a workspace with a TagGroup and a Tag in that group. Delete the TagGroup. Verify the Tag still exists with `group_id=None`.

---

### 95-annotation-tags.AC2: Tag CRUD

---

#### `95-annotation-tags.AC2.1`

**AC text:** Create tag with name, color, optional group_id, optional description

**Test type:** Integration

**Test file:** `tests/integration/test_tag_crud.py`

**Phase/task:** Phase 2 / Task 4

**Tests (class `TestCreateTag`):**
- Create a tag with name, color, group_id, and description. Verify all fields set, UUID generated, `created_at` set.
- Create a tag with only required fields (name, color). Verify `group_id` is None, `description` is None, `locked` is False, `order_index` is 0.

---

#### `95-annotation-tags.AC2.2`

**AC text:** Update tag name, color, description, group_id

**Test type:** Integration

**Test file:** `tests/integration/test_tag_crud.py`

**Phase/task:** Phase 2 / Task 4

**Tests (class `TestUpdateTag`):**
- Update tag name, color, description, group_id. Verify each field updated.
- Update with Ellipsis (not provided) leaves field unchanged.

---

#### `95-annotation-tags.AC2.3`

**AC text:** Delete tag removes the Tag row and all CRDT highlights referencing its UUID

**Test type:** Integration

**Test file:** `tests/integration/test_tag_crud.py`

**Phase/task:** Phase 2 / Task 5

**Tests (class `TestDeleteTagCrdtCleanup`):**
- Create a workspace with a tag. Build CRDT state with 3 highlights referencing that tag UUID. Delete the tag. Verify tag row gone, CRDT highlights removed, tag_order entry removed.
- Create a workspace with 2 tags. Add highlights for both. Delete only tag A. Verify tag A highlights gone, tag B highlights remain.
- Edge case: Tag with CRDT highlights but no tag_order entry. Delete tag. Verify cleanup succeeds without error (missing tag_order key silently skipped).

---

#### `95-annotation-tags.AC2.4`

**AC text:** Create and update TagGroup (name, order_index)

**Test type:** Integration

**Test file:** `tests/integration/test_tag_crud.py`

**Phase/task:** Phase 2 / Task 4

**Tests:**
- Class `TestCreateTagGroup`: Create a TagGroup with name and order_index. Verify fields and auto-generated UUID.
- Class `TestUpdateTagGroup`: Update TagGroup name and order_index. Verify changes.

---

#### `95-annotation-tags.AC2.5`

**AC text:** Delete TagGroup ungroups its tags (SET NULL)

**Test type:** Integration

**Test file:** `tests/integration/test_tag_crud.py`

**Phase/task:** Phase 2 / Task 4

**Tests (class `TestDeleteTagGroup`):**
- Create a TagGroup with a Tag in it. Delete the TagGroup. Verify TagGroup is gone, Tag still exists with `group_id=None`.

---

#### `95-annotation-tags.AC2.6`

**AC text:** Reorder tags within a group (update order_index)

**Test type:** Integration

**Test file:** `tests/integration/test_tag_crud.py`

**Phase/task:** Phase 2 / Task 5

**Tests (class `TestReorderTags`):**
- Create 3 tags with order_index 0, 1, 2. Call `reorder_tags([tag3.id, tag1.id, tag2.id])`. Verify order_index values are 0, 1, 2 matching the new order.

---

#### `95-annotation-tags.AC2.7`

**AC text:** Reorder groups within a workspace (update order_index)

**Test type:** Integration

**Test file:** `tests/integration/test_tag_crud.py`

**Phase/task:** Phase 2 / Task 5

**Tests (class `TestReorderTagGroups`):**
- Create 3 groups. Call `reorder_tag_groups()` with reversed order. Verify order_index values match new order.

---

#### `95-annotation-tags.AC2.8`

**AC text:** Update or delete a tag with `locked=True` is rejected

**Test type:** Integration

**Test file:** `tests/integration/test_tag_crud.py`

**Phase/task:** Phase 2 / Task 4

**Tests (class `TestLockEnforcement`):**
- Create tag with `locked=True`. Call `update_tag(tag.id, name="New")` -- raises `ValueError`.
- Create tag with `locked=True`. Call `delete_tag()` -- raises `ValueError`.
- Create tag with `locked=True`. Call `update_tag(tag.id, locked=False)` -- succeeds (lock toggle always permitted). Verify `tag.locked` is now False.
- Create tag with `locked=False`. Verify `update_tag()` and `delete_tag()` succeed.

---

#### `95-annotation-tags.AC2.9`

**AC text:** Create tag on workspace where `allow_tag_creation` resolves to False is rejected

**Test type:** Integration

**Test file:** `tests/integration/test_tag_crud.py`

**Phase/task:** Phase 2 / Task 4

**Tests (class `TestPermissionEnforcement`):**
- Create Course with `default_allow_tag_creation=False`, Activity with `allow_tag_creation=None` (inherits False). Call `create_tag()` -- raises `PermissionError`.
- Same setup but with `default_allow_tag_creation=True`. Call `create_tag()` -- succeeds.
- Same setup for `create_tag_group()` -- also raises `PermissionError` when denied.

---

### 95-annotation-tags.AC3: Import tags from another activity

---

#### `95-annotation-tags.AC3.1`

**AC text:** Import copies TagGroup and Tag rows from source activity's template workspace into target workspace

**Test type:** Integration

**Test file:** `tests/integration/test_tag_crud.py`

**Phase/task:** Phase 2 / Task 5

**Tests (class `TestImportTagsFromActivity`):**
- Create Activity A with 1 TagGroup and 3 Tags. Create Activity B. Call `import_tags_from_activity(A.id, B.template_workspace_id)`. Verify target workspace has 1 TagGroup and 3 Tags.

---

#### `95-annotation-tags.AC3.2`

**AC text:** Imported tags get new UUIDs (independent copies)

**Test type:** Integration

**Test file:** `tests/integration/test_tag_crud.py`

**Phase/task:** Phase 2 / Task 5

**Tests (class `TestImportTagsFromActivity`):**
- Verify imported Tags and TagGroup have different UUIDs from source.

---

#### `95-annotation-tags.AC3.3`

**AC text:** Imported tags preserve name, color, description, locked, group assignment, order

**Test type:** Integration

**Test file:** `tests/integration/test_tag_crud.py`

**Phase/task:** Phase 2 / Task 5

**Tests (class `TestImportTagsFromActivity`):**
- Verify imported tags preserve name, color, description, locked, order_index. Verify imported tags are assigned to the new TagGroup (not the source TagGroup's UUID).

---

### 95-annotation-tags.AC4: Workspace cloning propagates tags

---

#### `95-annotation-tags.AC4.1`

**AC text:** Cloning creates independent copies of all TagGroups in the student workspace

**Test type:** Integration

**Test file:** `tests/integration/test_tag_cloning.py`

**Phase/task:** Phase 3 / Task 3

**Tests (class `TestTagGroupCloning`):**
- Create activity with 2 TagGroups. Clone workspace. Verify clone has 2 TagGroups with same names and order_index but different UUIDs and the clone's workspace_id.

---

#### `95-annotation-tags.AC4.2`

**AC text:** Cloning creates independent copies of all Tags with group_id remapped to new TagGroup UUIDs

**Test type:** Integration

**Test file:** `tests/integration/test_tag_cloning.py`

**Phase/task:** Phase 3 / Task 3

**Tests (class `TestTagCloning`):**
- Create activity with 1 TagGroup and 3 Tags (2 grouped, 1 ungrouped). Clone workspace. Verify clone has 3 Tags with correct names, colors, descriptions. Verify grouped tags point to the clone's TagGroup UUID. Verify ungrouped tag has `group_id=None`.

---

#### `95-annotation-tags.AC4.3`

**AC text:** CRDT highlights in cloned workspace reference the new Tag UUIDs (not template UUIDs)

**Test type:** Integration

**Test file:** `tests/integration/test_tag_cloning.py`

**Phase/task:** Phase 3 / Task 4

**Tests (class `TestCrdtTagRemapping`):**
- Create activity with 2 tags. Add 3 highlights to template CRDT (2 for tag A, 1 for tag B). Clone workspace. Load clone CRDT. Verify all highlights have tags remapped to clone's Tag UUIDs.

**Additional backward-compat test (class `TestLegacyBriefTagPassthrough`):**
- Create activity with 1 tag. Add 2 highlights: one with UUID tag, one with legacy BriefTag string `"jurisdiction"`. Clone workspace. Verify UUID-tagged highlight remapped; legacy string highlight passes through unchanged.

---

#### `95-annotation-tags.AC4.4`

**AC text:** CRDT tag_order in cloned workspace uses new Tag UUIDs as keys

**Test type:** Integration

**Test file:** `tests/integration/test_tag_cloning.py`

**Phase/task:** Phase 3 / Task 4

**Tests (class `TestCrdtTagRemapping`):**
- Set `tag_order` on template with old Tag UUIDs as keys. Clone workspace. Verify `tag_order` keys are clone's Tag UUIDs. Verify highlight IDs in tag_order arrays are the clone's highlight IDs.

---

#### `95-annotation-tags.AC4.5`

**AC text:** Locked flag is preserved on cloned tags

**Test type:** Integration

**Test file:** `tests/integration/test_tag_cloning.py`

**Phase/task:** Phase 3 / Task 3

**Tests (class `TestTagCloning`):**
- Create activity with a tag where `locked=True`. Clone. Verify cloned tag has `locked=True`.

---

#### `95-annotation-tags.AC4.6`

**AC text:** Template with no tags clones cleanly (empty tag set)

**Test type:** Integration

**Test file:** `tests/integration/test_tag_cloning.py`

**Phase/task:** Phase 3 / Task 3

**Tests (class `TestEmptyTagClone`):**
- Create activity with no tags. Clone workspace. Verify clone has 0 TagGroups and 0 Tags. Verify clone completed successfully.

---

### 95-annotation-tags.AC5: Annotation page integration

---

#### `95-annotation-tags.AC5.1`

**AC text:** Tag toolbar renders from DB-backed tag list, not BriefTag enum

**Test type:** Integration

**Test file:** `tests/integration/test_workspace_tags.py`

**Phase/task:** Phase 4 / Task 7

**Tests (class `TestWorkspaceTags`):**
- Create a workspace with 3 tags. Call `workspace_tags(workspace_id)`. Verify returns 3 `TagInfo` instances with correct `name`, `colour`, and `raw_key` (UUID string). Verify order matches `order_index`.
- Create a workspace with 0 tags. Call `workspace_tags(workspace_id)`. Verify returns empty list.

---

#### `95-annotation-tags.AC5.2`

**AC text:** Keyboard shortcuts 1-0 map positionally to the first 10 tags in order

**Test type:** Human verification (E2E / manual)

**Note:** The keyboard handler logic is straightforward code (`key_to_index` dict mapping `"1"`-`"0"` to indices 0-9), but verifying it fires correctly requires browser-level keyboard event simulation. See Human Verification section below.

---

#### `95-annotation-tags.AC5.3`

**AC text:** Highlight cards display color from DB-backed tag data

**Test type:** Human verification (E2E / manual)

**Note:** Card colour rendering requires DOM inspection in a running NiceGUI application. The colour lookup logic (`tag_colours.get(tag_str, "#999999")`) is trivially correct from code review but cannot be verified without a browser. See Human Verification section below.

---

#### `95-annotation-tags.AC5.4`

**AC text:** Tag dropdown on highlight cards lists all workspace tags

**Test type:** Human verification (E2E / manual)

**Note:** Dropdown population uses `{ti.raw_key: ti.name for ti in state.tag_info_list}` which is correct by construction given `workspace_tags()` is tested. Rendering verification requires a browser. See Human Verification section below.

---

#### `95-annotation-tags.AC5.5`

**AC text:** Organise tab renders one column per tag (no untagged column)

**Test type:** Integration (partial)

**Test file:** `tests/integration/test_workspace_tags.py`

**Phase/task:** Phase 4 / Task 7

**Tests (class `TestWorkspaceTags`):**
- Verify `workspace_tags()` returns `TagInfo` instances matching the interface expected by `organise.py` (name, colour, raw_key fields populated). `organise.py` already consumes `list[TagInfo]` exclusively.

**Note:** Full rendering verification (visual column layout, absence of untagged column) requires human/E2E verification. See Human Verification section below.

---

#### `95-annotation-tags.AC5.6`

**AC text:** Respond tab renders tag-grouped highlights from DB-backed tags

**Test type:** Integration (partial)

**Test file:** `tests/integration/test_workspace_tags.py`

**Phase/task:** Phase 4 / Task 7

**Tests (class `TestWorkspaceTags`):**
- Same as AC5.5 -- `respond.py` already consumes `list[TagInfo]`. The integration test verifies `workspace_tags()` returns the correct `TagInfo` interface.

**Note:** Full rendering verification requires human/E2E verification. See Human Verification section below.

---

#### `95-annotation-tags.AC5.7`

**AC text:** PDF export uses tag colors from DB

**Test type:** Human verification

**Note:** PDF export requires running the full export pipeline (`export_annotation_pdf()`) which depends on TinyTeX and a running database. The code change is mechanical (`tag_colours` dict built from `state.tag_info_list` instead of `TAG_COLORS`). The existing `build_pdf_export` test fixture will be updated to accept `tag_colours: dict[str, str]` as a parameter (Phase 4 / Task 6), which verifies the dict is accepted. Visual colour verification in generated PDFs requires manual inspection. See Human Verification section below.

---

#### `95-annotation-tags.AC5.8`

**AC text:** Creating a highlight requires selecting a tag (no untagged highlights)

**Test type:** Human verification (E2E / manual)

**Note:** The code change is to remove the default fallback in `_add_highlight()` -- the `tag` parameter becomes required (`str` instead of `BriefTag | None`). This is a compile-time guarantee (type checker enforces it), but verifying that the UI prevents untagged highlight creation requires browser interaction. See Human Verification section below.

---

#### `95-annotation-tags.AC5.9`

**AC text:** Tag buttons truncate with ellipsis; full name shown on hover tooltip

**Test type:** Human verification (E2E / manual)

**Note:** CSS truncation (`max-width`, `text-overflow: ellipsis`) and NiceGUI `.tooltip()` are rendering-level concerns. See Human Verification section below.

---

#### `95-annotation-tags.AC5.10`

**AC text:** Tag toolbar wraps to two rows when needed (no horizontal scroll)

**Test type:** Human verification (E2E / manual)

**Note:** CSS `flex-wrap: wrap` behavior depends on viewport width and tag count. Requires visual verification. See Human Verification section below.

---

#### `95-annotation-tags.AC5.11`

**AC text:** `BriefTag`, `TAG_COLORS`, `TAG_SHORTCUTS` are deleted from codebase

**Test type:** Unit (codebase grep)

**Test file:** No dedicated test file -- verified by grep and type checker.

**Phase/task:** Phase 4 / Task 6

**Verification:**
- `grep -r "BriefTag\|TAG_COLORS\|TAG_SHORTCUTS" src/ tests/` returns no matches.
- `uvx ty check` passes (no unresolved references).
- `uv run test-debug` passes (no import errors from deleted symbols).

---

### 95-annotation-tags.AC6: Tag management UX -- quick create

---

#### `95-annotation-tags.AC6.1`

**AC text:** "+" button on toolbar opens quick-create dialog with name, color picker, optional group

**Test type:** Human verification (E2E / manual)

**Note:** Dialog rendering requires a running NiceGUI application. See Human Verification section below. The "+" button is wired in Phase 5 / Task 2.

---

#### `95-annotation-tags.AC6.2`

**AC text:** Creating a tag via quick-create applies it to the current text selection

**Test type:** Integration (workflow) + Human verification (UI)

**Test file:** `tests/integration/test_tag_management.py`

**Phase/task:** Phase 5 / Task 6

**Tests (class `TestQuickCreateWorkflow`):**
- Create tag via CRUD. Call `workspace_tags()` and verify it appears. Set up CRDT state and call `add_highlight(tag=raw_key)`, verify highlight stored with correct tag UUID.

**Note:** The full flow (text selection -> "+" button -> dialog -> highlight creation) requires E2E/manual verification. The integration test verifies the service-layer path.

---

#### `95-annotation-tags.AC6.3`

**AC text:** "+" button is hidden when `allow_tag_creation` resolves to False

**Test type:** Integration (gating logic) + Human verification (UI)

**Test file:** `tests/integration/test_tag_management.py`

**Phase/task:** Phase 5 / Task 6

**Tests (class `TestCreationGating`):**
- Course `default_allow_tag_creation=False`, Activity `allow_tag_creation=None`. Call `create_tag()` -- raises `PermissionError`. Change course default to True, call `create_tag()` -- succeeds.

**Note:** The button visibility (`on_add_click=None` when `allow_tag_creation` is False) is a UI rendering concern. The integration test verifies the underlying permission enforcement. Visual verification of button absence requires E2E/manual testing. See Human Verification section below.

---

### 95-annotation-tags.AC7: Tag management UX -- full dialog

---

#### `95-annotation-tags.AC7.1`

**AC text:** Gear button opens management dialog showing tags grouped by TagGroup

**Test type:** Human verification (E2E / manual)

**Phase/task:** Phase 5 / Task 5

**Note:** Dialog rendering and tag grouping layout require a running NiceGUI application. See Human Verification section below.

---

#### `95-annotation-tags.AC7.2`

**AC text:** Tags can be renamed, recolored, and given descriptions inline

**Test type:** Integration (CRUD) + Human verification (UI)

**Test file:** `tests/integration/test_tag_crud.py` (Phase 2 / Task 4, class `TestUpdateTag`)

**Note:** The CRUD operation (`update_tag(name=..., color=..., description=...)`) is tested in Phase 2. The inline editing UI (inputs, save button, re-render) requires E2E/manual verification. See Human Verification section below.

---

#### `95-annotation-tags.AC7.3`

**AC text:** Tags can be moved between groups or ungrouped

**Test type:** Integration (CRUD) + Human verification (UI)

**Test file:** `tests/integration/test_tag_crud.py` (Phase 2 / Task 4, class `TestUpdateTag`)

**Note:** `update_tag(group_id=new_group_id)` and `update_tag(group_id=None)` are tested in Phase 2. The group select dropdown in the management dialog requires E2E/manual verification. See Human Verification section below.

---

#### `95-annotation-tags.AC7.4`

**AC text:** Tags and groups can be reordered via drag

**Test type:** Integration (reorder logic) + Human verification (UI)

**Test file:** `tests/integration/test_tag_crud.py` (Phase 2 / Task 5, classes `TestReorderTags` and `TestReorderTagGroups`)

**Phase/task:** Phase 5 / Task 4 (drag UI wiring)

**Note:** `reorder_tags()` and `reorder_tag_groups()` are tested in Phase 2. The SortableJS drag interaction and event handling require E2E/manual verification. See Human Verification section below.

---

#### `95-annotation-tags.AC7.5`

**AC text:** Tag deletion shows highlight count and requires confirmation

**Test type:** Integration (delete + CRDT cleanup) + Human verification (UI)

**Test file:** `tests/integration/test_tag_management.py`

**Phase/task:** Phase 5 / Task 6

**Tests (class `TestDeleteWithCrdtCleanup`):**
- Create workspace with tag. Build CRDT state with 2 highlights. Delete tag. Verify `workspace_tags()` excludes deleted tag. Verify CRDT highlights removed.

**Note:** The confirmation dialog rendering and highlight count display require E2E/manual verification. See Human Verification section below.

---

#### `95-annotation-tags.AC7.6`

**AC text:** Group deletion moves tags to ungrouped (no highlight loss)

**Test type:** Integration

**Test file:** `tests/integration/test_tag_crud.py` (Phase 2 / Task 4, class `TestDeleteTagGroup`)

**Phase/task:** Phase 5 / Task 3 (UI wiring)

**Tests:**
- Delete TagGroup. Verify Tag still exists with `group_id=None`.

**Note:** The confirmation dialog in the management UI requires E2E/manual verification. The data-level behavior is fully tested.

---

#### `95-annotation-tags.AC7.7`

**AC text:** "Import tags from..." dropdown lists activities in course (instructor on template only)

**Test type:** Integration (import workflow) + Human verification (UI)

**Test file:** `tests/integration/test_tag_management.py`

**Phase/task:** Phase 5 / Task 6

**Tests (class `TestImportWorkflow`):**
- Create Activity A with 2 tags. Create Activity B with no tags. Call `import_tags_from_activity(A.id, B.template_workspace_id)`. Call `workspace_tags(B.template_workspace_id)`. Verify 2 tags appear with correct names and colours but different UUIDs.

**Note:** The dropdown listing activities, the instructor-only gating (`ctx.is_template and is_privileged_user(auth_user)`), and the UI trigger require E2E/manual verification. See Human Verification section below.

---

#### `95-annotation-tags.AC7.8`

**AC text:** Lock toggle available for instructors on template workspaces

**Test type:** Integration (lock toggle CRUD) + Human verification (UI)

**Test file:** `tests/integration/test_tag_crud.py` (Phase 2 / Task 4, class `TestLockEnforcement`)

**Phase/task:** Phase 5 / Task 4 (lock toggle UI)

**Tests:**
- `update_tag(tag.id, locked=True)` and `update_tag(tag.id, locked=False)` -- the lock toggle is always permitted on the `locked` field (Phase 2 refined lock guard).

**Note:** The UI switch rendering and instructor-only visibility require E2E/manual verification. See Human Verification section below.

---

#### `95-annotation-tags.AC7.9`

**AC text:** Locked tags show lock icon; edit/delete controls disabled for students

**Test type:** Human verification (E2E / manual)

**Phase/task:** Phase 5 / Task 3

**Note:** The lock icon rendering, `readonly`/`disabled` props on inputs, and student vs. instructor role differentiation are all UI rendering concerns. The underlying permission enforcement (`ValueError` on locked tag update/delete) is tested in Phase 2. See Human Verification section below.

---

### 95-annotation-tags.AC8: Activity settings + course defaults

---

#### `95-annotation-tags.AC8.1`

**AC text:** Activity settings dialog shows `allow_tag_creation` tri-state select

**Test type:** Integration (CRUD round-trip) + Human verification (UI)

**Test file:** `tests/integration/test_tag_settings.py`

**Phase/task:** Phase 6 / Task 3

**Tests:**
- Class `TestCreateActivityWithTagCreation`: Create activity with `allow_tag_creation=False`, verify persisted. Create with `None` (default), verify persisted.
- Class `TestUpdateActivityTagCreation`: Update to `False`, verify. Reset to `None` (inherit), verify. Update unrelated field without `allow_tag_creation`, verify unchanged (Ellipsis sentinel).

**Note:** The `ui.select` rendering in the activity settings dialog requires E2E/manual verification. See Human Verification section below.

---

#### `95-annotation-tags.AC8.2`

**AC text:** Course settings dialog shows `default_allow_tag_creation` switch

**Test type:** Integration (CRUD round-trip) + Human verification (UI)

**Test file:** `tests/integration/test_tag_settings.py`

**Phase/task:** Phase 6 / Task 3

**Tests (class `TestUpdateCourseDefaultTagCreation`):**
- Update `default_allow_tag_creation=False`, verify. Update to `True`, verify. Update unrelated field without `default_allow_tag_creation`, verify unchanged.

**Note:** The `ui.switch` rendering in the course settings dialog requires E2E/manual verification. See Human Verification section below.

---

#### `95-annotation-tags.AC8.3`

**AC text:** Activity `allow_tag_creation=NULL` inherits Course default

**Test type:** Integration

**Test file:** `tests/integration/test_tag_settings.py` and `tests/integration/test_tag_schema.py`

**Phase/task:** Phase 6 / Task 3 (round-trip via CRUD) and Phase 1 / Task 7 (direct PlacementContext)

**Tests:**
- Phase 1: `TestPlacementContextTagCreation` -- direct PlacementContext resolution.
- Phase 6: `TestTriStateInheritanceFromCrud` -- round-trip: update via CRUD, verify via PlacementContext. Course `default_allow_tag_creation=True`, Activity `allow_tag_creation=None` -> resolves True.

---

#### `95-annotation-tags.AC8.4`

**AC text:** Activity `allow_tag_creation=TRUE` overrides Course default FALSE

**Test type:** Integration

**Test file:** `tests/integration/test_tag_settings.py` and `tests/integration/test_tag_schema.py`

**Phase/task:** Phase 6 / Task 3 and Phase 1 / Task 7

**Tests:**
- Phase 1: `TestPlacementContextTagCreation` -- Activity `True` overrides Course `False`.
- Phase 6: `TestTriStateInheritanceFromCrud` -- same scenario via CRUD update round-trip.

---

#### `95-annotation-tags.AC8.5`

**AC text:** Activity `allow_tag_creation=FALSE` overrides Course default TRUE

**Test type:** Integration

**Test file:** `tests/integration/test_tag_settings.py` and `tests/integration/test_tag_schema.py`

**Phase/task:** Phase 6 / Task 3 and Phase 1 / Task 7

**Tests:**
- Phase 1: `TestPlacementContextTagCreation` -- Activity `False` overrides Course `True`.
- Phase 6: `TestTriStateInheritanceFromCrud` -- same scenario via CRUD update round-trip.

---

## Human Verification

### `95-annotation-tags.AC1.3` -- Seed data presence

**Why it cannot be automated:** Seed data requires the full `seed-data` CLI pipeline which creates courses, weeks, activities, and template workspaces in a running PostgreSQL database. This is infrastructure-level setup that depends on the full application context.

**Verification approach:**
1. Run `uv run seed-data` against a configured database.
2. Verify console output shows tag seeding messages (not "Tags exist" on first run).
3. Run `uv run seed-data` again. Verify "Tags exist" message (idempotent).
4. Inspect the database: verify 1 TagGroup named "Legal Case Brief" and 10 Tags with the expected names and colours exist on the template workspace.

---

### `95-annotation-tags.AC5.2` -- Keyboard shortcuts 1-0

**Why it cannot be automated:** Keyboard event handling requires a browser environment with NiceGUI's JavaScript bridge. The Python-side logic is a simple positional lookup, but verifying end-to-end keyboard -> highlight creation requires Playwright or manual testing.

**Verification approach:**
1. Open the annotation page with a workspace that has 10+ tags.
2. Select text in the document.
3. Press keys 1 through 0. Verify each creates a highlight with the corresponding positional tag.
4. Press keys for non-existent shortcuts (e.g., a letter key). Verify no highlight is created.

---

### `95-annotation-tags.AC5.3` -- Highlight card colours

**Why it cannot be automated:** Colour rendering is a visual DOM property.

**Verification approach:**
1. Open the annotation page with a workspace containing highlights with different tags.
2. Inspect highlight cards in the sidebar. Verify each card's colour indicator matches the tag's DB colour.
3. Change a tag's colour via the management dialog. Verify card colours update.

---

### `95-annotation-tags.AC5.4` -- Tag dropdown on cards

**Why it cannot be automated:** Dropdown rendering requires DOM inspection.

**Verification approach:**
1. Open the annotation page. Click a highlight card's tag dropdown.
2. Verify the dropdown lists all workspace tags by name.
3. Select a different tag. Verify the highlight's tag is updated in the CRDT and the card colour changes.

---

### `95-annotation-tags.AC5.5` -- Organise tab columns (full rendering)

**Why it cannot be automated (fully):** Column layout verification requires visual inspection. The data path is tested via `workspace_tags()`.

**Verification approach:**
1. Open the annotation page's Organise tab.
2. Verify one column per workspace tag. Verify no "Untagged" column exists.
3. Add a new tag via quick-create. Verify a new column appears.

---

### `95-annotation-tags.AC5.6` -- Respond tab rendering (full rendering)

**Why it cannot be automated (fully):** Tag-grouped rendering requires visual inspection.

**Verification approach:**
1. Open the annotation page's Respond tab.
2. Verify highlights are grouped by tag.
3. Verify tag names and colours match DB data.

---

### `95-annotation-tags.AC5.7` -- PDF export colours

**Why it cannot be automated (fully):** Visual colour verification in generated PDFs.

**Verification approach:**
1. Export a PDF from a workspace with multiple tagged highlights.
2. Open the PDF. Verify highlight colours match the DB-stored tag colours.
3. Change a tag colour, re-export. Verify the PDF reflects the new colour.

---

### `95-annotation-tags.AC5.8` -- No untagged highlights

**Why it cannot be automated:** Requires verifying the UI prevents creating highlights without a tag selection (the type signature enforces this at compile time, but the UX flow needs visual verification).

**Verification approach:**
1. Open the annotation page. Select text.
2. Verify that no highlight is created until a tag button is clicked or a keyboard shortcut is pressed.
3. Verify there is no "untagged" or default highlight mode.

---

### `95-annotation-tags.AC5.9` -- Tag button truncation and tooltip

**Why it cannot be automated:** CSS rendering behavior depends on viewport and font metrics.

**Verification approach:**
1. Create a tag with a long name (e.g., "Extremely Long Tag Name That Should Truncate").
2. Verify the toolbar button shows truncated text with ellipsis.
3. Hover over the button. Verify a tooltip shows the full tag name.

---

### `95-annotation-tags.AC5.10` -- Toolbar wraps to two rows

**Why it cannot be automated:** CSS flex-wrap behavior depends on viewport width.

**Verification approach:**
1. Create 15+ tags on a workspace.
2. Open the annotation page. Verify the tag toolbar wraps to multiple rows.
3. Verify there is no horizontal scrollbar on the toolbar.

---

### `95-annotation-tags.AC6.1` -- Quick-create dialog rendering

**Why it cannot be automated:** Dialog rendering requires a running NiceGUI application.

**Verification approach:**
1. Open the annotation page on a workspace where tag creation is allowed.
2. Click the "+" button on the toolbar.
3. Verify a dialog opens with: name input, colour picker (10 preset swatches + custom), optional group dropdown, Cancel and Create buttons.

---

### `95-annotation-tags.AC6.3` -- "+" button hidden when denied (UI)

**Why it cannot be automated (fully):** Button visibility is a rendering concern. The underlying permission is tested.

**Verification approach:**
1. Set an activity's `allow_tag_creation=False`.
2. Open the annotation page for a student workspace in that activity.
3. Verify the "+" button is not visible on the toolbar.
4. Set `allow_tag_creation=True`. Reload. Verify the "+" button appears.

---

### `95-annotation-tags.AC7.1` -- Management dialog rendering

**Why it cannot be automated:** Dialog layout and tag grouping are visual concerns.

**Verification approach:**
1. Click the gear button on the annotation toolbar.
2. Verify a dialog opens showing tags grouped by TagGroup, with an "Ungrouped" section.
3. Verify group headers show group names.

---

### `95-annotation-tags.AC7.2` -- Inline editing UI

**Why it cannot be automated:** Input field rendering and save-on-change behavior.

**Verification approach:**
1. Open the management dialog. Edit a tag's name inline. Click save.
2. Verify the name updates. Edit colour. Verify it updates.
3. Add a description. Verify it persists.

---

### `95-annotation-tags.AC7.3` -- Group reassignment UI

**Why it cannot be automated:** Dropdown interaction in the management dialog.

**Verification approach:**
1. Open the management dialog. Change a tag's group via the group dropdown.
2. Verify the tag moves to the new group section on re-render.
3. Set a tag's group to "None"/clear. Verify it moves to the Ungrouped section.

---

### `95-annotation-tags.AC7.4` -- Drag reorder UI

**Why it cannot be automated:** SortableJS drag interaction.

**Verification approach:**
1. Open the management dialog. Drag a tag to a new position within its group.
2. Close and reopen the dialog. Verify the new order persists.
3. Drag a group to a new position. Verify group order persists.
4. Close the dialog. Verify the toolbar tag order matches the new order.

---

### `95-annotation-tags.AC7.5` -- Delete confirmation UI

**Why it cannot be automated (fully):** Confirmation dialog rendering and highlight count display.

**Verification approach:**
1. Create highlights using a tag. Open the management dialog.
2. Click delete on that tag. Verify a confirmation dialog shows the highlight count.
3. Confirm deletion. Verify the tag and its highlights are removed.
4. Cancel deletion on another tag. Verify nothing is removed.

---

### `95-annotation-tags.AC7.7` -- Import dropdown UI

**Why it cannot be automated (fully):** Dropdown population and instructor-only gating.

**Verification approach:**
1. As an instructor, open the management dialog on a template workspace.
2. Verify the "Import tags from..." dropdown appears and lists other activities in the course (excluding the current one).
3. Select an activity and import. Verify tags appear in the dialog.
4. As a student, open the management dialog. Verify the import section is not visible.

---

### `95-annotation-tags.AC7.8` -- Lock toggle UI

**Why it cannot be automated:** Switch rendering and instructor-only visibility.

**Verification approach:**
1. As an instructor, open the management dialog on a template workspace.
2. Verify each tag row shows a lock toggle switch.
3. Toggle a tag to locked. Verify a lock icon appears.
4. As a student, open the management dialog. Verify no lock toggle is visible.

---

### `95-annotation-tags.AC7.9` -- Locked tag controls disabled for students

**Why it cannot be automated:** DOM disabled/readonly state on form controls.

**Verification approach:**
1. As an instructor, lock a tag on the template workspace.
2. Clone the workspace to a student.
3. As the student, open the management dialog. Verify the locked tag shows:
   - A lock icon
   - Name, colour, and description inputs are readonly/disabled
   - Delete button is disabled
4. Verify the student can still use the locked tag for annotation (applying highlights).

---

### `95-annotation-tags.AC8.1` -- Activity settings dialog UI

**Why it cannot be automated (fully):** Dialog rendering. The CRUD round-trip is tested.

**Verification approach:**
1. Open the activity settings dialog (tune icon on activity row).
2. Verify an "Allow tag creation" tri-state select appears with options: "Inherit from course", "Allowed", "Not allowed".
3. Change the setting and save. Verify it persists on re-open.

---

### `95-annotation-tags.AC8.2` -- Course settings dialog UI

**Why it cannot be automated (fully):** Dialog rendering. The CRUD round-trip is tested.

**Verification approach:**
1. Open the course settings dialog.
2. Verify a "Default allow tag creation" switch appears.
3. Toggle and save. Verify it persists on re-open.

---

## Test File Summary

| Test file | Test type | Phase | ACs covered |
|---|---|---|---|
| `tests/unit/test_tag_models.py` | Unit | P1/T6 | AC1.1, AC1.2, AC1.4 |
| `tests/unit/test_db_schema.py` (modified) | Unit | P1/T6 | AC1.1, AC1.2 |
| `tests/unit/conftest.py` (modified) | Unit fixtures | P1/T6 | -- |
| `tests/integration/test_tag_schema.py` | Integration | P1/T7 | AC1.5, AC1.6, AC1.7, AC8.3, AC8.4, AC8.5 |
| `tests/integration/test_tag_crud.py` | Integration | P2/T4-T5 | AC2.1-AC2.9, AC3.1-AC3.3, AC7.6 |
| `tests/integration/test_tag_cloning.py` | Integration | P3/T3-T4 | AC4.1-AC4.6 |
| `tests/integration/test_workspace_tags.py` | Integration | P4/T7 | AC5.1, AC5.5, AC5.6 |
| `tests/integration/test_tag_management.py` | Integration | P5/T6 | AC6.2, AC6.3, AC7.5, AC7.7 |
| `tests/integration/test_tag_settings.py` | Integration | P6/T3 | AC8.1-AC8.5 |
| `tests/integration/conftest.py` (modified) | Integration fixtures | P4/T6 | AC5.11 |
