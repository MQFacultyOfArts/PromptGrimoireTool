# Test Requirements: CRUD Management (#229)

Maps every acceptance criterion from the [design plan](../../design-plans/2026-03-02-crud-management-229.md) to either an automated test or a documented human verification step.

Slug: `crud-management-229`

---

## Automated Tests

| AC | Description | Test Type | Test File | Phase |
|----|-------------|-----------|-----------|-------|
| crud-management-229.AC1.1 | Instructor edits week title and week_number via dialog; changes persist after page refresh | integration | tests/integration/test_week_activity_edit.py | 4 |
| crud-management-229.AC1.2 | Instructor edits activity title and description via dialog; changes persist after page refresh | integration | tests/integration/test_week_activity_edit.py | 4 |
| crud-management-229.AC1.3 | Edit dialog pre-fills current values from the model | e2e | tests/e2e/test_crud_management.py | 4 |
| crud-management-229.AC1.4 | Edit triggers broadcast refresh to other connected clients | e2e | tests/e2e/test_crud_management.py | 4 |
| crud-management-229.AC1.5 | Template clone warning shown when instructor clicks "Edit Template" on an activity with student clones | e2e | tests/e2e/test_crud_management.py | 4 |
| crud-management-229.AC1.6 | Template clone warning not shown when no students have cloned | e2e | tests/e2e/test_crud_management.py | 4 |
| crud-management-229.AC2.1 | Instructor deletes a week with no student workspaces; week and its activities are removed | integration | tests/integration/test_delete_guards.py | 2 |
| crud-management-229.AC2.2 | Instructor deletes an activity with no student workspaces; activity and template workspace are removed | integration | tests/integration/test_delete_guards.py | 2 |
| crud-management-229.AC2.3 | Delete blocked with notification showing student count when student workspaces exist (force=False) | integration | tests/integration/test_delete_guards.py | 2 |
| crud-management-229.AC2.4 | Admin force-deletes a week with student workspaces; cascade removes all child entities | integration | tests/integration/test_delete_guards.py | 2 |
| crud-management-229.AC2.5 | Confirmation dialog shown before all destructive deletes | e2e | tests/e2e/test_crud_management.py | 5 |
| crud-management-229.AC2.6 | UI refreshes and broadcasts after deletion | e2e | tests/e2e/test_crud_management.py | 5 |
| crud-management-229.AC3.1 | Owner deletes workspace from course detail page; "Start Activity" reappears | e2e | tests/e2e/test_crud_management.py | 6 |
| crud-management-229.AC3.2 | Owner deletes workspace from navigator; card is removed | e2e | tests/e2e/test_crud_management.py | 6 |
| crud-management-229.AC3.3 | Confirmation dialog shown before workspace deletion | e2e | tests/e2e/test_crud_management.py | 6 |
| crud-management-229.AC3.4 | Non-owner cannot see or trigger workspace delete | e2e | tests/e2e/test_crud_management.py | 6 |
| crud-management-229.AC3.5 | DB-level delete_workspace() raises PermissionError when user_id is not workspace owner | integration | tests/integration/test_delete_guards.py | 2 |
| crud-management-229.AC4.1 | Owner deletes a user-uploaded document (source_document_id IS NULL); document and annotations removed, tags preserved | integration | tests/integration/test_delete_guards.py | 2 |
| crud-management-229.AC4.2 | After deletion, owner can upload a replacement document | human | UAT Phase 7 (upload form availability is a rendering concern) | 7 |
| crud-management-229.AC4.3 | Template-cloned document (source_document_id IS NOT NULL) has no delete button in UI | unit | tests/unit/pages/test_organise_documents.py (can_delete_document) | 7 |
| crud-management-229.AC4.4 | DB-level delete_document() raises ProtectedDocumentError for template-cloned documents | integration | tests/integration/test_delete_guards.py | 2 |
| crud-management-229.AC5.1 | Cloned documents have source_document_id set to the template document's ID | integration | tests/integration/test_document_provenance.py | 1 |
| crud-management-229.AC5.2 | User-uploaded documents have source_document_id as NULL | integration | tests/integration/test_document_provenance.py | 1 |
| crud-management-229.AC5.3 | Pre-migration documents have NULL source_document_id (treated as user-uploaded) | integration | tests/integration/test_document_provenance.py | 1 |
| crud-management-229.AC5.4 | Deleting a template source document sets clones' source_document_id to NULL (ON DELETE SET NULL) | integration | tests/integration/test_document_provenance.py | 1 |
| crud-management-229.AC5.5 | Warning shown when deleting a template document that has clones | human | UAT Phase 7 (clone warning dialog is a rendering concern) | 7 |
| crud-management-229.AC6.1 | Admin deletes a unit with no student workspaces | integration | tests/integration/test_delete_guards.py | 2 |
| crud-management-229.AC6.2 | Convenor (coordinator) deletes their own unit with no student workspaces | integration | tests/integration/test_crud_management_ui.py (NiceGUI User) | 5 |
| crud-management-229.AC6.3 | Delete blocked when student workspaces exist (same guard as weeks/activities) | integration | tests/integration/test_delete_guards.py | 2 |
| crud-management-229.AC6.4 | Admin force-deletes unit with student workspaces | integration | tests/integration/test_delete_guards.py | 2 |
| crud-management-229.AC6.5 | Non-admin, non-convenor cannot see Delete Unit button | integration | tests/integration/test_crud_management_ui.py (NiceGUI User) | 5 |
| crud-management-229.AC7.4 | Course detail page uses page_layout() and wider content column | unit | tests/unit/pages/test_courses_layout.py | 3 |
| crud-management-229.AC7.5 | All interactive elements have data-testid attributes (including previously missing ones) | e2e | tests/e2e/test_crud_management.py | 3 |

## Human Verification

| AC | Description | Why Not Automated | Verification Approach |
|----|-------------|-------------------|----------------------|
| crud-management-229.AC7.1 | Settings cog in action bar labelled "Unit Settings" (not icon-only) | Text label vs icon-only is a visual rendering concern. An E2E test can verify the button exists by `data-testid`, but confirming it renders as a text label (not just an icon) requires visual inspection of the Quasar component rendering. | **UAT (Phase 3):** Navigate to `/courses/{id}` as instructor. Verify "Unit Settings" button shows text label in the action bar, not a standalone cog icon. Screenshot for evidence. |
| crud-management-229.AC7.2 | Activity settings labelled "Activity Settings" | Same as AC7.1 -- verifying a text label renders visually rather than an icon requires human eyes on the rendered page. | **UAT (Phase 3):** On the same course detail page, expand a week and verify each activity row shows "Activity Settings" as a text-labelled button, not an icon-only cog. Screenshot for evidence. |
| crud-management-229.AC7.3 | All action buttons follow styling convention (primary/outline/negative) | Button colour, border style, and visual hierarchy are CSS/Quasar rendering concerns. Automated tests can verify `props` strings are set, but whether the visual output matches the intended hierarchy (filled blue vs blue border vs red border vs text-only) requires human review. | **UAT (Phase 3):** On the course detail page, visually confirm: (1) "Add Week" is filled blue (primary), (2) "Manage Enrollments", "Unit Settings", "Activity Settings" have blue borders (outline primary), (3) delete buttons have red borders (outline negative), (4) Cancel/Back are text-only (flat). Screenshot comparison against the styling table in the design plan. |
| crud-management-229.AC4.2 | After deletion, owner can upload a replacement document | Upload form availability is a rendering concern; the upload mechanism is unchanged by document deletion. | **UAT (Phase 7):** Delete a user-uploaded document, verify the upload form is still available on the annotation page. |
| crud-management-229.AC5.5 | Warning shown when deleting a template document that has clones | Clone warning dialog rendering requires visual inspection of the Quasar dialog. `count_document_clones()` is integration-tested separately. | **UAT (Phase 7):** Delete a template source document that has student clones. Verify warning dialog shows clone count before proceeding. |

## Test File Summary

| Test File | Test Type | Phases | AC Coverage |
|-----------|-----------|--------|-------------|
| tests/integration/test_document_provenance.py | integration | 1, 7 | AC5.1, AC5.2, AC5.3, AC5.4 |
| tests/integration/test_delete_guards.py | integration | 2, 7 | AC2.1, AC2.2, AC2.3, AC2.4, AC3.5, AC4.1, AC4.4, AC6.1, AC6.3, AC6.4 |
| tests/unit/pages/test_courses_layout.py | unit | 3 | AC7.4 |
| tests/unit/pages/test_organise_documents.py | unit | 7 | AC4.3 |
| tests/integration/test_week_activity_edit.py | integration | 4 | AC1.1, AC1.2 |
| tests/integration/test_crud_management_ui.py | integration (NiceGUI User) | 5-6 | AC2.5, AC3.1, AC3.3, AC3.4, AC6.2, AC6.5 |

## Coverage Cross-Check

**Total acceptance criteria:** 33 (AC1.1-AC1.6, AC2.1-AC2.6, AC3.1-AC3.5, AC4.1-AC4.4, AC5.1-AC5.5, AC6.1-AC6.5, AC7.1-AC7.5)

- **Automated tests:** 28 criteria
- **Human verification:** 5 criteria (AC4.2, AC5.5, AC7.1, AC7.2, AC7.3)
- **Total covered:** 33 / 33
