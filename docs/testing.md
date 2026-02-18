# Testing Guidelines

*Last updated: 2026-02-18*

## TDD is Mandatory

1. Write failing test first
2. Write minimal code to pass
3. Refactor
4. Repeat

No feature code without corresponding tests. Playwright for E2E, pytest for unit/integration.

## E2E Test Guidelines

### JavaScript in E2E Tests

Use Playwright's native APIs for user interactions (clicks, typing, drag). `page.evaluate()` is acceptable for:

- **Coordinate lookup**: `charOffsetToRect()` via the text walker for precise selection targeting
- **Readiness gates**: `wait_for_text_walker()` checks `window._textNodes` before interactions
- **Clipboard operations**: `navigator.clipboard.write()` for paste simulation

Do not use `page.evaluate()` to assert on internal DOM state or bypass the UI.

### E2E Test Structure

Tests are organised as **persona tests** — narrative user journeys that exercise multiple features in sequence. Each persona file covers one user archetype:

| File | Persona | Coverage |
|------|---------|----------|
| `test_law_student.py` | AustLII annotation workflow | Paste HTML, highlight, comment, organise, respond, export PDF |
| `test_translation_student.py` | CJK/RTL text handling | Mixed scripts, i18n PDF export, Arabic/Hebrew |
| `test_history_tutorial.py` | Bidirectional CRDT sync | Two students, highlight sync, comment sync, organise/respond sync |
| `test_naughty_student.py` | Adversarial security | Dead-end navigation, XSS/BLNS injection, copy protection bypass |
| `test_instructor_workflow.py` | Course setup + student clone | Create course, weeks, activities, template, enrol, student access |

Each method uses **pytest-subtests** for checkpoint assertions within a shared browser context, reducing page loads.

### Helper Modules

| Module | Purpose |
|--------|---------|
| `annotation_helpers.py` | `select_chars()`, `create_highlight()`, `setup_workspace_with_content()`, `wait_for_text_walker()` |
| `course_helpers.py` | `create_course()`, `add_week()`, `add_activity()`, `enrol_student()`, `publish_week()`, `configure_course_copy_protection()` |
| `conftest.py` | `app_server` fixture (NiceGUI server lifecycle), `fresh_page`, `_authenticate_page()`, cleanup endpoint |

### Common E2E Pitfalls

- Elements may be off-screen in headless mode — always scroll into view before assertions
- NiceGUI pages may need time to hydrate — use `expect().to_be_visible()` with appropriate timeouts
- **`wait_for_text_walker()`** is the canonical readiness gate before any char-offset operations
- **Copy protection setup**: create week/activity BEFORE enabling copy protection (dialog→nav race)
- **MockAuthClient `_pending_email` pollution**: use explicit `mock-token-{email}` format tokens instead of `MOCK_VALID_MAGIC_TOKEN` when test ordering matters (pytest-randomly)

See [docs/e2e-debugging.md](e2e-debugging.md) for E2E infrastructure details and debugging patterns.

## Database Test Architecture

### Core Principles

1. **NullPool for xdist safety** - Each test gets a fresh TCP connection, no pooling
2. **UUID-based isolation** - All test data uses unique identifiers to prevent collisions
3. **Canary-based rebuild detection** - A sentinel row detects unexpected database rebuilds
4. **Schema from Alembic only** - Never use `create_all()` in tests

### Key Fixtures

```python
# db_session - Primary fixture for database tests
@pytest.mark.asyncio
async def test_something(db_session: AsyncSession):
    # Fresh connection per test, NullPool ensures no event loop issues
    result = await db_session.execute(select(User))
```

The `db_session` fixture provides:
- Fresh AsyncSession per test (no connection reuse)
- NullPool to avoid event loop binding issues with xdist
- Automatic canary verification (fails fast if DB was rebuilt mid-run)

### pytest_configure Hook

At pytest startup (before xdist workers spawn):
1. Runs Alembic migrations to ensure schema is correct
2. Truncates all tables to remove leftover data from previous runs

This runs ONCE in the main process, eliminating race conditions.

### Canary Mechanism

A `db_canary` fixture inserts a known User row at session start. The `db_session` fixture verifies this row exists before yielding the session. If the canary is missing, the database was rebuilt mid-run and the test fails immediately with a clear error.

## Database Test Rules

1. **Use `db_session` fixture** - Don't create engines manually in tests
2. **NEVER use `drop_all()` or `truncate`** - Let pytest_configure handle cleanup
3. **NEVER use `create_all()` in tests** - Schema comes from Alembic
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

## Integration Test Patterns

### Skip Guard

Integration tests that require a database use a module-level skip guard. Every new integration test file must include this at the top:

```python
import os
import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set - skipping database integration tests",
)
```

This ensures the entire module is skipped when no test database is available, rather than failing with connection errors.

### Class-Based Organisation

Group tests by the function or behaviour they exercise:

```python
class TestCreateWorkspace:
    """Tests for create_workspace."""

    @pytest.mark.asyncio
    async def test_creates_workspace(self) -> None: ...

class TestGetWorkspace:
    """Tests for get_workspace."""

    @pytest.mark.asyncio
    async def test_returns_workspace_by_id(self) -> None: ...
    async def test_returns_none_for_missing(self) -> None: ...
```

Each class maps to one public function or one logical group of related operations. This keeps test files navigable as they grow.

### Reference Files

When writing new CRUD integration tests, use these as templates:

- **`tests/integration/test_workspace_crud.py`** — Workspace and document CRUD. Shows the skip guard, class-based grouping, UUID isolation, and `from __future__ import annotations` import.

## Test Markers

Custom markers are defined in `pyproject.toml` under `[tool.pytest.ini_options]`:

| Marker | Purpose | Default |
|--------|---------|---------|
| `slow` | Long-running tests | Deselected (`-m "not slow"`) |
| `e2e` | Playwright end-to-end tests | Excluded from `test-all` (`-m "not e2e"`) |
| `blns` | Big List of Naughty Strings | Opt-in (`-m blns`) |
| `latex` | Tests requiring TinyTeX/system fonts | Included by default |

Default addopts: `-ra -q -m 'not blns and not slow'`

To run a specific marker: `uv run pytest -m e2e` or `uv run pytest -m latex`.

## Fixture Analysis

`scripts/analyse_fixture.py` -- CLI for inspecting HTML conversation fixtures (plain or gzipped) without shell-level zcat/grep/perl.

```bash
# List all fixtures with sizes
uv run python scripts/analyse_fixture.py list

# Count/show tags matching a pattern
uv run python scripts/analyse_fixture.py tags google_gemini_debug user-query

# Regex search with context
uv run python scripts/analyse_fixture.py search claude_cooking "Thought process"

# Find text with surrounding HTML context (style attrs stripped)
uv run python scripts/analyse_fixture.py context claude_cooking "font-claude" --chars 200

# Tag counts, data-* attributes, class names
uv run python scripts/analyse_fixture.py structure google_aistudio_image
```

Fixture names can be partial (substring match). Supports both `.html` and `.html.gz` transparently.

### E2E Debugging

See [docs/e2e-debugging.md](e2e-debugging.md) for:
- Server lifecycle and cleanup endpoint details
- NiceGUI task leak patterns and fixes
- Watchdog stack dump analysis
- Server log (`test-e2e-server.log`) post-mortem
