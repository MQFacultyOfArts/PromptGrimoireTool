# Human Test Plan: Annotation Tags (Issue #95)

**Generated:** 2026-02-20
**Implementation plan:** `docs/implementation-plans/2026-02-18-95-annotation-tags/`
**Branch:** `95-annotation-tags`
**Automated tests:** 2712 passed (35/35 acceptance criteria covered)

## Prerequisites

- PostgreSQL running with `DATABASE__URL` pointing to the worktree database (`promptgrimoire_95_annotation_tags`)
- `uv run alembic upgrade head` completed
- `uv run test-all` passing (2712 tests, 0 failures)
- Application running via `uv run python -m promptgrimoire`
- At least one course with a week, activity, and template workspace seeded via `uv run seed-data`
- Two user accounts: one instructor (admin or instructor role), one student (enrolled in the course)

## Phase 1: Seed Data Verification (AC1.3)

| Step | Action | Expected |
|------|--------|----------|
| 1.1 | Run `uv run seed-data` against a fresh database (after `alembic upgrade head`) | Console output includes tag seeding messages. No "Tags exist" message. |
| 1.2 | Run `uv run seed-data` a second time | Console output shows "Tags exist" or similar idempotency message. No duplicate rows created. |
| 1.3 | Query `tag_group` table: `SELECT name FROM tag_group WHERE workspace_id = (SELECT template_workspace_id FROM activity WHERE title LIKE '%Legal%' LIMIT 1);` | One row: "Legal Case Brief" |
| 1.4 | Query `tag` table for that workspace: `SELECT name, color FROM tag WHERE workspace_id = <template_ws_id> ORDER BY order_index;` | 10 rows with colorblind-accessible hex colours matching the seed data palette. |

## Phase 2: Annotation Page Tag Rendering (AC5.2, AC5.3, AC5.4, AC5.8, AC5.9, AC5.10)

| Step | Action | Expected |
|------|--------|----------|
| 2.1 | Log in as the student. Navigate to a workspace with 10+ tags (e.g., one cloned from the Legal Case Brief activity). | Annotation page loads. Tag toolbar shows tag buttons in order_index order. |
| 2.2 | Count the tag buttons in the toolbar. | 10 buttons plus "+" and gear icons (if creation is allowed). No horizontal scrollbar. |
| 2.3 | Observe a tag with a long name (create one via management dialog if needed, e.g., "Extremely Long Tag Name That Should Truncate"). | Button text is truncated with ellipsis (`...`). |
| 2.4 | Hover over the truncated tag button. | Tooltip shows the full tag name. |
| 2.5 | Select text in the document area. Do NOT click a tag button or press a shortcut. | No highlight is created. There is no "untagged" or default highlight mode. |
| 2.6 | Select text, then press the `1` key. | A highlight is created with the first tag in the toolbar (verify by colour and sidebar card). |
| 2.7 | Select text, then press `2` through `0`. | Each key creates a highlight with the corresponding positional tag (2=second, ..., 0=tenth). |
| 2.8 | Press a letter key (e.g., `a`) with text selected. | No highlight is created. |
| 2.9 | Type in an input field (e.g., a comment box) while text is selected in the document. | Key presses are not intercepted -- characters are typed into the input field, no highlight is created. |
| 2.10 | Inspect a highlight card in the sidebar. | Card colour indicator matches the tag's stored hex colour from the database. |
| 2.11 | Click the tag dropdown on a highlight card. | Dropdown lists all workspace tags by name. |
| 2.12 | Select a different tag from the dropdown. | Card colour updates. The CRDT highlight's tag value changes (verify by reloading the page). |
| 2.13 | Resize the browser window narrower so the toolbar does not fit in one row. | Tag buttons wrap to two (or more) rows. No horizontal scrollbar appears on the toolbar. |

## Phase 3: Organise and Respond Tabs (AC5.5, AC5.6)

| Step | Action | Expected |
|------|--------|----------|
| 3.1 | Navigate to the Organise tab on a workspace with highlights in multiple tags. | One column per workspace tag. Column headers show tag names. |
| 3.2 | Verify there is no "Untagged" column. | No column for untagged highlights exists. |
| 3.3 | Create a new tag via quick-create ("+"). Return to Organise tab. | A new column appears for the new tag. |
| 3.4 | Navigate to the Respond tab. | Highlights are grouped by tag name. Tag names and colours match the database. |

## Phase 4: PDF Export (AC5.7)

| Step | Action | Expected |
|------|--------|----------|
| 4.1 | On a workspace with highlights using multiple tags, click Export PDF. | A PDF file is generated and downloaded. |
| 4.2 | Open the PDF. Inspect highlight colours. | Highlight colours in the PDF match the tag colours stored in the database. |
| 4.3 | Change a tag's colour via the management dialog (e.g., from blue to red). Re-export. | The new PDF reflects the updated tag colour. |

## Phase 5: Quick-Create Dialog (AC6.1, AC6.3)

| Step | Action | Expected |
|------|--------|----------|
| 5.1 | Log in as a student on a workspace where `allow_tag_creation` resolves to True. Click the "+" button on the toolbar. | A dialog opens with: name input (maxlength enforced), colour picker (10 preset swatches + custom input), optional group dropdown, Cancel and Create buttons. |
| 5.2 | Enter a name and select a colour. Click Create. | A new tag is created. It appears in the toolbar. If text was selected, a highlight is created with the new tag. |
| 5.3 | Try to create a tag with a duplicate name. | An error message appears (IntegrityError catch). The dialog does not close. |
| 5.4 | Set the activity's `allow_tag_creation` to False (via DB or activity settings dialog). Reload the annotation page. | The "+" button is not visible on the toolbar. |
| 5.5 | Set `allow_tag_creation` back to True. Reload. | The "+" button reappears. |

## Phase 6: Management Dialog (AC7.1-AC7.9)

| Step | Action | Expected |
|------|--------|----------|
| 6.1 | Click the gear button on the annotation toolbar. | Management dialog opens showing tags grouped by TagGroup. An "Ungrouped" section shows tags with no group. |
| 6.2 | Edit a tag's name inline. Click outside the field (blur). | The name updates immediately (save-on-blur). Reload the page to verify persistence. |
| 6.3 | Edit a tag's colour. | Colour updates. Toolbar button colour changes. |
| 6.4 | Add a description to a tag. | Description persists after closing and reopening the dialog. |
| 6.5 | Change a tag's group via the group dropdown. | The tag moves to the new group section on re-render. |
| 6.6 | Set a tag's group to "None" / ungrouped. | The tag moves to the Ungrouped section. |
| 6.7 | Drag a tag to a new position within its group (SortableJS). Close and reopen the dialog. | The new order persists. Toolbar tag order matches the new order. |
| 6.8 | Drag a group to a new position among groups. Close and reopen the dialog. | Group order persists. |
| 6.9 | Create highlights using a tag. Open the management dialog. Click delete on that tag. | A confirmation dialog appears showing the highlight count (e.g., "This tag has 3 highlights. Delete?"). |
| 6.10 | Confirm deletion. | Tag and its highlights are removed. Toolbar updates. Sidebar cards for those highlights disappear. |
| 6.11 | Click delete on another tag, then cancel. | Nothing is removed. |
| 6.12 | Delete a TagGroup. | Tags in that group move to Ungrouped. No highlights are lost. |
| 6.13 | As an instructor on a template workspace, click "Import tags from..." dropdown. | Dropdown lists other activities in the same course (excluding the current one). |
| 6.14 | Select an activity and confirm import. | Tags from the source activity appear in the management dialog with new UUIDs but same names/colours. |
| 6.15 | As a student, open the management dialog. Verify the import section is not visible. | No "Import tags from..." dropdown is shown. |
| 6.16 | As an instructor on a template workspace, verify each tag row shows a lock toggle switch. | Lock toggle switch is visible on each tag row. |
| 6.17 | Toggle a tag to locked. | A lock icon appears. |
| 6.18 | As a student, open the management dialog. Inspect the locked tag. | Lock icon visible. Name, colour, description inputs are readonly/disabled. Delete button is disabled. |
| 6.19 | As a student, verify the locked tag is still usable for annotation. | The tag button appears in the toolbar. Clicking it (or using its shortcut key) creates a highlight. |
| 6.20 | As a student, verify no lock toggle is visible. | No switch to change lock state is shown for students. |

## Phase 7: Activity and Course Settings (AC8.1, AC8.2)

| Step | Action | Expected |
|------|--------|----------|
| 7.1 | As an instructor, open the activity settings dialog (tune icon on activity row on the courses page). | An "Allow tag creation" tri-state select appears with options: "Inherit from course", "Allowed", "Not allowed". |
| 7.2 | Change the setting to "Not allowed" and save. Reopen. | The setting persists as "Not allowed". |
| 7.3 | Change the setting to "Inherit from course" and save. | The setting persists as "Inherit from course" (NULL in DB). |
| 7.4 | Open the course settings dialog. | A "Default allow tag creation" switch appears. |
| 7.5 | Toggle the switch off and save. Reopen. | The switch is off. Value persists as False. |
| 7.6 | Toggle the switch on and save. | The switch is on. Value persists as True. |

## End-to-End: Template-to-Student Clone with Tags

**Purpose:** Verify the full lifecycle from instructor tag setup through student workspace cloning, including CRDT highlight remapping.

| Step | Action | Expected |
|------|--------|----------|
| E2E.1 | As an instructor, open a template workspace. Create a TagGroup "Legal Case Brief" with 3 tags: "Jurisdiction" (blue, locked), "Facts" (orange), "Holding" (green). | Tags appear in the toolbar and management dialog. |
| E2E.2 | Select text and create highlights using each tag. Set tag_order (drag highlights in the organise tab). | Highlights appear in sidebar cards with correct colours. |
| E2E.3 | Publish the week. As a student, navigate to the activity. | A cloned workspace is created for the student. |
| E2E.4 | On the student workspace, verify the toolbar shows 3 tags with the same names and colours. | Tag names: Jurisdiction, Facts, Holding. Colours match template. |
| E2E.5 | Open management dialog. Verify "Jurisdiction" shows a lock icon and is not editable. | Lock icon present. Name/colour/description fields are readonly. Delete disabled. |
| E2E.6 | Verify "Facts" and "Holding" are editable (no lock icon). | Edit controls are enabled. |
| E2E.7 | Inspect the cloned highlights. Verify each highlight references the student workspace's tag UUIDs (not the template's). | Highlight cards show correct tag colours. Changing tag via dropdown works. |
| E2E.8 | Navigate to Organise tab. Verify columns match the 3 tags. | Three columns, no "Untagged" column. Highlights appear in the correct columns. |

## End-to-End: Permission Inheritance Flow

**Purpose:** Verify that course-level and activity-level tag creation settings cascade correctly to the annotation page.

| Step | Action | Expected |
|------|--------|----------|
| E2E.9 | Set course `default_allow_tag_creation=True`. Set activity `allow_tag_creation=NULL` (Inherit). Open student annotation page. | "+" button visible. Student can create tags. |
| E2E.10 | Set activity `allow_tag_creation=False`. Reload student page. | "+" button hidden. Student cannot create tags. CRUD raises PermissionError if attempted via API. |
| E2E.11 | Set course `default_allow_tag_creation=False`. Set activity `allow_tag_creation=TRUE`. Reload student page. | "+" button visible. Activity override takes precedence. |
| E2E.12 | Set activity `allow_tag_creation=NULL` (Inherit). Reload student page. | "+" button hidden. Course default (False) inherited. |

## Traceability

| Acceptance Criterion | Automated Test | Manual Step |
|----------------------|----------------|-------------|
| AC1.1 | `test_tag_models.py::TestTagGroupDefaults` + `test_db_schema.py` | -- |
| AC1.2 | `test_tag_models.py::TestTagDefaults` + `test_db_schema.py` | -- |
| AC1.3 | -- | Phase 1: 1.1-1.4 |
| AC1.4 | `test_tag_models.py::TestActivityTagCreationPolicy` + `TestCourseTagCreationPolicy` | -- |
| AC1.5 | `test_tag_schema.py::TestPlacementContextTagCreation` | -- |
| AC1.6 | `test_tag_schema.py::TestTagCascadeOnWorkspaceDelete` | -- |
| AC1.7 | `test_tag_schema.py::TestTagGroupSetNullOnDelete` | -- |
| AC2.1 | `test_tag_crud.py::TestCreateTag` | -- |
| AC2.2 | `test_tag_crud.py::TestUpdateTag` | -- |
| AC2.3 | `test_tag_crud.py::TestDeleteTagCrdtCleanup` | -- |
| AC2.4 | `test_tag_crud.py::TestCreateTagGroup` + `TestUpdateTagGroup` | -- |
| AC2.5 | `test_tag_crud.py::TestDeleteTagGroup` | -- |
| AC2.6 | `test_tag_crud.py::TestReorderTags` | -- |
| AC2.7 | `test_tag_crud.py::TestReorderTagGroups` | -- |
| AC2.8 | `test_tag_crud.py::TestLockEnforcement` | -- |
| AC2.9 | `test_tag_crud.py::TestPermissionEnforcement` | -- |
| AC3.1-3.3 | `test_tag_crud.py::TestImportTagsFromActivity` | -- |
| AC4.1 | `test_tag_cloning.py::TestTagGroupCloning` | -- |
| AC4.2 | `test_tag_cloning.py::TestTagCloning` | -- |
| AC4.3 | `test_tag_cloning.py::TestCrdtTagRemapping` + `TestLegacyBriefTagPassthrough` | -- |
| AC4.4 | `test_tag_cloning.py::TestCrdtTagRemapping` | -- |
| AC4.5 | `test_tag_cloning.py::TestTagCloning` | -- |
| AC4.6 | `test_tag_cloning.py::TestEmptyTagClone` | -- |
| AC5.1 | `test_workspace_tags.py::TestWorkspaceTags` + `TestWorkspaceTagsOrdering` | -- |
| AC5.2 | -- | Phase 2: 2.6-2.9 |
| AC5.3 | -- | Phase 2: 2.10 |
| AC5.4 | -- | Phase 2: 2.11-2.12 |
| AC5.5 | `test_workspace_tags.py` (data path) | Phase 3: 3.1-3.3 |
| AC5.6 | `test_workspace_tags.py` (data path) | Phase 3: 3.4 |
| AC5.7 | -- | Phase 4: 4.1-4.3 |
| AC5.8 | -- | Phase 2: 2.5 |
| AC5.9 | -- | Phase 2: 2.3-2.4 |
| AC5.10 | -- | Phase 2: 2.13 |
| AC5.11 | grep + ty check + test-all | -- |
| AC6.1 | -- | Phase 5: 5.1 |
| AC6.2 | `test_tag_management.py::TestQuickCreateWorkflow` | Phase 5: 5.2 |
| AC6.3 | `test_tag_management.py::TestCreationGating` | Phase 5: 5.4-5.5 |
| AC7.1 | -- | Phase 6: 6.1 |
| AC7.2 | `test_tag_crud.py::TestUpdateTag` | Phase 6: 6.2-6.4 |
| AC7.3 | `test_tag_crud.py::TestUpdateTag` | Phase 6: 6.5-6.6 |
| AC7.4 | `test_tag_crud.py::TestReorderTags` + `TestReorderTagGroups` | Phase 6: 6.7-6.8 |
| AC7.5 | `test_tag_management.py::TestDeleteWithCrdtCleanup` | Phase 6: 6.9-6.11 |
| AC7.6 | `test_tag_crud.py::TestDeleteTagGroup` | Phase 6: 6.12 |
| AC7.7 | `test_tag_management.py::TestImportWorkflow` | Phase 6: 6.13-6.15 |
| AC7.8 | `test_tag_crud.py::TestLockEnforcement` | Phase 6: 6.16-6.17, 6.20 |
| AC7.9 | -- | Phase 6: 6.18-6.19 |
| AC8.1 | `test_tag_settings.py::TestCreateActivityWithTagCreation` + `TestUpdateActivityTagCreation` | Phase 7: 7.1-7.3 |
| AC8.2 | `test_tag_settings.py::TestUpdateCourseDefaultTagCreation` | Phase 7: 7.4-7.6 |
| AC8.3-8.5 | `test_tag_settings.py::TestTriStateInheritanceFromCrud` + `test_tag_schema.py::TestPlacementContextTagCreation` | E2E: E2E.9-E2E.12 |
