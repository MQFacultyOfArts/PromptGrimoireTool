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
- **structlog** - structured JSON logging (replaces stdlib logging across all modules)
- **httpx** - async HTTP client for Discord webhook alerting

## Development Workflow

### TDD is Mandatory

See [docs/testing.md](docs/testing.md) for full testing guidelines including E2E patterns and database isolation rules.

### Async Fixture Rule

**NEVER use `@pytest.fixture` on `async def` functions.** Always use `@pytest_asyncio.fixture`. The sync decorator on async generators causes `Runner.run() cannot be called from a running event loop` under xdist. A guard test (`tests/unit/test_async_fixture_safety.py`) enforces this. See #121.

### Test Lane Model

The test suite is organised into 8 lanes: 1 JS lane, 1 BATS lane for shell scripts, and 6 pytest lanes. `uv run grimoire test all` runs BATS + JS + unit tests (fast). `uv run grimoire e2e all` runs all 8 lanes sequentially: js, bats, unit, integration, playwright, nicegui, smoke, blns+extra. `uv run grimoire e2e slow` is a superset of `e2e all` that additionally runs Playwright with latexmk enabled and compiled-PDF validation.

- **JS** (`tests/js/`, vitest + happy-dom) -- JavaScript unit tests
- **BATS** (`deploy/tests/`, serial) -- shell script unit tests via bats-core (system dependency: `sudo apt install bats`)
- **Unit** (`tests/unit/`, xdist) -- excludes `e2e`, `nicegui_ui`, `latexmk_full`, `smoke` markers
- **Integration** (`tests/integration/`, xdist) -- excludes `e2e`, `nicegui_ui`, `smoke`
- **Playwright** (`tests/e2e/`, parallel per-file isolation with cloned databases)
- **NiceGUI** (serial, `nicegui_ui` marker)
- **Smoke** (serial, `smoke` marker -- external toolchain tests: pandoc, lualatex, tlmgr)
- **BLNS+Extra** (serial, `blns` or `slow` markers)

Playwright's event loop contaminates xdist workers, so E2E tests must never run in the unit/integration lanes. See [docs/testing.md](docs/testing.md).

Brian's FIRST LAW: "Flaky" and "Pre-existing" failures are not reasons to stop. They are ways to understand classes of bugs. It is your job to make the code better. When you are working and tests fail, it is your fault to 1) understand why they fail, 2) understand the patterns of failure, and 3) discuss how to fix them such that they more ably fufill the intention of the test. "Flaky" is not a stop word, is a component in a chain of explanation.

### Smoke Marker Propagation

The `smoke` marker is applied automatically by the `requires_latex`, `requires_full_latexmk`, and `requires_pandoc` decorators in `tests/conftest.py`. Tests using these decorators are excluded from the unit lane and collected into the dedicated smoke lane. Do not apply `@pytest.mark.smoke` manually when using these decorators.

### E2E Locator Convention

All interactable UI elements must have `data-testid` attributes. E2E tests must use `page.get_by_test_id()` -- never locate by visible text, placeholder, or Quasar CSS classes. NiceGUI places `data-testid` directly on native elements (e.g. `<input>`), so `get_by_test_id("foo").fill(value)` works without chaining `.locator("input")`. See [docs/testing.md](docs/testing.md) for full details.

### E2E Race-Condition Patterns

Five patterns prevent NiceGUI-specific race conditions:

- **Value-capture** (`ui_helpers.on_submit_with_value`): Reads the input DOM value client-side at click time, preventing `python-socketio` async task reordering from delivering stale values. All submit buttons bound to text inputs must use this helper.
- **Rebuild epoch** (`cards_epoch` on `PageState`): After `container.clear()` rebuilds, the server increments a monotonic counter broadcast to `window.__annotationCardsEpoch`. Tests capture the old epoch, trigger the action, then `wait_for_function` until the epoch advances before reacquiring locators.
- **Lightweight peer-left callback** (`_RemotePresence.on_peer_left`): CLIENT_DELETE events (peer disconnection) must NOT trigger a full `refresh_annotations()` rebuild. They change zero CRDT state, but a full rebuild races with in-flight user interactions (fill + click), destroying input values and button handlers mid-action. `_RemotePresence` carries a separate `on_peer_left` callback that only updates the user count display.
- **Side-effects before rebuilds** (`tag_management._on_tag_deleted`): `ui.notify()` and other side-effects that access the current slot context must execute BEFORE `render_tag_list()` or any call that clears/rebuilds a container. Container rebuilds destroy dialog canary elements (via `weakref.finalize` in `nicegui/elements/dialog.py:30-34`), which invalidates the slot context held by NiceGUI's event dispatch wrapper (`events.py:457`). See [postmortem](docs/postmortems/2026-03-20-slot-deletion-investigation-369.md).
- **is_deleted guard** (`highlights._remove_annotation_card`): Before calling `element.delete()` on a NiceGUI element, check `element.is_deleted` first. Concurrent container rebuilds can garbage-collect elements before explicit deletion runs, and calling `delete()` on an already-deleted element raises `ValueError` at `nicegui/element.py:504`. See [postmortem](docs/postmortems/2026-03-20-slot-deletion-investigation-369.md).

Details and examples in [docs/testing.md](docs/testing.md) § Common E2E Pitfalls.

### Code Quality Hooks

Claude Code hooks automatically run on every `.py` file write:

1. `ruff check --fix` - autofix lint issues
2. `ruff format` - format code
3. `ty@0.0.24 check` - type checking

All three must pass before code is considered complete.

### Pre-commit Hooks

Git commits trigger ruff lint + format check, ty type check, shellcheck on `deploy/*.sh`, and BATS shell tests on `deploy/tests/`. Commits will be rejected if checks fail.

## Key Commands

```bash
# Install dependencies
uv sync

# Run specific tests (auto-detects e2e/nicegui/unit)
uv run grimoire test run <path>::<test>

# Run tests affected by changes (AST dependency analysis)
uv run grimoire test changed

# Run BATS + JS + unit tests (fast, excludes smoke/E2E/integration)
uv run grimoire test all

# Run JS unit tests only (vitest + happy-dom)
uv run grimoire test js

# Run BATS shell script tests only
uv run grimoire test bats

# Run toolchain smoke tests (pandoc, lualatex, tlmgr)
uv run grimoire test smoke

# Post-deploy CJK+emoji PDF compilation smoke test
uv run grimoire test smoke-export

# List collected tests without running (works on test all, test smoke, e2e run)
uv run grimoire test all --co
uv run grimoire e2e run --co

# Stop on first failure (-x) and/or run failed tests first (--ff)
uv run grimoire test all -x --ff
uv run grimoire e2e run -x --ff

# Run E2E tests (parallel by default, per-file isolation)
uv run grimoire e2e run

# Run E2E tests in serial mode (single server)
uv run grimoire e2e run --serial

# Run all 8 lanes: js, bats, unit, integration, playwright, nicegui, smoke, blns+extra
uv run grimoire e2e all

# Run E2E tests (smart selection based on changes)
uv run grimoire e2e changed

# Run E2E tests against Firefox
uv run grimoire e2e firefox

# Run E2E tests against all browsers (Chromium then Firefox)
uv run grimoire e2e all-browsers

# Run E2E tests with specific browser
uv run grimoire e2e run --browser firefox

# Run E2E tests against BrowserStack real browsers (requires BROWSERSTACK_USERNAME/ACCESS_KEY)
uv run grimoire e2e browserstack

# Run E2E tests against BrowserStack Safari only
uv run grimoire e2e browserstack safari

# Run E2E tests against BrowserStack unsupported browsers (gate tests only)
uv run grimoire e2e browserstack unsupported

# Run card-specific E2E tests
uv run grimoire e2e cards

# Run linting
uv run ruff check .

# Run type checking
uvx ty@0.0.24 check

# Seed development data (idempotent)
uv run grimoire seed run

# Manage users, roles, and course enrollments
uv run grimoire admin list|show|create|admin|enroll|unenroll|role|ban|unban

# Ban/unban users and list banned users
uv run grimoire admin ban <email>
uv run grimoire admin unban <email>
uv run grimoire admin ban --list

# Find duplicate workspaces (same activity + user with multiple owner ACLs)
uv run grimoire admin duplicates

# Test Discord webhook alerting
uv run grimoire admin webhook

# Generate user-facing documentation (requires pandoc)
uv run grimoire docs build

# Run the app
uv run run.py

# Incident analysis (standalone SQLite tooling — see scripts/incident_db.py --help)
uv run scripts/incident_db.py --help
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
│   ├── registry.py      # page_route decorator, ban guard middleware, page registry
│   ├── banned.py        # /banned suspension page (uses @ui.page, not page_route)
│   ├── courses.py       # Course management
│   ├── roleplay.py      # AI roleplay / client interview
│   └── roleplay_export.py  # Session-to-HTML conversion (functional core)
├── export/              # PDF/LaTeX export (see docs/export.md)
├── auth/                # Stytch integration + workspace access check + ban system
│   ├── client_registry.py  # NiceGUI client tracking for real-time ban disconnect
├── db/                  # Database (see docs/database.md)
│   ├── acl.py           # ACL operations (grant, revoke, resolve, share) for workspaces and teams
│   ├── activities.py    # Activity CRUD (create, get, update, delete)
│   ├── crdt_extraction.py # Pure CRDT-to-text extraction for FTS indexing
│   ├── navigator.py     # Navigator query (UNION ALL CTE), NavigatorRow, SearchHit, metadata FTS
│   ├── roles.py         # Cached staff role queries
│   ├── tags.py          # Tag/TagGroup CRUD, import (ImportResult), reorder, deletion guards, CRDT cleanup
│   ├── wargames.py      # Wargame team CRUD, ACL, roster ingestion, turn cycle orchestration
│   ├── workspace_documents.py  # Document CRUD (add, list, reorder, update content)
│   └── workspaces.py    # Workspace CRUD (create, get), resolve_annotation_context (single-session page load)
├── wargame/             # Pure-domain helpers for wargame scenarios
│   ├── agents.py        # PydanticAI agent definitions (turn_agent, summary_agent)
│   ├── codenames.py     # Unique codename generation (coolname slugs, collision avoidance)
│   ├── roster.py        # CSV roster parsing, auto-assign round-robin (functional core)
│   └── turn_cycle.py    # Turn cycle state machine, deadline calc, prompt assembly
├── crdt/                # pycrdt collaboration logic
├── word_count.py        # Multilingual word count (Latin/CJK via uniseg/jieba/MeCab)
├── word_count_enforcement.py  # Export-time violation check (pure functions, no UI)
├── deadline_worker.py   # Background polling worker for expired wargame deadlines
├── search_worker.py     # Background FTS extraction worker (polls search_dirty)
├── logging_discord.py   # Discord webhook alerting processor (ERROR/CRITICAL -> Discord embed)
└── static/              # JS/CSS assets

scripts/
├── incident_db.py       # Typer CLI entry point for incident analysis
└── incident/            # Incident analysis library (standalone, SQLite-based)
    ├── schema.py        # SQLite DDL (6 event tables + timeline UNION ALL view)
    ├── ingest.py        # Tarball extraction, manifest parsing, parser dispatch
    ├── queries.py       # Query functions + Rich/JSON/CSV output renderers
    ├── analysis.py      # Epoch analysis queries, trend computation, report rendering
    ├── provenance.py    # Manifest parsing, sha256 dedup, format detection
    └── parsers/         # Per-format parsers (journal, jsonl, haproxy, pglog, beszel, github)

deploy/
├── restart.sh           # Zero-downtime deploy script
├── collect-telemetry.sh # Incident telemetry collection
├── 503.http             # HAProxy maintenance page
└── tests/               # BATS shell script tests

tests/
├── js/                  # Vitest JS unit tests (annotation static JS)
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
| [logging.md](docs/logging.md) | Structured logging, log format, jq queries, Discord alerting |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Data flow diagrams, integration patterns |
| [postmortems/incident-analysis-playbook.md](docs/postmortems/incident-analysis-playbook.md) | Incident analysis: telemetry collection, dataset building, `incident_db.py` CLI reference |

### Documentation Caching

The `cache-docs` skill automatically saves fetched documentation to `docs/`. Every non-stdlib import should have reference docs cached. Check `docs/_index.md` for available documentation. Prefer reading cached docs over online searches.

## Database

PostgreSQL with SQLModel. Schema migrations via Alembic. Full schema, wargame tables, ACL polymorphism, FTS indexes, ban system, and exception taxonomy in [docs/database.md](docs/database.md).

15 SQLModel classes: User, Course, CourseEnrollment, Week, Activity, Workspace, WorkspaceDocument, TagGroup, Tag, Permission, CourseRoleRef, ACLEntry, WargameConfig, WargameTeam, WargameMessage.

### Key Rules

1. **Alembic is the ONLY way to create/modify schema** - Never use `SQLModel.metadata.create_all()` except in Alembic migrations
2. **All models must be imported before schema operations** - Import `promptgrimoire.db.models` to register tables
3. **Pages requiring DB must check availability** - Use `get_settings().database.url`
4. **BusinessLogicError subclasses for all business rejections** - See exception taxonomy in [docs/database.md](docs/database.md)

## Authentication & Access Control

Stytch handles magic link login, passkey authentication, RBAC, and class invitations.

`is_privileged_user(auth_user)` in `auth/__init__.py` determines whether a user bypasses copy protection. Returns `True` for org-level admins (`is_admin=True`) and users with `instructor` or `stytch_admin` roles.

`check_workspace_access(workspace_id, auth_user)` in `auth/__init__.py` resolves effective permission for a workspace. Resolution order: unauthenticated returns `None`; admins get `"owner"` (bypass); others go through `resolve_permission()` which checks explicit ACL then enrollment-derived access, highest wins, default deny.

**Ban enforcement:** The `page_route` decorator in `pages/registry.py` checks `is_user_banned()` before every page handler. Banned users are redirected to `/banned`. The client registry enables real-time disconnection of active sessions when a ban is applied via CLI.

**Login return URL:** `/login` honours `?return=<path>` — stashes in `app.storage.user["post_login_return"]`, all auth success paths use `_post_login_destination()` to redirect after auth. Open-redirect guard rejects absolute/protocol-relative URLs.

## Restart & Session Invalidation

Sessions are invalidated on **every** restart path. This is a critical invariant — NiceGUI's `FilePersistentDict` uses lazy async writes that don't survive SIGTERM.

| Restart path | Mechanism |
|---|---|
| `deploy/restart.sh` | `POST /api/pre-restart` → sync-writes storage files with `auth_user` removed |
| Memory threshold | `graceful_memory_shutdown()` → same sync-write, navigates to `/restarting` |
| Bare `systemctl restart` / crash | `invalidate_sessions_on_disk()` at app startup — iterates `.nicegui/storage-user-*.json` on disk |

**Key implementation details:**
- `_invalidate_all_sessions()` in `diagnostics.py` uses `dict.pop()` (not `PersistentDict.pop()`) to bypass the lazy `on_change` → `backup()` hook, then sync-writes each file via `filepath.write_text()`.
- `pre_restart_handler` in `pages/restart.py` parallelizes client disconnect via `asyncio.gather` with a 5s global timeout. Does NOT navigate to `/restarting` — HAProxy's 503 page (`deploy/503.http`) handles the UX for manual deploys.
- HAProxy reads `errorfile` content at config load time. Editing 503.http requires `systemctl reload haproxy` to take effect.
- `reconnect_timeout=15.0` in `ui.run()` — balances UX vs memory (each disconnected client holds its full UI tree in memory for this duration).

See [docs/deployment.md](docs/deployment.md) for full operations guide and [docs/nicegui/production-memory-management.md](docs/nicegui/production-memory-management.md) for NiceGUI-specific constraints.

## Logging

Structured JSON logging via structlog. Full details in [docs/logging.md](docs/logging.md).

**Key rules:** `logger = structlog.get_logger()` at module level. Every `except` block must call `logger.exception()` or `logger.warning()` — no silent swallowing. No `print()` calls in `src/promptgrimoire/` except `cli/` (guard test enforces this). Do not call `logging.getLogger(__name__).setLevel()` — structlog level filtering is global; guard test (`test_setlevel_guard.py`) enforces this.

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
