# Outcome 4: Remaining probes, summaries, and UAT

**Goal:** Soak, cram, and herd all use the common result boundary; a local
mechanics campaign is verified and the complete Bunyip UAT contract is ready.

**Depends on:** Outcomes 1 through 3 and a private adapter implementation for
live split UAT.

**Owns:** PERF-HARNESS-11 and final design conformance.

## Files and consumers

- Modify `tests/e2e/test_assessment_cram_load.py` and
  `tests/e2e/test_thundering_herd.py` — shared atomic result-envelope producers.
- Extend `src/promptgrimoire/cli/perf/results.py` and probe registry only where
  current probe semantics require typed differences.
- Extend focused unit tests for all three probe validators and campaign
  summaries.
- Update `docs/testing.md`, `docs/perf-target-adapter.md`, and the design if
  implementation evidence changed a contract.

## Work

1. Add failing result fixtures for cram and herd pass, degraded pass, measured
   boundary, and incomplete evidence.
2. Move their existing gate calculations into the common envelope without
   changing thresholds or erasing probe-specific observations.
3. Run a no-load mechanics campaign that proves schedule/state/cleanup, then a
   bounded local n=1 soak if host/database prerequisites are available.
4. Audit implementation against every design criterion and repair the living
   design where evidence required a different implementation detail.
5. Run full project gates. After the private adapter exists and live use is
   authorised, execute the split n=1 UAT and the interleaving/resume UAT from
   `index.md`.

## Verification

- Run: `uv run grimoire test changed`
- Run: `uv run ruff check .`
- Run: `uv run ruff format --check .`
- Run: `uv run ty check`
- Run: `uv run grimoire test all`
- Run when prerequisites are available: a project-native local n=1 campaign.
- Positive signal: all three probe fixtures classify through one validator,
  the mechanics campaign produces a revalidatable summary, and full gates have
  fresh zero exits.
- Failure signal: a probe retains bespoke completion semantics, a required
  gate is deselected, the campaign cannot be resumed from disk, or a live UAT
  prerequisite is reported as passed without execution.

## Finished-work implication

Brian runs the complete-surface UAT in `index.md` and judges whether status,
degradation, and interleaving are operationally clear. Any falsifier keeps the
design unaccepted. Publication and PR creation remain separate decisions.
