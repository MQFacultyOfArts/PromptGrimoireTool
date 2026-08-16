# Causal analysis: production deploy JS-runner availability

Date: 2026-08-15
Investigator: Codex (GPT-5)
Status: Corrected; post-simplification container verification pending

## Summary

The production deploy gate failed because its JavaScript lane selected a
globally available `npx` even though the repository-local JavaScript dependency
graph had never been installed. The temporary Vitest process then loaded
`/opt/promptgrimoire/vitest.config.js`, whose import of `vitest/config` could
not resolve from the project. The Python lane subsequently reported 3,959
passing tests, but the aggregate command correctly returned non-zero because
the earlier JavaScript lane had failed.

The production negative border was then exercised in the same checkout:
`npm ci --include=dev` installed the locked graph, and the exact local runner
`node_modules/.bin/vitest run` loaded the same configuration and passed all six
files and 123 tests.

The defect was broader than a bad executable check. Production provisioning,
the test runner, and the runbook disagreed about whether BATS and JavaScript
were required. The corrected contract provisions the locked JavaScript graph
in `restart.sh` and makes missing BATS or JavaScript lanes fail closed.

## Differential baseline

- Reference branch and application candidate:
  `eb4e0ce1c6a8a7ec0cac46aeacc76f05be062fec`
- Production pre-deploy commit:
  `3c87e87fd0333bd0acd3fc51dd704899d9f7866b`

The defective global-`npx` check exists at both commits. This was a latent
deployment-contract defect exposed by the first release after a long quiet
period, not a regression introduced by the release candidate.

## Production evidence

The release transcript records these observations from `/opt/promptgrimoire`:

1. The local runner and `happy-dom` were absent while a global `npx` and npm
   10.9.8 were present.
2. The JavaScript lane failed while loading `vitest.config.js`:

   ```text
   [UNRESOLVED_IMPORT] Could not resolve 'vitest/config' in vitest.config.js
   Error [ERR_MODULE_NOT_FOUND]: Cannot find package 'vitest' imported from
   /opt/promptgrimoire/vitest.config.js.timestamp-....mjs
   ```

3. The aggregate gate later printed `3,959 passed` for Python, then
   `ABORT: unit tests failed — not restarting`.
4. After `npm ci --include=dev`, the repository-local Vitest 4.1.2 passed six
   files and 123 tests against the same production checkout.
5. BATS 1.10.0 is now present at `/usr/bin/bats`.

These are exact operator-provided command outputs retained in the release chat,
not machine-attached log artifacts in this repository. That limits independent
provenance, but the error and the after-provisioning success exercise both sides
of the disputed dependency-availability boundary on production.

## Causal chain

1. `deploy/restart.sh` runs `grimoire test all` before its HAProxy and systemd
   mutation steps.
2. The historical `_run_js()` treated global `npx` availability as evidence
   that the JavaScript lane could run.
3. The production checkout had no local `node_modules` dependency graph.
4. `npx` launched a temporary Vitest, but Node resolved the configuration's
   bare `vitest/config` import from the project, where `vitest` was absent.
5. Vitest returned non-zero. `all_tests()` retained that result while
   continuing through the Python lane, which passed.
6. `all_tests()` collapsed the lane results to aggregate exit code 1, so
   `restart.sh` aborted before its restart path.
7. Installing the reviewed lock locally made that same configuration import and
   all 123 JavaScript tests pass, falsifying an ordinary test-code failure as
   the explanation for this attempt.

## Competing hypotheses

| Hypothesis | Before provisioning | After locked local install | Assessment |
|---|---|---|---|
| Python failure caused the abort | 3,959 Python tests passed | Unchanged | Falsified |
| BATS caused the observed Vitest startup error | Cannot produce that error | BATS separately provisioned | Falsified for this error |
| The JS tests themselves fail | Config fails before collection | All 123 pass | Falsified in this checkout |
| Missing local JS dependencies cause config resolution failure | Exact missing-package error | Same config and tests pass after install | Demonstrated |
| A temporary/global runner is a valid substitute for the locked local runner | It cannot resolve the project's config import | Local runner succeeds | Falsified |

## Correction

- `deploy/restart.sh` runs `npm --prefix "$APP_DIR" ci --include=dev` before
  the production test gate. Failure aborts before HAProxy or systemd changes.
- `_run_js()` invokes only `node_modules/.bin/vitest`; absence or lack of
  execute permission is a failed lane. Lockfile validation and replacement of
  any existing dependency tree are delegated to the immediately preceding
  `npm ci`, rather than reimplemented in the Python test runner.
- `_run_bats()` treats an absent executable, test directory, or `.bats` files
  as a failed lane.
- The deployment and testing documentation state that these gates are
  mandatory and that global `npx` is not a fallback.

The locked install addresses reproducibility but not every supply-chain policy.
Production npm 10.9.8 is too old to enforce the repository's
`min-release-age=14` setting. Upgrading npm is a separate infrastructure change;
it must not be hidden inside this application restart.

## Epistemic boundary

- **Demonstrated on production:** without local dependencies, the config import
  fails; after the locked local install, the same config and 123 tests pass.
- **Demonstrated from source order:** this test-gate failure prevents this
  script's later HAProxy and systemd mutation steps.
- **Verified by focused regression tests:** mandatory missing runners and test
  corpora fail closed, the JavaScript lane never falls back to global `npx`,
  and the deploy's clean locked install precedes `grimoire test all`.
- **Verified locally after the runner simplification:** BATS passed 94 tests,
  JavaScript passed 123 tests on the repository-local Vitest 4.1.2, and the
  Python lane passed 3,986 tests. The earlier focused export-job run passed all
  20 integration tests.
- **Verified in the local Actions container before the runner simplification:**
  `gh act` exited zero with all jobs passing: 96 BATS tests, 123 JavaScript
  tests, 3,985 Python tests with two environment-specific skips, 52 Playwright
  files, and 20 NiceGUI files. This result does not verify the later deletion
  of the custom npm graph validator and two redundant BATS tests; the container
  workflow must be rerun against the final snapshot.
- **Verified at the release boundary:** the strict slow suite passed before the
  application release; production then passed the real-auth, annotation, and
  affected-workspace PDF-export UAT before and after the separately staged
  TinyTeX update.

## Critical-review disposition

The first adversarial review found additional fail-open deployment behaviour
around pre-restart responses, connected-client counts, the standalone worker,
the TeX rollback path, and runtime-environment mutation. Those paths now abort
on missing or malformed positive evidence. Python dependencies are built in an
exact, commit-specific staged environment and both services run it with
`uv run --locked --no-sync`; TeX updates are locked, checksummed, and exercised
by a smoke export before the worker restarts.

One architectural limit remains explicit: the operator still fast-forwards the
single production source checkout before invoking `restart.sh`. The script
revalidates its exact commit and clean worktree before switching services, but
a fully atomic source rollback requires a future release-directory deployment
model rather than the current mutable-checkout topology.
