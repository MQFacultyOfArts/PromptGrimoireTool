# Workspace Sharing & Visibility Design

**GitHub Issue:** #97

## Summary

PromptGrimoire workspaces are currently private to their owner (or explicitly shared with specific users via ACL grants). This feature adds a collaborative layer that lets instructors enable peer browsing within a class activity, so enrolled students can view and annotate each other's workspaces without requiring the owner to manually share with every individual. A new `peer` permission level sits between viewer (read-only) and editor (full collaborative editing), granting the right to annotate and comment but not to add or remove documents. Instructors control whether sharing is allowed at the activity level; students then opt in workspace-by-workspace. When both conditions are met, any enrolled student can discover and interact with that workspace.

The approach is deliberately additive: no new access-control tables are introduced. Enrollment-based peer discovery extends the existing `resolve_permission` function with a third resolution path (explicit ACL beats enrollment-derived peer; highest permission wins). Anonymity is a render-time transformation — author names are replaced with deterministic labels (`Peer N`) only at the point of display, never in storage, so instructors always retain access to true authorship. A new instructor roster page provides a staff-only overview of student workspace activity per activity. The design consolidates a previously separate "commenter" concept (#166) into the single `peer` level.

## Definition of Done

1. **Peer permission level** — new row in Permission reference table: can view + create highlights/tags + reply to annotations. Cannot add/delete documents or manage ACL. Replaces the separate "annotator" and "commenter" concepts from #166.
2. **Enrollment-based discovery** — when an activity has sharing enabled, enrolled students can browse and interact with peer workspaces; `resolve_permission` grants peer-level access via enrollment.
3. **Annotation comments** — flat replies on any annotation (multiple replies, chronological order, no nesting). Stored in CRDT. Author identity subject to anonymity setting.
4. **Anonymity control** — instructor-controlled flag per activity (tri-state, inheriting course default). Hides author names on annotations and comments from peer viewers. Instructors always see true authorship.
5. **Workspace titles** — new `title` field on Workspace model (Alembic migration).
6. **Instructor view page** — new page from course/week showing roster of student workspaces per activity with basic stats; clickable to open any workspace.
7. **Sharing UX** — activity/course sharing & anonymity settings in existing settings UI; per-user sharing for loose workspaces via `grant_share`.
8. **Permission-aware rendering** — annotation page distinguishes peer (annotate + comment), viewer (read-only), and editor (full) modes.

**Out of scope:** Nested/threaded comment discussions, analytics dashboard, real-time revocation broadcast UX.

**Folds in:** #166 (commenter permission level — now unified with peer annotation as a single "peer" permission).

## Acceptance Criteria

### workspace-sharing-97.AC1: Peer permission level
- **workspace-sharing-97.AC1.1 Success:** Permission table contains 'peer' with level 15
- **workspace-sharing-97.AC1.2 Success:** Peer can view documents and highlights in shared workspace
- **workspace-sharing-97.AC1.3 Success:** Peer can create highlights and tags in shared workspace
- **workspace-sharing-97.AC1.4 Success:** Peer can add comments on highlights
- **workspace-sharing-97.AC1.5 Success:** Peer can delete own comments
- **workspace-sharing-97.AC1.6 Failure:** Peer cannot add or delete documents
- **workspace-sharing-97.AC1.7 Failure:** Peer cannot manage ACL (share workspace)
- **workspace-sharing-97.AC1.8 Failure:** Peer cannot delete others' comments

### workspace-sharing-97.AC2: Enrollment-based discovery
- **workspace-sharing-97.AC2.1 Success:** Student enrolled in course gets peer access to workspace where activity.allow_sharing=True AND workspace.shared_with_class=True
- **workspace-sharing-97.AC2.2 Success:** Explicit ACL entry with higher permission (e.g. editor) wins over enrollment-derived peer
- **workspace-sharing-97.AC2.3 Success:** Student's own workspace returns owner (from ACL), not peer
- **workspace-sharing-97.AC2.4 Failure:** Student not enrolled in course gets None (no access)
- **workspace-sharing-97.AC2.5 Failure:** Student enrolled but activity.allow_sharing=False gets None
- **workspace-sharing-97.AC2.6 Failure:** Student enrolled but workspace.shared_with_class=False gets None
- **workspace-sharing-97.AC2.7 Edge:** Loose workspace (no activity_id) — only explicit ACL grants access, no enrollment derivation
- **workspace-sharing-97.AC2.8 Edge:** Course-placed workspace (course_id set, no activity_id) — no peer discovery

### workspace-sharing-97.AC3: Annotation comments
- **workspace-sharing-97.AC3.1 Success:** User can add flat reply to any highlight
- **workspace-sharing-97.AC3.2 Success:** Multiple replies on same highlight shown chronologically
- **workspace-sharing-97.AC3.3 Success:** Comment stored with user_id, author display name, text, timestamp
- **workspace-sharing-97.AC3.4 Success:** Comment creator can delete own comment
- **workspace-sharing-97.AC3.5 Success:** Workspace owner can delete any comment
- **workspace-sharing-97.AC3.6 Failure:** Viewer cannot add comments
- **workspace-sharing-97.AC3.7 Edge:** Existing highlights without user_id display 'Unknown' for instructors

### workspace-sharing-97.AC4: Anonymity control
- **workspace-sharing-97.AC4.1 Success:** Activity.anonymous_sharing=True hides author names from peer viewers
- **workspace-sharing-97.AC4.2 Success:** Activity.anonymous_sharing=None inherits Course.default_anonymous_sharing
- **workspace-sharing-97.AC4.3 Success:** Instructor always sees true author regardless of anonymity flag
- **workspace-sharing-97.AC4.4 Success:** Owner viewing own workspace sees true author names
- **workspace-sharing-97.AC4.5 Success:** Peer sees own annotations with real name, others' with anonymised label
- **workspace-sharing-97.AC4.6 Success:** Anonymised labels are adjective-animal names deterministic per user_id (stable across sessions and page reloads)
- **workspace-sharing-97.AC4.7 Success:** PDF export respects anonymity flag — peer export shows anonymised names
- **workspace-sharing-97.AC4.8 Success:** Instructor PDF export shows true names
- **workspace-sharing-97.AC4.9 Edge:** Broadcast cursor/selection labels anonymised for peer viewers

### workspace-sharing-97.AC5: Workspace titles
- **workspace-sharing-97.AC5.1 Success:** Workspace has optional title field (VARCHAR 200, nullable)
- **workspace-sharing-97.AC5.2 Success:** Title displayed in workspace header, peer discovery list, instructor roster
- **workspace-sharing-97.AC5.3 Edge:** Workspace without title displays fallback (e.g. 'Untitled Workspace')

### workspace-sharing-97.AC6: Instructor view page
- **workspace-sharing-97.AC6.1 Success:** Staff-enrolled user can access workspace roster page
- **workspace-sharing-97.AC6.2 Success:** Roster lists workspaces per activity with student name, title, dates, document count, highlight count
- **workspace-sharing-97.AC6.3 Success:** Activity-level stats: N started / M enrolled
- **workspace-sharing-97.AC6.4 Success:** Click-through opens workspace at /annotation?workspace={id}
- **workspace-sharing-97.AC6.5 Failure:** Non-staff user cannot access instructor view page
- **workspace-sharing-97.AC6.6 Edge:** Activity with no student workspaces shows empty state with enrolled count

### workspace-sharing-97.AC7: Sharing UX
- **workspace-sharing-97.AC7.1 Success:** Instructor can toggle allow_sharing per activity (tri-state)
- **workspace-sharing-97.AC7.2 Success:** Instructor can toggle anonymous_sharing per activity (tri-state)
- **workspace-sharing-97.AC7.3 Success:** Instructor can set course defaults for both
- **workspace-sharing-97.AC7.4 Success:** Owner sees 'Share with class' toggle when activity allows sharing
- **workspace-sharing-97.AC7.5 Success:** Owner can toggle shared_with_class on and off
- **workspace-sharing-97.AC7.6 Success:** Owner can share loose workspace with specific user via grant_share
- **workspace-sharing-97.AC7.7 Failure:** 'Share with class' not shown when activity disallows sharing
- **workspace-sharing-97.AC7.8 Failure:** Non-owner cannot see sharing controls

### workspace-sharing-97.AC8: Permission-aware rendering
- **workspace-sharing-97.AC8.1 Success:** Viewer sees read-only UI (no tag toolbar, no highlight menu, no comment input, no document upload)
- **workspace-sharing-97.AC8.2 Success:** Peer sees annotate UI (tag toolbar, highlight menu, comment input) but no document upload
- **workspace-sharing-97.AC8.3 Success:** Editor sees full UI including document upload
- **workspace-sharing-97.AC8.4 Success:** Owner sees full UI plus ACL management controls
- **workspace-sharing-97.AC8.5 Edge:** Permission threaded via PageState.effective_permission to all rendering functions

## Glossary

- **ACL (Access Control List)**: The per-workspace table of explicit permission grants. Each row names a user and their permission level (e.g. owner, editor, viewer). Enrollment-based peer access is derived separately and does not write ACL rows.
- **Alembic**: The database migration tool used to apply schema changes to PostgreSQL in a versioned, repeatable way. All column additions and reference-data inserts go through Alembic migrations.
- **CRDT (Conflict-free Replicated Data Type)**: A data structure that allows multiple clients to edit shared state concurrently without coordination, with guaranteed merge. Used here via the `pycrdt` library to store highlights and comments.
- **PlacementContext**: A resolved view of an activity's settings (including sharing and copy-protection flags) computed from the Activity row and its parent Course defaults. Avoids repeating the tri-state inheritance logic at every call site.
- **`resolve_permission`**: The central function in `db/acl.py` that determines what permission a given user has on a given workspace. Returns the highest of: explicit ACL entry, enrollment-derived access, or `None` (deny).
- **`_derive_enrollment_permission`**: Internal function called by `resolve_permission`. Currently handles staff roles; this feature adds a student path that returns `peer` when sharing conditions are met.
- **Seam D / #96**: The prior work that introduced the ACL system (explicit grants, `resolve_permission`, the Permission reference table). This feature builds on top of it without modifying its core contract.
- **Permission reference table**: A database table mapping permission names (`owner`, `editor`, `peer`, `viewer`) to integer levels. Levels are used to compare and pick the highest permission when multiple apply.
- **Tri-state flag**: A `bool | None` column pattern used for activity-level settings that can explicitly be on, explicitly be off, or inherit the course-level default (`None`). Used for `anonymous_sharing`, `allow_sharing`, and `copy_protection`.
- **`grant_share()`**: Existing ACL helper that creates an explicit permission entry for a named user on a workspace. Used for the per-user sharing flow for loose workspaces.
- **`check_workspace_access()`**: Auth-layer function that combines privilege checks (admin bypass), explicit ACL, and enrollment derivation into a single permission string for a (workspace, user) pair.
- **PageState**: Object threaded through the annotation page that holds per-session rendering context. `effective_permission` is added here so all rendering functions can gate UI elements from a single source of truth.
- **Loose workspace**: A workspace not associated with any Activity (no `activity_id`). Only explicit ACL grants apply; enrollment-based peer discovery does not.
- **Full-replace pattern**: The CRDT write strategy for comments: read the current list, modify it in Python, write the entire list back. Simpler than operating on a CRDT Array but vulnerable to last-write-wins under concurrent edits.
- **`is_privileged_user`**: Auth helper returning `True` for org admins and users with `instructor` or `stytch_admin` roles. Gate for seeing true author names regardless of anonymity settings.
- **Stytch**: The third-party authentication provider used for magic-link login, passkeys, and RBAC. User identities are represented by Stytch user IDs (`user_id`).
- **NiceGUI**: The Python web UI framework used to build the application's pages and interactive components.
- **Broadcast / `broadcast.py`**: The module handling real-time cursor and selection state shared between clients viewing the same workspace. Peer viewers' cursor labels must be anonymised when the anonymity flag is active.

## Architecture

### Design Principle

Sharing and visibility layer on top of the existing ACL system (Seam D, #96). No new tables for access control — enrollment-based discovery extends `resolve_permission` with a third resolution path. Anonymity is a render-time concern controlled by per-activity flags, not a storage-time transformation. The original issue's `WorkspaceSharing` entity with `SharingMode` enum is superseded.

### Data Model Changes

**Permission table** — INSERT new row (no schema migration):

| name | level |
|------|-------|
| `peer` | 15 |

Sits between `viewer` (10) and `editor` (20). Peer permission grants: view documents, create highlights/tags, add/delete own comments. Cannot: add/delete documents, manage ACL.

**Workspace** — two new columns:

| Column | Type | Default | Purpose |
|--------|------|---------|---------|
| `title` | VARCHAR(200), NULL | `None` | Display name for workspace |
| `shared_with_class` | BOOLEAN, NOT NULL | `false` | Student opt-in for peer discovery |

**Activity** — one new column:

| Column | Type | Default | Purpose |
|--------|------|---------|---------|
| `anonymous_sharing` | BOOLEAN, NULL | `None` | Tri-state: None=inherit, True/False=override |

**Course** — one new column:

| Column | Type | Default | Purpose |
|--------|------|---------|---------|
| `default_anonymous_sharing` | BOOLEAN, NOT NULL | `false` | Course-level anonymity default |

**CRDT highlight/comment data** — `user_id: str` added alongside existing `author` field. `author` is the display name for rendering; `user_id` is the stable Stytch identifier for anonymity logic and ownership checks. Existing data without `user_id` treated as `None` (shown as "Unknown" to instructors, anonymised for peers).

### Permission Resolution

Extended `_derive_enrollment_permission` in `src/promptgrimoire/db/acl.py`. Currently returns `Course.default_instructor_permission` for staff roles, `None` for students. New path:

```
1. Explicit ACL entry → permission level
2. Enrollment-derived:
   a. Staff role → Course.default_instructor_permission (existing)
   b. Student role + activity sharing enabled + workspace.shared_with_class → "peer" (new)
3. Highest wins (Permission.level comparison)
4. Default deny → None
```

Three conditions for enrollment-based peer access: (1) student enrolled in the workspace's course, (2) `PlacementContext.allow_sharing == True`, (3) `Workspace.shared_with_class == True`. All three required.

`check_workspace_access` in `src/promptgrimoire/auth/__init__.py` unchanged — the new `"peer"` value flows through naturally.

### Permission Capability Matrix

| Capability | owner | editor | peer | viewer |
|-----------|-------|--------|------|--------|
| View documents & highlights | yes | yes | yes | yes |
| Add highlights/tags | yes | yes | yes | no |
| Add comments on highlights | yes | yes | yes | no |
| Delete own comments | yes | yes | yes | no |
| Delete others' comments | yes | no | no | no |
| Add/delete documents | yes | yes | no | no |
| Manage ACL (share) | yes | no | no | no |
| See true author names | yes | yes | anon flag | anon flag |

### Anonymity

Render-time transformation, not storage-time. Every highlight and comment stores both `user_id` and `author`. An anonymisation utility determines what name to display:

- **Instructor/admin** (`is_privileged_user` or staff enrollment): true `author`
- **Owner** (viewing own workspace): true `author`
- **Peer** with `anonymous_sharing == True`: anonymised adjective-animal label (e.g., "Calm Badger") — deterministic from `user_id` hash into hardcoded word lists (50 adjectives x 50 animals = 2,500 combinations, audited for appropriateness). Stable across sessions and page reloads. Own annotations show real name to self.
- **Peer** with `anonymous_sharing == False`: true `author`

Anonymity enforcement points: annotation cards (`cards.py`), organise tab cards (`organise.py`), PDF export (`pdf_export.py`), remote cursor/selection labels (`broadcast.py`).

### Two Collaboration Patterns

**Browse-peers** (enrollment-based discovery): each student has their own workspace. When `allow_sharing` and `shared_with_class` are both true, enrolled peers can discover and interact with it. Peers get `peer` permission (annotate + comment, no document management).

**Shared-workspace** (ACL editor grants): instructor or owner creates one workspace and grants `editor` ACL entries to multiple users. Full collaborative editing via CRDT. Already supported by existing ACL infrastructure.

### Sharing UX

**Two-step class sharing:**
1. Instructor enables `allow_sharing` on the Activity (enables the possibility)
2. Student clicks "Share with class" on their workspace (sets `shared_with_class = True`)

Both conditions must be true for peer discovery. Reversible — student can unshare.

**Per-user sharing** for loose workspaces and targeted grants: uses existing `grant_share()` from `src/promptgrimoire/db/acl.py`. Owner-initiated dialog in workspace header.

**Peer discovery UI** on course/activity page (`src/promptgrimoire/pages/courses.py`): below the student's "Resume" button, a "Peer Workspaces" section lists workspaces where `shared_with_class = True`. Gated by `PlacementContext.allow_sharing`. Each entry shows workspace title + author (or anonymised label) + link.

### Instructor View Page

New page at `/course/{course_id}/workspaces`, linked from course/week pages. Staff-enrolled users only.

**Layout:**
- Activity selector (dropdown/sidebar, grouped by week) using existing `get_activities_for_week()`
- Workspace roster for selected activity using `list_activity_workspaces()`

**Roster fields:** workspace title, student name (User JOIN), created date, last modified, document count, highlight count (`GROUP BY workspace_id`), click-through to `/annotation?workspace={id}`.

**Activity-level stats:** N started / M enrolled, "not started" student list.

## Existing Patterns

### Tri-State Activity/Course Fields (`src/promptgrimoire/db/models.py`, `src/promptgrimoire/db/workspaces.py`)

`anonymous_sharing` replicates the exact pattern used by `copy_protection` and `allow_sharing`:
- `Activity.anonymous_sharing: bool | None` with `Course.default_anonymous_sharing: bool`
- Resolution in `_resolve_activity_placement()` within `PlacementContext`
- UI mapping via `_model_to_ui()` / `_ui_to_model()` pure functions in `src/promptgrimoire/pages/courses.py`
- Course settings uses `ui.switch()`, activity settings uses `ui.select()` with tri-state options

### Permission Reference Table (`src/promptgrimoire/db/models.py`)

`peer` permission follows the reference table pattern established in Seam D. String PK (`name`), `level` integer for ordering. INSERT in Alembic migration, no schema change.

### Hybrid Permission Resolution (`src/promptgrimoire/db/acl.py`)

The new student enrollment path extends `_derive_enrollment_permission` following the same two-step sequential resolution pattern. PlacementContext is already resolved inside this function for staff access — student path reuses the same hierarchy walk.

### CRDT Comment Operations (`src/promptgrimoire/crdt/annotation_doc.py`)

`add_comment()` and `delete_comment()` already exist with origin-based echo prevention. Full-replace pattern (read list, mutate, write entire highlight back). Adding `user_id` field to comment dicts follows the existing dict structure.

### Auth Guard Pattern (`src/promptgrimoire/pages/annotation/workspace.py`, `src/promptgrimoire/auth/__init__.py`)

`check_workspace_access()` already returns the permission string. Threading it into `PageState` and gating UI components follows the existing pattern where `is_privileged_user` gates copy protection rendering.

### New Pattern: Render-Time Anonymisation

No existing precedent for identity transformation at render time. The anonymisation utility is new but contained — a pure function called at each display point rather than a cross-cutting middleware.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Data Model & Migration

**Goal:** Schema changes and reference data for all subsequent phases.

**Components:**
- `Workspace.title` and `Workspace.shared_with_class` columns in `src/promptgrimoire/db/models.py`
- `Activity.anonymous_sharing` column in `src/promptgrimoire/db/models.py`
- `Course.default_anonymous_sharing` column in `src/promptgrimoire/db/models.py`
- `PlacementContext.anonymous_sharing` field and resolution in `src/promptgrimoire/db/workspaces.py`
- `peer` row INSERT into `permission` table
- Single Alembic migration for all schema changes + seed data

**Dependencies:** None (first phase). Requires Seam D migration to have run (already deployed).

**Done when:** Migration runs cleanly, `peer` permission exists, PlacementContext resolves `anonymous_sharing`, models importable with new fields. Covers workspace-sharing-97.AC1, workspace-sharing-97.AC4.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Permission Resolution Extension

**Goal:** Enrollment-based peer access in the hybrid resolver.

**Components:**
- Extended `_derive_enrollment_permission` in `src/promptgrimoire/db/acl.py` — student enrollment + sharing enabled + shared_with_class → "peer"
- `list_peer_workspaces(activity_id, exclude_user_id)` query in `src/promptgrimoire/db/acl.py` — workspaces for activity where `shared_with_class = True`, excluding templates and current user

**Dependencies:** Phase 1 (peer permission level must exist, shared_with_class column must exist)

**Done when:** Students get peer-level access to shared workspaces in their enrolled activities. Students do NOT get access to unshared workspaces or workspaces in other courses. Covers workspace-sharing-97.AC2.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: CRDT User Identity & Comments

**Goal:** User identity on annotations/comments and comment UI.

**Components:**
- `user_id` field added to highlight and comment dicts in `src/promptgrimoire/crdt/annotation_doc.py` — `add_highlight()` and `add_comment()` signatures extended
- Anonymisation utility function — pure function: `(author, user_id, viewing_user_id, anonymous_sharing, viewer_is_staff) → display_name`
- Comment UI in `src/promptgrimoire/pages/annotation/cards.py` — extend `_build_comments_section()` with input form for adding replies, delete button for own comments, anonymised author display
- Comment creation wiring in `src/promptgrimoire/pages/annotation/highlights.py` — connect UI to `crdt_doc.add_comment()`

**Dependencies:** Phase 1 (anonymous_sharing field in PlacementContext)

**Done when:** Comments can be added and deleted via UI, user_id stored on all new highlights/comments, anonymisation renders correctly based on flag. Covers workspace-sharing-97.AC3, workspace-sharing-97.AC4.
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Permission-Aware Rendering

**Goal:** Annotation page respects permission levels.

**Components:**
- `effective_permission` field added to `PageState` in `src/promptgrimoire/pages/annotation/__init__.py`
- Permission threading in `src/promptgrimoire/pages/annotation/workspace.py` — pass permission from `check_workspace_access()` into PageState
- UI gating in `src/promptgrimoire/pages/annotation/document.py` — suppress tag toolbar and highlight menu for viewer
- UI gating in `src/promptgrimoire/pages/annotation/cards.py` — suppress comment input for viewer, delete button gating by ownership
- UI gating in `src/promptgrimoire/pages/annotation/content_form.py` — suppress document upload for peer/viewer
- UI gating in `src/promptgrimoire/pages/annotation/css.py` — read-only tag display for viewer
- Anonymised author labels in `src/promptgrimoire/pages/annotation/cards.py` and `src/promptgrimoire/pages/annotation/organise.py`

**Dependencies:** Phase 2 (peer permission resolution), Phase 3 (anonymisation utility)

**Done when:** Viewer sees read-only UI, peer can annotate/comment but not add documents, editor has full access, anonymity flag controls author display. Covers workspace-sharing-97.AC8.
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: Sharing UX

**Goal:** Activity/course settings and student sharing controls.

**Components:**
- Activity settings: `anonymous_sharing` tri-state select in `src/promptgrimoire/pages/courses.py` — follows existing `copy_protection` UI pattern
- Course settings: `default_anonymous_sharing` switch in `src/promptgrimoire/pages/courses.py`
- "Share with class" toggle in workspace header (`src/promptgrimoire/pages/annotation/workspace.py`) — visible when owner + activity sharing enabled, sets `Workspace.shared_with_class`
- Per-user sharing dialog in workspace header — owner-only, for loose workspaces, uses existing `grant_share()`

**Dependencies:** Phase 1 (anonymous_sharing columns), Phase 4 (permission threading for owner check)

**Done when:** Instructors can configure sharing/anonymity per activity/course, students can share/unshare with class, per-user sharing works for loose workspaces. Covers workspace-sharing-97.AC7.
<!-- END_PHASE_5 -->

<!-- START_PHASE_6 -->
### Phase 6: Peer Discovery & Instructor View

**Goal:** Student peer browsing and instructor workspace roster.

**Components:**
- Peer workspace list on activity page in `src/promptgrimoire/pages/courses.py` — "Peer Workspaces" section below "Resume" button, gated by `allow_sharing`, shows shared workspaces with anonymised/attributed author
- Instructor view page at new route — activity selector grouped by week, workspace roster table with student name (User JOIN), title, dates, document count, highlight count (GROUP BY), click-through
- Activity-level stats: started/enrolled counts, not-started list

**Dependencies:** Phase 2 (`list_peer_workspaces` query), Phase 3 (anonymisation for peer display), Phase 5 (sharing must be configurable)

**Done when:** Students see peer workspaces when sharing is enabled, instructors see workspace roster with stats per activity. Covers workspace-sharing-97.AC6.
<!-- END_PHASE_6 -->

<!-- START_PHASE_7 -->
### Phase 7: PDF Export Anonymity

**Goal:** PDF export respects anonymity flag.

**Components:**
- Anonymised author attribution in `src/promptgrimoire/pages/annotation/pdf_export.py` — use the same anonymisation utility from Phase 3
- Export context: pass `anonymous_sharing` flag and viewer identity into export pipeline
- Remote cursor/selection labels in `src/promptgrimoire/pages/annotation/broadcast.py` — anonymise display name for peer viewers

**Dependencies:** Phase 3 (anonymisation utility), Phase 4 (permission threading)

**Done when:** PDF exports show anonymised author names when anonymous_sharing is enabled and exporter is a peer. Instructor exports always show true names. Broadcast labels anonymised for peers. Covers workspace-sharing-97.AC4 (export aspect).
<!-- END_PHASE_7 -->

## Additional Considerations

**Comment concurrency:** The CRDT comment storage uses a full-replace pattern (read list, mutate, write entire highlight back). Concurrent comment additions from two clients on the same highlight result in last-write-wins on the list. At MVP scale (~50 students, rarely two commenting on the same highlight simultaneously), this is acceptable. If it becomes a problem, comments can be migrated to a proper pycrdt Array without changing the external interface.

**Backwards compatibility:** Existing highlights and comments lack `user_id`. The anonymisation utility treats `None` user_id as "Unknown" for instructors and uses the standard anonymised label for peers. No migration of existing CRDT data required.

**Workspace.shared_with_class and cloning:** When a workspace is cloned from an activity, `shared_with_class` defaults to `False`. The student must explicitly opt in. This prevents accidental exposure of in-progress work.

**Peer discovery query vs resolve_permission:** The "Peer Workspaces" list on the course page uses a direct query (`list_peer_workspaces`) that filters by `shared_with_class=True` and `allow_sharing` in one query — it does NOT call `resolve_permission` per workspace. `resolve_permission` is only for single-workspace page loads. This avoids N+1 query patterns.

**Mid-session sharing changes:** If an instructor disables `allow_sharing` while peers are connected, already-connected peers retain access until they reload. Real-time revocation broadcast is out of scope for this design. If immediate cutoff is needed, the instructor can revoke individual ACL entries (which triggers the existing websocket-based revocation from Seam D).

**Comment deletion authorization:** Comment deletion ownership checks (`user_id` match) are enforced at the server-side Python layer before calling `crdt_doc.delete_comment()`. Clients do not have direct CRDT write access — all mutations go through NiceGUI server-side callbacks. This is the same trust model used for all existing annotation operations.
