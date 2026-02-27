# Workspace Navigator Implementation Plan — Phase 2: Load-Test Fixture

**Goal:** Populate the development database with realistic data at scale (1100 students) for SQL query validation and FTS testing.

**Architecture:** A separate CLI command `uv run load-test-data` that creates courses, users, enrollments, weeks, activities (with template workspaces prepared by an instructor), student workspaces via direct insertion (modelled on the template's structure), loose workspaces, ACL shares, and CRDT state with highlights, comments, and response drafts. Idempotent — safe to run repeatedly. Text content uses differentiated lipsum/legal phrases so FTS results are distinguishable.

**Tech Stack:** asyncio CLI entry point, existing SQLModel service functions, pycrdt AnnotationDocument for CRDT state generation.

**Scope:** Phase 2 of revised plan (phases 1-3 cover FTS, load-test data, SQL query)

**Codebase verified:** 2026-02-25

**Design deviation:** This phase is not in the original design plan. Added to provide a realistic dataset for validating the navigator SQL query (Phase 3) at the target scale of 1100 students per unit.

**Key constraint:** Student workspace content is created via direct insertion, but the template (documents, tags, tag groups) comes from a prepared instructor activity template created through the production `create_activity()` path. This ensures the template structure is realistic.

---

## Acceptance Criteria Coverage

This phase implements:

### workspace-navigator-196.AC5: Cursor pagination (data prerequisites)
- **workspace-navigator-196.AC5.5 Edge:** Works correctly with 1100+ students in a single unit
  - *This phase:* provides the 1100-student dataset. Pagination verification is Phase 3.

No other ACs are directly tested — this phase is infrastructure for Phase 3 validation.

---

## Codebase Context for Executor

**Key files to read before implementing:**
- `src/promptgrimoire/cli.py` — Existing `seed_data()` at line 2376 and helpers. Follow the same async pattern with `asyncio.run()` entry point. Idempotency via `find_or_create_user()` and catch `DuplicateEnrollmentError`.
- `src/promptgrimoire/db/users.py` — `find_or_create_user(email, display_name)` at line 95. Returns `(User, bool)`.
- `src/promptgrimoire/db/courses.py` — `create_course(code, name, semester)` at line 20. `enroll_user(course_id, user_id, role)` at line 166.
- `src/promptgrimoire/db/activities.py` — `create_activity(week_id, title)` at line 21. Automatically creates template workspace.
- `src/promptgrimoire/db/workspace_documents.py` — `add_document(workspace_id, type, content, source_type, title)` at line 20.
- `src/promptgrimoire/db/workspaces.py` — `create_workspace()` at line 273 (returns bare workspace). `save_workspace_crdt_state(workspace_id, crdt_state)` at line 312.
- `src/promptgrimoire/db/acl.py` — `grant_permission(workspace_id, user_id, permission)` at line 36. UPSERT pattern.
- `src/promptgrimoire/crdt/annotation_doc.py` — `AnnotationDocument()` constructor, `add_highlight()` at line 216, `add_comment()` at line 435, `get_full_state()` at line 536.
- `src/promptgrimoire/db/tags.py` — Tag CRUD for seeding tags into template workspaces.
- `pyproject.toml` — `[project.scripts]` section at line 36.

**Critical patterns:**
- All DB functions use `get_session()` internally — no manual session management needed.
- Async functions wrapped with `asyncio.run()` from sync CLI entry point.
- `find_or_create_user()` is idempotent; `enroll_user()` raises `DuplicateEnrollmentError` — catch and skip.
- `grant_permission()` is UPSERT — idempotent.
- `create_workspace()` returns bare workspace. For loose workspaces, set `course_id` directly via session. For activity workspaces, set `activity_id`.
- Workspace.title defaults to None — set explicitly from activity name for student workspaces.

---

## Data Shape

| Entity | Count | Notes |
|--------|-------|-------|
| Courses | 3 | LAWS1100 (1100 students), LAWS2200 (80), ARTS1000 (15) |
| Instructors | 4 | 1 per course + 1 cross-course admin |
| Students | ~1195 | 1100 in LAWS1100, 80 in LAWS2200, 15 in ARTS1000. ~40 multi-enrolled (in 2 courses) |
| Weeks per course | 3-4 | Mix of published (is_published=True) and unpublished |
| Activities per published week | 2-3 | Each with template workspace + documents + tags |
| Student workspaces (activity-linked) | ~2500-3000 | 1-3 per student, some activities unstarted |
| Loose workspaces | 0-4 per student | 1d6-2 (min 0, max 4), course-placed, no activity |
| Documents per workspace | 1-3 | HTML content — differentiated lipsum/legal text |
| CRDT state per workspace | Yes | 2-5 highlights, 0-3 comments each, response draft |
| `shared_with_class` | ~20% | Peer-visible workspaces |
| Explicit ACL shares | ~50 | Editor/viewer grants across students |
| `search_dirty` | True | All new workspaces marked dirty for worker |

---

## Tasks

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Text content pools and CRDT builder helper

**Verifies:** None (infrastructure helper)

**Files:**
- Create: `src/promptgrimoire/cli_loadtest.py`

**Implementation:**

Create the load-test module with:

1. **Text content pools** — lists of differentiated text for documents, comments, and response drafts. Use legal/annotation domain text so FTS results are meaningful. Each pool item should be distinct enough that searching for a specific phrase identifies a narrow set of workspaces.

   Document pool: 8-10 HTML paragraphs of varied legal text (tort law scenarios, contract disputes, statutory interpretation). Each document gets 2-3 paragraphs randomly selected.

   Comment pool: 15-20 short annotation comments ("This establishes the duty of care", "Relevant to causation analysis", "Compare with Donoghue v Stevenson", etc.).

   Response draft pool: 5-8 short markdown paragraphs for Tab 3 ("In this case, the plaintiff must establish...", "The key issue is whether reasonable foreseeability...", etc.).

2. **`build_crdt_state(document_id, tag_names, student_name, content_length)` helper** — creates an AnnotationDocument, adds 2-5 highlights (randomly positioned within `0..content_length` character range — derive from `len(document_content)` at call time), 0-3 comments per highlight (drawn from comment pool), sets response draft text (drawn from response pool), and returns serialized bytes via `get_full_state()`.

   **Important:** Read `src/promptgrimoire/crdt/annotation_doc.py` line 216 for `add_highlight()` signature and line 435 for `add_comment()` signature before implementing. These methods take specific positional arguments (document_id, character offsets, tag name, highlight text, author info) that must match the CRDT schema exactly.

   The `tag_names` list is drawn from the activity template's tags. Highlights reference tags by name (matching the CRDT convention).

3. **`roll_1d6_minus_2()` helper** — returns `max(0, random.randint(1, 6) - 2)` for loose workspace count.

**Verification:**
Run: `uvx ty check`
Expected: No type errors.

**Commit:** `feat: add load-test text pools and CRDT builder helper`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Load-test CLI command — courses, users, and enrollments

**Verifies:** None (infrastructure — verified operationally)

**Files:**
- Modify: `src/promptgrimoire/cli_loadtest.py` (add to file from Task 1)
- Modify: `pyproject.toml` (add script entry)

**Implementation:**

Add `load_test_data()` as the sync CLI entry point (calls `asyncio.run(_async_load_test_data())`).

The async function creates:

1. **Courses:**
   - LAWS1100 "Introduction to Torts" semester 2026-S1 (default_allow_sharing=True, default_anonymous_sharing=True)
   - LAWS2200 "Contract Law" semester 2026-S1
   - ARTS1000 "Academic Skills" semester 2026-S1

2. **Instructors:** One per course via `find_or_create_user()`, enrolled with role "coordinator". Plus one admin user (`is_admin=True`) enrolled in all three courses as coordinator.

3. **Students:** Generate with email pattern `loadtest-{i}@test.local`, display name `"Load Test Student {i}"`. Use `find_or_create_user()` for idempotency.
   - 1100 students enrolled in LAWS1100
   - 80 enrolled in LAWS2200 (40 of these are also in LAWS1100 — multi-enrolled)
   - 15 enrolled in ARTS1000

4. **Weeks:** 3-4 per course. First 2-3 published, last unpublished.

5. **Activities:** 2-3 per published week. Each created via `create_activity()` (which auto-creates template workspace). Add 2-3 HTML documents to each template workspace via `add_document()`. Seed tags into template workspace (4-6 tags in 2 groups, following `_seed_tags_for_activity` pattern from existing seed script).

Register in pyproject.toml:
```toml
load-test-data = "promptgrimoire.cli_loadtest:load_test_data"
```

Use `rich.console.Console` for progress output (same as existing seed script).

**Verification:**
Run: `uv run load-test-data`
Expected: Creates courses, users, enrollments without errors. Progress output shows counts.

Run again (idempotency check): Should complete without errors or duplicates.

**Commit:** `feat: add load-test CLI for courses, users, and enrollments`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: Student workspaces with CRDT state

**Verifies:** None (infrastructure — verified operationally and via Phase 3 queries)

**Files:**
- Modify: `src/promptgrimoire/cli_loadtest.py`

**Implementation:**

After creating courses/users/activities (Task 2), create student workspaces:

For each student, for each published activity in their enrolled courses:
1. With probability ~70%, create a workspace for that activity (30% left unstarted).
2. **Idempotency:** Before creating, check if a workspace already exists for this student+activity pair (query by `activity_id` and owner ACL). Skip if exists.
3. Create workspace with `activity_id` set, `title` set to activity title.
3. Clone documents from template: for each document in the template workspace, create a corresponding document in the student workspace with the same content (or slightly varied — swap a paragraph from the content pool).
4. Create owner ACL entry via `grant_permission(workspace_id, user_id, "owner")`.
5. Build CRDT state via `build_crdt_state()` helper — highlights reference the cloned document IDs and template tags.
6. Save CRDT state via `save_workspace_crdt_state()`.
7. With probability ~20%, set `shared_with_class=True` on the workspace.

For loose workspaces:
1. Roll `1d6-2` for each student. For each:
2. Create workspace with `course_id` set (to one of their enrolled courses), `activity_id=None`.
3. Set title from a pool of prompt-grimoire-style names ("My Prompt Notes", "Week 3 Reflections", "Legal Research Draft", etc.).
4. Add 1-2 documents with content from the document pool.
5. Create owner ACL entry.
6. Build and save CRDT state.

All workspaces get `search_dirty=True` (the column default).

**Performance note:** Creating 2500+ workspaces sequentially may be slow but acceptable — this is a one-time fixture, not a hot path. Sequential creation is the recommended approach. Concurrent creation via `asyncio.gather()` is an optional optimisation only if you have verified that `create_workspace()`, `add_document()`, and `grant_permission()` are safe under concurrent calls (each uses `get_session()` which creates independent sessions, but verify before attempting).

**Verification:**
Run: `uv run load-test-data`
Expected: Workspaces created with documents and CRDT state. Progress output shows counts.

Verify in database:
```sql
SELECT COUNT(*) FROM workspace WHERE activity_id IS NOT NULL;  -- ~2500+
SELECT COUNT(*) FROM workspace WHERE activity_id IS NULL AND course_id IS NOT NULL;  -- loose workspaces
SELECT COUNT(*) FROM workspace WHERE crdt_state IS NOT NULL;  -- all should have CRDT
SELECT COUNT(*) FROM workspace WHERE search_dirty = TRUE;  -- all should be dirty
```

**Commit:** `feat: add student workspace generation with CRDT state`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: ACL shares and final verification

**Verifies:** None (infrastructure — verified operationally)

**Files:**
- Modify: `src/promptgrimoire/cli_loadtest.py`

**Implementation:**

After creating all workspaces (Task 3), add explicit ACL shares:

1. Select ~50 random student workspaces.
2. For each, grant "editor" or "viewer" permission to 1-2 other students in the same course via `grant_permission()`.
3. This creates the "Shared With Me" section data for the navigator.

Add a final summary print:
```
Load test data summary:
  Users: {count}
  Courses: {count}
  Enrollments: {count}
  Workspaces (activity): {count}
  Workspaces (loose): {count}
  Documents: {count}
  ACL shares: {count}
  Workspaces with shared_with_class: {count}
```

**Verification:**
Run: `uv run load-test-data`
Expected: Full run completes, summary shows expected counts.

Verify ACL shares:
```sql
SELECT COUNT(*) FROM acl_entry WHERE permission IN ('editor', 'viewer');
```
Expected: ~50-100 rows (original + load-test shares).

**Commit:** `feat: add ACL shares and load-test summary`
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->
