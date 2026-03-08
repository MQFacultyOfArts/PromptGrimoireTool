# Wargame Team Management and ACL Design

**GitHub Issue:** #295

## Summary

Seam 2 builds the service layer that lets a Game Master populate and manage teams in a wargame activity. The work has two parts. First, a pure domain layer handles codename generation (unique two-word slugs like BOLD-GRIFFIN via the `coolname` library) and CSV roster parsing (validating emails, roles, and team assignments with clear error reporting). Second, an imperative shell in `db/wargames.py` wires that pure logic to the database: creating and deleting teams, and managing who belongs to which team through the existing ACL table.

Access control for teams mirrors the existing workspace permission system. The same `acl_entry` table is reused, with `team_id` instead of `workspace_id`, so team members get `viewer` or `editor` roles with identical resolution semantics. A zero-editor invariant prevents any revoke or downgrade that would leave a team with no editors. Roster ingestion is fully atomic: a CSV upload either succeeds completely or rolls back, and re-importing a roster updates roles without removing existing members.

## Definition of Done

Seam 2 delivers the service layer for wargame team lifecycle and access control. Specifically:

1. **Team CRUD** (`db/wargames.py`) -- create team (with `coolname`-generated codename), list/get teams for an activity, delete team.
2. **Codename generator** -- single-word operation-style names via `coolname` library, collision-retry within activity scope.
3. **CSV roster parser** -- parse `email,team,role` format (role defaults to `editor` if omitted), validate structure, return clear errors on malformed input.
4. **Roster ingestion service** -- find-or-create users from emails, create teams from unique team values (or auto-assign round-robin to N teams when team column absent), grant ACL entries.
5. **Team ACL functions** -- `grant_team_permission()`, `revoke_team_permission()`, `resolve_team_permission()`, `list_team_members()`.
6. **Zero-editor invariant** -- reject any revoke or role-change that would leave a team with zero editors.
7. **Membership update semantics** -- re-import is additive (updates roles, never removes members); explicit remove operation with zero-editor guard.

**Success criteria:**
- All functions tested (unit + integration with DB).
- ACL resolution for teams works analogously to workspace ACL resolution.
- GM access via `is_privileged_user()` bypasses team ACL (existing infrastructure).
- CSV parsing handles malformed input gracefully (clear error messages).

**Out of scope:**
- GM UI for team management (Seam 5).
- Player room access checks (Seam 4).
- Excel/XLSX parsing.
- CRDT move buffer or notes (Seam 4).

## Acceptance Criteria

### wargame-team-mgmt-295.AC1: Codename Generation
- **wargame-team-mgmt-295.AC1.1 Success:** Generates 2-word uppercase slug (e.g. BOLD-GRIFFIN)
- **wargame-team-mgmt-295.AC1.2 Success:** No collisions within same activity
- **wargame-team-mgmt-295.AC1.3 Edge:** Retries on collision, raises after cap exceeded

### wargame-team-mgmt-295.AC2: CSV Roster Parsing
- **wargame-team-mgmt-295.AC2.1 Success:** Parses email,team,role with all columns present
- **wargame-team-mgmt-295.AC2.2 Success:** Role defaults to editor when column missing or empty
- **wargame-team-mgmt-295.AC2.3 Success:** team=None for all entries when team column absent
- **wargame-team-mgmt-295.AC2.4 Failure:** Duplicate email within CSV raises RosterParseError with line numbers
- **wargame-team-mgmt-295.AC2.5 Failure:** Malformed email (no @) raises RosterParseError
- **wargame-team-mgmt-295.AC2.6 Failure:** Invalid role value raises RosterParseError
- **wargame-team-mgmt-295.AC2.7 Success:** auto_assign_teams distributes round-robin across N teams

### wargame-team-mgmt-295.AC3: Team CRUD
- **wargame-team-mgmt-295.AC3.1 Success:** create_team generates codename and persists
- **wargame-team-mgmt-295.AC3.2 Success:** create_teams batch creates N teams with unique codenames
- **wargame-team-mgmt-295.AC3.3 Success:** delete_team cascades to ACL entries and messages
- **wargame-team-mgmt-295.AC3.4 Success:** rename_team updates codename
- **wargame-team-mgmt-295.AC3.5 Failure:** Rename to existing codename raises DuplicateCodenameError

### wargame-team-mgmt-295.AC4: Team ACL
- **wargame-team-mgmt-295.AC4.1 Success:** grant_team_permission upserts (create or update)
- **wargame-team-mgmt-295.AC4.2 Success:** resolve_team_permission returns permission or None
- **wargame-team-mgmt-295.AC4.3 Success:** list_team_members returns (User, permission) tuples

### wargame-team-mgmt-295.AC5: Zero-Editor Invariant
- **wargame-team-mgmt-295.AC5.1 Failure:** Revoke last editor raises ZeroEditorError
- **wargame-team-mgmt-295.AC5.2 Failure:** Downgrade last editor to viewer raises ZeroEditorError
- **wargame-team-mgmt-295.AC5.3 Failure:** Upsert grant that would downgrade last editor to viewer raises ZeroEditorError

### wargame-team-mgmt-295.AC6: Roster Ingestion
- **wargame-team-mgmt-295.AC6.1 Success:** Full pipeline creates teams, users, and ACL grants atomically
- **wargame-team-mgmt-295.AC6.2 Success:** Auto-assign mode with team_count distributes across new teams
- **wargame-team-mgmt-295.AC6.3 Failure:** Auto-assign mode without team_count raises error

### wargame-team-mgmt-295.AC7: Membership Update Semantics
- **wargame-team-mgmt-295.AC7.1 Success:** Re-import updates roles without removing existing members

## Glossary

- **Seam**: A vertical slice of the wargame feature, delivering a coherent chunk of back-end capability. This document covers Seam 2 (team management); other seams cover the schema (Seam 1), player rooms (Seam 4), and GM UI (Seam 5).
- **Wargame**: An activity type in PromptGrimoire where teams of students interact with an AI-driven scenario managed by a Game Master (GM). Extends the base `Activity` model via `WargameConfig`.
- **Game Master (GM)**: The instructor role that controls a wargame. GMs are identified by `is_privileged_user()` and bypass team ACL checks entirely.
- **coolname**: A Python library that generates random human-readable slugs from adjective-noun word lists. Used here to produce team codenames like BOLD-GRIFFIN.
- **ACL (Access Control List)**: The permission system in PromptGrimoire. Stored in the `acl_entry` table; each row binds a user to a target (workspace or team) with a `viewer` or `editor` role.
- **Partial unique index**: A PostgreSQL index with a `WHERE` clause, allowing uniqueness to be enforced over a subset of rows. Used here so `(team_id, user_id)` uniqueness is enforced independently of workspace-target rows in the same table.
- **Upsert**: An `INSERT ... ON CONFLICT DO UPDATE` operation that creates a row if it does not exist or updates it if it does. Used for ACL grants so re-granting a permission updates the role rather than failing.
- **Zero-editor invariant**: The rule that every team must always have at least one `editor`. Any revoke or role downgrade that would violate this is rejected with `ZeroEditorError`.
- **Functional core / imperative shell**: An architecture pattern where pure functions handle logic (no side effects, easy to test in isolation) and a thin "shell" layer coordinates I/O and database calls. The pure core lives in `wargame/`, the shell in `db/wargames.py`.
- **Round-robin distribution**: Assigning items to slots in cycling order (1, 2, 3, 1, 2, 3...). Used by `auto_assign_teams()` when the CSV has no team column and a team count is given instead.
- **RosterEntry**: A frozen dataclass representing one parsed row from a CSV upload: email, optional team name, and role.
- **RosterReport**: A frozen dataclass returned by `ingest_roster()` on success, summarising what was created and updated.
- **find_or_create_user**: An existing function in `db/users.py` that returns a user by email, creating them if they do not yet exist. Reused by roster ingestion to avoid duplicate user creation logic.
- **CASCADE**: A database-level rule on a foreign key that automatically deletes dependent rows when the parent row is deleted. Deleting a team cascades to its ACL entries and messages.
- **Additive re-import**: The membership update policy where uploading a roster a second time updates roles for existing members but never removes anyone. Members can only be removed through an explicit remove operation.

## Architecture

Functional core / imperative shell separation across two packages:

**Pure domain logic** (`src/promptgrimoire/wargame/`):
- `codenames.py` -- codename generation using `coolname`. Pure function: takes a set of existing codenames, returns a new unique one. Retry loop with cap on collisions.
- `roster.py` -- CSV parsing and validation. Returns `list[RosterEntry]` dataclass instances. Also contains `auto_assign_teams()` for round-robin distribution. No DB access.

**Imperative shell** (`src/promptgrimoire/db/wargames.py`):
- Team CRUD: `create_team()`, `create_teams()`, `get_team()`, `list_teams()`, `delete_team()`, `rename_team()`.
- Team ACL: `grant_team_permission()`, `revoke_team_permission()`, `resolve_team_permission()`, `list_team_members()`, `update_team_permission()`, `remove_team_member()`.
- Roster orchestration: `ingest_roster()` wires the pure parsing layer to DB operations in a single atomic session.

**Data flow:**

```
CSV text
  -> parse_roster()          [pure: wargame/roster.py]
  -> auto_assign_teams()     [pure: wargame/roster.py, if needed]
  -> ingest_roster()         [imperative: db/wargames.py]
     -> find_or_create_user()  [existing: db/users.py]
     -> create_team()          [new: db/wargames.py]
     -> grant_team_permission() [new: db/wargames.py]
  -> RosterReport            [dataclass: result summary]
```

**ACL integration:** Team ACL functions are parallel to workspace ACL functions in `db/acl.py`. They target the same `acl_entry` table using `team_id` instead of `workspace_id`, with the existing partial unique index `uq_acl_entry_team_user`. No modifications to existing workspace ACL code.

**Permission model:** Teams use `viewer` and `editor` from the existing `permission` table. GM access is not stored in ACL -- it uses `is_privileged_user()` at the page level (existing infrastructure, unchanged by this seam).

## Existing Patterns

**CRUD module structure** (`db/activities.py`, `db/users.py`): Async functions using `get_session()` context manager, flush + refresh, return model instances. `db/wargames.py` follows this pattern exactly.

**User lookup** (`db/users.py`): `find_or_create_user(email, display_name)` returns `tuple[User, bool]`. Roster ingestion reuses this -- no new user creation logic needed.

**ACL upsert** (`db/acl.py:grant_permission()`): Uses `pg_insert().on_conflict_do_update()` targeting partial unique index. Team ACL grant mirrors this pattern but targets `uq_acl_entry_team_user` with `workspace_id=None`.

**Domain exceptions** (`db/courses.py`): `DuplicateEnrollmentError`, `DeletionBlockedError` with descriptive attributes. New exceptions (`DuplicateCodenameError`, `ZeroEditorError`, `RosterParseError`) follow the same convention.

**Display name derivation** (`cli/admin.py`): `email.split("@", maxsplit=1)[0].replace(".", " ").title()`. Roster ingestion reuses this for auto-generated display names.

**Codename style divergence:** The design doc specifies "single-word operation style" but `coolname` generates minimum 2-word names. Design decision: use 2-word coolname slugs uppercased (e.g. BOLD-GRIFFIN). This is a departure from the spec, accepted in brainstorming.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Codename Generator and Roster Parser (Pure Core)

**Goal:** Implement the pure domain logic with no DB dependencies.

**Components:**
- `src/promptgrimoire/wargame/__init__.py` -- package init
- `src/promptgrimoire/wargame/codenames.py` -- `generate_codename(existing: set[str]) -> str` using `coolname.generate_slug(2)`, uppercased, collision retry with cap
- `src/promptgrimoire/wargame/roster.py` -- `RosterEntry` frozen dataclass, `parse_roster(csv_content: str) -> list[RosterEntry]`, `auto_assign_teams(entries, team_count) -> list[RosterEntry]`, `RosterParseError` with line-level detail
- Tests in `tests/unit/test_codenames.py` and `tests/unit/test_roster.py`

**Dependencies:** None (pure functions, no DB).

**Done when:** Codename generation produces unique 2-word uppercase slugs with collision retry. CSV parsing handles valid input, missing role (defaults to editor), missing team column (all entries get `team=None`), malformed input (clear errors with line numbers), duplicate emails (rejected). Auto-assign distributes entries round-robin. All unit tests pass.

**Covers:** wargame-team-mgmt-295.AC1, wargame-team-mgmt-295.AC2
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Team CRUD

**Goal:** Database operations for team lifecycle.

**Components:**
- `src/promptgrimoire/db/wargames.py` -- `create_team()`, `create_teams()`, `get_team()`, `list_teams()`, `delete_team()`, `rename_team()`, `DuplicateCodenameError`
- Export new functions from `src/promptgrimoire/db/__init__.py`
- Tests in `tests/unit/test_wargame_team_crud.py` (model validation) and `tests/integration/test_wargame_team_crud.py` (DB operations)

**Dependencies:** Phase 1 (codename generator).

**Done when:** Teams can be created with auto-generated codenames, listed per activity, retrieved by ID, deleted (CASCADE cleans up ACL + messages), renamed with uniqueness enforcement. Integration tests verify DB round-trips and constraint enforcement.

**Covers:** wargame-team-mgmt-295.AC3
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Team ACL Functions

**Goal:** Permission grant, revoke, resolve, and query for team targets.

**Components:**
- Team ACL functions in `src/promptgrimoire/db/wargames.py` -- `grant_team_permission()`, `revoke_team_permission()`, `resolve_team_permission()`, `list_team_members()`, `update_team_permission()`, `remove_team_member()`, `ZeroEditorError`
- Internal helper `_assert_editors_remain(session, team_id, exclude_user_id)` for zero-editor invariant
- Export new functions from `src/promptgrimoire/db/__init__.py`
- Tests in `tests/integration/test_wargame_team_acl.py`

**Dependencies:** Phase 2 (team CRUD -- needs teams to grant permissions on).

**Done when:** Permissions can be granted (upsert with zero-editor guard on downgrades), revoked (with zero-editor guard), resolved (simple lookup), listed (with user info). Role changes from editor to viewer are blocked when the user is the last editor -- including via upsert in `grant_team_permission()`. Integration tests verify upsert behaviour, zero-editor rejection across all code paths, and permission resolution.

**Covers:** wargame-team-mgmt-295.AC4, wargame-team-mgmt-295.AC5
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Roster Ingestion Orchestrator

**Goal:** Wire CSV parsing to DB operations in an atomic pipeline.

**Components:**
- `ingest_roster()` in `src/promptgrimoire/db/wargames.py` -- orchestrates parse, user creation, team creation, ACL grants
- `RosterReport` frozen dataclass in `src/promptgrimoire/db/wargames.py`
- Tests in `tests/integration/test_roster_ingestion.py`

**Dependencies:** Phases 1 (parser), 2 (team CRUD), 3 (team ACL).

**Done when:** Full pipeline works: CSV in, teams created, users found-or-created, ACL entries granted. Re-import updates roles without removing members. Auto-assign mode distributes across N teams. Mixed mode (some with team, some without) raises error. Atomicity verified (partial failure rolls back). Integration tests cover happy path, re-import, auto-assign, and error cases.

**Covers:** wargame-team-mgmt-295.AC6, wargame-team-mgmt-295.AC7
<!-- END_PHASE_4 -->

## Additional Considerations

**Codename collision cap:** `generate_codename()` retries up to 100 times before raising. With `coolname`'s 2-word namespace (~10^5 combinations), collisions are vanishingly unlikely for realistic team counts (<50 per activity). The cap is a safety net, not expected to trigger.

**CSV delimiter detection:** `parse_roster()` uses Python's `csv.Sniffer` or defaults to comma. Header detection is case-insensitive. Columns beyond `email`, `team`, `role` are ignored silently (forward-compatible with future fields like `mqid`).

**Transaction scope:** `ingest_roster()` runs in a single `get_session()` block. If any step fails (e.g. invalid email format that somehow passes parsing, FK violation), the entire import rolls back. The `RosterReport` is only returned on full success.
