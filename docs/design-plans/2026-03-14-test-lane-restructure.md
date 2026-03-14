# Test Lane Restructure Design

**GitHub Issue:** None

## Summary

The project's test suite has grown to include three categories of tests that are currently mixed together in ways that slow down the most common workflow: running `test all` during active development. Unit tests — fast, pure-logic tests with no external dependencies — are bunched in the same `tests/unit/` directory as toolchain-dependent tests that require pandoc, LuaLaTeX, or a live PostgreSQL connection. As a result, `test all` runs slower than it should and includes tests that will fail if those tools are not installed. One integration test class lives in `tests/unit/` outright.

This design restructures the test suite around a formal lane model. Each test belongs to exactly one lane defined by a combination of its file path and a pytest marker. The new `smoke` marker identifies toolchain-dependent tests, which are extracted from the fast unit lane into their own `test smoke` command. A misclassified database test moves to `tests/integration/`. The `test all` command is narrowed to pure unit tests only. Finally, `e2e all` — the full-suite command — is expanded from 4 lanes to 6, so that every test in the suite is reachable through a single orchestration point. The obsolete `all-fixtures` command is removed and its coverage absorbed into `e2e all`. No test is dropped; the total count of 3,891 is preserved across all lanes.

## Definition of Done

1. `test all` runs only `tests/unit/` (excluding `smoke`-marked tests), xdist, fast
2. `test smoke` is a new standalone command running `smoke`-marked tests, serial
3. `e2e all` runs 6 lanes (unit, integration, playwright, nicegui, smoke, blns+slow) with summary
4. `test all-fixtures` is removed
5. ~30 misclassified tests in `tests/unit/` gain `@pytest.mark.smoke` (via decorators or direct marking)
6. `TestEnsureDatabaseExistsIntegration` moves from `tests/unit/` to `tests/integration/`
7. `docs/testing.md` updated with the lane/verb matrix
8. No test is silently dropped — total count across all `e2e all` lanes equals current 3,891
9. Existing commands (`e2e run`, `e2e slow`, `test changed`, `test run`) unchanged in behaviour

## Acceptance Criteria

### test-lane-restructure.AC1: `test all` runs unit-only
- **test-lane-restructure.AC1.1 Success:** `test all` collects tests only from `tests/unit/`
- **test-lane-restructure.AC1.2 Success:** `test all` excludes smoke-marked tests
- **test-lane-restructure.AC1.3 Verify:** `test all` wall-clock time is measurably faster than current 13.5s

### test-lane-restructure.AC2: `test smoke` exists and works
- **test-lane-restructure.AC2.1 Success:** `test smoke` collects and runs all smoke-marked tests
- **test-lane-restructure.AC2.2 Success:** `test smoke` runs serial (no xdist)

### test-lane-restructure.AC3: `e2e all` runs 6 lanes
- **test-lane-restructure.AC3.1 Success:** `e2e all` summary shows 6 named lanes (unit, integration, playwright, nicegui, smoke, blns+slow)
- **test-lane-restructure.AC3.2 Verify:** Total test count across all 6 lanes equals current 3,891

### test-lane-restructure.AC4: No regressions
- **test-lane-restructure.AC4.1 Success:** `e2e run`, `e2e slow`, `test changed`, `test run` behaviour unchanged
- **test-lane-restructure.AC4.2 Success:** `test all-fixtures` produces command-not-found error

### test-lane-restructure.AC5: Misclassified tests fixed
- **test-lane-restructure.AC5.1 Success:** All `@requires_pandoc` and `@requires_latexmk` decorated tests carry `smoke` marker
- **test-lane-restructure.AC5.2 Success:** `TestEnsureDatabaseExistsIntegration` lives in `tests/integration/test_settings_db.py`

### test-lane-restructure.AC6: Documentation updated
- **test-lane-restructure.AC6.1 Verify:** `docs/testing.md` contains command-to-lane matrix
- **test-lane-restructure.AC6.2 Verify:** No references to `all-fixtures` in `docs/testing.md` or `CLAUDE.md`

## Glossary

- **Lane**: A named subset of the test suite defined by a path filter and/or pytest marker expression. Every test belongs to exactly one lane. Lanes differ in parallelism strategy (xdist, serial, per-file subprocess) and when they are run.
- **xdist**: `pytest-xdist`, a pytest plugin that distributes tests across multiple worker processes for parallel execution. Used by the unit and integration lanes.
- **Smoke test**: A test that checks whether an external toolchain (pandoc, lualatex, tlmgr) is installed and minimally functional. Excluded from the fast unit lane.
- **`smoke` marker**: A pytest marker (`@pytest.mark.smoke`) added to tests that require external toolchains. `addopts` in pyproject.toml causes `test all` to exclude them automatically.
- **BLNS**: Big List of Naughty Strings — a corpus of pathological string inputs used to fuzz input handling. Tests marked `blns` are slow by nature.
- **`latexmk_full`**: An existing pytest marker for full LaTeX compilation suites (full PDF round-trips). Run only by `e2e slow`, not by `e2e all`.
- **AST dependency analysis**: The mechanism behind `test changed`. Parses the Python AST of changed source files to determine which test files depend on them, then runs only the relevant subset.
- **`requires_pandoc` / `requires_latexmk`**: Decorator factories in `tests/conftest.py` that skip a test if the named tool is absent. After this change they also inject `@pytest.mark.smoke` automatically.
- **`LaneResult`**: A dataclass in `src/promptgrimoire/cli/e2e/_lanes.py` that captures the outcome of a single lane run.
- **`_run_pytest()`**: The shared pytest invocation helper in `src/promptgrimoire/cli/testing.py`. All lane commands call it with different arguments.
- **`run_all_lanes()`**: The orchestration function in `src/promptgrimoire/cli/e2e/__init__.py` that runs each lane sequentially and collects `LaneResult` instances.
- **`all-fixtures`**: A legacy `grimoire test` subcommand being removed. Its coverage is absorbed into `e2e all`.
- **Marker expression**: A boolean expression passed to pytest's `-m` flag (e.g., `not smoke`, `blns or slow`) that filters which tests are collected.

## Architecture

### Lane Model

Every test in the suite belongs to exactly one lane. Commands select lanes by marker expression and test path.

**Lane definitions:**

| Lane | Path filter | Marker filter | Workers | Purpose |
|------|-----------|---------------|---------|---------|
| Unit | `tests/unit/` | `not smoke` | xdist | Pure logic, no external toolchains |
| Integration | `tests/integration/` | (none beyond defaults) | xdist | Database-backed tests |
| Playwright | `tests/e2e/` | `e2e` | Parallel per-file | Browser E2E with cloned DBs |
| NiceGUI | `tests/e2e/` | `nicegui_ui` | Isolated subprocess | In-process UI simulation |
| Smoke | any | `smoke` | Serial | Toolchain existence/operation (pandoc, lualatex, tlmgr) |
| BLNS+Slow | any | `(blns or slow) and not smoke` | Serial | Naughty strings and explicitly-slow tests |

`latexmk_full` remains a separate marker for full PDF compilation suites, run only by `e2e slow`.

### Command-to-Lane Matrix

| Lane | `test all` | `test smoke` | `test changed` | `e2e all` | `e2e run` | `e2e slow` |
|------|:---:|:---:|:---:|:---:|:---:|:---:|
| Unit | Y | | AST | Y | | |
| Integration | | | AST | Y | | |
| Playwright | | | | Y | Y | |
| NiceGUI | | | | Y | | |
| Smoke | | Y | AST | Y | | |
| BLNS+Slow | | | | Y | | |
| latexmk_full | | | | | | Y |
| Playwright slow | | | | | | Y |

AST = `test changed` uses AST dependency analysis to select relevant tests regardless of lane.

### Smoke Marker Propagation

The `smoke` marker propagates through existing decorators in `tests/conftest.py`:

- `requires_pandoc` → adds `@pytest.mark.smoke` automatically
- `requires_latexmk` → adds `@pytest.mark.smoke` automatically
- `requires_full_latexmk` → already adds `latexmk_full`, also gets `smoke`

Tests not covered by decorators (e.g. `test_latex_environment.py` with custom `@requires_tinytex` skipif) get `@pytest.mark.smoke` applied directly at class/module level.

### `e2e all` Lane Orchestration

`run_all_lanes()` in `src/promptgrimoire/cli/e2e/__init__.py` runs 6 lanes sequentially, each producing a `LaneResult`. The existing `_print_all_lanes_summary()` renders all results in a table.

```
── Summary ──────────────────────────────────────────
  Lane             Exit   Log / Artifacts
  ─────────────    ─────  ──────────────────────
  unit             PASS   test-unit.log
  integration      PASS   test-integration.log
  playwright       PASS   [artifacts]
  nicegui          PASS   —
  smoke            PASS   test-smoke.log
  blns+slow        PASS   test-slow.log
```

## Existing Patterns

Investigation found the test infrastructure is well-factored:

- `_run_pytest()` in `src/promptgrimoire/cli/testing.py:272-353` is the shared pytest runner. All lanes call it with different `title`, `log_path`, `default_args`.
- `LaneResult` dataclass in `src/promptgrimoire/cli/e2e/_lanes.py:30-41` tracks per-lane outcomes.
- `_print_all_lanes_summary()` in `src/promptgrimoire/cli/e2e/__init__.py:109-132` renders multi-lane results.
- `run_all_lanes()` in `src/promptgrimoire/cli/e2e/__init__.py:135-183` orchestrates sequential lane execution.

This design follows the same patterns: each new lane is a `_run_pytest()` call producing a `LaneResult`. No new abstractions needed.

The `requires_pandoc` / `requires_latexmk` decorators in `tests/conftest.py` already compose markers — adding `pytest.mark.smoke` follows the established pattern.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Add Smoke Marker and Tag Tests

**Goal:** Define the `smoke` marker and apply it to all toolchain-dependent tests in `tests/unit/`.

**Components:**
- `pyproject.toml` — add `smoke` marker definition, add `smoke` to default `addopts` exclusion
- `tests/conftest.py` — add `pytest.mark.smoke` to `requires_pandoc` and `requires_latexmk` decorators
- `tests/unit/test_latex_environment.py` — add `@pytest.mark.smoke` directly (uses custom `requires_tinytex`)
- `tests/unit/test_latex_packages.py` — add `@pytest.mark.smoke` to class
- `tests/unit/export/test_empty_content_guard.py` — add `@pytest.mark.smoke` to `TestEmptyContentValueError`
- `tests/unit/input_pipeline/test_converters.py` — add `@pytest.mark.smoke` to `TestConvertPdfToHtml`
- `tests/unit/input_pipeline/test_process_input.py` — add `@pytest.mark.smoke` to `TestProcessInputPdf`

**Dependencies:** None

**Done when:**
- `uv run grimoire test all` excludes all smoke-marked tests
- `uv run grimoire test all -- -m smoke --co -q` collects the smoke tests
- Total collected tests across `test all` + smoke equals current total (minus the integration tests, which move in Phase 2)
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Move Misclassified Integration Test

**Goal:** Move the real-PostgreSQL test class from `tests/unit/` to `tests/integration/`.

**Components:**
- `tests/unit/test_settings.py` — extract `TestEnsureDatabaseExistsIntegration` class (lines 578-659)
- New file: `tests/integration/test_settings_db.py` — receives the extracted class with its imports and fixtures

**Dependencies:** Phase 1 (marker changes are independent but should land first)

**Done when:**
- `tests/integration/test_settings_db.py` exists and its tests pass
- `tests/unit/test_settings.py` no longer contains `TestEnsureDatabaseExistsIntegration`
- `uv run grimoire test all` no longer runs any tests with real `psycopg.connect()`
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Narrow `test all` to Unit-Only

**Goal:** Change `test all` to run only `tests/unit/`, excluding smoke.

**Components:**
- `src/promptgrimoire/cli/testing.py` — modify `all_tests()` to pass `tests/unit` as explicit testpath, update marker expression to exclude `smoke`

**Dependencies:** Phase 1 (smoke marker must exist), Phase 2 (integration tests must be in correct directory)

**Done when:**
- `uv run grimoire test all` runs only tests from `tests/unit/` and excludes smoke-marked tests
- Test count is lower than current 3,891 (unit-only subset)
- Wall-clock time is measurably faster
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Add `test smoke` Command and Remove `all-fixtures`

**Goal:** Add standalone smoke command, remove the obsolete `all-fixtures` command.

**Components:**
- `src/promptgrimoire/cli/testing.py` — add `smoke` command (serial, marker `smoke`, log to `test-smoke.log`), remove `all_fixtures_tests()` command

**Dependencies:** Phase 1 (smoke marker must exist)

**Done when:**
- `uv run grimoire test smoke` runs all smoke-marked tests and passes
- `uv run grimoire test all-fixtures` produces a "no such command" error
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: Expand `e2e all` to 6 Lanes

**Goal:** Add integration, smoke, and blns+slow lanes to `run_all_lanes()`.

**Components:**
- `src/promptgrimoire/cli/e2e/__init__.py` — modify `run_all_lanes()`:
  - Lane 1 (unit): narrow to `tests/unit/`, exclude smoke, log to `test-unit.log`
  - Lane 2 (integration): new, `tests/integration/`, xdist, log to `test-integration.log`
  - Lane 3 (playwright): unchanged
  - Lane 4 (nicegui): unchanged
  - Lane 5 (smoke): new, marker `smoke`, serial, log to `test-smoke.log`
  - Lane 6 (blns+slow): new, marker `(blns or slow) and not smoke`, serial, log to `test-slow.log`

**Dependencies:** Phase 3 (unit lane narrowed), Phase 4 (smoke command exists for reference)

**Done when:**
- `uv run grimoire e2e all` shows 6 lanes in summary output
- Total test count across all 6 lanes equals current 3,891
- All lanes pass
<!-- END_PHASE_5 -->

<!-- START_PHASE_6 -->
### Phase 6: Update Documentation

**Goal:** Update `docs/testing.md` and `CLAUDE.md` to reflect new lane structure.

**Components:**
- `docs/testing.md` — add lane/verb matrix, document `smoke` marker, remove `all-fixtures` references
- `CLAUDE.md` — update Key Commands section with new commands, remove `all-fixtures`

**Dependencies:** Phase 5 (all lanes working)

**Done when:**
- `docs/testing.md` contains the command-to-lane matrix
- `CLAUDE.md` Key Commands section reflects current command set
- No references to `all-fixtures` remain in documentation
<!-- END_PHASE_6 -->

## Additional Considerations

**`test changed` behaviour:** No code changes needed. The AST dependency analysis in `test changed` already determines which tests are relevant to the diff. Smoke-marked tests will be selected when their source dependencies change, because `test changed` uses its own marker expression (`not e2e and not nicegui_ui`) which does not exclude `smoke`. This is intentional — if you change a converter, the smoke test for it should run.

**Log file rename:** Lane 1 in `e2e all` currently logs to `test-all.log`. Renaming to `test-unit.log` is a breaking change for any scripts that parse logs. The `.gitignore` already covers `test-all.log` and will need entries for the new log filenames.

**Backwards compatibility:** `all-fixtures` is removed with no alias. The user confirmed they hadn't used it in two weeks and wants the coverage absorbed into `e2e all`.
