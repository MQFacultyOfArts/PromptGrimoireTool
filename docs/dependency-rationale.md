# Dependency Rationale

Last reviewed: 2026-02-10

Each dependency lists: what it does, why it's here (not a stdlib/transitive alternative), and where the evidence is.

## Production Dependencies

### nicegui == 3.6.1

**Claim:** Web UI framework. The entire frontend is built on NiceGUI's component model, server-sent events, and WebSocket integration.

**Evidence:** 13 files across `src/promptgrimoire/pages/` and `src/promptgrimoire/__init__.py` import from nicegui. Every page route, dialog, and UI component depends on it. Also provides the app server (`ui.run`), static file serving, client-side JS execution (`ui.run_javascript`), and the WebSocket-based client–server communication layer.

**Pin rationale:** Pinned to 3.6.1 because 3.7.x introduces a destroy+recreate regression that breaks char span injection. See `docs/design-plans/2026-02-10-nicegui-3.7.x-regression.md`.

**Why not alternatives:** NiceGUI was chosen for Python-native UI without a JS frontend build step. The project is deeply coupled to NiceGUI's component API, page routing, and storage system.

**Classification:** Hard core. Replacing NiceGUI means rewriting the entire frontend.

### sqlmodel >= 0.0.22

**Claim:** ORM combining Pydantic validation with SQLAlchemy query building. All database models are SQLModel classes.

**Evidence:** 9 files import from sqlmodel (8 in `src/promptgrimoire/db/` + `src/promptgrimoire/cli.py`). All 6 database tables (User, Course, CourseEnrollment, Week, Workspace, WorkspaceDocument) are SQLModel classes. Alembic migrations use SQLModel.metadata. Note: `models/scenario.py` uses stdlib `@dataclass`, not SQLModel.

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

**Claim:** Data validation via SQLModel's re-export of `Field`. Provides field constraints (max_length, ge, le, unique, index) used extensively in database models. Version floor pin — no direct `from pydantic import` statements exist in the codebase.

**Evidence:** `src/promptgrimoire/db/models.py` uses `from sqlmodel import Field, SQLModel` — the `Field` function is pydantic's, re-exported by sqlmodel. Constraints like `max_length=255`, `ge=1`, `le=52` are pydantic validation features. Also a transitive dependency of SQLModel and NiceGUI.

**Why not alternatives:** Pydantic is the standard Python validation library. SQLModel requires it. The explicit listing provides a minimum version floor tighter than SQLModel's own pydantic requirement.

**Classification:** Hard core (via SQLModel coupling and pydantic-settings). Now also used directly for `BaseModel` sub-models, `SecretStr`, and `@model_validator` in `src/promptgrimoire/config.py`.

**Revised:** 2026-02-13 — pydantic-settings migration adds direct usage of advanced pydantic features (BaseModel, SecretStr, model_validator) beyond SQLModel's Field re-export.

### pydantic-settings >= 2.8

**Added:** 2026-02-13
**Design plan:** docs/design-plans/2026-02-13-130-pydantic-settings.md
**Claim:** Typed configuration from environment variables and `.env` files. Replaces scattered `os.environ.get()` calls with a single validated `Settings(BaseSettings)` class.
**Evidence:** `src/promptgrimoire/config.py` (Settings class, get_settings singleton). All 15 files that previously used `os.environ.get()` now import from config.
**Why not alternatives:** pydantic-settings integrates natively with the existing Pydantic ecosystem (SQLModel, pydantic-ai). Provides type validation, SecretStr masking, and `.env` reading without manual `load_dotenv()`.
**Classification:** Hard core. All application configuration flows through it.

### ~~python-dotenv >= 1.0~~ (SUPERSEDED)

Superseded 2026-02-13 by pydantic-settings, which reads `.env` files natively (using python-dotenv internally as a transitive dependency). Direct `load_dotenv()` calls eliminated. See design plan `2026-02-13-130-pydantic-settings.md`.

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

**Evidence:** 14 migration files in `alembic/versions/`, `alembic/env.py`. CLAUDE.md documents "Alembic is the ONLY way to create/modify schema" as a project rule.

**Why not alternatives:** Alembic is the standard migration tool for SQLAlchemy. No viable alternative for SQLModel projects.

**Classification:** Hard core. All schema evolution depends on it.

### ~~bs4~~ (REMOVED)

Removed 2026-02-07. `list_normalizer.py` rewritten to use stdlib `re` (regex is sufficient for the simple `<li value>` → `<ol start>` transformation — DOM parsing added unwanted HTML5 normalisation like `<tbody>` insertion). Benchmark test migrated to selectolax. See #122.

### selectolax >= 0.4.6

**Claim:** Fast HTML parser (lexbor backend) for the input pipeline and export platform preprocessing.

**Evidence:** 8 files: `src/promptgrimoire/input_pipeline/html_input.py` and 7 files in `src/promptgrimoire/export/platforms/` (`__init__.py`, `base.py`, `claude.py`, `gemini.py`, `openai.py`, `scienceos.py`, `aistudio.py`). Used for HTML parsing, attribute stripping, element traversal, and content extraction.

**Why not alternatives:** selectolax with lexbor is significantly faster than stdlib alternatives. Chosen for performance in the HTML processing pipeline.

**Classification:** Hard core for the input/export pipeline. Replacing it means rewriting all HTML processing.

### ~~pylatexenc~~ (REMOVED)

Removed 2026-02-10. The Lark+pylatexenc marker pipeline in `export/latex.py` was replaced by the Pandoc Lua filter pipeline (`export/highlight_spans.py` + `export/filters/highlight.lua`). Highlights are now injected as HTML `<span>` attributes before Pandoc conversion, and the Lua filter reads them directly -- no post-Pandoc LaTeX AST walking needed. See #134.

### ~~lark~~ (REMOVED)

Removed 2026-02-10. Same replacement as pylatexenc above. The Lark lexer grammar for marker tokenization is no longer needed -- the Lua filter reads highlight data from span attributes set during pre-Pandoc processing. See #134.

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

### pydantic-ai >= 1.56.0

**Added:** 2026-02-10
**Design plan:** docs/design-plans/2026-02-10-llm-playground.md
**Claim:** Model-agnostic LLM agent framework for the playground. Provides unified streaming events (`ThinkingPart`, `TextPart`, `PartStartEvent`, `PartDeltaEvent`) across Anthropic and OpenRouter providers, eliminating the need for per-provider streaming code.
**Evidence:** Will be imported in `src/promptgrimoire/llm/playground_provider.py` (provider factory), `src/promptgrimoire/pages/playground.py` (streaming handler). Uses `AnthropicModel` for direct Claude access and `OpenRouterModel` for all other providers.
**Why not alternatives:** The existing `ClaudeClient` (anthropic SDK) only supports Anthropic. pydantic-ai abstracts multiple providers with a single streaming interface, supports extended thinking across providers (Claude native, DeepSeek `<think>` tags, Gemini reasoning_details), and handles `message_history` serialization for cross-model conversations. LiteLLM was considered but adds a proxy server; pydantic-ai is a library.
**Classification:** Hard core for the playground feature. The provider abstraction and streaming event model are built around pydantic-ai's API.

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

**Claim:** Subtest support for sharing expensive fixtures across related assertions in E2E and integration tests.

**Evidence:** Extensively used in `tests/e2e/` — `test_annotation_cards.py`, `test_annotation_sync.py`, `test_auth_pages.py`, `test_annotation_basics.py`, `test_annotation_highlights.py`. Also used in LaTeX integration tests for mega-document compile-once patterns where multiple assertions share a single expensive compile.

**Revised:** 2026-02-12 — expanded from E2E-only to integration test usage per `docs/design-plans/2026-02-12-latex-test-optimization.md`.

### pytest-order >= 1.3.0

**Claim:** Test ordering. Used to ensure PDF compilation tests run first (they're slow and fail-fast is useful).

**Evidence:** `@pytest.mark.order("first")` in 7 files: `tests/integration/test_pdf_export.py`, `tests/integration/test_chatbot_fixtures.py`, `tests/integration/test_pdf_pipeline.py`, `tests/unit/test_latex_packages.py`, `tests/unit/test_latex_environment.py`, `tests/unit/test_overlapping_highlights.py`, `tests/unit/export/test_latex_string_functions.py`.

### pytest-depper >= 0.2.0

**Claim:** Test dependency analysis. Used by `test-debug` CLI command to identify which tests to run based on code changes.

**Evidence:** `src/promptgrimoire/cli.py` references pytest-depper for smart test selection.

### pre-commit >= 4.5.1

**Claim:** Git hook management for pre-commit lint and type checks.

**Evidence:** `.pre-commit-config.yaml` (assumed), git hooks run ruff + ty on commit.

### ruff >= 0.14.11

**Claim:** Linter and formatter. Replaces flake8, isort, black, and pyupgrade.

**Evidence:** `pyproject.toml` `[tool.ruff.*]` configuration. Claude Code hooks run ruff on every file write.

### ast-grep-cli >= 0.40.5

**Claim:** Structural code search via AST pattern matching. Available as an MCP tool for Claude Code.

**Evidence:** Used by Claude Code's ast-grep MCP server for structural searches. Not imported by application code.

### rich >= 14.3.1

**Claim:** Terminal formatting for CLI output.

**Evidence:** `src/promptgrimoire/cli.py` uses Rich for test runner output formatting (panels, status displays).

**Why not alternatives:** Rich provides formatted terminal output. The alternative is plain print statements, which would degrade the developer experience for `test-debug` and `test-all`.

**Classification:** Protective belt. Only used in dev CLI tooling (`test-debug`, `test-all`), not in the web application. Moved from production deps to dev.

### psycopg[binary] >= 3.2

**Claim:** Synchronous PostgreSQL driver for test setup. Used by `tests/conftest.py` to truncate tables via a sync `create_engine` call.

**Evidence:** `tests/conftest.py:59` — converts `postgresql+asyncpg://` to `postgresql+psycopg://` for synchronous table truncation during test database reset.

**Why not alternatives:** SQLAlchemy's synchronous `create_engine` needs a sync driver. asyncpg only works with `create_async_engine`. The test conftest needs a one-shot sync connection for table cleanup.

**Classification:** Protective belt. Only needed for test infrastructure, not production.
