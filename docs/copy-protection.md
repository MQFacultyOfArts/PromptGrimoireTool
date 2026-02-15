# Copy Protection

*Last updated: 2026-02-15*

Per-activity copy protection prevents students from copying, cutting, dragging, or printing annotated content. Instructors and admins bypass it.

## Resolution Chain

1. `Activity.copy_protection` (tri-state: `None`/`True`/`False`)
2. If `None`, inherit from `Course.default_copy_protection` (bool, default `False`)
3. Resolved in `PlacementContext.copy_protection` during workspace placement query
4. Loose and course-placed workspaces always resolve to `False`

## Client-Side Enforcement

When `protect=True` and user is not privileged:

- **JS injection** (`_inject_copy_protection()` in `annotation/workspace.py`): Intercepts `copy`, `cut`, `contextmenu`, `dragstart` events on `#doc-container`, organise columns, and respond reference panel. Intercepts `paste` on Milkdown editor. Intercepts `Ctrl+P`/`Cmd+P`. Shows Quasar toast notification.
- **CSS print suppression**: `@media print` hides `.q-tab-panels`, shows "Printing is disabled" message.
- **Lock icon chip**: Amber "Protected" chip with lock icon in workspace header.

## UI Controls (Courses Page)

- **Course settings dialog** (`open_course_settings()`): Toggle `default_copy_protection` on/off.
- **Per-activity tri-state select**: "Inherit from course" / "On" / "Off". Pure mapping functions `_model_to_ui()` and `_ui_to_model()` convert between model `bool | None` and UI string keys.
