# CLI Typer Migration Implementation Plan — Phase 1

**Goal:** Add Typer as a direct dependency and create the `cli/` package skeleton with placeholder sub-apps.

**Architecture:** Create `src/promptgrimoire/cli/` as a Python package with `__init__.py` containing the root `typer.Typer()` app and sub-app registrations. Empty module stubs for each domain. Old `cli.py` monolith remains operational.

**Tech Stack:** Typer (already installed as transitive dep of complexipy at 0.24.1), uv

**Scope:** Phase 1 of 6 from original design

**Codebase verified:** 2026-03-02

---

## Acceptance Criteria Coverage

This phase is infrastructure — no ACs are verified by tests. Verification is operational.

### cli-typer-211.AC1: Module Structure
- **cli-typer-211.AC1.1 Success:** `src/promptgrimoire/cli/` is a Python package with `__init__.py`, `testing.py`, `e2e.py`, `admin.py`, `seed.py`, `export.py`, `docs.py` — **partially addressed** (files created but empty)

### cli-typer-211.AC3: Single Entry Point
- **cli-typer-211.AC3.1 Success:** `uv run grimoire --help` lists all sub-apps (test, e2e, admin, seed, export, docs) — **addressed**
- **cli-typer-211.AC3.2 Success:** `pyproject.toml` has `grimoire = "promptgrimoire.cli:app"` as the CLI entry point — **addressed**

**Verifies:** None (infrastructure phase — operational verification only)

---

<!-- START_TASK_1 -->
### Task 1: Add Typer as Direct Dependency

**Files:**
- Modify: `pyproject.toml:19-34` (dependencies list)

**Step 1: Add typer to dependencies**

Add `"typer>=0.15.0",` to the dependencies list in `pyproject.toml` at line 33 (before the closing `]`). Typer 0.24.1 is already installed as a transitive dependency of complexipy, so this just makes it explicit.

```toml
dependencies = [
    "nicegui==3.8.0",  # pinned: 3.8.0 includes our upstream fixes (#5805, #5806, #5749)
    "sqlmodel>=0.0.22",
    "pycrdt>=0.10",
    "stytch>=11.0",
    "pydantic>=2.10",
    "pydantic-settings>=2.7",
    "python-dotenv>=1.0",  # Required by pydantic-settings for .env file reading
    "asyncpg>=0.30",
    "anthropic>=0.76.0",
    "alembic>=1.18.0",
    "selectolax>=0.4.6",
    "emoji>=2.0.0",
    "lxml>=6.0",
    "coolname>=3.0.0",
    "typer>=0.15.0",
]
```

Note: The design plan says `typer[all]` but since Typer 0.12.1+ the `[all]` extra no longer exists — `typer` alone includes Rich and Shellingham.

**Step 2: Add grimoire entry point**

Add the `grimoire` entry point to `[project.scripts]` in `pyproject.toml` at line 50 (before `load-test-data`). Keep all existing entries — they will be removed in Phase 6.

```toml
[project.scripts]
promptgrimoire = "promptgrimoire:main"
test-changed = "promptgrimoire.cli:test_changed"
test-all = "promptgrimoire.cli:test_all"
test-e2e = "promptgrimoire.cli:test_e2e"
test-e2e-slow = "promptgrimoire.cli:test_e2e_slow"
test-e2e-noretry = "promptgrimoire.cli:test_e2e_noretry"
test-e2e-changed = "promptgrimoire.cli:test_e2e_changed"
test-all-fixtures = "promptgrimoire.cli:test_all_fixtures"
seed-data = "promptgrimoire.cli:seed_data"
set-admin = "promptgrimoire.cli:set_admin"
manage-users = "promptgrimoire.cli:manage_users"
show-export-log = "promptgrimoire.cli:show_export_log"
make-docs = "promptgrimoire.cli:make_docs"
grimoire = "promptgrimoire.cli:app"
load-test-data = "promptgrimoire.cli_loadtest:load_test_data"
```

**Step 3: Verify**

Run: `uv sync`
Expected: Dependencies resolve and install without errors.

**Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "deps: add typer as direct dependency and grimoire entry point"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Create cli/ Package with Root App and Stubs

**Files:**
- Create: `src/promptgrimoire/cli/__init__.py`
- Create: `src/promptgrimoire/cli/_shared.py`
- Create: `src/promptgrimoire/cli/testing.py`
- Create: `src/promptgrimoire/cli/e2e.py`
- Create: `src/promptgrimoire/cli/admin.py`
- Create: `src/promptgrimoire/cli/seed.py`
- Create: `src/promptgrimoire/cli/export.py`
- Create: `src/promptgrimoire/cli/docs.py`

**Important:** Creating `src/promptgrimoire/cli/__init__.py` will make Python treat `cli` as a package instead of the module `cli.py`. Both cannot coexist — Python will prefer the package (directory) over the module (file). This is fine because the old `cli.py` entry points (`promptgrimoire.cli:test_all` etc.) will continue to resolve through the package's `__init__.py` during the transition, BUT only if the old functions are importable from there. Since we are NOT re-exporting old functions from `__init__.py`, the old entry points will break.

**Resolution:** The old entry points must remain pointing at the old `cli.py`. To avoid the package/module conflict, we rename the old `cli.py` to `cli_legacy.py` and update the old entry points to point there. The new `cli/` package coexists cleanly.

**Step 1: Rename cli.py to cli_legacy.py**

```bash
git mv src/promptgrimoire/cli.py src/promptgrimoire/cli_legacy.py
```

**Step 2: Update all old entry points in pyproject.toml**

Change the module path for all old entry points from `promptgrimoire.cli:` to `promptgrimoire.cli_legacy:`:

```toml
[project.scripts]
promptgrimoire = "promptgrimoire:main"
test-changed = "promptgrimoire.cli_legacy:test_changed"
test-all = "promptgrimoire.cli_legacy:test_all"
test-e2e = "promptgrimoire.cli_legacy:test_e2e"
test-e2e-slow = "promptgrimoire.cli_legacy:test_e2e_slow"
test-e2e-noretry = "promptgrimoire.cli_legacy:test_e2e_noretry"
test-e2e-changed = "promptgrimoire.cli_legacy:test_e2e_changed"
test-all-fixtures = "promptgrimoire.cli_legacy:test_all_fixtures"
seed-data = "promptgrimoire.cli_legacy:seed_data"
set-admin = "promptgrimoire.cli_legacy:set_admin"
manage-users = "promptgrimoire.cli_legacy:manage_users"
show-export-log = "promptgrimoire.cli_legacy:show_export_log"
make-docs = "promptgrimoire.cli_legacy:make_docs"
grimoire = "promptgrimoire.cli:app"
load-test-data = "promptgrimoire.cli_loadtest:load_test_data"
```

**Step 3: Update test imports**

4 test files import from `promptgrimoire.cli`. Update them to `promptgrimoire.cli_legacy`:

- `tests/unit/test_manage_users.py:34` — change `from promptgrimoire.cli import _build_user_parser` to `from promptgrimoire.cli_legacy import _build_user_parser`. Also update the `_CLI` constant at its definition to `"promptgrimoire.cli_legacy"`.
- `tests/unit/test_cli_header.py:11` — change `from promptgrimoire.cli import _build_test_header` to `from promptgrimoire.cli_legacy import _build_test_header`
- `tests/unit/test_cli_parallel.py:10` — change `from promptgrimoire.cli import _allocate_ports` to `from promptgrimoire.cli_legacy import _allocate_ports`
- `tests/integration/test_acl_reference_tables.py:48,57` — change both `from promptgrimoire.cli import seed_data` to `from promptgrimoire.cli_legacy import seed_data`

**Step 4: Check for internal imports within cli.py itself**

Search for any `from promptgrimoire.cli import` or `import promptgrimoire.cli` references within cli.py (now cli_legacy.py) that might self-reference. These would need updating too.

**Step 5: Create `src/promptgrimoire/cli/__init__.py`**

```python
"""PromptGrimoire CLI — unified development tools."""

import typer

from promptgrimoire.cli.admin import admin_app
from promptgrimoire.cli.docs import docs_app
from promptgrimoire.cli.e2e import e2e_app
from promptgrimoire.cli.export import export_app
from promptgrimoire.cli.seed import seed_app
from promptgrimoire.cli.testing import test_app

app = typer.Typer(name="grimoire", help="PromptGrimoire development tools.")
app.add_typer(test_app, name="test")
app.add_typer(e2e_app, name="e2e")
app.add_typer(admin_app, name="admin")
app.add_typer(seed_app, name="seed")
app.add_typer(export_app, name="export")
app.add_typer(docs_app, name="docs")
```

**Step 6: Create stub modules**

Each stub module defines a `typer.Typer()` sub-app with a placeholder command.

`src/promptgrimoire/cli/_shared.py`:
```python
"""Cross-module infrastructure shared between testing and e2e modules."""
```

`src/promptgrimoire/cli/testing.py`:
```python
"""Unit/integration test commands."""

import typer

test_app = typer.Typer(help="Unit and integration test commands.")


@test_app.command()
def placeholder() -> None:
    """Placeholder — will be replaced in Phase 4."""
    typer.echo("Not yet implemented.")
```

`src/promptgrimoire/cli/e2e.py`:
```python
"""E2E test commands."""

import typer

e2e_app = typer.Typer(help="End-to-end test commands.")


@e2e_app.command()
def placeholder() -> None:
    """Placeholder — will be replaced in Phase 5."""
    typer.echo("Not yet implemented.")
```

`src/promptgrimoire/cli/admin.py`:
```python
"""User and role management commands."""

import typer

admin_app = typer.Typer(help="User, role, and course enrollment management.")


@admin_app.command()
def placeholder() -> None:
    """Placeholder — will be replaced in Phase 2."""
    typer.echo("Not yet implemented.")
```

`src/promptgrimoire/cli/seed.py`:
```python
"""Development data seeding commands."""

import typer

seed_app = typer.Typer(help="Seed development data.")


@seed_app.command()
def placeholder() -> None:
    """Placeholder — will be replaced in Phase 3."""
    typer.echo("Not yet implemented.")
```

`src/promptgrimoire/cli/export.py`:
```python
"""Export log inspection commands."""

import typer

export_app = typer.Typer(help="Export log inspection.")


@export_app.command()
def placeholder() -> None:
    """Placeholder — will be replaced in Phase 3."""
    typer.echo("Not yet implemented.")
```

`src/promptgrimoire/cli/docs.py`:
```python
"""Documentation generation and serving commands."""

import typer

docs_app = typer.Typer(help="Documentation generation and serving.")


@docs_app.command()
def placeholder() -> None:
    """Placeholder — will be replaced in Phase 3."""
    typer.echo("Not yet implemented.")
```

**Step 7: Verify operationally**

Run: `uv sync`
Expected: Clean install, no import errors.

Run: `uv run python -c "from promptgrimoire.cli import app; print('import OK')"`
Expected: Prints "import OK" with no errors. This catches import-time failures in stub modules before exercising the entrypoint.

Run: `uv run grimoire --help`
Expected: Output shows "PromptGrimoire development tools." with sub-apps listed: test, e2e, admin, seed, export, docs.

Run: `uv run grimoire test --help`
Expected: Output shows test sub-app help with placeholder command.

Run: `uv run grimoire test all`
Expected: All 3198+ tests pass — the old entry points now resolve through `cli_legacy.py`.

**Step 8: Commit**

```bash
git add src/promptgrimoire/cli_legacy.py src/promptgrimoire/cli/ pyproject.toml tests/unit/test_manage_users.py tests/unit/test_cli_header.py tests/unit/test_cli_parallel.py tests/integration/test_acl_reference_tables.py
git commit -m "feat: create cli/ package skeleton with typer sub-apps

Rename cli.py to cli_legacy.py to avoid package/module conflict.
Old entry points updated to cli_legacy, new grimoire entry point
added pointing to cli/ package."
```
<!-- END_TASK_2 -->

## UAT Steps

1. [ ] Run `uv sync` — should complete without errors
2. [ ] Run `uv run grimoire --help` — should show "PromptGrimoire development tools." and list sub-apps (test, e2e, admin, seed, export, docs)
3. [ ] Run `uv run grimoire test --help` — should show test sub-app help
4. [ ] Run `uv run grimoire test all` — all existing tests should pass
5. [ ] Run `uv run grimoire test changed` — should work as before

## Evidence Required

- [ ] `uv run grimoire --help` output showing all sub-apps
- [ ] `uv run grimoire test all` output showing green
