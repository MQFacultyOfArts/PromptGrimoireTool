# WIP State — Workspace ACL (#96)

**Last updated:** 2026-02-16
**Branch:** `96-workspace-acl`
**HEAD:** See `git log --oneline -5`

## Completed Phases

| Phase | Name | Status | UAT |
|-------|------|--------|-----|
| 1 | Reference Tables (Permission, CourseRole) | Done | Confirmed |
| 2 | CourseRole Normalisation | Done | Confirmed |
| 3 | ACL Model (ACLEntry) | Done | Confirmed |
| 4 | Permission Resolution | Done | No human UAT needed (pure backend logic, all automated tests) |

## In Progress: Phase 5 — Ownership at Clone

**Subcomponent A (Tasks 1-2): COMMITTED** (`488f7cd`)
- `get_user_workspace_for_activity()` added to `db/workspaces.py`
- `clone_workspace_from_activity()` updated with `user_id` param + atomic owner ACLEntry
- All existing clone tests updated to pass `user_id`

**Subcomponent B (Tasks 3-4): WIP COMMITTED** (`ab1c2a2`)
- `check_clone_eligibility()` added to `db/workspaces.py` — validates enrollment + week visibility
- `start_activity()` updated with full auth/enrollment/duplicate detection flow
- `tests/integration/test_clone_eligibility.py` created
- **Not yet reviewed.** Pre-commit hooks pass (ruff + ty). Integration tests not run (no test DB in this env).

**Subcomponent C (Tasks 5-6): NOT STARTED**
- Task 5: Update `db/__init__.py` exports
- Task 6: Integration tests for clone ownership (AC7.1-AC7.6)

### Resume instructions

```bash
cd .worktrees/96-workspace-acl
git log --oneline -5  # verify HEAD
# Review the WIP commit (ab1c2a2) — may need adjustments
# Then: "Continue with Phase 5 Subcomponent C, then code review"
```

## Remaining Phases

| Phase | Name | File |
|-------|------|------|
| 5 | Ownership at Clone (in progress) | `phase_05.md` |
| 6 | Sharing Controls | `phase_06.md` |
| 7 | Listing Queries | `phase_07.md` |
| 8 | Enforcement and Revocation | `phase_08.md` |

## Key Design Decisions Made During Implementation

- **`is_staff` boolean on `course_role`**: User directed — no magic numbers, no level thresholds. Boolean per policy, cached in memory via `get_staff_roles()` in `db/roles.py` (process-lifetime cache, queries DB once).
- **`_STAFF_ROLES` eliminated**: Was hardcoded in 3 files (`acl.py`, `weeks.py`, `courses.py`). Now all derive from `get_staff_roles()`.
- **`_MANAGER_ROLES`** in `pages/courses.py` remains as a separate hardcoded frozenset — different policy (page-level UI filtering), no `is_manager` column yet. Noted for future if needed.
- **`check_clone_eligibility()` should use `get_staff_roles()`** from `db/roles.py` instead of hardcoded staff set — consistent with Phase 4 decision. (Noted in Task 3 dispatch.)

## CLAUDE.md Refactoring

Two commits (cherry-pickable to main):
- `2972023` — docs: extract subsystem documentation into dedicated docs files
- `aa65cba` — refactor: reduce CLAUDE.md from 555 to 172 lines

## Test State

2370 passed, 181 skipped (`uv run test-all` on 2026-02-16). All integration tests skip due to no `DEV__TEST_DATABASE_URL`.
