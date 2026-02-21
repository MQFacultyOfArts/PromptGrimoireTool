# Annotation Tags QA Pass — Phase 1: E2E Tag Seeding Infrastructure

**Goal:** Fix all 10 broken E2E test files by seeding tags into standalone workspaces.

**Architecture:** A sync DB helper `_seed_tags_for_workspace()` in `tests/e2e/annotation_helpers.py` inserts the Legal Case Brief tag set (3 groups, 10 tags) using raw SQL with `ON CONFLICT DO NOTHING`. Wired into `setup_workspace_with_content()` and `_load_fixture_via_paste()` via `seed_tags=True` default parameter. `data-testid` attributes added to tag management dialog for Phase 2.

**Tech Stack:** psycopg (sync driver), PostgreSQL, Playwright, NiceGUI

**Scope:** Phase 1 of 6 from original design

**Codebase verified:** 2026-02-20

**Status:** COMPLETE (2026-02-21). All 3 tasks delivered: `af17932`, `5f4f570`, `e11b4ec`.

---

## Acceptance Criteria Coverage

This phase implements and tests:

### tags-qa-95.AC1: Broken E2E tests fixed
- **tags-qa-95.AC1.1 Success:** All 10 previously-broken E2E test files pass with tag seeding enabled
- **tags-qa-95.AC1.2 Success:** `create_highlight_with_tag()` finds toolbar buttons at expected indices after seeding
- **tags-qa-95.AC1.3 Success:** Seeding is idempotent -- calling `_seed_tags_for_workspace` twice does not create duplicate tags
- **tags-qa-95.AC1.4 Success:** `setup_workspace_with_content(seed_tags=False)` creates workspace without tags

---

## UAT

After this phase is complete, verify manually:

1. Run `uv run test-e2e` — all 10 previously-broken E2E test files pass
2. Open a workspace in `--headed` mode (`uv run test-e2e -k test_austlii_annotation_workflow --headed`), confirm 10 tag buttons visible in toolbar after page load
3. Open tag management dialog, confirm `data-testid` attributes are present in DOM via browser DevTools (inspect a tag name input, verify `data-testid="tag-name-input-..."`)
4. Run `uv run test-e2e -k "test_full_course_setup" -- --seed-tags=false` or verify that `seed_tags=False` parameter is respected (workspace loads without tags in toolbar)

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Create `_seed_tags_for_workspace()` sync DB helper

**Verifies:** tags-qa-95.AC1.3 (idempotency)

**Files:**
- Modify: `tests/e2e/annotation_helpers.py` (add function alongside other E2E helpers)

**Implementation:**

Create `_seed_tags_for_workspace(workspace_id: str) -> None` following the sync DB pattern of `_grant_workspace_access()` in `conftest.py` (lines 108-144):

1. Read `DATABASE__URL` from `os.environ`, swap `asyncpg` for `psycopg` in the URL
2. Create sync `sqlalchemy.create_engine(sync_url)`
3. Inside `engine.begin()` context:
   - INSERT 3 tag_group rows with `ON CONFLICT (id) DO NOTHING`
   - INSERT 10 tag rows with `ON CONFLICT (id) DO NOTHING`
   - Use deterministic UUIDs (uuid5 from workspace_id + group/tag name) so re-seeding is idempotent
4. Call `engine.dispose()`

Tag data (from `cli.py:1340` seed definitions):

| Group | Color | Tags (name, color, order) |
|-------|-------|---------------------------|
| Case ID | #4a90d9 | Jurisdiction (#1f77b4, 0), Procedural History (#ff7f0e, 1), Decision (#e377c2, 2), Order (#7f7f7f, 3) |
| Analysis | #d9534f | Legally Relevant Facts (#2ca02c, 4), Legal Issues (#d62728, 5), Reasons (#9467bd, 6), Court's Reasoning (#8c564b, 7) |
| Sources | #5cb85c | Domestic Sources (#bcbd22, 8), Reflection (#17becf, 9) |

All tags: `locked=True`, `description=None`. Groups have `order_index` 0, 1, 2 respectively.

Use `uuid.uuid5(uuid.UUID(workspace_id), f"seed-group-{group_name}")` for deterministic group IDs and `uuid.uuid5(uuid.UUID(workspace_id), f"seed-tag-{tag_name}")` for deterministic tag IDs. This makes ON CONFLICT work on the primary key.

**Testing:**

Idempotency (AC1.3) is verified by the E2E tests themselves — if `seed_tags=True` default causes double-seeding (e.g., a test that creates tags then reloads), `ON CONFLICT DO NOTHING` prevents duplicates. Explicit unit testing of a sync DB helper in E2E infrastructure is not required — operational verification (E2E tests pass) suffices.

**Verification:**

Run: `uv run pytest tests/e2e/annotation_helpers.py --co -q` (confirm no import errors)

**Commit:** `feat: add _seed_tags_for_workspace() E2E helper`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Wire `seed_tags` parameter into helper functions

**Verifies:** tags-qa-95.AC1.1, tags-qa-95.AC1.2, tags-qa-95.AC1.4

**Files:**
- Modify: `tests/e2e/annotation_helpers.py` — `setup_workspace_with_content()` (line 139) and `_load_fixture_via_paste()` (line 221)

**Implementation:**

Add `seed_tags: bool = True` parameter to both functions.

For `setup_workspace_with_content()` — after the existing `wait_for_text_walker()` at the end of the function:

```python
if seed_tags:
    workspace_id = page.url.split("workspace_id=")[1].split("&")[0]
    _seed_tags_for_workspace(workspace_id)
    page.reload()
    wait_for_text_walker(page)
```

For `_load_fixture_via_paste()` — same pattern after its final `wait_for_text_walker()`.

Call `_seed_tags_for_workspace(workspace_id)` which is defined in the same file (Task 1).

**Testing:**

- AC1.1: Run full E2E suite — all 10 previously-broken files pass
- AC1.2: `create_highlight_with_tag()` selects toolbar buttons by index — with 10 seeded tags, indices 0-9 are available
- AC1.4: Any test that passes `seed_tags=False` gets a workspace without tags

**Verification:**

Run: `uv run test-e2e`
Expected: All E2E tests pass (10 previously-broken files now work)

**Commit:** `feat: wire seed_tags into E2E workspace helpers`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_3 -->
### Task 3: Add `data-testid` attributes to tag management dialog

**Verifies:** None (infrastructure for Phase 2)

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/tag_management.py`

**Implementation:**

Add `data-testid` attributes to key elements in the management dialog for Playwright selectors in Phase 2. Target elements:

| Element | data-testid | Location in code |
|---------|-------------|-----------------|
| Management dialog container | `tag-management-dialog` | `open_tag_management()` (line 806) |
| Quick-create dialog | `tag-quick-create-dialog` | `open_quick_create()` (line 154) |
| Tag name input in each row | `tag-name-input-{tag_id}` | `_render_tag_row()` (line 266) |
| Tag color input in each row | `tag-color-input-{tag_id}` | `_render_tag_row()` (line 266) |
| Lock icon per tag | `tag-lock-icon-{tag_id}` | `_render_tag_row()` (line 266) |
| Group header | `tag-group-header-{group_id}` | `_render_group_header()` (line 384) |
| Delete tag button | `tag-delete-btn-{tag_id}` | `_render_tag_row()` |
| Delete group button | `group-delete-btn-{group_id}` | `_render_group_header()` |
| Add tag to group button | `group-add-tag-btn-{group_id}` | `_render_group_tags()` (line 532) |
| Import section | `tag-import-section` | `_render_import_section()` (line 664) |
| Done/close button | `tag-management-done-btn` | `open_tag_management()` |

Use NiceGUI's `.props(f'data-testid=tag-name-input-{tag.id}')` pattern on `ui.input`, `ui.button`, `ui.icon`, etc.

**Verification:**

Run: `uv run test-all` (existing tests still pass — data-testid attributes don't affect behaviour)

Optionally run `uv run test-e2e -k test_full_course_setup --headed` to visually confirm `data-testid` attributes render in the DOM via browser DevTools.

**Commit:** `chore: add data-testid attributes to tag management dialog`
<!-- END_TASK_3 -->
