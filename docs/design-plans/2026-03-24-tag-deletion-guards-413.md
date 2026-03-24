# Tag Deletion Guards & Import Hardening

**GitHub Issue:** #413

## Summary

This work hardens the tag and document management layer against two classes of bugs that surfaced during the March 2026 incidents: destructive operations that leave CRDT state dangling (the tag deletion 500 cascade), and import races that produce partial state or `IntegrityError` rollbacks under concurrent use.

The fix has three independent strands. First, a bottom-up deletion guard chain is added to the database layer: tag groups cannot be deleted while they contain tags, tags cannot be deleted while highlights reference them, and documents cannot be deleted while they have annotations. Each guard raises a typed `BusinessLogicError` subclass; the UI catches these and shows a clear warning notification instead of propagating an unhandled error. Second, `import_tags_from_workspace` is rewritten to run inside a single database transaction using `INSERT ... ON CONFLICT DO NOTHING`, making it atomic (all-or-nothing) and idempotent (re-importing the same source is safe). Third, buttons that trigger tag creation or import acquire a loading/disabled state for the duration of the async operation, closing the rapid-fire click window that generated 33 `UniqueViolation` rollbacks during the March 16 incident burst.

## Definition of Done

1. **Deletion guard chain:** Deletions are blocked bottom-up — documents with CRDT highlights cannot be deleted, tags with applied highlights cannot be deleted, tag groups containing tags cannot be deleted. Each guard raises a `BusinessLogicError` subclass. The UI surfaces clear error messages to the user (no 500s, no Discord pings).

2. **Import idempotency + atomicity (#365):** `import_tags_from_workspace` runs all group and tag creation in a single DB transaction. Existing groups are skipped by name (matching the existing tag-level dedup). Eliminates partial-import state, race conditions, and pool exhaustion from concurrent imports. Import button gets a loading guard so rapid clicks don't fire concurrent imports.

3. **Tag creation debounce:** "Create New Tag" button gets a loading guard to prevent rapid-fire clicks that bypass `_unique_tag_name` and trigger `UniqueViolation` rollbacks (33 events in the Mar 16 incident burst).

4. **Kill unhandled rollbacks in tag space:** `DuplicateNameError` from import is caught in the UI and shown as a notification. No uncaught `IntegrityError` paths in tag CRUD that hit Discord alerting.

**Out of scope:** Tag toolbar density/overflow UX (#288). Force-delete (workspace-level CASCADE already works). Tag CRDT cleanup refactoring.

## Acceptance Criteria

### tag-deletion-guards-413.AC1: Tag group deletion blocked when group has tags
- **tag-deletion-guards-413.AC1.1 Success:** Deleting an empty tag group succeeds and removes the group
- **tag-deletion-guards-413.AC1.2 Failure:** Deleting a tag group with 1+ tags raises `HasChildTagsError` with correct count
- **tag-deletion-guards-413.AC1.3 Failure:** UI shows warning notification naming the tag count when deletion is blocked
- **tag-deletion-guards-413.AC1.4 Edge:** Group deletion succeeds after all its tags are moved to another group or deleted

### tag-deletion-guards-413.AC2: Tag deletion blocked when tag has highlights
- **tag-deletion-guards-413.AC2.1 Success:** Deleting a tag with zero CRDT highlights succeeds
- **tag-deletion-guards-413.AC2.2 Failure:** Deleting a tag with 1+ CRDT highlights raises `HasHighlightsError` with correct count
- **tag-deletion-guards-413.AC2.3 Failure:** UI shows warning notification naming the highlight count when deletion is blocked
- **tag-deletion-guards-413.AC2.4 Edge:** Tag deletion succeeds after all its highlights are removed

### tag-deletion-guards-413.AC3: Document deletion blocked when document has annotations
- **tag-deletion-guards-413.AC3.1 Success:** Deleting a user-uploaded document with zero annotations succeeds
- **tag-deletion-guards-413.AC3.2 Failure:** Deleting a document with 1+ CRDT highlights raises `HasAnnotationsError` with correct count
- **tag-deletion-guards-413.AC3.3 Failure:** UI shows warning notification naming the annotation count when deletion is blocked
- **tag-deletion-guards-413.AC3.4 Success:** `can_delete_document` returns False when document has annotations (delete button hidden)
- **tag-deletion-guards-413.AC3.5 Edge:** Document deletion succeeds after all annotations on it are removed

### tag-deletion-guards-413.AC4: Import is atomic and idempotent
- **tag-deletion-guards-413.AC4.1 Success:** Importing from a source workspace creates all groups and tags in the target
- **tag-deletion-guards-413.AC4.2 Success:** Re-importing the same source skips all existing items (zero new, all skipped)
- **tag-deletion-guards-413.AC4.3 Success:** Partial tag overlap correctly creates new items and skips existing ones
- **tag-deletion-guards-413.AC4.3a Success:** Existing group name in target correctly remaps source tags to the existing group
- **tag-deletion-guards-413.AC4.4 Success:** `ImportResult` carries correct created/skipped counts for both tags and groups
- **tag-deletion-guards-413.AC4.5 Success:** UI notification reports created and skipped counts
- **tag-deletion-guards-413.AC4.6 Failure:** Import that fails mid-transaction leaves zero partial state (all-or-nothing)
- **tag-deletion-guards-413.AC4.7 Edge:** Concurrent imports to the same workspace do not raise `IntegrityError`

### tag-deletion-guards-413.AC5: UI loading guards prevent rapid-fire clicks
- **tag-deletion-guards-413.AC5.1 Success:** Import button shows loading state and is disabled during async operation
- **tag-deletion-guards-413.AC5.2 Success:** "Add tag" button in management dialog shows loading state during creation
- **tag-deletion-guards-413.AC5.3 Success:** Quick Create save button shows loading state during creation
- **tag-deletion-guards-413.AC5.4 Success:** All three buttons re-enable after operation completes (success or failure)
- **tag-deletion-guards-413.AC5.5 Failure:** `DuplicateNameError` from import shows user notification (not Discord alert)

## Glossary

- **BusinessLogicError**: Base exception class in `db/exceptions.py` used to signal domain rule violations (e.g. deletion blocked) before any database mutation occurs. Subclasses carry structured fields for UI messaging.
- **CRDT (Conflict-free Replicated Data Type)**: The data structure (via the pycrdt library) used to store collaborative annotation state — highlights and their tag references — in a way that merges concurrent edits without conflict. Highlight counts in this document are read from the CRDT, not from a separate relational table.
- **Dual-write**: The pattern of writing new data to both the relational database and the CRDT document in the same operation, so both stores stay in sync.
- **`ON CONFLICT DO NOTHING`**: A PostgreSQL `INSERT` clause that silently skips rows that would violate a unique constraint, enabling idempotent bulk inserts without explicit existence checks or exception handling.
- **`ImportResult`**: A new dataclass returned by `import_tags_from_workspace` carrying created/skipped counts for tags and groups, used to give the user feedback on what the import did.
- **`IntegrityError`**: A SQLAlchemy (and underlying psycopg) exception raised when a database constraint is violated — in this context, a unique constraint on tag name within a workspace.
- **`UniqueViolation`**: The PostgreSQL-level unique constraint error that surfaces as an `IntegrityError` in Python. Caused here by rapid-fire tag creation clicks submitting duplicate names before the first write completes.
- **Loading guard**: A UI pattern where a button is disabled and shows a spinner for the duration of an async operation, preventing a second click before the first completes.
- **Tag group**: A named container that organises tags within a workspace. Deletion hierarchy requires the group to be empty before it can be removed.
- **`group_id` remapping**: During import, source tag groups are recreated in the target workspace with new database IDs. Tags from the source must be inserted using the new target group IDs, not the original ones.
- **`_cleanup_crdt_highlights_for_tag`**: Existing function in `tags.py` that removes CRDT highlight references when a tag is deleted. The deletion guard makes this path unreachable for normal deletes; retained for force-delete scenarios.
- **`can_delete_document` / `can_edit_document`**: Predicate functions in `document_management.py` that determine whether UI controls should be shown. Defence-in-depth layered on top of the DB-level guard.

## Architecture

Three layers of defence prevent data corruption from tag/document deletion and import races:

1. **DB-layer guards** — pre-delete checks in `db/tags.py` and `db/workspace_documents.py` raise `BusinessLogicError` subclasses before any destructive operation. Guards enforce the deletion hierarchy: tag groups cannot be deleted while they contain tags, tags cannot be deleted while CRDT highlights reference them, documents cannot be deleted while they have annotations.

2. **Atomic idempotent import** — `import_tags_from_workspace` rewritten to run in a single `get_session()` transaction using `INSERT ... ON CONFLICT (workspace_id, name) DO NOTHING`. Eliminates race conditions, partial state, and pool exhaustion. Returns `ImportResult` with created/skipped counts for UI feedback.

3. **UI loading guards** — buttons that trigger tag/group creation or import get disable + spinner state during the async operation, preventing rapid-fire clicks that generate `UniqueViolation` rollbacks.

### Exception Hierarchy

Three new `BusinessLogicError` subclasses in `db/exceptions.py`:

- `HasAnnotationsError(document_id, highlight_count)` — document has CRDT highlights
- `HasHighlightsError(tag_id, highlight_count)` — tag has applied highlights
- `HasChildTagsError(group_id, tag_count)` — tag group contains tags

Each carries the entity ID and count for the UI message.

### Data Flow

**Deletion path (tag example):**
1. UI calls `delete_tag(tag_id, crdt_doc=...)`
2. `delete_tag` loads tag, loads DB-persisted CRDT state from workspace, counts highlights referencing tag
3. If count > 0: raise `HasHighlightsError` (no DB mutation occurs)
4. If count == 0: proceed with existing CRDT cleanup + row deletion
5. UI catches `HasHighlightsError`, shows `ui.notify("Cannot delete: N highlights use this tag")`

**Import path:**
1. UI disables import button (loading state)
2. `import_tags_from_workspace` opens single session
3. For each source group: `INSERT ... ON CONFLICT DO NOTHING RETURNING id`; if no return, query existing by name for group_id remap
4. For each source tag: same `ON CONFLICT` pattern
5. Bump `next_group_order` / `next_tag_order` counters
6. CRDT dual-write for newly created items only
7. Return `ImportResult(created_tags, skipped_tags, created_groups, skipped_groups)`
8. UI re-enables button, shows notification with counts

## Existing Patterns

**`BusinessLogicError` hierarchy** — `db/exceptions.py` already has `DeletionBlockedError`, `ProtectedDocumentError`, `TagLockedError` as guards that prevent destructive operations. The three new exceptions follow the same pattern: domain-specific subclass with structured attributes for UI messaging.

**`_flush_or_detect_duplicate`** — `db/tags.py:160` already handles `IntegrityError` from unique constraint violations by catching, rolling back, and raising `DuplicateNameError`. The import rewrite replaces this pattern with `ON CONFLICT DO NOTHING` for the import path, while leaving the existing pattern intact for individual `create_tag`/`create_tag_group` calls.

**Loading button pattern** — `tag_management.py:204` ("Done" button) already uses `btn.disable()` + `btn.props("loading")` with `finally` restore. The same pattern applies to the import, create, and quick-create buttons.

**`can_delete_document` / `can_edit_document`** — `document_management.py:62-86` already uses predicate functions to hide UI controls preemptively. `can_edit_document` checks annotation count; `can_delete_document` does not (gap being fixed).

**`_highlight_count_for_tag`** — `tag_management.py:124` already counts CRDT highlights for a tag. This logic moves to `db/tags.py` (or a shared module) since it's now a DB-layer concern used by the deletion guard.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Exception Types and DB Guards

**Goal:** Add deletion guard checks to the DB layer so destructive operations raise before mutating state.

**Components:**
- `HasAnnotationsError`, `HasHighlightsError`, `HasChildTagsError` in `src/promptgrimoire/db/exceptions.py`
- Pre-delete check in `delete_tag_group` (`src/promptgrimoire/db/tags.py`) — query child tag count, raise `HasChildTagsError`
- Pre-delete check in `delete_tag` (`src/promptgrimoire/db/tags.py`) — load DB-persisted CRDT state, count highlights referencing tag, raise `HasHighlightsError`
- Pre-delete check in `delete_document` (`src/promptgrimoire/db/workspace_documents.py`) — load DB-persisted CRDT state, count document highlights, raise `HasAnnotationsError`
- Highlight count helpers in `db/tags.py` and `db/workspace_documents.py` — read from DB-persisted CRDT (not in-memory snapshot) to close TOCTOU gap
- `can_delete_document` updated to check annotation count (matching `can_edit_document`)

**Dependencies:** None (first phase)

**Done when:** Unit tests verify that `delete_tag_group` raises when group has tags, `delete_tag` raises when tag has highlights, `delete_document` raises when document has annotations. All three pass through when the entity is empty. `can_delete_document` returns False when annotations exist.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: UI Error Handling for Deletion Guards

**Goal:** Surface deletion guard errors as user-friendly notifications instead of unhandled exceptions.

**Components:**
- `_do_delete` closure in `tag_management.py` (group deletion) — catch `HasChildTagsError`, show warning notification
- `_do_delete` closure in `tag_management.py` (tag deletion) — catch `HasHighlightsError`, show warning notification
- `_handle_delete_document` in `document_management.py` — catch `HasAnnotationsError`, show warning notification
- Delete button hidden preemptively via updated `can_delete_document` (defence-in-depth)

**Dependencies:** Phase 1

**Done when:** E2E tests verify that attempting to delete a tag group with tags shows a warning notification and the group survives. Same for tag with highlights and document with annotations. Delete button hidden for documents with annotations.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Atomic Idempotent Import

**Goal:** Rewrite `import_tags_from_workspace` to run in a single transaction with `ON CONFLICT DO NOTHING`.

**Components:**
- `ImportResult` dataclass in `src/promptgrimoire/db/tags.py` — `created_tags`, `skipped_tags`, `created_groups`, `skipped_groups` counts
- Rewritten `import_tags_from_workspace` in `src/promptgrimoire/db/tags.py` — single session, `ON CONFLICT DO NOTHING`, group_id remapping via existing-name lookup, atomic counter bumps
- CRDT dual-write for newly created items only (inside the same function)
- Updated import notification in `tag_import.py` — format `ImportResult` as user-friendly message with created/skipped counts

**Dependencies:** None (independent of Phases 1-2)

**Done when:** Unit tests verify: importing from source creates groups and tags; re-importing same source skips all (idempotent); concurrent imports don't raise `IntegrityError`; partial source overlap correctly creates new items and skips existing ones. `ImportResult` carries correct counts.
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: UI Loading Guards

**Goal:** Prevent rapid-fire clicks on tag creation and import buttons.

**Components:**
- Import button in `tag_import.py:134` — loading state wrapping `_import_from_workspace`
- "Add tag" callback in `tag_management.py` `_add_tag_in_group` — loading state on the trigger button
- Quick Create save button in `tag_quick_create.py:214` — loading state wrapping `_save`
- Catch `DuplicateNameError` in import path (`tag_import.py` `_import_from_workspace`) — currently uncaught, hits Discord

**Dependencies:** None (independent of Phases 1-3)

**Done when:** E2E tests verify that buttons show loading state during async operations and are disabled until completion. `DuplicateNameError` from import shows a notification instead of hitting Discord alerting.
<!-- END_PHASE_4 -->

## Additional Considerations

**Existing `_cleanup_crdt_highlights_for_tag` stays intact.** The deletion guard blocks `delete_tag` when highlights exist, so the cleanup path (`tags.py:774`) becomes unreachable for the normal flow. It remains as defence-in-depth for force-delete scenarios (workspace CASCADE) and potential future administrative tools.

**Memory record correction.** The project memory at `project_incident_20260322_tag_deletion.md` incorrectly states "The DB cascade deleted the tags from the `tag` table." The FK is actually SET NULL — tags survive as ungrouped when their group is deleted. The memory should be corrected during implementation.

**Import `_check_tag_creation_permission` runs once.** The rewritten import checks permission once at the start of the transaction, not per-tag. This is correct — permission doesn't change mid-import.

**TOCTOU gap closed via DB-persisted CRDT read.** The deletion guard for tags and documents reads highlight counts from the *database-persisted* CRDT state (not the in-memory client snapshot), inside the same transaction as the delete. This closes the CRDT propagation delay gap — if another user has synced a highlight, the DB-persisted state includes it. The pattern already exists in `_cleanup_crdt_highlights_from_db` (tags.py:826). Tag/document deletion is a rare operation (single-digit times per workspace lifetime), so the cost of deserialising the CRDT blob inside the transaction is negligible.

**Return type change:** `import_tags_from_workspace` changes from `list[Tag]` to `ImportResult`. Two callers: `tag_import.py:108` (updated in Phase 3) and integration tests in `test_tag_crud.py` (rewritten in Phase 3).
