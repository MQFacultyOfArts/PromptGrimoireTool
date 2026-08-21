# Outcome 3: External target command contract

**Goal:** The same public coordinator can run one leg through a bounded private
adapter without learning Bunyip paths, credentials, lease implementation, or
performance interpretation.

**Depends on:** Outcomes 1 and 2.

**Owns:** PERF-HARNESS-3, PERF-HARNESS-8, PERF-HARNESS-9.

## Files and consumers

- Create `src/promptgrimoire/cli/perf/targets.py` — local target and one
  exact-argv external executable target.
- Extend `src/promptgrimoire/cli/perf/runner.py` — lifecycle cleanup across
  target failures and signals.
- Create `tests/unit/test_perf_targets.py` — fake adapter producer and public
  coordinator consumer.
- Create `docs/perf-target-adapter.md` — versioned start/stop/collect request
  and response contract consumed by private `boxen/bunyip/perf-rig`.
- Update `docs/testing.md` — split-target invocation without private values.

## Work

1. Add failing fake-adapter tests for valid identity, malformed JSON, stale
   boot, wrong commit, wrong database, failed DB probe, wrong pool mode, stop
   failure, collection failure, and complete rotated logs.
2. Implement exact argument-vector subprocess calls and strict JSON parsing;
   do not accept shell fragments or import arbitrary code.
3. Validate target identity against the prepared database and leg's expected
   source/profile before pytest starts.
4. On every exit path, stop the opaque owned handle, collect into the immutable
   attempt directory, hash evidence, and prevent validation if cleanup or
   coverage is incomplete.
5. Document how the private durable wrapper holds and releases the live Bunyip
   flock per leg and yields between invocations without deciding campaign
   truth.

## Verification

- Run: `uv run grimoire test run tests/unit/test_perf_targets.py`
- Run: `uv run grimoire test run tests/unit/test_perf_campaign.py`
- Run: `uv run ruff check <modified Python files>`
- Run: `uv run ruff format --check <modified Python files>`
- Run: `uv run ty check`
- Positive signal: the fake adapter's attested process and complete logs yield
  a valid leg; each injected boundary failure yields the intended non-knee
  terminal classification and cleanup call.
- Failure signal: adapter stdout other than one valid schema is accepted, a
  secret-bearing field is retained, wrong provenance reaches measurement, or a
  target remains owned after a failure fixture.

## Finished-work implication

The private thread can implement the published protocol without copying public
campaign logic. Live Bunyip correctness remains a final external prerequisite.
