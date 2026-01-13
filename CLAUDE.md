# PromptGrimoire - Claude Code Instructions

## Project Overview

PromptGrimoire is a collaborative "classroom grimoire" for prompt iteration, annotation, and sharing in educational contexts. Based on the pedagogical framework from "Teaching the Unknown" (Ballsun-Stanton & Torrington, 2025).

**Target:** Session 1 2025 (Feb 23)

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

```
src/promptgrimoire/
├── __init__.py
├── main.py           # NiceGUI app entry
├── models/           # SQLModel definitions
├── parsers/          # Conversation format parsers
├── auth/             # Stytch integration
└── crdt/             # pycrdt collaboration logic

tests/
├── conftest.py       # Shared fixtures
├── unit/             # Unit tests
├── integration/      # Integration tests
└── e2e/              # Playwright E2E tests

docs/                 # Cached documentation (auto-populated)
```

## Documentation Caching

The `cache-docs` skill automatically saves fetched documentation to `docs/`. Every non-stdlib import should have reference docs cached. Check `docs/_index.md` for available documentation.

## Database

PostgreSQL with SQLModel. Schema migrations via Alembic (to be configured).

Key entities: User, Class, Conversation, Turn, Annotation, Tag, Comment

## Authentication

Stytch handles:

- Magic link login
- Passkey authentication
- RBAC (admin/instructor/student roles)
- Class invitations

## Conventions

- Type hints on all functions
- Docstrings for public APIs
- No `# type: ignore` without explanation
- Prefer composition over inheritance
- Keep functions small and focused
