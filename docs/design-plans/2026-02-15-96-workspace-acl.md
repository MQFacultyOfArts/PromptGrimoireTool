# Workspace ACL Design

**GitHub Issue:** #96

## Summary

This design implements fine-grained access control for workspaces through a hybrid permission model. The system combines explicit access grants (via Access Control Lists) with access derived from course enrollment and role hierarchy. When a student clones a workspace from an activity, they become its owner and can optionally share it with peers if the course settings allow. Instructors gain automatic access to all student workspaces within their courses. The implementation introduces a resource indirection layer that decouples authorisation from specific entity types, making the ACL system extensible to future permissioned resources like roleplay sessions.

The design replaces the existing `CourseRole` string enumeration with a reference table pattern, establishing a precedent for domain value sets that may grow over time. Permission resolution follows a precedence chain: administrator override (via Stytch roles) → highest of explicit ACL or enrollment-derived access → deny by default. Real-time access revocation is achieved through websocket-based push notifications to connected clients, enabling instructors to immediately revoke access without requiring page refresh. The sharing controls follow the existing copy-protection tri-state pattern, allowing per-activity overrides of course-level defaults.

## Definition of Done

1. **Resource indirection table** — `Resource` table as the ACL anchor point; all permissioned entities (workspaces, future roleplay sessions) get a Resource row
2. **Reference tables** — `Permission` (owner/editor/viewer) and `CourseRole` (coordinator/instructor/tutor/student) as reference tables with FK relationships, replacing the `CourseRole` StrEnum
3. **ACL model** — `ACLEntry` table with FKs to Resource, User, and Permission; unique constraint on (resource_id, user_id)
4. **Permission resolution** — `resolve_permission(resource_id, user_id)` implementing a hybrid model: checks explicit ACL entries and enrollment-derived access, returns the highest applicable permission; admin bypass via Stytch roles; default deny
5. **Ownership at clone** — when a student clones a workspace from an activity, a Resource row and an ACLEntry with owner permission are created atomically
6. **Sharing controls** — `allow_sharing` tri-state on Activity + default on Course (follows copy-protection pattern); owner can grant editor or viewer access to other students when sharing is enabled
7. **Listing queries** — "my workspaces" (via ACL entries), "course workspaces" (via hierarchy + loose placement), "activity workspaces", "user workspace for activity"
8. **Enforcement points** — guard function at workspace page entry points with push redirect via websocket for real-time revocation. Late phase, blocked on #120 rebase
9. **Clean migration** — no data preservation; reference table seed data in migration with fixed UUIDs

## Acceptance Criteria

### 96-workspace-acl.AC1: Reference tables exist with correct seed data
- **96-workspace-acl.AC1.1 Success:** Permission table contains owner (level 30), editor (level 20), viewer (level 10) with fixed UUIDs
- **96-workspace-acl.AC1.2 Success:** CourseRole table contains coordinator (40), instructor (30), tutor (20), student (10) with fixed UUIDs
- **96-workspace-acl.AC1.3 Success:** Reference table rows are created by the migration, not seed-data script
- **96-workspace-acl.AC1.4 Failure:** Duplicate name INSERT into Permission or CourseRole is rejected (UNIQUE constraint)

### 96-workspace-acl.AC2: Resource indirection table
- **96-workspace-acl.AC2.1 Success:** Creating a workspace atomically creates a Resource row with resource_type="workspace"
- **96-workspace-acl.AC2.2 Success:** Deleting a workspace does not CASCADE to Resource (RESTRICT)
- **96-workspace-acl.AC2.3 Failure:** Creating a workspace without a Resource fails (NOT NULL on resource_id)

### 96-workspace-acl.AC3: CourseRole normalisation
- **96-workspace-acl.AC3.1 Success:** CourseEnrollment uses role_id FK to CourseRole table
- **96-workspace-acl.AC3.2 Success:** Week visibility logic works identically after normalisation (coordinators/instructors/tutors see all weeks, students see only published)
- **96-workspace-acl.AC3.3 Success:** Enrollment CRUD functions accept role by reference table lookup
- **96-workspace-acl.AC3.4 Failure:** Enrolling with an invalid role_id is rejected (FK constraint)

### 96-workspace-acl.AC4: ACLEntry model
- **96-workspace-acl.AC4.1 Success:** ACLEntry can be created with valid resource_id, user_id, permission_id
- **96-workspace-acl.AC4.2 Success:** Deleting a Resource CASCADEs to its ACLEntry rows
- **96-workspace-acl.AC4.3 Success:** Deleting a User CASCADEs to their ACLEntry rows
- **96-workspace-acl.AC4.4 Failure:** Duplicate (resource_id, user_id) pair is rejected (UNIQUE constraint)
- **96-workspace-acl.AC4.5 Edge:** Granting a new permission to an existing (resource_id, user_id) pair upserts the permission_id

### 96-workspace-acl.AC5: ACL CRUD operations
- **96-workspace-acl.AC5.1 Success:** Grant permission to a user on a resource
- **96-workspace-acl.AC5.2 Success:** Revoke permission (delete ACLEntry)
- **96-workspace-acl.AC5.3 Success:** List all ACL entries for a resource
- **96-workspace-acl.AC5.4 Success:** List all ACL entries for a user

### 96-workspace-acl.AC6: Permission resolution
- **96-workspace-acl.AC6.1 Success:** User with explicit ACL entry gets that permission level
- **96-workspace-acl.AC6.2 Success:** Instructor enrolled in course gets Course.default_instructor_permission_id for workspaces in that course
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

- **ACL (Access Control List)**: A table of rules specifying which users can access which resources and at what permission level. Implemented via the `ACLEntry` table linking users to resources.
- **Resource indirection**: An architectural pattern where access control attaches to a generic `Resource` entity rather than directly to specific types like Workspaces. Allows the same ACL system to govern multiple entity types without duplication.
- **Tri-state field**: A boolean field that accepts three values: `True`, `False`, or `None` (null). Used to represent explicit overrides (`True`/`False`) vs. inheritance from a parent setting (`None`).
- **Reference table**: A database table containing a fixed set of domain values (like permission levels or roles) that other tables reference via foreign keys. Allows adding new values via INSERT without schema migration.
- **Seed data**: Initial rows inserted into a reference table during migration to populate standard values (e.g., "owner", "editor", "viewer" permissions). Uses fixed UUIDs for predictability across environments.
- **Stytch roles**: User role attributes managed by the third-party Stytch authentication service (e.g., `is_admin`, `instructor`). Used for organisation-level privilege checks, not per-resource access control.
- **PlacementContext**: A frozen dataclass that resolves a workspace's full hierarchy chain (Activity → Week → Course) and derived properties like `copy_protection` and `allow_sharing`.
- **Hybrid permission resolution**: A multi-step authorisation algorithm that checks explicit ACL entries and enrollment-derived access, returning the highest applicable permission level, with admin bypass at the top.
- **CASCADE / RESTRICT delete**: Database constraints controlling what happens when a parent row is deleted. CASCADE automatically deletes dependent rows; RESTRICT prevents deletion if dependents exist.
- **Materialised view**: A database view whose results are cached as a physical table, refreshed periodically or on-demand. Mentioned as a future optimisation for workspace listing queries.
- **CRDT (Conflict-free Replicated Data Type)**: A data structure for collaborative editing that allows concurrent updates without conflicts. Used in the annotation page for multiplayer features.
- **NiceGUI websocket**: The persistent bidirectional connection between browser and server maintained by the NiceGUI framework. Used here to push real-time access revocation notifications.

## Architecture

### Design Principle

Domain value sets that may grow are reference tables with foreign keys. Python enums are reserved for wire protocol constants (e.g., `SelectiveLogic` mapping SillyTavern integer values). This principle applies retroactively to `CourseRole` and forward to `Permission`.

### Data Model

Four new tables, two modified tables:

**New: `Resource`** — ACL anchor. Every permissioned entity gets a row. Decouples ACL from any specific resource type.

| Column | Type | Constraint |
|--------|------|------------|
| `id` | UUID | PK |
| `resource_type` | VARCHAR | NOT NULL ("workspace", etc.) |
| `created_at` | TIMESTAMPTZ | NOT NULL |

**New: `Permission`** — reference table for access levels. Seeded with fixed UUIDs.

| Column | Type | Constraint |
|--------|------|------------|
| `id` | UUID | PK |
| `name` | VARCHAR | UNIQUE, NOT NULL |
| `level` | INTEGER | NOT NULL |

Seed data: owner (30), editor (20), viewer (10). Higher level wins in resolution.

**New: `CourseRole`** — reference table replacing the StrEnum. Seeded with fixed UUIDs.

| Column | Type | Constraint |
|--------|------|------------|
| `id` | UUID | PK |
| `name` | VARCHAR | UNIQUE, NOT NULL |
| `level` | INTEGER | NOT NULL |

Seed data: coordinator (40), instructor (30), tutor (20), student (10).

**New: `ACLEntry`** — per-user, per-resource permission grant.

| Column | Type | Constraint |
|--------|------|------------|
| `id` | UUID | PK |
| `resource_id` | UUID | FK → Resource (CASCADE), NOT NULL |
| `user_id` | UUID | FK → User (CASCADE), NOT NULL |
| `permission_id` | UUID | FK → Permission, NOT NULL |
| `created_at` | TIMESTAMPTZ | NOT NULL |
| | | UNIQUE (resource_id, user_id) |

**Modified: `CourseEnrollment`** — `role` VARCHAR column replaced by `role_id` UUID FK → CourseRole.

**Modified: `Workspace`** — adds `resource_id` UUID FK → Resource (RESTRICT delete).

**Modified: `Activity`** — adds `allow_sharing: BOOLEAN NULL` (tri-state: NULL=inherit, TRUE=on, FALSE=off).

**Modified: `Course`** — adds `default_allow_sharing: BOOLEAN NOT NULL DEFAULT false` and `default_instructor_permission_id: UUID FK → Permission`.

### Hybrid Permission Resolution

Two-step sequential resolution in `db/acl.py`:

1. **Admin override** (checked at page level, not DB layer): `is_privileged_user(auth_user)` returns True → owner-level access. Uses Stytch roles from `app.storage.user`.
2. **Explicit ACL lookup**: query ACLEntry for `(resource_id, user_id)`. Index on unique constraint makes this fast.
3. **Enrollment-derived access**: resolve Resource → Workspace → Activity → Week → Course hierarchy. Check CourseEnrollment for `(course_id, user_id)` with instructor/coordinator/tutor role. Return `Course.default_instructor_permission_id` level.
4. **Highest wins**: if both explicit ACL and enrollment-derived access apply, return the **higher** permission level (by `Permission.level`). This prevents an explicit viewer grant from accidentally downgrading an instructor's enrollment-derived editor access.
5. **Default deny**: return `None`.

Admin check lives outside `db/acl.py` because it reads NiceGUI session state, not the database. The DB-layer resolution function is pure data.

### Enforcement

Guard function in `auth/__init__.py` combines Stytch admin check + DB resolution. Called at page entry following the existing `_check_auth()` pattern. Returns the Permission so the page knows what UI to render (editor sees full UI, viewer sees read-only).

Real-time revocation: when an instructor revokes access, push a redirect via the existing NiceGUI websocket connection using the connected client registry. No polling.

### Sharing Controls

Follows the copy-protection tri-state pattern exactly:

- `Activity.allow_sharing: bool | None` — explicit override
- `Course.default_allow_sharing: bool` — course-level default
- Resolution: Activity explicit value wins, else Course default
- Resolved in `PlacementContext.allow_sharing: bool`

Only workspace owners can share. Sharing creates an ACLEntry for the recipient with the chosen permission level (editor or viewer). Instructors can share on behalf of students (bypasses `allow_sharing` flag).

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

The new `_check_resource_access()` extends this pattern with per-resource ACL.

### Surrogate UUID PKs (`db/models.py`)

All existing models use UUID PKs with separate unique constraints (e.g., CourseEnrollment has `id: UUID` PK + unique on `(course_id, user_id)`). ACLEntry follows this convention.

### Atomic Creation Pattern (`db/workspaces.py`)

`create_activity()` atomically creates Activity + template Workspace. Extended: `create_workspace()` now atomically creates Resource + Workspace. `clone_workspace_from_activity()` atomically creates Resource + Workspace + ACLEntry(owner).

### Connected Client Registry (`pages/annotation.py`)

Annotation page tracks `_connected_clients` for multiplayer CRDT sync. Extended to support push-based revocation (map `(resource_id, user_id) → Client` for targeted redirect).

### New Pattern: Reference Tables

Divergence from existing `CourseRole` StrEnum. Justified by:
- Adding values to a StrEnum requires a code change + migration
- Reference tables allow INSERT without schema change
- `Permission` will grow (commenter deferred to #166)
- `CourseRole` may grow (marker, observer, examiner)

Comment added to Seam C (#95) noting `BriefTag` and `TagEditability` should follow this pattern.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Reference Tables and Resource Model

**Goal:** Create the foundational tables that everything else depends on.

**Components:**
- `Permission` table in `db/models.py` — reference table with name + level
- `CourseRole` table in `db/models.py` — reference table replacing StrEnum
- `Resource` table in `db/models.py` — ACL anchor with resource_type
- Alembic migration creating all three tables with seed data (fixed UUIDs)
- Python constants module for reference table name lookups

**Dependencies:** None (first phase)

**Done when:** Migration runs cleanly, seed data present, models importable. Covers 96-workspace-acl.AC1 (reference tables), 96-workspace-acl.AC2 (Resource table).
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: CourseRole Normalisation

**Goal:** Replace the `CourseRole` StrEnum with FK to the new reference table.

**Components:**
- `CourseEnrollment` model update in `db/models.py` — `role` VARCHAR → `role_id` UUID FK
- Alembic migration: drop `role` column, add `role_id` NOT NULL FK
- Update `db/courses.py` — all enrollment CRUD functions to use `role_id`
- Update `db/weeks.py` — `get_visible_weeks()` and `can_access_week()` role checks
- Update `pages/courses.py` — enrollment display and role assignment UI

**Dependencies:** Phase 1 (CourseRole table must exist)

**Done when:** All existing tests pass with the new FK-based role, enrollment and week visibility work as before. Covers 96-workspace-acl.AC3.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: ACL Model and Workspace Resource Link

**Goal:** Create ACLEntry table and link Workspaces to Resources.

**Components:**
- `ACLEntry` table in `db/models.py` — FKs to Resource, User, Permission
- `Workspace.resource_id` FK to Resource in `db/models.py`
- Alembic migration creating ACLEntry and adding resource_id to Workspace
- Updated `create_workspace()` in `db/workspaces.py` — atomically creates Resource + Workspace
- ACL CRUD functions in new `db/acl.py` — grant, revoke, list entries for a resource

**Dependencies:** Phase 1 (Resource and Permission tables must exist)

**Done when:** Workspaces are created with associated Resources, ACL entries can be granted and revoked. Covers 96-workspace-acl.AC4, 96-workspace-acl.AC5.
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Permission Resolution

**Goal:** Implement the hybrid resolution function.

**Components:**
- `resolve_permission()` in `db/acl.py` — two-step: explicit ACL lookup, then enrollment-derived
- `can_access_workspace()` convenience function in `db/acl.py`
- `Course.default_instructor_permission_id` FK in `db/models.py`
- `PlacementContext` update in `db/workspaces.py` — carry resolved instructor permission
- Alembic migration for Course column

**Dependencies:** Phase 3 (ACLEntry and Resource tables must exist)

**Done when:** Resolution correctly returns permission from explicit ACL, derives from enrollment for instructors, denies for unauthorised users. Covers 96-workspace-acl.AC6.
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: Ownership at Clone

**Goal:** Wire ACL ownership into the workspace cloning flow.

**Components:**
- Updated `clone_workspace_from_activity()` in `db/workspaces.py` — takes `user_id`, creates ACLEntry(owner) atomically
- Updated `start_activity()` in `pages/courses.py` — passes user_id, adds enrollment check (resolves TODO(Seam-D))
- `get_user_workspace_for_activity()` in `db/acl.py` — checks if user already has a workspace for this activity

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
- `grant_share()` function in `db/acl.py` — creates ACLEntry for recipient, validates sharing is allowed
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
- Database indexes on ACLEntry(user_id) and ACLEntry(resource_id, user_id)

**Dependencies:** Phase 5 (workspaces must have ACL entries to list)

**Done when:** Students see their own workspaces, instructors see all student workspaces in their course including loose ones, "Resume" vs "Start Activity" detection works. Covers 96-workspace-acl.AC9.
<!-- END_PHASE_7 -->

<!-- START_PHASE_8 -->
### Phase 8: Enforcement and Revocation

**Goal:** Add access guards at page entry points and real-time revocation.

**Components:**
- `_check_resource_access()` guard function in `auth/__init__.py`
- Enforcement in `pages/annotation.py` — top of `_render_workspace_view()` (**blocked on #120 rebase**)
- Enforcement in `pages/courses.py` — clone auth gate (already wired in Phase 5, this adds the redirect)
- Enforcement in `pages/roleplay.py` — page entry guard
- Revocation broadcast — extend connected client registry for push redirect via websocket
- Toast notification on revocation: "Your access has been revoked"

**Dependencies:** Phase 4 (resolution) and Phase 7 (listing). Annotation.py enforcement blocked on #120 rebase.

**Done when:** Unauthenticated users redirected to login, unauthorised users redirected to courses with notification, revocation pushes immediate redirect to connected clients. Covers 96-workspace-acl.AC10.
<!-- END_PHASE_8 -->

## Additional Considerations

**Materialised views:** All listing queries are behind clean function interfaces (`list_accessible_workspaces`, `list_course_workspaces`, etc.). If performance demands it, these can be backed by materialised views without changing the interface. Not needed at launch scale (~200 students per course).

**Phase 8 partial delivery:** Annotation.py enforcement is blocked on #120 (annotation.py refactor). Phases 1-7 and enforcement on courses.py/roleplay.py can proceed independently. Annotation.py enforcement should be queued as a follow-up after #120 merges.

**Commenter permission (#166):** Deferred. When peer review is designed, INSERT a new row into the Permission table. No migration needed — this is the benefit of the reference table pattern.
