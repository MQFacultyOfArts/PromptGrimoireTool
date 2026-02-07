# Seam B: Hierarchy & Placement Design

## Summary

This design introduces **Activities** as a new organisational layer within the course hierarchy. An Activity sits under a Week and owns a template workspace that instructors can populate with documents and annotations. When students "instantiate" an Activity, the system clones the template — both document content and annotation state (highlights, comments) — into a new workspace for that student, with all internal references (e.g., which document a highlight belongs to) correctly remapped to the new copies.

The design also establishes **workspace placement**: workspaces can be loosely associated with a Course (for unstructured student work) or formally placed within an Activity (for submissions tied to a specific assignment). These two associations are mutually exclusive. When an Activity or Course is deleted, student workspaces are preserved but become "loose" rather than deleted — a deliberate data-safety trade-off. Cloning is implemented via API replay rather than binary state copying to ensure CRDT document references are remapped atomically within a single database transaction.

## Definition of Done

Activity entity exists as a child of Week, with a template workspace that can be cloned (including CRDT state) when students instantiate their own workspaces. Workspaces can be optionally associated with an Activity (placed) or a Course (loose student work), with students able to place and remove workspaces freely. All CRUD operations follow existing async patterns with full test coverage.

**Deliverables:**
- Activity entity with Alembic migration (`week_id` required FK, `template_workspace_id` FK, `title`, `description` markdown field)
- Workspace extended with optional `activity_id` and `course_id` FKs (Alembic migration), mutually exclusive or both null
- `enable_save_as_draft` boolean on Workspace (Alembic migration)
- Template workspace auto-creation when Activity is created
- Full workspace cloning (documents + CRDT state) on student instantiation from Activity
- Place/remove workspace into/from Activity or Course (bidirectional)
- CRUD operations following existing async patterns in `db/`
- List Activities for a Week, list Activities for a Course (via Weeks)
- Unit + integration tests for all CRUD and cloning logic

**Not in scope:** Tag configuration (Seam C), permissions/ACL (Seam D), sharing/visibility (Seam E), UI pages (Seam F), export integration (Seam H).

## Acceptance Criteria

### 94-hierarchy-placement.AC1: Activity entity and schema
- **94-hierarchy-placement.AC1.1 Success:** Activity created with week_id, title, description; has auto-generated UUID and timestamps
- **94-hierarchy-placement.AC1.2 Success:** Activity's template workspace auto-created atomically
- **94-hierarchy-placement.AC1.3 Failure:** Creating Activity with non-existent week_id is rejected
- **94-hierarchy-placement.AC1.4 Failure:** Creating Activity without week_id is rejected (NOT NULL)
- **94-hierarchy-placement.AC1.5 Success:** Workspace supports optional activity_id, course_id, enable_save_as_draft fields
- **94-hierarchy-placement.AC1.6 Failure:** Workspace with both activity_id and course_id set is rejected (app-level)
- **94-hierarchy-placement.AC1.7 Success:** Deleting Activity sets workspace activity_id to NULL (SET NULL)
- **94-hierarchy-placement.AC1.8 Success:** Deleting Course sets workspace course_id to NULL (SET NULL)

### 94-hierarchy-placement.AC2: Activity CRUD and course page UI
- **94-hierarchy-placement.AC2.1 Success:** Create, get, update, delete Activity via CRUD functions
- **94-hierarchy-placement.AC2.2 Success:** Delete Activity cascade-deletes template workspace
- **94-hierarchy-placement.AC2.3 Success:** List Activities for Week returns correct set, ordered by created_at
- **94-hierarchy-placement.AC2.4 Success:** List Activities for Course (via Week join) returns Activities across all Weeks
- **94-hierarchy-placement.AC2.5 UAT:** Activities visible under Weeks on course detail page
- **94-hierarchy-placement.AC2.6 UAT:** Create Activity form (title, description) creates Activity and template workspace
- **94-hierarchy-placement.AC2.7 UAT:** Clicking Activity navigates to template workspace in annotation page

### 94-hierarchy-placement.AC3: Workspace placement
- **94-hierarchy-placement.AC3.1 Success:** Place workspace in Activity (sets activity_id, clears course_id)
- **94-hierarchy-placement.AC3.2 Success:** Place workspace in Course (sets course_id, clears activity_id)
- **94-hierarchy-placement.AC3.3 Success:** Make workspace loose (clears both)
- **94-hierarchy-placement.AC3.4 Failure:** Place workspace in non-existent Activity/Course is rejected
- **94-hierarchy-placement.AC3.5 Success:** List workspaces for Activity returns placed workspaces
- **94-hierarchy-placement.AC3.6 Success:** List loose workspaces for Course returns course-associated workspaces
- **94-hierarchy-placement.AC3.7 UAT:** Workspace can be placed into/removed from Activity or Course via UI

### 94-hierarchy-placement.AC4: Workspace cloning (documents + CRDT)
- **94-hierarchy-placement.AC4.1 Success:** Clone creates new workspace with activity_id set and enable_save_as_draft copied
- **94-hierarchy-placement.AC4.2 Success:** Cloned documents preserve content, type, source_type, title, order_index
- **94-hierarchy-placement.AC4.3 Success:** Cloned documents have new UUIDs (independent of template)
- **94-hierarchy-placement.AC4.4 Success:** Original template documents and CRDT state unmodified after clone
- **94-hierarchy-placement.AC4.5 Edge:** Clone of empty template creates empty workspace with activity_id set
- **94-hierarchy-placement.AC4.6 Success:** Cloned CRDT highlights reference new document UUIDs (remapped)
- **94-hierarchy-placement.AC4.7 Success:** Highlight fields preserved (start_char, end_char, tag, text, author)
- **94-hierarchy-placement.AC4.8 Success:** Comments on highlights preserved in clone
- **94-hierarchy-placement.AC4.9 Success:** Client metadata NOT cloned (fresh client state)
- **94-hierarchy-placement.AC4.10 Edge:** Clone of template with no CRDT state produces workspace with null crdt_state
- **94-hierarchy-placement.AC4.11 Success:** Clone operation is atomic (all-or-nothing within single transaction)
- **94-hierarchy-placement.AC4.12 UAT:** Instantiate button clones template and redirects to new workspace with highlights visible

## Glossary

- **Activity**: A discrete assignment or exercise within a Week. Each Activity has an instructor-managed template workspace that students clone when they start work.
- **ACID**: Atomicity, Consistency, Isolation, Durability — database transaction properties ensuring all-or-nothing execution.
- **Alembic**: Database migration tool for SQLAlchemy/SQLModel that tracks and applies schema changes.
- **API replay**: Technique for reconstructing state by calling high-level APIs rather than copying raw data, ensuring references are remapped correctly.
- **CASCADE DELETE**: Foreign key behaviour where deleting a parent record automatically deletes child records (e.g., deleting an Activity deletes its template workspace).
- **CRDT** (Conflict-free Replicated Data Type): Data structure allowing concurrent edits without coordination. pycrdt implements CRDTs for real-time collaborative annotation.
- **Loose workspace**: A workspace not associated with any Activity or Course (both `activity_id` and `course_id` are null).
- **Mutual exclusivity**: Application-level constraint preventing a workspace from being simultaneously placed in an Activity and associated with a Course.
- **pycrdt**: Python library wrapping Yrs (Rust CRDT implementation). Used for collaborative annotation state (highlights, comments).
- **SET NULL**: Foreign key behaviour where deleting a parent record sets the child's FK column to null rather than deleting the child.
- **SQLModel**: ORM combining Pydantic (validation) with SQLAlchemy (database operations).
- **Template workspace**: The instructor-managed workspace owned by an Activity, serving as the prototype for student clones.
- **Workspace placement**: The act of associating a student workspace with an Activity (formal submission) or a Course (loose work).
- **Y.Doc**: pycrdt's core document type. Each workspace has one Y.Doc holding all annotation state.
- **Y.Map**: pycrdt's map data structure (key-value store). Highlights are stored in a Y.Map keyed by highlight UUID.

## Architecture

Activity is a new entity that lives under Week in the course hierarchy. Each Activity owns a template Workspace whose documents and CRDT state get cloned when a student instantiates their own workspace.

```
Course
└── Week
    └── Activity
        └── template Workspace (owned, CASCADE DELETE)
            └── WorkspaceDocument(s)

Workspace (student instance)
├── activity_id → Activity (placed, SET NULL on delete)
├── course_id → Course (loose student work, SET NULL on delete)
└── enable_save_as_draft: bool
```

**Key relationships:**

- `Activity.week_id` — required FK to Week (CASCADE DELETE). Activity always belongs to a Week.
- `Activity.template_workspace_id` — required FK to Workspace (CASCADE DELETE). Deleting Activity destroys its template.
- `Workspace.activity_id` — optional FK to Activity (SET NULL). Student workspaces become loose if Activity is deleted.
- `Workspace.course_id` — optional FK to Course (SET NULL). Loose student work becomes unassociated if Course is deleted.
- `activity_id` and `course_id` are mutually exclusive at the application level (Pydantic validator). A workspace is either placed in an Activity, associated with a Course, or truly loose (both null).

**Workspace cloning via API replay:**

Cloning creates a new Workspace and replays template content through existing APIs rather than copying binary state directly. This ensures document ID references in CRDT highlights are remapped correctly.

1. Create new Workspace, copy `enable_save_as_draft` from template, set `activity_id`.
2. Copy each WorkspaceDocument via `add_document()`, preserving content, type, source_type, title, order. Build `{old_doc_id: new_doc_id}` mapping.
3. Deserialise template CRDT state into temporary AnnotationDocument. Create fresh AnnotationDocument for new workspace. Replay highlights with remapped `document_id` values. Replay comments. Serialise and save.
4. All steps execute within a single database transaction (ACID compliance).

Client metadata (cursor colours, usernames) is not cloned — students start with fresh client state.

## Existing Patterns

Investigation found consistent patterns across the existing data layer:

**CRUD pattern** (`src/promptgrimoire/db/workspaces.py`, `workspace_documents.py`, `courses.py`, `weeks.py`):
- Async functions using `async with get_session() as session:`
- `session.flush()` + `session.refresh()` for returning hydrated objects
- `try/except IntegrityError` for constraint violation handling (in `courses.py`)
- All FKs use `_cascade_fk_column()` helper for CASCADE DELETE

**Model pattern** (`src/promptgrimoire/db/models.py`):
- `_utcnow()` factory for timestamp defaults
- `_cascade_fk_column()` for FK columns
- Named unique constraints (e.g., `uq_course_enrollment_course_user`)
- `max_length` on all string fields

**CRDT pattern** (`src/promptgrimoire/crdt/annotation_doc.py`, `persistence.py`):
- `AnnotationDocument` wraps pycrdt Y.Doc
- Highlights stored in Y.Map with `document_id` field for multi-document support
- Comments nested within highlights
- Persistence manager debounces saves (5 seconds)

**Divergence from existing patterns:**
- `clone_workspace_from_activity()` uses a single session for multiple operations (existing CRUD is one-session-per-function). This is necessary for ACID atomicity of the clone operation.
- `Workspace.activity_id` and `Workspace.course_id` use SET NULL on delete (existing FKs all use CASCADE DELETE). This preserves student work when Activities or Courses are deleted.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Activity Entity, Schema, and CRUD

**Goal:** Activity table exists with correct constraints. Full CRUD operations work. Activities visible on course page.

**Components:**
- Activity model in `src/promptgrimoire/db/models.py` — `id`, `week_id` (required FK), `template_workspace_id` (required FK), `title`, `description`, `created_at`, `updated_at`
- Workspace model extended with `activity_id` (optional FK, SET NULL), `course_id` (optional FK, SET NULL), `enable_save_as_draft` (bool, default False)
- Pydantic validator on Workspace for `activity_id`/`course_id` mutual exclusivity
- Alembic migrations for Activity table and Workspace column additions
- Schema guard updated to verify new table
- Activity CRUD module `src/promptgrimoire/db/activities.py` — `create_activity()`, `get_activity()`, `update_activity()`, `delete_activity()`, `list_activities_for_week()`, `list_activities_for_course()`
- `create_activity()` atomically creates Activity + empty template Workspace in single transaction
- Course page UI: Activity list under each Week in `course_detail_page()`, "Create Activity" form (title, description), Activity links to template workspace in annotation page

**Dependencies:** None (Seam A complete)

**Covers ACs:** 94-hierarchy-placement.AC1.1–AC1.8, AC2.1–AC2.7

**Done when:** Migrations apply cleanly. CRUD operations pass automated tests (creation, FK constraints, SET NULL, cascade delete, listing queries, mutual exclusivity). UAT: create Activity on course page, see it listed under Week, click through to template workspace in annotation page.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Workspace Placement

**Goal:** Workspaces can be placed into/removed from Activities and Courses, with UI controls.

**Components:**
- Placement functions in `src/promptgrimoire/db/workspaces.py` — `place_workspace_in_activity()`, `place_workspace_in_course()`, `make_workspace_loose()`
- Listing functions — `list_workspaces_for_activity()`, `list_loose_workspaces_for_course()`
- FK validation (target Activity/Course must exist)
- Placement UI controls on annotation page for associating workspace with Activity or Course

**Dependencies:** Phase 1 (Activity CRUD and schema)

**Covers ACs:** 94-hierarchy-placement.AC3.1–AC3.7

**Done when:** Placement, removal, and listing pass automated tests (mutual exclusivity enforcement, invalid FK rejection). UAT: place a workspace into an Activity via UI, verify it appears in Activity's workspace list, remove it, verify it's loose.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Workspace Cloning (Documents)

**Goal:** Clone template workspace documents into a new student workspace. Instantiate button on course page.

**Components:**
- Clone function in `src/promptgrimoire/db/workspaces.py` — `clone_workspace_from_activity()` (workspace creation + document cloning)
- Single-transaction execution for ACID compliance
- Document ID mapping (`old_doc_id → new_doc_id`) built during cloning
- "Instantiate" button on Activity in course page — clones template and redirects to new workspace

**Dependencies:** Phase 1 (Activity with template workspace)

**Covers ACs:** 94-hierarchy-placement.AC4.1–AC4.5

**Done when:** Cloning passes automated tests (document field preservation, new UUIDs, empty template, atomicity, original unmodified). UAT: add document to template via annotation page, click Instantiate, verify cloned workspace has the document.
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Workspace Cloning (CRDT State)

**Goal:** Clone template CRDT state with document ID remapping via API replay.

**Components:**
- CRDT replay logic in `clone_workspace_from_activity()` — extends Phase 3's clone function
- Temporary AnnotationDocument for reading template state
- Fresh AnnotationDocument for building cloned state
- Highlight replay with `document_id` remapping using mapping from Phase 3
- Comment replay for each highlight

**Dependencies:** Phase 3 (document cloning with ID mapping)

**Covers ACs:** 94-hierarchy-placement.AC4.6–AC4.12

**Done when:** Automated tests verify CRDT clone with highlights, comment preservation, document ID remapping, empty CRDT clone, no client metadata leakage, atomicity. UAT: annotate template with highlights and comments, Instantiate, verify cloned workspace shows highlights on correct documents in annotation page.
<!-- END_PHASE_4 -->

## Additional Considerations

**SET NULL vs CASCADE for student workspace FKs:** Deleting an Activity or Course must not destroy student work. SET NULL makes workspaces "loose" rather than deleting them. This is a deliberate divergence from the project's CASCADE-everywhere pattern, justified by data safety.

**Empty template edge case:** If an instructor creates an Activity but hasn't added documents yet, students can still instantiate — they get an empty workspace with `activity_id` set. This is valid; the Activity may not be fully configured. The UI should indicate when a template has no content.

**Transaction scope for cloning:** The clone operation spans workspace creation, document copying, and CRDT state replay within a single transaction. This deviates from the one-session-per-function CRUD pattern but is necessary for atomicity. A partial clone (workspace exists but documents missing) would be a data integrity issue.

**Cross-seam notes posted:** Design decisions affecting Seams C, D, E, and F have been documented as comments on their respective GitHub issues (#95, #96, #97, #98).
