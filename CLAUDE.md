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
- **Lark** - parser generator for LaTeX marker tokenization

## Development Workflow

### TDD is Mandatory

See [docs/testing.md](docs/testing.md) for full testing guidelines including E2E patterns and database isolation rules.

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

# Run all tests (full suite)
uv run test-all

# Run linting
uv run ruff check .

# Run type checking
uvx ty check

# Run the app
uv run python -m promptgrimoire

# Find first failing test
uv run test-debug
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
- `marginalia` - auto-stacking margin notes (LuaLaTeX)
- `latexmk` - build automation

### Configuration

The `LATEXMK_PATH` env var overrides the default TinyTeX path if needed. Leave empty to use TinyTeX.

### Architecture

- `src/promptgrimoire/export/pdf.py` - `get_latexmk_path()` resolves latexmk location, `compile_latex()` compiles .tex to PDF (async)
- `scripts/setup_latex.py` - installs TinyTeX and packages
- Does NOT fall back to system PATH - TinyTeX only for consistency

**Note:** `compile_latex()` is async and uses `asyncio.create_subprocess_exec()` for non-blocking compilation.

### LaTeX Marker Pipeline

The annotation export uses a Lark-based lexer pipeline (Issue #85) to handle arbitrarily nested and overlapping highlights:

1. **Marker insertion** - `_insert_markers_into_html()` inserts `HLSTART{n}ENDHL`, `HLEND{n}ENDHL`, and `ANNMARKER{n}ENDMARKER` at word positions
2. **Pandoc conversion** - HTML to LaTeX (markers survive as plain text)
3. **Lexer tokenization** - `tokenize_markers()` uses Lark grammar to extract marker tokens
4. **Region building** - `build_regions()` tracks active highlight state to create regions with constant highlight sets
5. **LaTeX generation** - `generate_highlighted_latex()` wraps each region in nested `\highLight` and `\underLine` commands

Key types in `latex.py`:
- `MarkerToken` - Token from lexer (TEXT, HLSTART, HLEND, ANNMARKER)
- `Region` - Text span with frozenset of active highlight indices

## Database

PostgreSQL with SQLModel. Schema migrations via Alembic.

### Tables (6 SQLModel classes)

- **User** - Stytch-linked user accounts
- **Course** - Course/unit of study with weeks and enrolled members
- **CourseEnrollment** - Maps users to courses with course-level roles
- **Week** - Week within a course with visibility controls
- **Workspace** - Container for documents and CRDT state (unit of collaboration)
- **WorkspaceDocument** - Document within a workspace (source, draft, AI conversation)

### Workspace Architecture

Workspaces are isolated silos identified by UUID. Key design decisions:

- **No `created_by` FK** - Audit (who created) is separate from access control (who can use)
- **Future: ACL for access control** - Seam D will add workspace-user permissions
- **Future: Audit log for history** - Separate table for who-did-what tracking
- **`create_workspace()` takes no parameters** - Just creates an empty workspace with UUID

This separation prevents conflating audit concerns with authorization logic.

### Database Rules

1. **Alembic is the ONLY way to create/modify schema** - Never use `SQLModel.metadata.create_all()` except in Alembic migrations themselves
2. **All models must be imported before schema operations** - The `promptgrimoire.db.models` module must be imported to register tables with SQLModel.metadata
3. **Pages requiring DB must check availability** - Use `os.environ.get("DATABASE_URL")` and show a helpful error if not configured
4. **Use `verify_schema()` at startup** - Fail fast if tables are missing

### Page Database Dependencies

| Page | Route | DB Required |
|------|-------|-------------|
| annotation | `/annotation` | **Yes** |
| case_tool | `/case-tool` | **Yes** |
| roleplay | `/roleplay` | No |
| logs | `/logs` | No |
| auth | `/login`, `/logout` | Optional |

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
