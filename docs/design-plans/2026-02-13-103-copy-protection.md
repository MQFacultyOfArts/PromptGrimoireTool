# Per-Activity Copy Protection Design

## Summary

This design adds optional copy protection to activities, allowing instructors to create pedagogical friction that discourages students from copying source material or pasting pre-written answers during annotation exercises. The feature uses a nullable boolean on Activity (`copy_protection: bool | None`) with a course-level default (`default_copy_protection: bool`). When `copy_protection` is NULL, the activity inherits the course default — so changing the course toggle mid-semester dynamically affects all un-overridden activities. When explicitly set to True or False, the activity's own value takes precedence. Client-side JavaScript intercepts clipboard events (copy/cut/paste), context menus, text dragging, and print commands on protected content areas. Instructors and admins are automatically exempt via Stytch role checks.

The implementation prioritises transparency and instructor control. A non-interactive lock icon chip (with tooltip and aria-label) shows students when protection is active. Protections are purely client-side JavaScript event handlers — easily bypassed by technically savvy students, but effective as friction for casual copying. Text selection remains fully functional to preserve the core highlighting workflow. The design explicitly treats this as pedagogical scaffolding rather than security, with no server-side enforcement or digital rights management (DRM) mechanisms.

## Definition of Done

Per-activity pedagogical friction that discourages students from copying source material out of the annotation page or pasting pre-written content into the response editor. Implemented as client-side JS event interception with CSS print suppression, toggled by a boolean on the Activity model. Course model provides a default value inherited by new activities. Instructors and admins bypass all protections. Text selection remains fully functional for the core highlighting workflow.

**Deliverables:**

1. `Activity.copy_protection` nullable boolean field (default NULL = inherit from course) with Alembic migration. Explicit True/False overrides course default.
2. `Course.default_copy_protection` boolean field (default False) with Alembic migration. Dynamically inherited by activities with `copy_protection=NULL`.
3. Client-side protections when enabled: copy/cut interception on protected content (Tab 1 document, Tab 2/3 cards), right-click context menu disable, paste blocking in Milkdown editor, drag-text-out prevention, CSS print suppression + Ctrl+P intercept.
4. Toast notifications on blocked actions.
5. Instructor/admin bypass via Stytch-level roles — protections not injected.
6. Text selection remains functional — highlighting is unaffected.

**Out of scope:** Tab-switch detection, fullscreen enforcement, F12/DevTools blocking, watermarking, server-side enforcement. This is pedagogical friction, not DRM.

## Acceptance Criteria

### 103-copy-protection.AC1: Activity copy_protection field
- **AC1.1 Success:** Activity with `copy_protection=True` stores and retrieves correctly
- **AC1.2 Success:** Activity with `copy_protection=False` (explicit override) stores and retrieves correctly
- **AC1.3 Success:** Activity with `copy_protection=NULL` (default, inherit from course) stores and retrieves correctly
- **AC1.4 Edge:** Existing activities (pre-migration) default to `copy_protection=NULL`

### 103-copy-protection.AC2: PlacementContext resolution
- **AC2.1 Success:** Workspace in activity with `copy_protection=True` → PlacementContext has `copy_protection=True`
- **AC2.2 Success:** Workspace in activity with `copy_protection=False` → PlacementContext has `copy_protection=False`
- **AC2.3 Success:** Loose workspace (no activity) → PlacementContext has `copy_protection=False`
- **AC2.4 Success:** Course-placed workspace → PlacementContext has `copy_protection=False`

### 103-copy-protection.AC3: Nullable fallback inheritance
- **AC3.1 Success:** Activity with `copy_protection=NULL` in course with `default_copy_protection=True` → resolves to True
- **AC3.2 Success:** Activity with `copy_protection=NULL` in course with `default_copy_protection=False` → resolves to False
- **AC3.3 Success:** Activity with explicit `copy_protection=True` overrides course default of False
- **AC3.4 Success:** Activity with explicit `copy_protection=False` overrides course default of True
- **AC3.5 Success:** Changing course default dynamically affects activities with `copy_protection=NULL`
- **AC3.6 Success:** Changing course default does NOT affect activities with explicit `copy_protection`
- **AC3.7 Edge:** New activities default to `copy_protection=NULL` (inherit from course)

### 103-copy-protection.AC4: Client-side protections (E2E)
- **AC4.1 Success:** Copy blocked on Tab 1 document content for student
- **AC4.2 Success:** Copy blocked on Tab 2 organise cards for student
- **AC4.3 Success:** Copy blocked on Tab 3 reference cards for student
- **AC4.4 Success:** Cut blocked on same protected areas
- **AC4.5 Success:** Right-click context menu blocked on protected areas
- **AC4.6 Success:** Print suppressed (CSS @media print shows message, Ctrl+P intercepted)
- **AC4.7 Success:** Drag-text-out blocked on protected areas
- **AC4.8 Success:** Paste blocked in Milkdown editor for student
- **AC4.9 Success:** Copy from Milkdown editor (student's own writing) still works
- **AC4.10 Success:** Text selection for highlighting unaffected by protection
- **AC4.11 Success:** Debounced toast notification shown on blocked action
- **AC4.12 Failure:** Protection not active when `copy_protection=False` on activity
- **AC4.13 Failure:** Protection not active for loose workspace

### 103-copy-protection.AC5: Instructor/admin bypass
- **AC5.1 Success:** Admin user sees no protection even when `copy_protection=True`
- **AC5.2 Success:** User with `instructor` role sees no protection
- **AC5.3 Success:** User with `stytch_admin` role sees no protection
- **AC5.4 Failure:** Student sees protection when `copy_protection=True`
- **AC5.5 Failure:** Tutor sees protection when `copy_protection=True`
- **AC5.6 Edge:** Unauthenticated user sees protection when `copy_protection=True`

### 103-copy-protection.AC6: Student-facing indicator
- **AC6.1 Success:** Lock icon chip visible in header when protection active
- **AC6.2 Success:** Lock chip tooltip reads "Copy protection is enabled for this activity"
- **AC6.3 Failure:** Lock chip not visible when protection inactive

### 103-copy-protection.AC7: Instructor UI
- **AC7.1 Success:** Course settings shows "Default copy protection" toggle
- **AC7.2 Success:** Activity settings shows tri-state "Copy protection" control: Inherit from course / On / Off
- **AC7.3 Success:** New activities default to "Inherit from course" state
- **AC7.4 Success:** Per-activity explicit On/Off overrides course default
- **AC7.5 Success:** Resetting activity to "Inherit" clears override (sets `copy_protection=NULL`)

## Glossary

- **Activity**: A weekly assignment within a Course that owns a template Workspace. Students clone the template to complete the work.
- **Alembic**: Database migration tool for SQLAlchemy/SQLModel. All schema changes must go through Alembic migrations rather than direct SQL or `create_all()` calls.
- **Course**: A unit of study containing Weeks, which contain Activities. Equivalent to a class/subject at a university.
- **CRDT**: Conflict-free Replicated Data Type — enables real-time collaborative editing without locking. Used for workspace state synchronisation.
- **Milkdown**: Rich text editor framework used for the student response editor on Tab 3 of the annotation page.
- **NiceGUI**: Python web UI framework powering PromptGrimoire's interface. Built on FastAPI + Vue.
- **PlacementContext**: Frozen dataclass resolving the full hierarchy (Activity → Week → Course) for a workspace, used for UI display and feature gating like copy protection.
- **ProseMirror**: The underlying editor engine that Milkdown wraps. Relevant because paste interception must happen before ProseMirror processes the event.
- **Quasar**: UI component library used by NiceGUI. Provides `Quasar.Notify.create()` for toast notifications.
- **SQLModel**: ORM combining SQLAlchemy (database operations) with Pydantic (data validation). PromptGrimoire's data layer.
- **Stytch**: Authentication provider handling login (magic links, passkeys) and RBAC (role-based access control).
- **Workspace**: Container for documents and CRDT state — the unit of collaboration. Can be placed in an Activity or Course, or left loose (unplaced).

## Architecture

Per-activity copy protection adds a boolean toggle to Activity and a course-level default. When enabled, the annotation page injects client-side JS event handlers that intercept clipboard, context menu, paste, drag, and print operations on protected content areas. Instructors and admins bypass all protections via Stytch-level role check.

### Data Model Changes

**Activity** gains `copy_protection: bool | None = Field(default=None)`. Nullable tri-state:
- `None` — inherit from `Course.default_copy_protection` (the default for new and existing activities)
- `True` — explicit per-activity override, protection active
- `False` — explicit per-activity override, protection disabled

**Course** gains `default_copy_protection: bool = Field(default=False)`. Non-nullable. Dynamically inherited by all activities in the course that have `copy_protection=NULL`. Changing this value mid-semester takes effect immediately for un-overridden activities.

Alembic migration adds both columns. Activity column is nullable (default NULL). Course column is non-nullable (default False).

### PlacementContext Extension

`PlacementContext` (frozen dataclass in `src/promptgrimoire/db/workspaces.py`) gains `copy_protection: bool = False`. This is the **resolved** value — the tri-state is collapsed during `_resolve_activity_placement()`:
1. If `activity.copy_protection` is not None, use it directly
2. If `activity.copy_protection` is None, resolve through week → course → `default_copy_protection`

Loose workspaces and course-placed workspaces always resolve to `False`.

### Role Check

Pure function `is_privileged_user(auth_user: dict | None) -> bool` in `src/promptgrimoire/pages/annotation.py`. Returns True if `auth_user["is_admin"]` is True, or if `"instructor"` or `"stytch_admin"` appears in `auth_user["roles"]`. Returns False for students, tutors, unauthenticated users, missing data.

### Protection Decision

In `_render_workspace_view()`, after `get_placement_context()`:

```
protect = ctx.copy_protection and not is_privileged_user(auth_user)
```

If `protect` is True, JS and CSS are injected after the three-tab container is built. If False, nothing is injected.

### Client-Side Protections

Single JS block injected via `ui.run_javascript()`. Uses event delegation from the tab panels container.

**Protected content selectors:**
- `#doc-container` — Tab 1 document content
- `[data-testid="organise-columns"]` — Tab 2 highlight cards
- `[data-testid="respond-reference-panel"]` — Tab 3 reference cards

**Events intercepted:**
- `copy`, `cut` — on protected selectors. Students can still copy from Milkdown editor (their own writing).
- `contextmenu` — on protected selectors
- `paste` — on `#milkdown-respond-editor` only. Uses capture phase to intercept before ProseMirror.
- `dragstart` — on protected selectors
- `keydown` for Ctrl+P/Cmd+P — document-wide when protection active

**Print suppression:** Dynamically injected `<style>` block with `@media print` rule hiding tab panels and showing "Printing is disabled for this activity" message.

**Toast notifications:** Debounced `Quasar.Notify.create()` call on blocked actions. Single notification style: "Copying is disabled for this activity." Debounce prevents toast spam from repeated attempts.

### Student-Facing Indicator

When copy protection is active, a lock icon chip appears in the workspace header (alongside placement chip). Tooltip: "Copy protection is enabled for this activity."

## Existing Patterns

Investigation found these relevant patterns:

**Boolean config on Workspace:** `Workspace.enable_save_as_draft` provides precedent for activity-level configuration, though it lives on Workspace rather than Activity. The copy protection field goes on Activity since it applies to all workspaces in the activity.

**PlacementContext resolution:** `get_placement_context()` already walks workspace → activity → week → course in a single session. Adding `copy_protection` to this path requires reading one additional field from the already-fetched Activity object — no extra queries.

**JS injection:** Four patterns exist in `annotation.py`. Copy protection uses the same `ui.run_javascript()` pattern as char span injection and paste event handling (Pattern A/D from investigation).

**Activity creation:** `create_activity()` currently takes `week_id`, `title`, `description`. Adding `copy_protection` parameter is straightforward — the default NULL means no Course lookup is needed at creation time. Resolution happens lazily in PlacementContext when the annotation page loads.

**No existing copy protection pattern** in the codebase. This is new functionality.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Data Model & Migration

**Goal:** Add nullable `copy_protection` to Activity and `default_copy_protection` to Course with Alembic migration. Extend PlacementContext with resolved copy_protection.

**Components:**
- `Activity` model in `src/promptgrimoire/db/models.py` — new `copy_protection: bool | None` field (nullable, default NULL)
- `Course` model in `src/promptgrimoire/db/models.py` — new `default_copy_protection: bool` field (non-nullable, default False)
- Alembic migration adding both columns
- `PlacementContext` in `src/promptgrimoire/db/workspaces.py` — new `copy_protection: bool` field (resolved value), populated in `_resolve_activity_placement()` with fallback through week → course
- Resolution logic in `_resolve_activity_placement()` — collapse tri-state to bool using Course default

**Dependencies:** None (first phase)

**Done when:**
- Migration runs cleanly on existing database
- `PlacementContext` resolves copy_protection through Activity → Course fallback chain
- Tests verify: tri-state resolution, Course default inheritance, explicit overrides, loose workspace always False
- Covers: 103-copy-protection.AC1.*, 103-copy-protection.AC2.*, 103-copy-protection.AC3.*
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Activity CRUD for copy_protection

**Goal:** `create_activity()` and `update_activity()` support the nullable `copy_protection` field.

**Components:**
- `create_activity()` in `src/promptgrimoire/db/activities.py` — new optional `copy_protection` parameter (default None, stored as NULL)
- `update_activity()` in `src/promptgrimoire/db/activities.py` — support setting `copy_protection` to True, False, or None (reset to inherit)

**Dependencies:** Phase 1 (model fields exist)

**Done when:**
- Creating activity defaults to `copy_protection=NULL` (no Course lookup needed at creation — resolution happens in PlacementContext)
- Updating activity's `copy_protection` to True/False/None works
- Tests verify CRUD round-trips for all three states
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Role Check & Protection Decision

**Goal:** Pure function for role check and wiring into annotation page lifecycle.

**Components:**
- `is_privileged_user()` in `src/promptgrimoire/pages/annotation.py` — pure function checking Stytch-level roles
- Protection decision in `_render_workspace_view()` — resolve `ctx.copy_protection` and role, pass to JS injection point

**Dependencies:** Phase 1 (PlacementContext has copy_protection)

**Done when:**
- `is_privileged_user()` correctly identifies admin, instructor, stytch_admin roles
- Returns False for students, tutors, unauthenticated, missing data
- Protection flag correctly computed from PlacementContext + role check
- Covers: 103-copy-protection.AC5.*
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Client-Side Copy/Paste/Drag Protection

**Goal:** JS event interception for copy, cut, paste, drag, and right-click.

**Components:**
- JS protection script injected via `ui.run_javascript()` in `src/promptgrimoire/pages/annotation.py`
- Event handlers for `copy`, `cut`, `contextmenu`, `paste`, `dragstart`
- Debounced `Quasar.Notify.create()` toast
- Student-facing lock icon chip in workspace header

**Dependencies:** Phase 3 (protection decision wired)

**Done when:**
- Copy/cut blocked on Tab 1 doc, Tab 2 cards, Tab 3 reference cards
- Right-click blocked on same selectors
- Paste blocked in Milkdown editor
- Drag blocked on protected selectors
- Copy from Milkdown editor (student's own writing) still works
- Text selection for highlighting unaffected
- Toast shown on blocked action (debounced)
- Lock chip visible when protection active
- Covers: 103-copy-protection.AC4.*, 103-copy-protection.AC6.*
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: Print Suppression

**Goal:** CSS `@media print` suppression and Ctrl+P/Cmd+P intercept.

**Components:**
- Dynamic `<style>` block injection in `src/promptgrimoire/pages/annotation.py` — `@media print` rule
- `keydown` handler for Ctrl+P/Cmd+P in the protection JS

**Dependencies:** Phase 4 (JS injection infrastructure exists)

**Done when:**
- Browser print renders message instead of content when protection active
- Ctrl+P/Cmd+P intercepted and prevented
- Print works normally when protection is off
- Covers: 103-copy-protection.AC4.6, 103-copy-protection.AC4.7
<!-- END_PHASE_5 -->

<!-- START_PHASE_6 -->
### Phase 6: Instructor UI

**Goal:** Toggle controls for copy protection on course and activity settings.

**Components:**
- Course settings on courses page (`src/promptgrimoire/pages/courses.py`) — "Default copy protection" toggle
- Activity settings on courses page — per-activity "Copy protection" toggle, pre-set from course default
- `seed-data` update in `src/promptgrimoire/cli.py` — optionally set copy protection on seed activities

**Dependencies:** Phase 2 (CRUD supports copy_protection), Phase 4 (protection visible to verify)

**Done when:**
- Instructor can toggle course-level default
- Instructor can toggle per-activity override
- New activities inherit course default
- Changes take effect on next student page load
- Covers: 103-copy-protection.AC7.*
<!-- END_PHASE_6 -->

## Additional Considerations

**Accessibility:** Copy/paste blocking has WCAG concerns for students with motor disabilities or who use assistive technology. The per-activity toggle means instructors can disable protection for specific activities when accessibility accommodations are needed. The instructor bypass ensures staff are never impacted. The lock chip uses `aria-label` for screen reader accessibility.

**Not security — naming matters:** All protections are trivially bypassable via browser DevTools, disabling JS, or browser extensions. This is explicitly pedagogical friction — making casual copying inconvenient, not impossible. UI copy and code comments should use language like "discourages copying" rather than "prevents copying" to avoid instructor overconfidence. The field name `copy_protection` is pragmatic (matches issue #103) but documentation should be clear about its limitations.

**Nullable fallback rationale:** The proleptic challenge identified that a set-once inheritance model would make the course-level toggle useless mid-semester. The nullable fallback (`NULL = inherit from course`) means instructors can change the course default at any time and affect all activities that haven't been explicitly overridden. This adds one extra resolution step in PlacementContext (week → course lookup when activity value is NULL) but avoids the need for bulk-update tooling.
