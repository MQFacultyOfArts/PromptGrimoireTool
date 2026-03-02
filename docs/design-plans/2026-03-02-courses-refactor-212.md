# Courses Page Refactoring Design

**GitHub Issue:** [#212](https://github.com/MQFacultyOfArts/PromptGrimoireTool/issues/212)

## Summary

`courses.py` is a 1,011-line, single-file module handling five distinct page routes for unit management (listing, detail, creation, enrollments, and associated dialogs). Its `course_detail_page` function has a cognitive complexity score of 130, far above the project threshold of 15, and every course-specific page duplicates the same 15-line auth/database/enrollment check verbatim. The refactor converts this file into a structured Python package — `pages/courses/` — with one module per concern, matching the pattern already established by `pages/annotation/`.

The approach is test-first. Before any structural change, characterisation tests are written against the unmodified code using NiceGUI's `user` fixture (a lightweight in-process test client, introduced here for the first time in this project). These tests lock in existing behaviour and serve as the regression gate for all subsequent extraction. The `@require_course_access` decorator is then introduced to replace the repeated auth boilerplate, `page_layout()` is adopted to give all course pages consistent chrome (nav drawer, header), and the detail page is decomposed until every function falls within the complexity limit. The sequence is deliberately incremental: each phase leaves the test suite green before the next phase begins.

## Definition of Done

1. **Characterisation tests added** — unit tests for pure functions (`_model_to_ui`, `_ui_to_model`, `_build_peer_map`), integration tests for data-fetching logic currently buried in page functions, covering the blindspots identified in the baseline investigation
2. **All course pages use `page_layout()`** — consistent nav drawer, header, and chrome across all 5 routes (`/courses`, `/courses/new`, `/courses/{id}`, `/courses/{id}/weeks/new`, `/courses/{id}/weeks/{week_id}/activities/new`, `/courses/{id}/enrollments`)
3. **Auth/DB boilerplate extracted** — `@require_course_access` decorator replaces the repeated 15-line auth/DB/user check pattern across all page functions
4. **All functions pass complexipy threshold** — no function in `courses.py` (or extracted modules) exceeds cognitive complexity 15. Baseline: `course_detail_page` at 130, `manage_enrollments_page` at 28
5. **Existing E2E tests still pass** — `test_instructor_workflow.py` and related tests are the regression gate

## Acceptance Criteria

### courses-refactor-212.AC1: Characterisation tests cover existing behaviour
- **courses-refactor-212.AC1.1 Success:** Unit tests for `_model_to_ui` cover all three cases: `None` → `"inherit"`, `True` → `"on"`, `False` → `"off"`
- **courses-refactor-212.AC1.2 Success:** Unit tests for `_ui_to_model` cover the inverse: `"inherit"` → `None`, `"on"` → `True`, `"off"` → `False`
- **courses-refactor-212.AC1.3 Success:** Integration test for `_build_peer_map` returns correct peer data with anonymisation applied
- **courses-refactor-212.AC1.4 Success:** `user` fixture tests verify each page route renders without error for an enrolled user
- **courses-refactor-212.AC1.5 Failure:** `user` fixture tests verify unauthenticated access to `/courses/{id}` shows error, not course content

### courses-refactor-212.AC2: All pages use `page_layout()`
- **courses-refactor-212.AC2.1 Success:** Every course page renders a nav drawer with navigation items
- **courses-refactor-212.AC2.2 Success:** Every course page renders a header with page title and user email

### courses-refactor-212.AC3: Auth decorator extracts boilerplate
- **courses-refactor-212.AC3.1 Success:** `@require_course_access` injects `course`, `user_id`, `enrollment` into decorated function
- **courses-refactor-212.AC3.2 Failure:** Decorator renders error and returns early for invalid UUID, missing course, missing enrollment
- **courses-refactor-212.AC3.3 Failure:** `@require_course_access(require_role=_MANAGER_ROLES)` rejects enrolled users without manager role

### courses-refactor-212.AC4: All functions pass complexity threshold
- **courses-refactor-212.AC4.1 Success:** Extracted modules import correctly and all existing tests pass after extraction
- **courses-refactor-212.AC4.2 Success:** `complexipy src/promptgrimoire/pages/courses/ --max-complexity-allowed 15` reports zero failures
- **courses-refactor-212.AC4.3 Success:** No function in the package exceeds 40 lines

### courses-refactor-212.AC5: Existing E2E tests pass
- **courses-refactor-212.AC5.1 Success:** `test_instructor_workflow.py`, `test_navigator.py`, `test_anonymous_sharing.py` all pass unchanged

## Glossary

- **characterisation test**: A test written to document what existing code already does, not to specify new behaviour. Used here to create a safety net before restructuring code that lacks tests.
- **cognitive complexity**: A metric (used by complexipy and SonarQube) that scores how hard a function is to understand, weighting nested control flow more heavily than cyclomatic complexity. Threshold here is 15.
- **complexipy**: A Python tool that measures and enforces cognitive complexity limits on functions.
- **`@ui.page`**: NiceGUI decorator that registers a function as the handler for a URL route.
- **`@ui.refreshable`**: NiceGUI decorator that marks a function whose rendered output can be re-rendered in place without a full page reload.
- **`user` fixture**: NiceGUI's built-in pytest fixture that runs page functions in-process with a simulated browser client. Faster than Playwright; no real browser required.
- **`page_layout()`**: A context manager in `pages/layout.py` that renders the application's shared chrome — header, nav drawer, optional footer — around page content.
- **`@page_route` decorator**: A project-internal decorator (in `pages/registry.py`) that registers a page in the nav drawer in addition to wiring its URL route.
- **`@require_course_access`**: A new decorator introduced by this refactor. Handles auth, database initialisation, UUID parsing, course lookup, user lookup, enrollment check, and optional role check before calling the decorated page function.
- **`_course_clients`**: A module-level dict tracking which browser clients are currently viewing a course detail page, used to broadcast refresh signals when course content changes.
- **tri-state option**: A setting that can be `on`, `off`, or `inherit` (meaning: defer to the parent unit's setting). Used for copy-protection and similar per-activity toggles.
- **peer map**: A data structure mapping each activity to its visible peer workspaces with anonymised display names.
- **module-per-concern pattern**: The architectural convention (followed by `pages/annotation/`) of splitting a large module into submodules where each file handles one coherent responsibility.

## Architecture

Decompose `src/promptgrimoire/pages/courses.py` (1011 lines, complexity 130) into a `pages/courses/` package following the annotation page's module-per-concern pattern, adapted for the smaller scope.

### Package Structure

```
src/promptgrimoire/pages/courses/
├── __init__.py          Route registration, @require_course_access decorator
├── list_page.py         courses_list_page (route: /courses)
├── detail.py            course_detail_page + weeks_list refreshable (route: /courses/{id})
├── create.py            create_course/week/activity pages (3 routes)
├── enrollments.py       manage_enrollments_page (route: /courses/{id}/enrollments)
├── settings.py          open_course_settings, open_activity_settings dialogs
├── activity_row.py      _render_activity_row (extracted widget builder)
└── helpers.py           Pure functions, constants, peer map builder
```

### `@require_course_access` Decorator

Replaces the 15-line auth/DB/user/enrollment boilerplate repeated across 4 page functions. Defined in `__init__.py`.

**Contract:**

```python
def require_course_access(
    fn: Callable | None = None,
    *,
    require_role: frozenset[str] | None = None,
) -> Callable:
    """Decorator for course page functions that need auth + enrollment.

    Handles: auth check, DB init, UUID parsing, course lookup,
    user lookup, enrollment check, optional role check.

    Injects keyword arguments: course, user_id, enrollment.
    Renders appropriate error UI and returns early on failure.

    Args:
        require_role: If set, enrollment.role must be in this set.
    """
```

**Usage patterns:**
- `@require_course_access` — any enrolled user (course detail page)
- `@require_course_access(require_role=_MANAGER_ROLES)` — coordinators/instructors only (create week, create activity, manage enrollments)

`courses_list_page` does not use the decorator — it needs enrollment data across all courses, not access to a specific course. It does its own lighter auth inline.

### State and Communication

- **Module-level global** `_course_clients` dict stays in `detail.py` — it tracks connected clients for broadcast refresh and is only used by the detail page's lifecycle.
- **`_broadcast_weeks_refresh`** moves to `detail.py` alongside the client registry.
- **No shared mutable state between modules** — each page function is independent. Communication is via URL navigation, not shared objects.

### Test Architecture

Three test layers, using the NiceGUI `user` fixture as the new middle layer:

| Layer | Fixture | What it tests | Speed |
|-------|---------|---------------|-------|
| Unit | pytest | Pure functions in `helpers.py` | Fast |
| Integration (NiceGUI) | `user` fixture | Page rendering, decorator, dialogs, form interactions | Fast (no browser) |
| E2E | Playwright | Multi-user workflows, WebSocket broadcast | Slow |

The `user` fixture requires enabling `-p nicegui.testing.user_plugin` in pytest config. Not currently used in the project — this design introduces it.

## Existing Patterns

### Followed

- **`page_layout()` context manager** from `pages/layout.py` — used by annotation, navigator, and roleplay pages. Provides header, nav drawer, optional footer.
- **`@page_route` decorator** from `pages/registry.py` — registers pages in the nav drawer. Currently only `courses_list_page` uses it; the other course pages use bare `@ui.page`.
- **Package decomposition** from `pages/annotation/` — functionally-scoped submodules with a central `__init__.py` that handles route registration and imports.

### Diverged

- **No `PageState` dataclass.** The annotation page uses a central state object passed to all submodules. Course pages are simpler — each page function is self-contained with no cross-module state sharing. A state object would be over-engineering here.
- **Decorator instead of inline boilerplate.** The annotation page does inline auth/access checks. This design extracts the pattern into a reusable decorator since courses has 4 pages with identical boilerplate. The annotation page has only 1 entry point so a decorator wouldn't help there.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Spike the NiceGUI `user` Fixture on Existing Pages

**Goal:** Validate the `user` fixture works in this project before depending on it for courses characterisation tests. Adds lasting test coverage to currently-untested pages.

**Components:**
- `pyproject.toml` — add `-p nicegui.testing.user_plugin` to pytest `addopts`
- `tests/integration/pages/test_dialogs_user.py` — spike test for `pages/dialogs.py` (`show_content_type_dialog`): verify async dialog renders and responds to interaction. Currently has only signature-level unit tests.
- `tests/integration/pages/test_logviewer_user.py` — spike test for `pages/logviewer.py`: verify feature flag gate, "No logs" rendering, and log selection. Currently has zero test coverage.

**Dependencies:** None

**Done when:** Both spike tests pass, existing tests unaffected by plugin addition, `uv run test-all` green. Confirms the `user` fixture handles async pages, auth gates, and UI rendering in this project.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Write Pure Function Tests

**Goal:** Unit tests for extractable pure functions in courses.py.

**Components:**
- `tests/unit/pages/test_courses_helpers.py` — unit tests for `_model_to_ui`, `_ui_to_model`, `_tri_state_options`
- `tests/integration/test_build_peer_map.py` — integration test for `_build_peer_map` (needs DB, tests anonymisation logic)

**Dependencies:** Phase 1 (user fixture validated)

**Done when:** All new tests pass, `uv run test-all` green
- Covers: `courses-refactor-212.AC1.1`, `courses-refactor-212.AC1.2`, `courses-refactor-212.AC1.3`
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Write Characterisation Tests Using `user` Fixture

**Goal:** Lock in existing page behaviour with fast NiceGUI integration tests before any structural changes.

**Components:**
- `tests/integration/pages/test_courses_decorator.py` — tests for `@require_course_access`: unauthenticated redirect, missing DB error, invalid UUID, not-enrolled, wrong-role, happy path
- `tests/integration/pages/test_courses_list.py` — courses list page: renders enrolled courses, hides/shows "New Unit" button by role
- `tests/integration/pages/test_courses_detail.py` — course detail page: renders weeks, activity rows, publish/unpublish buttons for managers, start/resume for students
- `tests/integration/pages/test_courses_dialogs.py` — dialog interactions: `open_course_settings` save/cancel, `open_activity_settings` tri-state persistence
- `tests/integration/pages/test_courses_enrollments.py` — manage enrollments: add enrollment form, remove button

**Dependencies:** Phase 2 (pure function tests in place)

**Done when:** Characterisation tests pass against unmodified `courses.py`, covering all 5 page routes and both dialog functions
- Covers: `courses-refactor-212.AC1.4`, `courses-refactor-212.AC1.5`
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Extract `helpers.py` and `settings.py`

**Goal:** Move pure functions and dialog functions to their own modules without changing behaviour.

**Components:**
- `src/promptgrimoire/pages/courses/helpers.py` — constants (`_MANAGER_ROLES`, field configs, options dicts), pure functions (`_model_to_ui`, `_ui_to_model`, `_tri_state_options`), `_build_peer_map`
- `src/promptgrimoire/pages/courses/settings.py` — `open_course_settings`, `open_activity_settings`
- `src/promptgrimoire/pages/courses/__init__.py` — initial package file with re-exports

**Dependencies:** Phase 3 (characterisation tests as regression gate)

**Done when:** All Phase 2 and Phase 3 tests pass with imports updated to new locations
- Covers: `courses-refactor-212.AC4.1`
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: Create `@require_course_access` Decorator and Adopt `page_layout()`

**Goal:** Eliminate auth boilerplate and add consistent page chrome.

**Components:**
- `@require_course_access` decorator in `src/promptgrimoire/pages/courses/__init__.py`
- All 5 page functions updated to use `page_layout()`
- 4 course-specific pages updated to use the decorator
- `courses_list_page` gets `page_layout()` but keeps inline auth

**Dependencies:** Phase 4 (package structure exists)

**Done when:** All characterisation tests and E2E tests pass, pages render with nav drawer and header
- Covers: `courses-refactor-212.AC2.1`, `courses-refactor-212.AC2.2`, `courses-refactor-212.AC3.1`, `courses-refactor-212.AC3.2`, `courses-refactor-212.AC3.3`
<!-- END_PHASE_5 -->

<!-- START_PHASE_6 -->
### Phase 6: Decompose Page Functions into Package Modules

**Goal:** Extract page functions into separate files, decompose `course_detail_page` until all functions pass complexipy.

**Components:**
- `src/promptgrimoire/pages/courses/list_page.py` — `courses_list_page`
- `src/promptgrimoire/pages/courses/detail.py` — `course_detail_page` orchestrator, `weeks_list` refreshable, `_build_user_workspace_map`, `_broadcast_weeks_refresh`, `_course_clients`
- `src/promptgrimoire/pages/courses/activity_row.py` — `_render_activity_row`
- `src/promptgrimoire/pages/courses/create.py` — `create_course_page`, `create_week_page`, `create_activity_page`
- `src/promptgrimoire/pages/courses/enrollments.py` — `manage_enrollments_page`, `enrollments_list` refreshable
- Route wiring in `__init__.py`

**Dependencies:** Phase 5 (decorator and page_layout in place)

**Done when:** `uv run complexipy src/promptgrimoire/pages/courses/ --max-complexity-allowed 15` reports zero failures, all tests pass
- Covers: `courses-refactor-212.AC4.2`, `courses-refactor-212.AC4.3`
<!-- END_PHASE_6 -->

<!-- START_PHASE_7 -->
### Phase 7: Documentation and Cleanup

**Goal:** Update project documentation to reflect new structure.

**Components:**
- `CLAUDE.md` — update project structure section to show `pages/courses/` package
- `.ed3d/implementation-plan-guidance.md` — update file organisation section
- Run full E2E suite as final regression check

**Dependencies:** Phase 6 (decomposition complete)

**Done when:** Documentation reflects actual structure, `uv run test-e2e` passes, `uv run test-all` passes
- Covers: `courses-refactor-212.AC5.1`
<!-- END_PHASE_7 -->

## Additional Considerations

**NiceGUI route registration:** When extracting page functions to submodules, `@ui.page` decorators must still fire at import time. The `__init__.py` imports all submodules, which triggers registration. This is the same pattern used by `pages/annotation/__init__.py`.

**`@ui.refreshable` across files:** The `weeks_list` and `enrollments_list` refreshable functions stay in the same file as their parent page function. NiceGUI refreshables must be defined in the rendering context — they can't be imported from a different module and used as refreshables. `_render_activity_row` is a regular function (not refreshable) and can be imported freely.

**Broadcast cleanup:** The `_course_clients` dict and `on_disconnect` cleanup stay tightly coupled to `detail.py`. Moving them to a separate module would add indirection without benefit — they're only used by one page.
