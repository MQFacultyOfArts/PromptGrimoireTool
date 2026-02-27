# Copy Protection

*Last updated: 2026-02-27*

Per-activity copy protection prevents students from copying, cutting, dragging, or printing annotated content. Instructors and admins bypass it.

## Resolution Chain

1. `Activity.copy_protection` (tri-state: `None`/`True`/`False`)
2. If `None`, inherit from `Course.default_copy_protection` (bool, default `False`)
3. Resolved in `PlacementContext.copy_protection` during workspace placement query
4. Loose and course-placed workspaces always resolve to `False`

## Client-Side Enforcement

When `protect=True` and user is not privileged:

- **JS injection** (`inject_copy_protection()` in `annotation/header.py`): Intercepts `copy`, `cut`, `contextmenu`, `dragstart` events on `#doc-container`, organise columns, and respond reference panel. Intercepts `paste` on Milkdown editor. Intercepts `Ctrl+P`/`Cmd+P`. Shows Quasar toast notification.
- **SPA navigation deferred setup:** `header.py` renders before `document.py` loads annotation scripts. On SPA navigations (`ui.navigate.to()`), `setupCopyProtection` may not be defined yet. The injection checks `typeof setupCopyProtection === 'function'` — if undefined, it stores selectors in `window._pendingCopyProtection` for `document.py`'s dynamic loader to pick up after scripts load. See [e2e-debugging.md](e2e-debugging.md#nicegui-spa-navigation-script-loading).
- **CSS print suppression**: `@media print` hides `.q-tab-panels`, shows "Printing is disabled" message.
- **Lock icon chip**: Amber "Protected" chip with lock icon in workspace header.

## UI Controls (Courses Page)

- **Course settings dialog** (`open_course_settings()`): Toggle `default_copy_protection` on/off.
- **Per-activity tri-state select**: "Inherit from course" / "On" / "Off". Pure mapping functions `_model_to_ui()` and `_ui_to_model()` convert between model `bool | None` and UI string keys. Used for both copy protection and sharing controls.

## Sharing Controls

Workspace sharing follows the same tri-state resolution pattern as copy protection.

### Resolution Chain

1. `Activity.allow_sharing` (tri-state: `None`/`True`/`False`)
2. If `None`, inherit from `Course.default_allow_sharing` (bool, default `False`)
3. Resolved in `PlacementContext.allow_sharing` during workspace placement query
4. Loose and course-placed workspaces always resolve to `False`

### Enforcement

When `allow_sharing=True`, workspace owners can share via `grant_share()`. Staff (instructors/coordinators/tutors) can always share regardless of the setting. Sharing is limited to `"editor"` or `"viewer"` permissions -- `"owner"` cannot be granted via sharing.
