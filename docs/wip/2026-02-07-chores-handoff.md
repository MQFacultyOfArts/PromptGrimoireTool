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

### 6. Dependency upgrades

Controlled one-at-a-time upgrades with changelog review and test-all after each.

**Upgraded:**
| Package | From | To | Notes |
|---------|------|----|-------|
| rich | 14.3.1 | 14.3.2 | ZWJ cell_len bugfix |
| pycrdt | 0.12.45 | 0.12.46 | pyo3 build bump |
| anthropic | 0.77.0 | 0.78.0 | Beta type additions |
| sqlmodel | 0.0.31 | 0.0.32 | Annotated fields fix for Pydantic 2.12+ |
| playwright | 1.57.0 | 1.58.0 | Trace viewer; **run `playwright install` on work machine** (#123) |
| ruff | 0.14.14 | 0.15.0 | 2026 style guide, reformatted 4 files, fixed 16 lint issues |
| nicegui | 3.6.1 | 3.7.1 | **2 security fixes** (XSS via ui.markdown, path traversal via FileUpload.name) |

**Removed:**
- `odfdo` — unused, was intended for Phase 7 input conversion. `lxml` promoted to direct dep (used by `export/html_normaliser.py`).
- `html5lib` — zero imports in entire codebase. Was never wired in.
- `psycopg[binary]` — from production deps (moved to dev, see below). All production DB access uses asyncpg.

**Moved to dev deps:**
- `pytest-xdist[psutil]` — was in production dependencies
- `ast-grep-cli` — was in production dependencies
- `psycopg[binary]` — only used by `tests/conftest.py` for sync table truncation
- `lorem-text` — only used by `scripts/anonymise_chats.py`

**Fixed duplicate:**
- `pylatexenc` — was listed in both production deps and `[dependency-groups] dev`. Removed from dev group (production listing is correct).

### 7. Issues created (dependency session)

- **#122** — Migrate remaining bs4 usage to selectolax
- **#123** — Run `playwright install` on work machine after 1.58.0 upgrade

### 8. CLAUDE.md audit

- Fixed target date (2025 → 2026)
- Added lxml to tech stack (html5lib added then removed — was unused)
- Regenerated project structure tree (was missing ~15 files/dirs)
- Updated page DB dependencies table
- Removed duplicate `test-debug` entry

### 9. Dependency rationale audit

Created `docs/dependency-rationale.md` from first principles — searched codebase for every production and dev dependency, documented claims with file/line evidence, classified as hard core vs protective belt.

Key findings acted on:
- **html5lib**: Zero imports. Removed.
- **psycopg[binary]**: Not used in production (all connections use asyncpg). Moved to dev deps — only `tests/conftest.py` needs it for sync table truncation.
- **lorem-text**: Only used in utility script. Moved to dev deps.
- **pylatexenc**: Duplicate listing in dev group. Removed duplicate.
- **bs4**: Deprecated, migration tracked in #122 (already known).

## Dependabot alerts

All 3 alerts now **fixed** (nicegui 3.7.1 resolved the last two):
- GHSA-9ffm-fxg3-xrhh (High) — path traversal via FileUpload.name
- GHSA-v82v-c5x8-w282 (Medium) — XSS via ui.markdown()
- GHSA-wp53-j4wj-2cfg (High) — python-multipart path traversal (was already fixed)
