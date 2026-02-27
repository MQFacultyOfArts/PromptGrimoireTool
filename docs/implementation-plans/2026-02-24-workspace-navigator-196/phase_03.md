# Workspace Navigator Implementation Plan — Phase 3: Navigator SQL Query

**Goal:** Write, validate, and have human-approved the SQL query that powers the workspace navigator — returning all workspace data for a user across four sections in a single query.

**Architecture:** Contract-first. This phase specifies inputs, outputs, and constraints. The actual SQL is developed iteratively during implementation, validated against Phase 2 load-test data with `EXPLAIN ANALYZE`, and submitted for human approval before any Python wrapper is built.

**Tech Stack:** PostgreSQL (UNION ALL, CTEs, COALESCE for tristate resolution, keyset cursor pagination). Validated with `EXPLAIN ANALYZE` and `psql`.

**Scope:** Phase 3 of revised plan (phases 1-3 cover FTS, load-test data, SQL query)

**Codebase verified:** 2026-02-25

**Human review gate:** The SQL query is the most complex component of this feature. It MUST be reviewed and approved by a human before proceeding to Phase 4+. Approval is based on: correct results for all sections, correct permission filtering, and acceptable `EXPLAIN ANALYZE` performance against the 1100-student dataset.

**Key constraint:** The query stays as a single UNION ALL. Splitting into 4 separate queries is premature anti-optimisation.

**Design deviation:** Design plan specifies `load_navigator_page(user_id, is_privileged, cursor, limit)` with 4 parameters. Added `enrolled_course_ids: Sequence[UUID]` as a fifth parameter to keep enrollment queries separate from the navigator SQL — the caller pre-computes enrolled courses, avoiding embedding enrollment logic in the data layer.

---

## Acceptance Criteria Coverage

This phase implements and validates (via SQL, not UI):

### workspace-navigator-196.AC1: Navigator page renders all sections
- **workspace-navigator-196.AC1.1 Success:** Student sees "My Work" with all owned workspaces grouped by unit > week > activity
- **workspace-navigator-196.AC1.2 Success:** Student sees "Unstarted Work" with all published activities they haven't started
- **workspace-navigator-196.AC1.3 Success:** Student sees "Shared With Me" with workspaces shared via explicit ACL (editor/viewer)
- **workspace-navigator-196.AC1.4 Success:** Student sees "Shared in [Unit]" per enrolled unit, with peer workspaces grouped by anonymised student
  - *This phase:* raw display names returned; anonymisation verified at rendering layer.
- **workspace-navigator-196.AC1.5 Success:** Instructor sees "Shared in [Unit]" with all student workspaces grouped by real student name
- **workspace-navigator-196.AC1.6 Success:** Loose workspaces (no activity) appear under "Unsorted" within each student grouping
- **workspace-navigator-196.AC1.7 Edge:** Empty sections (no shared workspaces, no unstarted work) are hidden, not rendered empty
  - *This phase:* empty sections produce zero rows.
- **workspace-navigator-196.AC1.8 Edge:** Student enrolled in multiple units sees separate "Shared in [Unit]" section per unit

### workspace-navigator-196.AC5: Cursor pagination (data layer)
- **workspace-navigator-196.AC5.1 Success:** Initial load shows first 50 rows across all sections
- **workspace-navigator-196.AC5.2 Success:** "Load more" fetches next 50 rows, appended into correct sections
- **workspace-navigator-196.AC5.4 Edge:** Total rows fewer than 50 — loads all in one page, no "Load more"
- **workspace-navigator-196.AC5.5 Edge:** Works correctly with 1100+ students in a single unit

---

## Codebase Context for Executor

**Key files to read before implementing:**
- `src/promptgrimoire/db/acl.py` — Existing query patterns. `list_accessible_workspaces()` (line 114): Workspace JOIN ACLEntry pattern. `list_peer_workspaces_with_owners()` (line 552): shared_with_class filtering, template exclusion, owner JOIN. `_derive_enrollment_permission()` (line 223): hierarchy walk Workspace → Activity → Week → Course.
- `src/promptgrimoire/db/models.py` — All model relationships. Key FKs: Workspace.activity_id → Activity.id (SET NULL), Activity.week_id → Week.id (CASCADE), Week.course_id → Course.id (CASCADE), Workspace.course_id → Course.id (SET NULL), ACLEntry.workspace_id → Workspace.id (CASCADE), ACLEntry.user_id → User.id (CASCADE), CourseEnrollment.course_id + user_id (unique).
- `src/promptgrimoire/pages/courses.py` — `_build_peer_map()` (line 76): tristate resolution pattern with `resolve_tristate()` and anonymisation.
- `docs/database.md` — Full schema reference.

**Existing indexes (verified against database):**
- `uq_acl_entry_workspace_user` on `(workspace_id, user_id)` — ACL lookups
- `ix_acl_entry_user_id` on `(user_id)` — "find my workspaces" queries
- `ix_workspace_activity_id` on `(activity_id)` — workspace-to-activity
- `ix_workspace_course_id` on `(course_id)` — loose workspace lookups
- `ix_workspace_updated_at` on `(updated_at)` — sort key
- `uq_course_enrollment_course_user` on `(course_id, user_id)` — enrollment checks
- `ix_activity_week_id` on `(week_id)` — activity-to-week traversal
- `activity_template_workspace_id_key` unique on `(template_workspace_id)` — template exclusion

**Permission levels:** owner=30, editor=20, peer=15, viewer=10.
**Staff roles (is_staff=TRUE):** coordinator, instructor, tutor.
**Tristate resolution in SQL:** `COALESCE(a.allow_sharing, c.default_allow_sharing)` — activity override wins, else course default.
**Template exclusion:** `w.id != a.template_workspace_id` (or use the unique index for anti-join).

---

## Query Contract

### Inputs

| Parameter | Type | Description |
|-----------|------|-------------|
| `user_id` | UUID | The authenticated user |
| `is_privileged` | bool | Whether user has staff role in any enrolled course |
| `enrolled_course_ids` | UUID[] | Courses the user is enrolled in |
| `cursor` | (section_priority, sort_key, row_id) or NULL | Keyset cursor for pagination (NULL = first page) |
| `limit` | int | Rows per page (default 50) |

### Output columns (per row)

| Column | Type | Description |
|--------|------|-------------|
| `section` | text | `'my_work'`, `'unstarted'`, `'shared_with_me'`, `'shared_in_unit'` |
| `section_priority` | int | 1=my_work, 2=unstarted, 3=shared_with_me, 4=shared_in_unit |
| `workspace_id` | UUID or NULL | NULL for unstarted activities |
| `activity_id` | UUID or NULL | NULL for loose workspaces |
| `activity_title` | text or NULL | |
| `week_title` | text or NULL | |
| `week_number` | int or NULL | |
| `course_id` | UUID or NULL | |
| `course_code` | text or NULL | |
| `course_name` | text or NULL | |
| `title` | text or NULL | Workspace title (NULL → "Untitled Workspace" in UI) |
| `updated_at` | timestamptz or NULL | Last edit date |
| `owner_user_id` | UUID or NULL | Workspace owner |
| `owner_display_name` | text or NULL | Raw name (anonymisation in Python) |
| `permission` | text or NULL | Viewer's relationship: owner, editor, viewer, peer, or NULL (unstarted) |
| `shared_with_class` | bool | Whether workspace is peer-visible. `FALSE` for unstarted rows. |
| `sort_key` | timestamptz | For cursor pagination. For unstarted rows, use `activity.created_at`. |
| `row_id` | UUID | Tiebreaker for cursor. For unstarted rows, use `activity_id`. For zero-workspace instructor rows (workspace_id=NULL), use `owner_user_id`. |

### Section constraints

**Section 1 — my_work (priority=1):**
- All workspaces where user is owner (ACL permission='owner')
- Includes activity-linked AND loose workspaces (course_id set, activity_id NULL)
- Excludes activity template workspaces
- Sorted by updated_at DESC

**Section 2 — unstarted (priority=2):**
- Published activities in enrolled courses where user owns no workspace for that activity
- workspace_id is NULL in these rows (no workspace exists yet)
- Sorted by course_code, week_number, activity_title (or created_at)

**Section 3 — shared_with_me (priority=3):**
- Workspaces where user has explicit ACL entry with permission IN ('editor', 'viewer')
- NOT where user is owner (those are in section 1)
- Includes owner display name for attribution
- Sorted by updated_at DESC

**Section 4 — shared_in_unit (priority=4):**
- Per enrolled course
- **Student view (is_privileged=FALSE):**
  - Only workspaces with `shared_with_class=TRUE`
  - Only in activities where sharing is enabled: `COALESCE(activity.allow_sharing, course.default_allow_sharing) = TRUE`
  - Excludes user's own workspaces
  - Includes loose workspaces (course-placed, no activity) that are shared_with_class AND `course.default_allow_sharing = true`
- **Instructor view (is_privileged=TRUE):**
  - ALL non-template student workspaces in enrolled courses
  - ~~Includes students with zero workspaces as rows with workspace_id=NULL~~ **DEVIATION:** Zero-workspace students moved to `db/courses.list_students_without_workspaces()`, surfaced on the course detail page. See [#198](https://github.com/MQFacultyOfArts/PromptGrimoireTool/issues/198) for proper analytics page.
  - Includes loose workspaces
- Sorted by course_code, owner_display_name, updated_at DESC

### Keyset cursor pagination

- Mixed sort direction: section_priority ASC, sort_key DESC, row_id ASC
- Use OR scalar comparisons for the mixed-direction keyset (not ROW() comparison):
  ```sql
  WHERE (section_priority > :cursor_priority)
     OR (section_priority = :cursor_priority AND sort_key < :cursor_sort_key)
     OR (section_priority = :cursor_priority AND sort_key = :cursor_sort_key AND row_id > :cursor_row_id)
  ```
- Fetch `limit + 1` rows to detect whether more pages exist
- If `len(rows) > limit`, pop last row and construct next_cursor from the last returned row
- First page: cursor is NULL, no WHERE filter on cursor columns

---

## Tasks

<!-- START_SUBCOMPONENT_A (tasks 1-4) -->
<!-- START_TASK_1 -->
### Task 1: Write the SQL query iteratively

**Verifies:** workspace-navigator-196.AC1.1, AC1.2, AC1.3, AC1.4, AC1.5, AC1.6, AC1.8

**Files:**
- Create: `src/promptgrimoire/db/navigator.sql` (the query, for review)
- Create: `src/promptgrimoire/db/navigator.py` (Python module wrapping the query)

**Implementation:**

Write the UNION ALL query that satisfies the contract above. Work through it section by section:

1. Start with section 1 (my_work) — get it returning correct results for a test user.
2. Add section 2 (unstarted) — verify the NOT EXISTS subquery works.
3. Add section 3 (shared_with_me) — verify editor/viewer ACL filtering.
4. Add section 4 (shared_in_unit) — handle both student and instructor variants via parameterised WHERE conditions (not separate SQL branches).
5. Wrap in CTE, add keyset cursor WHERE clause and ORDER BY + LIMIT.

Test each section individually against the Phase 2 load-test data before combining.

Save the final query as `navigator.sql` for human review (this file is documentation, not executed directly).

Create `navigator.py` with:

```python
@dataclasses.dataclass(frozen=True, slots=True)
class NavigatorRow:
    """One row from the navigator query."""
    section: str
    section_priority: int
    workspace_id: UUID | None
    activity_id: UUID | None
    activity_title: str | None
    week_title: str | None
    week_number: int | None
    course_id: UUID | None
    course_code: str | None
    course_name: str | None
    title: str | None
    updated_at: datetime | None
    owner_user_id: UUID | None
    owner_display_name: str | None
    permission: str | None
    shared_with_class: bool
    sort_key: datetime
    row_id: UUID

class NavigatorCursor(NamedTuple):
    section_priority: int
    sort_key: datetime
    row_id: UUID

async def load_navigator_page(
    user_id: UUID,
    is_privileged: bool,
    enrolled_course_ids: Sequence[UUID],
    cursor: NavigatorCursor | None = None,
    limit: int = 50,
) -> tuple[list[NavigatorRow], NavigatorCursor | None]:
```

The function executes the query via `session.execute(text(...), params)` and maps results to `NavigatorRow` instances. Returns `(rows, next_cursor)`.

**Verification:**
Run the query manually in psql against the load-test database.
Verify each section returns correct rows for a student user and an instructor user.

**Commit:** `feat: implement navigator UNION ALL query with data loader`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: EXPLAIN ANALYZE validation

**Verifies:** workspace-navigator-196.AC5.5

**Files:**
- Create: `docs/implementation-plans/2026-02-24-workspace-navigator-196/explain-analyze-results.md` (documentation)

**Implementation:**

Run `EXPLAIN ANALYZE` against the Phase 2 load-test data for:

1. **Student query** — a student enrolled in LAWS1100 (1100 students), first page (no cursor).
2. **Student query** — same student, second page (with cursor from page 1).
3. **Instructor query** — an instructor in LAWS1100, first page.
4. **Instructor query** — same instructor, second page.
5. **Multi-enrolled student** — a student in both LAWS1100 and LAWS2200.

For each, capture the `EXPLAIN ANALYZE` output and document:
- Total execution time
- Whether GIN indexes are used (Bitmap Index Scan)
- Whether sequential scans appear on large tables (workspace, acl_entry, user)
- Row estimates vs actual rows

If sequential scans appear on tables with >100 rows, propose additional indexes.

Save results to `explain-analyze-results.md` for human review.

**Verification:**
All queries execute in <200ms against the 1100-student dataset.
No sequential scans on tables with >1000 rows.

**Commit:** `docs: add EXPLAIN ANALYZE results for navigator query`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Integration tests

**Verifies:** workspace-navigator-196.AC1.1, AC1.2, AC1.3, AC1.4, AC1.5, AC1.6, AC1.7, AC1.8, AC5.1, AC5.2, AC5.4

**Files:**
- Test: `tests/integration/test_navigator_loader.py` (integration — requires PostgreSQL)

**Implementation:**

Integration tests for `load_navigator_page()`. Create test data via direct model insertion (not via load-test fixture — tests must be self-contained).

Follow project integration test patterns: module-level skip guard, class-based grouping, `@pytest.mark.asyncio`, UUID-based isolation.

Tests must verify each AC:
- AC1.1: Create user with owned workspaces across 2 courses. Verify my_work rows include all, with correct course/week/activity context.
- AC1.2: Create published activities where user has no workspace. Verify unstarted rows appear. Create unpublished activity — verify excluded.
- AC1.3: Create workspace with editor ACL for user. Verify shared_with_me row appears with correct permission and owner display name.
- AC1.4: Create peer workspaces with `shared_with_class=True` in activities where `allow_sharing` resolves to True. Call with `is_privileged=False`. Verify shared_in_unit rows appear, excluding user's own.
- AC1.5: Same data, call with `is_privileged=True`. Verify all student workspaces appear (not just shared ones).
- AC1.6: Create loose workspace (course_id set, activity_id=None). Verify it appears in my_work for the owner and in shared_in_unit for instructors.
- AC1.7: Verify sections with no matching rows produce zero rows (empty sections hidden by UI).
- AC1.8: Enrol user in 2 courses. Verify shared_in_unit rows carry distinct course_id values.
- AC5.1: Insert enough test data to exceed 50 rows. Load with limit=50. Verify 50 rows returned and next_cursor is not None.
- AC5.2: Load first page with limit=50, use returned cursor to load second page. Verify second page rows are appended correctly (no duplicates, no gaps vs first page).
- AC5.4: Insert fewer than 50 rows. Verify all rows returned and next_cursor is None.

Additional test cases:
- AC5.5 (instructor at scale): Use load-test data — instructor in LAWS1100, verify query returns rows and next_cursor within acceptable time. Guard with a data-presence check (e.g., `COUNT(*) FROM workspace > 2000`) and skip if load-test data is absent. Place in a separate test class from self-contained tests.
- Template workspaces excluded from all sections.
- Activity with `allow_sharing=FALSE` (overriding course default TRUE) — no peer workspaces visible for that activity.
- Instructor view: enrolled student with zero workspaces appears as a row with `workspace_id=NULL` in shared_in_unit section.

**Verification:**
Run: `uv run test-changed`
Expected: All new tests pass.

**Commit:** `test: add integration tests for navigator data loader`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Human review gate

**Verifies:** None (process gate)

**Files:** None (review only)

**Implementation:**

Present for human review:
1. The SQL query (`navigator.sql`)
2. The `EXPLAIN ANALYZE` results
3. Any proposed additional indexes
4. Integration test results

**Do not proceed to Phase 4+ until human approves.**

**Verification:**
Human confirms: query is correct, performance is acceptable, indexes are appropriate.

**Commit:** None (no code changes)
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_A -->

---

## Next Steps — Phases 4-7 Not Yet Planned

**This concludes the first batch of implementation plans (Phases 1-3).** The design plan has 7 phases total. After the human review gate above approves the SQL query, the remaining phases need implementation plans written before execution continues:

| Phase | Design Section | Scope |
|-------|---------------|-------|
| Phase 4 | Search | Client-side title filter + FTS UI wiring, debounce, snippets |
| Phase 5 | Inline title rename | Pencil icon, inline edit, default title on clone |
| Phase 6 | Cursor pagination UI | "Load more" button, DOM append into sections |
| Phase 7 | Navigation chrome & i18n | Home icon, "Unit" terminology, pydantic-settings config |

**To plan phases 4-7:** Start a new session and run the `writing-implementation-plans` skill against the same design plan (`docs/design-plans/2026-02-24-workspace-navigator-196.md`), scoping to phases 4-7. Provide the phase 1-3 implementation plans as prior context.
