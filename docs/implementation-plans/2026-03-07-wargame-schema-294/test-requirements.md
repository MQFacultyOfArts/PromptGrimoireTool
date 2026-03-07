# Test Requirements: Wargame Schema (#294)

Maps each acceptance criterion from `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/wargame-schema-294/docs/design-plans/2026-03-06-wargame-schema-294.md` to automated tests or human verification. Rationalised against the implementation-plan decisions:
- stronger composite-FK subtype enforcement for `WargameConfig` and `WargameTeam`
- `sequence_no` as the canonical message ordering field
- ACL query-audit as a first-class deliverable

---

## Automated Test Mapping

### wargame-schema-294.AC1: Activity type discriminator

| Criterion | Test type | Test file | Phase | Test description |
|---|---|---|---|---|
| **AC1.1** Existing annotation activities automatically have `type='annotation'` after migration | integration | `tests/integration/test_wargame_schema.py::TestActivityTypeDiscriminator` | 1 | Preferred test: use migration-step fixtures if discovered during execution. Accepted fallback: insert an annotation activity without explicitly setting `type`, read it back, and assert `type == "annotation"` because the migration relies on the server default. |
| **AC1.2** New activity with `type='wargame'` and no `template_workspace_id` is accepted | integration | `tests/integration/test_wargame_schema.py::TestActivityTypeDiscriminator` | 1 | Persist a wargame activity with no template workspace and assert flush succeeds plus `template_workspace_id is None`. |
| **AC1.3** New activity with `type='annotation'` and a `template_workspace_id` is accepted | integration | `tests/integration/test_wargame_schema.py::TestActivityTypeDiscriminator` and `tests/integration/test_activity_crud.py::TestCreateActivity` | 1 | Keep the existing annotation creation path green and assert `create_activity()` yields `type == "annotation"` with a non-null template workspace. |
| **AC1.4** Activity with `type='annotation'` and NULL `template_workspace_id` is rejected by CHECK | integration | `tests/integration/test_wargame_schema.py::TestActivityTypeDiscriminator` | 1 | Insert annotation activity with NULL template and assert `IntegrityError` on `ck_activity_annotation_requires_template`. |
| **AC1.5** Activity with `type='wargame'` and a non-NULL `template_workspace_id` is rejected by CHECK | integration | `tests/integration/test_wargame_schema.py::TestActivityTypeDiscriminator` | 1 | Insert wargame activity with template workspace and assert `IntegrityError` on `ck_activity_wargame_no_template`. |

### wargame-schema-294.AC2: WargameConfig

| Criterion | Test type | Test file | Phase | Test description |
|---|---|---|---|---|
| **AC2.1** WargameConfig with `timer_delta` set and `timer_wall_clock` NULL is accepted | unit + integration | `tests/unit/test_wargame_models.py::TestWargameConfigValidation` and `tests/integration/test_wargame_schema.py::TestWargameConfigTable` | 2 | Assert the model validates and the DB persists a config with `timer_delta` only. |
| **AC2.2** WargameConfig with `timer_wall_clock` set and `timer_delta` NULL is accepted | unit + integration | `tests/unit/test_wargame_models.py::TestWargameConfigValidation` and `tests/integration/test_wargame_schema.py::TestWargameConfigTable` | 2 | Assert the model validates and the DB persists a config with `timer_wall_clock` only. |
| **AC2.3** WargameConfig with both timer fields NULL is rejected by CHECK | unit + integration | `tests/unit/test_wargame_models.py::TestWargameConfigValidation` and `tests/integration/test_wargame_schema.py::TestWargameConfigTable` | 2 | Assert model validation fails and DB constraint `ck_wargame_config_timer_exactly_one` rejects the row. |
| **AC2.4** WargameConfig with both timer fields set is rejected by CHECK | unit + integration | `tests/unit/test_wargame_models.py::TestWargameConfigValidation` and `tests/integration/test_wargame_schema.py::TestWargameConfigTable` | 2 | Assert model validation fails and DB constraint `ck_wargame_config_timer_exactly_one` rejects the row. |

### wargame-schema-294.AC3: WargameTeam

| Criterion | Test type | Test file | Phase | Test description |
|---|---|---|---|---|
| **AC3.1** Team created with codename and defaults (round 0, state 'drafting', NULL artifacts) | integration | `tests/integration/test_wargame_schema.py::TestWargameTeamTable` | 3 | Persist a team and assert default `current_round`, `round_state`, and NULL artifact fields. |
| **AC3.2** Multiple teams with different codenames under same activity | integration | `tests/integration/test_wargame_schema.py::TestWargameTeamTable` | 3 | Persist two teams with distinct codenames under one parent activity and assert both succeed. |
| **AC3.3** Duplicate codename under same activity rejected by UNIQUE | integration | `tests/integration/test_wargame_schema.py::TestWargameTeamTable` | 3 | Attempt a duplicate codename under one activity and assert `IntegrityError` on `uq_wargame_team_activity_codename`. |
| **AC3.4** Deleting the parent activity cascades to delete all teams | integration | `tests/integration/test_wargame_schema.py::TestWargameTeamTable` | 3 | Delete the parent activity and assert the child team row is gone. |

### wargame-schema-294.AC4: WargameMessage

| Criterion | Test type | Test file | Phase | Test description |
|---|---|---|---|---|
| **AC4.1** Message appended with next sequence_no | integration | `tests/integration/test_wargame_schema.py::TestWargameMessageTable` | 4 | Insert messages with ordered sequence numbers, query with `ORDER BY sequence_no ASC`, and assert canonical order is by `sequence_no`. |
| **AC4.2** Messages with different roles ('user', 'assistant', 'system') accepted | integration | `tests/integration/test_wargame_schema.py::TestWargameMessageTable` | 4 | Persist one message of each supported role and assert flush succeeds. |
| **AC4.3** Duplicate (team_id, sequence_no) rejected by UNIQUE | integration | `tests/integration/test_wargame_schema.py::TestWargameMessageTable` | 4 | Insert a duplicate `(team_id, sequence_no)` pair and assert `IntegrityError` on `uq_wargame_message_team_sequence`. |
| **AC4.4** Deleting team cascades to delete all messages | integration | `tests/integration/test_wargame_schema.py::TestWargameMessageTable` | 4 | Delete the parent team and assert the child message rows are gone. |

### wargame-schema-294.AC5: ACLEntry extension

| Criterion | Test type | Test file | Phase | Test description |
|---|---|---|---|---|
| **AC5.1** ACL grant with workspace_id set and team_id NULL (existing behaviour) | unit + integration | `tests/unit/test_wargame_models.py::TestAclEntryTargetValidation` and `tests/integration/test_wargame_schema.py::TestAclEntryTeamExtension` | 5 | Validate and persist a workspace-target ACL row; assert it remains valid. |
| **AC5.2** ACL grant with team_id set and workspace_id NULL (new team grant) | unit + integration | `tests/unit/test_wargame_models.py::TestAclEntryTargetValidation` and `tests/integration/test_wargame_schema.py::TestAclEntryTeamExtension` | 5 | Validate and persist a team-target ACL row; assert it remains valid. |
| **AC5.3** ACL grant with both workspace_id and team_id set rejected by CHECK | unit + integration | `tests/unit/test_wargame_models.py::TestAclEntryTargetValidation` and `tests/integration/test_wargame_schema.py::TestAclEntryTeamExtension` | 5 | Assert model validation and DB constraint reject a dual-target ACL row. |
| **AC5.4** ACL grant with both NULL rejected by CHECK | unit + integration | `tests/unit/test_wargame_models.py::TestAclEntryTargetValidation` and `tests/integration/test_wargame_schema.py::TestAclEntryTeamExtension` | 5 | Assert model validation and DB constraint reject a no-target ACL row. |
| **AC5.5** Existing workspace ACL grants remain valid after migration | integration | `tests/integration/test_wargame_schema.py::TestAclEntryTeamExtension` and `tests/integration/test_sharing_controls.py::TestGrantShareSuccess` | 5 | Assert workspace-target uniqueness still holds, `list_entries_for_user()` can return mixed targets, peer-listing queries remain NULL-safe when team-target rows exist, and existing `grant_share()` workspace ACL flows still create workspace-target rows with `team_id is None`. |

### wargame-schema-294.AC7: SQLModel classes

| Criterion | Test type | Test file | Phase | Test description |
|---|---|---|---|---|
| **AC7.1** All new tables (WargameConfig, WargameTeam, WargameMessage) have corresponding SQLModel classes | unit | `tests/unit/test_db_schema.py::test_all_models_registered` and `tests/unit/test_db_schema.py::test_get_expected_tables_returns_all_tables` | 2-4 | Assert all expected table names are registered in SQLModel metadata. |
| **AC7.2** Modified tables (Activity, ACLEntry) have updated SQLModel classes with new fields | unit | `tests/unit/test_wargame_models.py::TestActivityTypeValidation` and `tests/unit/test_wargame_models.py::TestAclEntryTargetValidation` | 1, 5 | Assert the updated models expose and enforce the new discriminator and ACL target invariants. |

### wargame-schema-294.AC8: Existing tests

| Criterion | Test type | Test file | Phase | Test description |
|---|---|---|---|---|
| **AC8.1** All existing unit and integration tests pass without modification (except where Activity's template_workspace_id nullability requires model-level validation updates) | harness regression | `uv run grimoire test all` | 1-5 | Use the project harness as the primary regression gate proving existing test suites still pass. |

---

## Human Verification

### wargame-schema-294.AC6: Migration integrity

| Criterion | Verification | Why human/local | Verification approach |
|---|---|---|---|
| **AC6.1** Migration applies to a database with existing data without errors | Human/local verification on a disposable database | Current codebase investigation did not find an established migration-step test harness for upgrade-from-old-schema with seeded legacy rows. | Create a disposable DB at revision `c08959d80031`, seed representative annotation data, run `alembic upgrade head`, and confirm the upgrade succeeds plus legacy rows are preserved. |
| **AC6.2** Migration downgrades cleanly | Human/local verification on a disposable database | The current downgrade is intentionally destructive for wargame-only rows and team-target ACL rows; this is better verified operationally on a disposable DB than assumed via a fixture pattern that does not yet exist. | Upgrade a disposable DB to head, seed wargame config/team/message/team-target ACL data, run `alembic downgrade c08959d80031`, and confirm downgrade succeeds with the expected destructive deletes. |

---

## Branch-Local Supplemental Checks

These are not separate design-plan AC groups, but the implementation plan intentionally adds them because of the stronger schema design adopted during planning.

| Supplemental check | Test type | Test file | Phase | Test description |
|---|---|---|---|---|
| `WargameConfig` cannot reference annotation activities | integration | `tests/integration/test_wargame_schema.py::TestWargameConfigTable` | 2 | Attempt to attach config to an annotation activity and assert failure on the composite FK or local discriminator check. |
| `WargameTeam` cannot reference annotation activities | integration | `tests/integration/test_wargame_schema.py::TestWargameTeamTable` | 3 | Attempt to attach a team to an annotation activity and assert failure on the composite FK or local discriminator check. |
| `sequence_no` remains the canonical sort key after edits/regenerations | integration | `tests/integration/test_wargame_schema.py::TestWargameMessageTable` | 4 | Update an earlier message row in place, re-read ordered by `sequence_no`, and assert order remains stable. |
| Workspace ACL queries remain NULL-safe in the presence of team-target rows | integration | `tests/integration/test_wargame_schema.py::TestAclEntryTeamExtension` | 5 | Prove team-target rows with `workspace_id NULL` do not poison workspace-owner subqueries or mixed-target listing paths. |

---

## Coverage Summary

| Category | Count | Notes |
|---|---|---|
| Automated AC checks | 22 | Covers AC1-AC5, AC7, and AC8 |
| Human/local AC checks | 2 | Both are AC6 migration-integrity checks |
| Supplemental automated checks | 4 | Stronger schema invariants adopted during planning |

All design-plan acceptance criteria are mapped either to automated verification or explicit human/local migration verification.
