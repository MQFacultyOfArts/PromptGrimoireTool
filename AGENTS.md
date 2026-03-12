# AI Agent Guidelines for PromptGrimoireTool

> **For**: AI assistants (Gemini CLI, Cursor, GitHub Copilot, Codex, Claude Code, etc.) working on the PromptGrimoireTool codebase.

## Project Context
PromptGrimoire is a collaborative "classroom grimoire" for prompt iteration, annotation, and sharing in educational contexts.

- **Tech Stack**: Python 3.14, NiceGUI, SQLModel (Pydantic + SQLAlchemy), PostgreSQL, pycrdt (real-time collaboration), Stytch (auth), mammoth (DOCX conversion), pymupdf4llm (PDF extraction).
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

### 3. Philosophical Testing Standard (The "Thing Itself")
- **No YOLO Synchronization**: Do not use arbitrary sleeps or wait for vague UI epiphenomena.
- **Test the Epistemological Boundary**: Every test must articulate the exact boundary it tests. Do not just assert that a side-effect occurred; assert that the *underlying capability or rule engine* correctly evaluated the state transition.
- **Falsifiable Statements**: Test both sides of the boundary (before the action and after the action) in a way that makes risky, falsifiable statements. You must be able to confidently assert the test is not vacuous.
- **Example**: Do not just check if a word count badge reads "16". Check if the system correctly transitions from a valid state to a definitive "(over limit)" violation state after the threshold is crossed.

### 3. Code Quality & Formatting
- **No Ad-Hoc Python Scripts**: NEVER write ad-hoc Python scripts to modify code or test files. ALWAYS use AST-aware tools (`uv run rtk sg`) for structural refactoring, or the native agent `replace` tool for literal edits. Do not litter the workspace with temporary python scripts.
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
uv run grimoire e2e run                 # E2E tests (parallel by default, per-file isolation)
uv run grimoire e2e run -k "pattern"    # E2E tests filtered by keyword
uv run grimoire e2e run --serial        # E2E tests in serial mode (single server)
uv run grimoire e2e all                 # Run unit tests + Playwright E2E + NiceGUI lanes
uv run grimoire e2e changed             # Smart selection E2E tests
uv run grimoire e2e cards               # Card-specific E2E tests (@pytest.mark.cards)

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
- Wargame Schema Design: `docs/design-plans/2026-03-06-wargame-schema-294.md`
- Collaboration (CRDT): `docs/ARCHITECTURE.md`
- Web UI & Routing: `docs/annotation-architecture.md`
- Input Pipeline (HTML/DOCX/PDF): `docs/input-pipeline.md`
- Export Pipeline: `docs/export.md`
- Testing: `docs/testing.md`

### Database Model Summary

15 SQLModel table classes. Activity uses a `type` discriminator (`"annotation"` | `"wargame"`) with composite FK enforcement. ACLEntry targets either a workspace or a wargame team (exactly one, CHECK-enforced). Wargame extension tables: WargameConfig (1:1 on Activity), WargameTeam (per-activity teams), WargameMessage (per-team message log ordered by `sequence_no`).

**Permission `can_edit` classifier**: `Permission.can_edit` (boolean) marks editorial capability. The zero-editor invariant queries this flag instead of hardcoding permission names.

**Wargame team management API** (`db/wargames.py`): Full team CRUD, ACL (grant/revoke/update with upsert), and atomic CSV roster ingestion (named-team and auto-assign modes). `ZeroEditorError` prevents leaving a team with no editable member. Pure-domain helpers (codename generation, roster parsing) live in `wargame/`.

**Navigator FTS** (`db/navigator.py`): `search_navigator()` runs a three-leg UNION ALL: (1) document content, (2) CRDT search_text, (3) metadata (owner name, workspace/activity/week titles, course code/name). Uses prefix matching via `to_tsquery` with `:*` suffixes. Metadata snippets are labelled ("Title: ... | Author: ... | Unit: ...").
