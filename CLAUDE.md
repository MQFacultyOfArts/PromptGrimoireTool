# PromptGrimoire - Claude Code Instructions

## Project Overview

PromptGrimoire is a collaborative "classroom grimoire" for prompt iteration, annotation, and sharing in educational contexts. Based on the pedagogical framework from "Teaching the Unknown" (Ballsun-Stanton & Torrington, 2025).

**Status:** Session 1 2026, Week 1 starts 3 Mar. Deployed at `grimoire.drbbs.org`.

## Use Cases

### 1. Prompt Annotation & Sharing (Core)

Collaborative annotation of AI conversations for teaching prompt engineering. Students and instructors can highlight, comment on, and tag conversation turns.

### 2. Legal Client Interview Simulation (Spike 4)

Import SillyTavern character cards to run AI-powered roleplay scenarios. Initial use case: tort law training where students interview a simulated client (Becky Bennett workplace injury case).

- **Input**: SillyTavern chara_card_v3 JSON with embedded lorebook (bundled Becky Bennett card auto-loads)
- **Features**: Keyword-triggered context injection, empathy-based trust mechanics
- **Output**: Export to annotation workspace (`ai_conversation` document type) or JSONL chat log

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
- **mammoth** - DOCX to semantic HTML conversion (file upload)
- **pymupdf4llm** - PDF to Markdown extraction with layout analysis (file upload)
- **lxml** - HTML normalisation in export pipeline
- **PydanticAI** - structured LLM output for wargame agents (turn_agent, summary_agent)
- **APScheduler** - deadline scheduling with SQLAlchemyJobStore (wargame turn cycle)

## Development Workflow

### TDD is Mandatory

See [docs/testing.md](docs/testing.md) for full testing guidelines including E2E patterns and database isolation rules.

### Async Fixture Rule

**NEVER use `@pytest.fixture` on `async def` functions.** Always use `@pytest_asyncio.fixture`. The sync decorator on async generators causes `Runner.run() cannot be called from a running event loop` under xdist. A guard test (`tests/unit/test_async_fixture_safety.py`) enforces this. See #121.

### E2E Test Isolation

E2E tests (Playwright) are excluded from `test-all` (`-m "not e2e"`) because Playwright's event loop contaminates xdist workers. E2E tests must run separately via `uv run grimoire e2e run`, which runs in parallel by default (per-file isolation with cloned databases, `--serial` for single server). See [docs/testing.md](docs/testing.md).

### E2E Locator Convention

All interactable UI elements must have `data-testid` attributes. E2E tests must use `page.get_by_test_id()` -- never locate by visible text, placeholder, or Quasar CSS classes. NiceGUI places `data-testid` directly on native elements (e.g. `<input>`), so `get_by_test_id("foo").fill(value)` works without chaining `.locator("input")`. See [docs/testing.md](docs/testing.md) for full details.

### E2E Race-Condition Patterns

Three patterns prevent NiceGUI-specific race conditions:

- **Value-capture** (`ui_helpers.on_submit_with_value`): Reads the input DOM value client-side at click time, preventing `python-socketio` async task reordering from delivering stale values. All submit buttons bound to text inputs must use this helper.
- **Rebuild epoch** (`cards_epoch` on `PageState`): After `container.clear()` rebuilds, the server increments a monotonic counter broadcast to `window.__annotationCardsEpoch`. Tests capture the old epoch, trigger the action, then `wait_for_function` until the epoch advances before reacquiring locators.
- **Lightweight peer-left callback** (`_RemotePresence.on_peer_left`): CLIENT_DELETE events (peer disconnection) must NOT trigger a full `refresh_annotations()` rebuild. They change zero CRDT state, but a full rebuild races with in-flight user interactions (fill + click), destroying input values and button handlers mid-action. `_RemotePresence` carries a separate `on_peer_left` callback that only updates the user count display.

Details and examples in [docs/testing.md](docs/testing.md) § Common E2E Pitfalls.

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

# Run specific tests (auto-detects e2e/nicegui/unit)
uv run grimoire test run <path>::<test>

# Run tests affected by changes (AST dependency analysis)
uv run grimoire test changed

# Run all tests (unit + integration, excludes E2E)
uv run grimoire test all

# Stop on first failure (-x) and/or run failed tests first (--ff)
uv run grimoire test all -x --ff
uv run grimoire e2e run -x --ff

# Run E2E tests (parallel by default, per-file isolation)
uv run grimoire e2e run

# Run E2E tests in serial mode (single server)
uv run grimoire e2e run --serial

# Run all lanes: unit tests + Playwright E2E + NiceGUI
uv run grimoire e2e all

# Run E2E tests (smart selection based on changes)
uv run grimoire e2e changed

# Run card-specific E2E tests
uv run grimoire e2e cards

# Run linting
uv run ruff check .

# Run type checking
uvx ty check

# Seed development data (idempotent)
uv run grimoire seed run

# Manage users, roles, and course enrollments
uv run grimoire admin list|show|create|admin|enroll|unenroll|role

# Generate user-facing documentation (requires pandoc)
uv run grimoire docs build

# Run the app
uv run run.py

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
│   ├── roleplay.py      # AI roleplay / client interview
│   └── roleplay_export.py  # Session-to-HTML conversion (functional core)
├── export/              # PDF/LaTeX export (see docs/export.md)
├── auth/                # Stytch integration + workspace access check
├── db/                  # Database (see docs/database.md)
│   ├── acl.py           # ACL operations (grant, revoke, resolve, share) for workspaces and teams
│   ├── activities.py    # Activity CRUD (create, get, update, delete)
│   ├── crdt_extraction.py # Pure CRDT-to-text extraction for FTS indexing
│   ├── navigator.py     # Navigator query (UNION ALL CTE), NavigatorRow, SearchHit
│   ├── roles.py         # Cached staff role queries
│   ├── tags.py          # Tag/TagGroup CRUD, import, reorder, CRDT cleanup
│   ├── wargames.py      # Wargame team CRUD, ACL (grant/revoke/update), roster ingestion
│   ├── workspace_documents.py  # Document CRUD (add, list, reorder, update content)
│   └── workspaces.py    # Workspace CRUD (create, get)
├── wargame/             # Pure-domain helpers for wargame scenarios
│   ├── agents.py        # PydanticAI agent definitions (turn_agent, summary_agent)
│   ├── codenames.py     # Unique codename generation (coolname slugs, collision avoidance)
│   ├── roster.py        # CSV roster parsing, auto-assign round-robin (functional core)
│   └── turn_cycle.py    # Turn cycle state machine, deadline calc, prompt assembly
├── crdt/                # pycrdt collaboration logic
├── word_count.py        # Multilingual word count (Latin/CJK via uniseg/jieba/MeCab)
├── word_count_enforcement.py  # Export-time violation check (pure functions, no UI)
├── scheduler.py         # APScheduler lifecycle and deadline job management
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

### Documentation Caching

The `cache-docs` skill automatically saves fetched documentation to `docs/`. Every non-stdlib import should have reference docs cached. Check `docs/_index.md` for available documentation. Prefer reading cached docs over online searches.

## Database

PostgreSQL with SQLModel. Schema migrations via Alembic. Full schema and design decisions in [docs/database.md](docs/database.md).

15 SQLModel classes: User, Course, CourseEnrollment, Week, Activity, Workspace, WorkspaceDocument, TagGroup, Tag, Permission, CourseRoleRef, ACLEntry, WargameConfig, WargameTeam, WargameMessage.

### Activity Type Discriminator

Activity has a `type` field (`"annotation"` or `"wargame"`) enforced by CHECK constraints. Annotation activities require `template_workspace_id`; wargame activities must not set it. Composite FK `(id, type)` lets child tables (WargameConfig, WargameTeam) enforce type-safe references via discriminator-enforcing foreign keys.

### Wargame Schema (Activity Extension)

Three new tables extend the Activity model for wargame scenarios:

- **WargameConfig** -- PK-as-FK one-to-one on Activity. Holds `system_prompt`, `scenario_bootstrap`, and exactly one timer mode (`timer_delta` XOR `timer_wall_clock`).
- **WargameTeam** -- Teams within a wargame activity. Codename unique per activity. Tracks `current_round`, `round_state`, `current_deadline`, `game_state_text`, `student_summary_text`.
- **WargameMessage** -- Per-team message log. Ordered by `sequence_no` (not timestamps). Supports in-place edits (`edited_at`, `thinking`, `metadata_json`).

### Permission `can_edit` Classifier

`Permission.can_edit` (boolean, default FALSE) marks which permission levels grant editorial capability. The wargame team ACL zero-editor invariant queries this flag directly instead of hardcoding permission-name lists. Seed data: `owner` and `editor` have `can_edit=TRUE`; `peer` and `viewer` have `can_edit=FALSE`.

### Wargame Team Management API

`db/wargames.py` provides the full team lifecycle: `create_team`, `create_teams`, `get_team`, `list_teams`, `rename_team`, `delete_team`. Team ACL: `grant_team_permission` (upsert), `revoke_team_permission`, `update_team_permission`, `remove_team_member`, `resolve_team_permission`, `list_team_members`. Roster ingestion: `ingest_roster` (atomic CSV import with two modes -- named-team and auto-assign).

**Zero-editor invariant:** `ZeroEditorError` is raised when a grant downgrade or revoke would leave a team with no `can_edit=TRUE` member. Enforced via `SELECT FOR UPDATE` row locking.

**Roster ingestion modes:** Named-team mode uses explicit team names from CSV. Auto-assign mode distributes members round-robin across `team_count` buckets, mapping to real teams by `created_at` order. Re-imports are additive (existing ACL rows preserved, changed roles updated). Editor-first grant ordering prevents false zero-editor violations during handoff swaps.

Pure-domain helpers live in `wargame/` (codename generation, roster CSV parsing, auto-assign). DB orchestration lives in `db/wargames.py`.

### Wargame Turn Cycle Engine (Seam 3 — Designed, Not Yet Implemented)

`db/wargames.py` will be extended with turn cycle orchestration: `start_game()`, `lock_round()`, `run_preprocessing()`, `publish_all()`, `on_deadline_fired()`. These follow the existing functional core / imperative shell pattern — pure domain logic in `wargame/turn_cycle.py` and `wargame/agents.py`, DB orchestration in `db/wargames.py`.

**LLM pattern divergence:** Wargame uses PydanticAI agents (structured output validation) instead of the direct `ClaudeClient` used for roleplay. Two agents: `turn_agent` (draft response + game state artifact) and `summary_agent` (student-facing summaries). Both use `anthropic:claude-sonnet-4-5`.

**Schema additions (planned):** `WargameTeam.move_buffer_crdt` and `WargameTeam.notes_crdt` (bytea), `WargameConfig.summary_system_prompt` (Text). See design plan: `docs/design-plans/2026-03-10-turn-cycle-296.md`.

### ACL Target Polymorphism

ACLEntry supports two target types: `workspace_id` or `team_id`. Exactly one must be set (enforced by CHECK constraint `ck_acl_entry_exactly_one_target` and model validator). Partial unique indexes enforce `(workspace_id, user_id)` and `(team_id, user_id)` uniqueness independently. ACL queries filter on `workspace_id IS NOT NULL` to avoid NULL poisoning from team-target rows.

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
- **PEP 758 (Python 3.14): `except` without parentheses** — `except ValueError, KeyError:` is **valid Python 3.14 syntax** that catches both exception types. This is NOT the old Python 2 `except X, e:` pattern. Do NOT "fix" this to `except (ValueError, KeyError):` — both forms are correct, the unparenthesised form is preferred for consistency with 3.14 idioms.

## Critical, for autonomous mode

- If you have a hook for making a PR, pause and ask the user.
- If you are working in a branch that is associated with a PR, ask the user if there is work they requested that is not part of that pr topic. Always keep the PR description up to date.
- Push back on new feature requests. Instead of doing work outside the scope of an extant PR, ask the user if they would like to make design notes in a github issue, and then start a new chat.
- When you are claude code running in autonomous mode, make sure to agree on a contract for the PR and the UAT before running it.
