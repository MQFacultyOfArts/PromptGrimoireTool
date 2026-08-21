# Outcome 2: Durable schedules, attempts, resume, and cooperative admission

**Goal:** One public campaign command resolves full N sweeps and controlled arm
patterns, records immutable attempts atomically, resumes by revalidation, and
releases scarce resources between legs so queued short tests can run.

**Depends on:** Outcome 1 result and prepared-database contracts.

**Owns:** PERF-HARNESS-5, PERF-HARNESS-6, PERF-HARNESS-7,
PERF-HARNESS-7A, PERF-HARNESS-7B.

## Files and consumers

- Create `src/promptgrimoire/cli/perf/campaign.py` — typed definition,
  explicit sweep/arm schedule resolution, and stop policies.
- Create `src/promptgrimoire/cli/perf/state.py` — atomic campaign state,
  immutable attempt paths, hashes, validated leg records, pause, and resume.
- Create `src/promptgrimoire/cli/perf/runner.py` — one-leg coordinator and full
  schedule loop.
- Modify `src/promptgrimoire/cli/perf/__init__.py` and
  `src/promptgrimoire/cli/__init__.py` — public `grimoire perf` commands.
- Modify `src/promptgrimoire/cli/_shared.py`, `cli/testing.py`, and
  `cli/e2e/__init__.py` — scoped short/campaign admission rather than one
  campaign-lifetime descriptor.
- Create `tests/unit/test_perf_campaign.py` and
  `tests/unit/test_perf_state.py`; extend lock tests in
  `tests/unit/test_cli_e2e_runner.py`.
- Update `docs/testing.md` — campaign creation, status, pause, resume, and
  evidence paths.

## Work

1. Add failing schedule tests for N sweeps, repetitions, ABBA at every N,
   explicit irregular legs, stable leg IDs, and definition mismatch on resume.
2. Add failing state tests proving raw probe JSON is insufficient, valid leg
   hashes are rechecked, corruption reruns, retries allocate new directories,
   and pause takes effect only between legs.
3. Add a two-process positive lock test: short work queued during a campaign
   leg acquires before the next campaign leg. Include a control showing an
   uncontended next leg still proceeds.
4. Implement the smallest typed schedule and atomic file store; avoid dynamic
   plugins, adaptive ordering, or a queue daemon.
5. Implement one-leg execution and the full campaign loop, with status and
   pause commands reading the same durable state.
6. Produce a summary grouped by parameter level and arm while retaining exact
   order and per-leg degradation.

## Verification

- Run: `uv run grimoire test run tests/unit/test_perf_campaign.py`
- Run: `uv run grimoire test run tests/unit/test_perf_state.py`
- Run: `uv run grimoire test run tests/unit/test_cli_e2e_runner.py`
- Run: `uv run ruff check <modified Python files>`
- Run: `uv run ruff format --check <modified Python files>`
- Run: `uv run ty check`
- Positive signal: a mechanics campaign resolves and persists exact ABBA order,
  a corrupt leg gets a new attempt, and the short-test process records
  acquisition between two campaign legs.
- Failure signal: campaign state regenerates from changed defaults, evidence
  presence skips validation, attempt paths repeat, or consecutive campaign legs
  acquire while short work is already queued.

## Finished-work implication

Human judgment is deferred to complete-surface UAT: status/summary clarity and
the operational experience of a short command interleaving with a campaign.
