# Word Count with Configurable Limits Implementation Plan

**Goal:** Instructors can configure word limits per activity and course-level enforcement default.

**Architecture:** Two `ui.number` inputs for word_minimum/word_limit in activity settings dialog. word_limit_enforcement added to `_ACTIVITY_TRI_STATE_FIELDS` for automatic tri-state select rendering. default_word_limit_enforcement added to `_COURSE_DEFAULT_FIELDS` as a switch.

**Tech Stack:** NiceGUI (ui.number, ui.select, ui.switch)

**Scope:** 6 phases from original design (phase 3 of 6)

**Codebase verified:** 2026-03-02

---

## Acceptance Criteria Coverage

This phase implements and tests:

### word-count-limits-47.AC3: Activity settings UI
- **word-count-limits-47.AC3.1 Success:** Instructor can set word minimum via number input in activity settings dialog
- **word-count-limits-47.AC3.2 Success:** Instructor can set word limit via number input in activity settings dialog
- **word-count-limits-47.AC3.3 Success:** Word limit enforcement appears as tri-state select (Inherit / Hard / Soft)
- **word-count-limits-47.AC3.4 Success:** Course defaults page has toggle for default word limit enforcement
- **word-count-limits-47.AC3.5 Success:** Values persist across page reloads

---

<!-- START_TASK_1 -->
### Task 1: Add word_limit_enforcement to _ACTIVITY_TRI_STATE_FIELDS

**Verifies:** word-count-limits-47.AC3.3

**Files:**
- Modify: `src/promptgrimoire/pages/courses.py` (lines 125-139, _ACTIVITY_TRI_STATE_FIELDS)

**Implementation:**

Add a new entry to `_ACTIVITY_TRI_STATE_FIELDS` after the existing entries:

```python
(
    "Word limit enforcement (overrides unit default)",
    "word_limit_enforcement",
    "Hard",
    "Soft",
),
```

This automatically renders a tri-state select with options: "Inherit from unit", "Hard", "Soft".

The existing `save()` function in `open_activity_settings()` already iterates `_ACTIVITY_TRI_STATE_FIELDS` to build kwargs, so no changes needed to the save logic — it will automatically pick up the new field.

**Testing:**

AC3.3 tested in Phase 6 E2E. For now, verify manually or with a unit test checking the field is in the list.

**Verification:**

Run: `uvx ty check`
Expected: No type errors.

**Commit:** `feat: add word_limit_enforcement to activity tri-state fields`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add default_word_limit_enforcement to _COURSE_DEFAULT_FIELDS

**Verifies:** word-count-limits-47.AC3.4

**Files:**
- Modify: `src/promptgrimoire/pages/courses.py` (lines 142-147, _COURSE_DEFAULT_FIELDS)

**Implementation:**

Add a new entry to `_COURSE_DEFAULT_FIELDS`:

```python
("Default word limit enforcement", "default_word_limit_enforcement"),
```

The existing `open_course_settings()` function renders `_COURSE_DEFAULT_FIELDS` as `ui.switch()` components and handles save automatically.

**Testing:**

AC3.4 tested in Phase 6 E2E. Verify type checking passes.

**Verification:**

Run: `uvx ty check`
Expected: No type errors.

**Commit:** `feat: add default_word_limit_enforcement to course defaults`
<!-- END_TASK_2 -->

<!-- START_SUBCOMPONENT_A (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: Add word_minimum and word_limit number inputs to activity settings

**Verifies:** word-count-limits-47.AC3.1, word-count-limits-47.AC3.2

**Files:**
- Modify: `src/promptgrimoire/pages/courses.py` (open_activity_settings function, lines 227-272)

**Implementation:**

In `open_activity_settings()`, add two `ui.number` inputs BEFORE the tri-state selects loop. Place them between the title label and the `for label, attr, ...` loop:

```python
word_min_input = (
    ui.number(
        "Word minimum",
        value=activity.word_minimum,
        min=1,
    )
    .classes("w-full")
    .props('data-testid="activity-word-minimum-input"')
)

word_limit_input = (
    ui.number(
        "Word limit",
        value=activity.word_limit,
        min=1,
    )
    .classes("w-full")
    .props('data-testid="activity-word-limit-input"')
)
```

In the `save()` function, add the word count fields to the kwargs:

```python
# After building kwargs from tri-state fields:
word_min_val = word_min_input.value
word_limit_val = word_limit_input.value

# Convert to int | None (ui.number may return float)
kwargs["word_minimum"] = int(word_min_val) if word_min_val is not None else None
kwargs["word_limit"] = int(word_limit_val) if word_limit_val is not None else None
```

Add validation before calling `update_activity()`:
```python
if kwargs["word_minimum"] is not None and kwargs["word_limit"] is not None:
    if kwargs["word_minimum"] >= kwargs["word_limit"]:
        ui.notify("Word minimum must be less than word limit", type="negative")
        return
```

Additionally, wrap the `update_activity()` call in a `try/except ValueError` to handle cross-field validation errors that arise from pre-existing model values. For example, if `word_minimum=400` already exists on the activity and the instructor only updates `word_limit=300`, the UI guard above won't catch it (it only checks `kwargs` values, not pre-existing model state), but the CRUD layer's validation in `update_activity()` will raise `ValueError`:

```python
try:
    await update_activity(activity.id, **kwargs)
except ValueError as e:
    ui.notify(str(e), type="negative")
    return
```

**Testing:**

Tests must verify:
- AC3.1: word_minimum number input renders with correct initial value
- AC3.2: word_limit number input renders with correct initial value
- AC2.5: Cross-field validation: minimum >= limit shows error notification
- Pre-existing field conflict: activity has word_minimum=400, updating word_limit=300 shows error notification (not unhandled exception)

These are UI-level tests — Phase 6 E2E covers the full flow. For unit testing, verify the validation logic in isolation if extracted to a helper.

**Verification:**

Run: `uvx ty check`
Expected: No type errors.

Run: `uv run ruff check src/promptgrimoire/pages/courses.py`
Expected: No lint errors.

**Commit:** `feat: add word count number inputs to activity settings dialog`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Add data-testid attributes to new controls

**Verifies:** word-count-limits-47.AC3.5

**Files:**
- Modify: `src/promptgrimoire/pages/courses.py`

**Implementation:**

Ensure all new controls have data-testid attributes:
- `data-testid="activity-word-minimum-input"` — word minimum number input (already added in Task 3)
- `data-testid="activity-word-limit-input"` — word limit number input (already added in Task 3)

**Add testids to tri-state selects.** The existing loop in `open_activity_settings()` (line 238-244) does NOT set data-testid on selects. Modify the loop to add `.props(f'data-testid="activity-{attr}-select"')` to each select:

```python
selects: dict[str, ui.select] = {}
for label, attr, on_text, off_text in _ACTIVITY_TRI_STATE_FIELDS:
    selects[attr] = (
        ui.select(
            options=_tri_state_options(on_text, off_text),
            value=_model_to_ui(getattr(activity, attr)),
            label=label,
        )
        .classes("w-full")
        .props(f'data-testid="activity-{attr}-select"')
    )
```

This produces `data-testid="activity-word_limit_enforcement-select"` for the word limit enforcement field.

**Add option-level testids** using the existing `_add_option_testids()` pattern from `src/promptgrimoire/pages/annotation/placement.py`. Import and call it after each select creation, or replicate the Quasar slot template inline:

```python
from promptgrimoire.pages.annotation.placement import _add_option_testids

for label, attr, on_text, off_text in _ACTIVITY_TRI_STATE_FIELDS:
    sel = ui.select(...)
    _add_option_testids(sel, f"activity-{attr}-opt")
    selects[attr] = sel
```

This produces option testids like `activity-word_limit_enforcement-opt-on`, `activity-word_limit_enforcement-opt-off`, `activity-word_limit_enforcement-opt-inherit`.

**Add testid to course defaults switch.** Modify the course settings loop in `open_course_settings()` to add `.props(f'data-testid="course-{attr}-switch"')` to each switch:

```python
switches[attr] = (
    ui.switch(label, value=getattr(course, attr))
    .props(f'data-testid="course-{attr}-switch"')
)
```

This produces `data-testid="course-default_word_limit_enforcement-switch"`.

**Verification:**

Run: `uvx ty check`
Expected: No type errors.

**Commit:** `feat: add data-testid attributes to word count UI controls`
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_5 -->
### Task 5: Final verification

**Files:**
- All files from this phase

**Step 1: Run full test suite**

Run: `uv run grimoire test changed`
Expected: All tests pass, no regressions.

**Step 2: Run linting and type checking**

Run: `uv run ruff check src/promptgrimoire/pages/courses.py`
Expected: No lint errors.

Run: `uvx ty check`
Expected: No type errors.

**Step 3: Verify commit history**

Run: `git log --oneline -5`
Expected: Clean commit history with conventional prefixes.
<!-- END_TASK_5 -->
