# Implementation Plan Guidance for PromptGrimoire

**Last updated:** 2026-01-30

## UAT is Critical

**Every deliverable must be testable by a human (Brian) before considered complete.**

### UAT Requirements

1. **Define acceptance criteria BEFORE implementation** - What will Brian test? How will he know it works?
2. **Provide manual test steps** - Exact commands/clicks to verify the feature
3. **No "trust me" completions** - If you can't demonstrate it, it's not done
4. **Incremental UAT** - Break large features into testable chunks

### UAT Checklist Template

For every implementation task, include:

```markdown
## UAT Steps
1. [ ] Start the app: `uv run python -m promptgrimoire`
2. [ ] Navigate to: [route]
3. [ ] Perform: [action]
4. [ ] Verify: [expected outcome]

## Evidence Required
- [ ] Screenshot/recording of working feature
- [ ] Test output showing green
```

## Commands

### Package Management (uv only)

```bash
# Install dependencies
uv sync

# Add a dependency
uv add <package>

# Add a dev dependency
uv add --dev <package>

# Run Python
uv run python -m promptgrimoire

# Run tests
uv run pytest

# Run specific test
uv run pytest tests/unit/test_foo.py -k test_name

# Find first failing test (custom script)
uv run test-debug

# Type checking
uvx ty check

# Linting
uv run ruff check .
uv run ruff format .
```

**Never use:** `pip install`, `python -m pip`, raw `python` (always `uv run python`)

### Git Workflow

```bash
# Check status
git status

# Create feature branch
git checkout -b feature/descriptive-name

# Stage specific files (preferred over git add .)
git add src/promptgrimoire/specific_file.py tests/unit/test_specific.py

# Commit with conventional prefix
git commit -m "feat: add widget support for dashboard"
git commit -m "fix: resolve highlight overlap in PDF export"
git commit -m "test: add E2E coverage for annotation flow"

# Push and set upstream
git push -u origin feature/descriptive-name

# Create PR
gh pr create --title "feat: descriptive title" --body "..."
```

**Commit prefixes:** `feat:`, `fix:`, `test:`, `docs:`, `chore:`, `refactor:`

**Never:**
- `git add .` or `git add -A` (stage specific files)
- `git push --force` to main/master
- `git commit --amend` after pre-commit failure (create new commit instead)

### Pre-commit Hooks

Commits trigger:
1. `ruff check` - lint
2. `ruff format --check` - format
3. `ty check` - type check

**If pre-commit fails:** Fix the issue, stage the fix, create a NEW commit (don't amend).

## Coding Standards

### Python 3.14 Idioms

```python
# Type hints required on all functions
def process_highlight(text: str, color: str) -> Highlight:
    ...

# Prefer composition over inheritance
@dataclass
class AnnotationService:
    repo: AnnotationRepository
    crdt: CRDTManager

# Keep functions small and focused
# No # type: ignore without explanation
```

### File Organization

```
src/promptgrimoire/
├── models/           # SQLModel data models
├── pages/            # NiceGUI page routes
├── services/         # Business logic
├── repositories/     # Database access
└── export/           # PDF/LaTeX export
```

### Testing Requirements

| Type | Location | When Required |
|------|----------|---------------|
| Unit | `tests/unit/` | All pure functions, services |
| Integration | `tests/integration/` | Database, external APIs |
| E2E | `tests/e2e/` | Critical user flows only |

**TDD is mandatory:**
1. Write failing test
2. Write minimal code to pass
3. Refactor
4. Repeat

### E2E Test Rules

**NEVER inject JavaScript.** Use Playwright native APIs:

```python
# GOOD - native Playwright
await page.mouse.move(start_x, start_y)
await page.mouse.down()
await page.mouse.move(end_x, end_y)
await page.mouse.up()

# BAD - JavaScript injection
await page.evaluate("window.getSelection().toString()")  # FORBIDDEN
```

**Always scroll into view** before assertions (headless mode quirk):
```python
await locator.scroll_into_view_if_needed()
await expect(locator).to_be_visible()
```

## Review Criteria

Code review will check:

- [ ] Tests written BEFORE implementation (TDD)
- [ ] No `any` types without justification
- [ ] No JavaScript injection in E2E tests
- [ ] UAT steps provided and testable
- [ ] Specific files staged (not `git add .`)
- [ ] Conventional commit message
- [ ] Type hints on all functions
- [ ] No `# type: ignore` without explanation

## Claude Code Plugins Available

### denubis-plugins (workflow)
- `denubis-plan-and-execute` - Design and implementation planning
- `denubis-basic-agents` - Generic subagents (Opus, Sonnet, Haiku)
- `denubis-research-agents` - Internet/codebase research
- `denubis-extending-claude` - Skills, transcripts, CLAUDE.md management

### claude-plugins-official (tools)
- `context7` - Library documentation lookup
- `playwright` - Browser automation (MCP)
- `serena` - Semantic code navigation (MCP)
- `pr-review-toolkit` - PR review agents
- `code-review` - Code review
- `frontend-design` - UI generation
- `commit-commands` - Git workflow helpers

### Key Skills

| Skill | When to Use |
|-------|-------------|
| `/start-design-plan` | Beginning any new feature |
| `/brainstorming` | Refining ideas before implementation |
| `/test-driven-development` | All implementation work |
| `/verification-before-completion` | Before claiming anything is done |
| `/requesting-code-review` | After completing a feature |
| `/commit` | Creating git commits |

## Cross-Reference

- Full project rules: [project-reference.md](project-reference.md)
- Design guidance: [design-plan-guidance.md](design-plan-guidance.md)
- Plugin checklist: [plugin-checklist.md](plugin-checklist.md)
