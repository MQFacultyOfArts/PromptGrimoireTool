# Workspace ACL — Test Requirements

**Design plan:** `docs/design-plans/2026-02-15-96-workspace-acl.md`

**Generated from:** Acceptance Criteria (96-workspace-acl.AC1–AC10)

---

## Traceability Matrix

| AC | Description | Phase | Test File | Test Function Pattern |
|----|-------------|-------|-----------|----------------------|
| AC1.1 | Permission table seed data (owner/editor/viewer with levels) | 1 | `tests/integration/test_acl_reference_tables.py` | `test_permission_seed_data` |
| AC1.2 | CourseRole table seed data (coordinator/instructor/tutor/student with levels) | 1 | `tests/integration/test_acl_reference_tables.py` | `test_course_role_seed_data` |
| AC1.3 | Seed data created by migration, not seed-data script | 1 | `tests/integration/test_acl_reference_tables.py` | `test_seed_from_migration` |
| AC1.4 | Duplicate name INSERT rejected (UNIQUE) | 1 | `tests/integration/test_acl_reference_tables.py` | `test_duplicate_name_rejected` |
| AC1.5 | Level columns have CHECK (1-100) and UNIQUE constraints | 1 | `tests/integration/test_acl_reference_tables.py` | `test_level_constraints` |
| AC3.1 | CourseEnrollment uses role FK to course_role table | 2 | `tests/integration/test_course_role_normalisation.py` | `test_enrollment_role_fk` |
| AC3.2 | Week visibility unchanged after normalisation | 2 | `tests/integration/test_course_role_normalisation.py` | `test_week_visibility_after_normalisation` |
| AC3.3 | Enrollment CRUD accepts role by reference table lookup | 2 | `tests/integration/test_course_role_normalisation.py` | `test_enrollment_crud_by_role_name` |
| AC3.4 | Invalid role_id rejected (FK constraint) | 2 | `tests/integration/test_course_role_normalisation.py` | `test_invalid_role_rejected` |
| AC4.1 | ACLEntry created with valid workspace_id, user_id, permission | 3 | `tests/integration/test_acl_crud.py` | `test_acl_entry_creation` |
| AC4.2 | Deleting Workspace CASCADEs to ACLEntry | 3 | `tests/integration/test_acl_crud.py` | `test_workspace_delete_cascades_acl` |
| AC4.3 | Deleting User CASCADEs to ACLEntry | 3 | `tests/integration/test_acl_crud.py` | `test_user_delete_cascades_acl` |
| AC4.4 | Duplicate (workspace_id, user_id) rejected (UNIQUE) | 3 | `tests/integration/test_acl_crud.py` | `test_duplicate_acl_entry_rejected` |
| AC4.5 | Grant to existing pair upserts permission | 3 | `tests/integration/test_acl_crud.py` | `test_grant_upserts_permission` |
| AC5.1 | Grant permission to user on workspace | 3 | `tests/integration/test_acl_crud.py` | `test_grant_permission` |
| AC5.2 | Revoke permission (delete ACLEntry) | 3 | `tests/integration/test_acl_crud.py` | `test_revoke_permission` |
| AC5.3 | List all ACL entries for a workspace | 3 | `tests/integration/test_acl_crud.py` | `test_list_entries_for_workspace` |
| AC5.4 | List all ACL entries for a user | 3 | `tests/integration/test_acl_crud.py` | `test_list_entries_for_user` |
| AC6.1 | Explicit ACL entry returns that permission | 4 | `tests/integration/test_permission_resolution.py` | `test_explicit_acl_permission` |
| AC6.2 | Instructor gets Course.default_instructor_permission | 4 | `tests/integration/test_permission_resolution.py` | `test_instructor_enrollment_derived` |
| AC6.3 | Coordinator gets enrollment-derived access | 4 | `tests/integration/test_permission_resolution.py` | `test_coordinator_enrollment_derived` |
| AC6.4 | Tutor gets enrollment-derived access | 4 | `tests/integration/test_permission_resolution.py` | `test_tutor_enrollment_derived` |
| AC6.5 | Higher of explicit ACL and enrollment-derived wins | 4 | `tests/integration/test_permission_resolution.py` | `test_higher_permission_wins` |
| AC6.6 | Admin gets owner-level access regardless | 4, 8 | `tests/integration/test_permission_resolution.py`, `tests/integration/test_enforcement.py` | `test_admin_bypass` |
| AC6.7 | Student without ACL gets None | 4 | `tests/integration/test_permission_resolution.py` | `test_student_no_acl_denied` |
| AC6.8 | Unenrolled user without ACL gets None | 4 | `tests/integration/test_permission_resolution.py` | `test_unenrolled_denied` |
| AC6.9 | No auth session gets None | 4, 8 | `tests/integration/test_permission_resolution.py`, `tests/integration/test_enforcement.py` | `test_no_auth_denied` |
| AC6.10 | Loose workspace — only explicit ACL | 4 | `tests/integration/test_permission_resolution.py` | `test_loose_workspace_explicit_only` |
| AC6.11 | Course-placed workspace — instructor access from enrollment | 4 | `tests/integration/test_permission_resolution.py` | `test_course_placed_instructor_access` |
| AC7.1 | Clone creates owner ACLEntry | 5 | `tests/integration/test_clone_ownership.py` | `test_clone_creates_owner_acl` |
| AC7.2 | Clone gated by enrollment | 5 | `tests/integration/test_clone_ownership.py` | `test_clone_requires_enrollment` |
| AC7.3 | Clone gated by week visibility | 5 | `tests/integration/test_clone_ownership.py` | `test_clone_requires_visible_week` |
| AC7.4 | Duplicate clone returns existing workspace | 5 | `tests/integration/test_clone_ownership.py` | `test_duplicate_clone_returns_existing` |
| AC7.5 | Unauthenticated cannot clone | 5 | `tests/integration/test_clone_ownership.py` | `test_unauthenticated_clone_rejected` |
| AC7.6 | Unenrolled cannot clone | 5 | `tests/integration/test_clone_ownership.py` | `test_unenrolled_clone_rejected` |
| AC8.1 | Owner shares as editor when sharing allowed | 6 | `tests/integration/test_sharing_controls.py` | `test_share_as_editor` |
| AC8.2 | Owner shares as viewer when sharing allowed | 6 | `tests/integration/test_sharing_controls.py` | `test_share_as_viewer` |
| AC8.3 | allow_sharing=None inherits course default | 6 | `tests/integration/test_sharing_controls.py` | `test_sharing_inherits_course_default` |
| AC8.4 | allow_sharing=True overrides course False | 6 | `tests/integration/test_sharing_controls.py` | `test_sharing_activity_overrides_course_true` |
| AC8.5 | allow_sharing=False overrides course True | 6 | `tests/integration/test_sharing_controls.py` | `test_sharing_activity_overrides_course_false` |
| AC8.6 | Instructor shares regardless of allow_sharing | 6 | `tests/integration/test_sharing_controls.py` | `test_staff_share_bypasses_flag` |
| AC8.7 | Non-owner cannot share | 6 | `tests/integration/test_sharing_controls.py` | `test_non_owner_cannot_share` |
| AC8.8 | Owner cannot share when sharing disabled | 6 | `tests/integration/test_sharing_controls.py` | `test_owner_blocked_when_sharing_disabled` |
| AC8.9 | Cannot grant owner permission via sharing | 6 | `tests/integration/test_sharing_controls.py` | `test_cannot_grant_owner_via_share` |
| AC9.1 | Student sees owned workspaces | 7 | `tests/integration/test_listing_queries.py` | `test_student_sees_owned_workspaces` |
| AC9.2 | Student sees shared workspaces | 7 | `tests/integration/test_listing_queries.py` | `test_student_sees_shared_workspaces` |
| AC9.3 | Instructor sees all student workspaces in course | 7 | `tests/integration/test_listing_queries.py` | `test_instructor_sees_course_workspaces` |
| AC9.4 | Instructor sees loose workspaces in course | 7 | `tests/integration/test_listing_queries.py` | `test_instructor_sees_loose_workspaces` |
| AC9.5 | Resume shown when user has workspace | 7 | `tests/integration/test_listing_queries.py` | `test_resume_detection_existing` |
| AC9.6 | Start Activity shown when no workspace | 7 | `tests/integration/test_listing_queries.py` | `test_start_activity_detection_none` |
| AC9.7 | Deleted activity workspace still in my-workspaces | 7 | `tests/integration/test_listing_queries.py` | `test_orphaned_workspace_still_listed` |
| AC10.1 | Unauthenticated redirected to /login | 8 | `tests/integration/test_enforcement.py` | `test_unauthenticated_redirect_login` |
| AC10.2 | Unauthorised redirected to /courses | 8 | `tests/integration/test_enforcement.py` | `test_unauthorised_redirect_courses` |
| AC10.3 | Viewer sees read-only UI | 8 | `tests/integration/test_enforcement.py` | `test_viewer_read_only` |
| AC10.4 | Editor/owner sees full UI | 8 | `tests/integration/test_enforcement.py` | `test_editor_owner_full_ui` |
| AC10.5 | Revocation pushes redirect via websocket | 8 | `tests/integration/test_enforcement.py` | `test_revocation_push_redirect` |
| AC10.6 | Revoked user sees toast notification | 8 | `tests/integration/test_enforcement.py` | `test_revocation_toast` |
| AC10.7 | No websocket — revocation on next page load | 8 | `tests/integration/test_enforcement.py` | `test_revocation_no_websocket` |

## Test File Summary

| Test File | Phase | AC Groups | Count |
|-----------|-------|-----------|-------|
| `tests/integration/test_acl_reference_tables.py` | 1 | AC1 | 5 |
| `tests/integration/test_course_role_normalisation.py` | 2 | AC3 | 4 |
| `tests/integration/test_acl_crud.py` | 3 | AC4, AC5 | 9 |
| `tests/integration/test_permission_resolution.py` | 4 | AC6 | 11 |
| `tests/integration/test_clone_ownership.py` | 5 | AC7 | 6 |
| `tests/integration/test_sharing_controls.py` | 6 | AC8 | 9 |
| `tests/integration/test_listing_queries.py` | 7 | AC9 | 7 |
| `tests/integration/test_enforcement.py` | 8 | AC6.6, AC6.9, AC10 | 9 |
| **Total** | | | **60** |

## Notes

- All integration tests require PostgreSQL (`DEV__TEST_DATABASE_URL`). Include skip guard: `pytest.mark.skipif(not get_settings().dev.test_database_url, reason="DEV__TEST_DATABASE_URL not configured")`.
- AC10.3 and AC10.4 (read-only vs full UI) are tested at the function return level in integration tests. Full UI verification deferred to E2E tests.
- AC10.5 and AC10.6 (websocket push) require connected NiceGUI clients. Tested as `revoke_and_redirect()` returning 0 when no clients connected (AC10.7). Full E2E testing deferred.
- AC7.5 is a type-system guarantee (function requires `user_id: UUID`). Page-level auth check tested via `_get_user_id()` returning `None`.
- Tests use `@pytest_asyncio.fixture` for all async fixtures (never `@pytest.fixture` on async functions).
