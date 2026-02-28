# PromptGrimoire - Claude Code Instructions

## Project Overview

PromptGrimoire is a collaborative "classroom grimoire" for prompt iteration, annotation, and sharing in educational contexts. Based on the pedagogical framework from "Teaching the Unknown" (Ballsun-Stanton & Torrington, 2025).

**Target:** Session 1 2026 (Feb 27)

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

E2E tests (Playwright) are excluded from `test-all` (`-m "not e2e"`) because Playwright's event loop contaminates xdist workers. E2E tests must run separately via `uv run test-e2e`, which runs in serial fail-fast mode by default (`--parallel` for xdist). See [docs/testing.md](docs/testing.md).

### E2E Locator Convention

All interactable UI elements must have `data-testid` attributes. E2E tests must use `page.get_by_test_id()` -- never locate by visible text, placeholder, or Quasar CSS classes. NiceGUI places `data-testid` directly on native elements (e.g. `<input>`), so `get_by_test_id("foo").fill(value)` works without chaining `.locator("input")`. See [docs/testing.md](docs/testing.md) for full details.

### Code Quality Hooks

Claude Code hooks automatically run on every `.py` file write:

1. `ruff check --fix` - autofix lint issues
2. `ruff format` - format code
3. `ty check` - type checking

All three must pass before code is considered complete.

### Pre-commit Hooks

Git commits trigger ruff lint + format check and ty type check. Commits will be rejected if checks fail.

## Key Commands

```bash
# Install dependencies
uv sync

# Run tests (smart selection based on changes - fast)
uv run test-changed

# Run all tests (unit + integration, excludes E2E)
uv run test-all

# Run E2E tests (starts server, serial fail-fast by default)
uv run test-e2e

# Run E2E tests in parallel (xdist)
uv run test-e2e --parallel

# Run E2E tests (smart selection based on changes)
uv run test-e2e-changed

# Run linting
uv run ruff check .

# Run type checking
uvx ty check

# Seed development data (idempotent)
uv run seed-data

# Manage users, roles, and course enrollments
uv run manage-users list|show|create|admin|enroll|unenroll|role

# Generate user-facing documentation (requires rodney, showboat, pandoc)
uv run make-docs

# Run the app
uv run python -m promptgrimoire

```

## Project Structure

```text
src/promptgrimoire/
├── models/              # Data models (Character, Session, Turn, LorebookEntry)
├── parsers/             # SillyTavern character card parser
├── llm/                 # Claude API client, lorebook activation, prompt assembly
├── input_pipeline/      # HTML input processing (see docs/input-pipeline.md)
├── pages/               # NiceGUI page routes
│   ├── annotation/      # Main annotation page (see docs/annotation-architecture.md)
│   ├── navigator/       # Workspace navigator (route: /, see docs/database.md § Navigator)
│   ├── courses.py       # Course management
│   └── roleplay.py      # AI roleplay / client interview
├── export/              # PDF/LaTeX export (see docs/export.md)
├── auth/                # Stytch integration + workspace access check
├── db/                  # Database (see docs/database.md)
│   ├── acl.py           # ACL operations (grant, revoke, resolve, share)
│   ├── crdt_extraction.py # Pure CRDT-to-text extraction for FTS indexing
│   ├── navigator.py     # Navigator query (UNION ALL CTE), NavigatorRow, SearchHit
│   ├── roles.py         # Cached staff role queries
│   └── tags.py          # Tag/TagGroup CRUD, import, reorder, CRDT cleanup
├── crdt/                # pycrdt collaboration logic
├── search_worker.py     # Background FTS extraction worker (polls search_dirty)
└── static/              # JS/CSS assets

tests/
├── unit/                # Unit tests
├── integration/         # Integration tests
└── e2e/                 # Playwright E2E tests (excluded from test-all)
```

## Documentation

Detailed subsystem docs live in `docs/`. Key references:

| Doc | Contents |
|-----|----------|
| [database.md](docs/database.md) | Schema, tables, hierarchy, workspace architecture, cloning, bootstrap, rules |
| [testing.md](docs/testing.md) | Test guidelines, E2E patterns, DB isolation, fixture analysis |
| [export.md](docs/export.md) | PDF/LaTeX pipeline, TinyTeX setup, highlight pipeline |
| [input-pipeline.md](docs/input-pipeline.md) | HTML input processing, CSS Highlight API |
| [annotation-architecture.md](docs/annotation-architecture.md) | Annotation page package structure, import ordering |
| [configuration.md](docs/configuration.md) | pydantic-settings, env vars, sub-models |
| [copy-protection.md](docs/copy-protection.md) | Resolution chain, client-side enforcement, UI controls |
| [e2e-debugging.md](docs/e2e-debugging.md) | E2E infrastructure, NiceGUI task leaks, cleanup endpoint |
| [nicegui/lifecycle.md](docs/nicegui/lifecycle.md) | NiceGUI client lifecycle, on_disconnect vs on_delete |
| [worktrees.md](docs/worktrees.md) | Git worktree setup, Serena memory management |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Data flow diagrams, integration patterns |
| [rodney/cli-reference.md](docs/rodney/cli-reference.md) | Rodney browser automation CLI (used by make-docs) |

### Documentation Caching

The `cache-docs` skill automatically saves fetched documentation to `docs/`. Every non-stdlib import should have reference docs cached. Check `docs/_index.md` for available documentation. Prefer reading cached docs over online searches.

## Database

PostgreSQL with SQLModel. Schema migrations via Alembic. Full schema and design decisions in [docs/database.md](docs/database.md).

12 SQLModel classes: User, Course, CourseEnrollment, Week, Activity, Workspace, WorkspaceDocument, TagGroup, Tag, Permission, CourseRoleRef, ACLEntry.

### Full-Text Search (FTS)

`workspace.search_text` stores materialised CRDT content (highlights, tags, comments, notes) for FTS. `workspace.search_dirty` is a boolean queue flag set on every CRDT save, cleared by the background `search_worker`. Two GIN expression indexes (`idx_workspace_document_fts`, `idx_workspace_search_text_fts`) power `search_navigator()` in `db/navigator.py`. See [docs/database.md](docs/database.md) for index naming convention.

### Key Rules

1. **Alembic is the ONLY way to create/modify schema** - Never use `SQLModel.metadata.create_all()` except in Alembic migrations
2. **All models must be imported before schema operations** - Import `promptgrimoire.db.models` to register tables
3. **Pages requiring DB must check availability** - Use `get_settings().database.url`

## Authentication & Access Control

Stytch handles magic link login, passkey authentication, RBAC, and class invitations.

`is_privileged_user(auth_user)` in `auth/__init__.py` determines whether a user bypasses copy protection. Returns `True` for org-level admins (`is_admin=True`) and users with `instructor` or `stytch_admin` roles.

`check_workspace_access(workspace_id, auth_user)` in `auth/__init__.py` resolves effective permission for a workspace. Resolution order: unauthenticated returns `None`; admins get `"owner"` (bypass); others go through `resolve_permission()` which checks explicit ACL then enrollment-derived access, highest wins, default deny.

## Conventions

- Type hints on all functions
- Docstrings for public APIs
- No `# type: ignore` without explanation
- Prefer composition over inheritance
- Keep functions small and focused
- **Terminology: "Unit" not "Course"** — Australian universities use "unit" for what other systems call "course". All user-facing UI text must say "Unit" (e.g. "Unit Settings", "New Unit", "Inherit from unit"). Code identifiers (`course`, `course_id`), URL paths (`/courses/`), and model/table names remain unchanged.

## Critical, for autonomous mode

- If you have a hook for making a PR, pause and ask the user.
- If you are working in a branch that is associated with a PR, ask the user if there is work they requested that is not part of that pr topic. Always keep the PR description up to date.
- Push back on new feature requests. Instead of doing work outside the scope of an extant PR, ask the user if they would like to make design notes in a github issue, and then start a new chat.
- When you are claude code running in autonomous mode, make sure to agree on a contract for the PR and the UAT before running it.
