# E2E Test Suite Refactor: Instructor Workflow Split

**GitHub Issue:** None

## Summary
This design plan addresses the significant flakiness and execution time of the monolithic `test_instructor_workflow.py` E2E test. It splits the instructor journey into four distinct, narrative-driven testing components. UI-heavy administrative tasks (Course Creation, Enrollment, and Tag Configuration) are migrated to fast `nicegui_user` integration tests, leveraging direct WebSocket interaction to bypass browser rendering overhead. The remaining Javascript-heavy canvas interactions (DOM Text Selection, Custom Highlights, and Keyboard Shortcuts) are preserved as smaller, focused Playwright E2E tests. To enable this separation without redundant setup, the design relies heavily on direct PostgreSQL database seeding to inject fully-formed workspace states prior to executing UI interactions.

## Definition of Done
1. The monolithic `test_instructor_workflow.py` file is removed.
2. The testing narrative is preserved across multiple, smaller test files.
3. Test execution time is reduced by running non-DOM UI tests via the `nicegui_user` fixture instead of Playwright.
4. The remaining E2E tests focus strictly on the JS-heavy annotation canvas interactions.
5. All test behavior/coverage (including student clone verification and keyboard shortcuts) is fully maintained.

## Acceptance Criteria
/### e2e-instructor-workflow-split.AC1: Component Refactoring/!b
n
c\
- **e2e-instructor-workflow-split.AC1.1 Success:** `tests/e2e/test_instructor_workflow.py` is entirely deleted from the codebase.\
- **e2e-instructor-workflow-split.AC1.2 Success:** The test suite passes in CI/CD without the monolithic file.\
\
### e2e-instructor-workflow-split.AC2: The "Glue" Happy Path E2E\
- **e2e-instructor-workflow-split.AC2.1 Success:** `test_happy_path_workflow.py` successfully creates a course, activity, and single tag without database seeding.\
- **e2e-instructor-workflow-split.AC2.2 Success:** The test successfully enrolls a student who clicks "Start Activity" and applies the tag.\
- **e2e-instructor-workflow-split.AC2.3 Prevention:** The test proves that browser state correctly transitions between administrative setup and canvas interaction without state bleed.\
\
### e2e-instructor-workflow-split.AC3: Exhaustive Setup Integration Tests\
- **e2e-instructor-workflow-split.AC3.1 Success:** `test_instructor_setup_ui.py` can exhaustively create, rename, and change colors for tags.\
- **e2e-instructor-workflow-split.AC3.2 Success:** The test successfully locks tags and reorders tag groups.\
- **e2e-instructor-workflow-split.AC3.3 Success:** The test exhaustively verifies course and activity creation edge cases.\
- **e2e-instructor-workflow-split.AC3.4 Performance:** The test executes via `nicegui_user` without invoking a Playwright browser instance.\
\
### e2e-instructor-workflow-split.AC4: Exhaustive Canvas E2E\
- **e2e-instructor-workflow-split.AC4.1 Success:** `test_annotation_canvas.py` successfully navigates to a pre-seeded workspace and applies a tag to text via the Playwright DOM.\
- **e2e-instructor-workflow-split.AC4.2 Restriction:** The student persona is prevented from renaming a pre-seeded locked tag (input is readonly).\
- **e2e-instructor-workflow-split.AC4.3 Success:** The student persona successfully uses keyboard shortcuts to apply tags based on the instructor's custom sort order.\
- **e2e-instructor-workflow-split.AC4.4 Success:** The instructor persona successfully threads a comment on a highlight and organises cards.\
\
## Glossary\
- **`nicegui_user`**: A testing fixture provided by NiceGUI that simulates a connected client over a WebSocket, allowing for fast, browserless integration testing of UI state.\
- **Playwright**: The E2E testing framework used to drive actual headless browser instances, required for testing complex DOM APIs like the TreeWalker or CSS Custom Highlights.\
- **Database Seeding**: The practice of using backend scripts (e.g., `_create_workspace_via_db`) to insert required data directly into PostgreSQL to skip slow UI setup steps.\
- **Template Workspace**: The instructor's version of an activity workspace where the rubric (tags, instructions, locked elements) is configured before being cloned by students.\
\
## Architecture\
\
The refactoring splits the massive 700+ line `test_instructor_workflow.py` file into a "Smoke + Exhaustive" pattern using three highly-focused testing components across two execution environments:\
\
1.  **The "Glue" E2E Test (`tests/e2e/test_happy_path_workflow.py`):**\
    A severely stripped-down version of the original monolithic test. It performs zero database seeding. An instructor creates a course, adds an activity, adds exactly one tag, and enrolls a student. The student logs in, clicks "Start Activity" and applies the tag. This guards against "state bleed" across navigations and proves the actual browser UI correctly stages data for the database.\
2.  **Exhaustive Setup Integration (`tests/integration/test_instructor_setup_ui.py`):**\
    Uses the fast `nicegui_user` WebSocket simulator to exhaustively test all administrative UI edge cases: locking tags, reordering groups, toggling copy protection, handling empty inputs, etc. This tests the Quasar/NiceGUI state without Playwright overhead.\
3.  **Exhaustive Canvas E2E (`tests/e2e/test_annotation_canvas.py`):**\
    Uses robust database seeding to instantly drop the instructor or student into fully-loaded workspaces. This file consolidates all the Playwright-heavy features: Keyboard shortcuts, TreeWalker boundaries, Custom Highlight rendering, and complex DOM coordinate mapping.\
\
## Existing Patterns\
\
Investigation found two distinct test environments currently in use:\
1.  **Playwright E2E (`tests/e2e/`):** Uses the `authenticated_page` fixture and requires full browser rendering. Used for testing the CRDT sync and the custom Javascript annotation API.\
2.  **NiceGUI User Integration (`tests/integration/`):** Uses the `nicegui_user` fixture (e.g., `test_crud_management_ui.py`) to simulate user clicks over the NiceGUI websocket directly against the ASGI application.\
\
This design aggressively expands the usage of pattern #2 to offload UI-heavy, DOM-independent tests from the slow E2E suite.\
\
We also continue the pattern of using `pytest-subtests` within narrative test files to prevent redundant teardowns, and we rely heavily on the existing database seeding pattern (`_create_workspace_via_db`, `_seed_tags_for_workspace`) from `tests/e2e/annotation_helpers.py`.\
\
## Implementation Phases\
\
<!-- START_PHASE_1 -->\
### Phase 1: The "Glue" Happy Path E2E\
**Goal:** Implement the stripped-down, continuous workflow test to guard against state bleed.\
\
**Components:**\
- `tests/e2e/test_happy_path_workflow.py` — New file testing the critical path from course creation to student annotation without DB seeding.\
\
**Dependencies:** None\
\
**Done when:** The happy path test passes using Playwright, proving the real browser UI can successfully stage data across the full journey.\
<!-- END_PHASE_1 -->\
\
<!-- START_PHASE_2 -->\
### Phase 2: Exhaustive Setup Integration\
**Goal:** Implement the complex UI edge case testing using `nicegui_user`.\
\
**Components:**\
- `tests/integration/test_instructor_setup_ui.py` — New file testing the Tag CRUD Quasar dialogs, course creation edge cases, and copy protection toggles.\
- Uses DB seeding helpers where appropriate to jump to specific dialog states.\
\
**Dependencies:** None\
\
**Done when:** All administrative UI edge cases (locking tags, reordering, validation) pass using the websocket harness.\
<!-- END_PHASE_2 -->\
\
<!-- START_PHASE_3 -->\
### Phase 3: Exhaustive Canvas E2E\
**Goal:** Consolidate all complex JS/DOM interactions into a focused Playwright test.\
\
**Components:**\
- `tests/e2e/test_annotation_canvas.py` — New E2E test file.\
- Heavily utilizes `_create_workspace_via_db` and `_seed_tags_for_workspace` to bypass UI setup.\
- Tests keyboard shortcuts, TreeWalker boundaries, and locked tag readonly assertions.\
\
**Dependencies:** None\
\
**Done when:** Instructor and student canvas interactions pass robustly using Playwright.\
<!-- END_PHASE_3 -->\
\
<!-- START_PHASE_4 -->\
### Phase 4: Teardown Monolith\
**Goal:** Remove the old monolithic test to realize the speed and maintenance gains.\
\
**Components:**\
- `tests/e2e/test_instructor_workflow.py` — File deleted.\
\
**Dependencies:** Phases 1, 2, and 3\
\
**Done when:** The original monolithic file is removed and the full test suite runs cleanly.\
<!-- END_PHASE_4 -->\
\
## Additional Considerations\
\
**Database Seeding Strategy:** The massive performance gain in Phases 3 and 4 relies on bypassing UI clicks to set up the workspace. We will lean entirely on SQL-level inserts (`tests/e2e/annotation_helpers.py`) to position the application state exactly where the Playwright assertions need to begin.\
