# Workspace Navigator Implementation Plan — Phase 2: Navigator Data Loader

**Goal:** A single entry point that returns all data the navigator page needs — four sections in one UNION ALL query with keyset cursor pagination.

**Architecture:** `db/navigator.py` provides `load_navigator_page()` which executes a single UNION ALL query across four sections (my_work, unstarted, shared_with_me, shared_in_unit). Each row carries a section tag, sort key, and all context needed for rendering. Keyset cursor on `(section_priority, sort_key, id)` provides efficient pagination across the unified result set. Anonymisation is applied in Python after the query returns.

**Tech Stack:** SQLAlchemy `text()` for the UNION ALL query, asyncpg, Python post-processing for anonymisation.

**Scope:** 7 phases from original design (phase 2 of 7)

**Codebase verified:** 2026-02-25

**Human review gate:** The UNION ALL SQL in Task 2 is the most complex query in this feature. It must be reviewed by a human before building the UI on top of it. Integration tests in this phase verify the SQL against PostgreSQL in isolation — no UI, no page layer, just the query and its results.

---

## Acceptance Criteria Coverage

This phase implements and tests:

### workspace-navigator-196.AC1: Navigator page renders all sections
- **workspace-navigator-196.AC1.1 Success:** Student sees "My Work" with all owned workspaces grouped by unit > week > activity
- **workspace-navigator-196.AC1.2 Success:** Student sees "Unstarted Work" with all published activities they haven't started
- **workspace-navigator-196.AC1.3 Success:** Student sees "Shared With Me" with workspaces shared via explicit ACL (editor/viewer)
- **workspace-navigator-196.AC1.4 Success:** Student sees "Shared in [Unit]" per enrolled unit, with peer workspaces grouped by anonymised student
- **workspace-navigator-196.AC1.5 Success:** Instructor sees "Shared in [Unit]" with all student workspaces grouped by real student name
- **workspace-navigator-196.AC1.6 Success:** Loose workspaces (no activity) appear under "Unsorted" within each student grouping
- **workspace-navigator-196.AC1.7 Edge:** Empty sections (no shared workspaces, no unstarted work) are hidden, not rendered empty
- **workspace-navigator-196.AC1.8 Edge:** Student enrolled in multiple units sees separate "Shared in [Unit]" section per unit

### workspace-navigator-196.AC5: Cursor pagination (data layer)
- **workspace-navigator-196.AC5.1 Success:** Initial load shows first 50 rows across all sections
- **workspace-navigator-196.AC5.2 Success:** "Load more" fetches next 50 rows, appended into correct sections
- **workspace-navigator-196.AC5.4 Edge:** Total rows fewer than 50 — loads all in one page, no "Load more"

---

## Codebase Context for Executor

**Key files to read before implementing:**
- `src/promptgrimoire/db/models.py` — All 12 SQLModel classes. Pay attention to: Workspace (line 312, fields: activity_id, course_id, title, shared_with_class, updated_at), Activity (line 251, fields: week_id, template_workspace_id, allow_sharing tristate), Week (line 218, fields: course_id, week_number, is_published), Course (line 121, fields: code, name, default_allow_sharing, default_anonymous_sharing), CourseEnrollment (line 182, fields: course_id, user_id, role), ACLEntry (line 464, fields: workspace_id, user_id, permission), Permission (line 27, natural PK on name, level for comparison).
- `src/promptgrimoire/db/acl.py` — Existing query patterns: `list_accessible_workspaces` (line 114), `list_peer_workspaces_with_owners` (line 552), `resolve_permission` (line 334), `_derive_enrollment_permission` (line 223). These show JOIN patterns and permission logic.
- `src/promptgrimoire/auth/anonymise.py` — `anonymise_author()` (line 36). Deterministic SHA-256 based pseudonym generation. Takes 6 params including viewer context.
- `src/promptgrimoire/pages/courses.py` — `_build_peer_map` (line 76). Shows the pattern: fetch raw data → apply `anonymise_author()` per row → build display structures.
- `src/promptgrimoire/db/workspaces.py` — `clone_workspace_from_activity` (line 590). Does NOT set title on cloned workspace.
- `docs/database.md` — Full schema reference.
- `docs/testing.md`, `CLAUDE.md` — Testing conventions (integration tests need skip guard, `db_session` fixture, class-based grouping).

**Critical patterns:**
- `Workspace.title` is `str | None`, defaults to `None`. UI pattern: `ws.title or "Untitled Workspace"`.
- `shared_with_class: bool` on Workspace gates peer visibility.
- Tristate fields on Activity (allow_sharing, anonymous_sharing) inherit from Course when `None`. Use `resolve_tristate(activity.field, course.default_field)` pattern from courses.py.
- Anonymisation is always done in Python, never in SQL. The data loader returns raw display names; the caller applies anonymisation.
- `get_session()` context manager from `db/engine.py` provides AsyncSession.
- Existing queries use `session.execute(text(...), params)` for raw SQL (see tags.py:72).

---

## Tasks

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: NavigatorRow dataclass and load_navigator_page signature

**Files:**
- Create: `src/promptgrimoire/db/navigator.py`

**Implementation:**

Create the module with the public API surface. Define a `NavigatorRow` dataclass (or NamedTuple) representing one row from the unified query:

```python
@dataclasses.dataclass(frozen=True, slots=True)
class NavigatorRow:
    section: str               # "my_work" | "unstarted" | "shared_with_me" | "shared_in_unit"
    section_priority: int      # 1=my_work, 2=unstarted, 3=shared_with_me, 4=shared_in_unit
    workspace_id: UUID | None  # None for unstarted activities
    activity_id: UUID | None
    activity_title: str | None
    week_title: str | None
    week_number: int | None
    course_id: UUID | None
    course_code: str | None
    course_name: str | None
    title: str | None          # workspace title (None → "Untitled Workspace" in UI)
    updated_at: datetime | None
    owner_user_id: UUID | None
    owner_display_name: str | None
    permission: str | None     # "owner", "editor", "viewer", "peer"
    shared_with_class: bool
    sort_key: datetime         # for cursor pagination
    row_id: UUID               # tiebreaker for cursor (workspace_id or activity_id)
```

Define `NavigatorCursor` as a NamedTuple for the keyset cursor:

```python
class NavigatorCursor(NamedTuple):
    section_priority: int
    sort_key: datetime
    row_id: UUID
```

Define the async function signature:

```python
async def load_navigator_page(
    session: AsyncSession,
    user_id: UUID,
    is_privileged: bool,
    enrolled_course_ids: Sequence[UUID],
    cursor: NavigatorCursor | None = None,
    limit: int = 50,
) -> tuple[list[NavigatorRow], NavigatorCursor | None]:
```

Returns `(rows, next_cursor)` where `next_cursor` is `None` when no more rows exist.

The function needs `enrolled_course_ids` because enrollment lookup is already done by auth middleware — no need to re-query it.

**Verification:**
Run: `uvx ty check`
Expected: Type checks pass.

**Commit:** `feat: add NavigatorRow dataclass and load_navigator_page signature`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: UNION ALL query implementation

**Verifies:** workspace-navigator-196.AC1.1, workspace-navigator-196.AC1.2, workspace-navigator-196.AC1.3, workspace-navigator-196.AC1.4, workspace-navigator-196.AC1.5, workspace-navigator-196.AC1.6, workspace-navigator-196.AC5.1, workspace-navigator-196.AC5.4

**Files:**
- Modify: `src/promptgrimoire/db/navigator.py`
- Test: `tests/integration/test_navigator_loader.py` (integration — requires PostgreSQL)

**Implementation:**

Implement the UNION ALL query inside `load_navigator_page`. The query has four SELECT branches, each producing the same column set (NULL-padded where fields don't apply):

**Section 1 — my_work (priority=1):** Workspaces where user is owner.
```sql
SELECT 1 AS section_priority, 'my_work' AS section,
       w.id AS workspace_id, a.id AS activity_id, a.title AS activity_title,
       wk.title AS week_title, wk.week_number, c.id AS course_id,
       c.code AS course_code, c.name AS course_name,
       w.title, w.updated_at, acl.user_id AS owner_user_id,
       u.display_name AS owner_display_name, acl.permission,
       w.shared_with_class,
       w.updated_at AS sort_key, w.id AS row_id
FROM workspace w
JOIN acl_entry acl ON acl.workspace_id = w.id AND acl.user_id = :user_id AND acl.permission = 'owner'
JOIN "user" u ON u.id = acl.user_id
LEFT JOIN activity a ON a.id = w.activity_id
LEFT JOIN week wk ON wk.id = a.week_id
LEFT JOIN course c ON c.id = COALESCE(wk.course_id, w.course_id)
WHERE w.id != COALESCE(a.template_workspace_id, '00000000-0000-0000-0000-000000000000')
```

**Section 2 — unstarted (priority=2):** Published activities in enrolled courses where user has no workspace.
```sql
SELECT 2, 'unstarted',
       NULL, a.id, a.title,
       wk.title, wk.week_number, c.id,
       c.code, c.name,
       NULL, NULL, NULL, NULL, NULL, FALSE,
       a.created_at, a.id
FROM activity a
JOIN week wk ON wk.id = a.week_id AND wk.is_published = TRUE
JOIN course c ON c.id = wk.course_id AND c.id = ANY(:enrolled_course_ids)
WHERE NOT EXISTS (
    SELECT 1 FROM workspace w2
    JOIN acl_entry acl2 ON acl2.workspace_id = w2.id AND acl2.user_id = :user_id AND acl2.permission = 'owner'
    WHERE w2.activity_id = a.id
)
```

**Section 3 — shared_with_me (priority=3):** Workspaces shared via explicit ACL where user is editor or viewer (not owner).
```sql
SELECT 3, 'shared_with_me',
       w.id, a.id, a.title,
       wk.title, wk.week_number, c.id,
       c.code, c.name,
       w.title, w.updated_at, owner_acl.user_id, owner_u.display_name, acl.permission,
       w.shared_with_class,
       w.updated_at, w.id
FROM workspace w
JOIN acl_entry acl ON acl.workspace_id = w.id AND acl.user_id = :user_id AND acl.permission IN ('editor', 'viewer')
LEFT JOIN acl_entry owner_acl ON owner_acl.workspace_id = w.id AND owner_acl.permission = 'owner'
LEFT JOIN "user" owner_u ON owner_u.id = owner_acl.user_id
LEFT JOIN activity a ON a.id = w.activity_id
LEFT JOIN week wk ON wk.id = a.week_id
LEFT JOIN course c ON c.id = COALESCE(wk.course_id, w.course_id)
```

**Section 4 — shared_in_unit (priority=4):** Per enrolled unit. Behaviour differs by role:
- **Instructor (is_privileged=True):** All non-template student workspaces in enrolled courses, grouped by student.
- **Student (is_privileged=False):** Only workspaces with `shared_with_class=TRUE` in activities where sharing is enabled, excluding own workspaces.

The `is_privileged` parameter controls which variant runs. Use a conditional branch in Python to build the appropriate SQL text for section 4 before assembling the full UNION ALL.

For instructors, include students with no workspaces as rows with `workspace_id=NULL` (AC1.6 — these render as "no work yet" entries). Use a LEFT JOIN from CourseEnrollment → Workspace to capture zero-workspace students.

**Keyset cursor WHERE clause** (appended when `cursor` is not None):
```sql
WHERE (section_priority, sort_key, row_id) > (:cursor_section, :cursor_sort_key, :cursor_row_id)
```

Wrap the UNION ALL in a CTE, apply cursor filter and LIMIT on the outer query:
```sql
WITH unified AS (
    <section 1 UNION ALL section 2 UNION ALL section 3 UNION ALL section 4>
)
SELECT * FROM unified
WHERE (:no_cursor OR (section_priority, sort_key, row_id) > (:c_section, :c_sort_key, :c_row_id))
ORDER BY section_priority, sort_key DESC, row_id
LIMIT :limit + 1
```

Fetch `limit + 1` rows to detect whether more exist. If `len(rows) > limit`, pop the last row and construct `next_cursor` from the last returned row. Otherwise `next_cursor = None`.

Map result rows to `NavigatorRow` dataclass instances.

**Testing:**

Integration tests require PostgreSQL. Module-level skip guard for `DEV__TEST_DATABASE_URL`. Class-based grouping.

Test setup: create test data via direct model insertion — courses, enrollments, weeks, activities, workspaces, ACL entries, users. Use the `db_session` fixture.

Tests must verify each AC listed above:
- AC1.1: Create user with owned workspaces across 2 courses. Verify my_work rows include all, grouped correctly by course/week/activity context.
- AC1.2: Create published activities where user has no workspace. Verify unstarted rows appear. Create unpublished activity — verify it's excluded.
- AC1.3: Create workspace with editor ACL for user. Verify shared_with_me row appears with correct permission and owner display name.
- AC1.4: Create peer workspaces with `shared_with_class=True`. Call with `is_privileged=False`. Verify shared_in_unit rows appear, excluding user's own. Verify owner_display_name is raw (anonymisation happens in caller).
- AC1.5: Same data, call with `is_privileged=True`. Verify all student workspaces appear (not just shared ones).
- AC1.6: Create student enrolled in course with no workspaces. Call with `is_privileged=True`. Verify a row appears with `workspace_id=None` for that student.
- AC1.7: (UI concern — data loader returns empty sections, UI hides them. Test that empty sections produce zero rows.)
- AC1.8: Enrol user in 2 courses. Verify shared_in_unit rows carry distinct course_id values.
- AC5.1: Insert 60 rows of test data. Load with limit=50. Verify 50 rows returned and next_cursor is not None.
- AC5.4: Insert 30 rows. Load with limit=50. Verify 30 rows returned and next_cursor is None.

**Verification:**
Run: `uv run test-changed`
Expected: All new tests pass.

**Commit:** `feat: implement UNION ALL navigator data loader with cursor pagination`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Post-processing helpers (anonymisation, section grouping)

**Verifies:** workspace-navigator-196.AC1.4, workspace-navigator-196.AC1.7

**Files:**
- Modify: `src/promptgrimoire/db/navigator.py`
- Test: `tests/unit/test_navigator_postprocess.py` (unit — no database)

**Implementation:**

Add helper functions for post-processing the flat row list:

```python
def apply_anonymisation(
    rows: list[NavigatorRow],
    viewing_user_id: UUID,
    viewer_is_privileged: bool,
    course_anonymous_sharing: dict[UUID, bool],
) -> list[NavigatorRow]:
```

Iterates rows. For `shared_in_unit` rows where `viewer_is_privileged=False`, applies `anonymise_author()` to `owner_display_name`, replacing it with the deterministic pseudonym. Requires the course-level `anonymous_sharing` flag (resolved from course defaults). Returns new `NavigatorRow` instances (frozen dataclass — create replacements).

```python
def group_by_section(
    rows: list[NavigatorRow],
) -> dict[str, list[NavigatorRow]]:
```

Groups rows by `section` field. Sections with zero rows are excluded from the dict (AC1.7 — empty sections hidden).

These are pure functions — no database access, no side effects. Unit-testable.

**Testing:**

Unit tests (no database needed):
- AC1.4: Create NavigatorRow list with shared_in_unit rows. Apply anonymisation with `viewer_is_privileged=False`. Verify owner_display_name is replaced with pseudonym. Verify same user_id always produces same pseudonym.
- AC1.7: Create rows spanning 3 sections but none for "shared_with_me". Verify group_by_section output has 3 keys, "shared_with_me" absent.
- Verify anonymisation does NOT replace names for my_work or shared_with_me sections.
- Verify privileged viewer sees raw names in all sections.

**Verification:**
Run: `uv run test-changed`
Expected: All new tests pass.

**Commit:** `feat: add navigator post-processing helpers for anonymisation and grouping`
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->
