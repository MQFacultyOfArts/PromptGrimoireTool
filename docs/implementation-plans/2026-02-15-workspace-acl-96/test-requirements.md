# Workspace ACL — Test Requirements

**Design plan:** `docs/design-plans/2026-02-15-96-workspace-acl.md`

**Generated from:** Acceptance Criteria (96-workspace-acl.AC1–AC10)

**Last audited:** 2026-02-16

---

## Traceability Matrix

| AC | Description | Phase | Test File | Test Class / Function |
|----|-------------|-------|-----------|-----------------------|
| AC1.1 | Permission table seed data (owner/editor/viewer with levels) | 1 | `tests/integration/test_acl_reference_tables.py` | `TestPermissionSeedData` (3 tests: owner, editor, viewer + row count) |
| AC1.2 | CourseRole table seed data (coordinator/instructor/tutor/student with levels) | 1 | `tests/integration/test_acl_reference_tables.py` | `TestCourseRoleRefSeedData` (5 tests: 4 roles + row count) |
| AC1.3 | Seed data created by migration, not seed-data script | 1 | `tests/integration/test_acl_reference_tables.py` | `TestSeedDataFromMigration` (2 tests: CLI source inspection) + implicit: integration tests find data without seed-data CLI |
| AC1.4 | Duplicate name INSERT rejected (PK constraint) | 1 | `tests/integration/test_acl_reference_tables.py` | `TestPermissionDuplicateNameRejected`, `TestCourseRoleRefDuplicateNameRejected` |
| AC1.5 | Level columns have CHECK (1-100) and UNIQUE constraints | 1 | `tests/integration/test_acl_reference_tables.py` | `TestPermissionLevelConstraints`, `TestCourseRoleRefLevelConstraints` |
| AC3.1 | CourseEnrollment uses role FK to course_role table | 2 | `tests/integration/test_course_role_normalisation.py` | `test_enrollment_with_valid_role` |
| AC3.2 | Week visibility unchanged after normalisation | 2 | `tests/integration/test_course_role_normalisation.py` | `TestWeekVisibility` (2 tests: instructor sees all, student sees published) |
| AC3.3 | Enrollment CRUD accepts role by reference table lookup | 2 | `tests/integration/test_course_role_normalisation.py` | `TestEnrollmentCRUD` (3 tests: enroll, update, default role) |
| AC3.4 | Invalid role_id rejected (FK constraint) | 2 | `tests/integration/test_course_role_normalisation.py` | `test_enrollment_with_invalid_role_raises` |
| AC4.1 | ACLEntry created with valid workspace_id, user_id, permission | 3 | `tests/integration/test_acl_crud.py` | `test_creates_acl_entry` |
| AC4.2 | Deleting Workspace CASCADEs to ACLEntry | 3 | `tests/integration/test_acl_crud.py` | `test_deleting_workspace_deletes_acl_entries` |
| AC4.3 | Deleting User CASCADEs to ACLEntry | 3 | `tests/integration/test_acl_crud.py` | `test_deleting_user_deletes_acl_entries` |
| AC4.4 | Duplicate (workspace_id, user_id) rejected (UNIQUE) | 3 | `tests/integration/test_acl_crud.py` | `test_duplicate_pair_raises_integrity_error` |
| AC4.5 | Grant to existing pair upserts permission | 3 | `tests/integration/test_acl_crud.py` | `test_upsert_updates_permission` |
| AC5.1 | Grant permission to user on workspace | 3 | `tests/integration/test_acl_crud.py` | `test_creates_acl_entry` (same as AC4.1) |
| AC5.2 | Revoke permission (delete ACLEntry) | 3 | `tests/integration/test_acl_crud.py` | `TestRevoke` (3 tests: revoke existing, nonexistent, double) |
| AC5.3 | List all ACL entries for a workspace | 3 | `tests/integration/test_acl_crud.py` | `test_returns_all_entries_for_workspace` + empty case |
| AC5.4 | List all ACL entries for a user | 3 | `tests/integration/test_acl_crud.py` | `test_returns_all_entries_for_user` + empty case |
| AC6.1 | Explicit ACL entry returns that permission | 4 | `tests/integration/test_permission_resolution.py` | `TestExplicitACL` (3 tests: viewer, editor, owner) |
| AC6.2 | Instructor gets Course.default_instructor_permission | 4 | `tests/integration/test_permission_resolution.py` | `TestEnrollmentDerivedInstructor` (3 tests: default, custom, template) |
| AC6.3 | Coordinator gets enrollment-derived access | 4 | `tests/integration/test_permission_resolution.py` | `TestEnrollmentDerivedCoordinator::test_coordinator_gets_default_permission` |
| AC6.4 | Tutor gets enrollment-derived access | 4 | `tests/integration/test_permission_resolution.py` | `TestEnrollmentDerivedTutor::test_tutor_gets_default_permission` |
| AC6.5 | Higher of explicit ACL and enrollment-derived wins | 4 | `tests/integration/test_permission_resolution.py` | `TestHighestWins` (2 tests: derived beats viewer, explicit owner beats derived) |
| AC6.6 | Admin gets owner-level access regardless | 4, 8 | `tests/integration/test_permission_resolution.py`, `tests/integration/test_enforcement.py` | `TestAdminBypass` (3 tests: is_privileged admin, instructor, DB layer returns None). Full composition in Phase 8. |
| AC6.7 | Student without ACL gets None | 4 | `tests/integration/test_permission_resolution.py` | `TestStudentDenial::test_student_without_acl_gets_none` |
| AC6.8 | Unenrolled user without ACL gets None | 4 | `tests/integration/test_permission_resolution.py` | `TestUnenrolledDenial::test_unenrolled_user_gets_none` |
| AC6.9 | No auth session gets None | 4, 8 | `tests/integration/test_permission_resolution.py`, `tests/integration/test_enforcement.py` | `TestNoAuthDenial` (2 tests: is_privileged None, unknown UUID). Full composition in Phase 8. |
| AC6.10 | Loose workspace — only explicit ACL | 4 | `tests/integration/test_permission_resolution.py` | `TestLooseWorkspace` (3 tests: no ACL, with ACL, instructor elsewhere) |
| AC6.11 | Course-placed workspace — instructor access from enrollment | 4 | `tests/integration/test_permission_resolution.py` | `TestCoursePlacedWorkspace` (2 tests: instructor access, student denial) |
| AC7.1 | Clone creates owner ACLEntry | 5 | `tests/integration/test_clone_ownership.py` | `TestCloneOwnership` (2 tests: creates entry, matches user) |
| AC7.2 | Clone gated by enrollment | 5 | `tests/integration/test_clone_eligibility.py`, `tests/integration/test_clone_ownership.py` | `test_enrolled_student_published_week_eligible`, `TestEligibilityGatesInCloneFlow::test_enrolled_student_eligible` |
| AC7.3 | Clone gated by week visibility | 5 | `tests/integration/test_clone_eligibility.py` | 4 tests: unpublished blocks student, future blocks student, staff bypasses both |
| AC7.4 | Duplicate clone returns existing workspace | 5 | `tests/integration/test_clone_ownership.py` | `TestDuplicateDetection` (3 tests: no workspace, existing, different user) |
| AC7.5 | Unauthenticated cannot clone | 5 | `tests/integration/test_clone_ownership.py` | `TestUnauthenticatedCloneRejection::test_clone_rejects_none_user_id` (type-system guarantee) |
| AC7.6 | Unenrolled cannot clone | 5 | `tests/integration/test_clone_eligibility.py`, `tests/integration/test_clone_ownership.py` | `test_unenrolled_user_rejected`, `test_unenrolled_user_blocked` |
| AC8.1 | Owner shares as editor when sharing allowed | 6 | `tests/integration/test_sharing_controls.py` | `test_owner_shares_as_editor` |
| AC8.2 | Owner shares as viewer when sharing allowed | 6 | `tests/integration/test_sharing_controls.py` | `test_owner_shares_as_viewer` |
| AC8.3 | allow_sharing=None inherits course default | 6 | `tests/integration/test_sharing_controls.py` | `test_activity_inherits_from_course_true`, `test_activity_inherits_from_course_false` |
| AC8.4 | allow_sharing=True overrides course False | 6 | `tests/integration/test_sharing_controls.py` | `test_activity_overrides_course_true` |
| AC8.5 | allow_sharing=False overrides course True | 6 | `tests/integration/test_sharing_controls.py` | `test_activity_overrides_course_false` |
| AC8.6 | Instructor shares regardless of allow_sharing | 6 | `tests/integration/test_sharing_controls.py` | `test_staff_bypasses_sharing_flag` |
| AC8.7 | Non-owner cannot share | 6 | `tests/integration/test_sharing_controls.py` | `test_non_owner_cannot_share` |
| AC8.8 | Owner cannot share when sharing disabled | 6 | `tests/integration/test_sharing_controls.py` | `test_sharing_disabled_blocks_owner` |
| AC8.9 | Cannot grant owner permission via sharing | 6 | `tests/integration/test_sharing_controls.py` | `test_cannot_grant_owner_permission` |
| AC9.1 | Student sees owned workspaces | 7 | `tests/integration/test_listing_queries.py` | 2 tests: cloned workspace, loose workspace |
| AC9.2 | Student sees shared workspaces | 7 | `tests/integration/test_listing_queries.py` | `test_shared_viewer_sees_workspace` |
| AC9.3 | Instructor sees all student workspaces in course | 7 | `tests/integration/test_listing_queries.py` | 2 tests: sees student clone, excludes template |
| AC9.4 | Instructor sees loose workspaces in course | 7 | `tests/integration/test_listing_queries.py` | `test_includes_loose_workspace` |
| AC9.5 | Resume shown when user has workspace | 7 | `tests/integration/test_listing_queries.py` | `test_owner_gets_resume` |
| AC9.6 | Start Activity shown when no workspace | 7 | `tests/integration/test_listing_queries.py` | `test_shared_viewer_gets_start` |
| AC9.7 | Deleted activity workspace still in my-workspaces | 7 | `tests/integration/test_listing_queries.py` | `test_orphaned_workspace_still_accessible` |
| AC10.1 | Unauthenticated redirected to /login | 8 | `tests/integration/test_enforcement.py` | `TestCheckWorkspaceAccessUnauthenticated::test_unauthenticated_returns_none` |
| AC10.2 | Unauthorised redirected to /courses | 8 | `tests/integration/test_enforcement.py` | `TestCheckWorkspaceAccessUnauthorised::test_unauthorised_user_returns_none` |
| AC10.3 | Viewer sees read-only UI | 8 | `tests/integration/test_enforcement.py` | `TestCheckWorkspaceAccessViewer::test_viewer_returns_viewer` |
| AC10.4 | Editor/owner sees full UI | 8 | `tests/integration/test_enforcement.py` | `TestCheckWorkspaceAccessEditorOwner` (2 tests: editor, owner) |
| AC10.5 | Revocation pushes redirect via websocket | 8 | `tests/integration/test_enforcement.py` | Deferred to E2E (websocket needed) |
| AC10.6 | Revoked user sees toast notification | 8 | `tests/integration/test_enforcement.py` | Deferred to E2E (websocket needed) |
| AC10.7 | No websocket — revocation on next page load | 8 | `tests/integration/test_enforcement.py` | `TestRevocationBroadcast` (2 tests: returns 0, cleans up dict) |

## Test File Summary

| Test File | Phase | AC Groups | Count |
|-----------|-------|-----------|-------|
| `tests/integration/test_acl_reference_tables.py` | 1 | AC1 | 5 + 2 (AC1.3 explicit) |
| `tests/integration/test_course_role_normalisation.py` | 2 | AC3 | 4 |
| `tests/integration/test_acl_crud.py` | 3 | AC4, AC5 | 9 |
| `tests/integration/test_permission_resolution.py` | 4 | AC6 | 11 + 5 (AC6.6, AC6.9) |
| `tests/integration/test_clone_eligibility.py` | 5 | AC7.2, AC7.3, AC7.6 | 7 |
| `tests/integration/test_clone_ownership.py` | 5 | AC7 | 6 + 1 (AC7.5) |
| `tests/integration/test_sharing_controls.py` | 6 | AC8 | 9 |
| `tests/integration/test_listing_queries.py` | 7 | AC9 | 7 |
| `tests/integration/test_enforcement.py` | 8 | AC6.6, AC6.9, AC10 | 11 |
| **Total** | | | **71** |

## Notes

- All integration tests require PostgreSQL (`DEV__TEST_DATABASE_URL`). Include skip guard: `pytest.mark.skipif(not get_settings().dev.test_database_url, reason="DEV__TEST_DATABASE_URL not configured")`.
- AC10.3 and AC10.4 (read-only vs full UI) are tested at the function return level in integration tests. Full UI verification deferred to E2E tests.
- AC10.5 and AC10.6 (websocket push) require connected NiceGUI clients. Tested as `revoke_and_redirect()` returning 0 when no clients connected (AC10.7). Full E2E testing deferred.
- AC7.5 is a type-system guarantee (function requires `user_id: UUID`). Explicit test verifies TypeError on None.
- AC6.6 and AC6.9 are split: building blocks tested in Phase 4 (is_privileged_user + resolve_permission), full composition via check_workspace_access() tested in Phase 8.
- Tests use `@pytest_asyncio.fixture` for all async fixtures (never `@pytest.fixture` on async functions).
- Test names in matrix now reflect **actual** class/function names in source, not aspirational names.
