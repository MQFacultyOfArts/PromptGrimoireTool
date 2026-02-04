# WIP: Implementation Plan - Spike COMPLETED

**Date:** 2026-02-04
**Status:** Spike PASSED, resuming implementation plan

## Spike Results (2026-02-04)

**Hypothesis:** "Removing xdist_group from service layer tests works because:
1. xdist workers are separate processes (isolated `_state`)
2. `reset_db_engine_per_test` disposes engine after each test
3. Each test gets fresh connections in its own event loop"

**Test Results:**

| Test File | Tests | Result |
|-----------|-------|--------|
| spike_service_layer_xdist.py | 6 | PASSED (5 consecutive runs) |
| test_workspace_crud (no marker) | 14 | PASSED |
| test_workspace_persistence (no marker) | 8 | PASSED |
| test_course_service (no marker) | 22 | PASSED |

**HYPOTHESIS VALIDATED** - Phase 3-4 approach (just remove xdist_group markers) is correct.

## Implementation Plan Status
- Phase 1 (phase_01.md): Add NullPool fixture - WRITTEN
- Phase 2 (phase_02.md): Migrate test_db_async.py - WRITTEN
- Phase 3 (phase_03.md): Remove xdist_group from workspace tests - WRITTEN, VALIDATED
- Phase 4 (phase_04.md): Remove xdist_group from course tests - WRITTEN, VALIDATED
- Phase 5 (phase_05.md): Document fixture responsibilities - WRITTEN (REVISED from original design)
- Phase 6 (phase_06.md): Verify full parallelism - WRITTEN

## Additional Spike: reset_db_engine_per_test (2026-02-04)

**Hypothesis:** "reset_db_engine_per_test can be removed"

**Test:** Removed fixture, ran workspace tests with -n 4

**Result:** 6 failed, 8 passed - `RuntimeError: Event loop is closed`

**Conclusion:** Fixture is REQUIRED for service layer tests. Pooled connections bind to event loops. Design Phase 5 revised accordingly.
