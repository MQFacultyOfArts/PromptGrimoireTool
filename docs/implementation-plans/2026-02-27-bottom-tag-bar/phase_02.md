# Bottom-Anchored Tag Bar Implementation Plan — Phase 2

**Goal:** Remove redundant inline page chrome — the "Annotation Workspace" heading and workspace UUID label.

**Architecture:** Delete two UI elements that duplicate information already in the navigator bar and URL. Update one E2E test that references the removed heading.

**Tech Stack:** NiceGUI (Python), Playwright (E2E test update)

**Scope:** 5 phases from original design (phase 2 of 5)

**Codebase verified:** 2026-02-27

---

## Acceptance Criteria Coverage

This phase implements and tests:

### bottom-tag-bar.AC2: Inline title and UUID removed
- **bottom-tag-bar.AC2.1 Success:** No `text-2xl` "Annotation Workspace" label visible in page content area
- **bottom-tag-bar.AC2.2 Success:** No workspace UUID text visible on the page; navigator bar shows "Annotation Workspace" as page title
- **bottom-tag-bar.AC2.3 Edge:** Header row (save status, user count, export, sharing) still renders correctly without the title above it

---

## Reference Files

The executor should read these for project context:
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/bottom-tag-bar/CLAUDE.md` — Project conventions
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/bottom-tag-bar/docs/annotation-architecture.md` — Annotation page package structure

---

<!-- START_TASK_1 -->
### Task 1: Remove inline title and UUID label

**Verifies:** bottom-tag-bar.AC2.1, bottom-tag-bar.AC2.2, bottom-tag-bar.AC2.3

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/__init__.py:306` (remove title label)
- Modify: `src/promptgrimoire/pages/annotation/workspace.py:531` (remove UUID label)

**Implementation:**

**File 1: `src/promptgrimoire/pages/annotation/__init__.py`**

At line 306, remove the title label line:

```python
# BEFORE (lines 305-308):
    with ui.column().classes("w-full p-4"):
        ui.label("Annotation Workspace").classes("text-2xl font-bold mb-4")

        if workspace_id:

# AFTER (lines 305-307):
    with ui.column().classes("w-full p-4"):
        if workspace_id:
```

The `with ui.column().classes("w-full p-4")` wrapper stays — it wraps the workspace content below (lines 308-318). Only the label on line 306 is removed.

The navigator title is already set via `@page_route(title="Annotation Workspace")` at lines 278-285, so no information is lost.

**File 2: `src/promptgrimoire/pages/annotation/workspace.py`**

At line 531, remove the UUID label:

```python
# BEFORE (lines 531-532):
    ui.label(f"Workspace: {workspace_id}").classes("text-gray-600 text-sm")
    await render_workspace_header(

# AFTER (line 531):
    await render_workspace_header(
```

The workspace ID is visible in the URL (`/annotation?workspace=<uuid>`), so no information is lost.

**Verification:**

Run: `uv run ruff check src/promptgrimoire/pages/annotation/__init__.py src/promptgrimoire/pages/annotation/workspace.py`
Expected: No lint errors

Run: `uvx ty check`
Expected: No type errors

**UAT Steps:**
1. [ ] Start the app: `uv run python -m promptgrimoire`
2. [ ] Navigate to: an annotation workspace with content
3. [ ] Verify: no "Annotation Workspace" heading appears in the page content area (navigator drawer title is fine)
4. [ ] Verify: no "Workspace: <uuid>" text visible on the page
5. [ ] Verify: the header row (save status indicator, user count badge, export button, sharing controls) is visible and correctly positioned — not misaligned or missing after the title removal (AC2.3)

**Commit:** `feat: remove redundant inline title and workspace UUID label`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Update E2E test crash-detection assertion

**Verifies:** None (test maintenance — prevents Phase 2 from breaking the test suite)

**Files:**
- Modify: `tests/e2e/test_naughty_student.py:293-294` (update selector)

**Implementation:**

At lines 293-294, the test checks that the page didn't crash by looking for visible text:

```python
# BEFORE:
                        heading = page.get_by_text("Annotation Workspace").first
                        expect(heading).to_be_visible(timeout=5000)

# AFTER:
                        tab_label = page.get_by_text("Annotate").first
                        expect(tab_label).to_be_visible(timeout=5000)
```

The "Annotate" tab label is created by `ui.tab("Annotate")` at `workspace.py:551` (inside the three-tab container). This text is always visible when the annotation page renders successfully. Confirmed: the exact string is `"Annotate"` (not an icon or aria-label).

**Verification:**

Run: `uv run test-e2e -k test_naughty_student`
Expected: Test passes (this test takes a while — it injects many naughty strings)

**UAT Steps:**
1. [ ] Run: `uv run test-e2e -k test_naughty_student`
2. [ ] Verify: test passes (crash-detection assertion finds "Annotate" tab label)

**Commit:** `test: update crash-detection selector after title removal`
<!-- END_TASK_2 -->
