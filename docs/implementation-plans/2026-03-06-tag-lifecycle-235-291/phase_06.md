# Tag Lifecycle Refactor — Phase 6: Unified Import

**Goal:** Single import mechanism from any accessible workspace, replacing `import_tags_from_activity()`.

**Architecture:** New `import_tags_from_workspace()` function that reads source tags/groups from DB, skips duplicates by name, creates new UUIDs, writes to target DB + CRDT via dual write. Access check at the function boundary via `resolve_permission()`. Workspace picker UI available to all users, listing all readable workspaces grouped by course/unit.

**Tech Stack:** SQLModel (existing queries), resolve_permission (existing ACL), NiceGUI ui.select

**Scope:** 8 phases from original design (phase 6 of 8)

**Codebase verified:** 2026-03-06

---

## Acceptance Criteria Coverage

This phase implements and tests:

### tag-lifecycle-235-291.AC3: Unified import
- **tag-lifecycle-235-291.AC3.1 Success:** User can import tags from a workspace they have read access to
- **tag-lifecycle-235-291.AC3.2 Success:** Imported tags merge additively — existing tags are preserved
- **tag-lifecycle-235-291.AC3.3 Success:** Tags with duplicate names in the target workspace are skipped
- **tag-lifecycle-235-291.AC3.4 Success:** Imported tag groups and ordering are preserved, appended after existing tags
- **tag-lifecycle-235-291.AC3.5 Success:** Imported tags default to unlocked regardless of source locked status
- **tag-lifecycle-235-291.AC3.6 Success:** Import is available to all users, not just instructors
- **tag-lifecycle-235-291.AC3.7 Edge:** Importing from a workspace with no tags produces no error and no changes

---

## Pre-existing Complexity Violations

The following functions in files touched by this phase exceed the complexipy threshold (15). Every function in every file this phase touches must be below 15 after changes, or commits will be rejected by pre-commit hook:

| Function | File | Complexity | Action |
|----------|------|-----------|--------|
| `update_tag` | db/tags.py | **18** | Phase 2 should have fixed this. If it's still above 15, this phase must extract lock-check and partial-update logic into helpers before committing. |

New function `import_tags_from_workspace` must also stay ≤15. No pre-existing violations in tag_import.py (max 6).

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Create `import_tags_from_workspace()` function

**Verifies:** tag-lifecycle-235-291.AC3.1, tag-lifecycle-235-291.AC3.2, tag-lifecycle-235-291.AC3.3, tag-lifecycle-235-291.AC3.4, tag-lifecycle-235-291.AC3.5, tag-lifecycle-235-291.AC3.7

**Files:**
- Modify: `src/promptgrimoire/db/tags.py` (add new function after `import_tags_from_activity`)
- Test: `tests/integration/test_tag_crud.py` (new test class)

**Implementation:**

Create a new async function:

```python
async def import_tags_from_workspace(
    source_workspace_id: UUID,
    target_workspace_id: UUID,
    user_id: UUID,
    crdt_doc: AnnotationDocument | None = None,
) -> list[Tag]:
    """Import tags and groups from a source workspace.

    Additive merge: existing tags in target are preserved. Tags with
    duplicate names (case-insensitive) are skipped. Imported tags default
    to unlocked regardless of source locked status.

    Args:
        source_workspace_id: Workspace to import from.
        target_workspace_id: Workspace to import into.
        user_id: User performing the import (must have read access to source).
        crdt_doc: Optional live CRDT doc for dual-write.

    Returns:
        List of newly created Tag objects.

    Raises:
        PermissionError: If user lacks read access to source workspace.
    """
```

Logic:
1. Check access: `resolve_permission(source_workspace_id, user_id)` — if None, raise `PermissionError`
2. Load source: `list_tag_groups_for_workspace(source_workspace_id)`, `list_tags_for_workspace(source_workspace_id)`
3. Load target existing names: `list_tags_for_workspace(target_workspace_id)` → `{t.name.lower() for t in tags}`
4. Create groups: for each source group, create with new UUID via `create_tag_group(target_workspace_id, group.name, crdt_doc=crdt_doc)`, maintain `group_id_map`
5. Create tags: for each source tag, skip if `tag.name.lower() in existing_names`, else `create_tag(target_workspace_id, tag.name, tag.color, group_id=group_id_map.get(tag.group_id), description=tag.description, locked=False, crdt_doc=crdt_doc)`
6. Return list of created tags

**Complexity budget:** Keep total function ≤15. Extract helpers if needed:
- `_check_import_access(source_workspace_id, user_id)` for permission check
- Reuse existing `create_tag()` and `create_tag_group()` (which now handle dual write from Phase 2)

**Testing:**

Integration tests:
- tag-lifecycle-235-291.AC3.1: Import from accessible workspace — verify tags created
- tag-lifecycle-235-291.AC3.2: Import when target has existing tags — verify existing preserved
- tag-lifecycle-235-291.AC3.3: Import when target has tag with same name — verify duplicate skipped
- tag-lifecycle-235-291.AC3.4: Verify imported groups and tags have correct order_index (appended after existing)
- tag-lifecycle-235-291.AC3.5: Import tag that is locked in source — verify unlocked in target
- tag-lifecycle-235-291.AC3.7: Import from workspace with no tags — verify no error, no changes
- Permission: Import from workspace user cannot access — verify PermissionError raised

**Verification:**
Run: `uv run pytest tests/integration/test_tag_crud.py -v -k "import_workspace"`
Expected: All tests pass

Run: `uv run complexipy src/promptgrimoire/db/tags.py --max-complexity-allowed 15`
Expected: No new violations

**Commit:** `feat: add import_tags_from_workspace with duplicate skipping and access check`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Create accessible workspaces listing query

**Verifies:** tag-lifecycle-235-291.AC3.1, tag-lifecycle-235-291.AC3.6

**Files:**
- Modify: `src/promptgrimoire/db/acl.py` (add new query function)
- Test: `tests/integration/test_tag_crud.py` (or new test file)

**Implementation:**

Add a function that lists workspaces the user can read, grouped by course:

```python
async def list_importable_workspaces(
    user_id: UUID,
    exclude_workspace_id: UUID | None = None,
) -> list[tuple[Workspace, str | None]]:
    """List workspaces with tags that the user can read from.

    Returns (workspace, course_name) tuples, ordered by course then workspace title.
    Excludes the specified workspace (typically the target).
    """
```

Logic:
1. Use `list_accessible_workspaces(user_id)` (confirmed at `db/acl.py:114`) as base — returns `list[tuple[Workspace, str]]`
2. Filter: exclude `exclude_workspace_id`, include only workspaces that have tags (join with Tag table, COUNT > 0)
3. Join with Course hierarchy for grouping: Workspace → Activity → Week → Course
4. Return sorted by course name then workspace title

**Testing:**

Integration tests:
- User with ACL on workspace sees it in list
- Workspace with no tags is excluded
- Target workspace is excluded
- User without access to workspace doesn't see it

**Verification:**
Run: `uv run pytest tests/integration/ -v -k "importable"`
Expected: All tests pass

**Commit:** `feat: add list_importable_workspaces query for tag import`

<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: Replace import UI with workspace picker for all users

**Verifies:** tag-lifecycle-235-291.AC3.1, tag-lifecycle-235-291.AC3.6

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/tag_import.py` (rewrite)
- Modify: `src/promptgrimoire/pages/annotation/tag_management.py:245-251` (remove instructor gate)

**Implementation:**

1. In `tag_management.py`, remove the `if is_instructor:` gate around `_render_import_section()` (line 245). The import section should always render.

2. Rewrite `_render_import_section()` in `tag_import.py`:
   - Call `list_importable_workspaces(user_id, exclude_workspace_id=state.workspace_id)`
   - Build grouped options for `ui.select()`: `{ws.id: f"{course_name} / {ws.title}" for ws, course_name in workspaces}`
   - On import button click: call `import_tags_from_workspace(source_ws_id, target_ws_id, user_id, crdt_doc=state.crdt_doc)`
   - After import: call `_refresh_tag_state(state)` then `await state.broadcast_update()`
   - Handle empty source gracefully (AC3.7)

3. Add `data-testid="import-workspace-select"` and `data-testid="import-tags-btn"` for E2E testability.

**Testing:**

- Unit/integration coverage from Tasks 1-2
- E2E coverage in Task 4

**Verification:**
Run: `uv run grimoire test changed`
Expected: All tests pass

Run: `uv run complexipy src/promptgrimoire/pages/annotation/tag_import.py --max-complexity-allowed 15`
Expected: No violations

**Commit:** `feat: replace activity-only tag import with workspace picker for all users`

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: E2E test — student user can access and use tag import

**Verifies:** tag-lifecycle-235-291.AC3.6

**Files:**
- Test: `tests/e2e/test_tag_import.py` (new file)

**Implementation:**

E2E test verifying the instructor gate is removed:

1. Log in as a student user (not instructor, not admin)
2. Open a workspace the student has write access to
3. Open the tag management dialog
4. Verify the import section is visible (`get_by_test_id("import-workspace-select")` exists)
5. Select a source workspace from the picker
6. Click import (`get_by_test_id("import-tags-btn")`)
7. Verify imported tags appear in the tag toolbar

This test catches regressions where the instructor gate is accidentally re-added or another permission check blocks students.

**Testing:**

Single test: `test_student_can_import_tags`

**Verification:**
Run: `uv run grimoire e2e run -k "student_can_import"`
Expected: Test passes

**Commit:** `test: E2E verify student user can import tags`

<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Full regression verification

**Verifies:** None (regression verification)

**Files:**
- No modifications — verification only

**Verification:**
Run: `uv run grimoire test all`
Expected: All tests pass

**Commit:** No commit needed — verification only

<!-- END_TASK_5 -->
<!-- END_SUBCOMPONENT_B -->
