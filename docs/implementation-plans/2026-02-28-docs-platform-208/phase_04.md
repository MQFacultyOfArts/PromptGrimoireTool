# Documentation Platform Implementation Plan — Phase 4

**Goal:** Rewrite the student workflow guide as a Python module using the Guide DSL, replacing the bash script.

**Architecture:** A single Python function `run_student_guide(page, base_url)` that uses the Guide DSL to walk through the student annotation workflow: login, navigate, create workspace, paste content, create highlights with tags, add comments, use organise/respond tabs, and export PDF. Imports `wait_for_text_walker()` and `select_chars()` from `tests/e2e/annotation_helpers.py` for text selection interactions.

**Tech Stack:** Python 3.14, Playwright sync API, Guide DSL (from Phase 1)

**Scope:** 6 phases from original design (phase 4 of 6)

**Codebase verified:** 2026-02-28

---

## Acceptance Criteria Coverage

This phase implements and tests:

### docs-platform-208.AC5: Guide scripts produce correct output (partial — student guide)
- **docs-platform-208.AC5.2 Success:** Student workflow guide produces markdown with ~10 screenshots covering: login, navigate, create workspace, paste content, highlight text, add comment, organise tab, respond tab, export PDF
- **docs-platform-208.AC5.3 Success:** All screenshots show element highlights where the guide directs attention and are trimmed of excess whitespace

### docs-platform-208.AC8: Old pipeline fully replaced (partial — bash scripts)
- **docs-platform-208.AC8.2 Success:** All bash guide scripts (`generate-instructor-setup.sh`, `generate-student-workflow.sh`, `common.sh`, `debug-instructor.sh`) are deleted

---

## Reference Files

The task implementor should read these files for context:

- **Existing bash script being replaced:** `docs/guides/scripts/generate-student-workflow.sh` (153 lines, 9 steps)
- **Common helpers being deleted:** `docs/guides/scripts/common.sh` (73 lines)
- **Debug script being deleted:** `docs/guides/scripts/debug-instructor.sh`
- **E2E annotation helpers (import):** `tests/e2e/annotation_helpers.py` — `wait_for_text_walker()` (line 661), `select_chars()` (line 355), `create_highlight_with_tag()` (line 465)
- **Student E2E test for interaction patterns:** `tests/e2e/test_law_student.py`
- **Annotation page data-testids:** `src/promptgrimoire/pages/annotation/` (workspace.py, cards.py, organise.py, respond.py, header.py, content_form.py, document.py)
- **Navigator data-testids:** `src/promptgrimoire/pages/navigator/_cards.py` — `start-activity-btn-{aid}`
- **Guide DSL (from Phase 1):** `src/promptgrimoire/docs/guide.py`
- **Screenshot module (from Phase 1):** `src/promptgrimoire/docs/screenshot.py`
- **Testing docs:** `docs/testing.md`
- **CLAUDE.md** — Project conventions

---

<!-- START_TASK_1 -->
### Task 1: Extract annotation helpers to src/promptgrimoire/docs/helpers.py

**Files:**
- Create: `src/promptgrimoire/docs/helpers.py`
- Modify: `tests/e2e/annotation_helpers.py` (update to re-export from new location)

**Implementation:**

Extract `wait_for_text_walker()` and `select_chars()` from `tests/e2e/annotation_helpers.py` into `src/promptgrimoire/docs/helpers.py`. These functions are pure Playwright interactions (mouse moves, page evaluations, DOM waits) with no test-specific dependencies, making them suitable for the production package.

The new `src/promptgrimoire/docs/helpers.py` should contain:
- `wait_for_text_walker(page: Page, *, timeout: int = 15000) -> None`
- `select_chars(page: Page, start_char: int, end_char: int) -> None`

After extraction, update `tests/e2e/annotation_helpers.py` to import from the new location and re-export, so existing E2E tests continue to work unchanged:
```python
from promptgrimoire.docs.helpers import wait_for_text_walker, select_chars  # re-export
```

**Verification:**

Run: `uv run python -c "from promptgrimoire.docs.helpers import wait_for_text_walker, select_chars; print('OK')"`
Expected: Prints "OK"

Run: `uv run test-all`
Expected: All tests pass (E2E helpers still work via re-export)

**Commit:** `refactor: extract annotation helpers to promptgrimoire.docs.helpers for guide scripts`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Write student workflow guide Python module

**Verifies:** docs-platform-208.AC5.2, docs-platform-208.AC5.3

**Files:**
- Modify: `src/promptgrimoire/docs/scripts/student_workflow.py` (replace stub from Phase 2)

**Implementation:**

Replace the stub in `src/promptgrimoire/docs/scripts/student_workflow.py` with the full guide function. The function `run_student_guide(page: Page, base_url: str) -> None` must:

**Prerequisites:** This guide depends on data created by the instructor guide (Phase 3). The instructor guide creates a unit (TRAN8034), week, and activity with tags. The student must be enrolled (done by instructor guide's enrollment step).

**Imports needed:**
```python
from promptgrimoire.docs.helpers import wait_for_text_walker, select_chars
```

**Prerequisite:** Before writing the guide, extract `wait_for_text_walker()` and `select_chars()` from `tests/e2e/annotation_helpers.py` into `src/promptgrimoire/docs/helpers.py`. These functions are needed by the guide scripts but `tests/` is not on the Python import path for `make-docs` (only `src/promptgrimoire` is in `pyproject.toml` `packages`). After extraction, update `tests/e2e/annotation_helpers.py` to import from the new location so E2E tests continue to work. The extracted functions are pure Playwright interactions with no test-specific dependencies, making them suitable for the production package.

1. **Authenticate as student:** Navigate to `f"{base_url}/auth/callback?token=mock-token-student@uni.edu"`. Wait for redirect away from `/auth/callback`.

2. Use `Guide("Student Workflow", Path("docs/guides"), page)` context manager.

3. **Step 1: Login (~1 screenshot)**
   - Note explaining student login
   - Screenshot of navigator page after login
   - Highlight: navigator elements

4. **Step 2: Navigate to Activity (~1 screenshot)**
   - Note explaining the navigator shows enrolled activities
   - Screenshot showing the activity list
   - Highlight: `start-activity-btn-*` (the start button for the activity)

5. **Step 3: Create Workspace (~1 screenshot)**
   - Click `start-activity-btn-*` (use prefix locator: `page.locator("[data-testid^='start-activity-btn']")`)
   - Wait for `content-editor` to be visible
   - Screenshot of empty workspace
   - Highlight: `content-editor`

6. **Step 4: Paste Content (~2 screenshots)**
   - Inject sample HTML content into the editor's contenteditable div (`.q-editor__content`). Use `page.evaluate()` to set innerHTML.
   - **Exemption from "no JS injection" rule:** The Quasar QEditor is a contenteditable `<div>`, not a standard `<input>` or `<textarea>`. Playwright's `fill()` does not work on contenteditable elements for HTML content — only `page.evaluate()` can set innerHTML. This matches the existing bash script's approach and is acceptable in guide scripts (which are not E2E tests).
   - Click `add-document-btn`
   - Wait for and click `confirm-content-type-btn`
   - Wait for `#doc-container` content to appear
   - Call `wait_for_text_walker(page)` to ensure text nodes are indexed
   - Screenshot after content is processed
   - Highlight: document container area

7. **Step 5: Highlight Text and Tag (~1 screenshot)**
   - Use `select_chars(page, start_char, end_char)` to select a text range (pick character offsets that select meaningful text from the injected content)
   - Wait for tag toolbar to show selection state
   - Click a tag button from the toolbar: `page.locator("[data-testid='tag-toolbar'] button").nth(0)`
   - Wait for `annotation-card` to appear
   - Screenshot showing the highlight and annotation card
   - Highlight: `annotation-card`, `tag-toolbar`

8. **Step 6: Add Comment (~1 screenshot)**
   - Click on the annotation card
   - Fill `comment-input` with a sample comment
   - Click `post-comment-btn`
   - Wait for comment to appear
   - Screenshot showing the comment on the card
   - Highlight: `comment-input`

9. **Step 7: Organise Tab (~1 screenshot)**
   - Click `tab-organise`
   - Wait for `organise-columns` to be visible
   - Screenshot of the organise view with tag columns
   - Highlight: `organise-columns`

10. **Step 8: Respond Tab (~1 screenshot)**
    - Click `tab-respond`
    - Wait for `milkdown-editor-container` to be visible
    - Type some response text into the editor
    - Screenshot showing the respond tab with reference panel
    - Highlight: `milkdown-editor-container`, `respond-reference-panel`

11. **Step 9: Export PDF (~1 screenshot)**
    - Click `export-pdf-btn`
    - Screenshot before/during export dialog (if a dialog appears) or after clicking export
    - Highlight: `export-pdf-btn`

Each step should include narrative text via `guide.note()` explaining what the student is doing and why. Use `highlight` parameter on screenshots to draw attention to relevant UI elements via their `data-testid` selectors.

**Wait strategies:** Follow patterns from `tests/e2e/test_law_student.py`:
- `wait_for_text_walker(page)` before text selection
- `page.get_by_test_id("element").wait_for(state="visible")` before interaction
- `page.wait_for_url()` after navigation
- Brief `page.wait_for_timeout(500)` after dynamic operations if needed

**Testing:**

This is an integration-level guide script. Verification is operational:
- `uv run make-docs` produces `docs/guides/student-workflow.md`
- The markdown file contains ~10 `##` headings
- The markdown file contains ~10 `![` image references
- Screenshots exist in `docs/guides/screenshots/` directory
- Screenshots show element highlights

**Verification:**

Run: `uv run make-docs` (requires running PostgreSQL and pandoc)
Expected: Produces both `docs/guides/instructor-setup.md` and `docs/guides/student-workflow.md` with screenshots

If the full pipeline is not available, verify the import:
Run: `uv run python -c "from promptgrimoire.docs.scripts.student_workflow import run_student_guide; print('OK')"`

**UAT Steps:**
1. [ ] Run: `uv run make-docs`
2. [ ] Open `docs/guides/student-workflow.md` — verify ~10 `##` headings
3. [ ] Verify ~10 `![` image references in the markdown
4. [ ] Open screenshots in `docs/guides/screenshots/` — verify highlight outlines present
5. [ ] Verify screenshots are trimmed (no large white margins)

**Evidence Required:**
- [ ] `uv run make-docs` exits zero
- [ ] Both `instructor-setup.md` and `student-workflow.md` exist with expected content

**Commit:** `feat: migrate student workflow guide to Python DSL`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Delete all remaining bash guide scripts

**Verifies:** docs-platform-208.AC8.2

**Files:**
- Delete: `docs/guides/scripts/generate-student-workflow.sh`
- Delete: `docs/guides/scripts/common.sh`
- Delete: `docs/guides/scripts/debug-instructor.sh`

Note: `generate-instructor-setup.sh` was already deleted in Phase 3.

**Step 1: Delete the bash scripts**

```bash
git rm docs/guides/scripts/generate-student-workflow.sh
git rm docs/guides/scripts/common.sh
git rm docs/guides/scripts/debug-instructor.sh
```

**Step 2: Verify no bash scripts remain**

Run: `ls docs/guides/scripts/`
Expected: Only Python files remain: `__init__.py`, `instructor_setup.py`, `student_workflow.py`

**Step 3: Commit**

```bash
git commit -m "chore: remove all replaced bash guide scripts"
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Verify full pipeline with both guides

**Files:** None (verification only)

**Step 1: Run make-docs**

Run: `uv run make-docs`
Expected: Full pipeline completes. Both guides produce markdown and screenshots.

**Step 2: Inspect output**

Verify:
- `docs/guides/instructor-setup.md` exists with ~7 headings and image references
- `docs/guides/student-workflow.md` exists with ~10 headings and image references
- `docs/guides/screenshots/` contains ~17 PNG files total
- Screenshots are trimmed and show highlights

**Step 3: Run existing tests**

Run: `uv run test-all`
Expected: All existing tests pass

Run: `uv run ruff check .`
Expected: No lint errors

Run: `uvx ty check`
Expected: No type errors
<!-- END_TASK_4 -->
