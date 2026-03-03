# CLI Typer Migration Implementation Plan — Phase 6

**Goal:** Final cleanup: ensure the old `cli.py` monolith is deleted (already renamed to `cli_legacy.py` and should have been removed in Phase 5), remove all old `[project.scripts]` entries, update documentation references.

**Architecture:** By this phase, all code has been migrated to the `cli/` package (Phases 2-5). This phase handles the meta-artifacts: entry points, documentation, and linting config.

**Tech Stack:** N/A (documentation and configuration changes only)

**Scope:** Phase 6 of 6 from original design

**Codebase verified:** 2026-03-02

---

## Acceptance Criteria Coverage

### cli-typer-211.AC1: Module Structure
- **cli-typer-211.AC1.2 Success:** Old `src/promptgrimoire/cli.py` monolith is deleted
- **cli-typer-211.AC1.3 Failure:** Importing `from promptgrimoire.cli import test_all` (old path) raises `ImportError`

### cli-typer-211.AC3: Single Entry Point
- **cli-typer-211.AC3.2 Success:** `pyproject.toml` has `grimoire = "promptgrimoire.cli:app"` as the CLI entry point
- **cli-typer-211.AC3.3 Success:** Old `[project.scripts]` entries (test-all, test-changed, etc.) are removed

---

<!-- START_TASK_1 -->
### Task 1: Verify and Clean Up cli_legacy.py Deletion

**Verifies:** cli-typer-211.AC1.2, cli-typer-211.AC1.3

**Files:**
- Verify deletion: `src/promptgrimoire/cli_legacy.py` (should have been deleted in Phase 5 Task 4)

**Implementation:**

This is a verification-only task. `cli_legacy.py` was deleted in Phase 5 Task 4.

1. Verify `cli_legacy.py` was deleted:
   ```bash
   ls src/promptgrimoire/cli_legacy.py 2>&1
   ```
   Expected: "No such file or directory". If it still exists, Phase 5 was incomplete — go back and complete Phase 5 Task 4 before continuing.

2. Verify no references remain:
   ```bash
   grep -r "cli_legacy" src/ tests/
   ```
   Expected: Zero results.

3. Verify the old import path fails:
   ```bash
   uv run python -c "from promptgrimoire.cli import test_all" 2>&1
   ```
   Expected: `AttributeError` or `ImportError` (because `cli` is now a package, and `test_all` is not exported from `__init__.py`).

**No commit** — verification only.
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Clean Up pyproject.toml Entry Points and Ruff Config

**Verifies:** cli-typer-211.AC3.2, cli-typer-211.AC3.3

**Files:**
- Modify: `pyproject.toml`

**Implementation:**

1. Replace the `[project.scripts]` section. Remove ALL old entries except `promptgrimoire` (the NiceGUI app) and `load-test-data` (separate module). Keep only `grimoire`:

```toml
[project.scripts]
promptgrimoire = "promptgrimoire:main"
grimoire = "promptgrimoire.cli:app"
load-test-data = "promptgrimoire.cli_loadtest:load_test_data"
```

2. Update ruff per-file-ignores. Remove the `"src/promptgrimoire/cli.py"` entry (lines 116-118):

```toml
# Remove this block:
"src/promptgrimoire/cli.py" = [
    "PLC0415",  # Late import of pytest for CLI commands
]
```

Add a replacement for the cli/ package if any module uses late imports:
```toml
"src/promptgrimoire/cli/*.py" = [
    "PLC0415",  # Late import of pytest for CLI commands
]
```

3. Run `uv sync` to pick up entry point changes.

**Verification:**

Run: `uv run grimoire --help`
Expected: Shows all sub-apps.

Run: Old `test-all` entry point should no longer exist in pyproject.toml.
Expected: Calling the removed entry fails (old entry removed).

**Commit:** `chore: clean up pyproject.toml entry points and ruff config for cli/ package`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Update CLAUDE.md Key Commands Section

**Files:**
- Modify: `CLAUDE.md` (lines 72-111, Key Commands section)

**Implementation:**

Replace the Key Commands section with the new `uv run grimoire <verb>` invocations:

```markdown
## Key Commands

\```bash
# Install dependencies
uv sync

# Run tests (smart selection based on changes - fast)
uv run grimoire test changed

# Run all tests (unit + integration, excludes E2E)
uv run grimoire test all

# Run E2E tests (starts server, serial fail-fast by default)
uv run grimoire e2e run

# Run E2E tests in parallel (xdist)
uv run grimoire e2e run --parallel

# Run E2E tests (smart selection based on changes)
uv run grimoire e2e changed

# Run linting
uv run ruff check .

# Run type checking
uvx ty check

# Seed development data (idempotent)
uv run grimoire seed run

# Manage users, roles, and course enrollments
uv run grimoire admin list|show|create|admin|enroll|unenroll|role

# Generate user-facing documentation (requires pandoc)
uv run grimoire docs build

# Run the app
uv run python -m promptgrimoire

\```
```

**Verification:**

Visual inspection of CLAUDE.md Key Commands section.

**Commit:** `docs: update CLAUDE.md Key Commands for grimoire CLI`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Update Documentation References

**Files:**
- Modify: `docs/database.md` (line 384)
- Modify: `docs/deployment.md` (lines 384, 402, 958-1005, 1096)
- Modify: `docs/testing.md` (if it contains old command references)

**Implementation:**

Search and replace old command references in documentation:

| Old script name | New invocation |
|-----|-----|
| `test-changed` | `uv run grimoire test changed` |
| `test-all` | `uv run grimoire test all` |
| `test-all-fixtures` | `uv run grimoire test all-fixtures` |
| `test-e2e` | `uv run grimoire e2e run` |
| `test-e2e --parallel` | `uv run grimoire e2e run --parallel` |
| `test-e2e-slow` | `uv run grimoire e2e slow` |
| `test-e2e-noretry` | `uv run grimoire e2e noretry` |
| `test-e2e-changed` | `uv run grimoire e2e changed` |
| `seed-data` | `uv run grimoire seed run` |
| `manage-users <sub>` | `uv run grimoire admin <sub>` |
| `set-admin <email>` | `uv run grimoire admin admin <email>` |
| `show-export-log` | `uv run grimoire export log` |
| `make-docs` | `uv run grimoire docs build` |

**`docs/deployment.md` — `grimoire-run` references:** The deployment docs use `grimoire-run <command>` for production invocations. `grimoire-run` is a bash wrapper at `/usr/local/bin/grimoire-run` that calls `uv run "$@"`. After migration, all `grimoire-run manage-users ...` commands become `grimoire-run grimoire admin ...`. Update the deployment.md usage examples with this mapping:

| Old (deployment.md) | New |
|-----|-----|
| `grimoire-run manage-users list` | `grimoire-run grimoire admin list` |
| `grimoire-run manage-users show <email>` | `grimoire-run grimoire admin show <email>` |
| `grimoire-run manage-users create <email>` | `grimoire-run grimoire admin create <email>` |
| `grimoire-run manage-users enroll ...` | `grimoire-run grimoire admin enroll ...` |
| `grimoire-run seed-data` | `grimoire-run grimoire seed run` |

The `grimoire-run` bash script itself (`uv run "$@"`) does not need modification — it passes all arguments through. The new invocation `grimoire-run grimoire admin list` becomes `uv run grimoire admin list` which works with the new entry point.

**Out of scope:** `.ed3d/implementation-plan-guidance.md` and the global `~/.claude/CLAUDE.md` contain old command references but are AI guidance documents, not user documentation. Update them in a followup commit or separate PR — do not include in this migration.

**Verification:**

Run: grep for old script names (`test-all`, `test-changed`, `test-e2e`, `seed-data`, `manage-users`, `set-admin`, `show-export-log`, `make-docs`) prefixed with `uv run` in `docs/` and `CLAUDE.md`.
Expected: Zero results (all updated to grimoire commands).

**Commit:** `docs: update all command references to grimoire CLI format`
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Final Verification — Full Suite and Complexity Gate

**Verifies:** cli-typer-211.AC4.1

**Files:** None (verification only)

**Implementation:**

Run the full verification suite:

1. `uv run complexipy src/promptgrimoire/cli/ --max-complexity-allowed 15`
   Expected: Zero failures.

2. `uv run grimoire test all`
   Expected: All tests pass.

3. `uv run grimoire --help`
   Expected: Lists all 6 sub-apps.

4. `uv run grimoire admin --help`
   Expected: Lists all 8 admin subcommands.

5. `uv run pytest tests/unit/test_cli_typer.py -v`
   Expected: All CliRunner help tests pass.

6. Verify no old entry points work — the removed `test-all`, `seed-data`, and `manage-users` script entries should all fail with "No such command" or similar.

**No commit** — verification only.
<!-- END_TASK_5 -->

## UAT Steps

1. [ ] Run `uv run grimoire --help` — lists all 6 sub-apps
2. [ ] Run `uv run grimoire test all` — full test suite passes
3. [ ] Run `uv run grimoire admin list --help` — admin commands work
4. [ ] Run `uv run grimoire seed run --help` — seed command works
5. [ ] Run `uv run complexipy src/promptgrimoire/cli/ --max-complexity-allowed 15` — zero failures
6. [ ] Confirm old script entry points (`test-all`, `seed-data`) no longer work
7. [ ] Check CLAUDE.md has updated commands

## Evidence Required

- [ ] `uv run grimoire --help` output
- [ ] `uv run complexipy src/promptgrimoire/cli/ --max-complexity-allowed 15` output
- [ ] Full test suite green via `uv run grimoire test all`
- [ ] Old entry points confirmed removed
