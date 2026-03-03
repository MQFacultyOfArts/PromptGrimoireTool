# AI Agent Guidelines for PromptGrimoireTool

> **For**: AI assistants (Gemini CLI, Cursor, GitHub Copilot, Codex, Claude Code, etc.) working on the PromptGrimoireTool codebase.

## Project Context
PromptGrimoire is a collaborative "classroom grimoire" for prompt iteration, annotation, and sharing in educational contexts.

- **Tech Stack**: Python 3.14, NiceGUI, SQLModel (Pydantic + SQLAlchemy), PostgreSQL, pycrdt (real-time collaboration), Stytch (auth).
- **Terminology**: Use "Unit" instead of "Course" in all user-facing UI text (Australian university standard). Code identifiers remain `course_id`, `/courses/`, etc.

## Core Rules & Guardrails

### 1. Database & Schema Operations
- **Alembic Only**: Alembic is the ONLY way to create or modify schema. Never use `SQLModel.metadata.create_all()` except within Alembic migrations.
- **Import Requirement**: All models must be imported (`import promptgrimoire.db.models`) before executing schema operations to ensure table registration.
- **Availability**: Pages requiring DB access must check `get_settings().database.url` before proceeding.

### 2. Testing Constraints (TDD Mandatory)
- **Async Fixtures**: NEVER use `@pytest.fixture` on `async def` functions. Always use `@pytest_asyncio.fixture`. Using the sync decorator causes `Runner.run() cannot be called from a running event loop` under xdist.
- **E2E Isolation**: E2E tests (Playwright) contaminate xdist workers. They are excluded from `test-all`. They must run separately via `uv run grimoire e2e run`.
- **E2E Locators**: All interactable UI elements must have `data-testid` attributes. E2E tests must use `page.get_by_test_id()`. Never locate by visible text, placeholder, or Quasar CSS classes.

### 3. Code Quality & Formatting
- All functions require type hints.
- Public APIs require docstrings.
- Do not use `# type: ignore` without explicit explanation.
- **Verification**: Code is not complete until `ruff check`, `ruff format`, and `ty check` all pass.

## Key Commands

Use these commands for verification and execution:

```bash
# Testing
uv run grimoire test changed           # Fast unit/integration tests based on git diff
uv run grimoire test all                # All tests EXCEPT E2E
uv run grimoire test all -k "pattern"   # Filter tests by keyword expression
uv run grimoire e2e run                 # E2E tests (serial, starts server)
uv run grimoire e2e run -k "pattern"    # E2E tests filtered by keyword
uv run grimoire e2e run --parallel      # E2E tests in parallel (xdist)
uv run grimoire e2e changed             # Smart selection E2E tests

# Code Quality
uv run ruff check .         # Linting
uv run ruff format .        # Formatting
uvx ty check                # Type checking

# Execution & Data
uv run grimoire seed run            # Idempotent development data seeding
uv run grimoire admin list|show|create|admin|enroll|unenroll|role  # User management
uv run grimoire docs build          # Generate user-facing documentation (requires pandoc)
uv run run.py                       # Run the application
```

## Autonomous Agent Guidelines

When operating autonomously (e.g., executing implementation plans, working on PRs):

1. **Scope Protection**: Push back on new feature requests that fall outside the current issue or PR scope. Ask the user to make design notes in a GitHub issue and start a new chat session instead.
2. **PR Management**: If working on a branch associated with a PR, always keep the PR description up to date. Before creating a PR automatically, pause and ask the user for confirmation.
3. **UAT Contracts**: Before marking an implementation plan or feature as complete, you must agree on a contract for the PR and User Acceptance Testing (UAT).
4. **Documentation Caching**: Prefer reading cached docs in `docs/` over running web searches.

## Architecture References
Before modifying core systems, reference the detailed documentation in the `docs/` folder:
- Schema & Persistence: `docs/database.md`
- Collaboration (CRDT): `docs/ARCHITECTURE.md`
- Web UI & Routing: `docs/annotation-architecture.md`
- Export Pipeline: `docs/export.md`
- Testing: `docs/testing.md`
