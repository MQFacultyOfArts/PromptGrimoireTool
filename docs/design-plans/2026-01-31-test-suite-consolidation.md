# Test Suite Consolidation Design

## Summary

This design consolidates 94 end-to-end tests spread across demo-dependent test files into a focused test suite targeting the `/annotation` route. The current test suite has significant technical debt: 68 tests rely on deprecated `/demo/*` routes that use fragile patterns like global CRDT state resets and hardcoded word indices, while the 26 tests in `test_annotation_page.py` duplicate setup code across test methods. The consolidation uses `pytest-subtests` to share expensive setup (browser context creation, authentication, navigation) across related assertions, reducing both test count and execution time by approximately 50%.

The approach involves six phases: installing test infrastructure (`pytest-subtests` for shared setup, `pytest-depper` for affected-test-only CI runs), consolidating edge case tests in `test_annotation_page.py`, creating two new test files for real-time sync and multi-user collaboration scenarios, migrating coverage from demo tests to annotation tests, and finally deprecating then removing the demo test files. All new tests use UUID-based workspace isolation instead of global state manipulation, follow existing patterns from `test_annotation_page.py` (authenticated fixtures, helper methods, explicit timeout assertions), and simulate real user behavior through Playwright's native APIs without JavaScript injection.

## Definition of Done

- All E2E tests for `/annotation` route use `pytest-subtests` for shared setup
- Demo page tests (`test_live_annotation.py`, `test_text_selection.py`, `test_two_tab_sync.py`) are deprecated/removed
- Two-tab sync tests rewritten for annotation highlight sync (not raw text editing)
- Multi-user collaboration tests cover highlight/cursor/selection broadcasting
- Test count reduced while maintaining or improving coverage
- No tests depend on `/demo/*` routes
- `pytest-depper` available for affected-test-only CI runs

## Glossary

- **E2E (End-to-End) tests**: Automated tests that exercise the full application stack from browser UI to database, simulating real user interactions using Playwright
- **pytest-subtests**: Pytest plugin that allows multiple assertions within a single test method to share setup/teardown while reporting each as a separate subtest result
- **pytest-depper**: Pytest plugin that analyzes code changes and runs only tests affected by those changes, reducing CI runtime
- **CRDT (Conflict-free Replicated Data Type)**: Data structure used for collaborative editing that allows multiple users to make concurrent changes that automatically converge to the same state
- **Fixture**: Pytest mechanism for providing reusable setup/teardown code (like authenticated browser contexts) to test functions
- **Playwright**: Browser automation framework used to drive E2E tests by simulating user interactions (clicks, typing, navigation)
- **UUID-based isolation**: Pattern where each test creates uniquely identified data (using UUID v4) to prevent interference between parallel test runs
- **Workspace**: A PromptGrimoire document container that can be annotated; contains HTML content and associated highlights/comments
- **Highlight**: User-created annotation span with associated color, tags, and optional comments

## Architecture

**Current state:** 68 E2E tests across 4 demo-dependent files + 26 tests in `test_annotation_page.py`. Demo tests use fragile patterns (global CRDT reset, hardcoded word indices, per-test browser context overhead).

**Target state:** Consolidated test suite using `pytest-subtests` for shared setup within test classes. Demo pages deprecated. All annotation functionality tested via `/annotation` route.

**Test file structure:**

```
tests/e2e/
├── test_annotation_page.py      # Core workflows (consolidated with subtests)
├── test_annotation_sync.py      # NEW: Two-tab real-time sync
├── test_annotation_collab.py    # NEW: Multi-user collaboration
├── test_auth_and_isolation.py   # Route-agnostic auth/isolation tests
└── conftest.py                  # Shared fixtures (two_annotation_tabs, etc.)

tests/e2e/deprecated/            # Moved before deletion
├── test_live_annotation.py
├── test_text_selection.py
├── test_two_tab_sync.py
└── test_user_isolation.py
```

**Key fixture:**

```python
@pytest.fixture
def two_annotation_tabs(browser, app_server, request):
    """Two authenticated browser tabs viewing same workspace."""
    workspace_id = create_test_workspace()
    context = browser.new_context()
    tab1 = context.new_page()
    tab2 = context.new_page()
    # Auth both tabs, navigate to same workspace
    yield tab1, tab2, workspace_id
    context.close()
```

## Existing Patterns

Investigation found existing test patterns in `test_annotation_page.py`:

- `authenticated_page` fixture for per-test browser context with mock auth
- `_create_highlight()` and `_select_words()` helpers for common operations
- `pytestmark_db` decorator for database-dependent tests
- `expect()` assertions with explicit timeouts

This design follows these patterns and extends them with:
- `pytest-subtests` for multiple assertions sharing setup
- Class-scoped fixtures for two-tab scenarios
- Shared workspace fixtures for collaboration tests

**Divergence:** Demo tests used global CRDT reset (`reset_crdt_state` fixture). New tests use UUID-based workspace isolation only - no global state manipulation.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Add pytest-subtests and pytest-depper

**Goal:** Install dependencies and verify they work

**Components:**
- `pyproject.toml` - add pytest-subtests, pytest-depper to dev dependencies
- Verify both plugins load correctly

**Dependencies:** None

**Done when:** `uv run pytest --co` shows plugins loaded, existing tests still pass
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Consolidate test_annotation_page.py with subtests

**Goal:** Reduce setup overhead by using subtests for related assertions

**Components:**
- `tests/e2e/test_annotation_page.py` - refactor 8 new edge case classes into 3-4 consolidated test methods using subtests
- Keep existing working tests, only consolidate the new edge cases (TestDeleteHighlight, TestChangeTagDropdown, TestKeyboardShortcuts, TestOverlappingHighlights, TestGoToHighlight, TestCardHoverEffect, TestSpecialContent)

**Dependencies:** Phase 1

**Done when:** Edge case tests consolidated, all tests pass, reduced test count with same coverage
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Create test_annotation_sync.py

**Goal:** Real-time sync tests between browser tabs on `/annotation`

**Components:**
- `tests/e2e/test_annotation_sync.py` - NEW file
- `tests/e2e/conftest.py` - add `two_annotation_tabs` fixture
- Tests for: highlight appears in other tab, delete syncs, comment syncs, cursor/selection presence

**Dependencies:** Phase 2

**Done when:** Two-tab highlight sync verified, 10+ sync scenarios covered
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Create test_annotation_collab.py

**Goal:** Multi-user collaboration tests

**Components:**
- `tests/e2e/test_annotation_collab.py` - NEW file
- Tests for: two users see each other's highlights, user count badge (after implementation), concurrent editing

**Dependencies:** Phase 3, Task #11 (user count badge)

**Done when:** Multi-user scenarios verified, concurrent operations handled correctly
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: Migrate remaining demo test coverage

**Goal:** Ensure all demo test behaviors are covered in new tests

**Components:**
- Review `test_live_annotation.py` - migrate any uncovered behaviors to `test_annotation_page.py`
- Review `test_text_selection.py` - verify coverage is implicit in existing tests
- Review `test_user_isolation.py` - migrate route-agnostic tests to `test_auth_and_isolation.py`

**Dependencies:** Phase 4

**Done when:** All demo test behaviors have equivalent coverage in new tests (except paragraph detection - blocked on Seam G)
<!-- END_PHASE_5 -->

<!-- START_PHASE_6 -->
### Phase 6: Deprecate and remove demo tests

**Goal:** Clean removal of demo-dependent tests

**Components:**
- Move `test_live_annotation.py`, `test_text_selection.py`, `test_two_tab_sync.py`, `test_user_isolation.py` to `tests/e2e/deprecated/`
- Add `pytest.mark.skip` with reason pointing to new test locations
- After verification period, delete deprecated directory

**Dependencies:** Phase 5

**Done when:** Demo tests moved to deprecated, CI runs only new tests, old tests skipped
<!-- END_PHASE_6 -->

## Additional Considerations

**Related Design:** See [2026-01-30-workspace-model.md](./2026-01-30-workspace-model.md) for the companion workspace model design. This test consolidation is part of the same branch (93-workspace-model) and executes in parallel with Phase 5 (Teardown) of that design.

**Paragraph detection tests (8 tests):** Blocked on Seam G (#99). Added as comment to that issue. These tests cannot be migrated until paragraph number detection is implemented in `/annotation`.

**Test execution time:** With subtests and shared setup, expect ~50% reduction in E2E test time. pytest-depper further reduces CI time by running only affected tests on PRs.

**Backward compatibility:** Demo pages remain functional during migration. Tests are deprecated (skipped) before deletion, allowing rollback if issues found.
