# Workspace Sharing & Visibility — Phase 2: Permission Resolution Extension

**Goal:** Enrollment-based peer access in the hybrid permission resolver.

**Architecture:** Extend `_derive_enrollment_permission` with a student path: if enrolled student + activity allows sharing + workspace opted in → return "peer". Add `list_peer_workspaces` query for the discovery page (Phase 6). Tri-state `allow_sharing` resolved inline using activity + course objects already loaded in the function.

**Tech Stack:** SQLModel, PostgreSQL, async SQLAlchemy

**Scope:** 7 phases from original design (phase 2 of 7)

**Codebase verified:** 2026-02-19

**Dependencies:** Phase 1 (model fields: `shared_with_class`, `allow_sharing`, `anonymous_sharing`)

---

## Acceptance Criteria Coverage

This phase implements and tests:

### workspace-sharing-97.AC2: Enrollment-based discovery
- **workspace-sharing-97.AC2.1 Success:** Student enrolled in course gets peer access to workspace where activity.allow_sharing=True AND workspace.shared_with_class=True
- **workspace-sharing-97.AC2.2 Success:** Explicit ACL entry with higher permission (e.g. editor) wins over enrollment-derived peer
- **workspace-sharing-97.AC2.3 Success:** Student's own workspace returns owner (from ACL), not peer
- **workspace-sharing-97.AC2.4 Failure:** Student not enrolled in course gets None (no access)
- **workspace-sharing-97.AC2.5 Failure:** Student enrolled but activity.allow_sharing=False gets None
- **workspace-sharing-97.AC2.6 Failure:** Student enrolled but workspace.shared_with_class=False gets None
- **workspace-sharing-97.AC2.7 Edge:** Loose workspace (no activity_id) — only explicit ACL grants access, no enrollment derivation
- **workspace-sharing-97.AC2.8 Edge:** Course-placed workspace (course_id set, no activity_id) — no peer discovery

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: Extend `_derive_enrollment_permission` with student peer path

**Verifies:** workspace-sharing-97.AC2.1, workspace-sharing-97.AC2.5, workspace-sharing-97.AC2.6, workspace-sharing-97.AC2.7, workspace-sharing-97.AC2.8

**Files:**
- Modify: `src/promptgrimoire/db/acl.py:264-267` (replace student `return None` with conditional peer path)

**Implementation:**

Currently at lines 264-267, after the staff role check:
```python
if enrollment.role not in staff_roles:
    return None
```

Replace with a student peer path. The three conditions for peer access are:
1. `workspace.activity_id is not None` (activity-placed — guards access to `activity` object loaded at line 240)
2. Resolved `allow_sharing` is `True` (tri-state: `activity.allow_sharing if not None else course.default_allow_sharing`)
3. `workspace.shared_with_class` is `True`

If all three conditions are met, return `"peer"`. Otherwise return `None`.

The `workspace` object is already loaded at line 231. The `activity` object is loaded at line 240 (only in the `workspace.activity_id is not None` branch). The `course` object needs to be loaded for the student path — currently it's only loaded at line 271 in the staff branch. Move the `course` fetch earlier (before the staff/student branch) so both paths can use it.

Note: the current code loads `course` at line 271 only in the staff path. The refactored version must load `course` before the role check so the student path can resolve `allow_sharing` against `course.default_allow_sharing`.

**Testing:**

Integration tests in `tests/integration/test_permission_resolution.py`. Add new test classes following the existing pattern (inline imports, UUID tag isolation, class-per-scenario):

- `TestStudentPeerAccess` — workspace-sharing-97.AC2.1: enrolled student + allow_sharing=True + shared_with_class=True → `"peer"`
- `TestStudentPeerDenied` — workspace-sharing-97.AC2.5: allow_sharing=False → None; workspace-sharing-97.AC2.6: shared_with_class=False → None
- `TestStudentPeerTriState` — workspace-sharing-97.AC2.1 variant: activity.allow_sharing=None + course.default_allow_sharing=True → "peer" (tri-state inheritance)
- `TestStudentPeerLooseWorkspace` — workspace-sharing-97.AC2.7: loose workspace + shared_with_class=True → None (no activity means no peer path)
- `TestStudentPeerCoursePlaced` — workspace-sharing-97.AC2.8: course-placed workspace + shared_with_class=True → None

Each test creates its own user/course/activity/workspace hierarchy with UUID tags for isolation.

**Verification:**
Run: `uv run pytest tests/integration/test_permission_resolution.py -v`
Expected: All tests pass (existing + new)

**Commit:** `feat(acl): add student peer access path in enrollment resolution`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Verify highest-wins and own-workspace resolution

**Verifies:** workspace-sharing-97.AC2.2, workspace-sharing-97.AC2.3, workspace-sharing-97.AC2.4

**Files:**
- Modify: `tests/integration/test_permission_resolution.py` (add test classes)

**Implementation:**

No code changes needed — the existing `_resolve_permission_with_session` highest-wins logic (lines 304-314) already compares Permission.level values and returns the higher one. The `"peer"` permission (level 15) will naturally lose to `"editor"` (level 20) or `"owner"` (level 30) via the existing comparison.

**Testing:**

Add test classes:
- `TestPeerVsExplicitACL` — workspace-sharing-97.AC2.2: student with explicit editor ACL + peer conditions met → `"editor"` (explicit wins)
- `TestOwnWorkspacePeer` — workspace-sharing-97.AC2.3: student who is owner (via ACL) of their workspace + peer conditions met → `"owner"` (ACL wins)
- `TestUnenrolledStudentPeer` — workspace-sharing-97.AC2.4: user not enrolled in course but workspace is shared → `None`

**Verification:**
Run: `uv run pytest tests/integration/test_permission_resolution.py -v`
Expected: All tests pass

**Commit:** `test(acl): verify peer vs explicit ACL and own-workspace resolution`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add `list_peer_workspaces` query

**Verifies:** workspace-sharing-97.AC2.1 (discovery aspect — used by Phase 6)

**Files:**
- Modify: `src/promptgrimoire/db/acl.py` (add new async function after existing functions)
- Create: `tests/integration/test_peer_discovery.py`

**Implementation:**

Add `list_peer_workspaces(activity_id: UUID, exclude_user_id: UUID) -> list[Workspace]`:
- Query: `SELECT * FROM workspace WHERE activity_id = :activity_id AND shared_with_class = true AND id NOT IN (SELECT workspace_id FROM acl_entry WHERE user_id = :exclude_user_id AND permission = 'owner')`
- Excludes: template workspaces (WHERE workspace.id NOT IN SELECT template_workspace_id FROM activity), the requesting user's own workspaces (via ACL owner check)
- Returns: list of Workspace objects
- Note: This is a direct query, not N+1 resolve_permission calls. Used by the peer discovery UI (Phase 6).

The query does NOT check enrollment or allow_sharing — the caller (Phase 6 UI code) is responsible for gating visibility based on PlacementContext.allow_sharing. This function just finds the workspaces that have opted into sharing for a given activity.

**Testing:**

Integration tests verifying:
- Returns shared workspaces for an activity
- Excludes workspaces where shared_with_class=False
- Excludes the requesting user's own workspace(s)
- Excludes template workspaces
- Returns empty list when no workspaces are shared
- Workspaces from other activities not included

**Verification:**
Run: `uv run test-debug`
Expected: All tests pass

**Commit:** `feat(acl): add list_peer_workspaces query for discovery`
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->
