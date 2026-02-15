# WIP State — Workspace ACL (#96)

**Last updated:** 2026-02-15
**Branch:** `96-workspace-acl`
**HEAD:** See `git log --oneline -5`

## Completed Phases

| Phase | Name | Status | UAT |
|-------|------|--------|-----|
| 1 | Reference Tables (Permission, CourseRole) | Done | Confirmed |
| 2 | CourseRole Normalisation | Done | Confirmed |
| 3 | ACL Model (ACLEntry) | Done | Confirmed |
| 4 | Permission Resolution | Done | Confirmed |

## Key Design Decisions Made During Implementation

- **`is_staff` boolean on `course_role`**: User directed — no magic numbers, no level thresholds. Boolean per policy, cached in memory via `get_staff_roles()` in `db/roles.py` (process-lifetime cache, queries DB once).
- **`_STAFF_ROLES` eliminated**: Was hardcoded in 3 files (`acl.py`, `weeks.py`, `courses.py`). Now all derive from `get_staff_roles()`.
- **`_MANAGER_ROLES`** in `pages/courses.py` remains as a separate hardcoded frozenset — different policy (page-level UI filtering), no `is_manager` column yet. Noted for future if needed.

## Next: Phase 5 — Ownership at Clone

Read `phase_05.md` and execute. This phase adds ACL owner grants when workspaces are cloned.

## Remaining Phases

| Phase | Name | File |
|-------|------|------|
| 5 | Ownership at Clone | `phase_05.md` |
| 6 | Sharing Controls | `phase_06.md` |
| 7 | Listing Queries | `phase_07.md` |
| 8 | Enforcement and Revocation | `phase_08.md` |

## CLAUDE.md Refactoring

Two commits (cherry-pickable to main):
- `2972023` — docs: extract subsystem documentation into dedicated docs files
- `aa65cba` — refactor: reduce CLAUDE.md from 555 to 172 lines

New docs created: `export.md`, `input-pipeline.md`, `annotation-architecture.md`, `configuration.md`, `copy-protection.md`, `worktrees.md`. Existing docs updated: `database.md`, `testing.md`, `_index.md`.

## Test State

All 2551 tests pass (`uv run test-all`).

## How to Resume

```bash
cd .worktrees/96-workspace-acl
git log --oneline -5  # verify HEAD
uv run test-debug     # verify tests pass
# Then: "Continue with Phase 5 of the workspace ACL implementation plan"
```
