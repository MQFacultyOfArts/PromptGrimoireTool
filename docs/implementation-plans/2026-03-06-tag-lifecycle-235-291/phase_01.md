# Tag Lifecycle Refactor — Phase 1: CRDT Schema Extension

**Goal:** Add `tags` and `tag_groups` Maps to `AnnotationDoc` with read/write methods.

**Architecture:** Extend `AnnotationDocument` with two new top-level pycrdt Maps (`tags`, `tag_groups`) using the same dict-in-Map storage pattern as highlights. Preserve existing `tag_order` Map unchanged for backward compatibility. Use the existing `_origin_var` ContextVar pattern (no `doc.transaction()`).

**Tech Stack:** pycrdt (Map, Array), Python dataclasses

**Scope:** 8 phases from original design (phase 1 of 8)

**Codebase verified:** 2026-03-06

---

## Acceptance Criteria Coverage

This phase implements and tests (CRDT side only — DB writes are Phase 2):

### tag-lifecycle-235-291.AC1: Tag metadata in DB and CRDT
- **tag-lifecycle-235-291.AC1.1 Success:** Creating a tag writes metadata to both DB `tag` table and CRDT `tags` Map with matching fields *(CRDT write method only — DB integration is Phase 2)*
- **tag-lifecycle-235-291.AC1.2 Success:** Updating a tag's name/colour/description in the management dialog updates both DB and CRDT *(CRDT update method only)*
- **tag-lifecycle-235-291.AC1.3 Success:** Deleting a tag removes it from both DB and CRDT, including its highlights list *(CRDT delete method only)*
- **tag-lifecycle-235-291.AC1.4 Success:** Creating/updating/deleting a tag group writes to both DB and CRDT *(CRDT methods only)*
- **tag-lifecycle-235-291.AC1.5 Edge:** On workspace load, if CRDT maps are empty but DB has tags, CRDT is hydrated from DB *(method signature only — hydration logic is Phase 3)*
- **tag-lifecycle-235-291.AC1.6 Edge:** On workspace load, if DB has a tag the CRDT doesn't, CRDT is reconciled (tag added) *(method signature only — reconciliation logic is Phase 3)*

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Add `tags` and `tag_groups` Maps to AnnotationDocument

**Verifies:** tag-lifecycle-235-291.AC1.1 (CRDT structure), tag-lifecycle-235-291.AC1.4 (CRDT structure)

**Files:**
- Modify: `src/promptgrimoire/crdt/annotation_doc.py:52-98` (AnnotationDocument.__init__ and properties)

**Implementation:**

Add two new Maps in `__init__` after the existing Map declarations (after line 65):

```python
self.doc["tags"] = Map()        # {tag_uuid_str: {name, colour, group_id, description, order_index, highlights}}
self.doc["tag_groups"] = Map()  # {group_uuid_str: {name, colour, order_index}}
```

Add property accessors following the existing pattern (after `tag_order` property, line 98):

```python
@property
def tags(self) -> Map:
    """Get the tags Map."""
    return self.doc["tags"]

@property
def tag_groups(self) -> Map:
    """Get the tag_groups Map."""
    return self.doc["tag_groups"]
```

**Testing:**

Tests must verify:
- tag-lifecycle-235-291.AC1.1: A freshly created `AnnotationDocument` has empty `tags` and `tag_groups` Maps accessible via properties
- tag-lifecycle-235-291.AC1.4: The Map properties return pycrdt Map instances

Test file: `tests/unit/test_annotation_doc.py` (add to existing file)

Follow existing pattern from `TestTagOrder` class. Tests are pure unit tests — no DB, no mocks, just direct `AnnotationDocument("test-doc")` instantiation.

**Verification:**
Run: `uv run pytest tests/unit/test_annotation_doc.py -v`
Expected: All existing tests pass + new tests pass

**Commit:** `feat: add tags and tag_groups Maps to AnnotationDocument`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Tag CRUD methods on AnnotationDocument

**Verifies:** tag-lifecycle-235-291.AC1.1, tag-lifecycle-235-291.AC1.2, tag-lifecycle-235-291.AC1.3

**Files:**
- Modify: `src/promptgrimoire/crdt/annotation_doc.py` (add methods after tag order operations section, ~line 458)
- Test: `tests/unit/test_annotation_doc.py` (new test class)

**Implementation:**

Add these methods to `AnnotationDocument`, following the highlight CRUD pattern (dict-in-Map with `_origin_var`):

**`set_tag(tag_id, name, colour, order_index, *, group_id=None, description=None, highlights=None, origin_client_id=None)`**
- Writes a complete tag dict to `self.tags[str(tag_id)]`
- Dict keys: `name`, `colour`, `group_id` (str or None), `description` (str or None), `order_index` (int), `highlights` (list[str], defaults to `[]`)
- Uses `_origin_var` pattern for echo prevention

**`get_tag(tag_id) -> dict[str, Any] | None`**
- Returns `self.tags.get(str(tag_id))` — None if missing

**`delete_tag(tag_id, origin_client_id=None)`**
- Removes `str(tag_id)` from `self.tags` if present
- Uses `_origin_var` pattern

**`list_tags() -> dict[str, dict[str, Any]]`**
- Returns `{tag_id: tag_data for tag_id, tag_data in self.tags.items()}`
- Returns empty dict if no tags

**Testing:**

Tests must verify each AC case:
- tag-lifecycle-235-291.AC1.1: `set_tag()` stores all fields correctly, `get_tag()` retrieves them with matching values
- tag-lifecycle-235-291.AC1.2: Calling `set_tag()` again with same ID and different name/colour/description overwrites correctly
- tag-lifecycle-235-291.AC1.3: `delete_tag()` removes the tag, subsequent `get_tag()` returns None
- Edge: `get_tag()` on non-existent ID returns None
- Edge: `delete_tag()` on non-existent ID does not raise
- Edge: `list_tags()` on empty doc returns empty dict
- Edge: `set_tag()` with `highlights` list preserves ordering

Test pattern: Create `AnnotationDocument("test")`, call methods, assert results. No DB, no mocks.

Verify CRDT sync: Create two docs, write a tag to doc1, sync state to doc2 via `get_full_state()` / `apply_update()`, verify doc2 has the tag. This follows the existing two-doc sync pattern from `test_crdt_sync.py`.

**Verification:**
Run: `uv run pytest tests/unit/test_annotation_doc.py -v -k "tag"`
Expected: All tests pass

**Commit:** `feat: add tag CRUD methods to AnnotationDocument`

<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: Tag group CRUD methods on AnnotationDocument

**Verifies:** tag-lifecycle-235-291.AC1.4

**Files:**
- Modify: `src/promptgrimoire/crdt/annotation_doc.py` (add methods after tag CRUD section)
- Test: `tests/unit/test_annotation_doc.py` (new test class)

**Implementation:**

Add these methods following the same pattern as tag CRUD:

**`set_tag_group(group_id, name, order_index, *, colour=None, origin_client_id=None)`**
- Writes `{name, colour, order_index}` to `self.tag_groups[str(group_id)]`

**`get_tag_group(group_id) -> dict[str, Any] | None`**
- Returns `self.tag_groups.get(str(group_id))`

**`delete_tag_group(group_id, origin_client_id=None)`**
- Removes from `self.tag_groups`

**`list_tag_groups() -> dict[str, dict[str, Any]]`**
- Returns all tag groups as `{group_id: group_data}`

**Testing:**

Tests must verify:
- tag-lifecycle-235-291.AC1.4: Create, update (overwrite), delete group — all operations work correctly
- Edge: Operations on non-existent groups don't raise
- CRDT sync: Group data syncs between two docs via get_full_state/apply_update

**Verification:**
Run: `uv run pytest tests/unit/test_annotation_doc.py -v -k "tag_group"`
Expected: All tests pass

**Commit:** `feat: add tag group CRUD methods to AnnotationDocument`

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Hydration helper method (signature + basic logic)

**Verifies:** tag-lifecycle-235-291.AC1.5, tag-lifecycle-235-291.AC1.6 (method signatures only — full integration is Phase 3)

**Files:**
- Modify: `src/promptgrimoire/crdt/annotation_doc.py` (add method)
- Test: `tests/unit/test_annotation_doc.py` (new test class)

**Implementation:**

Add a method that accepts tag and group data from a DB query result and populates CRDT Maps:

**`hydrate_tags_from_db(tags: list[dict[str, Any]], groups: list[dict[str, Any]], origin_client_id: str | None = None) -> None`**
- For each group dict: call `self.set_tag_group(group["id"], group["name"], group["order_index"], colour=group.get("colour"))`
- For each tag dict: call `self.set_tag(tag["id"], tag["name"], tag["colour"], tag["order_index"], group_id=tag.get("group_id"), description=tag.get("description"), highlights=tag.get("highlights", []))`
- Uses `_origin_var` once (wraps all calls in one origin block)

This method is a pure CRDT operation — it doesn't query the DB. Phase 3 will call it with data fetched from DB.

**Semantics:** `hydrate_tags_from_db()` performs a **full replacement** — it calls `set_tag()` / `set_tag_group()` for every entry in the input lists. If the CRDT already has entries, they are overwritten with the DB values. This is intentional: DB is authoritative, and the consistency check in Phase 3 calls this method to force CRDT back into sync with DB. The method docstring must explicitly state: "Full replacement — DB values overwrite existing CRDT entries. DB is authoritative."

**Testing:**

Tests must verify:
- tag-lifecycle-235-291.AC1.5: Call `hydrate_tags_from_db()` on an empty doc with tag/group data — verify all entries are populated with correct values
- tag-lifecycle-235-291.AC1.6: Call `hydrate_tags_from_db()` on a doc that already has a tag with a stale name — verify the tag's name is overwritten with the DB value (DB wins)
- Edge: Empty lists produce no errors and do not remove existing entries
- Edge: Tags with `group_id` referencing a group in the groups list resolve correctly

**Verification:**
Run: `uv run pytest tests/unit/test_annotation_doc.py -v -k "hydrate"`
Expected: All tests pass

**Commit:** `feat: add hydrate_tags_from_db method to AnnotationDocument`

<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_TASK_5 -->
### Task 5: Verify backward compatibility — existing TestTagOrder passes unchanged

**Verifies:** None (regression verification)

**Files:**
- No modifications — verification only

**Verification:**
Run: `uv run pytest tests/unit/test_annotation_doc.py::TestTagOrder -v`
Expected: All existing `TestTagOrder` tests pass without modification

Run: `uv run grimoire test changed`
Expected: All tests pass

**Commit:** No commit needed — verification only

<!-- END_TASK_5 -->
