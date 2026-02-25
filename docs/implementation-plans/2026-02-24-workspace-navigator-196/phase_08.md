# Workspace Navigator Implementation Plan — Phase 8: Navigation Chrome & i18n

**Goal:** Add a home icon on the annotation, roleplay, and courses pages to navigate back to `/`, and add a configurable "Unit" label setting for future i18n flexibility.

**Architecture:** Each page gets a home icon button added to its header area (per-page, not via `page_layout`). A new `I18nConfig` sub-model in pydantic-settings provides a configurable `unit_label` defaulting to `"Unit"`. The navigator page uses this label in section headers. Existing pages already hardcode "Unit" correctly — no retrofit needed.

**Tech Stack:** NiceGUI (`ui.button`, `ui.icon`, `ui.navigate.to`), pydantic-settings (`BaseModel`).

**Scope:** Phase 8 of 8

**Codebase verified:** 2026-02-25

---

## Acceptance Criteria Coverage

This phase implements and tests:

### workspace-navigator-196.AC6: Navigation chrome
- **workspace-navigator-196.AC6.1 Success:** Home icon on annotation tab bar navigates to `/`
- **workspace-navigator-196.AC6.2 Success:** Home icon on roleplay and courses pages navigates to `/`
- **workspace-navigator-196.AC6.3 Failure:** No global header bar imposed on annotation page (preserves existing layout)

### workspace-navigator-196.AC7: i18n terminology
- **workspace-navigator-196.AC7.1 Success:** All user-facing text displays "Unit" not "Course"
- **workspace-navigator-196.AC7.2 Success:** Label is configurable via pydantic-settings, defaults to "Unit"

---

## Codebase Context for Executor

**Key files to read before implementing:**
- `src/promptgrimoire/pages/annotation/workspace.py:540-553` — Annotation page tab bar. Tabs defined at line 550 with `ui.tabs()`. Home icon goes before the tabs container.
- `src/promptgrimoire/pages/roleplay.py:169-182` — Roleplay page. Title label at line 182 (`ui.label("SillyTavern Roleplay")`). Home icon goes before or beside the title.
- `src/promptgrimoire/pages/courses.py:298-317` — Courses list page. Title at line 317 (`ui.label("Units")`). Home icon goes before or beside the title.
- `src/promptgrimoire/pages/courses.py:408-462` — Courses detail page. Has back button + title in header row.
- `src/promptgrimoire/config.py:188-215` — `Settings` class. New `I18nConfig` sub-model will be added here.
- `src/promptgrimoire/pages/navigator.py` — Navigator page from Phase 4. Section headers use course names. Will use `unit_label` for the "Shared in {unit_label}: {course_name}" pattern if needed.

**i18n status:** All user-facing text in the codebase already says "Unit" (not "Course"). This was done as a previous codebase-wide rename. AC7.1 is already satisfied. AC7.2 requires adding the configurable setting so it can be changed if needed.

**Home icon pattern:** Use `ui.button(icon='home', on_click=lambda: ui.navigate.to('/')).props('flat round')` for a minimal icon button. Or `ui.icon('home', size='sm').classes('cursor-pointer').on('click', lambda: ui.navigate.to('/'))`.

---

## Tasks

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: Add I18nConfig to pydantic-settings

**Verifies:** workspace-navigator-196.AC7.2

**Files:**
- Modify: `src/promptgrimoire/config.py` (around line 188-215)

**Implementation:**

1. Add a new `I18nConfig` sub-model above the `Settings` class:
   ```python
   class I18nConfig(BaseModel):
       """Internationalisation labels."""
       unit_label: str = "Unit"
   ```

2. Add it to the `Settings` class:
   ```python
   i18n: I18nConfig = I18nConfig()
   ```

3. Environment variable: `I18N__UNIT_LABEL=Course` would override the default.

4. In the navigator page (`navigator.py`), use `get_settings().i18n.unit_label` when rendering section headers that reference the generic concept of a "unit". Specifically:
   - The `shared_in_unit` section display name mapping should read: `f"Shared in {get_settings().i18n.unit_label}: {course_name}"` (or `f"Shared in {course_name}"` if the label would be redundant with the course name).
   - Any "no results" or empty-state messages that would say "Unit" should use the configurable label.
   - This ensures AC7.2 is satisfied — the label is not just defined but actually consumed in rendering.

**Verification:**
Run: `uv run test-changed`
Manual: Verify `get_settings().i18n.unit_label` returns `"Unit"` by default.

**Commit:** `feat: add configurable unit_label to i18n settings`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add home icon to annotation page

**Verifies:** workspace-navigator-196.AC6.1, workspace-navigator-196.AC6.3

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/workspace.py` (around line 550)

**Implementation:**

Add a home icon button before the `ui.tabs()` at line 550. The icon should be visually minimal (flat, round) and navigate to `/` on click.

1. Insert a row or inline element before the tabs:
   ```python
   with ui.row().classes('w-full items-center'):
       ui.button(icon='home', on_click=lambda: ui.navigate.to('/')).props('flat round').tooltip('Home')
       with ui.tabs().classes("w-full") as tabs:
           ui.tab("Annotate")
           ui.tab("Organise")
           ui.tab("Respond")
   ```

2. **Preserve existing layout (AC6.3):** Do NOT add a global header bar. The home icon is a small button alongside the existing tabs, not a new header. The annotation page's existing layout structure must not change.

3. The icon should be unobtrusive — small, flat, doesn't take up significant space.

**Verification:**
Manual: Open annotation page. See home icon left of tabs. Click it — navigates to `/`. Verify no global header bar was added. Verify tabs still work normally.
Run: `uv run test-changed`

**Commit:** `feat: add home icon to annotation page tab bar`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add home icon to roleplay and courses pages

**Verifies:** workspace-navigator-196.AC6.2

**Files:**
- Modify: `src/promptgrimoire/pages/roleplay.py` (around line 182)
- Modify: `src/promptgrimoire/pages/courses.py` (around line 317, and detail pages)

**Implementation:**

1. **Roleplay page** (`roleplay.py:182`): Add home icon button before or beside the title label:
   ```python
   with ui.row().classes('items-center mb-4'):
       ui.button(icon='home', on_click=lambda: ui.navigate.to('/')).props('flat round').tooltip('Home')
       ui.label("SillyTavern Roleplay").classes("text-h4")
   ```

2. **Courses list page** (`courses.py:317`): Add home icon button beside the "Units" title:
   ```python
   with ui.row().classes('items-center mb-4'):
       ui.button(icon='home', on_click=lambda: ui.navigate.to('/')).props('flat round').tooltip('Home')
       ui.label("Units").classes("text-2xl font-bold")
   ```

3. **Courses detail pages:** The detail page (`courses.py:457-462`) already has a back button in its header row. Adding a home icon beside the back button (or relying on the back button for navigation) is sufficient. Add the home icon to the detail page header row if not already navigable to `/`.

**Verification:**
Manual: Navigate to roleplay page — see home icon, click to go to `/`. Navigate to courses list page — same. Navigate to course detail page — same.
Run: `uv run test-changed`

**Commit:** `feat: add home icon to roleplay and courses pages`
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 4-5) -->
<!-- START_TASK_4 -->
### Task 4: E2E test — home icon navigates to navigator

**Verifies:** workspace-navigator-196.AC6.1, workspace-navigator-196.AC6.2, workspace-navigator-196.AC6.3

**Files:**
- Modify: `tests/e2e/test_navigator.py` (or create `tests/e2e/test_navigation_chrome.py`)

**Implementation:**

E2E tests for home icon navigation using Playwright:

- AC6.1: Navigate to annotation page (with a workspace). Locate the home icon button. Click it. Verify URL changes to `/`. Verify navigator page loads.

- AC6.2: Navigate to `/roleplay`. Locate home icon. Click. Verify navigation to `/`. Repeat for `/courses`.

- AC6.3: Navigate to annotation page. Verify NO global header bar exists (no `q-header` element outside the page's own structure, or verify the annotation page layout is unchanged). Verify the home icon is a small button, not a header bar.

**Verification:**
Run: `uv run test-e2e -k test_nav`

**Commit:** `test: add E2E tests for home icon navigation chrome`
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: E2E test — i18n unit label

**Verifies:** workspace-navigator-196.AC7.1, workspace-navigator-196.AC7.2

**Files:**
- Modify: `tests/e2e/test_navigator.py`

**Implementation:**

E2E tests for i18n terminology:

- AC7.1: Navigate to `/`. Verify no text contains "Course" (search page text content). Verify section headers use "Unit" or course-specific names (e.g., "Shared in ARTS1234").

- AC7.2: This is best verified as an integration test rather than E2E (environment variable override). Create an integration test that verifies `get_settings().i18n.unit_label` returns `"Unit"` by default. Optionally, test that overriding `I18N__UNIT_LABEL` changes the value.

**Verification:**
Run: `uv run test-e2e -k test_navigator`
Run: `uv run test-changed` (for integration test)

**Commit:** `test: add tests for i18n unit label configuration`
<!-- END_TASK_5 -->
<!-- END_SUBCOMPONENT_B -->

---

## Next Phase

This is the final phase. After completing Phase 8, the workspace navigator feature is fully implemented across all 8 phases.
