# Testing Guidelines

## TDD is Mandatory

1. Write failing test first
2. Write minimal code to pass
3. Refactor
4. Repeat

No feature code without corresponding tests. Playwright for E2E, pytest for unit/integration.

## E2E Test Guidelines

**NEVER inject JavaScript in E2E tests.** Use Playwright's native APIs exclusively:

- **Text selection**: Use `page.mouse` to drag-select (move, down, move, up)
- **Keyboard input**: Use `page.keyboard.press()` or `locator.press()`
- **Clicks**: Use `locator.click()` with modifiers if needed
- **Assertions**: Use `expect()` from `playwright.sync_api`
- **Scroll into view**: Use `locator.scroll_into_view_if_needed()` before interacting with elements that may be off-screen

Tests must simulate real user behavior through Playwright events, not bypass the UI with JavaScript injection like `page.evaluate()` or `ui.run_javascript()`.

### Common E2E Pitfalls

- Elements may be off-screen in headless mode - always scroll into view before assertions
- NiceGUI pages may need time to hydrate - use `expect().to_be_visible()` with appropriate timeouts
- Floating menus/popups often require scroll context to position correctly
- **Annotation cards are scroll-sensitive** - they won't display if their anchor element is not visible; always `scroll_into_view_if_needed()` before selecting text for annotation
- **Sticky selections on highlighted text (NiceGUI 3.6+)** - selections made on already-highlighted text become "sticky" and won't clear with clicks outside the document container. Workaround: before each drag selection, click on a non-highlighted word *inside* the document (e.g., `[data-w="0"]` header word) to reliably clear existing selection

## Database Test Isolation

1. **UUID-based isolation is MANDATORY** - All test data must use unique identifiers (uuid4) to prevent collisions
2. **NEVER use `drop_all()` or `truncate`** - These break parallel test execution (pytest-xdist)
3. **NEVER use `create_all()` in tests** - Schema comes from Alembic migrations run once at session start
4. **Tests must be parallel-safe** - Assume pytest-xdist; tests may run concurrently

## Test Database Configuration

1. **Use `TEST_DATABASE_URL`** - Tests set `DATABASE_URL` from `TEST_DATABASE_URL` for isolation
2. **Schema is set up ONCE per test session** - `db_schema_guard` runs migrations before any tests
3. **Each test owns its data** - Create with UUIDs, don't rely on cleanup between tests

## Workspace Test Pattern

Workspaces require only UUID isolation, not user creation:

```python
# Good - workspace tests don't need users
workspace = await create_workspace()
doc = await add_document(workspace.id, type="source", content="...", raw_content="...")

# Bad - don't create users just for workspace ownership
user = await create_user(...)  # Not needed for workspace tests
```

This simplifies tests and reflects the design: workspaces are silos, access control comes later via ACL.
