# 94-hierarchy-placement: Test Requirements

Maps every acceptance criterion to either an automated test or a documented human verification step.

## Automated Tests

### AC1: Activity entity and schema

| Criterion ID | Type | Test File | Description |
|---|---|---|---|
| 94-hierarchy-placement.AC1.1 | integration | `tests/integration/test_activity_crud.py::TestCreateActivity::test_creates_with_uuid_and_timestamps` | Create Activity with valid week_id, title, description. Assert `id` is UUID, `created_at` and `updated_at` are set, `title` and `description` match input. |
| 94-hierarchy-placement.AC1.2 | integration | `tests/integration/test_activity_crud.py::TestCreateActivity::test_template_workspace_created_atomically` | Create Activity. Assert `template_workspace_id` is not None. Fetch the Workspace by that ID and assert it exists in DB. |
| 94-hierarchy-placement.AC1.3 | integration | `tests/integration/test_activity_crud.py::TestCreateActivity::test_rejects_nonexistent_week_id` | Call `create_activity(week_id=uuid4(), ...)`. Assert raises `IntegrityError`. |
| 94-hierarchy-placement.AC1.4 | unit | `tests/unit/test_workspace_placement_validation.py::TestActivityModel::test_week_id_required` | Construct Activity model without `week_id`. Assert Pydantic/SQLModel validation rejects it. (Also implicitly covered by NOT NULL column constraint in AC1.3 integration test.) |
| 94-hierarchy-placement.AC1.5 | unit | `tests/unit/test_workspace_placement_validation.py::TestWorkspacePlacementExclusivity::test_both_none_is_valid` | Create Workspace with defaults. Assert `activity_id` is None, `course_id` is None, `enable_save_as_draft` is False. |
| 94-hierarchy-placement.AC1.5 | integration | `tests/integration/test_activity_crud.py::TestWorkspacePlacementFields::test_workspace_has_activity_id_course_id_fields` | Create Workspace in DB. Assert `activity_id`, `course_id` default to None, `enable_save_as_draft` defaults to False. Confirms Alembic migration applied column additions correctly. |
| 94-hierarchy-placement.AC1.6 | unit | `tests/unit/test_workspace_placement_validation.py::TestWorkspacePlacementExclusivity::test_both_set_raises_value_error` | Construct `Workspace(activity_id=uuid4(), course_id=uuid4())`. Assert raises `ValueError` matching "cannot be placed in both". |
| 94-hierarchy-placement.AC1.6 | unit | `tests/unit/test_workspace_placement_validation.py::TestWorkspacePlacementExclusivity::test_activity_only_is_valid` | Construct `Workspace(activity_id=uuid4())`. Assert no error, `course_id` is None. |
| 94-hierarchy-placement.AC1.6 | unit | `tests/unit/test_workspace_placement_validation.py::TestWorkspacePlacementExclusivity::test_course_only_is_valid` | Construct `Workspace(course_id=uuid4())`. Assert no error, `activity_id` is None. |
| 94-hierarchy-placement.AC1.7 | integration | `tests/integration/test_activity_crud.py::TestCascadeBehavior::test_delete_activity_nulls_workspace_activity_id` | Create Activity. Place a student workspace in that Activity (set `activity_id` via session). Delete Activity via CRUD. Re-fetch workspace. Assert workspace exists with `activity_id=None`. |
| 94-hierarchy-placement.AC1.8 | integration | `tests/integration/test_activity_crud.py::TestCascadeBehavior::test_delete_course_nulls_workspace_course_id` | Create Course. Set workspace `course_id` via session. Delete Course. Re-fetch workspace. Assert workspace exists with `course_id=None`. |

### AC2: Activity CRUD and course page UI

| Criterion ID | Type | Test File | Description |
|---|---|---|---|
| 94-hierarchy-placement.AC2.1 | integration | `tests/integration/test_activity_crud.py::TestActivityCRUD::test_create_get_update_delete` | Full CRUD lifecycle: `create_activity()` returns Activity with fields set; `get_activity(id)` returns same; `update_activity(id, title=..., description=...)` changes fields; `delete_activity(id)` returns True; `get_activity(id)` returns None. |
| 94-hierarchy-placement.AC2.2 | integration | `tests/integration/test_activity_crud.py::TestActivityCRUD::test_delete_cascades_template_workspace` | Create Activity (auto-creates template workspace). Record `template_workspace_id`. Delete Activity. Fetch workspace by recorded ID. Assert returns None (workspace deleted). |
| 94-hierarchy-placement.AC2.3 | integration | `tests/integration/test_activity_crud.py::TestListActivities::test_list_for_week_ordered_by_created_at` | Create 3 Activities in a single Week with known creation order (small delays or explicit timestamps). Call `list_activities_for_week(week_id)`. Assert result order matches `created_at` ascending. |
| 94-hierarchy-placement.AC2.4 | integration | `tests/integration/test_activity_crud.py::TestListActivities::test_list_for_course_across_weeks` | Create Course with 2 Weeks. Add Activities to each Week. Call `list_activities_for_course(course_id)`. Assert all Activities returned, ordered by `week_number` then `created_at`. |
| 94-hierarchy-placement.AC2.5 | **human** | -- | See Human Verification section below. |
| 94-hierarchy-placement.AC2.6 | **human** | -- | See Human Verification section below. |
| 94-hierarchy-placement.AC2.7 | **human** | -- | See Human Verification section below. |

### AC3: Workspace placement

| Criterion ID | Type | Test File | Description |
|---|---|---|---|
| 94-hierarchy-placement.AC3.1 | integration | `tests/integration/test_workspace_placement.py::TestPlaceWorkspace::test_place_in_activity_sets_activity_id_clears_course_id` | Create Activity, Course, and Workspace. Place workspace in Course first. Then place in Activity. Assert `activity_id` is set, `course_id` is None. |
| 94-hierarchy-placement.AC3.2 | integration | `tests/integration/test_workspace_placement.py::TestPlaceWorkspace::test_place_in_course_sets_course_id_clears_activity_id` | Place workspace in Activity first. Then place in Course. Assert `course_id` is set, `activity_id` is None. |
| 94-hierarchy-placement.AC3.3 | integration | `tests/integration/test_workspace_placement.py::TestPlaceWorkspace::test_make_loose_clears_both` | Place workspace in Activity. Call `make_workspace_loose()`. Assert both `activity_id` and `course_id` are None. |
| 94-hierarchy-placement.AC3.4 | integration | `tests/integration/test_workspace_placement.py::TestPlaceWorkspace::test_place_in_nonexistent_activity_raises` | Call `place_workspace_in_activity(ws_id, uuid4())`. Assert raises `ValueError` matching "Activity.*not found". |
| 94-hierarchy-placement.AC3.4 | integration | `tests/integration/test_workspace_placement.py::TestPlaceWorkspace::test_place_in_nonexistent_course_raises` | Call `place_workspace_in_course(ws_id, uuid4())`. Assert raises `ValueError` matching "Course.*not found". |
| 94-hierarchy-placement.AC3.4 | integration | `tests/integration/test_workspace_placement.py::TestPlaceWorkspace::test_place_nonexistent_workspace_raises` | Call `place_workspace_in_activity(uuid4(), activity_id)`. Assert raises `ValueError` matching "Workspace.*not found". |
| 94-hierarchy-placement.AC3.5 | integration | `tests/integration/test_workspace_placement.py::TestListWorkspaces::test_list_for_activity` | Create Activity. Place 2 workspaces in it. Leave 1 workspace unplaced. Call `list_workspaces_for_activity(activity_id)`. Assert returns exactly 2 workspaces. |
| 94-hierarchy-placement.AC3.6 | integration | `tests/integration/test_workspace_placement.py::TestListWorkspaces::test_list_loose_for_course` | Create Course and Activity. Associate 2 workspaces with Course. Place 1 of those into the Activity (which clears `course_id`). Call `list_loose_workspaces_for_course(course_id)`. Assert returns only the 1 workspace still associated with Course. |
| 94-hierarchy-placement.AC3.7 | **human** | -- | See Human Verification section below. |

**Supporting tests for AC3.7 UI infrastructure (not AC-mapped but required for UAT):**

| Test ID | Type | Test File | Description |
|---|---|---|---|
| PlacementContext-loose | integration | `tests/integration/test_workspace_placement.py::TestPlacementContext::test_loose_workspace` | Workspace with no placement returns `placement_type="loose"` and `display_label="Unplaced"`. |
| PlacementContext-activity | integration | `tests/integration/test_workspace_placement.py::TestPlacementContext::test_activity_placement_shows_full_hierarchy` | Workspace placed in Activity returns full hierarchy fields and correct `display_label` format. |
| PlacementContext-course | integration | `tests/integration/test_workspace_placement.py::TestPlacementContext::test_course_placement` | Workspace placed in Course returns `placement_type="course"` and `display_label="Loose work for [code]"`. |
| PlacementContext-missing | integration | `tests/integration/test_workspace_placement.py::TestPlacementContext::test_nonexistent_workspace` | Non-existent workspace ID returns loose context (defensive fallback). |

### AC4: Workspace cloning (documents + CRDT)

| Criterion ID | Type | Test File | Description |
|---|---|---|---|
| 94-hierarchy-placement.AC4.1 | integration | `tests/integration/test_workspace_cloning.py::TestCloneDocuments::test_clone_creates_workspace_with_activity_id_and_draft_flag` | Create Activity, set `enable_save_as_draft=True` on template. Clone. Assert new workspace has `activity_id` matching Activity and `enable_save_as_draft=True`. |
| 94-hierarchy-placement.AC4.2 | integration | `tests/integration/test_workspace_cloning.py::TestCloneDocuments::test_cloned_docs_preserve_fields` | Add 2 documents to template with distinct content, type, source_type, title, order_index. Clone. Assert each cloned document has matching field values. |
| 94-hierarchy-placement.AC4.3 | integration | `tests/integration/test_workspace_cloning.py::TestCloneDocuments::test_cloned_docs_have_new_uuids` | Clone template with documents. Assert each cloned document ID differs from its template counterpart. Assert `doc_id_map` keys are template IDs and values are clone IDs. |
| 94-hierarchy-placement.AC4.4 | integration | `tests/integration/test_workspace_cloning.py::TestCloneDocuments::test_original_template_unmodified` | Record template workspace fields, document count, document content, and `crdt_state` before clone. Clone. Re-fetch template data. Assert all values unchanged. |
| 94-hierarchy-placement.AC4.5 | integration | `tests/integration/test_workspace_cloning.py::TestCloneDocuments::test_empty_template_produces_empty_workspace` | Create Activity with no documents. Clone. Assert new workspace exists with `activity_id` set, zero documents, empty `doc_id_map`. |
| 94-hierarchy-placement.AC4.5 | integration | `tests/integration/test_workspace_cloning.py::TestCloneDocuments::test_clone_nonexistent_activity_raises` | Call `clone_workspace_from_activity(uuid4())`. Assert raises `ValueError`. |
| 94-hierarchy-placement.AC4.6 | integration | `tests/integration/test_workspace_cloning.py::TestCloneCRDT::test_cloned_highlights_reference_new_document_uuids` | Create Activity with 2 docs. Add highlight with `document_id=str(template_doc_1.id)`. Save CRDT state. Clone. Load clone CRDT. Assert highlight's `document_id` matches cloned doc UUID from `doc_id_map`, not template doc UUID. |
| 94-hierarchy-placement.AC4.6 | integration | `tests/integration/test_workspace_cloning.py::TestCloneCRDT::test_multiple_highlights_across_documents_remapped` | Create Activity with 2 docs. Add 1 highlight referencing doc 1, 1 referencing doc 2. Clone. Assert each cloned highlight's `document_id` maps to its respective cloned document UUID. |
| 94-hierarchy-placement.AC4.7 | integration | `tests/integration/test_workspace_cloning.py::TestCloneCRDT::test_highlight_fields_preserved` | Add highlight with specific `start_char`, `end_char`, `tag`, `text`, `author`, `para_ref`. Clone. Assert cloned highlight has identical field values for all non-ID fields. |
| 94-hierarchy-placement.AC4.8 | integration | `tests/integration/test_workspace_cloning.py::TestCloneCRDT::test_comments_preserved_in_clone` | Add highlight with 2 comments (distinct author/text). Save CRDT state. Clone. Load clone CRDT. Assert 2 comments exist on the cloned highlight with matching `author` and `text`. |
| 94-hierarchy-placement.AC4.9 | integration | `tests/integration/test_workspace_cloning.py::TestCloneCRDT::test_client_metadata_not_cloned` | Register a client on template AnnotationDocument (writes to `client_meta` map). Save CRDT state. Clone. Load clone CRDT. Assert `client_meta` map is empty. |
| 94-hierarchy-placement.AC4.10 | integration | `tests/integration/test_workspace_cloning.py::TestCloneCRDT::test_null_crdt_state_produces_null_clone` | Create Activity with docs. Do NOT set CRDT state (`crdt_state` is None). Clone. Assert cloned workspace's `crdt_state` is None. |
| 94-hierarchy-placement.AC4.11 | integration | `tests/integration/test_workspace_cloning.py::TestCloneCRDT::test_clone_atomicity_with_crdt` | Clone Activity that has docs and CRDT state. Assert cloned workspace has non-null `crdt_state`, correct document count, and highlight count matching template. (Atomicity is structurally guaranteed by single-session design; this test validates the all-present outcome.) |
| 94-hierarchy-placement.AC4.11 | integration | `tests/integration/test_workspace_cloning.py::TestCloneCRDT::test_general_notes_cloned` | Set general notes on template CRDT state. Clone. Load clone CRDT. Assert `get_general_notes()` returns matching text. |
| 94-hierarchy-placement.AC4.12 | **human** | -- | See Human Verification section below. |

## Summary: Test File Inventory

| Test File | Type | AC Coverage |
|---|---|---|
| `tests/unit/test_workspace_placement_validation.py` | unit | AC1.4, AC1.5, AC1.6 |
| `tests/integration/test_activity_crud.py` | integration | AC1.1, AC1.2, AC1.3, AC1.5, AC1.7, AC1.8, AC2.1, AC2.2, AC2.3, AC2.4 |
| `tests/integration/test_workspace_placement.py` | integration | AC3.1, AC3.2, AC3.3, AC3.4, AC3.5, AC3.6, PlacementContext support |
| `tests/integration/test_workspace_cloning.py` | integration | AC4.1, AC4.2, AC4.3, AC4.4, AC4.5, AC4.6, AC4.7, AC4.8, AC4.9, AC4.10, AC4.11 |

---

## Human Verification (UAT)

The following criteria require manual verification because they test NiceGUI page rendering, user-facing navigation flows, and visual confirmation of UI state. These criteria involve browser interactions with dynamic NiceGUI components (cascading dropdowns, page navigation, real-time chip updates) that are not covered by the project's existing Playwright E2E patterns.

### 94-hierarchy-placement.AC2.5: Activities visible under Weeks on course detail page

**Justification:** Verifies NiceGUI page layout and rendering -- that Activity items appear under the correct Week sections with correct hierarchy, icons, and labels. The annotation page E2E fixture screenshot pattern does not extend to the course management pages.

**Verification approach:**
1. Navigate to a course detail page at `/courses/{course_id}`.
2. Confirm each Week section shows its Activities listed underneath with assignment icons.
3. Confirm Weeks with no Activities show "No activities yet" (when viewing as instructor).
4. **Pass criterion:** Activities appear under their correct parent Weeks.

### 94-hierarchy-placement.AC2.6: Create Activity form creates Activity and template workspace

**Justification:** Verifies form submission and server-side side-effect (template workspace creation) through the NiceGUI form flow. The form involves a page navigation, form fill, submit, and redirect.

**Verification approach:**
1. On course detail page, click "Add Activity" button under a Week.
2. Fill in title (e.g., "Annotate Becky Bennett Interview") and optional description.
3. Click submit.
4. Confirm redirect back to course detail page.
5. Confirm new Activity appears under the correct Week.
6. **Pass criterion:** Activity exists with title matching input; template workspace was auto-created (visible via Activity link).

### 94-hierarchy-placement.AC2.7: Clicking Activity navigates to template workspace in annotation page

**Justification:** Verifies navigation link targets and that the annotation page loads with the correct workspace context. Requires browser navigation and annotation page rendering.

**Verification approach:**
1. On course detail page, click an Activity title link.
2. Confirm browser navigated to `/annotation?workspace_id={template_workspace_id}`.
3. Confirm annotation page loads (empty workspace is acceptable for a new Activity).
4. **Pass criterion:** URL contains correct `workspace_id` parameter; annotation page renders without error.

### 94-hierarchy-placement.AC3.7: Workspace can be placed into/removed from Activity or Course via UI

**Justification:** Verifies the placement dialog UX flow including cascading dropdowns, chip state updates, and confirm/cancel behavior. This is a multi-step interactive flow with dynamic UI updates.

**Verification approach:**
1. Open a workspace in the annotation page at `/annotation?workspace_id={id}`.
2. Confirm a placement status chip is visible in the header (grey "Unplaced" for a loose workspace).
3. Click the chip to open the placement dialog.
4. Select "Place in Activity", choose a Course, Week, then Activity from the cascading dropdowns. Click Confirm.
5. Confirm chip updates to show full hierarchy label in blue.
6. Click chip again, select "Associate with Course", choose a Course. Click Confirm.
7. Confirm chip updates to "Loose work for {Course code}" in green.
8. Click chip again, select "Unplaced". Click Confirm.
9. Confirm chip reverts to "Unplaced" in grey.
10. **Pass criterion:** Chip state correctly reflects each placement mode after each change.

### 94-hierarchy-placement.AC4.12: Start button clones template and redirects to new workspace with highlights visible

**Justification:** Verifies the end-to-end user flow of cloning a template workspace and visually confirming that documents, highlights, and comments appear correctly in the clone. This requires browser rendering of the annotation page with CRDT-driven highlights -- a visual verification that goes beyond data-layer assertions.

**Verification approach:**
1. Navigate to a template workspace via its Activity link on the course page.
2. Add a document, then add highlights and comments using the annotation UI.
3. Return to the course detail page.
4. Click "Start" on that Activity.
5. Confirm redirect to `/annotation?workspace_id={new_clone_id}` (different workspace ID from template).
6. Confirm cloned workspace contains the same documents as the template (matching titles and content).
7. Confirm highlights are visible on the correct documents in the cloned workspace.
8. Confirm comments on highlights are preserved and visible.
9. Confirm highlight positions (character ranges) match the template.
10. **Pass criterion:** Highlights and comments appear in the clone on the correct documents; new workspace URL differs from template.

---

## Coverage Matrix

Every acceptance criterion is accounted for below. Criteria marked "auto" have one or more automated tests. Criteria marked "human" require manual UAT verification.

| Criterion | Coverage |
|---|---|
| 94-hierarchy-placement.AC1.1 | auto |
| 94-hierarchy-placement.AC1.2 | auto |
| 94-hierarchy-placement.AC1.3 | auto |
| 94-hierarchy-placement.AC1.4 | auto |
| 94-hierarchy-placement.AC1.5 | auto |
| 94-hierarchy-placement.AC1.6 | auto |
| 94-hierarchy-placement.AC1.7 | auto |
| 94-hierarchy-placement.AC1.8 | auto |
| 94-hierarchy-placement.AC2.1 | auto |
| 94-hierarchy-placement.AC2.2 | auto |
| 94-hierarchy-placement.AC2.3 | auto |
| 94-hierarchy-placement.AC2.4 | auto |
| 94-hierarchy-placement.AC2.5 | human |
| 94-hierarchy-placement.AC2.6 | human |
| 94-hierarchy-placement.AC2.7 | human |
| 94-hierarchy-placement.AC3.1 | auto |
| 94-hierarchy-placement.AC3.2 | auto |
| 94-hierarchy-placement.AC3.3 | auto |
| 94-hierarchy-placement.AC3.4 | auto |
| 94-hierarchy-placement.AC3.5 | auto |
| 94-hierarchy-placement.AC3.6 | auto |
| 94-hierarchy-placement.AC3.7 | human |
| 94-hierarchy-placement.AC4.1 | auto |
| 94-hierarchy-placement.AC4.2 | auto |
| 94-hierarchy-placement.AC4.3 | auto |
| 94-hierarchy-placement.AC4.4 | auto |
| 94-hierarchy-placement.AC4.5 | auto |
| 94-hierarchy-placement.AC4.6 | auto |
| 94-hierarchy-placement.AC4.7 | auto |
| 94-hierarchy-placement.AC4.8 | auto |
| 94-hierarchy-placement.AC4.9 | auto |
| 94-hierarchy-placement.AC4.10 | auto |
| 94-hierarchy-placement.AC4.11 | auto |
| 94-hierarchy-placement.AC4.12 | human |
