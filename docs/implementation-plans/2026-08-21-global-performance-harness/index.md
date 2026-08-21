# Global Performance Harness Implementation Plan

**Design:** `docs/design-plans/2026-08-21-global-performance-harness.md`

**Working root:** `/tmp/claude-1000/-home-brian-people-Brian-PromptGrimoireTool--worktrees-initial-snapshot-delivery/6764f446-1a72-41ec-913d-88df8649b472/scratchpad/perf-wt`

**Branch:** `perf/global-harness`, based on `main` at `f3e30843`

## Scope and current evidence

The current perf command prepares the test database before target selection and
the shared pytest launcher prepares it again. Existing performance probes emit
probe-specific JSON, while campaign state and validity decisions exist only in
the recovered private shell runner. The project already has stable E2E artifact
helpers and one host-wide test lock, but that lock is currently process-lifetime
state and cannot yield between campaign legs.

The implementation is divided into four independently recoverable outcomes:

1. [Single-run lifecycle and result boundary](outcome-1-single-run.md)
2. [Durable schedules, attempts, resume, and cooperative admission](outcome-2-campaign-state.md)
3. [External target command contract](outcome-3-external-target.md)
4. [Remaining probes, summaries, and UAT](outcome-4-probes-uat.md)

No outcome authorises a push, PR, deployment, private credential access, or
final history rewrite. Local checkpoint commits remain prohibited by the
project's explicit `Never commit unless explicitly requested` rule.

## Execution status — 2026-08-21

Outcomes 1 through 3 are implemented. Outcome 4's probe migrations, summaries,
automated signal cleanup, and fake-external lifecycle are implemented. The
remaining queue is deliberately live-UAT-only:

1. Receive the private Bunyip adapter implementation and its behavioral BATS
   evidence against `docs/perf-target-adapter.md`.
2. Supply the local direct and pooled database URLs and run the bounded local
   n=1 soak UAT.
3. Supply the adapter executable and run the bounded Bunyip n=1 soak UAT.
4. Run the short-test interleaving and interrupted-resume UAT below.
5. Obtain human acceptance of status, summary, degradation, and interleaving
   behavior before declaring the harness complete.

Latest automated evidence: 151 focused harness/CLI tests passed; the perf lane
collects 22 of 5609 tests; the full project gate passed 96 BATS tests, 140 JS
tests, and 4188 Python tests. Repository-wide Ruff check, Ruff format check,
Ty, and diff checks passed. `E2E_PERF_DIRECT_DATABASE_URL`,
`E2E_PERF_DATABASE_URL`, and `E2E_PERF_TARGET_ADAPTER` were unavailable, so no
local or Bunyip live UAT is represented by those results.

## Boundary flow

```text
private durable job / local operator
              |
              v
public campaign schedule + atomic state
              |
      scoped leg admission
              |
   prepare DB once (public)
              |
 local target OR exact-argv private adapter
              |
        attested server
              |
    pytest probe -> result envelope
              |
 target stop/collect -> public validation
              |
 immutable leg record + release admission
```

Outcome 1 owns the database/result producer-consumer boundary. Outcome 2 owns
the schedule/state/admission boundary. Outcome 3 owns the process boundary to
private Bunyip infrastructure. Outcome 4 owns adoption by the remaining real
probe consumers and finished-surface UAT.

## Complete-plan verification

- `uv run grimoire test changed`
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run ty check`
- `uv run grimoire test all`
- Focused local n=1 mechanics campaign through the project CLI.
- Bunyip n=1 UAT only after the private adapter implements the published
  contract and the human authorises live host use.

Positive completion requires fresh zero exit codes, a mechanically revalidated
campaign directory, and no owned server after cleanup. Any missing lane,
unvalidated result, stale attempt, or unavailable Bunyip adapter is reported as
an exclusion rather than converted into success.

## Finished-work UAT contract

After all automated checks and the private adapter are ready:

1. Start a two-level mechanics campaign with arm pattern ABBA.
2. While its first leg owns the host slot, start one short project test command.
3. Observe the first leg finish, the short command acquire and complete, then
   the next campaign leg resume without manual pause.
4. Interrupt after a later leg, rerun the same campaign ID, and observe that
   validated legs are revalidated and skipped while the first incomplete leg
   gets a new attempt directory.
5. Inspect status and summary output: exact N/arm order, separate degraded
   counts, immutable attempts, and no claim that infrastructure failure is a
   knee.

Falsifiers are a changed schedule on resume, a rerun validated leg, a short
test starved behind consecutive campaign legs, overwritten evidence, a running
target after termination, or a verdict derived only from pytest's exit code.
