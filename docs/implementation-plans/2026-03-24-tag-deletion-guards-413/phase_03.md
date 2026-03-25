# Tag Deletion Guards & Import Hardening — Phase 3: Atomic Idempotent Import

**Goal:** Rewrite `import_tags_from_workspace` to run in a single transaction with `ON CONFLICT DO NOTHING`, making it atomic and idempotent.

**Architecture:** Single `get_session()` block wraps all group and tag inserts using `pg_insert().on_conflict_do_nothing(constraint=...)`. Created vs skipped detected via `RETURNING`. Group-id remapping for existing groups via name lookup. Bulk counter increment instead of per-item. Returns `ImportResult` dataclass with created/skipped counts.

**Tech Stack:** Python 3.14, SQLAlchemy `pg_insert`, PostgreSQL `ON CONFLICT DO NOTHING`, pycrdt

**Scope:** Phase 3 of 4 from original design (independent of Phases 1-2)

**Codebase verified:** 2026-03-24

---

## Acceptance Criteria Coverage

This phase implements and tests:

### tag-deletion-guards-413.AC4: Import is atomic and idempotent
- **tag-deletion-guards-413.AC4.1 Success:** Importing from a source workspace creates all groups and tags in the target
- **tag-deletion-guards-413.AC4.2 Success:** Re-importing the same source skips all existing items (zero new, all skipped)
- **tag-deletion-guards-413.AC4.3 Success:** Partial tag overlap correctly creates new items and skips existing ones
- **tag-deletion-guards-413.AC4.3a Success:** Existing group name in target correctly remaps source tags to the existing group
- **tag-deletion-guards-413.AC4.4 Success:** `ImportResult` carries correct created/skipped counts for both tags and groups
- **tag-deletion-guards-413.AC4.5 Success:** UI notification reports created and skipped counts
- **tag-deletion-guards-413.AC4.6 Failure:** Import that fails mid-transaction leaves zero partial state (all-or-nothing)
- **tag-deletion-guards-413.AC4.7 Edge:** Concurrent imports to the same workspace do not raise `IntegrityError`

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Add ImportResult dataclass and rewrite import_tags_from_workspace

**Verifies:** tag-deletion-guards-413.AC4.1, tag-deletion-guards-413.AC4.2, tag-deletion-guards-413.AC4.3, tag-deletion-guards-413.AC4.3a, tag-deletion-guards-413.AC4.4, tag-deletion-guards-413.AC4.6, tag-deletion-guards-413.AC4.7

**Files:**
- Modify: `src/promptgrimoire/db/tags.py:694-754` (rewrite `import_tags_from_workspace`)
- Modify: `src/promptgrimoire/db/tags.py` (add `ImportResult` dataclass near line 694)
- Test: `tests/integration/test_tag_crud.py::TestImportTagsFromWorkspace` (rewrite tests for new return type)

**Implementation:**

**Step A — Add `ImportResult` dataclass:**

Place above `import_tags_from_workspace` (near line 694). Use `dataclasses.dataclass` (not Pydantic — this is a simple value object, not a model).

```python
from dataclasses import dataclass, field

@dataclass
class ImportResult:
    """Result of import_tags_from_workspace.

    Attributes:
        created_tags: Newly created Tag objects.
        skipped_tags: Count of source tags skipped (name already existed).
        created_groups: Newly created TagGroup objects.
        skipped_groups: Count of source groups skipped (name already existed).
    """

    created_tags: list[Tag] = field(default_factory=list)
    skipped_tags: int = 0
    created_groups: list[TagGroup] = field(default_factory=list)
    skipped_groups: int = 0
```

**Step B — Rewrite `import_tags_from_workspace`:**

The current implementation (lines 694-754) calls `create_tag_group` and `create_tag` in loops — each opens its own session. Rewrite to use a single `get_session()` block with `pg_insert().on_conflict_do_nothing()`.

Key implementation details:

1. **Permission checks** run before the session block:
   - `_check_import_access(source_workspace_id, user_id)` — verifies read access to source
   - `_check_tag_creation_permission(target_workspace_id)` — verifies tag creation allowed on target

2. **Source data read** happens before the session block (uses its own sessions internally):
   - `list_tag_groups_for_workspace(source_workspace_id)` — get source groups
   - `list_tags_for_workspace(source_workspace_id)` — get source tags
   - Early return `ImportResult()` if both are empty

3. **Single session block** for all mutations:
   - **Groups first:** For each source group, use `pg_insert(TagGroup).values(...).on_conflict_do_nothing(constraint="uq_tag_group_workspace_name").returning(TagGroup.id, TagGroup.name)`. If row returned → created (add to result, map source→target ID). If no row returned → existing, query by `(workspace_id, name)` to get ID for remapping.
   - **Tags second:** For each source tag, resolve `group_id` via the remap dict. Use `pg_insert(Tag).values(...).on_conflict_do_nothing(constraint="uq_tag_workspace_name").returning(Tag.id, Tag.name)`. If row returned → created (add to result). If no row returned → skipped.
   - **Counter bumps:** After all inserts, increment `next_group_order` by number of created groups and `next_tag_order` by number of created tags, using single `UPDATE` statements.
   - **Order indices:** Before inserting, read the current `next_group_order` and `next_tag_order` from the workspace. Assign `order_index = base + offset` for each new item.

4. **CRDT dual-write** for newly created items only (inside the same `get_session()` block, before the session closes — matching the existing pattern in `create_tag` and `create_tag_group`):
   - `crdt_doc.set_tag_group(group_id, name, color, order_index)` for each created group
   - `crdt_doc.set_tag(tag_id, name, colour, order_index, group_id, description, highlights=[])` for each created tag

5. **Return type:** `ImportResult` with populated lists and counts.

Existing `pg_insert` import pattern from `users.py:138`:
```python
from sqlalchemy.dialects.postgresql import insert as pg_insert
```

For `RETURNING` with `on_conflict_do_nothing`, use:
```python
stmt = pg_insert(TagGroup).values(
    id=uuid4(),
    workspace_id=target_workspace_id,
    name=src_group.name,
    color=src_group.color or "#808080",
    order_index=base_group_order + idx,
    created_at=datetime.now(UTC),
).on_conflict_do_nothing(
    constraint="uq_tag_group_workspace_name",
).returning(TagGroup.__table__.c.id)

result = await session.execute(stmt)
new_id = result.scalar_one_or_none()
```

If `new_id is None`, the group already exists — look it up:
```python
existing = await session.exec(
    select(TagGroup).where(
        TagGroup.workspace_id == target_workspace_id,
        TagGroup.name == src_group.name,
    )
)
existing_group = existing.one()
group_id_map[src_group.id] = existing_group.id
```

For the counter bump (raw SQL `text()` matches the existing pattern at tags.py:107 and tags.py:328, which use raw SQL with `RETURNING` for these same counters):
```python
await session.execute(
    text(
        "UPDATE workspace SET next_group_order = next_group_order + :count "
        "WHERE id = :ws_id"
    ),
    {"count": len(result_obj.created_groups), "ws_id": str(target_workspace_id)},
)
```

Important: Tags must be set to `locked=False` regardless of source (existing behaviour preserved — see current line 749).

**Testing:**

Rewrite the existing `TestImportTagsFromWorkspace` tests (7 tests) to work with `ImportResult` return type instead of `list[Tag]`.

Tests must verify:
- tag-deletion-guards-413.AC4.1: Import from source with 2 groups + 3 tags → `result.created_groups` has 2, `result.created_tags` has 3, all exist in target DB
- tag-deletion-guards-413.AC4.2: Import same source again → `result.created_tags == []`, `result.skipped_tags == 3`, `result.created_groups == []`, `result.skipped_groups == 2`
- tag-deletion-guards-413.AC4.3: Target has 1 tag with same name as source → that tag skipped, others created, counts correct
- tag-deletion-guards-413.AC4.3a: Target has group with same name as source group → source tags remapped to existing target group ID
- tag-deletion-guards-413.AC4.4: `ImportResult` fields have correct counts in all cases
- tag-deletion-guards-413.AC4.6: Atomicity is guaranteed by the single `get_session()` block — if any statement within the block raises, the entire transaction rolls back (see `engine.py:324`). Test approach: create a source workspace with groups and tags where one tag has an invalid color value (violates `ck_tag_color_hex` CHECK constraint). Import should raise `IntegrityError` from the invalid tag insert. Verify the target workspace has zero new groups and zero new tags — proving the entire transaction rolled back, not just the failing insert. If groups were created but tags weren't, atomicity is broken.
- tag-deletion-guards-413.AC4.7: Run two concurrent imports (asyncio.gather) to same target → no `IntegrityError`, combined result is correct

Existing test helpers (`_make_course_week_activity`, `create_user`, `grant_permission`) remain unchanged.

**Verification:**
Run: `uv run grimoire test run tests/integration/test_tag_crud.py::TestImportTagsFromWorkspace`
Expected: All tests pass

**Commit:** `feat(db): rewrite import_tags_from_workspace as atomic idempotent operation (#413)`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Update tag_import.py caller for ImportResult

**Verifies:** tag-deletion-guards-413.AC4.5

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/tag_import.py:108-130` (`_import_from_workspace`)

**Implementation:**

The current caller at line 108-130 uses `imported` as `list[Tag]`:
```python
imported = await import_tags_from_workspace(...)
if imported:
    ui.notify(f"Imported {len(imported)} tag(s)", type="positive")
else:
    ui.notify("No new tags to import", type="info")
```

Update to use `ImportResult`:
```python
result = await import_tags_from_workspace(
    source_workspace_id=UUID(ws_select.value),
    target_workspace_id=state.workspace_id,
    user_id=UUID(state.user_id),
    crdt_doc=state.crdt_doc,
)

# Notify BEFORE render_tag_list() — that call clears content_area
# which destroys dialog elements via weakref.finalize
if result.created_tags or result.created_groups:
    parts: list[str] = []
    if result.created_tags:
        parts.append(f"{len(result.created_tags)} tag{'s' if len(result.created_tags) != 1 else ''}")
    if result.created_groups:
        parts.append(f"{len(result.created_groups)} group{'s' if len(result.created_groups) != 1 else ''}")
    msg = f"Imported {', '.join(parts)}"
    if result.skipped_tags or result.skipped_groups:
        skipped_parts: list[str] = []
        if result.skipped_tags:
            skipped_parts.append(f"{result.skipped_tags} tag{'s' if result.skipped_tags != 1 else ''}")
        if result.skipped_groups:
            skipped_parts.append(f"{result.skipped_groups} group{'s' if result.skipped_groups != 1 else ''}")
        msg += f" ({', '.join(skipped_parts)} already existed)"
    ui.notify(msg, type="positive")
else:
    ui.notify("No new tags to import", type="info")
```

Update the import statement to include `ImportResult` if needed (or just use the function's return type).

**Testing:**

Tests must verify:
- tag-deletion-guards-413.AC4.5: UI notification text includes created and skipped counts with correct pluralisation

This is best tested as E2E or via the existing integration test that exercises the UI import flow. The notification format is a UI concern — verify manually or via E2E.

**Verification:**
Run: `uv run grimoire test all`
Expected: All tests pass

**Commit:** `feat(ui): show created/skipped counts in import notification (#413)`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->
