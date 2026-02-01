# PromptGrimoireTool - Project Overview

## Purpose
A collaborative "classroom grimoire" for prompt iteration, annotation, and sharing in educational contexts. Based on the pedagogical framework from "Teaching the Unknown" (Ballsun-Stanton & Torrington, 2025).

**Target Release:** Session 1 2025 (Feb 23)

## Core Use Cases

1. **Prompt Annotation & Sharing (Core)** - Collaborative annotation of AI conversations for teaching prompt engineering

2. **Legal Client Interview Simulation (Spike 4)** - Import SillyTavern character cards for AI-powered roleplay scenarios (tort law training)

3. **Legal Case Brief Tool (Planned)** - Structured legal case brief generation

## Tech Stack
- **Python 3.14** - bleeding edge
- **NiceGUI** - web UI framework
- **SQLModel** - ORM (Pydantic + SQLAlchemy)
- **PostgreSQL** - persistence
- **pycrdt** - CRDT for real-time collaboration
- **Stytch** - auth (magic links, passkeys, RBAC)
- **Lark** - parser generator for LaTeX marker tokenization
- **TinyTeX** - PDF export

## Project Structure
```
src/promptgrimoire/
├── main.py           # NiceGUI app entry
├── models/           # Data models
├── parsers/          # SillyTavern character card parser
├── llm/              # Claude API client, lorebook activation
├── pages/            # NiceGUI page routes
├── auth/             # Stytch integration
├── crdt/             # pycrdt collaboration logic
└── export/           # PDF/LaTeX export

tests/
├── unit/             # Unit tests (run first)
├── integration/      # Integration tests
└── e2e/              # Playwright E2E tests
```

## Key Files
- `CLAUDE.md` - Full project conventions and instructions
- `.env.example` - Environment variable documentation (source of truth)
- `pyproject.toml` - Dependencies and tool configuration
