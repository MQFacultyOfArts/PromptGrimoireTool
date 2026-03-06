# Implementation Plan Guidance for PromptGrimoire

**Last updated:** 2026-03-07

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
1. [ ] Start the app: `uv run run.py`
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
uv run run.py

# Run tests (smart selection based on changes - fast)
uv run grimoire test changed

# Run all tests (unit + integration, excludes E2E)
uv run grimoire test all

# Run E2E tests (starts server, serial fail-fast)
uv run grimoire e2e run

# Run specific test
uv run pytest tests/unit/test_foo.py -k test_name

# Type checking
uvx ty check

# Linting
uv run ruff check .
uv run ruff format .

# Seed development data (idempotent)
uv run grimoire seed run

# Manage users
uv run grimoire admin list|show|create|admin|enroll|unenroll|role

# Generate user-facing documentation
uv run grimoire docs build
```

**Standard test commands (use ONLY these):**
- `uv run grimoire test changed` — smart test selection based on changes vs main (fast)
- `uv run grimoire test all` — full unit + integration suite (excludes E2E)
- `uv run grimoire e2e run` — E2E tests (starts server, serial fail-fast by default)
- `uv run grimoire e2e run --parallel` — E2E tests with xdist parallelism
- `uv run grimoire e2e changed` — E2E tests affected by changes vs main
- `uv run pytest tests/unit/test_foo.py -k test_name` — specific test
- `uv run grimoire e2e run -k test_name` — specific E2E test

**Never use:** `pip install`, `python -m pip`, raw `python` (always `uv run python`)

**Never set environment variables manually** (e.g., `DATABASE_URL="" uv run ...`). The test commands handle configuration. If a test needs a database, it will skip gracefully when `TEST_DATABASE_URL` is not set.

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

**Commit prefixes:** `feat:`, `fix:`, `test:`, `docs:`, `chore:`, `refactor:`, `deps:`

**Never:**
- `git add .` or `git add -A` (stage specific files)
- `git push --force` to main/master
- `git commit --amend` after pre-commit failure (create new commit instead)

### Pre-commit Hooks

Commits trigger:
1. `ruff check` - lint (with autofix)
2. `ruff format --check` - format
3. `ty check` - type check
4. `complexipy` - cognitive complexity gate (rejects functions > 15)
5. `trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `check-added-large-files`, `check-merge-conflict`

**Note:** Security scanning is handled by ruff S rules (not standalone bandit). `pip-audit` scans for dependency vulnerabilities.

**If pre-commit fails:** Fix the issue, stage the fix, create a NEW commit (don't amend).

**If complexipy fails:** The function is too complex. Extract helper functions, use early returns, reduce nesting. Do NOT add `# noqa: complexipy` — discuss with Brian first.

### Claude Code Hooks (on `.py` file write)

Every time a `.py` file is written, hooks automatically run:
1. `ruff check --fix` - autofix lint issues
2. `ruff format` - format code
3. `ty check` - type checking

All three must pass before code is considered complete.

## Complexity and Refactoring

### Mechanical Enforcement

Two tools enforce complexity and dead code limits. These are not suggestions — complexipy is a pre-commit hook that **blocks commits**.

**complexipy** — cognitive complexity analyser (Sonar-style). Pre-commit hook rejects any function with complexity > 15.

```bash
# Check the whole codebase
uv run complexipy src/promptgrimoire/ --max-complexity-allowed 15

# Check a single file
uv run complexipy src/promptgrimoire/pages/courses.py

# JSON output for CI
uv run complexipy src/promptgrimoire/ --output-json
```

**vulture** — dead code finder. Manual/CI diagnostic (not pre-commit because it must scan the entire codebase).

```bash
# Find dead code (≥80% confidence)
uv run vulture src/promptgrimoire/ --min-confidence 80
```

### When to Refactor

These thresholds are enforced by tooling. You cannot commit code that violates them.

| Metric | Threshold | Enforced by | Action |
|--------|-----------|-------------|--------|
| Cognitive complexity | > 15 | complexipy pre-commit hook | Extract helper functions, reduce nesting |
| Function length | > 40 lines | Code review | Split into focused functions |
| File length | > 400 lines | Code review | Extract module |
| Nesting depth | > 3 levels | complexipy (indirectly) | Early returns, extract conditions |

### How to Reduce Complexity

When complexipy blocks a commit:

1. **Extract conditionals** — Move complex `if/elif` chains into named predicate functions
2. **Early returns** — Invert conditions and return early to reduce nesting
3. **Extract loops** — Move loop bodies into named functions
4. **Split UI builders** — NiceGUI page functions naturally grow; extract widget-building functions with clear data-in/UI-out signatures
5. **Never suppress** — Do not add `# noqa: complexipy` without discussing with Brian first

Pre-existing violations are refactoring targets, not permission to add more. New code must pass the threshold. Run `uv run complexipy src/promptgrimoire/ --max-complexity-allowed 15` to see current violations.

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

### Async Fixture Rule

**NEVER use `@pytest.fixture` on `async def` functions.** Always use `@pytest_asyncio.fixture`. The sync decorator on async generators causes `Runner.run() cannot be called from a running event loop` under xdist.

### File Organisation

```
src/promptgrimoire/
├── models/           # SQLModel data models
├── pages/            # NiceGUI page routes
├── db/               # Database engine, CRUD operations, schema guard
├── export/           # PDF/LaTeX export pipeline
├── input_pipeline/   # HTML input processing (detection, conversion, char spans)
├── llm/              # Claude API client, lorebook activation, prompt assembly
├── parsers/          # SillyTavern character card parser
├── crdt/             # pycrdt collaboration logic
├── auth/             # Stytch integration
└── static/           # Static assets (JS bundles, CSS)
```

### Testing Requirements

| Type | Location | When Required |
|------|----------|---------------|
| Unit | `tests/unit/` | All pure functions, business logic |
| Integration | `tests/integration/` | Database, external APIs |
| E2E | `tests/e2e/` | Critical user flows only (excluded from `test-all`) |

**TDD is mandatory:**
1. Write failing test
2. Write minimal code to pass
3. Refactor
4. Repeat

### E2E Test Rules

E2E tests are excluded from `test-all` (`-m "not e2e"`) because Playwright's event loop contaminates xdist workers. They must run separately with a live app server.

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

**All interactable UI elements MUST have `data-testid` attributes.** E2E tests MUST use `page.get_by_test_id()` — never locate by visible text, placeholder, CSS class, or `get_by_role(name=...)`. Button text changes silently break tests; testids are a stable contract.

```python
# GOOD — testid locator
page.get_by_test_id("start-activity-btn").click()
card.locator("[data-testid^='start-activity-btn-']").first.click()

# BAD — fragile text/role locator
page.get_by_role("button", name="Start Activity").click()  # BREAKS when text changes
page.get_by_text("Start Activity").click()  # BREAKS when text changes
page.locator(".q-item").filter(has_text="Home")  # BREAKS when class changes
```

**Always scroll into view** before assertions (headless mode quirk):
```python
await locator.scroll_into_view_if_needed()
await expect(locator).to_be_visible()
```

### Database Rules

1. **Alembic is the ONLY way to create/modify schema** - Never use `SQLModel.metadata.create_all()` except in Alembic migrations themselves
2. **All models must be imported before schema operations** - Import `promptgrimoire.db.models` to register tables with SQLModel.metadata
3. **Pages requiring DB must check availability** - Use `os.environ.get("DATABASE_URL")` and show a helpful error if not configured
4. **Use `verify_schema()` at startup** - Fail fast if tables are missing

## Design-Implementation Alignment Checks

### Before Implementation (Planning Gate)

After writing the implementation plan but before executing it, compare each phase against the design document. Flag any divergences:

- Schema contracts that differ from the design doc (new columns, different constraint patterns, changed FK strategies)
- Architectural decisions made in the implementation plan that the design doc doesn't cover
- Improvements over the design (e.g. stronger DBA contracts) that should be adopted

**If the implementation plan improves on the design:** Update the design doc to match. The design doc is the canonical record — it must reflect what will actually be built.

**If the implementation plan contradicts the design without improvement:** Fix the implementation plan to match the design.

Commit design doc updates with a clear message referencing the implementation plan's rationale.

### After Implementation (Finalisation Gate)

After all phases are complete and tests pass, compare what was actually built against the design document:

- Do the schema contracts in the design doc match the actual migration?
- Do the SQLModel classes match the design doc's described structure?
- Were any design decisions changed during implementation that the design doc doesn't reflect?

**Update the design doc to reflect reality.** The design doc is a living record, not a frozen spec. If implementation revealed that a different approach was needed, the design doc should say so (with a note explaining why).

### Complexipy Check Per Phase

After completing each implementation phase, run complexipy on all modified files:

```bash
uv run complexipy <modified-file-1> <modified-file-2> ...
```

- Pre-commit blocks functions with cognitive complexity > 15, but **file-level** complexity is also a concern
- If a file's total complexity is growing (especially > 100), note it as a refactoring candidate
- If the phase introduced functions near the threshold (complexity 10-15), flag them as at-risk
- Include complexipy results in the phase completion notes

This prevents complexity from accumulating silently across phases.

## Pre-PR Gate

Before raising a PR, **both** test suites must pass:

```bash
# Full unit + integration suite
uv run grimoire test all

# Full E2E suite (starts server, serial fail-fast)
uv run grimoire e2e run
```

Do not raise a PR with either suite failing. If E2E tests fail on unrelated issues, document them explicitly in the PR description.

## Review Criteria

Code review will check:

- [ ] Tests written BEFORE implementation (TDD)
- [ ] No `any` types without justification
- [ ] No JavaScript injection in E2E tests
- [ ] All interactable elements have `data-testid` attributes
- [ ] E2E tests use `get_by_test_id()` — no text/role/CSS locators
- [ ] UAT steps provided and testable
- [ ] Specific files staged (not `git add .`)
- [ ] Conventional commit message
- [ ] Type hints on all functions
- [ ] No `# type: ignore` without explanation
- [ ] Async fixtures use `@pytest_asyncio.fixture`

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
