# Suggested Commands for PromptGrimoireTool

## Development

```bash
# Install dependencies
uv sync

# Run the application
uv run python -m promptgrimoire

# Alternative entry point
uv run promptgrimoire
```

## Testing

```bash
# Find first failing test (PREFERRED - stops at first failure)
uv run test-debug

# Run all tests (slower, use for full verification)
uv run pytest

# Run specific test file
uv run pytest tests/unit/test_example.py

# Run with coverage
uv run pytest --cov=src/promptgrimoire
```

## Code Quality

```bash
# Linting (auto-fix)
uv run ruff check --fix .

# Format code
uv run ruff format .

# Type checking
uvx ty check
```

## Database

```bash
# Run migrations
uv run alembic upgrade head

# Create new migration
uv run alembic revision --autogenerate -m "description"

# Check migration status
uv run alembic current
```

## Git Worktrees (Recommended for parallel work)

```bash
# Create a worktree for feature work
git worktree add .worktrees/feature-name main

# List worktrees
git worktree list

# Remove worktree when done
git worktree remove .worktrees/feature-name
```

## CLI Utilities

```bash
# Set user as admin
uv run set-admin <email>

# Show export log
uv run show-export-log
```

## System Utilities (Linux)

Standard Linux commands work: `git`, `ls`, `cd`, `grep`, `find`, `cat`, etc.
