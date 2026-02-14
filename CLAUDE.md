# PromptGrimoire - Claude Code Instructions

## Project Overview

PromptGrimoire is a collaborative "classroom grimoire" for prompt iteration, annotation, and sharing in educational contexts. Based on the pedagogical framework from "Teaching the Unknown" (Ballsun-Stanton & Torrington, 2025).

**Target:** Session 1 2026 (Feb 23)

## Use Cases

### 1. Prompt Annotation & Sharing (Core)

Collaborative annotation of AI conversations for teaching prompt engineering. Students and instructors can highlight, comment on, and tag conversation turns.

### 2. Legal Client Interview Simulation (Spike 4)

Import SillyTavern character cards to run AI-powered roleplay scenarios. Initial use case: tort law training where students interview a simulated client (Becky Bennett workplace injury case).

- **Input**: SillyTavern chara_card_v3 JSON with embedded lorebook
- **Features**: Keyword-triggered context injection, empathy-based trust mechanics
- **Output**: JSONL chat log for post-session annotation

See: [Issue #32](https://github.com/MQFacultyOfArts/PromptGrimoireTool/issues/32)

### 3. Legal Case Brief Tool (Planned)

Structured legal case brief generation and analysis. PRD forthcoming.

## Tech Stack

- **Python 3.14** - bleeding edge
- **NiceGUI** - web UI framework
- **SQLModel** - ORM (Pydantic + SQLAlchemy)
- **PostgreSQL** - persistence
- **pycrdt** - CRDT for real-time collaboration
- **Stytch** - auth (magic links, passkeys, RBAC)
- **selectolax** - fast HTML parser (lexbor backend) for input pipeline
- **lxml** - HTML normalisation in export pipeline

## Development Workflow

### TDD is Mandatory

See [docs/testing.md](docs/testing.md) for full testing guidelines including E2E patterns and database isolation rules.

### Async Fixture Rule

**NEVER use `@pytest.fixture` on `async def` functions.** Always use `@pytest_asyncio.fixture`. The sync decorator on async generators causes `Runner.run() cannot be called from a running event loop` under xdist. A guard test (`tests/unit/test_async_fixture_safety.py`) enforces this. See #121.

### E2E Test Isolation

E2E tests (Playwright) are excluded from `test-all` (`-m "not e2e"`) because Playwright's event loop contaminates xdist workers. E2E tests must run separately via `uv run test-e2e`, which:

1. Runs Alembic migrations and truncates the test database
2. Starts a NiceGUI server on a random port (single instance)
3. Runs `pytest -m e2e` with xdist -- all workers share one server via `E2E_BASE_URL`
4. Shuts down the server when tests complete

See #121.

### Code Quality Hooks

Claude Code hooks automatically run on every `.py` file write:

1. `ruff check --fix` - autofix lint issues
2. `ruff format` - format code
3. `ty check` - type checking

All three must pass before code is considered complete.

### Pre-commit Hooks

Git commits trigger:

- ruff lint + format check
- ty type check

Commits will be rejected if checks fail.

## Key Commands

```bash
# Install dependencies
uv sync

# Run tests (smart selection based on changes - fast)
uv run test-debug

# Run all tests (unit + integration, excludes E2E)
uv run test-all

# Run E2E tests (starts server, runs Playwright with xdist)
uv run test-e2e

# Run linting
uv run ruff check .

# Run type checking
uvx ty check

# Seed development data (idempotent)
uv run seed-data

# Run the app
uv run python -m promptgrimoire

```

## Fixture Analysis

`scripts/analyse_fixture.py` — CLI for inspecting HTML conversation fixtures (plain or gzipped) without shell-level zcat/grep/perl.

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

### Visual QA Screenshots

`tests/e2e/test_fixture_screenshots.py` renders all fixtures through the annotation pipeline and captures screenshots to `output/fixture_screenshots/`. Each fixture test clears its own stale screenshots (e.g. `austlii_*.png`) before regenerating — no stale files accumulate.

```bash
# Generate all fixture screenshots (clears output first)
uv run pytest tests/e2e/test_fixture_screenshots.py -v

# Single fixture
uv run pytest tests/e2e/test_fixture_screenshots.py -v -k austlii
```

## Git Worktrees

This project uses git worktrees for parallel feature development. Worktrees are located in `.worktrees/`.

### Worktree Setup

```bash
# Create a new worktree for a feature branch
git worktree add .worktrees/<branch-name> <branch-name>

# List all worktrees
git worktree list

# Remove a worktree when done
git worktree remove .worktrees/<branch-name>
```

### Serena Memory Management

Serena stores project memories in `.serena/memories/`. To ensure all worktrees share the same memories:

1. The main worktree (project root) holds the canonical memories directory
2. When creating a new worktree, symlink its memories to main:

```bash
# After creating a worktree, symlink memories to main
rm -rf .worktrees/<branch>/.serena/memories
ln -s /absolute/path/to/main/.serena/memories .worktrees/<branch>/.serena/memories
```

This ensures:
- All worktrees see the same project context
- Memory updates in any worktree are immediately visible to others
- No duplicate/divergent memories across branches

The `.serena/project.yml` uses `project_name: "PromptGrimoire"` (directory-based) rather than branch names for worktree compatibility.

## Project Structure

```text
src/promptgrimoire/
├── __init__.py
├── __main__.py          # Module entry point
├── cli.py               # CLI tools (test-debug, test-all, test-e2e, seed-data, set-admin, etc.)
├── models/              # Data models (Character, Session, Turn, LorebookEntry)
├── parsers/             # SillyTavern character card parser
├── llm/                 # Claude API client, lorebook activation, prompt assembly
├── input_pipeline/      # HTML input processing (detection, conversion, text extraction)
├── pages/               # NiceGUI page routes
│   ├── annotation.py    # Main annotation page (CSS Highlight API rendering)
│   ├── auth.py          # Login/logout pages (browser feature gate)
│   ├── courses.py       # Course management
│   ├── dialogs.py       # Reusable dialog components
│   ├── highlight_api_demo.py # CSS Highlight API standalone demo
│   ├── index.py         # Landing page
│   ├── layout.py        # Shared page layout
│   ├── milkdown_spike.py # Milkdown editor spike
│   ├── registry.py      # Page route registry
│   ├── roleplay.py      # AI roleplay / client interview
│   └── text_selection.py # Text selection utilities
├── export/              # PDF/LaTeX export
│   ├── highlight_spans.py # Pre-Pandoc highlight span insertion (region computation)
│   ├── html_normaliser.py # HTML normalisation (lxml)
│   ├── latex_format.py  # LaTeX annotation formatting (format_annot_latex)
│   ├── latex_render.py  # LaTeX rendering: NoEscape, escape_latex, latex_cmd, render_latex
│   ├── list_normalizer.py # HTML list normalisation (stdlib re)
│   ├── pandoc.py        # Pandoc HTML-to-LaTeX conversion + pipeline orchestration
│   ├── pdf.py           # LaTeX compilation (async)
│   ├── pdf_export.py    # Export orchestration + generate_tex_only()
│   ├── preamble.py      # LaTeX preamble assembly + colour definitions
│   ├── promptgrimoire-export.sty # Static LaTeX preamble (packages, commands, environments)
│   ├── span_boundaries.py # Block/inline boundary detection for span splitting
│   ├── unicode_latex.py # Unicode detection, font registry, LaTeX escaping
│   ├── platforms/       # Platform-specific HTML preprocessing
│   └── filters/         # Pandoc Lua filters (highlight.lua, legal.lua)
├── static/              # Static assets (JS, CSS)
│   └── annotation-highlight.js # Text walker, highlight rendering, remote presence
├── auth/                # Stytch integration
├── db/                  # Database models, engine, CRUD operations
│   ├── models.py        # SQLModel table classes (User, Course, ..., Activity, Workspace, WorkspaceDocument)
│   ├── activities.py    # Activity CRUD (create with template workspace, list by week/course)
│   ├── courses.py       # Course CRUD (create, list, update, archive, enrollment)
│   ├── workspaces.py    # Workspace CRUD, placement, cloning, PlacementContext query
│   └── workspace_documents.py  # Document CRUD, workspaces_with_documents batch query
└── crdt/                # pycrdt collaboration logic

scripts/
├── analyse_fixture.py   # CLI for inspecting HTML conversation fixtures
├── setup_latex.py       # TinyTeX installer
└── html_to_pdf.py       # HTML to PDF conversion script

tests/
├── conftest.py          # Shared fixtures
├── fixtures/            # Test data (character cards, HTML conversation fixtures)
├── unit/                # Unit tests
├── integration/         # Integration tests
└── e2e/                 # Playwright E2E tests (excluded from test-all)

docs/                    # Cached documentation (auto-populated)
logs/sessions/           # JSONL session logs (auto-created)
```

## Documentation Caching

The `cache-docs` skill automatically saves fetched documentation to `docs/`. Every non-stdlib import should have reference docs cached. Check `docs/_index.md` for available documentation.

Prefer to read cached docs over online searches. If you need to run an online search, don't forget to use the skill to write your results back to the docs.

## PDF Export / LaTeX

PDF export uses TinyTeX for portable, consistent LaTeX compilation.

### Setup

```bash
# Install TinyTeX and required packages
uv run python scripts/setup_latex.py
```

This installs TinyTeX to `~/.TinyTeX` and the required packages:
- `lua-ul` - highlighting with LuaLaTeX
- `fontspec` - system font support
- `luacolor` - color support
- `todonotes` - margin notes
- `geometry` - page layout
- `marginalia` - auto-stacking margin notes (LuaLaTeX)
- `latexmk` - build automation

### Configuration

The `APP__LATEXMK_PATH` env var overrides the default TinyTeX path if needed. Leave empty to use TinyTeX.

### Architecture

- `src/promptgrimoire/export/pdf.py` - `get_latexmk_path()` resolves latexmk location, `compile_latex()` compiles .tex to PDF (async)
- `src/promptgrimoire/export/pdf_export.py` - `export_annotation_pdf()` full pipeline, `generate_tex_only()` for .tex without compilation (used by tests)
- `src/promptgrimoire/export/promptgrimoire-export.sty` - Static LaTeX preamble (packages, commands, environments, macros). Copied to output dir by `ensure_sty_in_dir()` before compilation
- `scripts/setup_latex.py` - installs TinyTeX and packages
- Does NOT fall back to system PATH - TinyTeX only for consistency

**Note:** `compile_latex()` is async and uses `asyncio.create_subprocess_exec()` for non-blocking compilation.

### LaTeX Rendering Utilities (`latex_render.py`)

Safe LaTeX string construction without f-string injection risks. Two patterns:

- `latex_cmd("definecolor", "mycolor", "HTML", "FF0000")` -- for simple `\name{arg1}{arg2}` commands. Arguments auto-escaped unless `NoEscape`.
- `render_latex(t"\\textbf{{{val}}}")` -- for complex templates using Python 3.14 t-strings. Interpolated values auto-escaped unless `NoEscape`.

Public API: `NoEscape`, `escape_latex`, `latex_cmd`, `render_latex`.

**Invariant:** No f-strings for LaTeX generation in the export module. A guard test (`tests/unit/export/test_no_fstring_latex.py`) enforces this.

### Dynamic Font Loading (`unicode_latex.py`)

Font loading is demand-driven based on document content:

1. `detect_scripts(body_text)` scans text for non-Latin Unicode scripts (Hebrew, Arabic, CJK, etc.)
2. `build_font_preamble(scripts)` emits only the `\directlua` fallback fonts needed for detected scripts
3. `build_annotation_preamble(tag_colours, body_text="")` orchestrates: loads `.sty`, generates font preamble, emits colour definitions

`FONT_REGISTRY` maps OpenType script tags to font names. `SCRIPT_TAG_RANGES` maps script tags to Unicode codepoint ranges. Latin fonts are always included.

### Highlight Pipeline (Pandoc + Lua Filter)

The annotation export uses a pre-Pandoc span injection + Lua filter pipeline (Issue #134) to handle arbitrarily nested and overlapping highlights:

1. **Region computation** - `compute_highlight_spans()` in `highlight_spans.py` computes non-overlapping regions from overlapping highlights using an event-sweep algorithm, then inserts `<span data-hl="..." data-colors="..." data-annots="...">` elements into clean HTML
2. **Block boundary splitting** - Boundary detection in `span_boundaries.py`. Spans are pre-split at block element boundaries (p, h1-h6, li, etc.) and inline formatting boundaries (b, em, code, etc.) because Pandoc silently destroys cross-boundary spans
3. **Pandoc conversion** - HTML to LaTeX with `highlight.lua` Lua filter included
4. **Lua filter rendering** - `highlight.lua` reads span attributes and emits nested `\highLight` / `\underLine` / `\annot` LaTeX commands using a "one, two, many" stacking model:
   - 1 highlight: single 1pt underline in tag's dark colour
   - 2 highlights: stacked 2pt outer + 1pt inner underlines
   - 3+ highlights: single 4pt underline in many-dark colour
5. **Post-processing** - `\annot` commands (which contain `\par`) are moved outside restricted LaTeX contexts (e.g. `\section{}` arguments)

Key files:
- `highlight_spans.py` - `compute_highlight_spans()`, `_HlRegion`, region computation + DOM insertion
- `latex_format.py` - `format_annot_latex()` annotation LaTeX formatting
- `span_boundaries.py` - `_detect_block_boundaries()`, `_detect_inline_boundaries()`, `PANDOC_BLOCK_ELEMENTS`
- `filters/highlight.lua` - Pandoc Lua filter for highlight/annotation rendering
- `pandoc.py` - `convert_html_with_annotations()` orchestrator, `convert_html_to_latex()` Pandoc subprocess
- `preamble.py` - `build_annotation_preamble()`, colour definitions
- `promptgrimoire-export.sty` - Static preamble: `\annot` macro, speaker environments, package loading

**Note:** Pandoc strips the `data-` prefix from HTML attributes in Lua filters (e.g. `data-hl` becomes `hl`).

## HTML Input Pipeline

The input pipeline (`src/promptgrimoire/input_pipeline/`) processes pasted or uploaded content for character-level annotation. It is the primary entry path for the annotation page.

### Pipeline Steps

1. **Content type detection** -- `detect_content_type()` uses magic bytes (PDF, DOCX, RTF) and structural heuristics (HTML tags) to classify input
2. **User confirmation** -- `show_content_type_dialog()` lets user override detected type
3. **Conversion to HTML** -- Plain text is wrapped in `<p>` tags; HTML passes through; RTF/DOCX/PDF conversion is Phase 7 (not yet implemented)
4. **Platform preprocessing** -- `preprocess_for_export()` strips chatbot chrome and injects speaker labels (with double-injection guard)
5. **Attribute stripping** -- Removes heavy inline styles, `data-*` attributes (except `data-speaker`), and class attributes to reduce size
6. **Empty element removal** -- Strips empty `<p>`/`<div>` elements (common in Office-pasted HTML)
7. **Text extraction** -- `extract_text_from_html()` builds a character list from clean HTML for highlight coordinate mapping. Highlight rendering and text selection use the CSS Custom Highlight API and JS text walker on the client side.

### Key Design Decision: CSS Custom Highlight API

The pipeline returns clean HTML from the server. Highlight rendering uses the CSS Custom Highlight API (`CSS.highlights`) with `StaticRange` objects built from a JS text walker's node map. Text selection detection converts browser `Selection` ranges to character offsets via the same text walker. The server extracts `document_chars` from the clean HTML using `extract_text_from_html()` for highlight coordinate mapping.

### Public API (`input_pipeline/__init__.py`)

- `detect_content_type(content: str | bytes) -> ContentType` -- Classify input content
- `process_input(content, source_type, platform_hint) -> str` -- Full pipeline (async)
- `extract_text_from_html(html: str) -> list[str]` -- Extract text chars from clean HTML
- `ContentType` -- Literal type: `"html" | "rtf" | "docx" | "pdf" | "text"`
- `CONTENT_TYPES` -- Tuple of all supported type strings

## Database

PostgreSQL with SQLModel. Schema migrations via Alembic.

### Tables (7 SQLModel classes)

- **User** - Stytch-linked user accounts
- **Course** - Course/unit of study with weeks and enrolled members. `default_copy_protection: bool` (default `False`) -- course-level default inherited by activities with `copy_protection=None`.
- **CourseEnrollment** - Maps users to courses with course-level roles
- **Week** - Week within a course with visibility controls
- **Activity** - Assignment within a Week; owns a template Workspace (RESTRICT delete). `week_id` FK with CASCADE delete, `template_workspace_id` FK with RESTRICT delete (unique). `copy_protection: bool | None` -- tri-state: `None`=inherit from course, `True`=on, `False`=off.
- **Workspace** - Container for documents and CRDT state (unit of collaboration). Placement fields: `activity_id` (SET NULL), `course_id` (SET NULL), `enable_save_as_draft`. Mutual exclusivity: a workspace can be in an Activity OR a Course, never both (Pydantic validator + DB CHECK constraint `ck_workspace_placement_exclusivity`).
- **WorkspaceDocument** - Document within a workspace (source, draft, AI conversation). Fields: `content` (clean HTML), `source_type` ("html", "rtf", "docx", "pdf", "text")

### Workspace Architecture

Workspaces are isolated silos identified by UUID. Key design decisions:

- **No `created_by` FK** - Audit (who created) is separate from access control (who can use)
- **Future: ACL for access control** - Seam D will add workspace-user permissions
- **Future: Audit log for history** - Separate table for who-did-what tracking
- **`create_workspace()` takes no parameters** - Just creates an empty workspace with UUID

This separation prevents conflating audit concerns with authorization logic.

### Hierarchy: Course > Week > Activity > Workspace

The content hierarchy is: Course contains Weeks, Weeks contain Activities, Activities own template Workspaces. Students clone the template to get their own Workspace.

- **Activity** owns exactly one **template Workspace** (1:1, RESTRICT delete). `create_activity()` atomically creates both.
- **Workspace placement** is optional: `activity_id` OR `course_id` (mutually exclusive via Pydantic validator + DB CHECK). A workspace with neither is "loose".
- **`PlacementContext`** (frozen dataclass) resolves the full hierarchy chain (Activity -> Week -> Course) for UI display. `display_label` provides a human-readable string like "Annotate Becky in Week 1 for LAWS1100".
- **Template detection**: `is_template` flag on PlacementContext is True when the workspace is an Activity's `template_workspace_id`.
- **Copy protection resolution**: `copy_protection: bool` on PlacementContext is resolved during placement query. Activity's explicit value wins; if `None`, inherits from `Course.default_copy_protection`. Loose and course-placed workspaces always resolve to `False`.

### Workspace Cloning

`clone_workspace_from_activity(activity_id)` creates a student workspace from a template:

1. Creates new Workspace with `activity_id` set and `enable_save_as_draft` copied
2. Copies all WorkspaceDocuments (content, type, source_type, title, order_index) with new UUIDs
3. Returns `(Workspace, doc_id_map)` -- the mapping of template doc UUIDs to cloned doc UUIDs
4. CRDT state is replayed via `_replay_crdt_state()`: highlights get `document_id` remapped, comments are preserved, general notes are copied, client metadata is NOT cloned
5. Entire operation is atomic (single session)

**Delete order for Activity** (circular FK): delete Activity first (SET NULL on student workspaces), then delete orphaned template Workspace (safe because RESTRICT FK no longer points to it).

### App Startup Database Bootstrap

When `DATABASE__URL` is configured, `main()` automatically bootstraps the database before starting the server:

1. **`ensure_database_exists(url) -> bool`** -- Creates the PostgreSQL database if it does not exist. Returns `True` if a new database was created, `False` otherwise (including `None`/empty URL or database already exists).
2. **`run_alembic_upgrade()`** -- Runs Alembic migrations to head (idempotent). Internally calls `ensure_database_exists()` again (harmless -- already exists, returns `False`).
3. **Conditional seeding** -- If `ensure_database_exists()` returned `True` (new DB), runs `uv run seed-data` to populate development data.
4. **Branch info** -- On feature branches (not main/master), prints `Branch: <name> | Database: <db_name>` to stdout.

This means `uv run python -m promptgrimoire` on a new feature branch automatically creates the branch-specific database, migrates it, and seeds it. No manual setup needed.

### Database Rules

1. **Alembic is the ONLY way to create/modify schema** - Never use `SQLModel.metadata.create_all()` except in Alembic migrations themselves
2. **All models must be imported before schema operations** - The `promptgrimoire.db.models` module must be imported to register tables with SQLModel.metadata
3. **Pages requiring DB must check availability** - Use `get_settings().database.url` and show a helpful error if not configured
4. **Use `verify_schema()` at startup** - Fail fast if tables are missing

### Page Database Dependencies

| Page | Route | DB Required |
|------|-------|-------------|
| annotation | `/annotation` | **Yes** |
| courses | `/courses` | **Yes** |
| roleplay | `/roleplay` | No |
| logviewer | `/logs` | No |
| highlight_api_demo | `/demo/highlight-api` | No |
| milkdown_spike | `/demo/milkdown-spike` | No |
| auth | `/login`, `/logout` | Optional |

## Authentication

Stytch handles:

- Magic link login
- Passkey authentication
- RBAC (admin/instructor/student roles)
- Class invitations

### Privilege Check

`is_privileged_user(auth_user)` in `auth/__init__.py` determines whether a user bypasses copy protection. Returns `True` for org-level admins (`is_admin=True`) and users with `instructor` or `stytch_admin` roles. Returns `False` for students, tutors, unauthenticated (`None`), and missing data.

## Copy Protection

Per-activity copy protection prevents students from copying, cutting, dragging, or printing annotated content. Instructors and admins bypass it.

### Resolution Chain

1. `Activity.copy_protection` (tri-state: `None`/`True`/`False`)
2. If `None`, inherit from `Course.default_copy_protection` (bool, default `False`)
3. Resolved in `PlacementContext.copy_protection` during workspace placement query
4. Loose and course-placed workspaces always resolve to `False`

### Client-Side Enforcement

When `protect=True` and user is not privileged:

- **JS injection** (`_inject_copy_protection()` in `annotation.py`): Intercepts `copy`, `cut`, `contextmenu`, `dragstart` events on `#doc-container`, organise columns, and respond reference panel. Intercepts `paste` on Milkdown editor. Intercepts `Ctrl+P`/`Cmd+P`. Shows Quasar toast notification.
- **CSS print suppression**: `@media print` hides `.q-tab-panels`, shows "Printing is disabled" message.
- **Lock icon chip**: Amber "Protected" chip with lock icon in workspace header.

### UI Controls (Courses Page)

- **Course settings dialog** (`open_course_settings()`): Toggle `default_copy_protection` on/off.
- **Per-activity tri-state select**: "Inherit from course" / "On" / "Off". Pure mapping functions `_model_to_ui()` and `_ui_to_model()` convert between model `bool | None` and UI string keys.

## Configuration (pydantic-settings)

All configuration is managed through `src/promptgrimoire/config.py` using pydantic-settings. Environment variables use double-underscore nesting: `DATABASE__URL`, `LLM__API_KEY`, `STYTCH__PROJECT_ID`, etc.

- **Access:** Call `get_settings()` for a cached, validated Settings instance
- **Branch detection:** Call `get_current_branch()` for the current git branch name (or `None` for detached HEAD). Reads `.git/HEAD` directly (no subprocess).
- **Testing:** Construct `Settings(_env_file=None, ...)` directly for isolation; call `get_settings.cache_clear()` to reset the singleton
- **`.env` files:** pydantic-settings reads `.env` natively — no `load_dotenv()` calls anywhere
- **Secrets:** Use `SecretStr` fields; call `.get_secret_value()` at the point of use

### Sub-models

| Prefix | Model | Key fields |
|--------|-------|------------|
| `DATABASE__` | `DatabaseConfig` | `url` |
| `LLM__` | `LlmConfig` | `api_key`, `model`, `thinking_budget`, `lorebook_token_budget` |
| `APP__` | `AppConfig` | `port`, `storage_secret`, `log_dir`, `latexmk_path`, `base_url` |
| `DEV__` | `DevConfig` | `auth_mock`, `enable_demo_pages`, `database_echo`, `test_database_url`, `branch_db_suffix` |
| `STYTCH__` | `StytchConfig` | `project_id`, `secret`, `public_token`, `default_org_id`, `sso_connection_id` |

### Environment Variables

**Source of truth:** `.env.example`

All environment variables are documented in `.env.example`. Copy it to `.env` and configure for your environment.

A test (`tests/unit/test_env_vars.py`) ensures `.env.example` stays in sync with code:

- All env vars used in code must be in `.env.example`
- All vars in `.env.example` must be used in code
- Each variable must have a documentation comment

**When adding new env vars:** Add them to `.env.example` with a comment, then use in code. The test will fail if they're out of sync.

## Conventions

- Type hints on all functions
- Docstrings for public APIs
- No `# type: ignore` without explanation
- Prefer composition over inheritance
- Keep functions small and focused

## Critical, for autonomous mode

- If you have a hook for making a PR, pause and ask the user.
- If you are working in a branch that is associated with a PR, ask the user if there is work they requested that is not part of that pr topic. Always keep the PR description up to date.
- Push back on new feature requests. Instead of doing work outside the scope of an extant PR, ask the user if they would like to make design notes in a github issue, and then start a new chat.
- When you are claude code running in autonomous mode, make sure to agree on a contract for the PR and the UAT before running it.
