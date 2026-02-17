# Test Architecture: External Service Isolation

## Summary

Refactor test architecture so external services (PostgreSQL, app server, LibreOffice, latexmk) run independently from tests. Tests connect to services and queue work rather than managing service lifecycles or sharing event loops. This eliminates event loop conflicts with pytest-xdist and establishes a clean separation between test code and infrastructure.

## Definition of Done

**Primary Deliverables:**
1. Single database connection manager - tests connect to PostgreSQL, don't manage async engines
2. Work queue pattern - tests queue work to services as different users would
3. External programs (LibreOffice, latexmk) called by services, not directly by tests
4. Event loop conflicts with xdist eliminated

**Success Criteria:**
- `uv run test-debug` passes with `-n auto` (xdist parallelism)
- No "Runner.run() cannot be called from a running event loop" errors
- Tests don't manage SQLAlchemy async engine lifecycle
- Database connection pooling is an implementation detail hidden from tests

**Key Exclusions:**
- E2E tests may still require browser automation (Playwright)
- RTF parser unit tests remain skipped (Issue #108)

## Glossary

- **xdist**: pytest plugin for parallel test execution; each worker is a separate Python process
- **Event loop**: asyncio construct; each xdist worker has its own, they don't share
- **Connection manager**: Centralised component that owns database connections
- **Work queue**: Pattern where tests submit work requests rather than executing directly

## Research Findings

### pytest-xdist Architecture

Each xdist worker (`-n auto` creates ~24 on modern machines) is a **separate Python process** with:
- Its own Python interpreter
- Its own asyncio event loop
- Its own copy of session-scoped fixtures (they're created per-worker, not shared)

**Key insight:** Session-scoped fixtures don't share state across workers. Each worker creates its own instance.

### pytest-asyncio Event Loops

With `asyncio_mode = "strict"` (current setting):
- Event loops are only created for tests explicitly marked with `@pytest.mark.asyncio`
- Sync tests don't get an event loop at all
- The `@pytest_asyncio.fixture` decorator is required for async fixtures

**The problem we hit:** SQLAlchemy's async engine binds to the event loop that created it. When a different worker (different loop) tries to use that engine, it fails with "Runner.run() cannot be called from a running event loop".

### asyncpg Connection Binding

asyncpg connections are bound to specific event loops at creation time. Attempting to use a connection from a different event loop causes errors. This is fundamental to how asyncpg works, not a bug.

## Architecture

### Current State (Problematic)

```
┌─────────────────────────────────────────────────────────────┐
│  Test Process (xdist worker)                                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Test Code                                            │   │
│  │  - Creates async engine (bound to this loop)         │   │
│  │  - Calls parse_rtf() → spawns LibreOffice            │   │
│  │  - Calls export_annotation_pdf() → spawns latexmk    │   │
│  │  - Manages connection lifecycle                       │   │
│  └─────────────────────────────────────────────────────┘   │
│                         ↓                                   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ External Services (managed by test)                  │   │
│  │  PostgreSQL  |  LibreOffice  |  latexmk              │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

Problems:
- Async engine bound to one worker's loop, unusable by others
- Tests spawn subprocesses within async context
- Connection pooling leaks into test code

### Target State

```
┌─────────────────────────────────────────────────────────────┐
│  External Services (running independently)                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │ PostgreSQL  │  │ App Server  │  │ Export Service      │ │
│  │ (always on) │  │ (optional)  │  │ (LibreOffice,       │ │
│  │             │  │             │  │  latexmk)           │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
         ▲                  ▲                  ▲
         │ sync connect     │ HTTP             │ queue work
         │                  │                  │
┌─────────────────────────────────────────────────────────────┐
│  Tests (isolated, just queue work)                          │
│  - Connect to database (sync or simple async)               │
│  - Make HTTP requests to app server                         │
│  - Queue export jobs, poll for results                      │
│  - No event loop management                                 │
└─────────────────────────────────────────────────────────────┘
```

Key changes:
1. **Database**: Tests get connections from a manager, don't create engines
2. **App server**: Already runs as subprocess for E2E; integration tests can use same pattern
3. **Export**: Queue-based interface; tests submit work, service calls external tools

## Existing Patterns to Follow

### Conversation fixtures
Already pre-computed: `tests/fixtures/conversations/*.html.gz`
Tests load these directly, don't call the original conversion.

### E2E app server
`app_server` fixture starts NiceGUI subprocess, E2E tests make HTTP requests.
This is the right pattern - service runs independently.

### UUID-based test isolation
Database tests use unique UUIDs for workspaces/users.
No cleanup needed between tests - isolation by data, not by connection.

## Implementation Phases

### Phase 1: Database Connection Manager

**Goal:** Tests get database sessions without managing async engine lifecycle.

**Files to modify:**
- `src/promptgrimoire/db/engine.py` - Add sync connection option or connection manager
- `tests/conftest.py` - Database fixtures use manager
- `tests/integration/conftest.py` - Remove engine reset logic

**Key changes:**
- Connection manager owns the engine, tests request sessions
- Manager handles loop binding internally
- Tests can use sync interface if they don't need async

### Phase 2: Export Service Interface

**Goal:** PDF export becomes a service tests queue to, not async code tests run.

**Files to modify:**
- `src/promptgrimoire/export/pdf_export.py` - Add sync interface or queue-based API
- `tests/conftest.py` - `pdf_exporter` fixture uses sync subprocess calls
- All tests using `pdf_exporter`

**Key changes:**
- `export_annotation_pdf()` can have a sync wrapper using `subprocess.run()`
- Tests don't share event loop with export process
- External tools (pandoc, latexmk) called by service, not test

### Phase 3: RTF Parsing Isolation

**Goal:** RTF→HTML conversion is pre-computed or service-based.

**Files to modify:**
- `tests/integration/test_cross_env_highlights.py` - Use pre-computed fixture
- Any other tests calling `parse_rtf()` directly

**Key changes:**
- `183-libreoffice.html` already exists as pre-computed fixture
- Tests load HTML directly, don't spawn LibreOffice
- Production code still uses LibreOffice; tests use fixtures

### Phase 4: Audit All Test Files

**Goal:** No test directly manages service lifecycles or spawns external processes.

**Files to audit:**
- All files in `tests/integration/`
- All files in `tests/unit/` that touch database or export
- `tests/conftest.py` fixtures

**Checklist per file:**
- [ ] No direct async engine creation
- [ ] No `parse_rtf()` calls (use fixtures)
- [ ] No direct subprocess calls to external tools
- [ ] Uses `@requires_latexmk` if PDF export needed
- [ ] Async tests properly marked

## Files Likely Affected

Based on grep for `parse_rtf`, `export_annotation_pdf`, `get_session`, `AsyncEngine`:

**Database access:**
- `src/promptgrimoire/db/engine.py`
- `tests/conftest.py`
- `tests/integration/conftest.py`
- `tests/integration/test_db_async.py`
- `tests/integration/test_workspace_*.py`
- `tests/integration/test_course_service.py`

**PDF export:**
- `tests/conftest.py` (`pdf_exporter` fixture)
- `tests/integration/test_pdf_export.py`
- `tests/integration/test_pdf_pipeline.py`
- `tests/integration/test_chatbot_fixtures.py`
- `tests/integration/test_cross_env_highlights.py`
- `tests/unit/test_overlapping_highlights.py`
- `tests/unit/export/test_latex_string_functions.py`

**RTF parsing:**
- `tests/integration/test_cross_env_highlights.py`
- `tests/unit/test_rtf_parser.py` (already skipped)
- `tests/unit/test_html_normaliser.py`
- `tests/unit/export/test_css_fidelity.py`

## Additional Considerations

### Sync vs Async Database Access

Two options for database tests:
1. **Sync interface**: Use `psycopg` directly for tests (no async, no event loop issues)
2. **Managed async**: Connection manager handles loop binding, tests just get sessions

Option 1 is simpler but diverges from production code path.
Option 2 is more realistic but needs careful implementation.

### CI Configuration

CI environments will:
- Have PostgreSQL running (required)
- May not have LibreOffice (tests use pre-computed fixtures)
- May not have TinyTeX/latexmk (skip with `@requires_latexmk`)

### Migration Path

This is a significant refactoring. Consider:
1. Feature branch for the work
2. Incremental commits per phase
3. Run full test suite after each phase
