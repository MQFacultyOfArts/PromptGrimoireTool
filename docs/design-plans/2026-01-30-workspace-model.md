# Workspace Model Design (Seam A)

## Summary

Foundation data model for annotation workspaces. A Workspace is the unit of collaboration and CRDT sync, containing 0..N documents that can be annotated. This seam establishes the core entities, CRUD API, and migrates the existing CRDT persistence from `AnnotationDocumentState` to `Workspace.crdt_state`. Permissions are handled via ACL in Seam D (no `owner_id` field - only `created_by` for audit).

## Definition of Done

**Acceptance Criterion (concrete):**

> Using the new `/annotation` route: upload 183.rtf, annotate it, click export PDF, and get a PDF with all annotations included. All existing E2E tests pass with the new workspace-based interface.

**Deliverables:**

1. **Workspace entity** with Alembic migration
   - `id: UUID` (PK)
   - `created_by: UUID` (FK → User, audit trail only - not ownership)
   - `crdt_state: bytes | None` (serialized pycrdt document)
   - `created_at: datetime`
   - `updated_at: datetime`

2. **WorkspaceDocument entity** with Alembic migration
   - `id: UUID` (PK)
   - `workspace_id: UUID` (FK → Workspace, CASCADE DELETE)
   - `type: str` (domain-defined: "source", "draft", "ai_conversation", etc.)
   - `content: str` (HTML with word-level spans)
   - `raw_content: str` (original pasted/uploaded text)
   - `order_index: int` (display order within workspace)
   - `title: str | None`
   - `created_at: datetime`

3. **CRUD API functions**
   - `create_workspace(created_by: UUID) → Workspace`
   - `delete_workspace(workspace_id: UUID) → None` (cascades documents)
   - `get_workspace(workspace_id: UUID) → Workspace | None`
   - `add_document(workspace_id, type, content, raw_content, title?) → WorkspaceDocument`
   - `list_documents(workspace_id) → list[WorkspaceDocument]` (ordered by order_index)
   - `reorder_documents(workspace_id, document_ids: list[UUID]) → None`

4. **CRDT persistence migration**
   - Remove or deprecate `AnnotationDocumentState` table
   - CRDT persistence uses `Workspace.crdt_state`
   - Update `PersistenceManager` and related code to work with workspaces

5. **Tests**
   - Unit tests for all CRUD operations
   - Migrate all existing live annotation tests to use Workspace
   - E2E test: create workspace, add document, verify data integrity

**Explicitly Out of Scope (deferred to other seams):**
- `activity_id` relationship → Seam B (Hierarchy & Placement)
- `owner_id` / permissions / ACL → Seam D (RBAC/ACL)
- Tag architecture → Seam C
- UI routes (navigation, workspace list) → Seam F

## Glossary

| Term | Definition |
|------|------------|
| **Workspace** | Container for documents and CRDT state. Unit of collaboration and sync. |
| **WorkspaceDocument** | A document within a workspace (source text, draft, AI conversation, etc.) |
| **CRDT** | Conflict-free Replicated Data Type. Enables real-time collaboration without conflicts. |
| **created_by** | Audit field recording who created the workspace. NOT ownership - permissions via ACL. |
| **document_id** | Within CRDT highlight data, identifies which WorkspaceDocument a highlight belongs to. |

---

## Architecture

### Data Model

```
Workspace (1) ←──────── (N) WorkspaceDocument
    │
    └── crdt_state: bytes
            │
            └── Contains highlights, each with document_id reference
```

**Key design decisions:**

1. **One CRDT per workspace** - All annotations across all documents in a workspace share one CRDT state. Each highlight includes `document_id` to identify its target document.

2. **No owner_id** - Permissions handled entirely by ACL (Seam D). `created_by` is audit-only.

3. **Document type is string** - Domains define their own types ("source", "draft", "ai_conversation") without enum constraints.

4. **Copy semantics for source documents** - When instantiated from an Activity (Seam B), source documents are copied into the workspace. Annotations reference positions in the copy. Instructor edits to Activity templates do NOT propagate to existing workspaces.

### CRDT Structure

Current highlight structure (to be extended):
```python
{
    "id": "highlight-uuid",
    "document_id": "workspace-document-uuid",  # NEW - required
    "start_word": 42,
    "end_word": 58,
    "paragraph_num": 12,
    "tag": "issue",
    "note": "This is the key legal issue",
    "author_id": "user-uuid",
    "created_at": "2026-01-30T10:00:00Z"
}
```

### Persistence Flow

```
User makes annotation
    ↓
AnnotationDocument.add_highlight(document_id, ...)
    ↓
PersistenceManager.mark_dirty(workspace_id)
    ↓
[5 second debounce]
    ↓
save_workspace_crdt_state(workspace_id, crdt_bytes)
    ↓
UPDATE workspace SET crdt_state = $1 WHERE id = $2
```

---

## Existing Patterns Followed

| Pattern | Source | Application |
|---------|--------|-------------|
| UUID primary keys | `db/models.py` | `id: UUID = Field(default_factory=uuid4, primary_key=True)` |
| CASCADE DELETE FKs | `_cascade_fk_column()` | `workspace_id` in WorkspaceDocument |
| Timezone-aware timestamps | `_timestamptz_column()` | `created_at`, `updated_at` |
| Async CRUD functions | `annotation_state.py` | All workspace/document operations |
| Repository modules | `db/courses.py`, `db/users.py` | New `db/workspaces.py`, `db/workspace_documents.py` |

---

## Implementation Phases

### Phase 1: Schema & API (additive)

**Goal:** New tables and API exist alongside old system.

1. Create Alembic migration for `workspace` table
2. Create Alembic migration for `workspace_document` table
3. Implement `db/workspaces.py` with CRUD functions
4. Implement `db/workspace_documents.py` with CRUD functions
5. Unit tests for all CRUD operations
6. Update `db/__init__.py` exports

**Verification:** `uv run pytest tests/unit/test_workspace*.py` passes

### Phase 2: CRDT Integration

**Goal:** CRDT persistence works with Workspace model.

1. Add `save_workspace_crdt_state()` function
2. Update `PersistenceManager` to call workspace save (not annotation_state)
3. Update `AnnotationDocumentRegistry` to load from Workspace
4. Update highlight structure to require `document_id`
5. Integration tests for CRDT round-trip with workspace

**Verification:** `uv run pytest tests/integration/test_crdt*.py` passes

### Phase 3: New Route

**Goal:** `/annotation` route works with workspace model.

1. Create `/annotation` page using workspace-based flow
2. User creates/enters workspace
3. User pastes content → creates WorkspaceDocument
4. Annotation UI works with new CRDT structure
5. E2E tests for new route

**Verification:** `uv run pytest tests/e2e/test_annotation.py` passes

### Phase 4: Parallel Operation

**Goal:** Both old and new routes work simultaneously.

1. `/demo/live-annotation` still works (old code)
2. `/annotation` works (new code)
3. Both test suites pass

**Verification:** Full test suite passes

### Phase 5: Teardown

**Goal:** Remove old system.

1. Remove `/demo/live-annotation` route
2. Create migration to drop `annotation_document_state` table
3. Remove `db/annotation_state.py`
4. Remove old CRDT persistence code paths
5. Remove/update old tests

**Verification:** Full test suite passes, no references to `AnnotationDocumentState`

---

## Design Decisions

### Why no owner_id?

**Decision:** Use `created_by` for audit, handle permissions via ACL (Seam D).

**Rationale:**
- Avoids dual permission models (owner field + ACL)
- Group work: multiple people can have "owner" role in ACL
- Transfer ownership = change ACL role, not migrate a field
- Cleaner separation of concerns (Seam A = data, Seam D = permissions)

### Why one CRDT per workspace (not per document)?

**Decision:** Single CRDT contains all highlights, each with `document_id`.

**Rationale:**
- Tab 2 (Organize) needs all highlights across all documents
- Tab 3 sidebar also aggregates highlights
- Single sync point simplifies real-time collaboration
- Matches issue spec: "One CRDT document per workspace"

### Why copy (not reference) source documents?

**Decision:** When workspace is instantiated from Activity, source docs are copied.

**Rationale:**
- Annotations reference word positions; changing source breaks annotations
- Students shouldn't see their work change unexpectedly
- Workspace is self-contained unit of truth
- Admin can edit individual workspaces if corrections needed

### Why string type for documents (not enum)?

**Decision:** `type: str` with domain-defined values.

**Rationale:**
- Case Brief needs: "source"
- Translation needs: "source", "ai_conversation", "draft"
- Future domains may need other types
- Avoid schema migrations for new document types

---

## Additional Considerations

### Test Isolation

All test data uses UUID-based isolation. No `truncate` or `drop_all`. Each test creates its own workspace with unique ID.

### Migration Safety

Phases 1-4 are additive. Only Phase 5 removes the old system. If issues arise, we can stay in Phase 4 indefinitely.

### Future Seams

| Seam | Depends On | Adds To Workspace Model |
|------|------------|------------------------|
| B: Hierarchy | A | `activity_id` FK (nullable) |
| C: Tags | A | Tag entities, highlight→tag relationship |
| D: RBAC/ACL | A | WorkspaceAccess table with roles |
| E: Sharing | A, B, D | Visibility rules |
| G: Annotation Layer | A, C | Full annotation UI integration |

### Performance Considerations

- CRDT state can grow large with many highlights
- `updated_at` indexed for "recently modified" queries
- `workspace_id` indexed on WorkspaceDocument for fast listing

### Related Design: Test Suite Consolidation

See [2026-01-31-test-suite-consolidation.md](./2026-01-31-test-suite-consolidation.md) for the companion design that migrates all E2E tests from `/demo/*` routes to `/annotation`, implements `pytest-subtests` for efficient test structure, and removes demo page dependencies. This work is part of the same branch (93-workspace-model) and should be executed in parallel with Phase 5 (Teardown).

---

## Scenario Reference

See Epic #92 for the "Tute Table" scenario analysis that informed these design decisions.
