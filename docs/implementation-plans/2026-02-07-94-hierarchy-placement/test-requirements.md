# Test Requirements — 94-hierarchy-placement

## Automated Tests

| AC | Description | Test Type | Test File | Phase |
|----|-------------|-----------|-----------|-------|
| AC1.1 | Activity created with week_id, title, description; has auto-generated UUID and timestamps | Integration | `tests/integration/test_activity_crud.py` | 1 |
| AC1.2 | Activity's template workspace auto-created atomically | Integration | `tests/integration/test_activity_crud.py` | 1 |
| AC1.3 | Creating Activity with non-existent week_id is rejected | Integration | `tests/integration/test_activity_crud.py` | 1 |
| AC1.4 | Creating Activity without week_id is rejected (NOT NULL) | Integration | `tests/integration/test_activity_crud.py` | 1 |
| AC1.5 | Workspace supports optional activity_id, course_id, enable_save_as_draft fields | Integration | `tests/integration/test_workspace_placement_fields.py` | 1 |
| AC1.6 | Workspace with both activity_id and course_id set is rejected (app-level) | Unit | `tests/unit/test_workspace_model.py` | 1 |
| AC1.7 | Deleting Activity sets workspace activity_id to NULL (SET NULL) | Integration | `tests/integration/test_workspace_placement_fields.py` | 1 |
| AC1.8 | Deleting Course sets workspace course_id to NULL (SET NULL) | Integration | `tests/integration/test_workspace_placement_fields.py` | 1 |
| AC2.1 | Create, get, update, delete Activity via CRUD functions | Integration | `tests/integration/test_activity_crud.py` | 1 |
| AC2.2 | Delete Activity cascade-deletes template workspace | Integration | `tests/integration/test_activity_crud.py` | 1 |
| AC2.3 | List Activities for Week returns correct set, ordered by created_at | Integration | `tests/integration/test_activity_crud.py` | 1 |
| AC2.4 | List Activities for Course (via Week join) returns Activities across all Weeks | Integration | `tests/integration/test_activity_crud.py` | 1 |
| AC3.1 | Place workspace in Activity (sets activity_id, clears course_id) | Integration | `tests/integration/test_workspace_placement.py` | 2 |
| AC3.2 | Place workspace in Course (sets course_id, clears activity_id) | Integration | `tests/integration/test_workspace_placement.py` | 2 |
| AC3.3 | Make workspace loose (clears both) | Integration | `tests/integration/test_workspace_placement.py` | 2 |
| AC3.4 | Place workspace in non-existent Activity/Course is rejected | Integration | `tests/integration/test_workspace_placement.py` | 2 |
| AC3.5 | List workspaces for Activity returns placed workspaces | Integration | `tests/integration/test_workspace_placement.py` | 2 |
| AC3.6 | List loose workspaces for Course returns course-associated workspaces | Integration | `tests/integration/test_workspace_placement.py` | 2 |
| AC4.1 | Clone creates new workspace with activity_id set and enable_save_as_draft copied | Integration | `tests/integration/test_workspace_clone.py` | 3 |
| AC4.2 | Cloned documents preserve content, type, source_type, title, order_index | Integration | `tests/integration/test_workspace_clone.py` | 3 |
| AC4.3 | Cloned documents have new UUIDs (independent of template) | Integration | `tests/integration/test_workspace_clone.py` | 3 |
| AC4.4 | Original template documents and CRDT state unmodified after clone | Integration | `tests/integration/test_workspace_clone.py` | 3 |
| AC4.5 | Clone of empty template creates empty workspace with activity_id set | Integration | `tests/integration/test_workspace_clone.py` | 3 |
| AC4.6 | Cloned CRDT highlights reference new document UUIDs (remapped) | Integration | `tests/integration/test_workspace_clone_crdt.py` | 4 |
| AC4.7 | Highlight fields preserved (start_char, end_char, tag, text, author) | Integration | `tests/integration/test_workspace_clone_crdt.py` | 4 |
| AC4.8 | Comments on highlights preserved in clone | Integration | `tests/integration/test_workspace_clone_crdt.py` | 4 |
| AC4.9 | Client metadata NOT cloned (fresh client state) | Integration | `tests/integration/test_workspace_clone_crdt.py` | 4 |
| AC4.10 | Clone of template with no CRDT state produces workspace with null crdt_state | Integration | `tests/integration/test_workspace_clone_crdt.py` | 4 |
| AC4.11 | Clone operation is atomic (all-or-nothing within single transaction) | Integration | `tests/integration/test_workspace_clone_crdt.py` | 4 |

### Implementation Notes for Automated Tests

**AC1.4 (NOT NULL enforcement):** The `week_id` field uses `_cascade_fk_column("week.id")` which is `nullable=False`. Testing at integration level by attempting to create an Activity with `week_id=None` and expecting a database error is the most reliable approach. A pure model-level test is insufficient because SQLModel may allow None in Python but fail at the DB layer.

**AC1.6 (mutual exclusivity):** Unit-testable because this is a Pydantic `@model_validator(mode="after")` that raises `ValueError` purely from in-memory field values. No database interaction needed. Test four cases: both set (reject), activity_id only (accept), course_id only (accept), neither set (accept).

**AC1.7 and AC1.8 (SET NULL behaviour):** These test database-level FK behaviour (`ondelete="SET NULL"`). AC1.8 requires `session.delete(course)` directly because only `archive_course()` exists (soft-delete). The test must bypass the CRUD layer for Course deletion to trigger the real FK cascade.

**AC2.2 (template workspace deletion):** The design uses RESTRICT on `Activity.template_workspace_id`, NOT CASCADE. The application-level `delete_activity()` explicitly deletes the template workspace first, then the Activity. The test verifies `delete_activity()` behaviour, not a database-level CASCADE.

**AC4.1 (enable_save_as_draft copied):** Test both values: create a template with `enable_save_as_draft=True`, clone, verify clone has `True`; repeat with `False`.

**AC4.9 (client metadata not cloned):** Must check `dict(clone_doc.client_meta)` is empty, NOT `get_client_ids()`, because the latter checks an in-memory dict that would be empty on any fresh AnnotationDocument regardless. The test must first write client metadata into the template's CRDT state, clone, then verify the cloned CRDT's `client_meta` Y.Map is empty.

**AC4.11 (atomicity):** Tested in two directions: (1) successful clone produces both documents and CRDT state in a single commit, (2) failed clone (e.g., non-existent activity_id raises ValueError) leaves no partial state.

## Human Verification

| AC | Description | Justification | Verification Approach |
|----|-------------|---------------|----------------------|
| AC2.5 | Activities visible under Weeks on course detail page | UI layout and rendering correctness requires full NiceGUI runtime with `@ui.refreshable` patterns | **Phase 1 UAT:** Seed test data → login → navigate to LAWS1100 → verify Activities appear under Weeks with "Add Activity" buttons. **Evidence:** Screenshot of course detail page. |
| AC2.6 | Create Activity form creates Activity and template workspace | Form submission, navigation, and side-effects span the full NiceGUI request/response cycle | **Phase 1 UAT:** Click "Add Activity" → fill form → submit → verify redirect and Activity visible. **Evidence:** Screenshots of form and result. |
| AC2.7 | Clicking Activity navigates to template workspace in annotation page | Navigation between pages via `workspace_id` query param requires a running app | **Phase 1 UAT:** Click Activity link → verify annotation page loads with template workspace UUID. **Evidence:** Screenshot of annotation page via Activity link. |
| AC3.7 | Workspace placement controls on annotation page | Dialog overlay, dropdown selections, notification feedback, and badge refresh require browser interaction | **Phase 2 UAT:** Open workspace → verify "Loose" badge → change to Activity → verify badge → make loose → place in Course → verify each state. **Evidence:** Screenshots of each placement state. |
| AC4.12 | Instantiate clones template with highlights visible | End-to-end flow: Instantiate button → redirect → CRDT highlights render at correct positions with comments | **Phase 4 UAT:** Add document and highlights to template → Instantiate → verify cloned workspace has highlights, comments, and no stale client metadata. **Evidence:** Screenshots of cloned workspace with highlights and comments. |

### Justification for UAT-Only Criteria

All five human-verification criteria involve NiceGUI page rendering, navigation, and interactive UI controls. The project excludes Playwright E2E tests from `test-all` (they require a live server and separate execution), and E2E test creation is not scoped for this feature. This approach is consistent with the project's existing E2E test isolation strategy documented in CLAUDE.md.
