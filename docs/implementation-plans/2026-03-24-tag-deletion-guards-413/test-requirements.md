# Test Requirements: Tag Deletion Guards & Import Hardening (#413)

Maps each acceptance criterion from the design to specific automated tests or human verification steps.

## AC1: Tag group deletion blocked when group has tags

### AC1.1 -- Deleting an empty tag group succeeds and removes the group

| Field | Value |
|-------|-------|
| **Test type** | Integration |
| **Test file** | `tests/integration/test_tag_crud.py::TestDeleteTagGroup` |
| **Description** | Create a tag group with zero tags. Call `delete_tag_group(group_id)`. Assert it returns `True` and the group no longer exists in the DB. |
| **Phase/Task** | Phase 1 / Task 2 |

### AC1.2 -- Deleting a tag group with 1+ tags raises `HasChildTagsError` with correct count

| Field | Value |
|-------|-------|
| **Test type** | Integration |
| **Test file** | `tests/integration/test_tag_crud.py::TestDeleteTagGroup` |
| **Description** | Create a tag group, add 2 tags to it. Call `delete_tag_group(group_id)`. Assert `HasChildTagsError` is raised with `tag_count=2`. Assert group still exists. |
| **Phase/Task** | Phase 1 / Task 2 |

### AC1.3 -- UI shows warning notification naming the tag count when deletion is blocked

| Field | Value |
|-------|-------|
| **Test type** | E2E |
| **Test file** | `tests/e2e/test_tag_deletion_guards.py::test_delete_group_with_tags_shows_warning` |
| **Description** | Set up workspace with seeded tags in a group. Open tag management dialog, click delete on the group, confirm in the dialog. Assert an amber warning notification appears containing a tag count. Assert the group survives. |
| **Phase/Task** | Phase 2 / Task 3 |

### AC1.4 -- Group deletion succeeds after all its tags are moved or deleted

| Field | Value |
|-------|-------|
| **Test type** | Integration |
| **Test file** | `tests/integration/test_tag_crud.py::TestDeleteTagGroup` |
| **Description** | Two sub-cases: (a) Create group A with 1 tag and group B. Move the tag to group B (update `group_id`). Assert `delete_tag_group(group_A_id)` succeeds. (b) Create group with 1 tag, delete the tag, assert `delete_tag_group` succeeds. |
| **Phase/Task** | Phase 1 / Task 2 |

---

## AC2: Tag deletion blocked when tag has highlights

### AC2.1 -- Deleting a tag with zero CRDT highlights succeeds

| Field | Value |
|-------|-------|
| **Test type** | Integration |
| **Test file** | `tests/integration/test_tag_crud.py::TestDeleteTag` |
| **Description** | Create a tag with no CRDT highlights referencing it. Call `delete_tag(tag_id)`. Assert returns `True` and tag is gone. |
| **Phase/Task** | Phase 1 / Task 3 |

### AC2.2 -- Deleting a tag with 1+ CRDT highlights raises `HasHighlightsError` with correct count

| Field | Value |
|-------|-------|
| **Test type** | Integration |
| **Test file** | `tests/integration/test_tag_crud.py::TestDeleteTag` |
| **Description** | Create a tag, add 3 CRDT highlights referencing it via `AnnotationDocument.add_highlight(tag=str(tag.id))`, persist CRDT state. Call `delete_tag(tag_id)`. Assert `HasHighlightsError` raised with `highlight_count=3`. Tag still exists. |
| **Phase/Task** | Phase 1 / Task 3 |

### AC2.3 -- UI shows warning notification naming the highlight count when deletion is blocked

| Field | Value |
|-------|-------|
| **Test type** | E2E |
| **Test file** | `tests/e2e/test_tag_deletion_guards.py::test_delete_tag_with_highlights_shows_warning` |
| **Description** | Set up workspace with content and a tag. Create a highlight using that tag via the UI. Open tag management dialog, click delete on the tag, confirm. Assert amber warning notification appears containing "highlight" and a count. Tag still visible. |
| **Phase/Task** | Phase 2 / Task 3 |

### AC2.4 -- Tag deletion succeeds after all its highlights are removed

| Field | Value |
|-------|-------|
| **Test type** | Integration |
| **Test file** | `tests/integration/test_tag_crud.py::TestDeleteTag` |
| **Description** | Create tag with CRDT highlights. Remove all highlights from the CRDT doc, persist updated state. Call `delete_tag(tag_id)`. Assert succeeds. |
| **Phase/Task** | Phase 1 / Task 3 |

---

## AC3: Document deletion blocked when document has annotations

### AC3.1 -- Deleting a user-uploaded document with zero annotations succeeds

| Field | Value |
|-------|-------|
| **Test type** | Integration |
| **Test file** | `tests/integration/test_delete_guards.py::TestDeleteDocument` |
| **Description** | Create a user-uploaded document (`source_document_id=None`) with no CRDT highlights. Call `delete_document(doc_id, user_id=owner_id)`. Assert returns `True`. |
| **Phase/Task** | Phase 1 / Task 4 |

### AC3.2 -- Deleting a document with 1+ CRDT highlights raises `HasAnnotationsError` with correct count

| Field | Value |
|-------|-------|
| **Test type** | Integration |
| **Test file** | `tests/integration/test_delete_guards.py::TestDeleteDocument` |
| **Description** | Create document, add 2 CRDT highlights with `document_id=str(doc.id)`, persist CRDT state. Call `delete_document`. Assert `HasAnnotationsError` raised with `highlight_count=2`. Document still exists. |
| **Phase/Task** | Phase 1 / Task 4 |

### AC3.3 -- UI shows warning notification naming the annotation count when deletion is blocked

| Field | Value |
|-------|-------|
| **Test type** | E2E |
| **Test file** | `tests/e2e/test_tag_deletion_guards.py::test_delete_document_with_annotations_shows_warning` |
| **Description** | Set up workspace with content. Add a highlight annotation. Open document management, click delete. Assert amber warning notification containing "annotation" and a count. Document still present. |
| **Phase/Task** | Phase 2 / Task 3 |

### AC3.4 -- `can_delete_document` returns False when document has annotations (delete button hidden)

| Field | Value |
|-------|-------|
| **Test type** | Unit |
| **Test file** | `tests/unit/test_document_management.py` |
| **Description** | Call `can_delete_document(user_uploaded_doc, is_owner=True, annotation_count=3)`. Assert returns `False`. Also verify positive case (`annotation_count=0` returns `True`), template doc case (`source_document_id` set returns `False`), and non-owner case (`is_owner=False` returns `False`). Pure function tests with mock `WorkspaceDocument` objects. |
| **Phase/Task** | Phase 1 / Task 5 |

### AC3.5 -- Document deletion succeeds after all annotations on it are removed

| Field | Value |
|-------|-------|
| **Test type** | Integration |
| **Test file** | `tests/integration/test_delete_guards.py::TestDeleteDocument` |
| **Description** | Create document with CRDT highlights. Remove all highlights, persist updated CRDT state. Call `delete_document`. Assert succeeds. |
| **Phase/Task** | Phase 1 / Task 4 |

---

## AC4: Import is atomic and idempotent

### AC4.1 -- Importing from a source workspace creates all groups and tags in the target

| Field | Value |
|-------|-------|
| **Test type** | Integration |
| **Test file** | `tests/integration/test_tag_crud.py::TestImportTagsFromWorkspace` |
| **Description** | Source workspace has 2 groups and 3 tags. Call `import_tags_from_workspace`. Assert `result.created_groups` has 2 items, `result.created_tags` has 3 items. Verify all exist in the target DB. |
| **Phase/Task** | Phase 3 / Task 1 |

### AC4.2 -- Re-importing the same source skips all existing items

| Field | Value |
|-------|-------|
| **Test type** | Integration |
| **Test file** | `tests/integration/test_tag_crud.py::TestImportTagsFromWorkspace` |
| **Description** | Import from source once. Import again. Assert `result.created_tags == []`, `result.skipped_tags == 3`, `result.created_groups == []`, `result.skipped_groups == 2`. No duplicate rows in target. |
| **Phase/Task** | Phase 3 / Task 1 |

### AC4.3 -- Partial tag overlap correctly creates new items and skips existing ones

| Field | Value |
|-------|-------|
| **Test type** | Integration |
| **Test file** | `tests/integration/test_tag_crud.py::TestImportTagsFromWorkspace` |
| **Description** | Target already has 1 tag with the same name as a source tag. Import. Assert that tag is skipped, the other source tags are created. Counts match. |
| **Phase/Task** | Phase 3 / Task 1 |

### AC4.3a -- Existing group name in target correctly remaps source tags to the existing group

| Field | Value |
|-------|-------|
| **Test type** | Integration |
| **Test file** | `tests/integration/test_tag_crud.py::TestImportTagsFromWorkspace` |
| **Description** | Target has a group with the same name as a source group. Source has tags in that group. Import. Assert the group is skipped (not duplicated), source tags are created under the existing target group's ID. |
| **Phase/Task** | Phase 3 / Task 1 |

### AC4.4 -- `ImportResult` carries correct created/skipped counts

| Field | Value |
|-------|-------|
| **Test type** | Integration |
| **Test file** | `tests/integration/test_tag_crud.py::TestImportTagsFromWorkspace` |
| **Description** | Covered by assertions in AC4.1 through AC4.3a tests. Each test verifies `ImportResult` fields (`created_tags`, `skipped_tags`, `created_groups`, `skipped_groups`) are accurate. |
| **Phase/Task** | Phase 3 / Task 1 |

### AC4.5 -- UI notification reports created and skipped counts

| Field | Value |
|-------|-------|
| **Test type** | E2E |
| **Test file** | `tests/e2e/test_tag_import.py` (extend existing) |
| **Description** | Set up source and target workspaces. Perform import via UI. Assert notification text includes created count. Perform import again. Assert notification says "No new tags to import" or shows skipped counts. |
| **Phase/Task** | Phase 3 / Task 2 |
| **Human verification** | Notification text pluralisation edge cases ("1 tag" vs "2 tags") are verbose to test exhaustively. Manual: import tags in dev, verify notification reads naturally for 0/1/N combinations. |

### AC4.6 -- Import that fails mid-transaction leaves zero partial state

| Field | Value |
|-------|-------|
| **Test type** | Integration |
| **Test file** | `tests/integration/test_tag_crud.py::TestImportTagsFromWorkspace` |
| **Description** | Create source workspace where one tag has an invalid color value violating `ck_tag_color_hex`. Import should raise `IntegrityError`. Verify target workspace has zero new groups and zero new tags, proving the entire transaction rolled back atomically. |
| **Phase/Task** | Phase 3 / Task 1 |

### AC4.7 -- Concurrent imports to the same workspace do not raise `IntegrityError`

| Field | Value |
|-------|-------|
| **Test type** | Integration |
| **Test file** | `tests/integration/test_tag_crud.py::TestImportTagsFromWorkspace` |
| **Description** | Run two concurrent imports (`asyncio.gather`) from the same source to the same target. Assert neither raises `IntegrityError`. Combined result across both calls produces the correct final state (all items exist, no duplicates). |
| **Phase/Task** | Phase 3 / Task 1 |

---

## AC5: UI loading guards prevent rapid-fire clicks

### AC5.1 -- Import button shows loading state and is disabled during async operation

| Field | Value |
|-------|-------|
| **Test type** | E2E |
| **Test file** | `tests/e2e/test_tag_loading_guards.py::test_import_button_prevents_double_import` |
| **Description** | Open tag import, select source workspace, click import. Assert the button has the `disabled` attribute during the operation. After import completes, assert button is re-enabled. |
| **Phase/Task** | Phase 4 / Task 4 |
| **Human verification** | Button loading state is transient and racy to assert in E2E. Tests use outcome-based assertions (no duplicate entities from rapid clicks) as primary verification. Transient `disabled` attribute checks are best-effort. |

### AC5.2 -- "Add tag" button in management dialog shows loading state during creation

| Field | Value |
|-------|-------|
| **Test type** | E2E |
| **Test file** | `tests/e2e/test_tag_loading_guards.py::test_add_tag_button_prevents_rapid_creation` |
| **Description** | Open tag management dialog, click "Add tag". Wait for tag to appear. Count tags — assert exactly 1 new tag (not 2+ from rapid clicks). |
| **Phase/Task** | Phase 4 / Task 4 |

### AC5.3 -- Quick Create save button shows loading state during creation

| Field | Value |
|-------|-------|
| **Test type** | E2E |
| **Test file** | `tests/e2e/test_tag_loading_guards.py::test_quick_create_button_prevents_double_create` |
| **Description** | Open quick create dialog, fill tag name, click Create. Assert button has `disabled` attribute during creation. After creation, assert tag appears in toolbar. |
| **Phase/Task** | Phase 4 / Task 4 |

### AC5.4 -- All three buttons re-enable after operation completes (success or failure)

| Field | Value |
|-------|-------|
| **Test type** | E2E |
| **Test file** | `tests/e2e/test_tag_loading_guards.py` (covered by AC5.1, AC5.2, AC5.3 tests) |
| **Description** | Each of the three tests above asserts the button is re-enabled after the operation. For the failure case (e.g. import with no source selected, or duplicate name), verify the button re-enables after the error notification. |
| **Phase/Task** | Phase 4 / Task 4 |

### AC5.5 -- `DuplicateNameError` from import shows user notification (not Discord alert)

| Field | Value |
|-------|-------|
| **Test type** | Integration + Code Review |
| **Test file** | `tests/integration/test_tag_crud.py::TestImportTagsFromWorkspace` (DB-layer) |
| **Description** | After Phase 3's `ON CONFLICT DO NOTHING` rewrite, `DuplicateNameError` should be unreachable from the import path. The catch in `tag_import.py` is defence-in-depth. Test at the DB layer that concurrent imports do not raise `DuplicateNameError` (covered by AC4.7). |
| **Phase/Task** | Phase 4 / Task 1 |
| **Human verification** | Verify by code review that `except DuplicateNameError` block uses `logger.warning()` (not `logger.exception()` which would be ERROR level and trigger Discord). |

---

## Exception Classes (supporting tests)

| AC | Test type | Test file | Description | Phase/Task |
|----|-----------|-----------|-------------|------------|
| All | Unit | `tests/unit/test_exceptions.py` | Instantiation stores attributes correctly. Message includes count with correct pluralisation (singular/plural). All three are `BusinessLogicError` subclasses. | Phase 1 / Task 1 |

---

## Summary: Test File Inventory

| Test File | Type | Lane | ACs Covered | Phase |
|-----------|------|------|-------------|-------|
| `tests/unit/test_exceptions.py` | Unit | unit (xdist) | Supporting (exception classes) | P1 |
| `tests/unit/test_document_management.py` | Unit | unit (xdist) | AC3.4 | P1 |
| `tests/integration/test_tag_crud.py::TestDeleteTagGroup` | Integration | integration (xdist) | AC1.1, AC1.2, AC1.4 | P1 |
| `tests/integration/test_tag_crud.py::TestDeleteTag` | Integration | integration (xdist) | AC2.1, AC2.2, AC2.4 | P1 |
| `tests/integration/test_delete_guards.py::TestDeleteDocument` | Integration | integration (xdist) | AC3.1, AC3.2, AC3.5 | P1 |
| `tests/integration/test_tag_crud.py::TestImportTagsFromWorkspace` | Integration | integration (xdist) | AC4.1-AC4.4, AC4.6, AC4.7 | P3 |
| `tests/e2e/test_tag_deletion_guards.py` | E2E | playwright | AC1.3, AC2.3, AC3.3 | P2 |
| `tests/e2e/test_tag_import.py` (extend) | E2E | playwright | AC4.5 | P3 |
| `tests/e2e/test_tag_loading_guards.py` | E2E | playwright | AC5.1-AC5.4 | P4 |

## Criteria Requiring Human Verification

| AC | Reason | Verification Approach |
|----|--------|----------------------|
| AC4.5 | Notification text pluralisation edge cases | Manual: import tags in dev, verify notification reads naturally for 0/1/N created/skipped combinations |
| AC5.5 | Log level policy verification | Code review: verify `except DuplicateNameError` uses `logger.warning()`, not `logger.exception()` |
| AC5.1/5.2/5.3 | Transient button loading state is racy in E2E | E2E tests use outcome-based assertions (no duplicate entities). If flaky, downgrade to manual: click rapidly, confirm only one entity created |
