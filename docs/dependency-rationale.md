# Dependency Rationale

Last reviewed: 2026-03-10

Each dependency lists: what it does, why it's here (not a stdlib/transitive alternative), and where the evidence is.

## Production Dependencies

### nicegui == 3.8.0

**Claim:** Web UI framework. The entire frontend is built on NiceGUI's component model, server-sent events, and WebSocket integration.

**Evidence:** 13 files across `src/promptgrimoire/pages/` and `src/promptgrimoire/__init__.py` import from nicegui. Every page route, dialog, and UI component depends on it. Also provides the app server (`ui.run`), static file serving, client-side JS execution (`ui.run_javascript`), and the WebSocket-based client–server communication layer.

**Pin rationale:** Pinned to 3.8.0 which includes our upstream fixes (#5805 element re-render regression, #5806 Outbox.stop wake, #5749 SPA script injection). The 3.7.x destroy+recreate regression from `docs/design-plans/2026-02-10-nicegui-3.7.x-regression.md` is resolved. The `Outbox.stop()` monkey-patch in `cli.py` was removed as the fix is now upstream.

**Why not alternatives:** NiceGUI was chosen for Python-native UI without a JS frontend build step. The project is deeply coupled to NiceGUI's component API, page routing, and storage system.

**Classification:** Hard core. Replacing NiceGUI means rewriting the entire frontend.

### sqlmodel >= 0.0.22

**Claim:** ORM combining Pydantic validation with SQLAlchemy query building. All database models are SQLModel classes.

**Evidence:** 12 files import from sqlmodel (11 in `src/promptgrimoire/db/` + `src/promptgrimoire/cli.py`). All 12 database tables (User, Course, CourseEnrollment, Week, Activity, Workspace, WorkspaceDocument, TagGroup, Tag, Permission, CourseRoleRef, ACLEntry) are SQLModel classes. Alembic migrations use SQLModel.metadata. Note: `models/scenario.py` uses stdlib `@dataclass`, not SQLModel.

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
**Design plan:** docs/design-plans/2026-02-13-pydantic-settings-130.md
**Claim:** Typed configuration from environment variables and `.env` files. Replaces scattered `os.environ.get()` calls with a single validated `Settings(BaseSettings)` class.
**Evidence:** `src/promptgrimoire/config.py` (Settings class, get_settings singleton). All 15 files that previously used `os.environ.get()` now import from config.
**Why not alternatives:** pydantic-settings integrates natively with the existing Pydantic ecosystem (SQLModel, pydantic-ai). Provides type validation, SecretStr masking, and `.env` reading without manual `load_dotenv()`.
**Classification:** Hard core. All application configuration flows through it.

### ~~python-dotenv >= 1.0~~ (SUPERSEDED)

Superseded 2026-02-13 by pydantic-settings, which reads `.env` files natively (using python-dotenv internally as a transitive dependency). Direct `load_dotenv()` calls eliminated. See design plan `2026-02-13-pydantic-settings-130.md`.

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

### pydantic-ai >= 1.67.0

**Added:** 2026-02-10
**Design plan:** docs/design-plans/2026-02-10-llm-playground.md
**Revised:** 2026-03-12 — version bumped to >=1.67.0 for wargame turn cycle engine (Seam 3, #296). Used for structured AI output with typed return models.
**Claim:** Model-agnostic LLM agent framework. Provides structured output validation (Pydantic-typed return models), unified streaming events, and message history serialisation across providers.
**Evidence:** `src/promptgrimoire/wargame/agents.py` (turn_agent, summary_agent with TurnResult/StudentSummary output types). Called from `src/promptgrimoire/db/wargames.py` (start_game, run_preprocessing, publish_all). Will also be imported in `src/promptgrimoire/llm/playground_provider.py` (provider factory), `src/promptgrimoire/pages/playground.py` (streaming handler).
**Why not alternatives:** The existing `ClaudeClient` (anthropic SDK) only supports Anthropic and lacks structured output validation. pydantic-ai abstracts multiple providers with a single streaming interface, validates model responses against Pydantic schemas with automatic retry on validation failure, and handles `message_history` serialization. LiteLLM was considered but adds a proxy server; pydantic-ai is a library.
**Classification:** Hard core for playground and wargame features. The provider abstraction, structured output types, and message history serialisation are built around pydantic-ai's API.

### ~~apscheduler >= 3.11, < 4~~ (REMOVED)

**Removed:** 2026-03-12
**Reason:** Never added to `pyproject.toml`. The design plan originally specified APScheduler for deadline scheduling, but implementation used a polling worker (`deadline_worker.py`) instead. Polling follows the same pattern as `search_worker.py` (30s adaptive interval) and avoids APScheduler's async compatibility issues (3.x requires sync PostgreSQL driver; 4.x is alpha). Deadlines survive restarts because state is in `WargameTeam.current_deadline` -- the worker simply polls for expired rows on startup.

### typer[all]

**Added:** 2026-03-02
**Design plan:** docs/design-plans/2026-03-02-cli-typer-211.md
**Claim:** CLI framework for all developer-facing commands. Replaces argparse and raw `sys.argv` parsing with type-annotated argument declarations, auto-generated help, and shell completion.
**Evidence:** All files in `src/promptgrimoire/cli/` import typer. The single entry point `grimoire` in `[project.scripts]` points to `promptgrimoire.cli:app`, a `typer.Typer()` instance. Sub-apps for test, e2e, admin, seed, export, and docs are registered via `add_typer()`.
**Why not alternatives:** click is typer's underlying library but requires more boilerplate. argparse (stdlib) lacks auto-generated Rich help, shell completion, and the composable sub-app model. The project already uses Rich and Pydantic, which typer integrates with natively.
**Classification:** Hard core for CLI. All command-line entry points depend on it.

### python-slugify >= 8.0.4

**Added:** 2026-03-10
**Design plan:** docs/design-plans/2026-03-08-pdf-export-filename-271.md
**Claim:** Deterministic ASCII transliteration and underscore-safe separator normalisation for PDF export filename segments.
**Evidence:** Phase 1 of `pdf-export-filename-271` selects a transliteration dependency for the new filename policy in `src/promptgrimoire/export/filename.py`. The builder must convert names such as `José Núñez` to `Jose_Nunez` and remove emoji/symbol-only input before the export basename is passed into `export_annotation_pdf(...)`.
**Why not alternatives:** The design explicitly rejects relying on a vague "Unidecode or similar" layer. The tests need the concrete `text-unidecode` behaviour that `python-slugify` provides in this environment, including deterministic transliteration plus punctuation-to-underscore normalisation for Turnitin- and Windows-safe filenames. Recreating that behaviour with stdlib-only code would mean maintaining our own transliteration table and separator cleanup rules.
**Classification:** Protective belt. Narrow runtime dependency used only by the export filename policy.

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

### junitparser >= 4.0.2

**Added:** 2026-02-20
**Design plan:** docs/design-plans/2026-02-20-parallel-e2e-runner-95.md
**Claim:** JUnit XML merging for parallel E2E test runner. Each worker subprocess produces its own JUnit XML file; junitparser merges them into a single aggregate report.
**Evidence:** `src/promptgrimoire/cli.py` — used in `_run_parallel_e2e()` to merge per-file XML results.
**Serves:** Developers (aggregate test results), CI (single JUnit XML for reporting).

### pytest-rerunfailures >= 16.1

**Added:** 2026-02-22
**Claim:** Automatic retry for flaky tests. Provides `--reruns N` flag to re-run failed tests up to N times before reporting failure. Used by `test-all` and `test-e2e` CLI commands to mitigate transient PostgreSQL connection errors under xdist parallelism.
**Evidence:** `pyproject.toml` dev dependency. `src/promptgrimoire/cli.py` passes `--reruns` flag in test runner commands.
**Why not alternatives:** pytest-rerunfailures is the standard pytest plugin for test retries. No viable alternative with the same pytest integration.
**Classification:** Protective belt. Test infrastructure only.

### pytest-sugar >= 1.1.1

**Added:** 2026-02-22
**Claim:** Prettier pytest progress bars. Auto-activates as a pytest plugin when installed. Replaces the default dot-based progress with a real-time progress bar showing test names and pass/fail status.
**Evidence:** `pyproject.toml` dev dependency. No explicit imports -- pytest auto-discovers the plugin.
**Why not alternatives:** pytest-sugar is the standard pytest progress plugin. Drop-in replacement for default output.
**Classification:** Protective belt. Developer experience only. No code depends on it.

### playwright >= 1.49

**Claim:** Browser automation for E2E tests.

**Evidence:** Transitive via pytest-playwright, but also listed explicitly for `playwright install` CLI access.

### pytest-subtests >= 0.15.0

**Claim:** Subtest support for sharing expensive fixtures across related assertions in E2E and integration tests.

**Evidence:** Extensively used in `tests/e2e/` — `test_annotation_cards.py`, `test_annotation_sync.py`, `test_auth_pages.py`, `test_annotation_basics.py`, `test_annotation_highlights.py`. Also used in LaTeX integration tests for mega-document compile-once patterns where multiple assertions share a single expensive compile.

**Revised:** 2026-02-12 — expanded from E2E-only to integration test usage per `docs/design-plans/2026-02-12-latex-test-optimization-76.md`.

### pytest-order >= 1.3.0

**Claim:** Test ordering. Used to ensure PDF compilation tests run first (they're slow and fail-fast is useful).

**Evidence:** `@pytest.mark.order("first")` in 7 files: `tests/integration/test_pdf_export.py`, `tests/integration/test_chatbot_fixtures.py`, `tests/integration/test_pdf_pipeline.py`, `tests/unit/test_latex_packages.py`, `tests/unit/test_latex_environment.py`, `tests/unit/test_overlapping_highlights.py`, `tests/unit/export/test_latex_string_functions.py`.

### pytest-depper >= 0.2.0

**Claim:** Test dependency analysis. Used by `test-changed` CLI command to identify which tests to run based on code changes.

**Evidence:** `src/promptgrimoire/cli.py` references pytest-depper for smart test selection.

### pre-commit >= 4.5.1

**Claim:** Git hook management for pre-commit lint and type checks.

**Evidence:** `.pre-commit-config.yaml` (assumed), git hooks run ruff + ty on commit.

### ruff >= 0.14.11

**Claim:** Linter and formatter. Replaces flake8, isort, black, and pyupgrade.

**Evidence:** `pyproject.toml` `[tool.ruff.*]` configuration. Claude Code hooks run ruff on every file write.

### pyright >= 1.1.408

**Added:** 2026-03-10
**Claim:** LSP server for Claude Code. Provides code intelligence (go-to-definition, hover, find-references) during AI-assisted development sessions. Not used for type checking — the project uses `ty` for that.
**Evidence:** `pyproject.toml` dev dependency. No CLI invocation or CI integration.
**Classification:** Protective belt. Developer tooling only, no code depends on it.

### ast-grep-cli >= 0.40.5

**Claim:** Structural code search via AST pattern matching. Available as an MCP tool for Claude Code.

**Evidence:** Used by Claude Code's ast-grep MCP server for structural searches. Not imported by application code.

### rich >= 14.3.1

**Claim:** Terminal formatting for CLI output.

**Evidence:** `src/promptgrimoire/cli.py` uses Rich for test runner output formatting (panels, status displays).

**Why not alternatives:** Rich provides formatted terminal output. The alternative is plain print statements, which would degrade the developer experience for `test-changed` and `test-all`.

**Classification:** Protective belt. Only used in dev CLI tooling (`test-changed`, `test-all`), not in the web application. Moved from production deps to dev.

### psycopg[binary] >= 3.2

**Claim:** Synchronous PostgreSQL driver for test setup. Used by `tests/conftest.py` to truncate tables via a sync `create_engine` call.

**Evidence:** `tests/conftest.py:59` — converts `postgresql+asyncpg://` to `postgresql+psycopg://` for synchronous table truncation during test database reset.

**Why not alternatives:** SQLAlchemy's synchronous `create_engine` needs a sync driver. asyncpg only works with `create_async_engine`. The test conftest needs a one-shot sync connection for table cleanup.

**Classification:** Protective belt. Only needed for test infrastructure, not production.

### Pillow

**Added:** 2026-02-28
**Design plan:** docs/design-plans/2026-02-28-docs-platform-208.md
**Claim:** Image processing for whitespace trimming of screenshots captured during guide generation. `ImageChops.difference()` detects content bounds, `Image.crop()` removes empty margins.
**Evidence:** `src/promptgrimoire/docs/screenshot.py` — `trim_whitespace()` function.
**Serves:** Developers (guide authoring), end users (cleaner screenshots in documentation).

### uniseg

**Added:** 2026-03-02
**Design plan:** docs/design-plans/2026-03-02-word-count-limits-47.md
**Claim:** UAX #29 compliant Unicode word boundary detection. Used as the default tokeniser for Latin, Korean, and other space-delimited scripts in the word count function.
**Evidence:** `src/promptgrimoire/word_count.py` — `word_count()` calls `uniseg.wordbreak.words()` for non-CJK text segments.
**Serves:** Runtime users (accurate word counting for limit enforcement).

### jieba

**Added:** 2026-03-02
**Design plan:** docs/design-plans/2026-03-02-word-count-limits-47.md
**Claim:** Chinese text word segmentation. Chinese text has no whitespace between words; jieba provides dictionary-based segmentation required for accurate word counting.
**Evidence:** `src/promptgrimoire/word_count.py` — `word_count()` calls `jieba.lcut()` for segments classified as "zh" by `segment_by_script()`.
**Serves:** Runtime users (accurate Chinese word counting in translation assessments).

### mecab-python3 + unidic-lite

**Added:** 2026-03-02
**Design plan:** docs/design-plans/2026-03-02-word-count-limits-47.md
**Claim:** Japanese morphological analysis. Japanese text mixes kanji, hiragana, and katakana without whitespace boundaries; MeCab provides dictionary-based segmentation. unidic-lite provides the bundled dictionary.
**Evidence:** `src/promptgrimoire/word_count.py` — `word_count()` calls `_MECAB_TAGGER.parse()` (MeCab.Tagger with `-Owakati` output) for segments classified as "ja" by `segment_by_script()`.
**Serves:** Runtime users (accurate Japanese word counting in translation assessments).

### mkdocs-material

**Added:** 2026-02-28
**Design plan:** docs/design-plans/2026-02-28-docs-platform-208.md
**Claim:** Static site generator for HTML documentation. Renders guide markdown and screenshots into a themed HTML site deployable to GitHub Pages.
**Evidence:** `mkdocs.yml` — site configuration. `src/promptgrimoire/cli.py` — `mkdocs build` invoked by `make_docs()`.
**Serves:** Instructors and students (browsable user guides), developers (local preview via `mkdocs serve`).

### pip-audit

**Added:** 2026-03-03
**Design plan:** docs/design-plans/2026-03-03-ci-harness.md
**Claim:** Scans installed Python packages against known CVE databases. Catches dependency vulnerabilities before they reach production.
**Evidence:** CI quality job runs `uv run pip-audit` to scan the locked environment.
**Serves:** Developers and CI (supply-chain security gate).

### mammoth

**Added:** 2026-03-10
**Design plan:** docs/design-plans/2026-03-10-file-upload-109.md
**Claim:** Converts DOCX (Word XML) to semantic HTML preserving headings, lists, bold/italic, and paragraph structure. Used in the input pipeline for file upload.
**Evidence:** `src/promptgrimoire/input_pipeline/converters.py` — `convert_docx_to_html()` calls `mammoth.convert_to_html()`.
**Serves:** Runtime users (students/instructors uploading DOCX files).

### pymupdf4llm

**Added:** 2026-03-10
**Design plan:** docs/design-plans/2026-03-10-file-upload-109.md
**Claim:** Extracts structured Markdown from PDF files using AI-based layout analysis (via pymupdf.layout). Produces paragraph-aware output that pymupdf's raw text extraction does not.
**Evidence:** `src/promptgrimoire/input_pipeline/converters.py` — `convert_pdf_to_html()` calls `pymupdf4llm.to_markdown()`.
**Serves:** Runtime users (students/instructors uploading PDF files).

### pymupdf-layout

**Added:** 2026-03-10
**Design plan:** docs/design-plans/2026-03-10-file-upload-109.md
**Claim:** Graph Neural Network layout analysis engine for pymupdf. Imported before pymupdf4llm to activate enhanced paragraph, table, and heading detection in PDFs. Runs on CPU without GPU.
**Evidence:** `src/promptgrimoire/input_pipeline/converters.py` — `import pymupdf.layout` must precede pymupdf4llm usage.
**Serves:** Runtime users (improved PDF structure detection).

### browserstack-sdk

**Added:** 2026-03-12
**Design plan:** docs/design-plans/2026-03-12-cross-browser-e2e-261.md
**Claim:** BrowserStack SDK for cross-browser E2E testing against real browsers. Wraps pytest invocation (`browserstack-sdk pytest ...`) and transparently intercepts Playwright's browser launch, routing it through a CDP WebSocket to BrowserStack's cloud. Also manages the BrowserStack Local tunnel for localhost testing.
**Evidence:** `src/promptgrimoire/cli/e2e/__init__.py` — `browserstack` subcommand swaps subprocess prefix to `["browserstack-sdk", "pytest"]`. `browserstack/*.yml` — platform configs.
**Serves:** Developers (local cross-browser testing), CI (PR gate against real Safari/Firefox).

### openpyxl

**Added:** 2026-03-12
**Design plan:** docs/design-plans/2026-03-12-bulk-enrol-320.md
**Claim:** Parses Moodle "Grades" XLSX exports for bulk student enrolment. Used in `src/promptgrimoire/enrol/xlsx_parser.py` to read workbook bytes, iterate rows, and extract student data.
**Evidence:** `from openpyxl import load_workbook` in `enrol/xlsx_parser.py` (to be created in Phase 2 of bulk-enrol-320).
**Serves:** Runtime — admin CLI and instructor UI upload both depend on XLSX parsing.
**Why not alternatives:** `pandas` is heavyweight for simple row iteration. `xlrd` only supports `.xls` (not `.xlsx`). openpyxl is the de facto standard for `.xlsx` in Python, read-only mode is memory-efficient.

### ~~bandit~~ (REMOVED)

**Removed:** 2026-03-03
**Design plan:** docs/design-plans/2026-03-03-ci-harness.md
**Reason:** Replaced by ruff's `S` rule set, which reimplements Bandit's security checks natively with 10-100x better performance. Rule skips (B101→S101, B404→S404, B603→S603, B607→S607) carry over to ruff configuration.

### openpyxl

**Added:** 2026-03-12
**Design plan:** docs/design-plans/2026-03-12-bulk-enrol-320.md
**Claim:** Parses Moodle "Grades" XLSX exports for bulk student enrolment. Used in `src/promptgrimoire/enrol/xlsx_parser.py` to read workbook bytes, iterate rows, and extract student data.
**Evidence:** `from openpyxl import load_workbook` in `enrol/xlsx_parser.py` (to be created in Phase 2 of bulk-enrol-320).
**Serves:** Runtime — admin CLI and instructor UI upload both depend on XLSX parsing.
**Why not alternatives:** `pandas` is heavyweight for simple row iteration. `xlrd` only supports `.xls` (not `.xlsx`). openpyxl is the de facto standard for `.xlsx` in Python, read-only mode is memory-efficient.
