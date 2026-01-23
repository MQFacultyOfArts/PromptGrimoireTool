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

Tests must simulate real user behavior through Playwright events, not bypass the UI with JavaScript injection like `page.evaluate()` or `ui.run_javascript()`.

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

# Run E2E tests
uv run playwright test
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

## Database

PostgreSQL with SQLModel. Schema migrations via Alembic (to be configured).

Key entities: User, Class, Conversation, Turn, Annotation, Tag, Comment

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
