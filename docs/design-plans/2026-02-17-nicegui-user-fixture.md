# NiceGUI User Fixture Tests Design

**Status:** WIP — spike needed before implementation planning
**GitHub Issue:** None

## Summary

Add a new test tier using NiceGUI's built-in `User` fixture for fast, headless, in-process testing of server-side page behaviours. Fills a coverage gap between pure-function unit tests and full-browser Playwright E2E tests. Targets three specific areas: dialog interaction logic, render function component wiring, and empty/error state rendering. Complements (does not replace) the #156 persona-based E2E test migration.

## Definition of Done

1. **User fixture infrastructure** — A conftest setup that loads PromptGrimoire pages in-process via NiceGUI's `User` fixture with mocked auth, no real database required
2. **Dialog interaction tests** — Replace signature-only checks in `test_dialogs.py` with tests that render the dialog, click buttons, and verify callbacks return correct values
3. **Render function tests** — Call `render_organise_tab()`, `render_respond_tab()` and verify the NiceGUI component tree (correct containers, labels, empty states)
4. **Updated docs** — Brief section in `docs/testing.md` on when to use User fixture vs unit vs E2E

Out of scope: migrating existing E2E tests, fixing flaky E2E tests, changes to #156 persona-based test migration.

## Spike Required

**The dialog testing pattern has no upstream precedent.** NiceGUI's own test suite tests dialogs only via the Screen (Selenium) fixture, not the User fixture. The proposed `await asyncio.sleep(0)` pattern for async dialog interaction is derived from source code inspection, not from documented or tested examples.

Before implementation planning, a spike must confirm:
1. `show_content_type_dialog()` can be rendered and interacted with via the User fixture
2. The `asyncio.sleep(0)` yield pattern correctly allows `await dialog` to resolve
3. `user.find().click()` on dialog buttons triggers `dialog.submit()` as expected
4. This works on pinned NiceGUI 3.6.1

If the spike fails, the dialog testing approach needs rethinking (possibly testing dialog logic extraction instead of rendered interaction).

## Architecture

### Test Tier Positioning

```
Unit tests (tests/unit/)
  └─ Pure functions, no NiceGUI — group_highlights_by_tag(), _parse_sort_end_args()

User fixture tests (tests/nicegui-user/)    ← NEW
  └─ Server-side page rendering, no browser — dialogs, render functions, empty states

E2E tests (tests/e2e/)
  └─ Full browser via Playwright — JS execution, CSS Highlight API, mouse interaction
```

User fixture tests run as part of `test-all` (no Playwright, no subprocess server).

### Infrastructure Approach: Direct Render Calls (Approach C)

Use `user_simulation(root=...)` with a trivial root function per test. Each test creates its own NiceGUI context — no shared app state, no routes, no DB. Render functions are called directly within `with user:` blocks, passing mock state objects.

**Why not a thin main file (Approach B):** Importing `promptgrimoire.pages` triggers transitive imports (CRDT, export, auth, DB) that may fail without configuration. Direct render calls avoid this entirely. Approach B can be added later if route-level tests prove valuable.

**Fixture location:** `tests/nicegui-user/conftest.py` wrapping `user_simulation` with cleanup.

### Dependency Classification

Analysis of target functions by what they need to run:

| Function | Classification | Mocking needed |
|----------|---------------|----------------|
| `show_content_type_dialog()` | **Pure NiceGUI** | Nothing. `CONTENT_TYPES` is a static constant. |
| `render_organise_tab()` | **Needs state** | Mock `AnnotationDocument` with `.get_all_highlights()` and `.get_tag_order()`. Real `ui.element` panel. |
| `render_respond_tab()` | **Needs external** | Mock `AnnotationDocument`. Milkdown JS init will degrade gracefully (no browser). `get_persistence_manager()` only called on Yjs update events, not at render time. |

### Test Targets

#### 1. Dialog Interaction Tests

**Replaces:** `tests/unit/pages/test_dialogs.py` (currently signature-only)
**New file:** `tests/nicegui-user/test_dialogs.py`

Tests:
- Confirm returns selected content type
- Cancel returns None
- Changing the select widget changes the returned type
- Preview expansion renders when preview content provided

**Async pattern** (needs spike validation):
```python
user.find('Open').click()       # schedules async dialog handler
await asyncio.sleep(0)          # yield so handler reaches await dialog
user.find('Confirm').click()    # fires dialog.submit()
await user.should_see('Result') # retries give coroutine time to propagate
```

#### 2. Render Function Tests

**New file:** `tests/nicegui-user/test_organise_render.py`

`render_organise_tab(panel, tags, crdt_doc, ...)`:
- Empty document shows no highlight cards
- Document with highlights shows cards in correct tag columns
- Untagged highlights appear in "Untagged" column
- Locate button present when `on_locate` callback provided

**New file:** `tests/nicegui-user/test_respond_render.py`

`render_respond_tab(panel, tags, crdt_doc, ...)`:
- Empty document shows "No highlights yet" in reference panel
- Document with highlights shows reference cards grouped by tag
- Filter input filters displayed cards
- Editor container renders (Milkdown JS init fails gracefully)

#### 3. Signature Tests Disposition

`tests/unit/pages/test_dialogs.py` — replaced by `tests/nicegui-user/test_dialogs.py`, delete original.

`tests/unit/pages/test_annotation_warp.py` — signature checks for `_warp_to_highlight`, `render_organise_tab`, `render_respond_tab`. Once render function tests exist in `tests/nicegui-user/`, the signature-only checks in this file become redundant. Evaluate for deletion or reduction.

## Investigation Findings

### Flaky E2E Tests (40 skipped, #120)

39 of 40 flaky E2E tests genuinely require a real browser (mouse coordinates, `page.evaluate()`, CSS Highlight API, drag-and-drop, Milkdown JS, multi-context CRDT sync). The User fixture cannot replace them. Only `test_auth_pages.py::TestLoginPage::test_login_page_elements_and_magic_link` is a plausible User fixture candidate.

### NiceGUI User Fixture in 3.6.1

Confirmed available. API surface: `User.open()`, `User.find()`, `User.should_see()`, `User.should_not_see()`, `UserInteraction.click()`, `.type()`, `.clear()`, `.trigger()`. JavaScript simulation via regex rules (no real JS execution).

### App Loading

`main()` does DB bootstrap + Alembic + `ui.run()` — too heavy for User fixture. Direct render calls with `user_simulation(root=...)` bypass this entirely.

## Existing Patterns

- Unit tests extract pure functions from page modules and test them directly — this design follows the same philosophy but at the component rendering level
- E2E tests use `setup_workspace_with_content()` helpers — User fixture tests will use mock state objects instead
- `tests/unit/pages/` already exists for page-adjacent unit tests — `tests/nicegui-user/` adds a parallel tier

## Implementation Phases

### Phase 1: Spike — Validate Dialog Testing Pattern

Confirm the `asyncio.sleep(0)` dialog interaction pattern works on NiceGUI 3.6.1 with `show_content_type_dialog()`. This is a go/no-go gate for the rest.

### Phase 2: Infrastructure

`tests/nicegui-user/conftest.py` with User fixture setup. Verify tests run in `test-all`.

### Phase 3: Dialog Tests

Replace `test_dialogs.py` signature checks with rendered interaction tests.

### Phase 4: Render Function Tests

`test_organise_render.py` and `test_respond_render.py` with mock state objects.

### Phase 5: Documentation

Update `docs/testing.md` with User fixture tier guidelines.

## Glossary

- **User fixture**: NiceGUI's `nicegui.testing.User` class — simulates a browser user in-process via HTTPX ASGI transport, no real browser
- **user_simulation**: Context manager from `nicegui.testing` that creates an isolated NiceGUI app context with global state reset
- **Direct render calls (Approach C)**: Testing strategy where render functions are called directly in a bare NiceGUI context, bypassing route registration and page-level dependencies
- **Thin main file (Approach B)**: Alternative strategy (deferred) where a shared test entry point imports all page routes — enables route-level testing but requires managing transitive import side effects
- **Signature-only tests**: Existing unit tests that verify function existence and parameter signatures via `inspect` without calling the functions
