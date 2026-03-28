# Annotation Deferred Load — Phase 1: Unified Context Resolver

**Goal:** Replace 5 separate DB functions (each opening their own session) with a single `resolve_annotation_context()` that resolves all annotation page data in one session with JOINed queries.

**Architecture:** New `AnnotationContext` dataclass composes `PlacementContext` (existing) with permission, privileged user IDs, tags, tag groups, and CRDT state. A single function in `db/workspaces.py` resolves everything in one session. CRDT functions gain optional kwargs to accept pre-fetched data.

**Tech Stack:** SQLAlchemy async ORM (`select().join()`), SQLModel, pytest-asyncio integration tests.

**Scope:** Phase 1 of 4 from original design.

**Codebase verified:** 2026-03-25

---

## Acceptance Criteria Coverage

This phase implements and tests:

### annotation-deferred-load-377.AC2: Unified DB context resolution
- **annotation-deferred-load-377.AC2.1:** `resolve_annotation_context()` executes in a single DB session
- **annotation-deferred-load-377.AC2.2:** Workspace row is fetched exactly once per page load (verified by query count instrumentation or mock)
- **annotation-deferred-load-377.AC2.3:** Activity -> Week -> Course hierarchy is resolved via JOIN, not sequential selects
- **annotation-deferred-load-377.AC2.4:** Function returns correct results for all workspace states: activity-placed, course-placed, standalone (no parent), template
- **annotation-deferred-load-377.AC2.5:** CRDT registry accepts pre-fetched workspace on cold-cache path (no redundant fetch for crdt_state on first load; warm-cache path already skips the fetch)

---

## Reference Files

The task-implementor should read these files for context:

- **Testing patterns:** `docs/testing.md`, `CLAUDE.md` (lines 47-102), `tests/conftest.py` (db_session fixture), `tests/integration/test_workspace_crud.py` (CRUD test pattern)
- **Implementation guidance:** `.ed3d/implementation-plan-guidance.md`
- **Existing resolver pattern:** `src/promptgrimoire/db/workspaces.py:223-263` (`get_workspace_export_metadata` — single-session with JOIN and private helpers)
- **Permission resolution:** `src/promptgrimoire/db/acl.py:302-348` (`_resolve_permission_with_session` — takes session param)
- **CRDT consistency:** `src/promptgrimoire/crdt/annotation_doc.py:893-934` (`_ensure_crdt_tag_consistency`)
- **CRDT registry:** `src/promptgrimoire/crdt/annotation_doc.py:937-1001` (`AnnotationDocumentRegistry`)

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->

<!-- START_TASK_1 -->
### Task 1: Create AnnotationContext dataclass

**Verifies:** annotation-deferred-load-377.AC2.1 (structural prerequisite)

**Files:**
- Modify: `src/promptgrimoire/db/workspaces.py` (add after `PlacementContext` at line ~211)

**Implementation:**

Add a frozen dataclass that composes all data needed for annotation page load. This embeds `PlacementContext` rather than extending it to avoid polluting the existing API used by export and other callers.

```python
from promptgrimoire.db.models import Tag, TagGroup, Workspace

@dataclass(frozen=True)
class AnnotationContext:
    """All data needed for annotation page load, resolved in a single session.

    Replaces 5+ separate DB function calls that each opened their own session:
    - get_workspace()
    - check_workspace_access() -> resolve_permission()
    - get_placement_context()
    - get_privileged_user_ids_for_workspace()
    - list_tags_for_workspace() + list_tag_groups_for_workspace()
    """

    workspace: Workspace
    permission: str | None
    """Effective permission for the requesting user. None = no access."""
    placement: PlacementContext
    privileged_user_ids: frozenset[str]
    """String-form User.id values for staff/admins — matches CRDT annotation author format."""
    tags: list[Tag]
    tag_groups: list[TagGroup]
```

Note: `crdt_state` is already on `workspace.crdt_state` — no separate field needed.

**Verification:**
Run: `uv run python -c "from promptgrimoire.db.workspaces import AnnotationContext; print('OK')"`
Expected: `OK` (no import errors)

**Commit:** `feat(db): add AnnotationContext dataclass for batched page load`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Implement resolve_annotation_context()

**Verifies:** annotation-deferred-load-377.AC2.1, annotation-deferred-load-377.AC2.2, annotation-deferred-load-377.AC2.3, annotation-deferred-load-377.AC2.4

**Files:**
- Modify: `src/promptgrimoire/db/workspaces.py` (add function after `AnnotationContext`)
- Read (do not modify): `src/promptgrimoire/db/acl.py` (import `_resolve_permission_with_session`)
- Read (do not modify): `src/promptgrimoire/db/models.py` (model column names)

**Implementation:**

Create `resolve_annotation_context()` in `db/workspaces.py`. A single async function that opens one session and resolves everything:

1. **Workspace fetch:** `session.get(Workspace, workspace_id)` — single PK lookup, returns workspace with `crdt_state`.

2. **Hierarchy resolution via JOIN:** Replace the 3 sequential `session.get()` calls in `_resolve_activity_placement()` with an ORM `select().join()` query. The query handles all 3 placement states:
   - Activity-placed: `workspace.activity_id` -> activity -> week -> course (via week)
   - Course-placed: `workspace.course_id` -> course (no activity/week)
   - Standalone: both NULL, no joins resolve

   Use `select()` with LEFT JOINs on Activity, Week, and Course (two paths). The existing `_resolve_activity_placement()` and `_resolve_course_placement()` private helpers show exactly which columns are accessed and how `resolve_tristate()` is applied. Match their output exactly.

   **Template detection:** Standalone workspaces need a reverse lookup (`SELECT activity WHERE template_workspace_id = :workspace_id`). Activity-placed workspaces check `activity.template_workspace_id == workspace_id`. Both are handled in the existing `get_placement_context()` (line 287-296).

3. **Permission resolution:** The design says to reuse `_resolve_permission_with_session()`, but **critical caveat:** that function internally calls `_derive_enrollment_permission()` (acl.py:256) which does `session.get(Workspace, workspace_id)` at line 266 AND walks the hierarchy again via `_resolve_workspace_course()`. This violates AC2.2 (workspace fetched once).

   **The implementor must choose one approach:**
   - **(a) Inline permission resolution:** Using data already resolved by the JOIN (workspace, course_id, enrollment), implement the two-step hybrid resolution directly inside `resolve_annotation_context()`. The explicit ACL lookup is a simple `select(ACLEntry).where(workspace_id, user_id)`. The enrollment-derived permission needs the course_id (already resolved) and enrollment row.
   - **(b) Create `_resolve_permission_with_context(session, workspace, course_id, user_id)`:** A new helper that accepts pre-fetched data instead of re-fetching. This keeps the permission logic separate but avoids the double-fetch.

   Either approach achieves AC2.2. The existing `_resolve_permission_with_session` should NOT be called directly — it will re-fetch workspace and re-walk hierarchy.

   The caller (`check_workspace_access` in `auth/__init__.py`) also does admin bypass — the resolver should handle this by accepting an `is_admin: bool` parameter and short-circuiting to `"owner"` permission when True.

4. **Privileged user IDs:** Replicate the logic from `get_privileged_user_ids_for_workspace()` (acl.py:665-711) within the same session. The `course_id` is already resolved from step 2. Query `CourseEnrollment` for staff roles + `User` for admins. Import `get_staff_roles()` from `db/roles.py` (cached, no DB hit).

5. **Tags and tag groups:** Two `select()` queries in the same session — `Tag` and `TagGroup` filtered by `workspace_id`, ordered by `order_index`. Match the existing `list_tags_for_workspace()` and `list_tag_groups_for_workspace()` return types.

**Function signature:**

```python
async def resolve_annotation_context(
    workspace_id: UUID,
    user_id: UUID,
    *,
    is_admin: bool = False,
) -> AnnotationContext | None:
    """Resolve all data needed for annotation page load in a single session.

    Returns None if workspace does not exist.
    """
```

**Key implementation notes:**
- Import `_resolve_permission_with_session` from `db.acl`. This creates a new cross-module import. Verify no circular import: `db/acl.py` does not import from `db/workspaces.py` (confirmed by codebase investigation).
- Use `resolve_tristate()` (already in workspaces.py) for Activity override -> Course default resolution.
- The `PlacementContext` construction must exactly match the existing `_resolve_activity_placement()` and `_resolve_course_placement()` outputs for field parity.
- Apply `# type: ignore[arg-type]` on `.join()` calls per codebase convention. The project uses `ty` as the type checker, but `# type: ignore` directives are accepted and used throughout the codebase (see `db/courses.py:407`, `db/tags.py:307` for examples). Always include an explanation after `--` (e.g., `# type: ignore[arg-type]  -- SQLModel Column expression valid at runtime`).

**Verification:**
Run: `uv run python -c "from promptgrimoire.db.workspaces import resolve_annotation_context; print('OK')"`
Expected: `OK` (no import errors, no circular imports)

**Commit:** `feat(db): implement resolve_annotation_context with JOINed hierarchy`

<!-- END_TASK_2 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->

<!-- START_TASK_3 -->
### Task 3: Add workspace parameter to CRDT registry

**Verifies:** annotation-deferred-load-377.AC2.5

**Files:**
- Modify: `src/promptgrimoire/crdt/annotation_doc.py` (modify `get_or_create_for_workspace` at line 957)

**Implementation:**

Add an optional `workspace` parameter to `get_or_create_for_workspace()` so callers with pre-fetched workspace data skip the redundant `get_workspace()` call on cold cache.

Current signature (line 957):
```python
async def get_or_create_for_workspace(
    self, workspace_id: UUID
) -> AnnotationDocument:
```

New signature:
```python
async def get_or_create_for_workspace(
    self, workspace_id: UUID, *, workspace: Workspace | None = None
) -> AnnotationDocument:
```

When `workspace` is provided AND has `crdt_state`, skip the `get_workspace()` call (line 986). The warm-cache path (line 973-977) is unchanged — it never fetches workspace.

**Key constraint:** Existing callers pass only `workspace_id` — they must continue to work unchanged. The `workspace` kwarg is optional with default `None`, falling back to the existing `get_workspace()` call.

**Verification:**
Run: `uv run grimoire test changed`
Expected: Existing tests pass (no callers affected)

**Commit:** `feat(crdt): accept pre-fetched workspace in registry`

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Add optional tags/tag_groups to _ensure_crdt_tag_consistency

**Verifies:** annotation-deferred-load-377.AC2.5

**Files:**
- Modify: `src/promptgrimoire/crdt/annotation_doc.py` (modify `_ensure_crdt_tag_consistency` at line 893)

**Implementation:**

Add optional `tags` and `tag_groups` kwargs so callers with pre-fetched data skip the internal DB fetch.

Current signature (line 893):
```python
async def _ensure_crdt_tag_consistency(
    doc: AnnotationDocument,
    workspace_id: UUID,
) -> None:
```

New signature:
```python
async def _ensure_crdt_tag_consistency(
    doc: AnnotationDocument,
    workspace_id: UUID,
    *,
    tags: list[Tag] | None = None,
    tag_groups: list[TagGroup] | None = None,
) -> None:
```

When `tags` is provided, skip `list_tags_for_workspace()` call (line 909). When `tag_groups` is provided, skip `list_tag_groups_for_workspace()` call (line 910). Either can be provided independently.

**Key constraint:** Existing callers (line 976, 994) pass only `(doc, workspace_id)` — they must continue to work unchanged.

**Verification:**
Run: `uv run grimoire test changed`
Expected: Existing tests pass

**Commit:** `feat(crdt): accept pre-fetched tags in consistency check`

<!-- END_TASK_4 -->

<!-- END_SUBCOMPONENT_B -->

<!-- START_SUBCOMPONENT_C (tasks 5-6) -->

<!-- START_TASK_5 -->
### Task 5: Integration tests for resolve_annotation_context

**Verifies:** annotation-deferred-load-377.AC2.1, annotation-deferred-load-377.AC2.2, annotation-deferred-load-377.AC2.3, annotation-deferred-load-377.AC2.4

**Files:**
- Create: `tests/integration/test_annotation_context.py`
- Read (reference pattern): `tests/integration/test_workspace_crud.py`

**Testing:**

Tests must verify each AC listed above. Follow the integration test pattern from `test_workspace_crud.py`: one class per concern, `@pytest.mark.asyncio` on each test, import functions inside test body, UUID-based data isolation.

Each test creates its own workspace + hierarchy data (no shared fixtures):

- **annotation-deferred-load-377.AC2.4 (activity-placed):** Create course -> week -> activity -> workspace chain. Call `resolve_annotation_context()`. Assert: `placement.placement_type == "activity"`, correct `course_code`, `week_number`, `activity_title`, all `resolve_tristate` fields match what `_resolve_activity_placement` would produce.

- **annotation-deferred-load-377.AC2.4 (course-placed):** Create course -> workspace (direct `course_id`, no activity). Assert: `placement.placement_type == "course"`, correct course fields, no activity/week fields.

- **annotation-deferred-load-377.AC2.4 (standalone):** Create workspace with no `activity_id` or `course_id`. Assert: `placement.placement_type == "loose"`, all hierarchy fields None.

- **annotation-deferred-load-377.AC2.4 (template, activity-placed):** Create activity with `template_workspace_id == workspace_id`. Assert: `placement.is_template == True`.

- **annotation-deferred-load-377.AC2.4 (template, standalone):** Create a standalone workspace (no `activity_id`, no `course_id`). Create an activity with `template_workspace_id` pointing to this workspace. Call `resolve_annotation_context()`. Assert: `placement.is_template == True`. This tests the reverse lookup path (`SELECT activity WHERE template_workspace_id = :workspace_id`) which is different from the activity-placed template detection.

- **annotation-deferred-load-377.AC2.1 (single session):** Verify the function completes without error (structural — uses one `async with get_session()` by design).

- **annotation-deferred-load-377.AC2.3 (permission resolution):** Create workspace + ACL entry for test user. Assert `context.permission` matches expected permission string. Test admin bypass: `is_admin=True` returns `"owner"` regardless of ACL.

- **annotation-deferred-load-377.AC2.3 (privileged users):** Create course with staff enrollment. Assert `context.privileged_user_ids` contains the staff user ID as a string.

- **annotation-deferred-load-377.AC2.3 (tags):** Create workspace with tags and tag groups. Assert `context.tags` and `context.tag_groups` lists match DB records in order.

- **Nonexistent workspace:** Call with random UUID. Assert returns `None`.

All tests must have the skip guard:
```python
pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)
```

**Verification:**
Run: `uv run grimoire test run tests/integration/test_annotation_context.py`
Expected: All tests pass

**Commit:** `test(db): integration tests for resolve_annotation_context`

<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Integration tests for CRDT pre-fetch kwargs

**Verifies:** annotation-deferred-load-377.AC2.5

**Files:**
- Create: `tests/integration/test_crdt_prefetch.py`
- Read (reference): `src/promptgrimoire/crdt/annotation_doc.py:893-1001`

**Testing:**

Tests verify that CRDT functions accept and use pre-fetched data:

- **get_or_create_for_workspace with workspace kwarg:** Create workspace with CRDT state. Call `registry.get_or_create_for_workspace(workspace_id, workspace=workspace)`. Assert document is hydrated from provided workspace's `crdt_state` without a separate `get_workspace()` call. (Verify by checking the returned document contains the expected CRDT state.)

- **_ensure_crdt_tag_consistency with pre-fetched tags:** Create workspace with tags in DB. Call `_ensure_crdt_tag_consistency(doc, workspace_id, tags=db_tags, tag_groups=db_groups)` with pre-fetched lists. Assert CRDT tag maps are hydrated correctly (same result as calling without kwargs).

- **Backward compatibility:** Call both functions WITHOUT the new kwargs (existing call pattern). Assert they still work correctly (existing tag-fetch and workspace-fetch paths execute).

**Verification:**
Run: `uv run grimoire test run tests/integration/test_crdt_prefetch.py`
Expected: All tests pass

**Commit:** `test(crdt): integration tests for pre-fetched data kwargs`

<!-- END_TASK_6 -->

<!-- END_SUBCOMPONENT_C -->
