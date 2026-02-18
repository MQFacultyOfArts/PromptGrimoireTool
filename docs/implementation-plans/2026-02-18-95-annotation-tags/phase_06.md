# Annotation Tag Configuration — Phase 6: Activity Settings + Course Defaults

**Goal:** Wire `allow_tag_creation` into the activity/course settings UI and generalise the tri-state settings pattern into a data-driven approach for maintainability.

**Architecture:** Add `allow_tag_creation` parameter to `create_activity()`, `update_activity()`, and `update_course()` CRUD functions following the existing Ellipsis sentinel pattern. Refactor `pages/courses.py` settings dialogs from per-field explicit code to data-driven loops over field config tuples. The refactoring replaces the existing `_COPY_PROTECTION_OPTIONS` and `_SHARING_OPTIONS` dicts with a `_tri_state_options()` factory, and the existing per-field `ui.select`/`ui.switch` blocks with loops over `_ACTIVITY_TRI_STATE_FIELDS` and `_COURSE_DEFAULT_FIELDS`. Adding `allow_tag_creation` is then just adding one tuple to each list.

**Tech Stack:** SQLModel, NiceGUI

**Scope:** Phase 6 of 6 from original design

**Codebase verified:** 2026-02-18

---

## Acceptance Criteria Coverage

This phase implements and tests:

### 95-annotation-tags.AC8: Activity settings + course defaults
- **95-annotation-tags.AC8.1 Success:** Activity settings dialog shows `allow_tag_creation` tri-state select
- **95-annotation-tags.AC8.2 Success:** Course settings dialog shows `default_allow_tag_creation` switch
- **95-annotation-tags.AC8.3 Success:** Activity `allow_tag_creation=NULL` inherits Course default
- **95-annotation-tags.AC8.4 Success:** Activity `allow_tag_creation=TRUE` overrides Course default FALSE
- **95-annotation-tags.AC8.5 Success:** Activity `allow_tag_creation=FALSE` overrides Course default TRUE

---

## Key Files Reference

These files contain patterns to follow. Read them before implementing:

- `src/promptgrimoire/db/activities.py:21-70` — `create_activity()` with `copy_protection` tri-state param
- `src/promptgrimoire/db/activities.py:79-111` — `update_activity()` with Ellipsis sentinel pattern for `copy_protection` and `allow_sharing`
- `src/promptgrimoire/db/courses.py:88-124` — `update_course()` with Ellipsis sentinel pattern for `default_copy_protection` and `default_allow_sharing`
- `src/promptgrimoire/pages/courses.py:72-84` — `_COPY_PROTECTION_OPTIONS`, `_SHARING_OPTIONS` (to replace with factory)
- `src/promptgrimoire/pages/courses.py:87-106` — `_model_to_ui()`, `_ui_to_model()` (already generic, keep as-is)
- `src/promptgrimoire/pages/courses.py:125-158` — `open_course_settings()` (to refactor)
- `src/promptgrimoire/pages/courses.py:161-199` — `open_activity_settings()` (to refactor)
- `tests/integration/test_tag_schema.py` — Phase 1 tests for PlacementContext tri-state inheritance (AC8.3-8.5 already verified there)
- `tests/integration/test_activity_crud.py` — existing activity CRUD test patterns
- `docs/testing.md` — testing guidelines
- `CLAUDE.md` — async fixture rule, project conventions

---

**Note on AC8.3-8.5:** The tri-state inheritance logic (Activity explicit → Course default) is implemented and tested in Phase 1 Task 5 (`PlacementContext.allow_tag_creation` resolution) and Phase 1 Task 7 (integration tests). Phase 6 verifies the CRUD functions accept and persist the new fields, and the settings UI wires them. The inheritance behavior itself is already proven.

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Add allow_tag_creation to activity and course CRUD functions

**Files:**
- Modify: `src/promptgrimoire/db/activities.py`
- Modify: `src/promptgrimoire/db/courses.py`

**Implementation:**

**In `db/activities.py`:**

1. Add `allow_tag_creation` parameter to `create_activity()` (line 21-26):
   ```python
   async def create_activity(
       week_id: UUID,
       title: str,
       description: str | None = None,
       copy_protection: bool | None = None,
       allow_tag_creation: bool | None = None,
   ) -> Activity:
   ```
   In the function body, add `allow_tag_creation=allow_tag_creation` to the `Activity(...)` constructor call (line 54-60).

2. Add `allow_tag_creation` parameter to `update_activity()` (line 79-84):
   ```python
   async def update_activity(
       activity_id: UUID,
       title: str | None = None,
       description: str | None = ...,  # type: ignore[assignment]
       copy_protection: bool | None = ...,  # type: ignore[assignment]
       allow_sharing: bool | None = ...,  # type: ignore[assignment]
       allow_tag_creation: bool | None = ...,  # type: ignore[assignment]  -- Ellipsis sentinel distinguishes "not provided" from explicit None (reset to inherit)
   ) -> Activity | None:
   ```
   Add the guard clause in the function body (after the `allow_sharing` block at line 104-105):
   ```python
   if allow_tag_creation is not ...:
       activity.allow_tag_creation = allow_tag_creation
   ```

3. Update docstrings to document the new parameter.

**In `db/courses.py`:**

4. Add `default_allow_tag_creation` parameter to `update_course()` (line 88-92):
   ```python
   async def update_course(
       course_id: UUID,
       name: str | None = None,
       default_copy_protection: bool = ...,  # type: ignore[assignment]
       default_allow_sharing: bool = ...,  # type: ignore[assignment]
       default_allow_tag_creation: bool = ...,  # type: ignore[assignment]  -- Ellipsis sentinel
   ) -> Course | None:
   ```
   Add the guard clause (after line 119-120):
   ```python
   if default_allow_tag_creation is not ...:
       course.default_allow_tag_creation = default_allow_tag_creation
   ```

5. Update docstring to document the new parameter.

**Verification:**
Run: `uvx ty check`
Expected: No type errors

Run: `uv run test-debug`
Expected: All existing tests pass (backward compatible — new params have defaults)

**Commit:** `feat: add allow_tag_creation to activity and course CRUD functions`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Refactor settings dialogs to data-driven tri-state fields

**Verifies:** 95-annotation-tags.AC8.1, 95-annotation-tags.AC8.2

**Files:**
- Modify: `src/promptgrimoire/pages/courses.py`

**Implementation:**

This task refactors the existing per-field settings code into data-driven loops, then adds `allow_tag_creation` as a new entry in the field config.

1. Replace the static options dicts (lines 72-84) with a factory function:
   ```python
   def _tri_state_options(on_label: str = "On", off_label: str = "Off") -> dict[str, str]:
       """Build a tri-state options dict for activity settings selects."""
       return {"inherit": "Inherit from course", "on": on_label, "off": off_label}
   ```

   Remove `_COPY_PROTECTION_OPTIONS` and `_SHARING_OPTIONS`.

2. Define the field config tuples:
   ```python
   # (UI label, model attribute name, on_label, off_label)
   _ACTIVITY_TRI_STATE_FIELDS: list[tuple[str, str, str, str]] = [
       ("Copy protection", "copy_protection", "On", "Off"),
       ("Allow sharing", "allow_sharing", "Allowed", "Not allowed"),
       ("Allow tag creation", "allow_tag_creation", "Allowed", "Not allowed"),
   ]

   # (UI label, model attribute name)
   _COURSE_DEFAULT_FIELDS: list[tuple[str, str]] = [
       ("Default copy protection", "default_copy_protection"),
       ("Default allow sharing", "default_allow_sharing"),
       ("Default allow tag creation", "default_allow_tag_creation"),
   ]
   ```

3. Refactor `open_activity_settings()` (lines 161-199):
   ```python
   async def open_activity_settings(activity: Activity) -> None:
       """Open a dialog to edit per-activity settings.

       Shows tri-state selects for each policy field, driven by
       _ACTIVITY_TRI_STATE_FIELDS config.
       """
       with ui.dialog() as dialog, ui.card().classes("w-96"):
           ui.label("Activity Settings").classes("text-lg font-bold")

           selects: dict[str, ui.select] = {}
           for label, attr, on_text, off_text in _ACTIVITY_TRI_STATE_FIELDS:
               selects[attr] = ui.select(
                   options=_tri_state_options(on_text, off_text),
                   value=_model_to_ui(getattr(activity, attr)),
                   label=label,
               ).classes("w-full")

           with ui.row().classes("w-full justify-end gap-2"):
               ui.button("Cancel", on_click=dialog.close).props("flat")

               async def save() -> None:
                   kwargs = {
                       attr: _ui_to_model(selects[attr].value)
                       for _, attr, *_ in _ACTIVITY_TRI_STATE_FIELDS
                   }
                   await update_activity(activity.id, **kwargs)
                   for _, attr, *_ in _ACTIVITY_TRI_STATE_FIELDS:
                       setattr(activity, attr, kwargs[attr])
                   dialog.close()
                   ui.notify("Activity settings saved", type="positive")

               ui.button("Save", on_click=save).props("color=primary")

       dialog.open()
   ```

4. Refactor `open_course_settings()` (lines 125-158):
   ```python
   async def open_course_settings(course: Course) -> None:
       """Open a dialog to edit course settings.

       Shows boolean switches for each default policy field, driven by
       _COURSE_DEFAULT_FIELDS config.
       """
       with ui.dialog() as dialog, ui.card().classes("w-96"):
           ui.label("Course Settings").classes("text-lg font-bold")

           switches: dict[str, ui.switch] = {}
           for label, attr in _COURSE_DEFAULT_FIELDS:
               switches[attr] = ui.switch(label, value=getattr(course, attr))

           with ui.row().classes("w-full justify-end gap-2"):
               ui.button("Cancel", on_click=dialog.close).props("flat")

               async def save() -> None:
                   kwargs = {
                       attr: switches[attr].value
                       for _, attr in _COURSE_DEFAULT_FIELDS
                   }
                   await update_course(course.id, **kwargs)
                   for _, attr in _COURSE_DEFAULT_FIELDS:
                       setattr(course, attr, kwargs[attr])
                   dialog.close()
                   ui.notify("Course settings saved", type="positive")

               ui.button("Save", on_click=save).props("color=primary")

       dialog.open()
   ```

5. Verify the `update_activity` and `update_course` imports are already present (they should be — check the import block at the top of courses.py).

**Verification:**
Run: `uvx ty check`
Expected: No type errors

Run: `uv run test-debug`
Expected: All existing tests pass (behavior unchanged, only structure refactored)

**Commit:** `refactor: data-driven tri-state settings dialogs, add allow_tag_creation`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: Integration tests for CRUD parameter acceptance

**Verifies:** 95-annotation-tags.AC8.1, 95-annotation-tags.AC8.2

**Files:**
- Create: `tests/integration/test_tag_settings.py`

**Implementation:**

Follow the pattern from `tests/integration/test_activity_crud.py`:
- Module-level `pytestmark` skip guard
- Class-based grouping, `@pytest.mark.asyncio async def` methods

**Testing:**

`TestCreateActivityWithTagCreation`:
- AC8.1: Create an activity with `allow_tag_creation=False`. Fetch it via `get_activity()`. Verify `activity.allow_tag_creation is False`.
- AC8.1: Create an activity with `allow_tag_creation=None` (default). Verify `activity.allow_tag_creation is None`.

`TestUpdateActivityTagCreation`:
- AC8.1: Create an activity. Call `update_activity(activity.id, allow_tag_creation=False)`. Verify the field is updated.
- AC8.1: Call `update_activity(activity.id, allow_tag_creation=None)` (reset to inherit). Verify the field is None.
- AC8.1: Call `update_activity(activity.id, title="New Title")` without `allow_tag_creation`. Verify `allow_tag_creation` is unchanged (Ellipsis sentinel works).

`TestUpdateCourseDefaultTagCreation`:
- AC8.2: Create a course. Call `update_course(course.id, default_allow_tag_creation=False)`. Verify the field is updated.
- AC8.2: Call `update_course(course.id, default_allow_tag_creation=True)`. Verify the field is updated.
- AC8.2: Call `update_course(course.id, name="New Name")` without `default_allow_tag_creation`. Verify `default_allow_tag_creation` is unchanged.

`TestTriStateInheritanceFromCrud`:
- AC8.3: Create course with `default_allow_tag_creation=True`, activity with `allow_tag_creation=None`. Call `get_placement_context(workspace_id)`. Verify `ctx.allow_tag_creation is True`.
- AC8.4: Update activity to `allow_tag_creation=True`, course to `default_allow_tag_creation=False`. Verify context resolves to `True`.
- AC8.5: Update activity to `allow_tag_creation=False`, course to `default_allow_tag_creation=True`. Verify context resolves to `False`.

Note: AC8.3-8.5 are also tested in Phase 1 Task 7. These tests verify the same inheritance but exercise it through the CRUD update functions (round-trip: update via CRUD → verify via PlacementContext).

**Verification:**
Run: `uv run test-debug`
Expected: All tests pass

**Commit:** `test: add integration tests for tag creation settings CRUD and inheritance`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Update db/__init__.py exports for new CRUD parameters

**Files:**
- Modify: `src/promptgrimoire/db/__init__.py` (if needed)

**Implementation:**

Verify that `create_activity`, `update_activity`, and `update_course` are already exported from `db/__init__.py`. These functions already exist — their signatures are changing but no new exports are needed. If the exports are already present, this task is a no-op verification.

Check that no other modules import `create_activity` or `update_activity` with positional arguments that would break with the new parameter. The new parameters have defaults (`None` for `create_activity`, Ellipsis for `update_activity` and `update_course`) so all existing call sites remain compatible.

**Verification:**
Run: `uvx ty check`
Expected: No type errors across the full codebase

Run: `uv run test-all`
Expected: All tests pass (full suite verification — the refactored settings dialogs and new CRUD params are backward compatible)

**Commit:** `chore: verify exports and backward compatibility for tag creation settings`
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->
