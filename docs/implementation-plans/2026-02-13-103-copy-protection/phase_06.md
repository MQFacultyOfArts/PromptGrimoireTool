# Per-Activity Copy Protection Implementation Plan — Phase 6

**Goal:** Toggle controls for copy protection on course and activity settings, plus seed data updates.

**Architecture:** Course settings dialog (opened via gear icon on course detail page) with `ui.switch` for `default_copy_protection`. Per-activity settings dialog with `ui.select` for tri-state copy protection (Inherit/On/Off). New `update_course()` CRUD function in `db/courses.py`. Seed data optionally sets copy protection on seed activities.

**Tech Stack:** NiceGUI (ui.switch, ui.select, ui.dialog), SQLModel, Python 3.14

**Scope:** Phase 6 of 6 from original design

**Codebase verified:** 2026-02-13

---

## Acceptance Criteria Coverage

This phase implements and tests:

### 103-copy-protection.AC7: Instructor UI
- **103-copy-protection.AC7.1 Success:** Course settings shows "Default copy protection" toggle
- **103-copy-protection.AC7.2 Success:** Activity settings shows tri-state "Copy protection" control: Inherit from course / On / Off
- **103-copy-protection.AC7.3 Success:** New activities default to "Inherit from course" state
- **103-copy-protection.AC7.4 Success:** Per-activity explicit On/Off overrides course default
- **103-copy-protection.AC7.5 Success:** Resetting activity to "Inherit" clears override (sets `copy_protection=NULL`)

---

## Reference Files

The executor should read these files for context:

- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/103-copy-protection/src/promptgrimoire/pages/courses.py` — Course detail page (line 218), `_render_activity_row()` (line 294), create activity page (line 494)
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/103-copy-protection/src/promptgrimoire/pages/dialogs.py` — Awaitable dialog pattern (lines 10-70)
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/103-copy-protection/src/promptgrimoire/db/courses.py` — Course CRUD (no update_course yet)
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/103-copy-protection/src/promptgrimoire/db/activities.py` — `update_activity()` Ellipsis sentinel pattern (line 74)
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/103-copy-protection/src/promptgrimoire/cli.py` — `seed_data()` (line 387)

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Create update_course() CRUD function

**Verifies:** None (infrastructure — prerequisite for UI)

**Files:**
- Modify: `src/promptgrimoire/db/courses.py` (add `update_course()`)
- Test: `tests/integration/test_course_service.py` (integration — verify update round-trip)

**Implementation:**

Add `update_course()` to `db/courses.py` following the `update_activity()` Ellipsis sentinel pattern:

```python
async def update_course(
    course_id: UUID,
    name: str | None = None,
    default_copy_protection: bool = ...,  # type: ignore[assignment]  -- Ellipsis sentinel
) -> Course | None:
    """Update a course's mutable fields.

    Uses Ellipsis sentinel to distinguish 'not provided' from explicit values.
    Pass default_copy_protection=True/False to change, or omit to leave unchanged.
    """
    async with get_session() as session:
        course = await session.get(Course, course_id)
        if course is None:
            return None
        if name is not None:
            course.name = name
        if default_copy_protection is not ...:
            course.default_copy_protection = default_copy_protection
        session.add(course)
        await session.flush()
        await session.refresh(course)
        return course
```

**Testing:**

Integration tests following `test_activity_crud.py` patterns:
- Update `default_copy_protection` from False to True — verify round-trip
- Update `default_copy_protection` from True to False — verify round-trip
- Update with only `name` (omit `default_copy_protection`) — verify field unchanged
- Update nonexistent course — returns None

**Verification:**

Run:
```bash
uv run pytest tests/integration/ -k "course" -v
```

Expected: All tests pass.

**Commit:**

```bash
git add src/promptgrimoire/db/courses.py tests/integration/test_course_service.py
git commit -m "feat: add update_course() CRUD function with Ellipsis sentinel pattern"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Course settings dialog with copy protection toggle

**Verifies:** 103-copy-protection.AC7.1

**Files:**
- Modify: `src/promptgrimoire/pages/courses.py` (add settings dialog + gear icon button on course detail page)

**Implementation:**

1. Add a settings gear icon button to the course detail page header (around line 280-289, alongside existing course info):

```python
ui.button(icon="settings", on_click=lambda: open_course_settings(course)).props("flat round")
```

2. Create `open_course_settings()` async function following the dialog pattern from `dialogs.py`:

```python
async def open_course_settings(course: Course) -> None:
    with ui.dialog() as dialog, ui.card().classes("w-96"):
        ui.label("Course Settings").classes("text-lg font-bold")

        switch = ui.switch(
            "Default copy protection",
            value=course.default_copy_protection,
        )

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancel", on_click=lambda: dialog.close()).props("flat")

            async def save():
                await update_course(course.id, default_copy_protection=switch.value)
                course.default_copy_protection = switch.value
                dialog.close()
                ui.notify("Course settings saved", type="positive")

            ui.button("Save", on_click=save).props("color=primary")

    dialog.open()
```

Import `update_course` from `promptgrimoire.db.courses`.

**Testing:**

This is a UI component — functional testing requires E2E. Unit tests can verify the dialog function signature and that `update_course()` is called with expected parameters (mock-based).

**Verification:**

Run:
```bash
uv run test-all
```

Expected: All tests pass.

**Commit:**

```bash
git add src/promptgrimoire/pages/courses.py
git commit -m "feat: add course settings dialog with copy protection toggle"
```
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: Per-activity copy protection tri-state control

**Verifies:** 103-copy-protection.AC7.2, AC7.3, AC7.4, AC7.5

**Files:**
- Modify: `src/promptgrimoire/pages/courses.py` (add activity settings button + dialog with tri-state select)
- Test: `tests/unit/test_copy_protection_ui.py` (unit — pure mapping function tests)

**Implementation:**

1. Add a "Settings" icon button to `_render_activity_row()` (around line 310, alongside existing buttons):

```python
ui.button(icon="tune", on_click=lambda a=activity: open_activity_settings(a)).props(
    "flat round dense size=sm"
).tooltip("Activity settings")
```

2. Create `open_activity_settings()` async function:

```python
# Map model values to UI labels
_COPY_PROTECTION_OPTIONS = {
    "inherit": "Inherit from course",
    "on": "On",
    "off": "Off",
}

def _model_to_ui(value: bool | None) -> str:
    if value is None:
        return "inherit"
    return "on" if value else "off"

def _ui_to_model(value: str) -> bool | None:
    if value == "inherit":
        return None
    return value == "on"


async def open_activity_settings(activity: Activity) -> None:
    with ui.dialog() as dialog, ui.card().classes("w-96"):
        ui.label("Activity Settings").classes("text-lg font-bold")

        select = ui.select(
            options=_COPY_PROTECTION_OPTIONS,
            value=_model_to_ui(activity.copy_protection),
            label="Copy protection",
        ).classes("w-full")

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancel", on_click=lambda: dialog.close()).props("flat")

            async def save():
                new_value = _ui_to_model(select.value)
                await update_activity(activity.id, copy_protection=new_value)
                activity.copy_protection = new_value
                dialog.close()
                ui.notify("Activity settings saved", type="positive")

            ui.button("Save", on_click=save).props("color=primary")

    dialog.open()
```

Import `update_activity` from `promptgrimoire.db.activities`.

**Testing:**

Unit tests for the pure mapping functions:
- `_model_to_ui(None)` returns `"inherit"`
- `_model_to_ui(True)` returns `"on"`
- `_model_to_ui(False)` returns `"off"`
- `_ui_to_model("inherit")` returns `None`
- `_ui_to_model("on")` returns `True`
- `_ui_to_model("off")` returns `False`

AC verification:
- AC7.3: New activity has `copy_protection=None` → UI shows "Inherit from course" by default
- AC7.4: Setting to "On" calls `update_activity(id, copy_protection=True)`
- AC7.5: Setting back to "Inherit" calls `update_activity(id, copy_protection=None)` — clears override

**Verification:**

Run:
```bash
uv run test-all
```

Expected: All tests pass.

**Commit:**

```bash
git add src/promptgrimoire/pages/courses.py tests/unit/test_copy_protection_ui.py
git commit -m "feat: add per-activity tri-state copy protection control"
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Update seed data with copy protection

**Verifies:** None (development convenience)

**Files:**
- Modify: `src/promptgrimoire/cli.py:387-422` (`seed_data()` — optionally enable copy protection)

**Implementation:**

Update the `create_activity()` call in `seed_data()` to enable copy protection on the seed activity:

```python
activity = await create_activity(
    week_id=week1.id,
    title="Annotate Becky Bennett Interview",
    description=desc,
    copy_protection=True,
)
```

Also update the course to enable the default:

```python
await update_course(course.id, default_copy_protection=True)
```

Import `update_course` from `promptgrimoire.db.courses`.

This allows testing copy protection immediately after seeding without manual configuration.

**Verification:**

Run:
```bash
uv run seed-data
```

Expected: Seed completes successfully. Verify by checking the database or loading the annotation page.

**Commit:**

```bash
git add src/promptgrimoire/cli.py
git commit -m "chore: enable copy protection in seed data for development testing"
```

**UAT Steps (end of Phase 6):**

1. [ ] Verify tests: `uv run test-all` — all pass
2. [ ] Start the app: `uv run python -m promptgrimoire`
3. [ ] Seed data: `uv run seed-data`
4. [ ] Navigate to course detail page:
   - [ ] Click gear icon — course settings dialog opens
   - [ ] Verify "Default copy protection" toggle is visible and reflects current state
   - [ ] Toggle it on, click Save — verify notification shown
   - [ ] Reload page — verify toggle state persisted
5. [ ] Navigate to activity row on course page:
   - [ ] Click tune icon — activity settings dialog opens
   - [ ] Verify "Copy protection" select shows tri-state: Inherit from course / On / Off
   - [ ] New activity shows "Inherit from course" by default (AC7.3)
   - [ ] Set to "On", click Save — verify notification shown (AC7.4)
   - [ ] Set back to "Inherit from course", click Save — verify it clears override (AC7.5)
6. [ ] Navigate to annotation page for the activity with copy protection on:
   - [ ] Verify lock chip visible, copy protection active

**Evidence Required:**
- [ ] Test output showing all tests green
- [ ] Screenshot of course settings dialog with copy protection toggle
- [ ] Screenshot of activity settings dialog with tri-state select
- [ ] Confirmation that toggle/select changes persist
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->
