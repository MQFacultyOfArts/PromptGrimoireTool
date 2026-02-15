# Database Schema

**Last updated:** 2026-02-15

PostgreSQL with SQLModel ORM. Schema managed via Alembic migrations.

## Tables

### User

Stytch-linked user accounts.

| Column | Type | Constraint |
|--------|------|------------|
| `id` | UUID | PK |
| `email` | VARCHAR(255) | UNIQUE, NOT NULL, INDEX |
| `display_name` | VARCHAR(100) | NOT NULL |
| `stytch_member_id` | VARCHAR | UNIQUE, INDEX, nullable |
| `is_admin` | BOOLEAN | NOT NULL, default FALSE |
| `created_at` | TIMESTAMPTZ | NOT NULL |
| `last_login` | TIMESTAMPTZ | nullable |

### Course

Course/unit of study with weeks and enrolled members.

| Column | Type | Constraint |
|--------|------|------------|
| `id` | UUID | PK |
| `code` | VARCHAR(20) | NOT NULL, INDEX |
| `name` | VARCHAR(200) | NOT NULL |
| `semester` | VARCHAR(20) | NOT NULL, INDEX |
| `is_archived` | BOOLEAN | NOT NULL, default FALSE |
| `default_copy_protection` | BOOLEAN | NOT NULL, default FALSE |
| `default_instructor_permission` | VARCHAR(50) | FK → Permission.name (RESTRICT), NOT NULL, default "editor" |
| `created_at` | TIMESTAMPTZ | NOT NULL |

**`default_copy_protection`**: Course-level default inherited by activities with `copy_protection=NULL`.

**`default_instructor_permission`**: Default permission level for instructors accessing student workspaces via enrollment-derived access. FK to `permission.name` with RESTRICT delete.

### CourseEnrollment

Maps users to courses with course-level roles.

| Column | Type | Constraint |
|--------|------|------------|
| `id` | UUID | PK |
| `course_id` | UUID | FK → Course (CASCADE), NOT NULL |
| `user_id` | UUID | FK → User (CASCADE), NOT NULL |
| `role` | VARCHAR(50) | FK → course_role.name (RESTRICT), NOT NULL, default "student" |
| `created_at` | TIMESTAMPTZ | NOT NULL |
| | | UNIQUE (course_id, user_id) |

**`role`**: String FK to the `course_role` reference table. Valid values: `coordinator`, `instructor`, `tutor`, `student`. RESTRICT prevents deletion of referenced role rows.

### Week

Week within a course with visibility controls.

| Column | Type | Constraint |
|--------|------|------------|
| `id` | UUID | PK |
| `course_id` | UUID | FK → Course (CASCADE), NOT NULL |
| `week_number` | INTEGER | NOT NULL, CHECK (1-52) |
| `title` | VARCHAR(200) | NOT NULL |
| `is_published` | BOOLEAN | NOT NULL, default FALSE |
| `visible_from` | TIMESTAMPTZ | nullable |
| `created_at` | TIMESTAMPTZ | NOT NULL |
| | | UNIQUE (course_id, week_number) |

**Visibility rules**: Instructors/coordinators/tutors see all weeks. Students see only published weeks where `visible_from` has passed (or is NULL).

### Activity

Assignment within a Week. Owns a template Workspace.

| Column | Type | Constraint |
|--------|------|------------|
| `id` | UUID | PK |
| `week_id` | UUID | FK → Week (CASCADE), NOT NULL |
| `template_workspace_id` | UUID | FK → Workspace (RESTRICT), NOT NULL, UNIQUE |
| `title` | VARCHAR(200) | NOT NULL |
| `description` | TEXT | nullable |
| `copy_protection` | BOOLEAN | nullable (tri-state) |
| `created_at` | TIMESTAMPTZ | NOT NULL |
| `updated_at` | TIMESTAMPTZ | NOT NULL |

**`copy_protection`**: Tri-state — `NULL`=inherit from course, `TRUE`=on, `FALSE`=off. Resolved in `PlacementContext`.

**`template_workspace_id`**: 1:1 relationship. RESTRICT prevents orphaning the activity's template. Created atomically with the activity via `create_activity()`.

### Workspace

Container for documents and CRDT state. Unit of collaboration.

| Column | Type | Constraint |
|--------|------|------------|
| `id` | UUID | PK |
| `crdt_state` | BYTEA | nullable |
| `activity_id` | UUID | FK → Activity (SET NULL), nullable |
| `course_id` | UUID | FK → Course (SET NULL), nullable |
| `enable_save_as_draft` | BOOLEAN | NOT NULL, default FALSE |
| `created_at` | TIMESTAMPTZ | NOT NULL |
| `updated_at` | TIMESTAMPTZ | NOT NULL |
| | | CHECK: `activity_id` and `course_id` mutually exclusive |

**Placement**: A workspace can be placed in an Activity OR a Course, never both. Enforced by Pydantic validator + DB CHECK constraint (`ck_workspace_placement_exclusivity`). A workspace with neither is "loose".

**No `created_by` FK**: Audit (who created) is separate from access control (who can access). ACL handles access; audit log is future work.

### WorkspaceDocument

Document within a workspace.

| Column | Type | Constraint |
|--------|------|------------|
| `id` | UUID | PK |
| `workspace_id` | UUID | FK → Workspace (CASCADE), NOT NULL |
| `type` | VARCHAR(50) | NOT NULL |
| `content` | TEXT | NOT NULL |
| `source_type` | VARCHAR(20) | NOT NULL |
| `order_index` | INTEGER | NOT NULL, default 0 |
| `title` | VARCHAR(500) | nullable |
| `created_at` | TIMESTAMPTZ | NOT NULL |

**`type`**: Domain string — "source", "draft", "ai_conversation".

**`source_type`**: Content format — "html", "rtf", "docx", "pdf", "text".

## ACL Tables (Issue #96)

These tables are being added by the workspace ACL feature.

### Permission

Reference table for access permission levels. String PK.

| Column | Type | Constraint |
|--------|------|------------|
| `name` | VARCHAR(50) | PK |
| `level` | INTEGER | NOT NULL, UNIQUE, CHECK (BETWEEN 1 AND 100) |

Seed data: `owner` (30), `editor` (20), `viewer` (10). Higher level wins in resolution.

### CourseRole (reference table)

Reference table replacing the `CourseRole` StrEnum. String PK.

| Column | Type | Constraint |
|--------|------|------------|
| `name` | VARCHAR(50) | PK |
| `level` | INTEGER | NOT NULL, UNIQUE, CHECK (BETWEEN 1 AND 100) |
| `is_staff` | BOOLEAN | NOT NULL, default FALSE |

Seed data: `coordinator` (40, staff), `instructor` (30, staff), `tutor` (20, staff), `student` (10).

**`is_staff`**: Marks roles that derive instructor-level access (week visibility, ACL permission resolution). Queried once at startup and cached via `get_staff_roles()` in `db/roles.py`.

**Note:** The SQLModel class is named `CourseRoleRef` to avoid collision with the existing `CourseRole` StrEnum. Table name is `course_role`. After Phase 2 deletes the StrEnum, the class can be renamed.

### ACLEntry

Per-user, per-workspace permission grant.

| Column | Type | Constraint |
|--------|------|------------|
| `id` | UUID | PK |
| `workspace_id` | UUID | FK → Workspace (CASCADE), NOT NULL |
| `user_id` | UUID | FK → User (CASCADE), NOT NULL |
| `permission` | VARCHAR(50) | FK → Permission.name (RESTRICT), NOT NULL |
| `created_at` | TIMESTAMPTZ | NOT NULL |
| | | UNIQUE (workspace_id, user_id) |
| | | INDEX on user_id |

**CASCADE on workspace/user**: ACL entries are meaningless without the workspace they protect or the user they grant access to.

**RESTRICT on permission**: Permission reference rows must never be deleted while ACLEntries reference them.

**Future extensibility**: When roleplay sessions or other resource types need ACL, add a nullable FK column (e.g., `roleplay_session_id`) with a CHECK constraint ensuring exactly one FK is set — same mutual exclusivity pattern as `Workspace.activity_id`/`course_id`.

## Modified Tables (Issue #96) — Planned

> **Not yet migrated.** These columns will be added in later phases of #96.

### Course (additions)

| Column | Type | Constraint |
|--------|------|------------|
| `default_allow_sharing` | BOOLEAN | NOT NULL, default FALSE |

### Activity (additions)

| Column | Type | Constraint |
|--------|------|------------|
| `allow_sharing` | BOOLEAN | nullable (tri-state) |

**`allow_sharing`**: Tri-state — `NULL`=inherit from course, `TRUE`=on, `FALSE`=off. Mirrors `copy_protection` pattern exactly.

## Hierarchy

```
Course
  └── Week (CASCADE)
        └── Activity (CASCADE)
              └── template Workspace (RESTRICT, 1:1)
              └── student Workspaces (SET NULL, 1:many via activity_id)
                    └── WorkspaceDocuments (CASCADE)
                    └── ACLEntries (CASCADE)
```

## Design Decisions

### Reference tables use string PKs

Reference data's identity IS the name. `permission = "owner"` is self-documenting in queries and code. No UUID indirection, no constants module. Foreign key values are readable in database queries.

### No Resource indirection table

ACLEntry links directly to Workspace via FK. When new resource types need ACL (e.g., roleplay sessions), a new FK column is added with mutual exclusivity CHECK — the same pattern already used for Workspace placement. This avoids an unnecessary intermediate table and join for a hypothetical future use case (YAGNI).

### Hybrid permission resolution

Permission resolution is a multi-step algorithm:

1. **Admin bypass** (page level): `is_privileged_user(auth_user)` → owner-level access
2. **Explicit ACL**: query ACLEntry for `(workspace_id, user_id)`
3. **Enrollment-derived**: resolve Workspace → Activity → Week → Course hierarchy, check CourseEnrollment for instructor/coordinator/tutor role, return `Course.default_instructor_permission`
4. **Highest wins**: if both explicit and derived access exist, return the higher level
5. **Default deny**: return `None`

Admin check lives outside `db/acl.py` because it reads NiceGUI session state, not the database. The DB-layer function is pure data.

### Surrogate UUID PKs with business-rule unique constraints

All entity tables use UUID PKs (ORM compatibility, no sequential ID leakage). Business-rule uniqueness is enforced via separate UNIQUE constraints:
- CourseEnrollment: UNIQUE (course_id, user_id)
- ACLEntry: UNIQUE (workspace_id, user_id)
- Week: UNIQUE (course_id, week_number)

### CASCADE / RESTRICT strategy

- **CASCADE**: Used when child rows are meaningless without the parent (enrollments, ACL entries, documents).
- **RESTRICT**: Used when the child should be explicitly handled before parent deletion (Activity → template Workspace, ACLEntry → Permission).
- **SET NULL**: Used when the child should survive parent deletion but lose the association (student Workspace → deleted Activity).

## Workspace Architecture

Workspaces are isolated silos identified by UUID.

- **`create_workspace()` takes no parameters** - Just creates an empty workspace with UUID
- **`PlacementContext`** (frozen dataclass) resolves the full hierarchy chain (Activity -> Week -> Course) for UI display. `display_label` provides a human-readable string like "Annotate Becky in Week 1 for LAWS1100".
- **Template detection**: `is_template` flag on PlacementContext is True when the workspace is an Activity's `template_workspace_id`.
- **Copy protection resolution**: `copy_protection: bool` on PlacementContext is resolved during placement query. Activity's explicit value wins; if `None`, inherits from `Course.default_copy_protection`. Loose and course-placed workspaces always resolve to `False`. See [docs/copy-protection.md](copy-protection.md).

### Workspace Cloning

`clone_workspace_from_activity(activity_id)` creates a student workspace from a template:

1. Creates new Workspace with `activity_id` set and `enable_save_as_draft` copied
2. Copies all WorkspaceDocuments (content, type, source_type, title, order_index) with new UUIDs
3. Returns `(Workspace, doc_id_map)` -- the mapping of template doc UUIDs to cloned doc UUIDs
4. CRDT state is replayed via `_replay_crdt_state()`: highlights get `document_id` remapped, comments are preserved, general notes are copied, client metadata is NOT cloned
5. Entire operation is atomic (single session)

**Delete order for Activity** (circular FK): delete Activity first (SET NULL on student workspaces), then delete orphaned template Workspace (safe because RESTRICT FK no longer points to it).

## App Startup Database Bootstrap

When `DATABASE__URL` is configured, `main()` automatically bootstraps the database before starting the server:

1. **`ensure_database_exists(url) -> bool`** -- Creates the PostgreSQL database if it does not exist. Returns `True` if a new database was created, `False` otherwise (including `None`/empty URL or database already exists).
2. **`run_alembic_upgrade()`** -- Runs Alembic migrations to head (idempotent). Internally calls `ensure_database_exists()` again (harmless -- already exists, returns `False`).
3. **Conditional seeding** -- If `ensure_database_exists()` returned `True` (new DB), runs `uv run seed-data` to populate development data.
4. **Branch info** -- On feature branches (not main/master), prints `Branch: <name> | Database: <db_name>` to stdout.

This means `uv run python -m promptgrimoire` on a new feature branch automatically creates the branch-specific database, migrates it, and seeds it. No manual setup needed.

## Database Rules

1. **Alembic is the ONLY way to create/modify schema** - Never use `SQLModel.metadata.create_all()` except in Alembic migrations themselves
2. **All models must be imported before schema operations** - The `promptgrimoire.db.models` module must be imported to register tables with SQLModel.metadata
3. **Pages requiring DB must check availability** - Use `get_settings().database.url` and show a helpful error if not configured
4. **Use `verify_schema()` at startup** - Fail fast if tables are missing

## Page Database Dependencies

| Page | Route | DB Required |
|------|-------|-------------|
| annotation | `/annotation` | **Yes** |
| courses | `/courses` | **Yes** |
| roleplay | `/roleplay` | No |
| logviewer | `/logs` | No |
| highlight_api_demo | `/demo/highlight-api` | No |
| milkdown_spike | `/demo/milkdown-spike` | No |
| auth | `/login`, `/logout` | Optional |
