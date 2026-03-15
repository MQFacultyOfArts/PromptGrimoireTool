# Test Requirements: Test Lane Restructure

Maps every acceptance criterion from the design plan to either an automated test or a documented human verification step. Rationalised against implementation decisions in phases 1-6.

---

## Automated Tests

### AC1: `test all` runs unit-only

| Criterion | Test Type | Test File | Description |
|-----------|-----------|-----------|-------------|
| AC1.1 `test all` collects tests only from `tests/unit/` | Unit | `tests/unit/test_cli_testing.py` | Invoke `test all -- --co -q`, assert every collected path starts with `tests/unit/`. Phase 3 Task 1 restricts testpath to `tests/unit`. |
| AC1.2 `test all` excludes smoke-marked tests | Unit | `tests/unit/test_cli_testing.py` | Invoke `test all -- --co -q`, assert no collected test ID matches a known smoke-marked test (e.g. `test_latex_environment`). Phase 3 Task 1 adds `and not smoke` to the marker expression. |

### AC2: `test smoke` exists and works

| Criterion | Test Type | Test File | Description |
|-----------|-----------|-----------|-------------|
| AC2.1 `test smoke` collects and runs all smoke-marked tests | Unit | `tests/unit/test_cli_testing.py` | Assert `smoke` is a registered subcommand. Invoke `test smoke -- --co -q`, assert collected count > 0 and includes known smoke tests. Phase 4 Task 1 adds the command (TDD -- tests written before implementation). |
| AC2.2 `test smoke` runs serial (no xdist) | Unit | `tests/unit/test_cli_testing.py` | Inspect the `default_args` passed to `_run_pytest()` for the smoke command. Assert no `-n` flag is present. Phase 4 Task 1 specifies serial execution. |

### AC3: `e2e all` runs 6 lanes

| Criterion | Test Type | Test File | Description |
|-----------|-----------|-----------|-------------|
| AC3.1 `e2e all` summary shows 6 named lanes | Integration | `tests/unit/test_cli_testing.py` or manual invocation | Assert `run_all_lanes()` produces exactly 6 `LaneResult` instances with names `unit`, `integration`, `playwright`, `nicegui`, `smoke`, `blns+slow`. Phase 5 Task 1 implements this. See note [1]. |

### AC4: No regressions

| Criterion | Test Type | Test File | Description |
|-----------|-----------|-----------|-------------|
| AC4.1 `e2e run`, `e2e slow`, `test changed`, `test run` behaviour unchanged | Unit | `tests/unit/test_cli_testing.py` | Existing tests for these commands must continue to pass unchanged. Phase 5 Task 1 UAT steps 7-14 verify each command. No code changes touch these commands, so their existing test coverage is sufficient. Finalization task #32 added explicit regression verification. |
| AC4.2 `test all-fixtures` produces command-not-found error | Unit | `tests/unit/test_cli_testing.py` | After Phase 4 Task 2 removes the command, assert that invoking `test all-fixtures` raises a Typer usage error / exit code != 0. The existing `all-fixtures` tests are removed in the same task. |

### AC5: Misclassified tests fixed

| Criterion | Test Type | Test File | Description |
|-----------|-----------|-----------|-------------|
| AC5.1 All `@requires_pandoc` and `@requires_latexmk` decorated tests carry `smoke` marker | Unit | `tests/unit/test_cli_testing.py` or dedicated marker test | Collect all tests with `-m smoke --co -q` and verify known toolchain-dependent tests appear. Phase 1 Tasks 2-3 implement the marker propagation and direct application. A structural assertion (grep or AST check confirming `pytest.mark.smoke` on every `requires_pandoc`/`requires_latexmk` decorated function) provides stronger coverage. |
| AC5.2 `TestEnsureDatabaseExistsIntegration` lives in `tests/integration/test_settings_db.py` | Unit | `tests/unit/test_cli_testing.py` or structural check | Assert the class exists in `tests/integration/test_settings_db.py` (importable, has both test methods). Assert the class does NOT exist in `tests/unit/test_settings.py`. Phase 2 Task 1 performs the move. |

---

## Human Verification

### AC1.3: `test all` wall-clock time is measurably faster than current 13.5s

**Justification:** Wall-clock time depends on hardware, system load, and process scheduling. An automated threshold assertion would be flaky across CI runners and developer machines. The design plan specifies "measurably faster" as a relative comparison, not an absolute bound.

**Verification approach:**
1. Before applying Phase 3, record `test all` wall-clock time (baseline: ~13.5s per design plan)
2. After applying Phase 3, run `test all` three times and record wall-clock times
3. Confirm the median post-change time is lower than the baseline
4. Record both numbers in the PR description

**Implementation phase:** Phase 3 Task 1 UAT step 6 ("wall-clock time < 13.5s").

---

### AC3.2: Total test count across all 6 lanes equals current 3,891

**Justification:** This is a conservation-of-tests invariant. The exact number (3,891) was measured at design time and will drift as the codebase evolves. An automated test asserting `== 3891` would break on the next unrelated test addition. The assertion that matters is "no test was silently dropped" -- a relative property, not an absolute count.

**Verification approach:**
1. Before starting implementation, record `uv run pytest --co -q 2>&1 | tail -1` as the baseline count
2. After Phase 5, run `e2e all` and sum the test counts from all 6 lanes in the summary output
3. Confirm the sum equals the baseline count recorded in step 1
4. Record both numbers in the PR description

**Implementation phase:** Phase 5 Task 1 UAT step 5 ("Summary table with 6 lanes").

---

### AC6.1: `docs/testing.md` contains command-to-lane matrix

**Justification:** Verifying documentation content quality -- that the matrix is correct, complete, and matches the implemented lane model -- is a judgment call. An automated grep for "Lane" or a table header would catch only the presence of text, not its accuracy. The matrix must match the actual command-to-lane wiring in the code, which is a semantic check.

**Verification approach:**
1. After Phase 6 Task 1, open `docs/testing.md` and locate the lane matrix section
2. Verify the matrix matches the 6-lane model from the design plan's Architecture section
3. Verify each command row correctly marks which lanes it runs
4. Run `uv run grimoire docs build` to confirm the docs build succeeds

**Implementation phase:** Phase 6 Task 1.

**Partial automation:** `grep -c "Lane" docs/testing.md` as a smoke check that the section exists. Phase 6 Task 1 UAT step 3 uses this.

---

### AC6.2: No references to `all-fixtures` in `docs/testing.md` or `CLAUDE.md`

**Justification:** This CAN be automated. However, the implementation plan already includes it as a grep-based verification in Phase 6 Tasks 1 and 2.

**Automated test possibility:** A unit test that greps both files for `all-fixtures` and asserts zero matches. This is worth implementing as a guard test to prevent re-introduction.

| Criterion | Test Type | Test File | Description |
|-----------|-----------|-----------|-------------|
| AC6.2 No `all-fixtures` references in docs | Unit | `tests/unit/test_docs_consistency.py` (new) or inline in `test_cli_testing.py` | Read `docs/testing.md` and `CLAUDE.md`, assert `"all-fixtures"` does not appear in either file. Phase 6 Tasks 1-2 UAT steps use grep; a persistent test prevents regression. |

---

## Rationalisation Against Implementation Decisions

### Phase 1 coverage

Phase 1 tasks implement AC5.1 (smoke marker propagation). The plan uses decorator composition (`requires_pandoc` and `requires_latexmk` inject `pytest.mark.smoke` automatically) plus direct `@pytest.mark.smoke` on classes with custom toolchain checks. The automated test for AC5.1 should verify both propagation paths: decorator-based and direct.

Finalization task #35 added baseline count verification to Phase 1 Task 3, ensuring the arithmetic (test all count + smoke count = original total) is checked during UAT. This arithmetic is the Phase 1 contribution to AC3.2 (conservation invariant).

### Phase 2 coverage

Phase 2 implements AC5.2 (class relocation). A single task with clear structural assertions (class exists in new location, absent from old location). No ambiguity.

### Phase 3 coverage

Phase 3 implements AC1.1, AC1.2, AC1.3. AC1.1 and AC1.2 are automatable via collection assertions. AC1.3 (wall-clock time) requires human verification as discussed above.

### Phase 4 coverage

Phase 4 implements AC2.1, AC2.2, AC4.2. Finalization task #34 added CLI tests for the new smoke command to `test_cli_testing.py`, following TDD (tests before implementation). AC4.2 (all-fixtures removal) is verified by asserting the command produces an error.

### Phase 5 coverage

Phase 5 implements AC3.1, AC3.2, AC4.1. AC3.1 is automatable (count LaneResult instances). AC3.2 requires human verification (conservation invariant against a moving baseline). AC4.1 relies on existing tests for unchanged commands plus explicit regression checks added by finalization task #32.

Finalization task #36 added an audit step for consumers of `test-all.log` before renaming to `test-unit.log`, preventing silent breakage of any scripts or CI jobs that parse the old log filename.

### Phase 6 coverage

Phase 6 implements AC6.1, AC6.2. AC6.1 requires human judgment on matrix accuracy. AC6.2 can and should be automated as a guard test. Finalization task #38 strengthened the Phase 6 Task 2 verification grep.

---

## Summary

| AC | Sub | Automated | Human | Implementing Phase |
|----|-----|:---------:|:-----:|:------------------:|
| AC1 | 1.1 | Y | | Phase 3 |
| AC1 | 1.2 | Y | | Phase 3 |
| AC1 | 1.3 | | Y | Phase 3 |
| AC2 | 2.1 | Y | | Phase 4 |
| AC2 | 2.2 | Y | | Phase 4 |
| AC3 | 3.1 | Y | | Phase 5 |
| AC3 | 3.2 | | Y | Phase 5 |
| AC4 | 4.1 | Y | | Phase 5 |
| AC4 | 4.2 | Y | | Phase 4 |
| AC5 | 5.1 | Y | | Phase 1 |
| AC5 | 5.2 | Y | | Phase 2 |
| AC6 | 6.1 | | Y | Phase 6 |
| AC6 | 6.2 | Y | | Phase 6 |

**Totals:** 10 automated, 3 human verification.
