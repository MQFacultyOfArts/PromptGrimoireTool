# CLI Typer Migration Implementation Plan — Phase 2

**Goal:** Migrate the `manage-users` argparse subcommands and `set-admin` to Typer, converting 8 subcommands into `@admin_app.command()` functions.

**Architecture:** Move all `_cmd_*` async functions, helper functions (`_find_course`, `_require_user`, `_require_course`, `_update_stytch_metadata`, `_format_last_login`), and the command dispatch logic from `cli_legacy.py` into `cli/admin.py`. Each argparse subcommand becomes a Typer command with `typer.Argument()` / `typer.Option()` parameter declarations. Async functions keep the existing `asyncio.run()` wrapper pattern. Tests updated to use new import paths and CliRunner for argument semantics.

**Tech Stack:** Typer, asyncio, Rich Console

**Scope:** Phase 2 of 6 from original design

**Codebase verified:** 2026-03-02

---

## Acceptance Criteria Coverage

### cli-typer-211.AC2: Typer Framework
- **cli-typer-211.AC2.1 Success:** All commands use `typer.Argument()` / `typer.Option()` for parameter declaration
- **cli-typer-211.AC2.2 Success:** `--help` flag renders auto-generated help text for every command and sub-app

### cli-typer-211.AC3: Single Entry Point
- **cli-typer-211.AC3.4 Success:** `set-admin` entry point is removed entirely (no alias)

### cli-typer-211.AC5: Tests Pass and Expand
- **cli-typer-211.AC5.3 Success:** `test_manage_users.py` `_cmd_*` function tests pass with import from `promptgrimoire.cli.admin`
- **cli-typer-211.AC5.5 Success:** `CliRunner` help tests exist for `grimoire admin` (partial — other sub-apps covered in Phase 3)
- **cli-typer-211.AC5.6 Failure:** Old `_build_user_parser` tests are removed (argparse no longer exists)
- **cli-typer-211.AC5.7 Success:** Admin command tests verify argument semantics via `CliRunner` (not just help rendering) — e.g., `--remove` flag is received by `_cmd_admin`, `--role` option is forwarded correctly

### cli-typer-211.AC6: Argument Compatibility
- **cli-typer-211.AC6.1 ~~Success~~ NOT IMPLEMENTED:** Design states `grimoire admin list --semester S1-2026` but `_cmd_list` has no `--semester` parameter. The existing argparse `list` subcommand only accepts `--all`. This AC is aspirational — the parameter does not exist in the current implementation and is not added by this migration.
- **cli-typer-211.AC6.2 Success:** `grimoire admin show user@example.com` accepts positional email argument
- **cli-typer-211.AC6.3 Success:** `grimoire admin enroll` requires the same positional/option args as before

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Populate cli/admin.py with Typer Commands and Helpers

**Verifies:** cli-typer-211.AC2.1, cli-typer-211.AC2.2, cli-typer-211.AC6.2, cli-typer-211.AC6.3

**Files:**
- Modify: `src/promptgrimoire/cli/admin.py` (replace placeholder)

**Implementation:**

Replace the placeholder in `admin.py` with the full admin sub-app. Move these functions from `cli_legacy.py` (formerly `cli.py`):

**Helper functions (copy verbatim, adjust imports):**
- `_format_last_login` (lines 1796-1800)
- `_find_course` (lines 1867-1878)
- `_require_user` (lines 1881-1890)
- `_require_course` (lines 1893-1899)
- `_update_stytch_metadata` (lines 1992-2030)

**Command functions (copy verbatim, adjust imports):**
- `_cmd_list` (lines 1902-1933)
- `_cmd_create` (lines 1936-1951)
- `_cmd_show` (lines 1954-1989)
- `_cmd_admin` (lines 2033-2052)
- `_cmd_instructor` (lines 2055-2077)
- `_cmd_enroll` (lines 2080-2099)
- `_cmd_unenroll` (lines 2102-2120)
- `_cmd_role` (lines 2123-2148)

**For each command, create a sync Typer wrapper** that maps argparse arguments to `typer.Argument()` / `typer.Option()` and calls `asyncio.run()`. The argument mapping:

| Old argparse | Typer command | Arguments |
|---|---|---|
| `list --all` | `list_users(*, include_all: bool = typer.Option(False, "--all"))` | `--all` flag |
| `show <email>` | `show(email: str = typer.Argument(...))` | positional email |
| `create <email> --name` | `create(email: str = typer.Argument(...), name: str \| None = typer.Option(None))` | positional + option |
| `admin <email> --remove` | `admin(email: str = typer.Argument(...), remove: bool = typer.Option(False, "--remove"))` | positional + flag |
| `instructor <email> --remove` | `instructor(email: str = typer.Argument(...), remove: bool = typer.Option(False, "--remove"))` | positional + flag |
| `enroll <email> <code> <semester> --role` | `enroll(email: str, code: str, semester: str, role: str = typer.Option("student"))` | 3 positional + option |
| `unenroll <email> <code> <semester>` | `unenroll(email: str, code: str, semester: str)` | 3 positional |
| `role <email> <code> <semester> <new_role>` | `role(email: str, code: str, semester: str, new_role: str)` | 4 positional |

**Important:** The `list` command must be named `list_users` in Python (since `list` is a builtin) but registered as `@admin_app.command("list")` in Typer to preserve the CLI-facing name.

**Important:** AC6.1 mentions `--semester S1-2026` for the `list` command, but the existing argparse `list` command only has `--all`. Check if `--semester` filtering exists in `_cmd_list`. If not, the AC may be aspirational. The existing `_cmd_list` function signature is `async def _cmd_list(*, include_all: bool = False, console: Console | None = None)` — no semester parameter. **Do not add parameters that don't exist in the current implementation.**

Each Typer wrapper follows this pattern:
```python
@admin_app.command("list")
def list_users(
    include_all: bool = typer.Option(False, "--all", help="Include users who haven't logged in"),
) -> None:
    """List all users."""
    asyncio.run(_cmd_list(include_all=include_all))
```

**Verification:**

Run: `uv run grimoire admin --help`
Expected: Shows all 8 subcommands with help text.

Run: `uv run grimoire admin list --help`
Expected: Shows `--all` option.

**Commit:** `feat: populate admin.py with typer commands migrated from argparse`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Update Admin Tests for New Import Paths and Add CliRunner Tests

**Verifies:** cli-typer-211.AC5.3, cli-typer-211.AC5.5, cli-typer-211.AC5.6, cli-typer-211.AC5.7

**Files:**
- Modify: `tests/unit/test_manage_users.py`

**Implementation:**

1. **Update imports:** Change `from promptgrimoire.cli_legacy import` to `from promptgrimoire.cli.admin import` for all `_cmd_*` functions and helpers.

2. **Update `_CLI` constant:** Change from `"promptgrimoire.cli_legacy"` to `"promptgrimoire.cli.admin"` (used as patch target throughout).

3. **Remove `TestUserParserSubcommands` class entirely** (lines 30-99). This class tests `_build_user_parser()` which no longer exists. Satisfies AC5.6.

4. **Add new `TestAdminCliRunner` class** with CliRunner tests that verify argument semantics (not just help rendering). These replace the argparse parser tests and satisfy AC5.7.

**Testing:**

Tests must verify each AC listed above:
- cli-typer-211.AC5.3: All existing `_cmd_*` tests pass with import from `promptgrimoire.cli.admin`
- cli-typer-211.AC5.5: CliRunner help test for `grimoire admin`
- cli-typer-211.AC5.6: `_build_user_parser` tests removed — importing it should fail
- cli-typer-211.AC5.7: CliRunner tests verify `--remove` flag reaches `_cmd_admin`, `--role` option forwards correctly, positional args work

CliRunner tests should patch the underlying `_cmd_*` functions to verify argument forwarding without hitting the database. Example pattern:

```python
from typer.testing import CliRunner
from promptgrimoire.cli import app

runner = CliRunner()

def test_admin_remove_flag_forwarded(self):
    """--remove flag is received by _cmd_admin."""
    with patch(f"{_CLI}._cmd_admin", new_callable=AsyncMock) as mock:
        result = runner.invoke(app, ["admin", "admin", "user@test.com", "--remove"])
        assert result.exit_code == 0
        mock.assert_called_once_with(email="user@test.com", remove=True)
```

Follow existing test patterns in the file for consistency (use `_make_user()`, `_make_course()` helpers, patch DB layer).

**Verification:**

Run: `uv run pytest tests/unit/test_manage_users.py -v`
Expected: All tests pass.

**Commit:** `test: update admin tests for typer imports and add CliRunner argument tests`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_3 -->
### Task 3: Remove set-admin Entry Point and Legacy Admin Code

**Verifies:** cli-typer-211.AC3.4

**Files:**
- Modify: `pyproject.toml` (remove `set-admin` entry point)
- Modify: `src/promptgrimoire/cli_legacy.py` (remove `set_admin`, `manage_users`, `_build_user_parser`, and all `_cmd_*`/helper functions that were copied to admin.py)

**Implementation:**

1. Remove `set-admin = "promptgrimoire.cli_legacy:set_admin"` from `[project.scripts]` in pyproject.toml.

2. Remove `manage-users = "promptgrimoire.cli_legacy:manage_users"` from `[project.scripts]` in pyproject.toml. (The old entry point is no longer needed — `grimoire admin` replaces it.)

3. In `cli_legacy.py`, delete the following functions (they now live in `cli/admin.py`):
   - `_format_last_login` (lines 1796-1800)
   - `_build_user_parser` (lines 1803-1864)
   - `_find_course` (lines 1867-1878)
   - `_require_user` (lines 1881-1890)
   - `_require_course` (lines 1893-1899)
   - `_cmd_list` (lines 1902-1933)
   - `_cmd_create` (lines 1936-1951)
   - `_cmd_show` (lines 1954-1989)
   - `_update_stytch_metadata` (lines 1992-2030)
   - `_cmd_admin` (lines 2033-2052)
   - `_cmd_instructor` (lines 2055-2077)
   - `_cmd_enroll` (lines 2080-2099)
   - `_cmd_unenroll` (lines 2102-2120)
   - `_cmd_role` (lines 2123-2148)
   - `manage_users` (lines 2151-2209)
   - `set_admin` (lines 2212-2238)

4. Run `uv sync` to pick up the removed entry points.

**Verification:**

Run: `uv run grimoire admin list --help`
Expected: Works correctly via new path.

Run: `uv run grimoire admin admin test@example.com 2>&1 || echo "Entry point removed"`
Expected: Command not found (entry removed).

Run: `uv run grimoire test all`
Expected: All tests pass.

**Commit:** `refactor: remove legacy admin code from cli_legacy.py and old entry points`
<!-- END_TASK_3 -->

## UAT Steps

1. [ ] Run `uv run grimoire admin --help` — should show all 8 subcommands
2. [ ] Run `uv run grimoire admin list --help` — should show `--all` option
3. [ ] Run `uv run grimoire admin show --help` — should show positional email argument
4. [ ] Run `uv run grimoire admin enroll --help` — should show email, code, semester positional args and `--role` option
5. [ ] Run `uv run pytest tests/unit/test_manage_users.py -v` — all tests pass
6. [ ] Confirm `set-admin` entry point no longer works

## Evidence Required

- [ ] `uv run grimoire admin --help` output
- [ ] Test output showing green for test_manage_users.py
