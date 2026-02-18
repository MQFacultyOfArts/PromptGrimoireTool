# Showboat E2E Demo Documents Implementation Plan

**Goal:** Instrument all five persona tests with Showboat narrative calls to produce stakeholder-readable demo documents.

**Architecture:** Each persona test file calls `showboat_init()` at the start, then `showboat_note()` and `showboat_screenshot()` at key subtest checkpoints. For multi-method test classes (naughty student, translation student), `showboat_init` is idempotent — first method to execute creates the document, subsequent methods append. Screenshots are selective: key visual moments only, not every subtest.

**Tech Stack:** showboat_helpers (Phase 1), Playwright sync API (page.screenshot)

**Scope:** 3 phases from original design (phase 3 of 3)

**Codebase verified:** 2026-02-17

---

## Acceptance Criteria Coverage

This phase implements and tests:

### showboat-e2e-demos.AC3: Persona tests produce stakeholder-readable documents
- **showboat-e2e-demos.AC3.1 Success:** Each of the five persona tests produces its own Showboat document
- **showboat-e2e-demos.AC3.2 Success:** Documents contain narrative notes describing what the persona does
- **showboat-e2e-demos.AC3.3 Success:** Documents contain screenshots at key visual moments
- **showboat-e2e-demos.AC3.4 Quality:** Documents are readable standalone — a stakeholder unfamiliar with the codebase can follow the story

### showboat-e2e-demos.AC1: Showboat helper module works with graceful degradation
- **showboat-e2e-demos.AC1.3 Success:** `showboat_screenshot()` captures a Playwright screenshot and appends it as a Showboat image (end-to-end verification via actual E2E test runs)

---

<!-- START_TASK_1 -->
### Task 1: Make showboat_init idempotent

**Files:**
- Modify: `tests/e2e/showboat_helpers.py`

**Implementation:**

Modify `showboat_init()` to check if the target `.md` file already exists. If it does, return the existing path without re-initializing. This supports multi-method persona tests (naughty student has 4 methods, translation student has 4 methods) where each method independently calls `showboat_init` — the first to execute creates the document, subsequent methods get the existing path and append via note/screenshot.

Add before the `subprocess.run` call:
```python
if target.exists():
    return target
```

**Verification:**

Run: `uv run pytest tests/unit/test_showboat_helpers.py -v`
Expected: All existing tests still pass. The idempotency doesn't affect existing tests since they use `tmp_path` fixtures.

**Commit:**

```bash
git add tests/e2e/showboat_helpers.py
git commit -m "feat: make showboat_init idempotent for multi-method test classes"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Instrument test_naughty_student.py

**Verifies:** showboat-e2e-demos.AC3.1, showboat-e2e-demos.AC3.2, showboat-e2e-demos.AC3.3, showboat-e2e-demos.AC3.4

**Files:**
- Modify: `tests/e2e/test_naughty_student.py`

**Implementation:**

Add import at top:
```python
from tests.e2e.showboat_helpers import showboat_init, showboat_note, showboat_screenshot
```

Slug: `"naughty-student"`, Title: `"Naughty Student: Adversarial Behaviour"`

Each of the 4 test methods calls `showboat_init("naughty-student", "Naughty Student: Adversarial Behaviour")` at the start (idempotent — only first method creates the file).

**Method: `test_dead_end_navigation`** (3 subtests)
- After auth: `showboat_note(doc, "## Dead-End Navigation\n\nAn adversarial student attempts to access annotation workspaces with invalid, nonexistent, and missing workspace IDs.")`
- After `invalid_workspace_id` subtest: `showboat_screenshot(doc, page, "Invalid UUID: page shows 'No workspace selected' fallback")`
- After `no_workspace_id` subtest: `showboat_screenshot(doc, page, "No workspace ID: page shows workspace creation UI")`

**Method: `test_xss_injection_sanitised`** (2 subtests)
- After auth: `showboat_note(doc, "## XSS Injection Sanitisation\n\nThe student pastes script tags and event handlers as content. The input pipeline must sanitise them.")`
- After `script_tag_stripped` subtest: `showboat_screenshot(doc, page, "Script tag pasted: content renders safely, no JS alert fired")`
- After `html_injection_escaped` subtest: `showboat_screenshot(doc, page, "IMG onerror injection: content renders safely")`

**Method: `test_blns_content_resilience`** (dynamic subtests)
- After auth: `showboat_note(doc, "## BLNS Content Resilience\n\nThe student pastes Big List of Naughty Strings content. The system must not crash.")`
- After the BLNS loop completes (before blns_highlight_resilience): `showboat_screenshot(doc, page, "BLNS strings processed: page still functional")`
- After `blns_highlight_resilience` subtest (if not skipped): `showboat_screenshot(doc, page, "BLNS highlight resilience: annotation created on naughty content")`

**Method: `test_copy_protection_bypass`** (7 subtests)
- After instructor_setup subtest: `showboat_note(doc, "## Copy Protection Bypass\n\nAn instructor creates a copy-protected course. A student attempts to bypass copy, cut, context menu, and print restrictions.")`
- After `student_clones_workspace` subtest: `showboat_screenshot(doc, student_page, "Student's cloned workspace with protected content visible")`
- After `copy_blocked` subtest: `showboat_screenshot(doc, student_page, "Copy attempt blocked: toast notification 'Copying is disabled'")`
- After `print_blocked` subtest: `showboat_screenshot(doc, student_page, "Print attempt blocked: toast notification shown")`
- After `protected_indicator_visible` subtest: `showboat_screenshot(doc, student_page, "Protected indicator: lock icon chip visible in header")`

**Intentionally omitted subtests:** `nonexistent_workspace_id` (visually identical to `invalid_workspace_id`), `cut_blocked` and `context_menu_blocked` (toast identical to `copy_blocked` — same "Copying is disabled" message).

**Testing:**
- AC3.1: Verified by running `uv run test-e2e -k test_naughty_student` and checking `output/showboat/naughty-student.md` exists
- AC3.2-3.4: Manual inspection of the generated document

**Verification:**

Run: `uv run test-e2e -k test_naughty_student`
Expected: Tests pass. If showboat installed, `output/showboat/naughty-student.md` contains notes and image references.

**Commit:**

```bash
git add tests/e2e/test_naughty_student.py
git commit -m "feat: instrument naughty student test with showboat narratives"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Instrument test_translation_student.py

**Verifies:** showboat-e2e-demos.AC3.1, showboat-e2e-demos.AC3.2, showboat-e2e-demos.AC3.3, showboat-e2e-demos.AC3.4

**Files:**
- Modify: `tests/e2e/test_translation_student.py`

**Implementation:**

Add import at top:
```python
from tests.e2e.showboat_helpers import showboat_init, showboat_note, showboat_screenshot
```

Slug: `"translation-student"`, Title: `"Translation Student: Multilingual Annotation"`

Each of the 4 test methods calls `showboat_init(...)` at the start (idempotent).

**Method: `test_cjk_annotation_workflow`** (4 subtests)
- After auth: `showboat_note(doc, "## CJK Annotation\n\nThe translation student pastes Chinese, Japanese, and Korean source text and creates highlights.")`
- After `authenticate_and_create_workspace`: `showboat_screenshot(doc, page, "Chinese text rendered in annotation workspace")`
- After `highlight_chinese_text`: `showboat_screenshot(doc, page, "Chinese text highlighted with annotation card visible")`
- After `add_korean_content`: `showboat_screenshot(doc, page, "Korean content highlighted")`

**Method: `test_rtl_annotation_workflow`** (2 subtests)
- Note: `"## RTL Content\n\nThe student annotates Arabic and Hebrew right-to-left text."`
- After `arabic_content`: `showboat_screenshot(doc, page, "Arabic RTL text rendered and highlighted")`
- After `hebrew_content`: `showboat_screenshot(doc, page, "Hebrew RTL text rendered and highlighted")`

**Method: `test_mixed_script_annotation`** (3 subtests)
- Note: `"## Mixed Script\n\nThe student works with a document containing Latin, CJK, and Arabic scripts together."`
- After `paste_mixed_content`: `showboat_screenshot(doc, page, "Mixed-script content rendered: Latin, CJK, Arabic")`
- After `highlight_across_scripts`: `showboat_screenshot(doc, page, "Cross-script highlight with annotation card")`

**Method: `test_i18n_pdf_export`** (3 subtests)
- Note: `"## i18n PDF Export\n\nThe student exports a Chinese Wikipedia fixture annotation to PDF with CJK characters."`
- After `paste_cjk_fixture`: `showboat_screenshot(doc, page, "Chinese Wikipedia fixture rendered in workspace")`
- After `highlight_and_comment`: `showboat_screenshot(doc, page, "CJK content highlighted with UUID comment")`

**Intentionally omitted subtests:** `add_japanese_content` (visually similar to Korean highlight), `add_comment_with_uuid` in mixed-script (no visual change worth capturing), `export_pdf` in i18n PDF (result is a file download, not a page visual).

**Verification:**

Run: `uv run test-e2e -k test_translation_student`
Expected: Tests pass. If showboat installed, `output/showboat/translation-student.md` exists with notes and images.

**Commit:**

```bash
git add tests/e2e/test_translation_student.py
git commit -m "feat: instrument translation student test with showboat narratives"
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Instrument test_history_tutorial.py

**Verifies:** showboat-e2e-demos.AC3.1, showboat-e2e-demos.AC3.2, showboat-e2e-demos.AC3.3, showboat-e2e-demos.AC3.4

**Files:**
- Modify: `tests/e2e/test_history_tutorial.py`

**Implementation:**

Add import at top:
```python
from tests.e2e.showboat_helpers import showboat_init, showboat_note, showboat_screenshot
```

Slug: `"history-tutorial"`, Title: `"History Tutorial: Collaborative Annotation"`

**Special consideration:** This test uses the `two_authenticated_contexts` fixture which provides `(page1, page2, workspace_id, user1_email, user2_email)`. It does NOT create its own browser context. Screenshots alternate between page1 (Student A) and page2 (Student B) to show both perspectives of the sync.

**Method: `test_bidirectional_sync_workflow`** (11 subtests)
- Before subtests: `showboat_note(doc, "Two history students collaborate in real-time on a shared annotation workspace. Student A and Student B each have their own browser, connected to the same document.")`
- After `student_a_highlights_text`: `showboat_screenshot(doc, page1, "Student A creates first highlight — annotation card appears")`
- After `highlight_syncs_to_student_b`: `showboat_screenshot(doc, page2, "Student B's view: highlight synced from Student A")`
- After `second_highlight_syncs_to_student_a`: `showboat_screenshot(doc, page1, "Student A's view: both highlights visible (A's and B's)")`
- After `student_a_adds_comment`: `showboat_note(doc, "Student A adds a comment to the first highlight.")`
- After `comment_syncs_to_student_b`: `showboat_screenshot(doc, page2, "Student B sees A's comment synced to their view")`
- After `tag_change_syncs_to_student_b`: `showboat_screenshot(doc, page2, "Tag change synced: 'Procedural History' visible on Student B")`
- After `concurrent_highlights`: `showboat_screenshot(doc, page1, "Concurrent highlights resolved: 4 annotation cards visible")`
- After `user_count_shows_two`: `showboat_note(doc, "Both students see user count of 2.")`
- After `student_b_leaves` (AFTER page2.context.close()): `showboat_screenshot(doc, page1, "Student B departed: user count drops to 1")`

**Note:** The `showboat_screenshot` call after `student_b_leaves` MUST use `page1` since `page2` is closed at that point.

**Intentionally omitted subtests:** `student_b_highlights_text` (the sync result is captured in `second_highlight_syncs_to_student_a`), `student_a_changes_tag` (the sync result is captured in `tag_change_syncs_to_student_b`).

**Verification:**

Run: `uv run test-e2e -k test_history_tutorial`
Expected: Tests pass. If showboat installed, `output/showboat/history-tutorial.md` exists with notes and screenshots from both perspectives.

**Commit:**

```bash
git add tests/e2e/test_history_tutorial.py
git commit -m "feat: instrument history tutorial test with showboat narratives"
```
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Instrument test_law_student.py

**Verifies:** showboat-e2e-demos.AC3.1, showboat-e2e-demos.AC3.2, showboat-e2e-demos.AC3.3, showboat-e2e-demos.AC3.4

**Files:**
- Modify: `tests/e2e/test_law_student.py`

**Implementation:**

Add import at top:
```python
from tests.e2e.showboat_helpers import showboat_init, showboat_note, showboat_screenshot
```

Slug: `"law-student"`, Title: `"Law Student: AustLII Case Annotation"`

**Method: `test_austlii_annotation_workflow`** (11 subtests)
- After auth: `showboat_note(doc, "A law student annotates the Lawlis v R case judgment from AustLII, using legal-specific tags (Jurisdiction, Procedural History, Legal Issues, Reasons).")`
- After `authenticate_and_paste_fixture`: `showboat_screenshot(doc, page, "AustLII case judgment rendered in annotation workspace")`
- After `highlight_with_legal_tag`: `showboat_screenshot(doc, page, "First legal highlight (Jurisdiction tag) with annotation card")`
- After `add_comment_with_uuid`: `showboat_note(doc, "Student adds a comment to the Jurisdiction highlight.")`
- After `highlight_with_different_tag`: `showboat_screenshot(doc, page, "Second highlight with Legal Issues tag")`
- After `change_tag_via_dropdown`: `showboat_screenshot(doc, page, "Tag changed via dropdown to Procedural History")`
- After `keyboard_shortcut_tag`: `showboat_note(doc, "Third highlight created using keyboard shortcut '5' for Reasons tag.")`
- After `organise_tab`: `showboat_screenshot(doc, page, "Organise tab: highlights grouped by legal tag")`
- After `respond_tab`: `showboat_screenshot(doc, page, "Respond tab: Milkdown editor visible")`
- After `reload_persistence`: `showboat_screenshot(doc, page, "After page reload: all annotations and comments persist")`
- After `export_pdf_with_annotations`: `showboat_note(doc, "PDF exported successfully with both UUID comments found in the document.")`

**Verification:**

Run: `uv run test-e2e -k test_law_student`
Expected: Tests pass. If showboat installed, `output/showboat/law-student.md` exists.

**Commit:**

```bash
git add tests/e2e/test_law_student.py
git commit -m "feat: instrument law student test with showboat narratives"
```
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Instrument test_instructor_workflow.py

**Verifies:** showboat-e2e-demos.AC3.1, showboat-e2e-demos.AC3.2, showboat-e2e-demos.AC3.3, showboat-e2e-demos.AC3.4

**Files:**
- Modify: `tests/e2e/test_instructor_workflow.py`

**Implementation:**

Add import at top:
```python
from tests.e2e.showboat_helpers import showboat_init, showboat_note, showboat_screenshot
```

Slug: `"instructor-workflow"`, Title: `"Instructor Workflow: Course Setup & Student Delivery"`

**Method: `test_full_course_setup`** (9 subtests)
- After auth: `showboat_note(doc, "An instructor sets up a course from scratch: creates the course, configures weeks and activities, fills the template workspace, enables copy protection, publishes, and enrols a student.")`
- After `authenticate_as_instructor`: `showboat_note(doc, "Instructor authenticated.")`
- After `create_course`: `showboat_screenshot(doc, page, "Course created with unique code")`
- After `create_activity`: `showboat_screenshot(doc, page, "Week and activity added to course")`
- After `configure_copy_protection`: `showboat_screenshot(doc, page, "Copy protection enabled for the course")`
- After `edit_template_workspace`: `showboat_screenshot(doc, page, "Template workspace filled with 'Becky Bennett' content")`
- After `publish_week`: `showboat_screenshot(doc, page, "Week published — Unpublish button visible")`
- After `enrol_student`: `showboat_note(doc, "Student enrolled in the course.")`
- After `student_clones_and_sees_content`: `showboat_note(doc, "Student logged in, cloned the template workspace, and sees the Becky Bennett content — copy protection active.")`

**Note:** The `student_clones_and_sees_content` subtest calls a helper function that creates its own browser context internally. A screenshot would require accessing the student page object inside that function. If the helper function doesn't expose the page, add a showboat_note instead. The task-implementor should check whether `_student_clones_and_sees_content` can be modified to accept a doc parameter, or whether a note suffices.

**Verification:**

Run: `uv run test-e2e -k test_instructor_workflow`
Expected: Tests pass. If showboat installed, `output/showboat/instructor-workflow.md` exists.

**Commit:**

```bash
git add tests/e2e/test_instructor_workflow.py
git commit -m "feat: instrument instructor workflow test with showboat narratives"
```
<!-- END_TASK_6 -->

## UAT Steps

1. [ ] Run `uv run test-e2e` — all E2E tests pass (showboat calls are no-ops if absent, so tests must not break)
2. [ ] Verify 5 showboat documents exist: `ls output/showboat/*.md` — expect `naughty-student.md`, `translation-student.md`, `history-tutorial.md`, `law-student.md`, `instructor-workflow.md`
3. [ ] Open `output/showboat/naughty-student.md` — verify it contains section headings (## Dead-End Navigation, ## XSS Injection, etc.) and image references
4. [ ] Open `output/showboat/history-tutorial.md` — verify screenshots alternate between Student A and Student B perspectives
5. [ ] Open `output/showboat/law-student.md` — verify narrative reads coherently as a standalone document (AC3.4: stakeholder-readable)
6. [ ] Verify no test execution time regression: showboat calls should add <1s per test method
