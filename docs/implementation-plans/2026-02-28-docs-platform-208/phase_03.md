# Documentation Platform Implementation Plan — Phase 3

**Goal:** Rewrite the instructor setup guide as a Python module using the Guide DSL, replacing the bash script.

**Architecture:** A single Python function `run_instructor_guide(page, base_url)` that uses the Guide DSL to navigate the app, interact with UI elements via Playwright, capture annotated screenshots, and produce a narrative markdown document. Reuses E2E course_helpers for standard flows (create course, add week, add activity, enrol student). Authentication via mock token URL pattern.

**Tech Stack:** Python 3.14, Playwright sync API, Guide DSL (from Phase 1)

**Scope:** 6 phases from original design (phase 3 of 6)

**Codebase verified:** 2026-02-28

---

## Acceptance Criteria Coverage

This phase implements and tests:

### docs-platform-208.AC5: Guide scripts produce correct output (partial — instructor only)
- **docs-platform-208.AC5.1 Success:** Instructor setup guide produces markdown with ~7 screenshots covering: login, create unit, create week, create activity, configure tags, enrol note, student view
- **docs-platform-208.AC5.3 Success:** All screenshots show element highlights where the guide directs attention and are trimmed of excess whitespace

---

## Reference Files

The task implementor should read these files for context:

- **Existing bash script being replaced:** `docs/guides/scripts/generate-instructor-setup.sh` (206 lines, 7 steps)
- **Common helpers:** `docs/guides/scripts/common.sh` (73 lines)
- **E2E course helpers (reuse):** `tests/e2e/course_helpers.py` — `create_course()`, `add_week()`, `add_activity()`, `enrol_student()`, `publish_week()`, `configure_course_copy_protection()`
- **E2E annotation helpers:** `tests/e2e/annotation_helpers.py` — `_seed_tags_for_workspace()`, `seed_tag_id()`, `seed_group_id()`
- **Instructor E2E test for interaction patterns:** `tests/e2e/test_instructor_workflow.py`
- **Course page data-testids:** `src/promptgrimoire/pages/courses.py`
- **Tag management data-testids:** `src/promptgrimoire/pages/annotation/tag_management.py`, `tag_management_rows.py`
- **Guide DSL (from Phase 1):** `src/promptgrimoire/docs/guide.py`
- **Screenshot module (from Phase 1):** `src/promptgrimoire/docs/screenshot.py`
- **Testing docs:** `docs/testing.md`
- **CLAUDE.md** — Project conventions

---

<!-- START_TASK_1 -->
### Task 1: Write instructor guide Python module

**Verifies:** docs-platform-208.AC5.1, docs-platform-208.AC5.3

**Files:**
- Modify: `src/promptgrimoire/docs/scripts/instructor_setup.py` (replace stub from Phase 2)

**Implementation:**

Replace the stub in `src/promptgrimoire/docs/scripts/instructor_setup.py` with the full guide function. The function `run_instructor_guide(page: Page, base_url: str) -> None` must:

1. **Authenticate as instructor:** Navigate to `f"{base_url}/auth/callback?token=mock-token-instructor@uni.edu"`. Wait for redirect away from `/auth/callback`.

2. Use `Guide("Instructor Setup", Path("docs/guides"), page)` context manager.

3. **Step 1: Login and Navigator (~1 screenshot)**
   - Note explaining the login process
   - Screenshot of navigator page after login
   - Highlight: navigator elements if available

4. **Step 2: Create Unit (~1 screenshot)**
   - Navigate to `/courses/new`
   - Fill `course-code-input` with "TRAN8034"
   - Fill `course-name-input` with "Translation Technologies"
   - Fill `course-semester-input` with "S1 2026"
   - Screenshot with highlights on form fields
   - Click `create-course-btn`
   - Wait for redirect to course detail page

5. **Step 3: Add Week (~1 screenshot)**
   - Click `add-week-btn`
   - Fill `week-number-input` (auto-fills to 1 or set to "3")
   - Fill `week-title-input` with "Source Text Analysis"
   - Click `create-week-btn`
   - Wait for redirect back to course detail
   - Screenshot of course page showing the new week
   - Click `publish-week-btn` to publish the week

6. **Step 4: Create Activity (~1 screenshot)**
   - Click `add-activity-btn` on the week card
   - Fill `activity-title-input` with "Source Text Analysis with AI"
   - Fill `activity-description-input` with description text
   - Click `create-activity-btn`
   - Wait for redirect
   - Screenshot of course page showing the activity

7. **Step 5: Configure Tags (~1 screenshot)**
   - This is the most complex step. The guide needs to:
     - Navigate to the template workspace for the activity
     - Add content to the workspace (paste or inject sample HTML)
     - Open tag management dialog (`tag-settings-btn`)
     - Create tag groups and tags
     - Screenshot the tag management dialog with highlights on key elements
     - Close the dialog (`tag-management-done-btn`)
   - Note: The bash script uses `_seed_tags_for_workspace()` from annotation_helpers.py for deterministic tag seeding. The Python guide can either seed via the same DB helper or create tags through the UI. Since the guide is meant to show the user how to use the UI, prefer UI interaction where practical, but seeding is acceptable for content that would be tedious to demonstrate step-by-step.

8. **Step 6: Enrol Student Note (~1 screenshot)**
   - Click `manage-enrollments-btn`
   - Fill `enrollment-email-input` with "student@uni.edu"
   - Click `add-enrollment-btn`
   - Wait for success notification
   - Screenshot showing enrollment page
   - Click `back-to-unit-btn`

9. **Step 7: Student View (~1 screenshot)**
   - Re-authenticate as student: `f"{base_url}/auth/callback?token=mock-token-student@uni.edu"`
   - Navigate to the student's view of the course/activity
   - Screenshot showing the student perspective

Each step should include narrative text via `guide.note()` explaining what the instructor is doing and why. Use `highlight` parameter on screenshots to draw attention to relevant UI elements via their `data-testid` selectors.

**Wait strategies:** Use `page.wait_for_url()` after navigation, `page.get_by_test_id("element").wait_for(state="visible")` before interaction. Follow patterns from `tests/e2e/test_instructor_workflow.py` and `tests/e2e/course_helpers.py`.

**Testing:**

This is an integration-level guide script that drives a real browser. Unit testing the guide function itself is impractical (it requires a running app server). Verification is operational:
- `uv run make-docs` produces `docs/guides/instructor-setup.md`
- The markdown file contains 7 `##` headings (one per step)
- The markdown file contains 7 `![` image references
- Screenshots exist in `docs/guides/screenshots/` directory
- Screenshots show element highlights (visible outlines)

The "integration test property" of make-docs (AC4.4) provides regression coverage: if the guide breaks, `make-docs` exits non-zero.

**Verification:**

Run: `uv run make-docs` (requires running PostgreSQL and pandoc)
Expected: Produces `docs/guides/instructor-setup.md` with ~7 screenshots

If the full pipeline is not available for local testing, verify the import works:
Run: `uv run python -c "from promptgrimoire.docs.scripts.instructor_setup import run_instructor_guide; print('OK')"`

**UAT Steps:**
1. [ ] Run: `uv run make-docs`
2. [ ] Open `docs/guides/instructor-setup.md` — verify ~7 `##` headings
3. [ ] Verify ~7 `![` image references in the markdown
4. [ ] Open screenshots in `docs/guides/screenshots/` — verify red outlines on highlighted elements
5. [ ] Verify screenshots are trimmed (no large white margins)

**Evidence Required:**
- [ ] `uv run make-docs` exits zero
- [ ] `docs/guides/instructor-setup.md` exists with expected content

**Commit:** `feat: migrate instructor setup guide to Python DSL`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Delete old instructor bash script

**Files:**
- Delete: `docs/guides/scripts/generate-instructor-setup.sh`

**Step 1: Delete the bash script**

Remove `docs/guides/scripts/generate-instructor-setup.sh`.

**Step 2: Verify no references remain**

Search for "generate-instructor-setup" in the codebase. The only reference should be in `src/promptgrimoire/cli.py` which was updated in Phase 2 to call the Python function instead.

**Step 3: Commit**

```bash
git rm docs/guides/scripts/generate-instructor-setup.sh
git commit -m "chore: remove replaced instructor guide bash script"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Verify full pipeline with instructor guide

**Files:** None (verification only)

**Step 1: Run make-docs**

Run: `uv run make-docs`
Expected: Pipeline completes, instructor guide produces markdown and screenshots. Student guide runs as stub (from Phase 2).

**Step 2: Inspect output**

Verify:
- `docs/guides/instructor-setup.md` exists and contains ~7 `##` headings
- `docs/guides/screenshots/` contains ~7 PNG files for instructor guide
- Screenshots are trimmed (no large white margins)
- Screenshots show red outlines on highlighted elements

**Step 3: Run existing tests**

Run: `uv run test-all`
Expected: All existing tests pass, no regressions

Run: `uv run ruff check .`
Expected: No lint errors

Run: `uvx ty check`
Expected: No type errors
<!-- END_TASK_3 -->
