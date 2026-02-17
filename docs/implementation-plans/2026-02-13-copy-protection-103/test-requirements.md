# Per-Activity Copy Protection -- Test Requirements

**Feature:** Per-activity copy protection (Issue #103)
**Design plan:** `docs/design-plans/2026-02-13-103-copy-protection.md`
**Implementation phases:** `docs/implementation-plans/2026-02-13-103-copy-protection/phase_01.md` through `phase_06.md`
**Generated:** 2026-02-13

---

## Summary

42 acceptance criteria across 7 AC groups (AC1--AC7). 15 are unit-testable, 12 are integration-testable, 15 require E2E/manual verification.

---

## Automated Test Coverage Required

### AC1: Activity copy_protection field

| AC | Description | Type | Phase/Task | Test File | What Test Must Verify |
|----|-------------|------|------------|-----------|----------------------|
| AC1.1 | Activity with `copy_protection=True` stores and retrieves correctly | Integration | P1/T2 | `tests/integration/test_workspace_placement.py` | Create Activity with `copy_protection=True`, read back from DB, assert field value is `True` |
| AC1.2 | Activity with `copy_protection=False` (explicit override) stores and retrieves correctly | Integration | P1/T2 | `tests/integration/test_workspace_placement.py` | Create Activity with `copy_protection=False`, read back from DB, assert field value is `False` |
| AC1.3 | Activity with `copy_protection=NULL` (default, inherit from course) stores and retrieves correctly | Integration | P1/T2 | `tests/integration/test_workspace_placement.py` | Create Activity with `copy_protection=None`, read back from DB, assert field value is `None` |
| AC1.4 | Existing activities (pre-migration) default to `copy_protection=NULL` | Integration | P1/T2 | `tests/integration/test_workspace_placement.py` | Create Activity without specifying `copy_protection`, assert field defaults to `None` |

### AC2: PlacementContext resolution

| AC | Description | Type | Phase/Task | Test File | What Test Must Verify |
|----|-------------|------|------------|-----------|----------------------|
| AC2.1 | Workspace in activity with `copy_protection=True` resolves to `PlacementContext.copy_protection=True` | Integration | P1/T2 | `tests/integration/test_workspace_placement.py` | Create activity with `copy_protection=True`, place workspace, call `get_placement_context()`, assert `ctx.copy_protection is True` |
| AC2.2 | Workspace in activity with `copy_protection=False` resolves to `PlacementContext.copy_protection=False` | Integration | P1/T2 | `tests/integration/test_workspace_placement.py` | Create activity with `copy_protection=False`, place workspace, call `get_placement_context()`, assert `ctx.copy_protection is False` |
| AC2.3 | Loose workspace (no activity) resolves to `PlacementContext.copy_protection=False` | Integration | P1/T2 | `tests/integration/test_workspace_placement.py` | Create loose workspace, call `get_placement_context()`, assert `ctx.copy_protection is False` |
| AC2.4 | Course-placed workspace resolves to `PlacementContext.copy_protection=False` | Integration | P1/T2 | `tests/integration/test_workspace_placement.py` | Create workspace with `course_id` set, call `get_placement_context()`, assert `ctx.copy_protection is False` |

### AC3: Nullable fallback inheritance

| AC | Description | Type | Phase/Task | Test File | What Test Must Verify |
|----|-------------|------|------------|-----------|----------------------|
| AC3.1 | Activity `copy_protection=NULL` + course `default_copy_protection=True` resolves to True | Integration | P1/T2 | `tests/integration/test_workspace_placement.py` | Set course `default_copy_protection=True`, create activity with `copy_protection=None`, resolve PlacementContext, assert `copy_protection is True` |
| AC3.2 | Activity `copy_protection=NULL` + course `default_copy_protection=False` resolves to False | Integration | P1/T2 | `tests/integration/test_workspace_placement.py` | Set course `default_copy_protection=False`, create activity with `copy_protection=None`, resolve PlacementContext, assert `copy_protection is False` |
| AC3.3 | Explicit `copy_protection=True` overrides course default of False | Integration | P1/T2 | `tests/integration/test_workspace_placement.py` | Course default False, activity explicit True, assert PlacementContext `copy_protection is True` |
| AC3.4 | Explicit `copy_protection=False` overrides course default of True | Integration | P1/T2 | `tests/integration/test_workspace_placement.py` | Course default True, activity explicit False, assert PlacementContext `copy_protection is False` |
| AC3.5 | Changing course default dynamically affects activities with `copy_protection=NULL` | Integration | P1/T2 | `tests/integration/test_workspace_placement.py` | Activity `copy_protection=None`, update course default from False to True, re-fetch PlacementContext, assert new value reflected |
| AC3.6 | Changing course default does NOT affect activities with explicit `copy_protection` | Integration | P1/T2 | `tests/integration/test_workspace_placement.py` | Activity `copy_protection=True`, update course default from True to False, re-fetch PlacementContext, assert value unchanged |
| AC3.7 | New activities default to `copy_protection=NULL` (inherit from course) | Integration | P1/T2 | `tests/integration/test_workspace_placement.py` | Create activity via `create_activity()` with no `copy_protection` arg, assert `activity.copy_protection is None` |

### AC5: Instructor/admin bypass

| AC | Description | Type | Phase/Task | Test File | What Test Must Verify |
|----|-------------|------|------------|-----------|----------------------|
| AC5.1 | Admin user (`is_admin=True`) returns `is_privileged_user() -> True` | Unit | P3/T1 | `tests/unit/test_auth_roles.py` | `is_privileged_user({"is_admin": True, "roles": []})` returns `True` |
| AC5.2 | User with `instructor` role returns `is_privileged_user() -> True` | Unit | P3/T1 | `tests/unit/test_auth_roles.py` | `is_privileged_user({"is_admin": False, "roles": ["instructor"]})` returns `True` |
| AC5.3 | User with `stytch_admin` role returns `is_privileged_user() -> True` | Unit | P3/T1 | `tests/unit/test_auth_roles.py` | `is_privileged_user({"is_admin": False, "roles": ["stytch_admin"]})` returns `True` |
| AC5.4 | Student (no privileged role) returns `is_privileged_user() -> False` | Unit | P3/T1 | `tests/unit/test_auth_roles.py` | `is_privileged_user({"is_admin": False, "roles": []})` returns `False` |
| AC5.5 | Tutor role returns `is_privileged_user() -> False` | Unit | P3/T1 | `tests/unit/test_auth_roles.py` | `is_privileged_user({"is_admin": False, "roles": ["tutor"]})` returns `False` |
| AC5.6 | Unauthenticated user returns `is_privileged_user() -> False` | Unit | P3/T1 | `tests/unit/test_auth_roles.py` | `is_privileged_user(None)` returns `False` |

### AC4: Client-side protections (conditional injection boundary)

These ACs verify the **conditional injection boundary** -- whether JS/CSS is injected or not. Actual clipboard interception is verified via E2E or manual testing (see Human Verification Required below).

| AC | Description | Type | Phase/Task | Test File | What Test Must Verify |
|----|-------------|------|------------|-----------|----------------------|
| AC4.12 | Protection not active when `copy_protection=False` on activity | Unit | P4/T2 | `tests/unit/test_copy_protection_js.py` | When `protect=False`, `_inject_copy_protection()` is NOT called (mock `ui.run_javascript`, assert not called) |
| AC4.13 | Protection not active for loose workspace | Unit | P4/T2 | `tests/unit/test_copy_protection_js.py` | When workspace has no activity (loose), `protect` resolves to `False`, JS not injected |

### AC4: Client-side protections (print suppression conditional)

| AC | Description | Type | Phase/Task | Test File | What Test Must Verify |
|----|-------------|------|------------|-----------|----------------------|
| AC4.6 (partial) | Print CSS injected when `protect=True` | Unit | P5/T1 | `tests/unit/test_copy_protection_js.py` | When `protect=True`, `ui.add_css` is called (mock and assert). When `protect=False`, `ui.add_css` is NOT called |

### AC6: Student-facing indicator (conditional rendering)

| AC | Description | Type | Phase/Task | Test File | What Test Must Verify |
|----|-------------|------|------------|-----------|----------------------|
| AC6.3 | Lock chip not visible when protection inactive | Unit | P4/T1 | `tests/unit/test_copy_protection_js.py` | When `protect=False`, `ui.chip` with `icon="lock"` is NOT called |

### AC7: Instructor UI (pure mapping functions)

| AC | Description | Type | Phase/Task | Test File | What Test Must Verify |
|----|-------------|------|------------|-----------|----------------------|
| AC7.3 (partial) | `_model_to_ui(None)` returns `"inherit"` | Unit | P6/T3 | `tests/unit/test_copy_protection_ui.py` | `_model_to_ui(None) == "inherit"` |
| AC7.4 (partial) | `_ui_to_model("on")` returns `True` | Unit | P6/T3 | `tests/unit/test_copy_protection_ui.py` | `_ui_to_model("on") is True` |
| AC7.5 (partial) | `_ui_to_model("inherit")` returns `None` | Unit | P6/T3 | `tests/unit/test_copy_protection_ui.py` | `_ui_to_model("inherit") is None` |

### Phase 2 CRUD (no new ACs, extends AC1 coverage through service layer)

| AC | Description | Type | Phase/Task | Test File | What Test Must Verify |
|----|-------------|------|------------|-----------|----------------------|
| -- | `create_activity()` with `copy_protection=True` persists value | Integration | P2/T1 | `tests/integration/test_activity_crud.py` | Call `create_activity(copy_protection=True)`, read back, assert `True` |
| -- | `create_activity()` without `copy_protection` defaults to `None` | Integration | P2/T1 | `tests/integration/test_activity_crud.py` | Call `create_activity()` with no `copy_protection` arg, assert `None` |
| -- | `update_activity()` sets `copy_protection` from None to True | Integration | P2/T1 | `tests/integration/test_activity_crud.py` | Create with None, update to True, read back, assert `True` |
| -- | `update_activity()` resets `copy_protection` from True to None | Integration | P2/T1 | `tests/integration/test_activity_crud.py` | Create with True, update to None (reset to inherit), assert `None` |
| -- | `update_activity()` with only title does NOT change `copy_protection` | Integration | P2/T1 | `tests/integration/test_activity_crud.py` | Create with True, update title only, assert `copy_protection` still `True` |

### Phase 6 CRUD (infrastructure for instructor UI)

| AC | Description | Type | Phase/Task | Test File | What Test Must Verify |
|----|-------------|------|------------|-----------|----------------------|
| -- | `update_course()` sets `default_copy_protection` from False to True | Integration | P6/T1 | `tests/integration/test_course_service.py` | Call `update_course(default_copy_protection=True)`, read back, assert `True` |
| -- | `update_course()` sets `default_copy_protection` from True to False | Integration | P6/T1 | `tests/integration/test_course_service.py` | Call `update_course(default_copy_protection=False)`, read back, assert `False` |
| -- | `update_course()` with only name does NOT change `default_copy_protection` | Integration | P6/T1 | `tests/integration/test_course_service.py` | Update name only, assert `default_copy_protection` unchanged |
| -- | `update_course()` for nonexistent course returns None | Integration | P6/T1 | `tests/integration/test_course_service.py` | Call with bogus UUID, assert returns `None` |

---

## Human Verification Required

These acceptance criteria require human verification because they involve browser-level behavior (clipboard interception, context menus, print dialogs, visual rendering) that cannot be reliably tested in headless automation.

### AC4: Client-side protections (browser behavior)

| AC | Description | Why Manual | Steps |
|----|-------------|-----------|-------|
| AC4.1 | Copy blocked on Tab 1 document content for student | Clipboard API interception requires real browser context | See Phase 4 UAT below |
| AC4.2 | Copy blocked on Tab 2 organise cards for student | Same -- clipboard interception | See Phase 4 UAT below |
| AC4.3 | Copy blocked on Tab 3 reference cards for student | Same -- clipboard interception | See Phase 4 UAT below |
| AC4.4 | Cut blocked on same protected areas | Same -- clipboard interception | See Phase 4 UAT below |
| AC4.5 | Right-click context menu blocked on protected areas | Context menu suppression is browser-specific | See Phase 4 UAT below |
| AC4.6 | Print suppressed (CSS @media print shows message, Ctrl+P intercepted) | Print dialog is OS-level, CSS print emulation is unreliable in headless | See Phase 5 UAT below |
| AC4.7 | Drag-text-out blocked on protected areas | Drag events in headless Playwright are synthetic, not real DnD | See Phase 4 UAT below |
| AC4.8 | Paste blocked in Milkdown editor for student | ProseMirror capture-phase interception must be verified in real browser | See Phase 4 UAT below |
| AC4.9 | Copy from Milkdown editor (student's own writing) still works | Must verify that copy is NOT blocked in editor area | See Phase 4 UAT below |
| AC4.10 | Text selection for highlighting unaffected by protection | Core workflow must be verified visually | See Phase 4 UAT below |
| AC4.11 | Debounced toast notification shown on blocked action | Toast rendering and debounce timing require visual verification | See Phase 4 UAT below |

### AC6: Student-facing indicator (visual)

| AC | Description | Why Manual | Steps |
|----|-------------|-----------|-------|
| AC6.1 | Lock icon chip visible in header when protection active | Visual rendering of chip position, icon, and color | See Phase 4 UAT below |
| AC6.2 | Lock chip tooltip reads "Copy protection is enabled for this activity" | Tooltip content and trigger require hover interaction | See Phase 4 UAT below |

### AC7: Instructor UI (interactive dialogs)

| AC | Description | Why Manual | Steps |
|----|-------------|-----------|-------|
| AC7.1 | Course settings shows "Default copy protection" toggle | Dialog rendering, toggle interaction, persistence | See Phase 6 UAT below |
| AC7.2 | Activity settings shows tri-state "Copy protection" control | Dialog rendering, select interaction | See Phase 6 UAT below |

---

## Human Test Plan

### Prerequisites

- PostgreSQL running with `DATABASE_URL` configured
- `uv run alembic upgrade head` applied (Phase 1 migration)
- `uv run seed-data` completes without error
- `uv run test-all` passes (all automated tests green)
- Two browser sessions available: one for instructor role, one for student role

### Phase 1 UAT: Data Model & Migration

| Step | Action | Expected |
|------|--------|----------|
| 1 | Run `uv run alembic current` | Shows the copy protection migration as head |
| 2 | Run `uv run python -m promptgrimoire` | App starts without error |
| 3 | Run `uv run seed-data` | Completes without error (existing seed path defaults `copy_protection` to NULL) |
| 4 | Run `uv run test-all` | All pass, including `TestCopyProtectionResolution` tests |

### Phase 2 UAT: Activity CRUD

| Step | Action | Expected |
|------|--------|----------|
| 1 | Run `uv run test-all` | All pass, including new CRUD round-trip tests in `TestActivityCRUD` |
| 2 | Run `uv run python -m promptgrimoire` | App starts without error |
| 3 | Run `uv run seed-data` | Completes without error |

### Phase 3 UAT: Role Check & Protection Decision

| Step | Action | Expected |
|------|--------|----------|
| 1 | Run `uv run test-all` | All pass, including `TestIsPrivilegedUser` tests |
| 2 | Run `uv run python -m promptgrimoire` | App starts without error |
| 3 | Enable copy protection on seed activity via SQL: `UPDATE activity SET copy_protection = true WHERE title = 'Annotate Becky Bennett Interview';` | Row updated |
| 4 | As instructor: navigate to annotation page for the protected activity | No copy protection JS in DevTools console, `protect=False` in server logs (temporary debug line) |
| 5 | As student: navigate to same annotation page | `protect=True` in server logs (temporary debug line) |

### Phase 4 UAT: Client-Side Copy/Paste/Drag Protection

| Step | Action | Expected |
|------|--------|----------|
| 1 | Run `uv run test-all` | All pass |
| 2 | Run `uv run seed-data` | Completes without error |
| 3 | As student, navigate to annotation page for a protected activity | Lock icon chip with amber background visible in workspace header |
| 4 | Hover over lock chip | Tooltip reads "Copy protection is enabled for this activity" |
| 5 | Select text in Tab 1 document content, press Ctrl+C | Copy blocked; toast notification "Copying is disabled for this activity." appears top-right |
| 6 | Rapidly press Ctrl+C 5 times | Only one toast visible (debounce via Quasar `group` key) |
| 7 | Select text in Tab 1 document, press Ctrl+X | Cut blocked; toast shown |
| 8 | Right-click on Tab 1 document content | Context menu does NOT appear; toast shown |
| 9 | Try to drag-select and drag text out of Tab 1 document | Drag blocked; toast shown |
| 10 | Switch to Tab 2 (Organise), select text on a highlight card, press Ctrl+C | Copy blocked; toast shown |
| 11 | Switch to Tab 3 (Respond), select text on a reference card, press Ctrl+C | Copy blocked; toast shown |
| 12 | In Milkdown editor on Tab 3, type "Hello world", select it, press Ctrl+C | Copy WORKS (student's own writing is not protected) |
| 13 | In Milkdown editor, press Ctrl+V (with clipboard content) | Paste blocked; toast shown |
| 14 | On Tab 1, select text and use highlighting tool | Text selection and highlighting work normally -- protection does not interfere |
| 15 | As instructor, navigate to the same protected activity | No lock chip visible, copy/paste/drag all work normally |
| 16 | Navigate to a loose workspace (no activity association) | No lock chip, no copy protection active |

### Phase 5 UAT: Print Suppression

| Step | Action | Expected |
|------|--------|----------|
| 1 | Run `uv run test-all` | All pass |
| 2 | As student, navigate to annotation page for a protected activity | Page loads normally |
| 3 | Press Ctrl+P (or Cmd+P on Mac) | Print dialog does NOT open; toast notification shown |
| 4 | Use browser menu File > Print | Print preview shows "Printing is disabled for this activity." message instead of tab panel content |
| 5 | As instructor, navigate to same protected activity | Page loads normally |
| 6 | Press Ctrl+P | Print dialog opens normally |
| 7 | Print preview | Shows normal content (no suppression message) |

### Phase 6 UAT: Instructor UI

| Step | Action | Expected |
|------|--------|----------|
| 1 | Run `uv run test-all` | All pass |
| 2 | Run `uv run seed-data` | Completes without error |
| 3 | Navigate to course detail page | Gear icon visible in course header |
| 4 | Click gear icon | Course settings dialog opens |
| 5 | Verify "Default copy protection" toggle is visible | Toggle reflects current course state (True after seed-data) |
| 6 | Toggle from True to False, click Save | Notification "Course settings saved" appears |
| 7 | Reload page, click gear icon again | Toggle state persisted as False |
| 8 | On course page, find an activity row | "Tune" icon visible on the row |
| 9 | Click tune icon on an activity | Activity settings dialog opens |
| 10 | Verify "Copy protection" select is visible | Shows tri-state: "Inherit from course" / "On" / "Off" |
| 11 | For a new activity (not explicitly overridden), verify select value | Shows "Inherit from course" (AC7.3) |
| 12 | Change select to "On", click Save | Notification "Activity settings saved" appears |
| 13 | Reload page, click tune icon on same activity | Select shows "On" (persisted) |
| 14 | Navigate to annotation page for that activity as student | Lock chip visible, copy protection active (AC7.4) |
| 15 | Return to course page, click tune icon, change to "Inherit from course", Save | Notification shown |
| 16 | Navigate to annotation page again as student | Copy protection state matches course default (AC7.5) |

### End-to-End: Full inheritance chain

**Purpose:** Verify that the tri-state inheritance model works dynamically across the full Course > Activity > Workspace chain.

| Step | Action | Expected |
|------|--------|----------|
| 1 | As instructor, set course `default_copy_protection=False` | Saved |
| 2 | Create a new activity (or reset existing to "Inherit from course") | Activity `copy_protection=NULL` |
| 3 | As student, navigate to annotation page for that activity | No lock chip, no copy protection |
| 4 | As instructor, change course `default_copy_protection=True` | Saved |
| 5 | As student, reload annotation page for same activity | Lock chip appears, copy protection active (dynamic inheritance) |
| 6 | As instructor, set activity to explicit "Off" | Activity `copy_protection=False` |
| 7 | As student, reload annotation page | No lock chip, no copy protection (explicit override wins) |
| 8 | As instructor, change course default back to False | Saved |
| 9 | As student, reload annotation page | Still no copy protection (explicit False unchanged) |
| 10 | As instructor, reset activity to "Inherit from course" | Activity `copy_protection=NULL` |
| 11 | As student, reload annotation page | No copy protection (course default is False) |

### End-to-End: Role-based bypass verification

**Purpose:** Verify that privileged users are never subject to copy protection, regardless of activity/course settings.

| Step | Action | Expected |
|------|--------|----------|
| 1 | Set activity `copy_protection=True` explicitly | Saved |
| 2 | As admin user, navigate to annotation page | No lock chip, all copy/paste/drag operations work |
| 3 | As instructor, navigate to annotation page | No lock chip, all operations work |
| 4 | As student, navigate to annotation page | Lock chip visible, copy/paste/drag blocked |
| 5 | As tutor, navigate to annotation page | Lock chip visible, copy/paste/drag blocked (tutors are not privileged) |

---

## Traceability Matrix

| Acceptance Criterion | Automated Test | Manual Step |
|----------------------|----------------|-------------|
| AC1.1 | `tests/integration/test_workspace_placement.py::TestCopyProtectionResolution` | P1 UAT step 4 |
| AC1.2 | `tests/integration/test_workspace_placement.py::TestCopyProtectionResolution` | P1 UAT step 4 |
| AC1.3 | `tests/integration/test_workspace_placement.py::TestCopyProtectionResolution` | P1 UAT step 4 |
| AC1.4 | `tests/integration/test_workspace_placement.py::TestCopyProtectionResolution` | P1 UAT step 4 |
| AC2.1 | `tests/integration/test_workspace_placement.py::TestCopyProtectionResolution` | P1 UAT step 4 |
| AC2.2 | `tests/integration/test_workspace_placement.py::TestCopyProtectionResolution` | P1 UAT step 4 |
| AC2.3 | `tests/integration/test_workspace_placement.py::TestCopyProtectionResolution` | P1 UAT step 4 |
| AC2.4 | `tests/integration/test_workspace_placement.py::TestCopyProtectionResolution` | P1 UAT step 4 |
| AC3.1 | `tests/integration/test_workspace_placement.py::TestCopyProtectionResolution` | P1 UAT step 4 |
| AC3.2 | `tests/integration/test_workspace_placement.py::TestCopyProtectionResolution` | P1 UAT step 4 |
| AC3.3 | `tests/integration/test_workspace_placement.py::TestCopyProtectionResolution` | P1 UAT step 4 |
| AC3.4 | `tests/integration/test_workspace_placement.py::TestCopyProtectionResolution` | P1 UAT step 4 |
| AC3.5 | `tests/integration/test_workspace_placement.py::TestCopyProtectionResolution` | P1 UAT step 4 |
| AC3.6 | `tests/integration/test_workspace_placement.py::TestCopyProtectionResolution` | P1 UAT step 4 |
| AC3.7 | `tests/integration/test_workspace_placement.py::TestCopyProtectionResolution` | P1 UAT step 4 |
| AC4.1 | -- (browser-level) | P4 UAT step 5 |
| AC4.2 | -- (browser-level) | P4 UAT step 10 |
| AC4.3 | -- (browser-level) | P4 UAT step 11 |
| AC4.4 | -- (browser-level) | P4 UAT step 7 |
| AC4.5 | -- (browser-level) | P4 UAT step 8 |
| AC4.6 | `tests/unit/test_copy_protection_js.py` (injection boundary only) | P5 UAT steps 3--4 |
| AC4.7 | -- (browser-level) | P4 UAT step 9 |
| AC4.8 | -- (browser-level) | P4 UAT step 13 |
| AC4.9 | -- (browser-level) | P4 UAT step 12 |
| AC4.10 | -- (browser-level) | P4 UAT step 14 |
| AC4.11 | -- (browser-level) | P4 UAT steps 5--6 |
| AC4.12 | `tests/unit/test_copy_protection_js.py` | P4 UAT step 16 |
| AC4.13 | `tests/unit/test_copy_protection_js.py` | P4 UAT step 16 |
| AC5.1 | `tests/unit/test_auth_roles.py::TestIsPrivilegedUser` | E2E role bypass step 2 |
| AC5.2 | `tests/unit/test_auth_roles.py::TestIsPrivilegedUser` | E2E role bypass step 3 |
| AC5.3 | `tests/unit/test_auth_roles.py::TestIsPrivilegedUser` | -- |
| AC5.4 | `tests/unit/test_auth_roles.py::TestIsPrivilegedUser` | E2E role bypass step 4 |
| AC5.5 | `tests/unit/test_auth_roles.py::TestIsPrivilegedUser` | E2E role bypass step 5 |
| AC5.6 | `tests/unit/test_auth_roles.py::TestIsPrivilegedUser` | -- |
| AC6.1 | -- (visual rendering) | P4 UAT step 3 |
| AC6.2 | -- (visual rendering) | P4 UAT step 4 |
| AC6.3 | `tests/unit/test_copy_protection_js.py` | P4 UAT step 15 |
| AC7.1 | -- (dialog interaction) | P6 UAT steps 3--7 |
| AC7.2 | -- (dialog interaction) | P6 UAT steps 8--10 |
| AC7.3 | `tests/unit/test_copy_protection_ui.py` (mapping fn only) | P6 UAT step 11 |
| AC7.4 | `tests/unit/test_copy_protection_ui.py` (mapping fn only) | P6 UAT steps 12--14 |
| AC7.5 | `tests/unit/test_copy_protection_ui.py` (mapping fn only) | P6 UAT steps 15--16 |

---

## Test File Summary

| Test File | Type | Phase | AC Coverage | Test Class |
|-----------|------|-------|-------------|------------|
| `tests/integration/test_workspace_placement.py` | Integration | P1 | AC1.1--AC1.4, AC2.1--AC2.4, AC3.1--AC3.7 | `TestCopyProtectionResolution` |
| `tests/integration/test_activity_crud.py` | Integration | P2 | (extends AC1 through CRUD layer) | `TestActivityCRUD` |
| `tests/unit/test_auth_roles.py` | Unit | P3 | AC5.1--AC5.6 | `TestIsPrivilegedUser` |
| `tests/unit/test_copy_protection_js.py` | Unit | P4, P5 | AC4.6 (partial), AC4.12, AC4.13, AC6.3 | `TestCopyProtectionConditions` |
| `tests/unit/test_copy_protection_ui.py` | Unit | P6 | AC7.3--AC7.5 (mapping fns) | (pure function tests) |
| `tests/integration/test_course_service.py` | Integration | P6 | (infrastructure for AC7.1) | (update_course tests) |
