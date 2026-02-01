# Code Style and Conventions

## Primary References

Style and conventions are managed through Claude Code skills. Use these:

- **`/coding-effectively`** - Full coding standards framework (orchestrates sub-skills)
- **`/python-idioms`** - Python 3.14+ patterns, t-strings, type checking with ty
- **`/test-driven-development`** - TDD workflow (RED-GREEN-REFACTOR)
- **`/writing-good-tests`** - pytest patterns, mock strategy, test isolation
- **`/functional-core-imperative-shell`** - Separation of pure logic from side effects

## Project-Specific Notes

See `CLAUDE.md` for project-specific rules including:
- E2E test guidelines (never inject JavaScript - use Playwright native APIs)
- Database rules (Alembic only, UUID isolation for tests)
- LaTeX marker pipeline architecture

## Quick Reference

```bash
# Code quality (hooks run automatically on .py writes)
uv run ruff check --fix .
uv run ruff format .
uvx ty check
```
