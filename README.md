# PromptGrimoire

A collaborative tool for prompt iteration, annotation, and sharing in educational contexts.

## Overview

PromptGrimoire enables educators and students to:

- **Import** AI conversation transcripts (Claude, ChatGPT, Chatcraft.org, ScienceOS)
- **Annotate** prompts and responses with structured tags and threaded comments
- **Collaborate** in real-time during "show me your prompts" classroom discussions
- **Share** effective prompting patterns to build a collective grimoire

Based on the pedagogical framework from ["Teaching the Unknown: A Pedagogical Framework for Teaching With and About AI"](paper/) (Ballsun-Stanton & Torrington, 2025).

## Quick Start

### Prerequisites

- Python 3.14+
- PostgreSQL
- [uv](https://docs.astral.sh/uv/) package manager

### Development Setup

```bash
# Clone the repository
git clone https://github.com/your-org/promptgrimoire.git
cd promptgrimoire

# Install dependencies
uv sync

# Set up pre-commit hooks
uv run pre-commit install

# Run tests
uv run pytest

# Start the development server
uv run python -m promptgrimoire
```

### Environment Variables

```bash
# .env
DATABASE_URL=postgresql://user:pass@localhost/promptgrimoire
STYTCH_PROJECT_ID=your-project-id
STYTCH_SECRET=your-secret
```

## Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│                        NiceGUI UI                           │
├─────────────────────────────────────────────────────────────┤
│  Parsers  │  CRDT Sync (pycrdt)  │  Auth (Stytch RBAC)      │
├─────────────────────────────────────────────────────────────┤
│                   SQLModel / PostgreSQL                     │
└─────────────────────────────────────────────────────────────┘
```

### Key Components

- **Parsers**: Convert conversation exports from various AI providers into a common format
- **CRDT Sync**: Real-time collaborative editing via pycrdt (Yjs port)
- **Auth**: Stytch handles magic links, passkeys, and role-based access control
- **Storage**: PostgreSQL with SQLModel ORM

## Development

### Code Quality

This project enforces strict code quality via automated hooks:

- **Ruff**: Linting and formatting
- **ty**: Type checking
- **pytest**: Testing (TDD workflow required)
- **Playwright**: End-to-end testing

All checks run automatically on file save (Claude Code hooks) and git commit (pre-commit hooks).

### Testing

```bash
# Run all tests
uv run pytest

# Run E2E tests
uv run playwright test

# Run specific test file
uv run pytest tests/unit/test_parsers.py
```

### Project Structure

```text
src/promptgrimoire/     # Main application code
tests/                  # Test suite
docs/                   # Cached library documentation
paper/                  # Research papers
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Write tests first (TDD)
4. Implement your changes
5. Ensure all checks pass
6. Submit a pull request

## License

[See LICENSE](LICENSE)

## Acknowledgments

- Based on research from Macquarie University's experimental AI pedagogy unit
- Inspired by the concept of a "classroom grimoire" for collaborative prompt development
