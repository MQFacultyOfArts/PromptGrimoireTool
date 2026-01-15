# PromptGrimoire - Project Infrastructure & PRD Plan

## Context
Building a collaborative "classroom grimoire" for prompt iteration, annotation, and sharing in educational contexts. Based on the pedagogical framework from "Teaching the Unknown" (Ballsun-Stanton & Torrington).

**Timeline:** 6 weeks to Session 1 2025 (Feb 23)

---

## Product Requirements Document (PRD)

### Vision
A lightweight tool for educators and students to:
- Accept student prompts (copy-paste from multiple AI providers)
- Enable real-time collaborative annotation with structured tagging
- Support in-class "show me your prompts" discussions
- Build a shared grimoire of effective prompting patterns

### Core Features

#### 1. Conversation Import & Parsing
- Multi-format parsers: Claude, ChatGPT, Chatcraft.org, ScienceOS
- Full conversation as atomic unit
- Parse into individual turns (human/assistant pairs)
- Plain text fallback with manual delimiters

#### 2. Real-time Collaborative Annotation
- **Tech:** pycrdt (Yjs port) + PostgreSQL + NiceGUI websockets
- Highlight ranges on prompt/response text
- Structured tags (emergent folksonomy with seed defaults)
- Threaded comments on highlights
- Live cursors/presence indicators

#### 3. Tag System
- Emergent folksonomy: users create tags freely
- Seed defaults: effective/ineffective/hallucination/good-structure
- Class-scoped tag namespacing
- Tag frequency surfacing for popular tags

#### 4. Class Management
- Stytch magic links + passkeys for auth
- Stytch-managed invites per class
- Stytch RBAC for permissions (admin/instructor/student roles)
- Future: Okta SSO integration via Stytch

#### 5. Sharing & Discovery
- Private by default (class-scoped)
- Explicit contribution to public grimoire
- Attribution preserved
- Search across accessible content

#### 6. Presentation Mode
- "Class view" optimized for projection
- Surface recently shared/annotated prompts
- Sorting/filtering for "show me your prompts" discussions

### Tech Stack
- **Python 3.14** (bleeding edge, matches .python-version)
- **NiceGUI** - web UI framework
- **SQLModel** - ORM (Pydantic + SQLAlchemy)
- **PostgreSQL** - persistence
- **pycrdt** - CRDT for real-time collaboration
- **Stytch** - auth (magic links, passkeys, invites)
- **Ruff** - linting + formatting
- **ty** - type checking
- **Playwright** - E2E testing
- **pytest** - unit/integration testing

### User Roles (Stytch RBAC)

- **Admin:** Full system access, manage institutions
- **Instructor:** Create classes, manage tags, invite students, projection view
- **Student:** Import prompts, annotate, share to class/grimoire

---

## Phase 1: Project Infrastructure Setup (This Session)

### 1. CLAUDE.md
Claude Code instructions for this project:
- Project overview and architecture
- TDD workflow requirements
- Hook behavior documentation
- Key commands and conventions

### 2. README.md
- Project description
- Quick start / development setup
- Architecture overview
- Contributing guidelines

### 3. pyproject.toml Updates
Add dependencies:
- nicegui
- sqlmodel
- psycopg (PostgreSQL driver)
- pycrdt
- stytch
- pydantic
- pytest
- pytest-asyncio
- playwright
- ruff (dev)

Add tool configurations for ruff, ty.

### 4. Claude Code Hooks (.claude/hooks/)
Pre-write hooks that:
1. Run `ruff check --fix` (autofix)
2. Run `ruff check` (verify)
3. Run `ruff format` (format)
4. Run `ty check` (typecheck)

Hook triggers on file write to *.py files.

### 5. GitHub Hooks (.github/workflows/ + .pre-commit-config.yaml)
- **pre-commit:** ruff lint + format + ty check
- **CI workflow:** lint, typecheck, test on push/PR

### 6. Test Infrastructure
- `tests/` directory structure
- pytest configuration
- Playwright setup for E2E
- Example test demonstrating TDD pattern

### 7. Claude Code Skill: `cache-docs`
Auto-triggered skill to cache documentation for all non-core dependencies.

**File:** `.claude/skills/cache-docs/SKILL.md`

```yaml
---
name: cache-docs
description: When fetching library documentation, API references, or technical docs for project dependencies, automatically save a copy to docs/ folder. Triggers on WebFetch of documentation sites, user pasting docs, or discussion of library APIs.
---
```

**Behavior:**
- Auto-triggers when documentation is fetched or pasted
- Saves to `docs/<library-name>/<slugified-title>.md`
- Adds YAML frontmatter: source URL, fetch date, summary
- Every non-stdlib import should have reference docs cached
- Updates `docs/_index.md` with new entries

### 8. docs/ Directory Structure
```
docs/
├── _index.md           # Auto-maintained index
├── pycrdt/
│   └── quickstart.md
├── stytch/
│   └── rbac.md
├── nicegui/
├── sqlmodel/
└── claude-code/
    └── skills.md       # This very documentation!
```

---

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `CLAUDE.md` | Create | Claude Code project instructions |
| `README.md` | Rewrite | Project documentation |
| `pyproject.toml` | Update | Dependencies + tool config |
| `.claude/settings.json` | Create | Hook configuration |
| `.claude/skills/cache-docs/SKILL.md` | Create | Auto-triggered skill for caching documentation |
| `.pre-commit-config.yaml` | Create | Git pre-commit hooks |
| `.github/workflows/ci.yml` | Create | GitHub Actions CI |
| `tests/__init__.py` | Create | Test package |
| `tests/conftest.py` | Create | pytest fixtures |
| `tests/test_example.py` | Create | TDD example |
| `src/promptgrimoire/__init__.py` | Create | Package structure |
| `docs/_index.md` | Create | Documentation cache index |

---

## Database Schema (Preview)

```
User (id, email, display_name, created_at)
Class (id, name, owner_id, invite_code, created_at)
ClassMembership (user_id, class_id, acl_flags)
Conversation (id, class_id, owner_id, raw_text, parsed_turns, crdt_state)
Turn (id, conversation_id, role, content, sequence)
Annotation (id, conversation_id, user_id, turn_id, start_offset, end_offset, crdt_state)
Tag (id, name, class_id, usage_count)
AnnotationTag (annotation_id, tag_id)
Comment (id, annotation_id, user_id, content, parent_id, created_at)
```

---

## Verification

After implementation:
1. `ruff check .` passes
2. `ty check` passes
3. `pytest` runs (even if just example test)
4. Git commit triggers pre-commit hooks
5. `uv run python -m promptgrimoire` doesn't crash

---

## Open Questions for Later Sessions
- Exact Stytch configuration (needs API keys)
- PostgreSQL hosting on NCI
- pycrdt WebSocket architecture details
- Parser specifications per AI provider
- UI/UX wireframes for annotation interface
