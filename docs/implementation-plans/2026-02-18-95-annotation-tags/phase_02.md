# Annotation Tag Configuration — Phase 2: Tag CRUD

**Goal:** Create `db/tags.py` with CRUD operations for TagGroup and Tag, including lock enforcement, permission enforcement, reorder, import-from-activity, and tag deletion cascading to CRDT highlights.

**Architecture:** New `db/tags.py` module following the `db/activities.py` CRUD pattern. CRUD functions enforce their own business rules (locked tags reject modification, `allow_tag_creation` resolved internally via PlacementContext). Tag deletion coordinates CRDT highlight cleanup using the lazy-import pattern established by `_replay_crdt_state()` in `db/workspaces.py:469`. Import-from-activity copies tags between workspaces with new UUIDs and group_id remapping.

**Tech Stack:** SQLModel, pycrdt, PostgreSQL

**Scope:** Phase 2 of 6 from original design

**Codebase verified:** 2026-02-18

---

## Acceptance Criteria Coverage

This phase implements and tests:

### 95-annotation-tags.AC2: Tag CRUD
- **95-annotation-tags.AC2.1 Success:** Create tag with name, color, optional group_id, optional description
- **95-annotation-tags.AC2.2 Success:** Update tag name, color, description, group_id
- **95-annotation-tags.AC2.3 Success:** Delete tag removes the Tag row and all CRDT highlights referencing its UUID
- **95-annotation-tags.AC2.4 Success:** Create and update TagGroup (name, order_index)
- **95-annotation-tags.AC2.5 Success:** Delete TagGroup ungroups its tags (SET NULL)
- **95-annotation-tags.AC2.6 Success:** Reorder tags within a group (update order_index)
- **95-annotation-tags.AC2.7 Success:** Reorder groups within a workspace (update order_index)
- **95-annotation-tags.AC2.8 Failure:** Update or delete a tag with `locked=True` is rejected
- **95-annotation-tags.AC2.9 Failure:** Create tag on workspace where `allow_tag_creation` resolves to False is rejected

### 95-annotation-tags.AC3: Import tags from another activity
- **95-annotation-tags.AC3.1 Success:** Import copies TagGroup and Tag rows from source activity's template workspace into target workspace
- **95-annotation-tags.AC3.2 Success:** Imported tags get new UUIDs (independent copies)
- **95-annotation-tags.AC3.3 Success:** Imported tags preserve name, color, description, locked, group assignment, order

---

**Note on AC2.9 scope:** Both `create_tag()` and `create_tag_group()` enforce `allow_tag_creation` internally. The CRUD function resolves `PlacementContext` via the workspace → activity → course join chain and raises `PermissionError` when the permission resolves to False. This is defense-in-depth — the UI will also check, but the CRUD layer is the authoritative enforcement point.

---

## Key Files Reference

These files contain patterns to follow. Read them before implementing:

- `src/promptgrimoire/db/activities.py` — CRUD function pattern (`get_session()`, Ellipsis sentinel, return conventions)
- `src/promptgrimoire/db/workspaces.py:450-516` — `_replay_crdt_state()` for lazy `crdt/` import pattern and CRDT state manipulation
- `src/promptgrimoire/db/workspaces.py:519-599` — `clone_workspace_from_activity()` for document/ID remapping pattern
- `src/promptgrimoire/db/workspaces.py:144-222` — `get_placement_context()` and `_resolve_activity_placement()` for permission resolution
- `src/promptgrimoire/crdt/annotation_doc.py:230-270` — `add_highlight()` and highlight data structure (tag field is a string)
- `src/promptgrimoire/crdt/annotation_doc.py:280-310` — `remove_highlight()` for CRDT highlight removal
- `src/promptgrimoire/crdt/annotation_doc.py:344-375` — `tag_order` Map structure and `set_tag_order()`
- `src/promptgrimoire/db/__init__.py` — module exports pattern (imports + `__all__`)
- `tests/integration/test_activity_crud.py` — integration test pattern (pytestmark skip guard, class-based, async, helper functions)
- `docs/testing.md` — testing guidelines
- `CLAUDE.md` — async fixture rule, project conventions

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: Create db/tags.py with TagGroup and Tag CRUD

**Files:**
- Create: `src/promptgrimoire/db/tags.py`

**Implementation:**

Create a new module following the `db/activities.py` pattern. Include these functions:

**TagGroup CRUD:**
- `async def create_tag_group(workspace_id: UUID, name: str, order_index: int = 0) -> TagGroup` — Creates a TagGroup. Resolves `PlacementContext` via `get_placement_context(workspace_id)` and raises `PermissionError` if `allow_tag_creation` is False.
- `async def get_tag_group(group_id: UUID) -> TagGroup | None`
- `async def update_tag_group(group_id: UUID, name: str | None = None, order_index: int | None = None) -> TagGroup | None`
- `async def delete_tag_group(group_id: UUID) -> bool` — Deletes the group. Tags in the group get `group_id=NULL` via the SET NULL FK constraint. Returns True if found and deleted.
- `async def list_tag_groups_for_workspace(workspace_id: UUID) -> list[TagGroup]` — Returns groups ordered by `order_index`.

**Tag CRUD:**
- `async def create_tag(workspace_id: UUID, name: str, color: str, *, group_id: UUID | None = None, description: str | None = None, locked: bool = False, order_index: int = 0) -> Tag` — Creates a Tag. Resolves `PlacementContext` via `get_placement_context(workspace_id)` and raises `PermissionError` if `allow_tag_creation` is False.
- `async def get_tag(tag_id: UUID) -> Tag | None`
- `async def update_tag(tag_id: UUID, *, name: str | None = ..., color: str | None = ..., description: str | None = ..., group_id: UUID | None = ..., locked: bool | None = None) -> Tag | None` — Uses the Ellipsis sentinel pattern from `update_activity()`. If `tag.locked` is True, only the `locked` field itself may be changed (to allow instructor lock toggle); all other field changes raise `ValueError("Tag is locked")`.
- `async def delete_tag(tag_id: UUID) -> bool` — Checks `tag.locked` and raises `ValueError("Tag is locked")` if locked. Before deleting the Tag row, calls `_cleanup_crdt_highlights_for_tag()` (Task 3) to remove CRDT highlights. Returns True if found and deleted.
- `async def list_tags_for_workspace(workspace_id: UUID) -> list[Tag]` — Returns tags ordered by `order_index`.

**Permission resolution in create functions:**

Both `create_tag()` and `create_tag_group()` must resolve `allow_tag_creation` internally. Import `get_placement_context` from `promptgrimoire.db.workspaces` and call it with the workspace_id. If `ctx.allow_tag_creation` is False, raise `PermissionError("Tag creation not allowed on this workspace")`.

Note: `get_placement_context()` handles workspaces not placed in any activity (returns defaults). Template workspaces (instructor workspaces) placed in activities with `allow_tag_creation=None` inherit from the course default (True), so instructors can create tags on templates by default.

**Lock enforcement:**

`delete_tag()` checks `tag.locked` as a guard clause at the top — raises `ValueError("Tag is locked")` if locked.

`update_tag()` uses a refined lock guard: if `tag.locked` is True and ANY field other than `locked` is being changed (i.e., `name`, `color`, `description`, or `group_id` is not Ellipsis), raise `ValueError("Tag is locked")`. The `locked` field itself is always permitted — this enables the instructor lock toggle in Phase 5. Implementation pattern:
```python
if tag.locked:
    has_non_lock_changes = any(v is not ... for v in [name, color, description, group_id])
    if has_non_lock_changes:
        raise ValueError("Tag is locked")
```

**Verification:**
Run: `uvx ty check`
Expected: No type errors from new module

**Commit:** `feat: add db/tags.py with TagGroup and Tag CRUD`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add reorder and import-from-activity functions

**Files:**
- Modify: `src/promptgrimoire/db/tags.py`

**Implementation:**

Add these functions to `db/tags.py`:

**Reorder functions:**
- `async def reorder_tags(tag_ids: list[UUID]) -> None` — Takes an ordered list of tag UUIDs and sets `order_index` to the list position (0, 1, 2, ...). Uses a single session, fetches all tags, validates they exist, updates `order_index` for each.
- `async def reorder_tag_groups(group_ids: list[UUID]) -> None` — Same pattern for TagGroup ordering.

**Import from activity:**
- `async def import_tags_from_activity(source_activity_id: UUID, target_workspace_id: UUID) -> list[Tag]` — Copies all TagGroups and Tags from the source activity's template workspace into the target workspace with new UUIDs.

The import function:
1. Load the source activity, get its `template_workspace_id`
2. Query all TagGroups for the source template workspace, ordered by `order_index`
3. Query all Tags for the source template workspace, ordered by `order_index`
4. Build a `group_id_map: dict[UUID, UUID]` — for each source TagGroup, create a new TagGroup in the target workspace (same name, order_index), map `old_group_id -> new_group_id`
5. For each source Tag, create a new Tag in the target workspace with: same name, color, description, locked, order_index, and `group_id=group_id_map.get(source_tag.group_id)` (remapped, or None if ungrouped)
6. Return the list of newly created Tags

This follows the same ID-remapping pattern as `clone_workspace_from_activity()` in `db/workspaces.py:580-592` (document ID remapping).

**Verification:**
Run: `uvx ty check`
Expected: No type errors

**Commit:** `feat: add reorder and import_tags_from_activity to db/tags.py`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add tag deletion CRDT highlight cleanup and update exports

**Verifies:** 95-annotation-tags.AC2.3

**Files:**
- Modify: `src/promptgrimoire/db/tags.py`
- Modify: `src/promptgrimoire/db/__init__.py`

**Implementation:**

**CRDT cleanup function in `db/tags.py`:**

Add a private helper `_cleanup_crdt_highlights_for_tag(workspace_id: UUID, tag_id: UUID) -> int` that:
1. Uses a lazy import: `from promptgrimoire.crdt.annotation_doc import AnnotationDocument` (same pattern as `db/workspaces.py:469`)
2. Loads the workspace's `crdt_state` bytes from the DB (via `get_session()`)
3. If no `crdt_state`, returns 0
4. Creates a temporary `AnnotationDocument` and calls `apply_update(crdt_state)`
5. Iterates `doc.get_all_highlights()`, collects IDs of highlights where `highlight["tag"] == str(tag_id)`
6. Calls `doc.remove_highlight(highlight_id)` for each matching highlight
7. Removes the tag_order entry: `del doc.tag_order[str(tag_id)]` (if it exists)
8. Serialises the updated CRDT state via `doc.get_full_state()` and saves back to the workspace's `crdt_state` column
9. Returns the count of removed highlights

This function is called by `delete_tag()` (Task 1) before the Tag row is deleted.

**Update `db/__init__.py` exports:**

Add imports from `db/tags.py` to `src/promptgrimoire/db/__init__.py`:

```python
from promptgrimoire.db.tags import (
    create_tag,
    create_tag_group,
    delete_tag,
    delete_tag_group,
    get_tag,
    get_tag_group,
    import_tags_from_activity,
    list_tag_groups_for_workspace,
    list_tags_for_workspace,
    reorder_tag_groups,
    reorder_tags,
    update_tag,
    update_tag_group,
)
```

Verify `Tag` and `TagGroup` are already in the models import block (added in Phase 1 Task 3). Add all new CRUD function names to `__all__` in alphabetical order.

**Verification:**
Run: `uvx ty check`
Expected: No type errors

Run: `python -c "from promptgrimoire.db import create_tag, create_tag_group, Tag, TagGroup; print('OK')"`
Expected: `OK`

**Commit:** `feat: add CRDT highlight cleanup on tag deletion and update db exports`
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 4-5) -->
<!-- START_TASK_4 -->
### Task 4: Integration tests for CRUD, lock, and permission enforcement

**Verifies:** 95-annotation-tags.AC2.1, 95-annotation-tags.AC2.2, 95-annotation-tags.AC2.4, 95-annotation-tags.AC2.5, 95-annotation-tags.AC2.8, 95-annotation-tags.AC2.9

**Files:**
- Create: `tests/integration/test_tag_crud.py`

**Implementation:**

Follow the pattern from `tests/integration/test_activity_crud.py`:
- Module-level `pytestmark = pytest.mark.skipif(not get_settings().dev.test_database_url, reason="DEV__TEST_DATABASE_URL not configured")`
- Class-based grouping, `@pytest.mark.asyncio async def` methods
- UUID isolation for all created entities
- Helper function `_make_course_week_activity()` that creates a Course (with `default_allow_tag_creation=True`), Week, and Activity, returning all three. Uses `uuid4().hex[:6]` for unique course codes.

**Testing:**

`TestCreateTag`:
- AC2.1: Create a tag with name, color, group_id, description. Verify all fields are set, UUID is generated, `created_at` is set.
- AC2.1: Create a tag with only required fields (name, color). Verify `group_id` is None, `description` is None, `locked` is False, `order_index` is 0.

`TestUpdateTag`:
- AC2.2: Update tag name, color, description, group_id. Verify each field is updated.
- AC2.2: Update with Ellipsis (not provided) leaves field unchanged.

`TestCreateTagGroup`:
- AC2.4: Create a TagGroup with name and order_index. Verify fields and auto-generated UUID.

`TestUpdateTagGroup`:
- AC2.4: Update TagGroup name and order_index. Verify changes.

`TestDeleteTagGroup`:
- AC2.5: Create a TagGroup with a Tag in it. Delete the TagGroup. Verify TagGroup is gone, Tag still exists with `group_id=None`.

`TestLockEnforcement`:
- AC2.8: Create a tag with `locked=True`. Call `update_tag(tag.id, name="New")` — should raise `ValueError`. Call `delete_tag()` — should raise `ValueError`.
- AC2.8: Create a tag with `locked=True`. Call `update_tag(tag.id, locked=False)` — should SUCCEED (lock toggle is always permitted). Verify `tag.locked` is now False.
- AC2.8: Create a tag with `locked=False`. Verify `update_tag()` and `delete_tag()` succeed.

`TestPermissionEnforcement`:
- AC2.9: Create a Course with `default_allow_tag_creation=False`. Create an Activity with `allow_tag_creation=None` (inherits False). Create a workspace placed in the activity. Call `create_tag()` with that workspace_id — should raise `PermissionError`.
- AC2.9: Same setup but with `default_allow_tag_creation=True`. Call `create_tag()` — should succeed.
- AC2.9: Same setup for `create_tag_group()` — verify it also raises `PermissionError` when denied.

**Verification:**
Run: `uv run test-debug`
Expected: All tests pass

**Commit:** `test: add integration tests for tag CRUD, lock, and permission enforcement`
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Integration tests for reorder, import, and CRDT cleanup

**Verifies:** 95-annotation-tags.AC2.3, 95-annotation-tags.AC2.6, 95-annotation-tags.AC2.7, 95-annotation-tags.AC3.1, 95-annotation-tags.AC3.2, 95-annotation-tags.AC3.3

**Files:**
- Modify: `tests/integration/test_tag_crud.py`

**Implementation:**

Add these test classes to `tests/integration/test_tag_crud.py`:

`TestReorderTags`:
- AC2.6: Create 3 tags in a workspace with order_index 0, 1, 2. Call `reorder_tags([tag3.id, tag1.id, tag2.id])`. Verify order_index values are now 0, 1, 2 matching the new order.

`TestReorderTagGroups`:
- AC2.7: Create 3 groups. Call `reorder_tag_groups()` with reversed order. Verify order_index values match new order.

`TestImportTagsFromActivity`:
- AC3.1: Create Activity A with template workspace containing 1 TagGroup and 3 Tags. Create Activity B with its own template workspace. Call `import_tags_from_activity(source_activity_id=A.id, target_workspace_id=B.template_workspace_id)`. Verify target workspace now has 1 TagGroup and 3 Tags.
- AC3.2: Verify imported Tags and TagGroup have different UUIDs from source.
- AC3.3: Verify imported tags preserve name, color, description, locked, order_index. Verify imported tags are assigned to the new TagGroup (not the source TagGroup's UUID).

`TestDeleteTagCrdtCleanup`:
- AC2.3: Create a workspace with a tag. Manually build CRDT state with 3 highlights referencing that tag's UUID (create an `AnnotationDocument`, call `add_highlight()` 3 times with `tag=str(tag.id)`), serialise with `get_full_state()`, save to workspace's `crdt_state`. Call `delete_tag()`. Verify: tag row is gone, load CRDT state into a new `AnnotationDocument`, verify `get_all_highlights()` returns empty list, verify `tag_order` has no entry for the deleted tag UUID.
- AC2.3: Create a workspace with 2 tags. Add highlights for both tags to CRDT. Delete only tag A. Verify: tag A highlights are gone, tag B highlights remain.
- AC2.3 (edge case): Create a workspace with a tag. Build CRDT state with highlights for the tag but do NOT add a `tag_order` entry for it. Call `delete_tag()`. Verify cleanup succeeds without error (missing `tag_order` key is silently skipped) and highlights are removed.

**Verification:**
Run: `uv run test-debug`
Expected: All tests pass

**Commit:** `test: add integration tests for tag reorder, import, and CRDT cleanup`
<!-- END_TASK_5 -->
<!-- END_SUBCOMPONENT_B -->
