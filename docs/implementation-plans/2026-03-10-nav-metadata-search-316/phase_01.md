# Navigator Metadata Search Implementation Plan — Phase 1

**Goal:** Make owner name, activity title, week title, course code, course name, and workspace title searchable via the navigator search bar.

**Architecture:** Add a third UNION ALL leg to the `fts` CTE in `_SEARCH_SQL` (`src/promptgrimoire/db/navigator.py`). This leg joins visible workspaces to their owner (via ACL), activity, week, and course, concatenates all metadata into one string, and runs PostgreSQL FTS against it. No schema changes, no migration, no search_worker changes.

**Tech Stack:** PostgreSQL FTS (`to_tsvector`, `websearch_to_tsquery`, `ts_headline`, `ts_rank`), SQLAlchemy `text()`, pytest + pytest-asyncio integration tests.

**Scope:** 2 phases from original design (phase 1 of 2).

**Codebase verified:** 2026-03-11

---

## Acceptance Criteria Coverage

This phase implements and tests:

### nav-metadata-search-316.AC1: Owner name search
- **nav-metadata-search-316.AC1.1 Success:** Searching for a term matching the owner's `display_name` returns their workspaces

### nav-metadata-search-316.AC2: Activity title search
- **nav-metadata-search-316.AC2.1 Success:** Searching for an activity title (or substring) returns workspaces under that activity

### nav-metadata-search-316.AC3: Week title search
- **nav-metadata-search-316.AC3.1 Success:** Searching for a week title returns workspaces in that week

### nav-metadata-search-316.AC4: Course code search
- **nav-metadata-search-316.AC4.1 Success:** Searching for a course code (e.g. "LAWS1000") returns workspaces in that unit

### nav-metadata-search-316.AC5: Course name search
- **nav-metadata-search-316.AC5.1 Success:** Searching for a course name (e.g. "Tort Law") returns workspaces in that unit

### nav-metadata-search-316.AC6: Snippet highlights matched metadata
- **nav-metadata-search-316.AC6.1 Success:** Snippet contains `<mark>` tags around the matched metadata term

### nav-metadata-search-316.AC7: Existing search regression
- **nav-metadata-search-316.AC7.1 Regression:** Document content FTS still returns correct results
- **nav-metadata-search-316.AC7.2 Regression:** CRDT search_text FTS still returns correct results

### nav-metadata-search-316.AC9: Orphan workspace handling
- **nav-metadata-search-316.AC9.1 Edge:** Workspace with no activity/week/course does not cause errors and is still findable by owner name or workspace title

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Add metadata FTS leg to `_SEARCH_SQL`

**Verifies:** nav-metadata-search-316.AC1.1, AC2.1, AC3.1, AC4.1, AC5.1, AC6.1, AC9.1 (implementation; tests in Task 2)

**Files:**
- Modify: `src/promptgrimoire/db/navigator.py:337-351` (insert new UNION ALL leg after the existing CRDT search_text leg)

**Implementation:**

Insert a third UNION ALL leg into the `fts` CTE, between the existing CRDT leg (ending at line 351) and the closing `)` of the `fts` CTE.

The new leg must:

1. **Join chain:** `workspace w` → `acl_entry acl ON acl.workspace_id = w.id AND acl.permission = 'owner'` → `"user" u ON u.id = acl.user_id` → `activity a ON a.id = w.activity_id` (LEFT JOIN) → `week wk ON wk.id = a.week_id` (LEFT JOIN) → `course c ON c.id = COALESCE(wk.course_id, w.course_id)` (LEFT JOIN). All joins after `acl_entry` and `"user"` are LEFT JOINs to handle orphan workspaces.

2. **Concatenation expression:** Build a metadata string:
   ```sql
   COALESCE(w.title, '') || ' ' || COALESCE(u.display_name, '') || ' ' || COALESCE(a.title, '') || ' ' || COALESCE(wk.title, '') || ' ' || COALESCE(c.code, '') || ' ' || COALESCE(c.name, '')
   ```

3. **FTS filter:** `WHERE w.id IN (SELECT workspace_id FROM visible_ws) AND to_tsvector('english', <concat>) @@ websearch_to_tsquery('english', :query)`

4. **SELECT clause:** Same structure as existing legs — `ws_id`, `ts_headline(...)` AS `snippet`, `ts_rank(...)` AS `rank`. Reuse `_HEADLINE_OPTIONS`.

The exact SQL to insert after the existing CRDT leg's closing line (`AND to_tsvector(...) @@ websearch_to_tsquery(...)`) and before the `),` that closes the `fts` CTE:

```sql
  UNION ALL
  SELECT w.id AS ws_id,
    ts_headline('english',
      COALESCE(w.title, '') || ' ' || COALESCE(u.display_name, '') || ' '
        || COALESCE(a.title, '') || ' ' || COALESCE(wk.title, '') || ' '
        || COALESCE(c.code, '') || ' ' || COALESCE(c.name, ''),
      websearch_to_tsquery('english', :query),
      '{_HEADLINE_OPTIONS}'
    ) AS snippet,
    ts_rank(
      to_tsvector('english',
        COALESCE(w.title, '') || ' ' || COALESCE(u.display_name, '') || ' '
          || COALESCE(a.title, '') || ' ' || COALESCE(wk.title, '') || ' '
          || COALESCE(c.code, '') || ' ' || COALESCE(c.name, '')),
      websearch_to_tsquery('english', :query)
    ) AS rank
  FROM workspace w
  JOIN acl_entry acl ON acl.workspace_id = w.id AND acl.permission = 'owner'
  JOIN "user" u ON u.id = acl.user_id
  LEFT JOIN activity a ON a.id = w.activity_id
  LEFT JOIN week wk ON wk.id = a.week_id
  LEFT JOIN course c ON c.id = COALESCE(wk.course_id, w.course_id)
  WHERE w.id IN (SELECT workspace_id FROM visible_ws)
    AND to_tsvector('english',
      COALESCE(w.title, '') || ' ' || COALESCE(u.display_name, '') || ' '
        || COALESCE(a.title, '') || ' ' || COALESCE(wk.title, '') || ' '
        || COALESCE(c.code, '') || ' ' || COALESCE(c.name, ''))
      @@ websearch_to_tsquery('english', :query)
```

**Key details:**
- The `acl_entry` join uses `AND acl.permission = 'owner'` — this is how the existing `_NAV_CTE` resolves workspace owners (see lines 96-98 of `navigator.py`).
- `COALESCE(wk.course_id, w.course_id)` mirrors the existing nav CTE pattern (line 103) where workspace may have a direct `course_id` without going through activity→week.
- LEFT JOINs on activity, week, course ensure orphan workspaces (no activity) still participate in metadata search via owner name and workspace title.

**Verification:**

Run: `uv run ruff check src/promptgrimoire/db/navigator.py && uv run ruff format src/promptgrimoire/db/navigator.py`
Expected: No errors

Run: `uvx ty check`
Expected: No new type errors

Run: `uv run complexipy src/promptgrimoire/db/navigator.py --max-complexity-allowed 15`
Expected: No functions exceed complexity threshold

**Commit:** `feat: add metadata FTS leg to navigator search (#316)`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Integration tests for metadata search

**Verifies:** nav-metadata-search-316.AC1.1, AC2.1, AC3.1, AC4.1, AC5.1, AC6.1, AC7.1, AC7.2, AC9.1

**Files:**
- Modify: `tests/integration/test_fts_search.py` — add new test helper and test classes

**Implementation:**

Add a new helper function `_create_workspace_with_metadata()` to `tests/integration/test_fts_search.py`. This helper creates the full hierarchy: course → week → activity → workspace + owner ACL + document.

```python
async def _create_workspace_with_metadata(
    *,
    owner_display_name: str | None = None,
    activity_title: str = "Test Activity",
    week_title: str = "Week 1",
    course_code: str | None = None,
    course_name: str = "Test Course",
    workspace_title: str | None = None,
    document_content: str = "<p>placeholder content</p>",
) -> tuple[UUID, UUID]:
    """Create a user + course hierarchy + workspace for metadata FTS testing.

    Returns (user_id, workspace_id).
    """
```

The helper must:
1. Generate a unique `tag = uuid4().hex[:8]` for data isolation
2. Create a user with `display_name = owner_display_name or f"Meta User {tag}"`
3. Create a course with `code = course_code or f"M{tag[:6].upper()}"`, `name = course_name`
4. Create a week with `week_number=1`, `title = week_title`
5. Create an annotation activity with `title = activity_title` (requires `template_workspace_id` — create a template workspace first)
6. Create the target workspace, set `activity_id` and `course_id` via SQL UPDATE
7. Grant owner permission via `grant_permission(ws.id, user.id, "owner")`
8. Set workspace title if provided (via SQL UPDATE)
9. Create a `WorkspaceDocument` with `document_content`
10. Return `(user.id, ws.id)`

Use existing imports already in the file: `create_user` from `promptgrimoire.db.users`, `create_workspace` from `promptgrimoire.db.workspaces`, `grant_permission` from `promptgrimoire.db.acl`, `create_course` from `promptgrimoire.db.courses`, `WorkspaceDocument` from `promptgrimoire.db.models`. Add imports for `create_week` from `promptgrimoire.db.weeks` and activity creation.

For activity creation, check `promptgrimoire.db.activities` for `create_activity()`. The activity needs `week_id`, `title`, `type="annotation"`, and `template_workspace_id` (a separate workspace). Follow the pattern in `tests/integration/test_activity_crud.py`.

**Tests to add** (each as a class with one `@pytest.mark.asyncio` test method, following existing file style):

1. **`TestMetadataSearchOwnerName`** (AC1.1): Create workspace with `owner_display_name="Bartholomew Greenfield"`. Search for `"Bartholomew"`. Assert workspace appears in results.

2. **`TestMetadataSearchActivityTitle`** (AC2.1): Create workspace with `activity_title="Contractual Obligations Analysis"`. Search for `"Contractual Obligations"`. Assert workspace appears.

3. **`TestMetadataSearchWeekTitle`** (AC3.1): Create workspace with `week_title="Foundations of Tort"`. Search for `"Foundations Tort"`. Assert workspace appears.

4. **`TestMetadataSearchCourseCode`** (AC4.1): Create workspace with `course_code="LAWS3100"`. Search for `"LAWS3100"`. Assert workspace appears.

5. **`TestMetadataSearchCourseName`** (AC5.1): Create workspace with `course_name="Environmental Regulation"`. Search for `"Environmental Regulation"`. Assert workspace appears.

6. **`TestMetadataSearchWorkspaceTitle`**: Create workspace with `workspace_title="Jurisprudential Analysis Portfolio"` (using `_create_workspace_with_metadata`). Search for `"Jurisprudential Analysis"`. Assert workspace appears. This tests workspace title as a standalone searchable field.

8. **`TestMetadataSearchSnippetHighlight`** (AC6.1): Create workspace with `course_code="LAWS3100"`, `course_name="Environmental Regulation"`. Search for `"LAWS3100"`. Assert `"<mark>"` and `"</mark>"` appear in the result's snippet.

9. **`TestMetadataSearchOrphanWorkspace`** (AC9.1): Create a workspace with NO activity/week/course (use `_create_owned_workspace_with_document` with a distinctive `title`). Search for the title. Assert workspace appears. This tests that LEFT JOINs handle missing hierarchy.

10. **`TestMetadataSearchRegressionDocumentContent`** (AC7.1): Create workspace with document containing "promissory estoppel" (using `_create_owned_workspace_with_document`). Search for `"promissory estoppel"`. Assert workspace appears. This explicitly verifies document content FTS still works after adding the metadata leg.

11. **`TestMetadataSearchRegressionCRDTSearchText`** (AC7.2): Create workspace with `search_text="quantum meruit restitution"` (using `_create_owned_workspace_with_document` with `search_text` param). Search for `"quantum meruit"`. Assert workspace appears. This explicitly verifies CRDT search_text FTS still works.

Each test should:
- Call the helper to create test data
- Call `_search(query, user_id)` (the existing search helper)
- Assert `len(results) >= 1`
- Assert `any(h.row.workspace_id == ws_id for h in results)`
- For AC6.1, also assert `"<mark>" in results[0].snippet`

**Verification:**

Run: `uv run grimoire test run tests/integration/test_fts_search.py`
Expected: All tests pass (including existing tests — regression check)

Run: `uv run grimoire test all`
Expected: Full suite passes

**Commit:** `test: add metadata search integration tests (#316)`

## UAT Steps

1. [ ] Start the app: `uv run run.py`
2. [ ] Seed development data: `uv run grimoire seed run`
3. [ ] Navigate to: `/` (navigator page)
4. [ ] Type a known owner display name (e.g., from seed data) into the search bar
5. [ ] Verify: workspaces owned by that user appear in search results
6. [ ] Type a known course code (e.g., "LAWS1100") into the search bar
7. [ ] Verify: workspaces in that unit appear in search results
8. [ ] Type a document content term (e.g., from a known workspace) into the search bar
9. [ ] Verify: existing document content search still works (regression)

## Evidence Required

- [ ] Integration test output showing all metadata search tests green
- [ ] Manual verification in running app that metadata search returns results
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->
