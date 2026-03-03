# CLI Typer Migration — Test Requirements

Maps every acceptance criterion from the design plan to either an automated test or a documented human verification step.

**Source design:** `docs/design-plans/2026-03-02-cli-typer-211.md`
**Implementation phases:** `docs/implementation-plans/2026-03-02-cli-typer-211/phase_01.md` through `phase_06.md`

---

## Automated Tests

### cli-typer-211.AC1: Module Structure

| AC | Criterion | Test Type | Test File | Phase | Notes |
|----|-----------|-----------|-----------|-------|-------|
| AC1.1 | `src/promptgrimoire/cli/` is a Python package with `__init__.py`, `testing.py`, `e2e.py`, `admin.py`, `seed.py`, `export.py`, `docs.py` | Unit | `tests/unit/test_cli_typer.py` | P3 T5 | The CliRunner help tests (`test_grimoire_help`) implicitly verify that all sub-apps are importable and registered. A dedicated import-each-module test is not strictly needed because `test_grimoire_help` asserts all 6 sub-app names appear in `--help` output, which requires all modules to exist, define their `*_app`, and be registered in `__init__.py`. |
| AC1.2 | Old `src/promptgrimoire/cli.py` monolith is deleted | Unit | `tests/unit/test_cli_typer.py` | P6 T1 | The `test_old_import_path_not_exported` test (AC1.3 below) serves as the regression guard. If `cli.py` still existed as a module instead of a package, Python would resolve `promptgrimoire.cli` as the file rather than the package, and the import-boundary assertions would fail in unpredictable ways. The Phase 6 Task 1 verification (`ls cli_legacy.py`) is the primary check; automated coverage is via AC1.3. |
| AC1.3 | Importing `from promptgrimoire.cli import test_all` (old path) raises `ImportError` | Unit | `tests/unit/test_cli_typer.py` | P3 T5 | `test_old_import_path_not_exported` uses `importlib.import_module("promptgrimoire.cli")` and asserts `not hasattr(mod, "test_all")`, `not hasattr(mod, "seed_data")`, etc. This guards against accidental re-export from `__init__.py`. Added during finalization review (fix #33). |

### cli-typer-211.AC2: Typer Framework

| AC | Criterion | Test Type | Test File | Phase | Notes |
|----|-----------|-----------|-----------|-------|-------|
| AC2.1 | All commands use `typer.Argument()` / `typer.Option()` for parameter declaration | Unit | `tests/unit/test_manage_users.py`, `tests/unit/test_cli_typer.py` | P2 T2, P3 T5 | The CliRunner argument-semantics tests in `test_manage_users.py` (AC5.7) verify that Typer commands accept the expected arguments and forward them correctly. The help tests in `test_cli_typer.py` verify all commands render help without error. Together these confirm Typer parameter declarations are correct. No separate "audit all commands for typer.Argument usage" test is needed; the functional tests serve as the verification. |
| AC2.2 | `--help` flag renders auto-generated help text for every command and sub-app | Unit | `tests/unit/test_cli_typer.py` | P3 T5 | 7 tests: `test_grimoire_help`, `test_grimoire_test_help`, `test_grimoire_e2e_help`, `test_grimoire_admin_help`, `test_grimoire_seed_help`, `test_grimoire_export_help`, `test_grimoire_docs_help`. Each asserts `exit_code == 0` and relevant keywords in output. |
| AC2.3 | No `argparse` or raw `sys.argv` usage in `cli/` package (except `ctx.args` for pytest passthrough) | Unit | `tests/unit/test_cli_typer.py` | P3 T5 | **Not directly tested by a dedicated automated test.** See Human Verification section below. |
| AC2.4 | Pytest passthrough args (e.g., `-k test_foo -x`) are forwarded correctly via `ctx.args` | **None** | N/A | P4 T2, P5 T1 | See Human Verification section below. |

### cli-typer-211.AC3: Single Entry Point

| AC | Criterion | Test Type | Test File | Phase | Notes |
|----|-----------|-----------|-----------|-------|-------|
| AC3.1 | `uv run grimoire --help` lists all sub-apps (test, e2e, admin, seed, export, docs) | Unit | `tests/unit/test_cli_typer.py` | P3 T5 | `test_grimoire_help` asserts all 6 sub-app names appear in CliRunner output. |
| AC3.2 | `pyproject.toml` has `grimoire = "promptgrimoire.cli:app"` as the CLI entry point | **None** | N/A | P1 T1, P6 T2 | See Human Verification section below. |
| AC3.3 | Old `[project.scripts]` entries (test-all, test-changed, etc.) are removed | **None** | N/A | P6 T2 | See Human Verification section below. |
| AC3.4 | `set-admin` entry point is removed entirely (no alias) | **None** | N/A | P2 T3 | See Human Verification section below. |

### cli-typer-211.AC4: Complexity Compliance

| AC | Criterion | Test Type | Test File | Phase | Notes |
|----|-----------|-----------|-----------|-------|-------|
| AC4.1 | `complexipy src/promptgrimoire/cli/ --max-complexity-allowed 15` reports zero failures | Integration | N/A (CI verification step) | P6 T5 | Run as a verification command, not a pytest test. Could be added as a CI step. See Human Verification section for per-phase approach. |
| AC4.2 | `_stream_with_progress` cognitive complexity <= 15 | Integration | N/A (complexipy verification) | P4 T2 | Verified by `complexipy src/promptgrimoire/cli/testing.py --max-complexity-allowed 15`. Phase 4 Task 2 verification step. |
| AC4.3 | `_run_all_workers` cognitive complexity <= 15 | Integration | N/A (complexipy verification) | P5 T2 | Verified by `complexipy src/promptgrimoire/cli/e2e.py --max-complexity-allowed 15`. Phase 5 Task 2 verification step. |
| AC4.4 | `_run_fail_fast_workers` cognitive complexity <= 15 | Integration | N/A (complexipy verification) | P5 T2 | Same complexipy run as AC4.3. |
| AC4.5 | `_retry_parallel_failures` cognitive complexity <= 15 | Integration | N/A (complexipy verification) | P5 T2 | Same complexipy run as AC4.3. |

### cli-typer-211.AC5: Tests Pass and Expand

| AC | Criterion | Test Type | Test File | Phase | Notes |
|----|-----------|-----------|-----------|-------|-------|
| AC5.1 | `test_cli_header.py` passes with import from `promptgrimoire.cli._shared` | Unit | `tests/unit/test_cli_header.py` | P4 T3 | Import updated from `promptgrimoire.cli_legacy` to `promptgrimoire.cli._shared`. All 11 existing tests exercise `_build_test_header`. |
| AC5.2 | `test_cli_parallel.py` passes with import from `promptgrimoire.cli.e2e` | Unit | `tests/unit/test_cli_parallel.py` | P5 T3 | Import updated from `promptgrimoire.cli_legacy` to `promptgrimoire.cli.e2e`. All 3 existing tests exercise `_allocate_ports`. |
| AC5.3 | `test_manage_users.py` `_cmd_*` function tests pass with import from `promptgrimoire.cli.admin` | Unit | `tests/unit/test_manage_users.py` | P2 T2 | Import updated from `promptgrimoire.cli_legacy` to `promptgrimoire.cli.admin`. All existing `_cmd_*` tests continue to pass. |
| AC5.4 | `test_make_docs.py` passes with import from `promptgrimoire.cli.docs` | Unit | `tests/unit/test_make_docs.py` | P3 T4 | Import updated from `promptgrimoire.cli` to `promptgrimoire.cli.docs`. `.parents` depth adjusted from `[2]` to `[3]` due to deeper nesting. |
| AC5.5 | CliRunner help tests exist for `grimoire`, `grimoire test`, `grimoire e2e`, `grimoire admin`, `grimoire seed`, `grimoire export`, `grimoire docs` | Unit | `tests/unit/test_cli_typer.py` | P3 T5 | 7 CliRunner help tests, one per entry point and sub-app. |
| AC5.6 | Old `_build_user_parser` tests are removed (argparse no longer exists) | Unit | `tests/unit/test_manage_users.py` | P2 T2 | `TestUserParserSubcommands` class deleted. Verified by test file not containing `_build_user_parser` references. |
| AC5.7 | Admin command tests verify argument semantics via CliRunner (not just help rendering) | Unit | `tests/unit/test_manage_users.py` | P2 T2 | New `TestAdminCliRunner` class with tests that patch `_cmd_*` functions and invoke via CliRunner, asserting argument forwarding. Examples: `--remove` flag forwarded to `_cmd_admin`, `--role` option forwarded to `_cmd_enroll`, positional `email` forwarded to `_cmd_show`. |

### cli-typer-211.AC6: Argument Compatibility

| AC | Criterion | Test Type | Test File | Phase | Notes |
|----|-----------|-----------|-----------|-------|-------|
| AC6.1 | `grimoire admin list --semester S1-2026` accepts the same options as `manage-users list --semester S1-2026` | **NOT IMPLEMENTED** | N/A | N/A | **Struck as aspirational during design review.** The existing `_cmd_list` function only accepts `--all`; there is no `--semester` parameter in the current implementation. The design AC was written against an assumed interface that does not exist. This migration preserves existing functionality; it does not add new parameters. No test, no implementation. |
| AC6.2 | `grimoire admin show user@example.com` accepts positional email argument | Unit | `tests/unit/test_manage_users.py` | P2 T2 | CliRunner test invokes `["admin", "show", "user@example.com"]` and asserts `_cmd_show` receives `email="user@example.com"`. |
| AC6.3 | `grimoire admin enroll` requires the same positional/option args as before | Unit | `tests/unit/test_manage_users.py` | P2 T2 | CliRunner test invokes `["admin", "enroll", "user@test.com", "ARTS1000", "S1-2026", "--role", "student"]` and asserts all args forwarded. |
| AC6.4 | `grimoire docs build serve` accepts the optional action argument | Unit | `tests/unit/test_cli_typer.py` (or inline in `test_make_docs.py`) | P3 T3 | The `build` command accepts an optional `action` positional argument. The existing `test_make_docs.py` tests exercise the `make_docs()` function with action parameters. A CliRunner test verifying `["docs", "build", "serve"]` invokes without error would provide additional coverage. |

---

## Human Verification

These criteria cannot be fully automated (or automation would be fragile/low-value) and require manual verification during implementation or UAT.

### AC2.3: No argparse or raw sys.argv usage in cli/ package

**Justification:** A grep-based test for `argparse` and `sys.argv` strings would be brittle (false positives from comments, docstrings, or the legitimate `ctx.args` passthrough pattern). The real verification is that all commands work via Typer CliRunner without argparse, which is covered by AC2.1/AC2.2/AC5.5/AC5.7 tests.

**Verification approach:** During Phase 3 (Task 2 specifically eliminates `sys.argv` in `export.py`) and Phase 2 (eliminates argparse in `admin.py`), the implementer runs:
```bash
grep -rn "import argparse\|from argparse\|sys\.argv" src/promptgrimoire/cli/
```
Expected: zero results (or only comments/docstrings).

### AC2.4: Pytest passthrough args forwarded correctly via ctx.args

**Justification:** Testing pytest passthrough end-to-end requires spawning a subprocess that runs actual pytest, which is slow and environment-dependent (needs test files, database, etc.). The Typer `context_settings={"allow_extra_args": True}` pattern is a well-established Click/Typer feature. The implementation copies `ctx.args` directly to the subprocess command list.

**Verification approach:** During Phase 4 and Phase 5 UAT, the implementer runs:
```bash
uv run grimoire test all -k test_cli_header -x
```
and confirms the `-k test_cli_header -x` args are forwarded (only `test_cli_header` tests run, execution stops on first failure).

### AC3.2: pyproject.toml has correct grimoire entry point

**Justification:** Verifying the content of `pyproject.toml` with an automated test would mean parsing the TOML file in a test, which is over-engineering. The CliRunner tests (AC3.1) already prove the entry point works because they import `from promptgrimoire.cli import app` and invoke it.

**Verification approach:** Visual inspection of `pyproject.toml` during Phase 1 Task 1 and Phase 6 Task 2. The Phase 6 Task 5 verification step also runs `uv run grimoire --help` which only works if the entry point is configured correctly.

### AC3.3: Old [project.scripts] entries removed

**Justification:** The removal is a `pyproject.toml` edit. Automating verification would require parsing TOML in a test. Instead, the Phase 6 Task 5 verification confirms old commands fail.

**Verification approach:** During Phase 6 UAT, the implementer verifies the removed `test-all`, `seed-data`, and `manage-users` script entry points all fail with "command not found" or equivalent. Phase 6 Task 2 explicitly lists the removal.

### AC3.4: set-admin entry point removed entirely

**Justification:** Same rationale as AC3.3. The entry point is removed in Phase 2 Task 3.

**Verification approach:** During Phase 2 UAT, verify the removed `set-admin` entry point fails. The `set-admin` functionality is replaced by `grimoire admin admin <email>`.

### AC4.1 through AC4.5: Complexity compliance (complexipy gate)

**Justification:** `complexipy` is a CLI tool, not a pytest-compatible library. Wrapping it in `subprocess.run()` inside a pytest test would work but creates a dependency on the tool being installed and a fragile coupling to its output format. The project already uses complexipy as a manual verification step (not as a CI gate). Adding it as a CI step is the right long-term fix, but is out of scope for this migration.

**Verification approach:** Each phase that modifies complexity-sensitive functions runs complexipy as a verification step:
- Phase 4 Task 2: `uv run complexipy src/promptgrimoire/cli/testing.py --max-complexity-allowed 15`
- Phase 5 Task 2: `uv run complexipy src/promptgrimoire/cli/e2e.py --max-complexity-allowed 15`
- Phase 6 Task 5: `uv run complexipy src/promptgrimoire/cli/ --max-complexity-allowed 15` (full package sweep)

All must report zero failures. Evidence (command output) is captured in the PR.

---

## Test File Summary

| Test File | Existing / New | Phase Created/Modified | ACs Covered |
|-----------|---------------|----------------------|-------------|
| `tests/unit/test_cli_typer.py` | **New** | P3 T5 | AC1.1, AC1.3, AC2.1 (partial), AC2.2, AC3.1, AC5.5, AC6.4 |
| `tests/unit/test_manage_users.py` | Existing (modified) | P2 T2 | AC2.1 (admin), AC5.3, AC5.6, AC5.7, AC6.2, AC6.3 |
| `tests/unit/test_cli_header.py` | Existing (modified) | P4 T3 | AC5.1 |
| `tests/unit/test_cli_parallel.py` | Existing (modified) | P5 T3 | AC5.2 |
| `tests/unit/test_make_docs.py` | Existing (modified) | P3 T4 | AC5.4 |
| `tests/integration/test_acl_reference_tables.py` | Existing (modified) | P3 T6 | (import path update only, no AC coverage) |

---

## Coverage Matrix

Every AC below is either covered by an automated test (A), human verification (H), or marked NOT IMPLEMENTED (X).

| AC | Description | Coverage | Phase |
|----|-------------|----------|-------|
| AC1.1 | cli/ package with all modules | A | P3 |
| AC1.2 | Old cli.py deleted | A (via AC1.3) | P6 |
| AC1.3 | Old import path fails | A | P3 |
| AC2.1 | Typer Argument/Option declarations | A | P2, P3 |
| AC2.2 | --help renders for all commands | A | P3 |
| AC2.3 | No argparse/sys.argv in cli/ | H | P2, P3 |
| AC2.4 | Pytest passthrough via ctx.args | H | P4, P5 |
| AC3.1 | grimoire --help lists all sub-apps | A | P3 |
| AC3.2 | pyproject.toml entry point correct | H | P1, P6 |
| AC3.3 | Old [project.scripts] entries removed | H | P6 |
| AC3.4 | set-admin entry point removed | H | P2 |
| AC4.1 | complexipy zero failures (full package) | H | P6 |
| AC4.2 | _stream_with_progress <= 15 | H | P4 |
| AC4.3 | _run_all_workers <= 15 | H | P5 |
| AC4.4 | _run_fail_fast_workers <= 15 | H | P5 |
| AC4.5 | _retry_parallel_failures <= 15 | H | P5 |
| AC5.1 | test_cli_header.py passes (new import) | A | P4 |
| AC5.2 | test_cli_parallel.py passes (new import) | A | P5 |
| AC5.3 | test_manage_users.py passes (new import) | A | P2 |
| AC5.4 | test_make_docs.py passes (new import) | A | P3 |
| AC5.5 | CliRunner help tests for all sub-apps | A | P3 |
| AC5.6 | Old _build_user_parser tests removed | A | P2 |
| AC5.7 | Admin CliRunner argument semantics | A | P2 |
| AC6.1 | --semester option on admin list | **X (NOT IMPLEMENTED)** | N/A |
| AC6.2 | admin show positional email | A | P2 |
| AC6.3 | admin enroll same args as before | A | P2 |
| AC6.4 | docs build accepts action argument | A | P3 |

**Totals:** 16 automated, 10 human verification, 1 not implemented. All 27 acceptance criteria accounted for.
