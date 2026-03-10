# CRUD Management Implementation Plan - Phase 3: Course Detail Page Layout & Button Styling

**Goal:** Adopt `page_layout()` wrapper, create `courses.css`, widen content area, establish consistent button styling, and add `data-testid` to all interactive elements.

**Architecture:** Course detail page adopts the same `page_layout()` + custom CSS pattern as the navigator. Course-specific elements (back arrow, role badge) move from the header into the content area. Settings cog moves to the action bar with a text label. All buttons follow the four-tier styling convention (primary/outline/destructive/flat).

**Tech Stack:** NiceGUI, Quasar (Vue component library), CSS

**Scope:** Phase 3 of 7 from original design

**Codebase verified:** 2026-03-02

**Testing documentation:** `docs/testing.md`, `CLAUDE.md` (data-testid convention)

---

## Acceptance Criteria Coverage

This phase implements and tests:

### crud-management-229.AC7: UI consistency and testability
- **crud-management-229.AC7.1 Success:** Settings cog in action bar labelled "Unit Settings" (not icon-only)
- **crud-management-229.AC7.2 Success:** Activity settings labelled "Activity Settings"
- **crud-management-229.AC7.3 Success:** All action buttons follow styling convention (primary/outline/negative)
- **crud-management-229.AC7.4 Success:** Course detail page uses page_layout() and wider content column
- **crud-management-229.AC7.5 Success:** All interactive elements have data-testid attributes (including previously missing ones)

---

<!-- START_TASK_1 -->
### Task 1: Create courses.css

**Files:**
- Create: `src/promptgrimoire/static/courses.css`

**Implementation:**

Create a CSS file following the navigator.css pattern. The content column uses `width: min(100%, 73rem)` for wider layout:

```css
.courses-content-column {
    width: min(100%, 73rem) !important;
}

.courses-scroll-area {
    height: calc(100vh - var(--q-header-height, 64px));
    overflow-y: auto;
}
```

**Verification:**

Run: file exists and contains expected classes

**Commit:** `feat: add courses.css with content column width`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Adopt page_layout() and restructure course detail page

**Verifies:** crud-management-229.AC7.4

**Files:**
- Modify: `src/promptgrimoire/pages/courses.py:430+` (course_detail_page function)

**Implementation:**

Replace the manual header construction (lines 479-494) with `page_layout()`. The course-specific elements move to content area.

1. Add import: `from promptgrimoire.pages.layout import page_layout`
2. Add import for CSS file path (use `Path(__file__).parent.parent / "static" / "courses.css"` or similar pattern matching navigator)
3. Wrap the page content in `with page_layout(f"{course.code} - {course.name}"):`
4. Add `ui.add_css(_CSS_FILE)` as first statement inside the layout block (matching navigator pattern)
5. Create a scroll container column with `courses-scroll-area` and `courses-content-column` classes (matching navigator pattern)

The header row currently at lines 479-494 (home button, back arrow, title, role badge, settings cog) is replaced by:
- `page_layout()` handles: menu button, title in header bar, user email, logout, nav drawer
- First content row: back arrow + role badge (course-specific navigation)
- The home button is no longer needed (nav drawer provides navigation)
- The settings cog moves to the action bar (Task 3)

**Testing:**

- crud-management-229.AC7.4: Course detail page renders inside `page_layout()` with navigation drawer accessible. Content column uses `courses-content-column` class with `width: min(100%, 73rem)`.

**Verification:**

Run: `uvx ty check`
Expected: No type errors

Run: `uv run test-all`
Expected: No regressions (existing tests should still pass)

**Commit:** `feat: adopt page_layout() for course detail page`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Refactor action bar with consistent button styling

**Verifies:** crud-management-229.AC7.1, crud-management-229.AC7.2, crud-management-229.AC7.3

**Files:**
- Modify: `src/promptgrimoire/pages/courses.py` (action bar section, currently lines 498-506; activity settings, currently lines 554-559)

**Implementation:**

Restructure the action bar (the `if can_manage:` block with Add Week and Manage Enrollments):

1. **"Add Week" button** — keep filled primary: `.props('color=primary data-testid="add-week-btn"')`
2. **"Manage Enrollments" button** — change from `flat` to outline: `.props('outline color=primary data-testid="manage-enrollments-btn"')`
3. **"Unit Settings" button** — move from header (currently icon-only `flat round` cog at line 488-493) to the action bar row. Change to labelled outline button with settings icon:
   ```python
   ui.button(
       "Unit Settings",
       icon="settings",
       on_click=lambda: open_course_settings(course),
   ).props('outline color=primary data-testid="course-settings-btn"')
   ```

4. **Activity settings** — change from icon-only cog (line 554-559) to labelled button:
   ```python
   ui.button(
       "Activity Settings",
       icon="settings",
       on_click=lambda a=act: open_activity_settings(a),
   ).props(
       'outline color=primary dense size=sm '
       f'data-testid="activity-settings-btn-{act.id}"'
   )
   ```
   Note: the `data-testid` should include the activity ID for uniqueness since there's one per activity.

**Button styling convention reference:**

| Button type | Quasar props |
|------------|-------------|
| Primary action (Add Week) | `color=primary` |
| Secondary action (Manage Enrollments, Unit Settings, Activity Settings) | `outline color=primary` |
| Destructive (future: Delete Week, Delete Unit) | `outline color=negative` |
| Cancel/Back | `flat` |

**Visual change note:** "Add Week" currently has no color prop (Quasar default = grey fill). Changing to `color=primary` makes it blue-filled. This is intentional per the design's button hierarchy but is a visible change — verify appearance during visual review.

**Testing:**

- crud-management-229.AC7.1: "Unit Settings" button appears in action bar with text label and settings icon
- crud-management-229.AC7.2: "Activity Settings" button has text label and settings icon
- crud-management-229.AC7.3: Add Week is filled primary, Manage Enrollments and settings buttons are outline primary

**Verification:**

Run: `uvx ty check`
Expected: No type errors

**Commit:** `feat: apply consistent button styling to course action bar`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Add data-testid to all interactive elements

**Verifies:** crud-management-229.AC7.5

**Files:**
- Modify: `src/promptgrimoire/pages/courses.py` (multiple locations)

**Implementation:**

Add `data-testid` attributes to all interactive elements currently missing them. Based on investigation, these elements need `data-testid` added:

1. **Back arrow button** (currently line 483):
   `.props('flat round data-testid="back-btn"')`

2. **Edit Template / Create Template button** (currently lines 549-553):
   `.props(f'flat dense size=sm color=secondary data-testid="template-btn-{act.id}"')`

3. **Resume button** (currently lines 565-569):
   `.props(f'flat dense size=sm color=primary data-testid="resume-btn-{act.id}"')`

4. **Start Activity button** (currently lines 593-595):
   `.props(f'flat dense size=sm color=primary data-testid="start-activity-btn-{act.id}"')`

5. **Cancel button in course settings dialog** (currently line 208):
   `.props('flat data-testid="cancel-course-settings-btn"')`

6. **Cancel button in activity settings dialog** (currently line 253):
   `.props('flat data-testid="cancel-activity-settings-btn"')`

Use activity ID suffix for per-activity elements to ensure uniqueness when multiple activities are displayed.

**Testing:**

- crud-management-229.AC7.5: All interactive elements have `data-testid` attributes. A test can verify this by checking the page HTML for any `<button>` or `<a>` elements without `data-testid`.

**Verification:**

Run: `uvx ty check`
Expected: No type errors

Run: `uv run test-all`
Expected: No regressions

**Commit:** `feat: add data-testid to all course page interactive elements`
<!-- END_TASK_4 -->
