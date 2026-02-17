# Workspace ACL Design

**GitHub Issue:** #96

## Summary

This design implements fine-grained access control for workspaces through a hybrid permission model. The system combines explicit access grants (via Access Control Lists) with access derived from course enrollment and role hierarchy. When a student clones a workspace from an activity, they become its owner and can optionally share it with peers if the course settings allow. Instructors gain automatic access to all student workspaces within their courses. ACL entries link directly to workspaces via FK; when future resource types need ACL (e.g., roleplay sessions), a new FK column is added to ACLEntry with a mutual exclusivity CHECK constraint — the same pattern used for Workspace placement (`activity_id`/`course_id`).

The design replaces the existing `CourseRole` string enumeration with a reference table pattern, establishing a precedent for domain value sets that may grow over time. Reference tables use string PKs (`name` is the primary key) — no UUIDs for reference data whose identity is the name itself. Permission resolution follows a precedence chain: administrator override (via Stytch roles) → highest of explicit ACL or enrollment-derived access → deny by default. Real-time access revocation is achieved through websocket-based push notifications to connected clients, enabling instructors to immediately revoke access without requiring page refresh. The sharing controls follow the existing copy-protection tri-state pattern, allowing per-activity overrides of course-level defaults.

## Definition of Done

1. **Reference tables** — `Permission` (owner/editor/viewer) and `CourseRole` (coordinator/instructor/tutor/student) as reference tables with string PKs (`name`), FK relationships, and `level` columns for ordering; replacing the `CourseRole` StrEnum
2. **ACL model** — `ACLEntry` table with FKs to Workspace, User, and Permission (string FK); unique constraint on (workspace_id, user_id)
3. **Permission resolution** — `resolve_permission(workspace_id, user_id)` implementing a hybrid model: checks explicit ACL entries and enrollment-derived access, returns the highest applicable permission; admin bypass via Stytch roles; default deny
4. **Ownership at clone** — when a student clones a workspace from an activity, an ACLEntry with owner permission is created atomically
5. **Sharing controls** — `allow_sharing` tri-state on Activity + default on Course (follows copy-protection pattern); owner can grant editor or viewer access to other students when sharing is enabled
6. **Listing queries** — "my workspaces" (via ACL entries), "course workspaces" (via hierarchy + loose placement), "activity workspaces", "user workspace for activity"
7. **Enforcement points** — guard function at workspace page entry points with push redirect via websocket for real-time revocation
8. **Clean migration** — no data preservation; reference table seed data in migration

## Acceptance Criteria

### 96-workspace-acl.AC1: Reference tables exist with correct seed data
- **96-workspace-acl.AC1.1 Success:** Permission table contains owner (level 30), editor (level 20), viewer (level 10) with string PKs
- **96-workspace-acl.AC1.2 Success:** CourseRole table contains coordinator (40), instructor (30), tutor (20), student (10) with string PKs
- **96-workspace-acl.AC1.3 Success:** Reference table rows are created by the migration, not seed-data script
- **96-workspace-acl.AC1.4 Failure:** Duplicate name INSERT into Permission or CourseRole is rejected (PK constraint)
- **96-workspace-acl.AC1.5 Success:** Level columns have CHECK constraints (BETWEEN 1 AND 100) and are UNIQUE within each table

### 96-workspace-acl.AC3: CourseRole normalisation
- **96-workspace-acl.AC3.1 Success:** CourseEnrollment uses `role` string FK to CourseRole table (ondelete=RESTRICT)
- **96-workspace-acl.AC3.2 Success:** Week visibility logic works identically after normalisation (coordinators/instructors/tutors see all weeks, students see only published)
- **96-workspace-acl.AC3.3 Success:** Enrollment CRUD functions accept role by name (string FK lookup)
- **96-workspace-acl.AC3.4 Failure:** Enrolling with an invalid role name is rejected (FK constraint)

### 96-workspace-acl.AC4: ACLEntry model
- **96-workspace-acl.AC4.1 Success:** ACLEntry can be created with valid workspace_id, user_id, permission (string FK)
- **96-workspace-acl.AC4.2 Success:** Deleting a Workspace CASCADEs to its ACLEntry rows
- **96-workspace-acl.AC4.3 Success:** Deleting a User CASCADEs to their ACLEntry rows
- **96-workspace-acl.AC4.4 Failure:** Duplicate (workspace_id, user_id) pair is rejected (UNIQUE constraint)
- **96-workspace-acl.AC4.5 Edge:** Granting a new permission to an existing (workspace_id, user_id) pair upserts the permission

### 96-workspace-acl.AC5: ACL CRUD operations
- **96-workspace-acl.AC5.1 Success:** Grant permission to a user on a workspace
- **96-workspace-acl.AC5.2 Success:** Revoke permission (delete ACLEntry)
- **96-workspace-acl.AC5.3 Success:** List all ACL entries for a workspace
- **96-workspace-acl.AC5.4 Success:** List all ACL entries for a user

### 96-workspace-acl.AC6: Permission resolution
- **96-workspace-acl.AC6.1 Success:** User with explicit ACL entry gets that permission level
- **96-workspace-acl.AC6.2 Success:** Instructor enrolled in course gets Course.default_instructor_permission for workspaces in that course
- **96-workspace-acl.AC6.3 Success:** Coordinator enrolled in course gets access (same as instructor)
- **96-workspace-acl.AC6.4 Success:** Tutor enrolled in course gets access (same as instructor)
- **96-workspace-acl.AC6.5 Success:** When both explicit ACL and enrollment-derived access exist, the higher permission level wins
- **96-workspace-acl.AC6.6 Success:** Admin (via Stytch) gets owner-level access regardless of ACL/enrollment
- **96-workspace-acl.AC6.7 Failure:** Student enrolled in course but without explicit ACL entry gets None (no access to others' workspaces)
- **96-workspace-acl.AC6.8 Failure:** Unenrolled user with no ACL entry gets None
- **96-workspace-acl.AC6.9 Failure:** User with no auth session gets None
- **96-workspace-acl.AC6.10 Edge:** Workspace with no activity_id (loose) — only explicit ACL entries grant access, no enrollment derivation
- **96-workspace-acl.AC6.11 Edge:** Workspace placed in course (course_id set, no activity_id) — instructor access derived from course enrollment

### 96-workspace-acl.AC7: Ownership at clone
- **96-workspace-acl.AC7.1 Success:** Cloning a workspace from an activity creates ACLEntry with owner permission for the cloning user
- **96-workspace-acl.AC7.2 Success:** Clone is gated by enrollment check — user must be enrolled in the activity's course
- **96-workspace-acl.AC7.3 Success:** Clone is gated by week visibility — activity's week must be visible to the user
- **96-workspace-acl.AC7.4 Success:** If user already has a workspace for this activity, return existing workspace instead of creating duplicate
- **96-workspace-acl.AC7.5 Failure:** Unauthenticated user cannot clone
- **96-workspace-acl.AC7.6 Failure:** User not enrolled in the course cannot clone

### 96-workspace-acl.AC8: Sharing controls
- **96-workspace-acl.AC8.1 Success:** Owner can share workspace as editor when allow_sharing is True
- **96-workspace-acl.AC8.2 Success:** Owner can share workspace as viewer when allow_sharing is True
- **96-workspace-acl.AC8.3 Success:** Activity.allow_sharing=None inherits Course.default_allow_sharing
- **96-workspace-acl.AC8.4 Success:** Activity.allow_sharing=True overrides Course.default_allow_sharing=False
- **96-workspace-acl.AC8.5 Success:** Activity.allow_sharing=False overrides Course.default_allow_sharing=True
- **96-workspace-acl.AC8.6 Success:** Instructor can share on behalf of students regardless of allow_sharing flag
- **96-workspace-acl.AC8.7 Failure:** Non-owner (editor/viewer) cannot share
- **96-workspace-acl.AC8.8 Failure:** Owner cannot share when allow_sharing resolves to False
- **96-workspace-acl.AC8.9 Failure:** Cannot grant permission higher than owner (owner cannot make someone else owner)

### 96-workspace-acl.AC9: Listing queries
- **96-workspace-acl.AC9.1 Success:** Student sees all workspaces they own (cloned)
- **96-workspace-acl.AC9.2 Success:** Student sees workspaces shared with them
- **96-workspace-acl.AC9.3 Success:** Instructor sees all student workspaces in their course via hierarchy
- **96-workspace-acl.AC9.4 Success:** Instructor sees loose workspaces placed in their course
- **96-workspace-acl.AC9.5 Success:** "Resume" shown for activity when user already has a workspace for it
- **96-workspace-acl.AC9.6 Success:** "Start Activity" shown when user has no workspace for the activity
- **96-workspace-acl.AC9.7 Edge:** Workspace whose activity was deleted (activity_id SET NULL) still appears in student's "my workspaces"

### 96-workspace-acl.AC10: Enforcement and revocation
- **96-workspace-acl.AC10.1 Success:** Unauthenticated user accessing a workspace URL is redirected to /login
- **96-workspace-acl.AC10.2 Success:** Unauthorised user accessing a workspace URL is redirected to /courses with notification
- **96-workspace-acl.AC10.3 Success:** Authorised user with viewer permission sees read-only UI
- **96-workspace-acl.AC10.4 Success:** Authorised user with editor/owner permission sees full edit UI
- **96-workspace-acl.AC10.5 Success:** Revoking access pushes immediate redirect to the connected client via websocket
- **96-workspace-acl.AC10.6 Success:** Revoked user sees toast notification "Your access has been revoked"
- **96-workspace-acl.AC10.7 Edge:** User with no active websocket connection — revocation takes effect on next page load

## Glossary

- **ACL (Access Control List)**: A table of rules specifying which users can access which workspaces and at what permission level. Implemented via the `ACLEntry` table linking users to workspaces.
- **Tri-state field**: A boolean field that accepts three values: `True`, `False`, or `None` (null). Used to represent explicit overrides (`True`/`False`) vs. inheritance from a parent setting (`None`).
- **Reference table**: A database table containing a fixed set of domain values (like permission levels or roles) that other tables reference via foreign keys. Uses string PKs — the name IS the identity. Allows adding new values via INSERT without schema migration.
- **Seed data**: Initial rows inserted into a reference table during migration to populate standard values (e.g., "owner", "editor", "viewer" permissions).
- **Stytch roles**: User role attributes managed by the third-party Stytch authentication service (e.g., `is_admin`, `instructor`). Used for organisation-level privilege checks, not per-workspace access control.
- **PlacementContext**: A frozen dataclass that resolves a workspace's full hierarchy chain (Activity → Week → Course) and derived properties like `copy_protection` and `allow_sharing`.
- **Hybrid permission resolution**: A multi-step authorisation algorithm that checks explicit ACL entries and enrollment-derived access, returning the highest applicable permission level, with admin bypass at the top.
- **CASCADE / RESTRICT delete**: Database constraints controlling what happens when a parent row is deleted. CASCADE automatically deletes dependent rows; RESTRICT prevents deletion if dependents exist.
- **Materialised view**: A database view whose results are cached as a physical table, refreshed periodically or on-demand. Mentioned as a future optimisation for workspace listing queries.
- **CRDT (Conflict-free Replicated Data Type)**: A data structure for collaborative editing that allows concurrent updates without conflicts. Used in the annotation page for multiplayer features.
- **NiceGUI websocket**: The persistent bidirectional connection between browser and server maintained by the NiceGUI framework. Used here to push real-time access revocation notifications.
- **Mutual exclusivity FK pattern**: A pattern where a table has multiple nullable FK columns with a CHECK constraint ensuring exactly one is set. Used for Workspace placement (`activity_id`/`course_id`) and extensible to ACLEntry when new resource types need ACL.

## Architecture

### Design Principle

Domain value sets that may grow are reference tables with string PKs and foreign keys. Python enums are reserved for wire protocol constants (e.g., `SelectiveLogic` mapping SillyTavern integer values). This principle applies retroactively to `CourseRole` and forward to `Permission`. Reference table identity is the name itself — no UUIDs for lookup data.

### Data Model

Three new tables, three modified tables:

**New: `Permission`** — reference table for access levels. String PK.

| Column | Type | Constraint |
|--------|------|------------|
| `name` | VARCHAR(50) | PK |
| `level` | INTEGER | NOT NULL, UNIQUE, CHECK (BETWEEN 1 AND 100) |

Seed data: owner (30), editor (20), viewer (10). Higher level wins in resolution.

**New: `CourseRole`** — reference table replacing the StrEnum. String PK.

| Column | Type | Constraint |
|--------|------|------------|
| `name` | VARCHAR(50) | PK |
| `level` | INTEGER | NOT NULL, UNIQUE, CHECK (BETWEEN 1 AND 100) |

Seed data: coordinator (40), instructor (30), tutor (20), student (10).

**New: `ACLEntry`** — per-user, per-workspace permission grant.

| Column | Type | Constraint |
|--------|------|------------|
| `id` | UUID | PK |
| `workspace_id` | UUID | FK → Workspace (CASCADE), NOT NULL |
| `user_id` | UUID | FK → User (CASCADE), NOT NULL |
| `permission` | VARCHAR(50) | FK → Permission.name (RESTRICT), NOT NULL |
| `created_at` | TIMESTAMPTZ | NOT NULL |
| | | UNIQUE (workspace_id, user_id) |

**Future extensibility:** When roleplay sessions or other resource types need ACL, add a nullable FK column (e.g., `roleplay_session_id`) with a CHECK constraint ensuring exactly one FK is set — mirroring the existing `Workspace.activity_id`/`course_id` mutual exclusivity pattern.

**Modified: `CourseEnrollment`** — `role` column becomes string FK → CourseRole.name (ondelete=RESTRICT).

**Modified: `Activity`** — adds `allow_sharing: BOOLEAN NULL` (tri-state: NULL=inherit, TRUE=on, FALSE=off).

**Modified: `Course`** — adds `default_allow_sharing: BOOLEAN NOT NULL DEFAULT false` and `default_instructor_permission: VARCHAR(50) FK → Permission.name (RESTRICT)`.

### Hybrid Permission Resolution

Two-step sequential resolution in `db/acl.py`:

1. **Admin override** (checked at page level, not DB layer): `is_privileged_user(auth_user)` returns True → owner-level access. Uses Stytch roles from `app.storage.user`.
2. **Explicit ACL lookup**: query ACLEntry for `(workspace_id, user_id)`. Index on unique constraint makes this fast.
3. **Enrollment-derived access**: resolve Workspace → Activity → Week → Course hierarchy. Check CourseEnrollment for `(course_id, user_id)` with instructor/coordinator/tutor role. Return `Course.default_instructor_permission` level.
4. **Highest wins**: if both explicit ACL and enrollment-derived access apply, return the **higher** permission level (by `Permission.level`). This prevents an explicit viewer grant from accidentally downgrading an instructor's enrollment-derived editor access.
5. **Default deny**: return `None`.

Admin check lives outside `db/acl.py` because it reads NiceGUI session state, not the database. The DB-layer resolution function is pure data.

### Enforcement

Guard function `check_workspace_access()` in `auth/__init__.py` combines Stytch admin check + DB resolution. Called at page entry following the existing `_check_auth()` pattern. Returns the permission name so the page knows what UI to render (editor sees full UI, viewer sees read-only).

Real-time revocation: when an instructor revokes access, push a redirect via the existing NiceGUI websocket connection using the connected client registry. No polling. `revoke_and_redirect()` in `pages/annotation/broadcast.py` uses `Client.run_javascript()` for cross-client push (NiceGUI's `ui.notify()`/`ui.navigate.to()` only work in the current client context).

### Sharing Controls

Follows the copy-protection tri-state pattern exactly:

- `Activity.allow_sharing: bool | None` — explicit override
- `Course.default_allow_sharing: bool` — course-level default
- Resolution: Activity explicit value wins, else Course default
- Resolved in `PlacementContext.allow_sharing: bool`

Only workspace owners can share. Sharing creates an ACLEntry for the recipient with the chosen permission level (editor or viewer). Instructors can share on behalf of students (bypasses `allow_sharing` flag). The ownership check and grant must happen in a single database session to prevent TOCTOU races.

## Existing Patterns

### Copy-Protection Tri-State (`db/models.py`, `db/workspaces.py`, `pages/courses.py`)

The `allow_sharing` field replicates this pattern exactly:
- `Activity.copy_protection: bool | None` with `Course.default_copy_protection: bool`
- Resolved in `_resolve_activity_placement()` within `PlacementContext`
- UI mapping via `_model_to_ui()` / `_ui_to_model()` pure functions
- Course settings dialog uses `ui.switch()`, activity settings uses `ui.select()` with tri-state options

### Auth Guard Pattern (`pages/courses.py`, `auth/__init__.py`)

- `_check_auth()` → redirect to `/login` if unauthenticated
- `_get_current_user()` → `app.storage.user.get("auth_user")`
- `_get_user_id()` → local DB UUID from session
- `is_privileged_user()` → org-level admin/instructor check via Stytch roles

The new `check_workspace_access()` extends this pattern with per-workspace ACL.

### Surrogate UUID PKs (`db/models.py`)

All existing models use UUID PKs with separate unique constraints (e.g., CourseEnrollment has `id: UUID` PK + unique on `(course_id, user_id)`). ACLEntry follows this convention.

### Atomic Creation Pattern (`db/workspaces.py`)

`create_activity()` atomically creates Activity + template Workspace. `clone_workspace_from_activity()` atomically creates Workspace + ACLEntry(owner).

### Connected Client Registry (`pages/annotation/__init__.py`, `pages/annotation/broadcast.py`)

Annotation page tracks `_workspace_presence` for multiplayer CRDT sync. Extended to support push-based revocation (map `(workspace_id, user_id) → Client` for targeted redirect via `revoke_and_redirect()`).

### New Pattern: Reference Tables

Divergence from existing `CourseRole` StrEnum. Justified by:
- Adding values to a StrEnum requires a code change + migration
- Reference tables allow INSERT without schema change
- `Permission` will grow (commenter deferred to #166)
- `CourseRole` may grow (marker, observer, examiner)

Reference tables use string PKs — the name is the identity. No UUIDs, no constants module. `permission = "owner"` is self-documenting in queries and code.

Comment added to Seam C (#95) noting `BriefTag` and `TagEditability` should follow this pattern.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Reference Tables

**Goal:** Create the foundational reference tables that everything else depends on.

**Components:**
- `Permission` table in `db/models.py` — string PK, level with CHECK + UNIQUE
- `CourseRole` table in `db/models.py` — string PK, level with CHECK + UNIQUE
- Alembic migration creating both tables with seed data

**Dependencies:** None (first phase)

**Done when:** Migration runs cleanly, seed data present, models importable. Covers 96-workspace-acl.AC1.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: CourseRole Normalisation

**Goal:** Replace the `CourseRole` StrEnum with string FK to the new reference table.

**Components:**
- `CourseEnrollment` model update in `db/models.py` — `role` VARCHAR → string FK to CourseRole.name (ondelete=RESTRICT)
- Alembic migration: ALTER `role` column to add FK constraint
- Update `db/courses.py` — all enrollment CRUD functions to use role name (string FK lookup)
- Update `db/weeks.py` — `get_visible_weeks()` and `can_access_week()` role checks
- Update `pages/courses.py` — enrollment display and role assignment UI

**Dependencies:** Phase 1 (CourseRole table must exist)

**Done when:** All existing tests pass with the new FK-based role, enrollment and week visibility work as before. Covers 96-workspace-acl.AC3.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: ACL Model

**Goal:** Create ACLEntry table linking users to workspaces with permissions.

**Components:**
- `ACLEntry` table in `db/models.py` — FKs to Workspace (CASCADE), User (CASCADE), Permission (RESTRICT)
- Alembic migration creating ACLEntry table
- ACL CRUD functions in new `db/acl.py` — grant (upsert), revoke, list entries

**Dependencies:** Phase 1 (Permission table must exist)

**Done when:** ACL entries can be granted and revoked on workspaces. Covers 96-workspace-acl.AC4, 96-workspace-acl.AC5.
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Permission Resolution

**Goal:** Implement the hybrid resolution function.

**Components:**
- `resolve_permission()` in `db/acl.py` — two-step: explicit ACL lookup, then enrollment-derived
- `can_access_workspace()` convenience function in `db/acl.py`
- `Course.default_instructor_permission` string FK to Permission.name in `db/models.py`
- Alembic migration for Course column

**Dependencies:** Phase 3 (ACLEntry table must exist)

**Done when:** Resolution correctly returns permission from explicit ACL, derives from enrollment for instructors, denies for unauthorised users. Covers 96-workspace-acl.AC6.
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: Ownership at Clone

**Goal:** Wire ACL ownership into the workspace cloning flow.

**Components:**
- Updated `clone_workspace_from_activity()` in `db/workspaces.py` — takes `user_id`, creates ACLEntry(owner) atomically
- Updated `start_activity()` in `pages/courses.py` — passes user_id, adds enrollment check (resolves TODO(Seam-D))
- `get_user_workspace_for_activity()` in `db/acl.py` — checks if user already owns a workspace for this activity

**Dependencies:** Phase 4 (resolution must work to verify ownership)

**Done when:** Cloning creates owner ACL entry, clone is gated by enrollment check, duplicate clone detection works. Covers 96-workspace-acl.AC7.
<!-- END_PHASE_5 -->

<!-- START_PHASE_6 -->
### Phase 6: Sharing Controls

**Goal:** Enable student-to-student workspace sharing.

**Components:**
- `Activity.allow_sharing` and `Course.default_allow_sharing` fields in `db/models.py`
- `PlacementContext.allow_sharing` resolution in `db/workspaces.py`
- Alembic migration for sharing columns
- `grant_share()` function in `db/acl.py` — creates ACLEntry for recipient, validates sharing is allowed; ownership check and grant in single session
- UI mapping functions in `pages/courses.py` — tri-state select for activity settings, switch for course settings
- `update_activity()` and `update_course()` extensions in `db/activities.py` and `db/courses.py`

**Dependencies:** Phase 5 (ownership must be established before sharing can be constrained to owners)

**Done when:** Sharing can be enabled/disabled per activity/course, owners can share workspaces, non-owners cannot. Covers 96-workspace-acl.AC8.
<!-- END_PHASE_6 -->

<!-- START_PHASE_7 -->
### Phase 7: Listing Queries

**Goal:** Implement workspace listing for students and instructors.

**Components:**
- `list_accessible_workspaces()` in `db/acl.py` — student's "my workspaces" via ACL entries
- `list_course_workspaces()` in `db/acl.py` — instructor view via hierarchy + loose workspaces
- `list_activity_workspaces()` in `db/acl.py` — per-activity student workspace list
- Database indexes on ACLEntry(user_id) and ACLEntry(workspace_id, user_id)

**Dependencies:** Phase 5 (workspaces must have ACL entries to list)

**Done when:** Students see their own workspaces, instructors see all student workspaces in their course including loose ones, "Resume" vs "Start Activity" detection works. Covers 96-workspace-acl.AC9.
<!-- END_PHASE_7 -->

<!-- START_PHASE_8 -->
### Phase 8: Enforcement and Revocation

**Goal:** Add access guards at page entry points and real-time revocation.

**Components:**
- `check_workspace_access()` guard function in `auth/__init__.py`
- Enforcement in `pages/annotation/workspace.py` — top of `_render_workspace_view()`
- Enforcement in `pages/courses.py` — clone auth gate (already wired in Phase 5, this adds the redirect)
- Enforcement in `pages/roleplay.py` — page entry guard
- Revocation broadcast in `pages/annotation/broadcast.py` — `revoke_and_redirect()` using connected client registry
- Toast notification on revocation: "Your access has been revoked"

**Dependencies:** Phase 4 (resolution) and Phase 7 (listing).

**Done when:** Unauthenticated users redirected to login, unauthorised users redirected to courses with notification, revocation pushes immediate redirect to connected clients. Covers 96-workspace-acl.AC10.
<!-- END_PHASE_8 -->

## Additional Considerations

**Materialised views:** All listing queries are behind clean function interfaces (`list_accessible_workspaces`, `list_course_workspaces`, etc.). If performance demands it, these can be backed by materialised views without changing the interface. Not needed at launch scale (~200 students per course).

**Commenter permission (#166):** Deferred. When peer review is designed, INSERT a new row into the Permission table. No migration needed — this is the benefit of the reference table pattern.

**Future resource types:** When roleplay sessions or other entities need ACL, add a nullable FK column to ACLEntry (e.g., `roleplay_session_id FK → RoleplaySession`) with a CHECK constraint ensuring exactly one FK is set. This is the same mutual exclusivity pattern already used for `Workspace.activity_id`/`course_id`. No intermediate table needed.
