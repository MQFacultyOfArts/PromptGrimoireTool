# Human Test Plan: Per-Activity Copy Protection (103-copy-protection)

## Prerequisites

- PostgreSQL running with `DATABASE_URL` configured
- `uv run alembic upgrade head` applied (all migrations including copy protection)
- `uv run seed-data` completes without error
- `uv run test-all` passes (2427 tests, 2 skipped)
- Two browser sessions: one as instructor/admin, one as student
- Browser DevTools accessible

## Phase 4: Client-Side Copy/Paste/Drag Protection

| Step | Action | Expected |
|------|--------|----------|
| 1 | As student, navigate to annotation page for protected activity | Lock icon chip (amber, "Protected") visible in header |
| 2 | Hover lock chip | Tooltip: "Copy protection is enabled for this activity" |
| 3 | Tab 1: select text, press Ctrl+C | Blocked; toast "Copying is disabled for this activity." |
| 4 | Rapidly press Ctrl+C 5 times | Only one toast visible (Quasar group deduplication) |
| 5 | Tab 1: select text, press Ctrl+X | Blocked; toast shown |
| 6 | Tab 1: right-click on document | Context menu blocked; toast shown |
| 7 | Tab 1: drag selected text | Drag blocked; toast shown |
| 8 | Tab 2: select text on organise card, Ctrl+C | Blocked; toast shown |
| 9 | Tab 3: select text on reference card, Ctrl+C | Blocked; toast shown |
| 10 | Tab 3: type in Milkdown editor, select, Ctrl+C | Copy WORKS (own writing not protected) |
| 11 | Tab 3: Ctrl+V into Milkdown editor | Blocked; toast shown |
| 12 | Tab 1: select text, use highlighting tool | Selection and highlighting work normally |
| 13 | As instructor, navigate to same activity | No lock chip; copy/paste/drag all work |
| 14 | Navigate to loose workspace | No lock chip; no protection |

## Phase 5: Print Suppression

| Step | Action | Expected |
|------|--------|----------|
| 1 | As student on protected activity, press Ctrl+P | Print dialog blocked; toast shown |
| 2 | Use File > Print menu | Print preview shows "Printing is disabled for this activity." |
| 3 | As instructor, Ctrl+P on same activity | Print dialog opens normally |
| 4 | Instructor print preview | Normal page content shown |

## Phase 6: Instructor UI Controls

| Step | Action | Expected |
|------|--------|----------|
| 1 | As instructor, course detail page | Gear icon visible in header |
| 2 | Click gear icon | Course settings dialog opens |
| 3 | Verify "Default copy protection" toggle | Reflects current state |
| 4 | Toggle, click Save | "Course settings saved" notification |
| 5 | Reload, reopen dialog | Toggle state persisted |
| 6 | Find activity row | Tune icon visible |
| 7 | Click tune icon | Activity settings dialog opens |
| 8 | Verify "Copy protection" select | 3 options: Inherit from course / On / Off |
| 9 | New activity shows "Inherit from course" | Default state correct |
| 10 | Change to "On", Save | "Activity settings saved" notification |
| 11 | Reload, reopen | Shows "On" (persisted) |
| 12 | Change to "Inherit from course", Save | Notification shown |

## End-to-End: Full Inheritance Chain

| Step | Action | Expected |
|------|--------|----------|
| 1 | Instructor: set course default OFF | Saved |
| 2 | Reset activity to "Inherit from course" | Saved |
| 3 | Student: visit annotation page | No lock chip; copy works |
| 4 | Instructor: set course default ON | Saved |
| 5 | Student: reload same page | Lock chip appears; copy blocked (dynamic inheritance) |
| 6 | Instructor: set activity to explicit "Off" | Saved |
| 7 | Student: reload | No lock chip (explicit override wins) |
| 8 | Instructor: set course default OFF | Saved |
| 9 | Instructor: reset activity to "Inherit" | Saved |
| 10 | Student: reload | No protection (inherits course default=False) |

## End-to-End: Role-Based Bypass

| Step | Action | Expected |
|------|--------|----------|
| 1 | Set activity to explicit On | Saved |
| 2 | Admin user visits annotation page | No lock chip; everything works |
| 3 | Instructor visits same page | No lock chip; everything works |
| 4 | Student visits same page | Lock chip; copy blocked |
| 5 | Tutor visits same page | Lock chip; copy blocked (tutors not privileged) |

## Acceptance Criteria Traceability

| AC | Automated Test | Manual Step |
|----|---------------|-------------|
| AC1.1-AC1.4 | `test_workspace_placement.py::TestCopyProtectionResolution` | - |
| AC2.1-AC2.4 | `test_workspace_placement.py::TestCopyProtectionResolution` | - |
| AC3.1-AC3.7 | `test_workspace_placement.py::TestCopyProtectionResolution` | E2E inheritance chain |
| AC4.1 | - | Phase 4 step 3 |
| AC4.2 | - | Phase 4 step 8 |
| AC4.3 | - | Phase 4 step 9 |
| AC4.4 | - | Phase 4 step 5 |
| AC4.5 | - | Phase 4 step 6 |
| AC4.6 | `test_copy_protection_js.py::TestPrintSuppressionInjection` | Phase 5 steps 1-2 |
| AC4.7 | - | Phase 4 step 7 |
| AC4.8 | - | Phase 4 step 11 |
| AC4.9 | - | Phase 4 step 10 |
| AC4.10 | - | Phase 4 step 12 |
| AC4.11 | - | Phase 4 step 4 |
| AC4.12 | `test_copy_protection_js.py::test_ac4_12` | Phase 4 step 14 |
| AC4.13 | `test_copy_protection_js.py::test_ac4_13` | Phase 4 step 14 |
| AC5.1-AC5.6 | `test_auth_roles.py::TestIsPrivilegedUser` | E2E role bypass |
| AC6.1-AC6.2 | - | Phase 4 steps 1-2 |
| AC6.3 | `test_copy_protection_js.py::TestRenderWorkspaceHeaderSignature` | Phase 4 step 13 |
| AC7.1 | - | Phase 6 steps 1-5 |
| AC7.2 | - | Phase 6 steps 6-8 |
| AC7.3 | `test_copy_protection_ui.py::test_none_returns_inherit` | Phase 6 step 9 |
| AC7.4 | `test_copy_protection_ui.py::test_on_returns_true` | Phase 6 steps 10-11 |
| AC7.5 | `test_copy_protection_ui.py::test_inherit_returns_none` | Phase 6 step 12 |
