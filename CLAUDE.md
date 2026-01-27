# PromptGrimoire - Claude Code Instructions

## Project Overview

PromptGrimoire is a collaborative "classroom grimoire" for prompt iteration, annotation, and sharing in educational contexts. Based on the pedagogical framework from "Teaching the Unknown" (Ballsun-Stanton & Torrington, 2025).

**Target:** Session 1 2025 (Feb 23)

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

## Development Workflow

### TDD is Mandatory

1. Write failing test first
2. Write minimal code to pass
3. Refactor
4. Repeat

No feature code without corresponding tests. Playwright for E2E, pytest for unit/integration.

### E2E Test Guidelines

**NEVER inject JavaScript in E2E tests.** Use Playwright's native APIs exclusively:

- **Text selection**: Use `page.mouse` to drag-select (move, down, move, up)
- **Keyboard input**: Use `page.keyboard.press()` or `locator.press()`
- **Clicks**: Use `locator.click()` with modifiers if needed
- **Assertions**: Use `expect()` from `playwright.sync_api`
- **Scroll into view**: Use `locator.scroll_into_view_if_needed()` before interacting with elements that may be off-screen

Tests must simulate real user behavior through Playwright events, not bypass the UI with JavaScript injection like `page.evaluate()` or `ui.run_javascript()`.

**Common E2E pitfalls:**

- Elements may be off-screen in headless mode - always scroll into view before assertions
- NiceGUI pages may need time to hydrate - use `expect().to_be_visible()` with appropriate timeouts
- Floating menus/popups often require scroll context to position correctly
- **Annotation cards are scroll-sensitive** - they won't display if their anchor element is not visible; always `scroll_into_view_if_needed()` before selecting text for annotation

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

# Run tests
uv run pytest

# Run linting
uv run ruff check .

# Run type checking
uvx ty check

# Run the app
uv run python -m promptgrimoire

# Find first failing test
uv run test-debug
```

## Project Structure

```text
src/promptgrimoire/
├── __init__.py
├── main.py           # NiceGUI app entry
├── models/           # Data models (Character, Session, Turn, LorebookEntry)
├── parsers/          # SillyTavern character card parser
├── llm/              # Claude API client, lorebook activation, prompt assembly
├── pages/            # NiceGUI page routes (/roleplay, /logs, /auth, etc.)
├── auth/             # Stytch integration
└── crdt/             # pycrdt collaboration logic

tests/
├── conftest.py       # Shared fixtures
├── fixtures/         # Test data (Becky Bennett character card)
├── unit/             # Unit tests
├── integration/      # Integration tests
└── e2e/              # Playwright E2E tests

docs/                 # Cached documentation (auto-populated)
logs/sessions/        # JSONL session logs (auto-created)
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
- `marginnote` - margin annotations
- `latexmk` - build automation

### Configuration

The `LATEXMK_PATH` env var overrides the default TinyTeX path if needed. Leave empty to use TinyTeX.

### Architecture

- `src/promptgrimoire/export/pdf.py` - `get_latexmk_path()` resolves latexmk location
- `scripts/setup_latex.py` - installs TinyTeX and packages
- Does NOT fall back to system PATH - TinyTeX only for consistency

## Database

PostgreSQL with SQLModel. Schema migrations via Alembic.

### Tables (6 SQLModel classes)

- **User** - Stytch-linked user accounts
- **Class** - Student enrollment containers
- **Conversation** - Imported conversations for annotation
- **Highlight** - Annotated passages in case documents
- **HighlightComment** - Comment threads on highlights
- **AnnotationDocumentState** - Persisted CRDT state

### Database Rules

1. **Alembic is the ONLY way to create/modify schema** - Never use `SQLModel.metadata.create_all()` except in Alembic migrations themselves
2. **All models must be imported before schema operations** - The `promptgrimoire.db.models` module must be imported to register tables with SQLModel.metadata
3. **Pages requiring DB must check availability** - Use `os.environ.get("DATABASE_URL")` and show a helpful error if not configured
4. **Use `verify_schema()` at startup** - Fail fast if tables are missing

### Page Database Dependencies

| Page | Route | DB Required |
|------|-------|-------------|
| case_tool | `/case-tool` | **Yes** |
| live_annotation_demo | `/demo/live-annotation` | Optional |
| roleplay | `/roleplay` | No |
| logs | `/logs` | No |
| auth | `/login`, `/logout` | Optional |

## Testing Rules

### Database Test Isolation

1. **UUID-based isolation is MANDATORY** - All test data must use unique identifiers (uuid4) to prevent collisions
2. **NEVER use `drop_all()` or `truncate`** - These break parallel test execution (pytest-xdist)
3. **NEVER use `create_all()` in tests** - Schema comes from Alembic migrations run once at session start
4. **Tests must be parallel-safe** - Assume pytest-xdist; tests may run concurrently

### Test Database Configuration

1. **Use `TEST_DATABASE_URL`** - Tests set `DATABASE_URL` from `TEST_DATABASE_URL` for isolation
2. **Schema is set up ONCE per test session** - `db_schema_guard` runs migrations before any tests
3. **Each test owns its data** - Create with UUIDs, don't rely on cleanup between tests

## Authentication

Stytch handles:

- Magic link login
- Passkey authentication
- RBAC (admin/instructor/student roles)
- Class invitations

## Environment Variables

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
