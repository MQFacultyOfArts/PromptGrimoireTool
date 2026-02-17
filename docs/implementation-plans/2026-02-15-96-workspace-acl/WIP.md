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
| 5 | Ownership at Clone | Done | Code reviewed, no issues |
| 6 | Sharing Controls | Done | 2599 passed |
| 7 | Listing Queries | Done | 2608 passed |
| 8 | Enforcement and Revocation | Done | 2628 passed |

## All Phases Complete

All 8 phases of the workspace ACL implementation are done. Pending: human UAT and PR.

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
