# Dependency Rationale

Last reviewed: 2026-02-07

Each dependency lists: what it does, why it's here (not a stdlib/transitive alternative), and where the evidence is.

## Production Dependencies

### nicegui >= 2.0

**Claim:** Web UI framework. The entire frontend is built on NiceGUI's component model, server-sent events, and WebSocket integration.

**Evidence:** 14 files in `src/promptgrimoire/pages/` import from nicegui. Every page route, dialog, and UI component depends on it. Also provides the app server (`ui.run`), static file serving, and client-side JS execution (`ui.run_javascript`).

**Why not alternatives:** NiceGUI was chosen for Python-native UI without a JS frontend build step. The project is deeply coupled to NiceGUI's component API, page routing, and storage system.

**Classification:** Hard core. Replacing NiceGUI means rewriting the entire frontend.

### sqlmodel >= 0.0.22

**Claim:** ORM combining Pydantic validation with SQLAlchemy query building. All database models are SQLModel classes.

**Evidence:** 11 files in `src/promptgrimoire/db/` and `src/promptgrimoire/models/scenario.py`. All 6 database tables (User, Course, CourseEnrollment, Week, Workspace, WorkspaceDocument) are SQLModel classes. Alembic migrations use SQLModel.metadata.

**Why not alternatives:** SQLModel unifies the Pydantic validation layer with SQLAlchemy persistence. Using SQLAlchemy alone would require separate Pydantic models and manual mapping.

**Classification:** Hard core. All database models, queries, and migrations depend on it.

### pycrdt >= 0.10

**Claim:** CRDT library for real-time collaborative editing. Powers the annotation document sync between multiple users.

**Evidence:** `src/promptgrimoire/crdt/annotation_doc.py`, `src/promptgrimoire/crdt/sync.py`, `src/promptgrimoire/pages/milkdown_spike.py`, `tests/integration/test_crdt_sync.py`.

**Why not alternatives:** pycrdt implements Yjs-compatible CRDTs in Python, enabling interop with the Yjs JavaScript ecosystem (used by Milkdown editor). No other Python CRDT library provides Yjs wire-format compatibility.

**Classification:** Hard core. The collaboration architecture is built around CRDT documents.

### stytch >= 11.0

**Claim:** Authentication provider. Handles magic link login, passkey authentication, SSO, and RBAC.

**Evidence:** `src/promptgrimoire/auth/client.py`, `tests/unit/test_auth_client.py`.

**Why not alternatives:** Stytch provides passwordless auth (magic links, passkeys) as a managed service. Building equivalent auth from scratch would be significant effort and a security liability.

**Classification:** Hard core for auth. Replacing it means reimplementing the entire auth flow.

### pydantic >= 2.10

**Claim:** Data validation. Used directly in database models (via SQLModel) and for structured data throughout.

**Evidence:** `src/promptgrimoire/db/models.py` (direct import of `Field`). Also a transitive dependency of SQLModel and NiceGUI.

**Why not alternatives:** Pydantic is the standard Python validation library. SQLModel requires it. Even without SQLModel, Pydantic would be needed for request/response validation.

**Classification:** Hard core (via SQLModel coupling).

### python-dotenv >= 1.0

**Claim:** Loads `.env` files into `os.environ` for local development configuration.

**Evidence:** 14 files reference `os.environ.get()` for config. `alembic/env.py` directly calls `load_dotenv()`. `src/promptgrimoire/__init__.py` loads dotenv at startup.

**Why not alternatives:** Standard, minimal library for env file loading. No meaningful alternative exists in the stdlib.

**Classification:** Protective belt. Could be replaced by any env-loading mechanism or removed in production (where env vars are set by the deployment platform).

### asyncpg >= 0.30

**Claim:** Async PostgreSQL driver used by SQLAlchemy's async engine.

**Evidence:** `src/promptgrimoire/db/engine.py` uses `create_async_engine` with `postgresql+asyncpg://` connection strings. All `.env.example` DATABASE_URL examples use the asyncpg driver. `alembic/env.py` uses `async_engine_from_config` with the same driver.

**Why not alternatives:** asyncpg is the fastest async PostgreSQL driver for Python. Required for SQLAlchemy's async session support.

**Classification:** Protective belt. The hard core commitment is to async PostgreSQL; asyncpg is the driver choice. Could theoretically be swapped for psycopg async, but asyncpg is faster.

### anthropic >= 0.76.0

**Claim:** Claude API client for the legal roleplay chat simulation.

**Evidence:** `src/promptgrimoire/llm/client.py` (imports `anthropic`), `src/promptgrimoire/llm/prompt.py` (imports `anthropic.types.MessageParam`).

**Why not alternatives:** Official SDK for the Claude API. The roleplay feature is specifically designed around Claude's capabilities.

**Classification:** Hard core for the roleplay feature. Not used by annotation or export.

### alembic >= 1.18.0

**Claim:** Database schema migration tool. All schema changes go through Alembic migrations.

**Evidence:** 15 migration files in `alembic/versions/`, `alembic/env.py`. CLAUDE.md documents "Alembic is the ONLY way to create/modify schema" as a project rule.

**Why not alternatives:** Alembic is the standard migration tool for SQLAlchemy. No viable alternative for SQLModel projects.

**Classification:** Hard core. All schema evolution depends on it.

### rich >= 14.3.1

**Claim:** Terminal formatting for CLI output.

**Evidence:** `src/promptgrimoire/cli.py` uses Rich for test runner output formatting (panels, status displays).

**Why not alternatives:** Rich provides formatted terminal output. The alternative is plain print statements, which would degrade the developer experience for `test-debug` and `test-all`.

**Classification:** Protective belt. Only used in CLI tooling, not in the web application.

### bs4 >= 0.0.2

**Claim:** HTML parsing and tree manipulation for list normalisation in the export pipeline.

**Evidence:** `src/promptgrimoire/export/list_normalizer.py` (production), `scripts/anonymise_chats.py` (utility), `tests/benchmark/test_dom_performance.py` (benchmark comparison).

**Why not alternatives:** The project is migrating to selectolax. bs4 remains only where tree manipulation (insert, wrap, decompose) is needed — selectolax handles these differently. See #122.

**Status:** DEPRECATED. Migration to selectolax tracked in #122.

### selectolax >= 0.4.6

**Claim:** Fast HTML parser (lexbor backend) for the input pipeline and export platform preprocessing.

**Evidence:** 13 files across `src/promptgrimoire/input_pipeline/` and `src/promptgrimoire/export/platforms/`. Used for HTML parsing, attribute stripping, element traversal, and content extraction.

**Why not alternatives:** selectolax with lexbor is significantly faster than BeautifulSoup (see `tests/benchmark/test_dom_performance.py`). Chosen for performance in the HTML processing pipeline.

**Classification:** Hard core for the input/export pipeline. Replacing it means rewriting all HTML processing.

### pylatexenc >= 2.10

**Claim:** Unicode-to-LaTeX character mapping for the PDF export pipeline.

**Evidence:** `src/promptgrimoire/export/latex.py` (imports `pylatexenc` for LaTeX tokenization).

**Why not alternatives:** pylatexenc provides comprehensive Unicode-to-LaTeX mapping. Building this mapping by hand would be error-prone and incomplete.

**Classification:** Protective belt. Used in one module for character mapping.

### lark >= 1.1.0

**Claim:** Parser generator for the LaTeX marker tokenization pipeline.

**Evidence:** `src/promptgrimoire/export/latex.py` — Lark grammar defines the marker token language (HLSTART, HLEND, ANNMARKER, TEXT). `tokenize_markers()` uses the Lark parser.

**Why not alternatives:** Lark provides EBNF grammar support with multiple parsing algorithms. The marker language has nested, overlapping structures that benefit from a proper parser rather than regex.

**Classification:** Hard core for the export pipeline. The marker grammar is defined in Lark syntax.

### emoji >= 2.0.0

**Claim:** Emoji detection and handling for Unicode processing in the export pipeline.

**Evidence:** `src/promptgrimoire/export/unicode_latex.py`, `tests/unit/test_unicode_handling.py`, `tests/conftest.py`.

**Why not alternatives:** The emoji library provides a maintained database of emoji codepoints. The stdlib has no emoji detection. Regex-based detection is fragile as new emoji are added with each Unicode version.

**Classification:** Protective belt. Used for a specific Unicode edge case in LaTeX export.

### lxml >= 6.0

**Claim:** HTML normalisation in the export pipeline. Converts HTML to a consistent structure before LaTeX conversion.

**Evidence:** `src/promptgrimoire/export/html_normaliser.py` (imports `lxml.html`).

**Why not alternatives:** lxml provides fast, standards-compliant HTML parsing with tree manipulation. Used specifically for normalising HTML structure (fixing unclosed tags, consistent element nesting) before the pandoc conversion step.

**Classification:** Protective belt. Used in one module. Could potentially be replaced by selectolax, but lxml's HTML normalisation behaviour is well-understood and standards-compliant.

## Dev Dependencies

### pytest >= 8.0

**Claim:** Test framework. All 1,975+ tests use pytest.

**Evidence:** `tests/` directory, `pyproject.toml` test configuration.

### pytest-asyncio >= 0.24

**Claim:** Async test support. All database and CRDT tests are async.

**Evidence:** `pyproject.toml` configures `asyncio_mode = "auto"`. Used throughout integration tests.

**Gotcha:** Must use `@pytest_asyncio.fixture` (not `@pytest.fixture`) on async fixtures. Guard test in `tests/unit/test_async_fixture_safety.py`. See CLAUDE.md.

### pytest-xdist[psutil] >= 3.8.0

**Claim:** Parallel test execution. `test-all` uses `-n auto --dist=worksteal`.

**Evidence:** `src/promptgrimoire/cli.py` configures xdist flags for parallel execution.

**Gotcha:** E2E tests must be excluded from xdist runs (`-m "not e2e"`) because Playwright's event loop contaminates workers. See #121.

### pytest-playwright >= 0.7.2

**Claim:** Playwright integration for pytest. Provides fixtures for E2E browser testing.

**Evidence:** `tests/e2e/` directory. Provides `page`, `browser`, `context` fixtures.

### playwright >= 1.49

**Claim:** Browser automation for E2E tests.

**Evidence:** Transitive via pytest-playwright, but also listed explicitly for `playwright install` CLI access.

### pytest-subtests >= 0.15.0

**Claim:** Subtest support for sharing expensive fixtures across related assertions in E2E tests.

**Evidence:** Extensively used in `tests/e2e/` — `test_annotation_cards.py`, `test_annotation_sync.py`, `test_auth_pages.py`, `test_annotation_basics.py`, `test_annotation_highlights.py`.

### pytest-order >= 1.3.0

**Claim:** Test ordering. Used to ensure PDF compilation tests run first (they're slow and fail-fast is useful).

**Evidence:** `@pytest.mark.order("first")` in `tests/integration/test_pdf_export.py`, `test_chatbot_fixtures.py`.

### pytest-depper >= 0.2.0

**Claim:** Test dependency analysis. Used by `test-debug` CLI command to identify which tests to run based on code changes.

**Evidence:** `src/promptgrimoire/cli.py` references pytest-depper for smart test selection.

### pytest-cov >= 6.0

**Claim:** Code coverage reporting.

**Evidence:** `pyproject.toml` `[tool.coverage.*]` configuration.

### pre-commit >= 4.5.1

**Claim:** Git hook management for pre-commit lint and type checks.

**Evidence:** `.pre-commit-config.yaml` (assumed), git hooks run ruff + ty on commit.

### ruff >= 0.14.11

**Claim:** Linter and formatter. Replaces flake8, isort, black, and pyupgrade.

**Evidence:** `pyproject.toml` `[tool.ruff.*]` configuration. Claude Code hooks run ruff on every file write.

### ast-grep-cli >= 0.40.5

**Claim:** Structural code search via AST pattern matching. Available as an MCP tool for Claude Code.

**Evidence:** Used by Claude Code's ast-grep MCP server for structural searches. Not imported by application code.

### psycopg[binary] >= 3.2

**Claim:** Synchronous PostgreSQL driver for test setup. Used by `tests/conftest.py` to truncate tables via a sync `create_engine` call.

**Evidence:** `tests/conftest.py:59` — converts `postgresql+asyncpg://` to `postgresql+psycopg://` for synchronous table truncation during test database reset.

**Why not alternatives:** SQLAlchemy's synchronous `create_engine` needs a sync driver. asyncpg only works with `create_async_engine`. The test conftest needs a one-shot sync connection for table cleanup.

**Classification:** Protective belt. Only needed for test infrastructure, not production.

### lorem-text >= 3.0

**Claim:** Lorem ipsum text generation for chat anonymisation utility script.

**Evidence:** `scripts/anonymise_chats.py` — single usage for replacing real chat content with placeholder text.

**Why not alternatives:** Simple, single-purpose library. Could be replaced by a hand-rolled generator, but the script is a utility, not production code.

**Classification:** Protective belt. Dev-only utility.
