# Testing Guidelines

*Last updated: 2026-03-11*

## TDD is Mandatory

1. Write failing test first
2. Write minimal code to pass
3. Refactor
4. Repeat

No feature code without corresponding tests. Playwright for E2E, pytest for unit/integration.

## E2E Test Guidelines

### Lane Command Contract

The E2E surface is split into explicit lanes:

- `uv run grimoire e2e run` runs the **Playwright** lane only (`tests/e2e`).
- `uv run grimoire e2e nicegui` runs the **NiceGUI** lane only (`tests/integration` allowlist).
- `uv run grimoire e2e all` runs Playwright first, then NiceGUI, for a local full-suite umbrella run.

`uv run grimoire test all` excludes both `e2e` and `nicegui_ui` markers so browser and NiceGUI harness tests do not contaminate the regular xdist unit/integration lane.

Artifacts from lane runs are written under:

- Local Playwright lane: `output/test_output/e2e/playwright/...`
- Local NiceGUI lane: `output/test_output/e2e/nicegui/...`
- CI uploads:
  - `e2e-playwright-artifacts`
  - `nicegui-ui-artifacts`

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
| `card_helpers.py` | `expand_card()`, `collapse_card()`, `add_comment_to_highlight()` (with epoch wait), `get_comment_authors()` |
| `highlight_tools.py` | `create_highlight()`, `create_highlight_with_tag()`, `find_text_range()`, `select_text_range()`, `scroll_to_char()` |
| `db_fixtures.py` | `_create_workspace_via_db()`, `_create_workspace_no_tag_permission()`, `_create_workspace_with_word_limits()`, `get_user_id_by_email()` |
| `export_tools.py` | `ExportResult`, `export_pdf_text()`, `export_annotation_tex_text()` |
| `fixture_loaders.py` | `_load_fixture_via_paste()`, `setup_workspace_with_content()` |
| `page_interactions.py` | `navigate_home_via_drawer()`, `drag_sortable_item()`, `toggle_share_with_class()`, `clone_activity_workspace()` |
| `tag_helpers.py` | `seed_tag_id()`, `seed_group_id()`, `_seed_tags_for_workspace()`, `_lock_tag_in_db()` |
| `course_helpers.py` | `create_course()`, `add_week()`, `add_activity()`, `enrol_student()`, `publish_week()`, `configure_course_copy_protection()` |
| `conftest.py` | `app_server` fixture (NiceGUI server lifecycle), `fresh_page`, `_authenticate_page()`, cleanup endpoint |

`annotation_helpers.py` is deprecated — it was decomposed into the modules above. Do not add new helpers there.

### Locator Strategy

All interactable UI elements must have `data-testid` attributes. E2E tests must locate elements via `get_by_test_id()` rather than visible text, placeholders, or Quasar CSS classes.

**NiceGUI-specific behaviour:** `ui.input().props('data-testid="foo"')` places the attribute directly on the native `<input>` element, not on a wrapper `<div>`. This means `get_by_test_id("foo").fill(value)` works directly — do not chain `.locator("input")`.

```python
# Good — data-testid targets the native element
page.get_by_test_id("course-code-input").fill("LAWS1100")
page.get_by_test_id("add-week-btn").click()
page.get_by_test_id("tab-organise").click()

# Bad — fragile, breaks when text/placeholder/class changes
page.get_by_placeholder("e.g., LAWS1100").fill("LAWS1100")
page.get_by_role("button", name="Add Week").click()
page.get_by_text("Organise", exact=True).click()
```

When adding new UI elements, add `data-testid` in the source and use `get_by_test_id` in tests. Convention: kebab-case, descriptive (`course-settings-btn`, `enrollment-email-input`, `tab-respond`).

### Common E2E Pitfalls

- Elements may be off-screen in headless mode — always scroll into view before assertions
- NiceGUI pages may need time to hydrate — use `expect().to_be_visible()` with appropriate timeouts
- **Value-Capture Race**: When Playwright calls `fill()` and then immediately `click()`s a button, the server's `click` task can race the `input` task. To fix this, use the `ui_helpers.py:on_submit_with_value` pattern to extract the exact DOM string on the client during the click.
- **Rebuild Epoch Race**: When the server calls `container.clear()` and rebuilds a UI, the DOM is destroyed and recreated. Playwright `expect` assertions might pass against a dying DOM node. To fix this, use the **Epoch Pattern**:
  1.  Server: `state.cards_epoch += 1` and `ui.run_javascript(f"window.__annotationCardsEpoch = {state.cards_epoch}")` unconditionally at the end of the rebuild.
  2.  Test: Capture `old_epoch = page.evaluate("() => window.__annotationCardsEpoch || 0")`.
  3.  Test: Click button.
  4.  Test: `page.wait_for_function("(old) => (window.__annotationCardsEpoch || 0) > old", arg=old_epoch)`.
  5.  Test: Reacquire locators from the strictly new DOM.
- **Slot Context After `container.clear()`**: `ui.run_javascript()` resolves the NiceGUI client via the current slot stack. When an event handler (e.g. post-comment click) triggers `container.clear()`, the handler's slot — bound to a child element inside that container — is destroyed. Any `ui.run_javascript()` call after `clear()` but outside a `with container:` block will raise `RuntimeError: The parent element this slot belongs to has been deleted.` **Rule:** Any function that calls `container.clear()` must wrap its entire body in `with container:` so that all subsequent `ui.run_javascript()` calls (including epoch broadcasts) resolve through the container's slot, not the caller's dead slot. See `_refresh_annotation_cards` in `cards.py` for the canonical pattern.
- **`wait_for_text_walker()`** is the canonical readiness gate before any char-offset operations
- **`find_text_range(needle)`** searches document text via the browser's text walker and returns `(start_char, end_char)` — use this instead of hardcoded numeric offsets, which break when fixture HTML changes
- **Copy protection setup**: create week/activity BEFORE enabling copy protection (dialog→nav race)
- **MockAuthClient `_pending_email` pollution**: use explicit `mock-token-{email}` format tokens instead of `MOCK_VALID_MAGIC_TOKEN` when test ordering matters (pytest-randomly)

- **Fixture colour name mismatch (display names vs UUIDs)**: HTML fixtures with pre-baked `data-annots` attributes hardcode colour names like `tag-Jurisdiction-dark`. The live app export path uses UUID-keyed colours from `state.tag_colours()` (which maps `ti.raw_key` → colour). The preamble generates `tag-{uuid}-dark`, not `tag-Jurisdiction-dark`. In fast mode (`.tex` only) this doesn't matter — undefined colours aren't exercised. In slow mode (full compilation) LaTeX fails on "Undefined color", the export handler catches the exception and never triggers a download, and Playwright burns 120s waiting. **Rule:** E2E tests that compile PDFs must either (a) use inline HTML without pre-baked `data-annots`, or (b) create real CRDT highlights so colour refs use UUID keys end-to-end. A guard test (`test_fixture_colour_guard.py`) catches mismatches at the unit level.

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
| `slow` | Long-running tests | Deselected |
| `e2e` | Playwright end-to-end tests | Own lane |
| `nicegui_ui` | NiceGUI user-simulation tests | Own lane |
| `blns` | Big List of Naughty Strings | Deselected |
| `smoke` | External toolchains (pandoc, lualatex, tlmgr) | Own lane |
| `latex` | Tests requiring TinyTeX/system fonts | Included in unit lane |
| `latexmk_full` | Full compiled-PDF suites | Deselected from unit lane |

Default addopts: `-ra -q -m 'not blns and not slow and not perf and not smoke'`

## Test Lanes

The test suite is organised into 6 lanes. Each lane is a separate `_run_pytest()` invocation producing a `LaneResult`.

### Lane Definitions

| Lane | Path Filter | Marker Filter | Workers | Purpose |
|------|-------------|---------------|---------|---------|
| unit | `tests/unit/` | `not e2e and not nicegui_ui and not latexmk_full and not smoke` | xdist auto | Fast unit tests |
| integration | `tests/integration/` | `not e2e and not nicegui_ui and not smoke` | xdist auto | DB integration tests |
| playwright | `tests/e2e/` | `e2e` | parallel (per-file) | Browser E2E tests |
| nicegui | NiceGUI UI files | `nicegui_ui` | serial | In-process NiceGUI tests |
| smoke | all paths | `smoke` | serial | External toolchain tests |
| blns+slow | all paths | `(blns or slow) and not smoke` | serial | Naughty strings and slow tests |

### Command-to-Lane Matrix

| Command | unit | integration | playwright | nicegui | smoke | blns+slow |
|---------|:----:|:-----------:|:----------:|:-------:|:-----:|:---------:|
| `test all` | X | | | | | |
| `test smoke` | | | | | X | |
| `test run <path>` | auto-detected | auto-detected | auto-detected | auto-detected | | |
| `test changed` | X | X | | | | |
| `e2e run` | | | X | | | |
| `e2e slow` | | | X (slow) | | | |
| `e2e all` | X | X | X | X | X | X |

### Smoke Marker Propagation

The `smoke` marker is applied automatically by the `requires_pandoc`, `requires_latexmk`, and `requires_full_latexmk` decorator factories in `tests/conftest.py`. Tests with custom toolchain checks (e.g. `requires_tinytex`) carry `@pytest.mark.smoke` directly at the class level.

To run E2E tests: `uv run grimoire e2e run`.

### Debug Log File

`test-debug.log` is configured as pytest's `log_file` at WARNING level. It captures warnings and errors from all test runs. The file is gitignored. To get verbose output for debugging, temporarily change `log_file_level` to `DEBUG` in `pyproject.toml`.

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

### NiceGUI Integration Test Pitfalls (PG005)

**Sync element access must be gated by `_should_see_testid`.** The helpers `_set_input_value` and `_click_testid` are synchronous — they do not yield to the event loop. If the page handler is an async function with mid-render `await` calls (e.g. `await get_all_roles()`), elements created after the await may not exist yet.

```python
# BAD — races if page handler has an await before rendering the input:
await nicegui_user.should_see(content="Add Enrollment")
_set_input_value(nicegui_user, "enrollment-email-input", student_email)

# GOOD — _should_see_testid yields to the event loop via asyncio.sleep:
await _should_see_testid(nicegui_user, "enrollment-email-input")
_set_input_value(nicegui_user, "enrollment-email-input", student_email)
```

**Why `should_see(content=...)` is not enough:** It matches text content, not element identity. A label rendered synchronously before an `await` can satisfy `should_see`, but the input rendered after the `await` doesn't exist yet. `_should_see_testid` polls for the specific `data-testid`, yielding to the event loop on each retry.

**Guard test:** `test_e2e_anti_patterns.py::test_nicegui_sync_access_has_testid_gate` (PG005) scans all `tests/integration/` async test functions and flags any `_set_input_value` or `_click_testid` call without a preceding `await _should_see_testid` for the same testid. Suppress with `# noqa: PG005`.

**Root cause reference:** 2026-03-17 CI failure in `TestEnrollStudent.test_enroll_student` — `courses.py:_render_add_enrollment_form` renders a label synchronously then awaits `get_all_roles()` before creating the input. On CI (cold DB), the await didn't complete within the same event loop tick.

See [docs/e2e-debugging.md](e2e-debugging.md) for:
- Server lifecycle and cleanup endpoint details
- NiceGUI task leak patterns and fixes
- Watchdog stack dump analysis
- Server log (`test-e2e-server.log`) post-mortem

## Debugging Production Issues

### Incident Telemetry Pipeline

For structured post-incident analysis, use the automated telemetry pipeline. Full procedure in [docs/postmortems/2026-03-16-incident-response.md](postmortems/2026-03-16-incident-response.md) § "Automated telemetry pipeline".

| Tool | Purpose |
|------|---------|
| `deploy/collect-telemetry.sh` | Collects journal, structlog JSONL, HAProxy, PG logs from prod (handles rotated files) |
| `scripts/incident_db.py ingest` | Parses tarball into normalised SQLite database |
| `scripts/incident_db.py beszel` | Adds Beszel system metrics (CPU, memory, load) via PocketBase API |
| `scripts/incident_db.py sources` | Source inventory with timestamps and provenance |
| `scripts/incident_db.py timeline` | Cross-source timeline view |
| `scripts/incident_db.py breakdown` | Error breakdown by event type |
| `.claude/skills/incident-analysis/` | Structured analysis methodology (provenance, falsification, self-challenge) |

### Extract/Rehydrate Workspace

Two scripts support pulling production workspace state into a local dev database for debugging:

```bash
# On prod (peer auth via Unix socket):
sudo -u promptgrimoire uv run scripts/extract_workspace.py <workspace-uuid>
# Output: /tmp/workspace_<uuid>.json

# Copy to local:
scp grimoire.drbbs.org:/tmp/workspace_<uuid>.json /tmp/

# Load into local dev database:
uv run scripts/rehydrate_workspace.py /tmp/workspace_<uuid>.json
# Then open: http://localhost:8080/annotation?workspace_id=<uuid>
```

The JSON contains workspace, documents, tag groups, and tags. Binary fields (CRDT state) are base64-encoded. The workspace is inserted standalone (`activity_id` and `course_id` set to NULL) so no parent records are needed.

### Retrieving LaTeX Export Logs from Production

The systemd service runs with `PrivateTmp=true`, so `/tmp` inside the service is isolated. Export logs are not visible from a normal shell.

**Find the private tmp path:**

```bash
sudo bash -c 'ls /tmp/systemd-private-*-promptgrimoire.service-*/tmp/'
```

**Copy a specific log out:**

```bash
sudo bash -c 'cp /tmp/systemd-private-*-promptgrimoire.service-*/tmp/promptgrimoire_export_<hash>/<filename>.log /tmp/export_debug.log'
```

**Note:** `nsenter` also works but writes into the private namespace — use real paths (e.g. `/tmp/systemd-private-*/...`) from outside the namespace, not `nsenter` + `cp`.
