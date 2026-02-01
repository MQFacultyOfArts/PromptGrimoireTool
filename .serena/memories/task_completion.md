# Task Completion

## Primary Reference

Use the Claude Code skill: **`/verification-before-completion`**

This skill enforces running verification commands and confirming output before making success claims.

## Project-Specific Verification

```bash
# All three must pass (hooks run automatically on .py writes):
uv run ruff check --fix .
uv run ruff format .
uvx ty check

# Test verification - stop at first failure
uv run test-debug
```

## Related Skills

- **`/test-driven-development`** - Ensures tests written first
- **`/systematic-debugging`** - When fixes fail repeatedly
- **`/requesting-code-review`** - Before merging/PRs

## Hard Rules (from CLAUDE.md)

- Task not complete without verification evidence
- After 3 consecutive failures: STOP, revert, document, ask
- Never commit unless explicitly requested
