# Chores Session Handoff — 2026-02-07

## What happened this session

### 1. Merged `106-html-input-pipeline` into main (partial)

Branch merged with `--no-ff`. Core HTML input pipeline is on main. Remaining #106 work (E2E test reimplementation, remaining phases) continues on follow-up branch.

Schema change: `WorkspaceDocument.raw_content` removed, replaced with `source_type`. Migration `9a0b954d51bf`.

### 2. Fixed xdist event loop collision (#121)

`test-all` was intermittently failing (8-19 errors per run) because Playwright's event loop contaminated xdist workers.

**Fixes:**
- `tests/integration/conftest.py`: `@pytest.fixture` → `@pytest_asyncio.fixture` on `reset_db_engine_per_test`
- `tests/e2e/conftest.py`: Removed `xdist_group("e2e")`
- `src/promptgrimoire/cli.py`: `test-all` now uses `-m "not e2e"` to exclude Playwright
- `tests/unit/test_async_fixture_safety.py`: Guard test (AST scan) catches `@pytest.fixture` on `async def`

**Rule:** Never use `@pytest.fixture` on async functions. Always `@pytest_asyncio.fixture`. Documented in CLAUDE.md.

**Result:** `test-all` deterministically passes (1,975 passed, 0 errors).

### 3. Branch cleanup

**Deleted (local + remote):**
- `101-cjk-blns` — merged, no WIP (had leaked dotfiles in worktree)
- `css-fidelity-pdf-export` — merged, Serena memories were stale (referenced old file names)
- `test-architecture-external-isolation` — superseded by #121 fix, uncommitted changes were minor refactors
- `wip/test-architecture-isolation-2026-02-04` — single WIP commit, subset of above
- `origin/html-input-pipeline` — old name duplicate of `106-html-input-pipeline`
- 3x `origin/claude/*` branches — auto-generated PR artifacts

**Rebased onto main:**
- `94-hierarchy-placement` — was 72 commits behind, 0 unique commits. Now at main HEAD. Ready for design work.

**Kept as-is:**
- `106-html-input-pipeline` — local branch, no worktree. In progress, has 1 commit ahead of main (Ralph removal).
- `milkdown-crdt-spike` — local branch + worktree. In progress, 2 commits ahead.

### 4. Issues created

- **#120** — Refactor `annotation.py` (2,302 lines) into smaller modules. Three natural seams identified.
- **#121** — xdist event loop collision. Root cause documented, fixes applied, remaining E2E isolation noted.

### 5. CLAUDE.md updated

- Librarian ran post-merge: added `input_pipeline` module, public API, schema change, `selectolax` dep, project structure, milkdown route
- Added async fixture rule and E2E isolation sections
- Updated `test-all` description

## Remaining state on work machine

On the work machine, `106-html-input-pipeline` has unpushed work. When you get there:

```bash
git fetch --prune          # sync deletions
git pull                   # get main updates

# Check 106 branch state
git log main..106-html-input-pipeline --oneline
```

## Current branch/worktree layout

```
main                          — current, clean, pushed
94-hierarchy-placement        — worktree at .worktrees/, rebased to main HEAD
milkdown-crdt-spike           — worktree at .worktrees/, 2 ahead
106-html-input-pipeline       — local only (no worktree), 1 ahead
```

## Dependabot alerts

2 vulnerabilities on default branch (1 high, 1 moderate). Check:
https://github.com/MQFacultyOfArts/PromptGrimoireTool/security/dependabot
