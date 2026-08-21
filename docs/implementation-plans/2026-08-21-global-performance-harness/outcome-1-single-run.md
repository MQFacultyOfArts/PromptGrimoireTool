# Outcome 1: Single-run lifecycle and result boundary

**Goal:** Local `grimoire e2e perf` prepares the database exactly once before
server start, and the soak probe writes a versioned explicit verdict that can
distinguish pass, degraded pass, and collapse.

**Depends on:** Accepted global-harness design.

**Owns:** PERF-HARNESS-1, PERF-HARNESS-2, PERF-HARNESS-4, PERF-HARNESS-10.

## Files and consumers

- Modify `src/promptgrimoire/cli/_shared.py` — return a typed prepared database
  context from the existing migration/truncate/clone path.
- Modify `src/promptgrimoire/cli/testing.py` — accept an already-prepared
  context and avoid a second destructive call.
- Modify `src/promptgrimoire/cli/e2e/__init__.py` — order preparation before
  local start and pass the context into pytest; reject unsafe already-running
  split mode.
- Create `src/promptgrimoire/cli/perf/models.py` and
  `src/promptgrimoire/cli/perf/results.py` — versioned classifications,
  envelope validation, and atomic JSON writing.
- Modify `tests/e2e/test_soak_full_crud_load.py` — first real result-envelope
  producer.
- Modify/create focused tests under `tests/unit/` — first consumers of the
  prepared-context and verdict contracts.

## Work

1. Add failing CLI tests proving the observed call order is prepare once,
   server start, pytest, server stop; add the negative duplicate-preparation
   case.
2. Add failing pure tests for parsed database-name equality and each explicit
   probe verdict, including degradation that cannot be labelled clean.
3. Return `PreparedTestDatabase` from the existing Alembic/truncate/clone code,
   thread it into `_run_pytest`, and remove the perf command's second cleanup.
4. Add atomic versioned result writing and migrate soak's existing gate
   calculation without changing its thresholds.
5. Preserve existing raw payload fields and document the additive schema.

## Verification

- Run: `uv run grimoire test run tests/unit/test_cli_e2e_runner.py`
- Run: `uv run grimoire test run tests/unit/test_perf_results.py`
- Run: `uv run ruff check <modified Python files>`
- Run: `uv run ruff format --check <modified Python files>`
- Run: `uv run ty check`
- Positive signal: tests positively observe one preparation before server
  start and parse three distinct measured verdict fixtures.
- Failure signal: a mock second preparation, mismatched DB name, missing
  envelope field, or degraded result described as clean passes a test.

## Finished-work implication

None: automated evidence settles the single-process ordering and pure result
classification. Live server/database behaviour is retained for final UAT.
