# CLI Typer Migration Implementation Plan — Phase 3

**Goal:** Migrate the three simplest command groups — seed, export, docs — from `cli_legacy.py` to their own Typer modules.

**Architecture:** Each command becomes a `@<sub>_app.command()` with Typer arguments/options replacing raw `sys.argv` parsing and argparse. `docs.py` temporarily imports `_pre_test_db_cleanup`, `_start_e2e_server`, and `_stop_e2e_server` from `cli_legacy` — these move to `_shared.py`/`e2e.py` in Phases 4-5. The `test_cli_typer.py` file provides CliRunner help tests for all sub-apps.

**Tech Stack:** Typer, asyncio, Rich Console

**Scope:** Phase 3 of 6 from original design

**Codebase verified:** 2026-03-02

**Codebase discrepancy:** Design mentions `_generate_guide_index_and_nav()` — this function does not exist in the codebase. The actual helper is `_make_docs_build_and_serve(action)`.

---

## Acceptance Criteria Coverage

### cli-typer-211.AC1: Module Structure
- **cli-typer-211.AC1.1 Success:** `src/promptgrimoire/cli/` is a Python package with `__init__.py`, `testing.py`, `e2e.py`, `admin.py`, `seed.py`, `export.py`, `docs.py` — **seed, export, docs populated**

### cli-typer-211.AC2: Typer Framework
- **cli-typer-211.AC2.1 Success:** All commands use `typer.Argument()` / `typer.Option()` for parameter declaration
- **cli-typer-211.AC2.3 Success:** No `argparse` or raw `sys.argv` usage in `cli/` package (except `ctx.args` for pytest passthrough)

### cli-typer-211.AC3: Single Entry Point
- **cli-typer-211.AC3.1 Success:** `uv run grimoire --help` lists all sub-apps (test, e2e, admin, seed, export, docs) — **partially (seed, export, docs now functional)**

### cli-typer-211.AC5: Tests Pass and Expand
- **cli-typer-211.AC5.4 Success:** `test_make_docs.py` passes with import from `promptgrimoire.cli.docs`
- **cli-typer-211.AC5.5 Success:** `CliRunner` help tests exist for `grimoire`, `grimoire test`, `grimoire e2e`, `grimoire admin`, `grimoire seed`, `grimoire export`, `grimoire docs`

### cli-typer-211.AC6: Argument Compatibility
- **cli-typer-211.AC6.4 Success:** `grimoire docs build serve` accepts the optional action argument

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Populate cli/seed.py with Typer Commands

**Verifies:** cli-typer-211.AC2.1

**Files:**
- Modify: `src/promptgrimoire/cli/seed.py` (replace placeholder)

**Implementation:**

Move these functions from `cli_legacy.py`:
- `_seed_user_and_course` (lines 2241-2273)
- `_seed_enrolment_and_weeks` (lines 2276-2349)
- `_seed_tags_for_activity` (lines 2352-2442)
- `seed_data` (lines 2445-2478) — becomes the Typer command wrapper

The existing `seed_data()` function contains an inner async `_seed()` function and calls `asyncio.run(_seed())`. Convert to Typer pattern:

```python
@seed_app.command("run")
def run() -> None:
    """Seed the database with development data. Idempotent."""
    asyncio.run(_seed())
```

The `_seed()` inner function and all helper functions move as-is.

**Note:** `tests/integration/test_acl_reference_tables.py` imports `seed_data` for `inspect.getsource()` analysis. After Phase 1, this import already points to `cli_legacy`. When we move `seed_data` to `cli/seed.py`, that test's import (`from promptgrimoire.cli_legacy import seed_data`) still works because the function remains in `cli_legacy.py` until Phase 6. The `inspect.getsource()` test checks that `seed_data` doesn't reference certain models — it doesn't care which module the function lives in, so pointing at the legacy copy is fine for now.

**Verification:**

Run: `uv run grimoire seed run --help`
Expected: Shows "Seed the database with development data. Idempotent."

**Commit:** `feat: populate seed.py with typer command migrated from cli_legacy`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Populate cli/export.py with Typer Commands

**Verifies:** cli-typer-211.AC2.1, cli-typer-211.AC2.3

**Files:**
- Modify: `src/promptgrimoire/cli/export.py` (replace placeholder)

**Implementation:**

Move these functions from `cli_legacy.py`:
- `_find_export_dir` (lines 2481-2500)
- `_show_error_context` (lines 2503-2540)
- `show_export_log` (lines 2543-2593) — becomes Typer command

The existing `show_export_log()` uses raw `sys.argv` parsing. Convert to Typer:

```python
@export_app.command("log")
def log(
    user_id: str | None = typer.Argument(None, help="User ID (default: most recent export)"),
    tex: bool = typer.Option(False, "--tex", help="Show .tex source instead of log"),
    both: bool = typer.Option(False, "--both", help="Show error context from log and tex"),
) -> None:
    """Show the most recent PDF export LaTeX log."""
    ...
```

This eliminates the `sys.argv` manual parsing at lines 2556-2560.

**Verification:**

Run: `uv run grimoire export log --help`
Expected: Shows options for `--tex`, `--both`, and optional `user_id` argument.

**Commit:** `feat: populate export.py with typer command replacing sys.argv parsing`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: Populate cli/docs.py with Typer Commands

**Verifies:** cli-typer-211.AC2.1, cli-typer-211.AC2.3, cli-typer-211.AC6.4

**Files:**
- Modify: `src/promptgrimoire/cli/docs.py` (replace placeholder)

**Implementation:**

Move these functions from `cli_legacy.py`:
- `_make_docs_build_and_serve` (lines 2596-2625)
- `make_docs` (lines 2628-2704) — becomes Typer command

The existing `make_docs()` uses argparse for an optional positional arg. Convert to Typer:

```python
@docs_app.command("build")
def build(
    action: str | None = typer.Argument(None, help="Post-build action: serve or gh-deploy"),
) -> None:
    """Generate documentation guides, build MkDocs site, create PDFs."""
    ...
```

**Important dependency:** `make_docs()` calls `_pre_test_db_cleanup()`, `_start_e2e_server(port)`, and `_stop_e2e_server(process)`. These functions still live in `cli_legacy.py`. For Phase 3, `docs.py` must import them from `cli_legacy`:

```python
from promptgrimoire.cli_legacy import (
    _pre_test_db_cleanup,
    _start_e2e_server,
    _stop_e2e_server,
)
```

These imports will be updated in Phases 4-5 when the functions move to their final homes (`_shared.py` and `e2e.py`).

**Verification:**

Run: `uv run grimoire docs build --help`
Expected: Shows optional action argument.

Run: `uv run grimoire docs build serve --help` (should not error on the "serve" arg)

**Commit:** `feat: populate docs.py with typer command replacing argparse`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Update test_make_docs.py Imports

**Verifies:** cli-typer-211.AC5.4

**Files:**
- Modify: `tests/unit/test_make_docs.py`

**Implementation:**

The test file currently does `import promptgrimoire.cli as cli_module` (line 14) and patches functions on that module object. Update to import from the new location:

1. Change `import promptgrimoire.cli as cli_module` to `import promptgrimoire.cli.docs as cli_module`

2. Update patches on shared infrastructure functions that are imported into docs.py from cli_legacy:
   - `patch.object(cli_module, "_pre_test_db_cleanup")` — this patches the attribute on the docs module. Since docs.py imports `_pre_test_db_cleanup` from `cli_legacy`, the patch target should be `"promptgrimoire.cli.docs._pre_test_db_cleanup"` (patch where used, not where defined).
   - Same for `_start_e2e_server` and `_stop_e2e_server`

3. Update `_guides_dir` computation: `Path(cli_module.__file__).resolve().parents[2]` — this resolves to the project root via the module file path. With `cli/docs.py` the nesting is one level deeper, so it should be `.parents[3]` instead of `.parents[2]`.

**Testing:**

Tests must verify:
- cli-typer-211.AC5.4: All existing make_docs tests pass with import from `promptgrimoire.cli.docs`

**Verification (run BEFORE committing — verifies the .parents depth fix):**

Run: `uv run pytest tests/unit/test_make_docs.py -v`
Expected: All tests pass. If path-related tests fail, the `.parents` depth is wrong — investigate.

**Commit:** (only after tests pass) `test: update test_make_docs.py imports for cli.docs module`
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_TASK_5 -->
### Task 5: Create test_cli_typer.py with CliRunner Help Tests

**Verifies:** cli-typer-211.AC5.5, cli-typer-211.AC1.3

**Files:**
- Create: `tests/unit/test_cli_typer.py`

**Implementation:**

Create a test file with `CliRunner` help tests for the root app and all sub-apps. This verifies that all Typer sub-apps are properly registered and render help.

```python
from typer.testing import CliRunner
from promptgrimoire.cli import app

runner = CliRunner()
```

Tests needed (one per sub-app):
- `test_grimoire_help` — `runner.invoke(app, ["--help"])`, assert exit_code 0, assert all sub-app names appear in output
- `test_grimoire_test_help` — `runner.invoke(app, ["test", "--help"])`, assert exit_code 0
- `test_grimoire_e2e_help` — `runner.invoke(app, ["e2e", "--help"])`, assert exit_code 0
- `test_grimoire_admin_help` — `runner.invoke(app, ["admin", "--help"])`, assert exit_code 0
- `test_grimoire_seed_help` — `runner.invoke(app, ["seed", "--help"])`, assert exit_code 0
- `test_grimoire_export_help` — `runner.invoke(app, ["export", "--help"])`, assert exit_code 0
- `test_grimoire_docs_help` — `runner.invoke(app, ["docs", "--help"])`, assert exit_code 0

**Import boundary regression guard (AC1.3):**
- `test_old_import_path_not_exported` — verifies that `promptgrimoire.cli` does NOT export legacy function names like `test_all`, `test_changed`, `seed_data`, `manage_users`. Use `importlib.import_module("promptgrimoire.cli")` and assert `not hasattr(mod, "test_all")` etc. This guards against accidental re-export from `__init__.py`.

Each test verifies exit_code == 0 and that relevant keywords appear in the output.

**Testing:**

Tests must verify:
- cli-typer-211.AC5.5: CliRunner help tests exist for all 7 entry points
- cli-typer-211.AC1.3: Old import paths raise `AttributeError` (not exported from package)

**Verification:**

Run: `uv run pytest tests/unit/test_cli_typer.py -v`
Expected: All 8 tests pass.

**Commit:** `test: add CliRunner help tests and import boundary guard for all typer sub-apps`
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Remove Migrated Functions from cli_legacy.py

**Files:**
- Modify: `src/promptgrimoire/cli_legacy.py`
- Modify: `pyproject.toml` (remove old entry points)

**Implementation:**

1. In `pyproject.toml`, remove these entry points:
   - `seed-data = "promptgrimoire.cli_legacy:seed_data"`
   - `show-export-log = "promptgrimoire.cli_legacy:show_export_log"`
   - `make-docs = "promptgrimoire.cli_legacy:make_docs"`

2. In `cli_legacy.py`, delete:
   - `_seed_user_and_course` (lines 2241-2273)
   - `_seed_enrolment_and_weeks` (lines 2276-2349)
   - `_seed_tags_for_activity` (lines 2352-2442)
   - `seed_data` (lines 2445-2478)
   - `_find_export_dir` (lines 2481-2500)
   - `_show_error_context` (lines 2503-2540)
   - `show_export_log` (lines 2543-2593)
   - `_make_docs_build_and_serve` (lines 2596-2625)
   - `make_docs` (lines 2628-2704)

   **Do NOT delete** `_pre_test_db_cleanup`, `_start_e2e_server`, `_stop_e2e_server` — they are still needed by `docs.py` (imported from cli_legacy) and will move in Phases 4-5.

3. Update `test_acl_reference_tables.py` import: The `seed_data` function was removed from `cli_legacy.py` and now lives in `cli/seed.py`. Update the import:
   - Change `from promptgrimoire.cli_legacy import seed_data` to `from promptgrimoire.cli.seed import seed_data` (at lines 48 and 57)

4. Run `uv sync` to pick up entry point changes.

**Verification:**

Run: `uv run grimoire test all`
Expected: All tests pass.

Run: `uv run grimoire seed run --help`
Expected: Works.

**Commit:** `refactor: remove migrated seed/export/docs functions from cli_legacy`
<!-- END_TASK_6 -->

## UAT Steps

1. [ ] Run `uv run grimoire seed run --help` — shows seed help text
2. [ ] Run `uv run grimoire export log --help` — shows export help with `--tex`, `--both`, `user_id`
3. [ ] Run `uv run grimoire docs build --help` — shows optional action argument
4. [ ] Run `uv run pytest tests/unit/test_make_docs.py -v` — all tests pass
5. [ ] Run `uv run pytest tests/unit/test_cli_typer.py -v` — all 7 help tests pass
6. [ ] Run `uv run grimoire test all` — full suite passes

## Evidence Required

- [ ] `uv run grimoire --help` showing all sub-apps
- [ ] Test output showing green for test_cli_typer.py and test_make_docs.py
