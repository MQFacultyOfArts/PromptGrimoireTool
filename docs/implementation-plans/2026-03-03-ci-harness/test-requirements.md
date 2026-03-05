# CI Harness — Test Requirements

Maps each acceptance criterion to its verification method. Because this feature is a CI workflow (GitHub Actions YAML + tooling configuration), the primary verification is the workflow itself running successfully on GitHub, not unit tests.

## Verification Categories

| Category | Description |
|----------|-------------|
| **Workflow run** | Verified by CI passing on GitHub. Evidence: green check on PR. |
| **Static inspection** | Verified by reading a file for specific content. Can be automated with a grep/assertion in a shell script, but the primary evidence is the file diff in the PR. |
| **Local command** | Verified by running a command locally and checking exit code / output. |
| **Human verification** | Requires a person to check GitHub UI or logs. Cannot be meaningfully automated. |

---

## ci-harness.AC1: Workflow triggers correctly

### ci-harness.AC1.1 — Push to `main` triggers all three jobs

| Field | Value |
|-------|-------|
| **Verification** | Human verification |
| **What to check** | After merging the PR, confirm a workflow run appears on the `main` branch with all three jobs (quality, test-all, e2e). |
| **Evidence** | `gh run list --branch main --limit 1` shows a CI run with three jobs. |
| **Why not automated** | Requires an actual push to `main`, which only happens at merge time. The trigger configuration is a YAML declaration; there is no way to unit-test GitHub's event dispatch. |

### ci-harness.AC1.2 — PR targeting `main` triggers all three jobs

| Field | Value |
|-------|-------|
| **Verification** | Human verification (verified during Phase 3 Task 6) |
| **What to check** | With the PR open and a push to the branch, confirm three jobs appear in the PR's checks tab. |
| **Evidence** | `gh run list --branch cli-typer-211 --limit 1` shows a CI run. `gh run view <run-id>` shows three jobs. Screenshot or URL of green PR checks. |
| **Why not automated** | Requires an actual PR event on GitHub. The trigger is verified by pushing to the branch with an open PR. |

### ci-harness.AC1.3 — Push to non-main branch does not trigger CI

| Field | Value |
|-------|-------|
| **Verification** | Static inspection + human verification |
| **What to check** | The `on:` block in `.github/workflows/ci.yml` specifies `push: branches: [main]` and `pull_request: branches: [main]`. A push to a branch without an open PR targeting `main` should produce no workflow run. |
| **Evidence** | (1) Inspect the `on:` trigger in the workflow file. (2) Optionally, push to a throwaway branch with no PR and confirm `gh run list --branch <branch>` returns nothing. |
| **Why not automated** | GitHub Actions trigger semantics are defined by GitHub's runtime, not testable in isolation. The static check of the YAML is the primary verification. |

### ci-harness.AC1.4 — All three jobs run in parallel

| Field | Value |
|-------|-------|
| **Verification** | Static inspection |
| **What to check** | None of the three jobs (`quality`, `test-all`, `e2e`) have a `needs:` key referencing another job. |
| **Evidence** | Inspect `.github/workflows/ci.yml` — no `needs:` declarations between the three jobs. `gh run view <run-id>` shows all three jobs starting at approximately the same time. |
| **How to verify** | `grep -c 'needs:' .github/workflows/ci.yml` returns 0. |

---

## ci-harness.AC2: Quality job catches issues

### ci-harness.AC2.1 — `ruff check .` passes (including S security rules)

| Field | Value |
|-------|-------|
| **Verification** | Workflow run + local command |
| **What to check** | The quality job's "Run ruff lint" step exits 0 in CI. Locally: `uv run ruff check .` exits 0. |
| **Evidence** | Green quality job. Local exit code 0. |
| **Pre-verification** | `uv run ruff check . --select S` confirms S rules are active and pass. |

### ci-harness.AC2.2 — `ruff format --check .` passes

| Field | Value |
|-------|-------|
| **Verification** | Workflow run + local command |
| **What to check** | The quality job's "Run ruff format check" step exits 0. Locally: `uv run ruff format --check .` exits 0. |
| **Evidence** | Green quality job. Local exit code 0. |

### ci-harness.AC2.3 — `vulture` reports no dead code above confidence threshold

| Field | Value |
|-------|-------|
| **Verification** | Workflow run + local command |
| **What to check** | The quality job's "Run vulture" step exits 0. Locally: `uv run vulture` exits 0. |
| **Evidence** | Green quality job. Local exit code 0 with no output. |

### ci-harness.AC2.4 — `complexipy` reports no functions above complexity 15

| Field | Value |
|-------|-------|
| **Verification** | Human verification (temporarily bypassed) |
| **What to check** | The complexipy step is commented out in `.github/workflows/ci.yml` with a reference to a tracking issue. The pre-commit hook still blocks new violations locally. |
| **Evidence** | (1) The workflow file contains the commented-out step with explanation. (2) A GitHub issue tracks re-enablement. (3) The pre-commit complexipy hook still runs on local commits. |
| **Why not automated** | 59 pre-existing violations. CI enablement is intentionally deferred. The bypass is tracked via GitHub issue. |

### ci-harness.AC2.5 — `pip-audit` reports no known vulnerabilities

| Field | Value |
|-------|-------|
| **Verification** | Workflow run + local command |
| **What to check** | The quality job's "Run pip-audit" step exits 0. Locally: `uv run pip-audit` exits 0. |
| **Evidence** | Green quality job. Local output: "No known vulnerabilities found." |

### ci-harness.AC2.6 — `ty check` passes

| Field | Value |
|-------|-------|
| **Verification** | Workflow run + local command |
| **What to check** | The quality job's "Run ty type check" step exits 0. Locally: `uvx ty check` exits 0. |
| **Evidence** | Green quality job. Local exit code 0. |

### ci-harness.AC2.7 — Introducing a ruff S violation fails the quality job

| Field | Value |
|-------|-------|
| **Verification** | Local command (negative test) |
| **What to check** | Adding a known S-rule violation (e.g., `password = "hardcoded"` in a source file) causes `uv run ruff check .` to exit non-zero with an S105 violation. |
| **Evidence** | Local ruff output showing the S105 error. Then revert the change. |
| **Why not a CI test** | CI tests the positive case (code is clean). The negative case is verified locally during Phase 3 to confirm the rules are actually active, then reverted. Running a deliberately-failing commit in CI would be wasteful. |

---

## ci-harness.AC3: test-all job runs correctly

### ci-harness.AC3.1 — `uv run grimoire test all` completes against Postgres

| Field | Value |
|-------|-------|
| **Verification** | Workflow run |
| **What to check** | The test-all job completes successfully. The log shows `uv run grimoire test all` running tests against the Postgres service container. |
| **Evidence** | Green test-all job. Log shows test collection and pass count. |

### ci-harness.AC3.2 — MeCab-dependent tests pass

| Field | Value |
|-------|-------|
| **Verification** | Workflow run |
| **What to check** | The test-all job log includes `tests/unit/test_word_count.py` passing. The "Install system dependencies" step log shows `mecab` and `libmecab-dev` installed. |
| **Evidence** | Green test-all job. Log grep for `test_word_count` shows collected and passed tests. |

### ci-harness.AC3.3 — A genuinely failing test fails the job

| Field | Value |
|-------|-------|
| **Verification** | Structural (inherent to pytest) |
| **What to check** | `uv run grimoire test all` delegates to pytest, which exits non-zero on any test failure. GitHub Actions fails the step on non-zero exit. This is the default behaviour of both pytest and GitHub Actions. |
| **Evidence** | No special verification needed. This is how pytest and GitHub Actions work by default. If desired, verify locally: add `assert False` to a test, run `uv run grimoire test all`, confirm exit code 1, revert. |
| **Why not a CI test** | Same reasoning as AC2.7 — deliberately breaking a test in CI is wasteful. The invariant is structural: pytest returns non-zero on failure, Actions treats non-zero as failure. |

---

## ci-harness.AC4: E2E job runs correctly

### ci-harness.AC4.1 — `uv run grimoire e2e run` completes against Postgres with Playwright

| Field | Value |
|-------|-------|
| **Verification** | Workflow run |
| **What to check** | The e2e job completes successfully. The log shows Playwright chromium installed, server started, and tests running. |
| **Evidence** | Green e2e job. Log shows "Install Playwright browsers" step and "Run E2E tests" step both succeeding. |

### ci-harness.AC4.2 — App starts successfully with MeCab available

| Field | Value |
|-------|-------|
| **Verification** | Workflow run (implicit) |
| **What to check** | The E2E tests require the NiceGUI app to start. If MeCab were missing, the app would fail to import `word_count.py` and crash at startup, failing all E2E tests. |
| **Evidence** | Green e2e job (implies app started, which implies MeCab loaded). |

### ci-harness.AC4.3 — Mock auth works (no Stytch credentials needed)

| Field | Value |
|-------|-------|
| **Verification** | Workflow run (implicit) |
| **What to check** | The E2E server sets `DEV__AUTH_MOCK=true` internally. If mock auth were broken, the app would try to initialise Stytch, fail (no credentials), and crash. No `STYTCH_*` secrets are configured in the workflow. |
| **Evidence** | Green e2e job (implies auth mock worked). No secrets in `.github/workflows/ci.yml`. |

---

## ci-harness.AC5: Bandit-to-ruff migration

### ci-harness.AC5.1 — Ruff S rules enabled with equivalent skips

| Field | Value |
|-------|-------|
| **Verification** | Static inspection + local command |
| **What to check** | (1) `pyproject.toml` `[tool.ruff.lint]` `select` includes `"S"`. (2) `ignore` includes `S404`, `S603`, `S607`. (3) `per-file-ignores` for `tests/**/*.py` includes `S101`. |
| **Evidence** | Inspect `pyproject.toml` diff in the PR. `uv run ruff check . --select S` exits 0. |
| **How to verify** | `grep '"S"' pyproject.toml` in the ruff lint select section. `grep 'S404' pyproject.toml`. `grep 'S101' pyproject.toml` in per-file-ignores. |

### ci-harness.AC5.2 — Bandit removed from dev dependencies and pre-commit config

| Field | Value |
|-------|-------|
| **Verification** | Static inspection + local command |
| **What to check** | (1) No `bandit` entry in `pyproject.toml` dev dependencies. (2) No `[tool.bandit]` section in `pyproject.toml`. (3) No bandit hook in `.pre-commit-config.yaml`. |
| **Evidence** | `grep -i bandit pyproject.toml` returns nothing (or only a comment about migration). `grep -i bandit .pre-commit-config.yaml` returns nothing. |

### ci-harness.AC5.3 — `_server_script.py` has per-file-ignore for security rules

| Field | Value |
|-------|-------|
| **Verification** | Static inspection |
| **What to check** | `pyproject.toml` `[tool.ruff.lint.per-file-ignores]` has an entry for `"src/promptgrimoire/cli/e2e/_server_script.py"` that includes `S101`, `S108`, `S110`. |
| **Evidence** | Inspect the per-file-ignores section in `pyproject.toml`. |

### ci-harness.AC5.4 — `uv run bandit` fails (no longer installed)

| Field | Value |
|-------|-------|
| **Verification** | Local command |
| **What to check** | `uv run bandit --version` fails with an error (bandit is not a dev dependency and was never directly installed — it was only pulled in by pre-commit's isolated environment). |
| **Evidence** | Command exits non-zero with error output. |

---

## ci-harness.AC6: pip-audit integration

### ci-harness.AC6.1 — `pip-audit` is in dev dependencies

| Field | Value |
|-------|-------|
| **Verification** | Static inspection |
| **What to check** | `pip-audit` appears in the `[dependency-groups]` `dev` list in `pyproject.toml`. |
| **Evidence** | `grep 'pip-audit' pyproject.toml` returns a match in the dev dependencies section. |

### ci-harness.AC6.2 — `uv run pip-audit` scans and exits 0

| Field | Value |
|-------|-------|
| **Verification** | Workflow run + local command |
| **What to check** | Locally: `uv run pip-audit` exits 0 with "No known vulnerabilities found." In CI: the quality job's pip-audit step passes. |
| **Evidence** | Local exit code 0. Green quality job. |

---

## Verification Summary

| AC | Method | Automated? | Phase |
|----|--------|------------|-------|
| AC1.1 | Human: check CI run after merge to main | No | Post-merge |
| AC1.2 | Human: check CI run on PR push | No | Phase 3 Task 6 |
| AC1.3 | Static inspection of `on:` block | Partially (grep) | Phase 2 Task 1 |
| AC1.4 | Static inspection for absence of `needs:` | Yes (grep) | Phase 2 Task 1 |
| AC2.1 | CI workflow run + local `ruff check .` | Yes | Phase 3 Task 3 |
| AC2.2 | CI workflow run + local `ruff format --check .` | Yes | Phase 3 Task 5 |
| AC2.3 | CI workflow run + local `vulture` | Yes | Phase 3 Task 1 |
| AC2.4 | Human: verify bypass + tracking issue | No (deferred) | Phase 3 Task 2 |
| AC2.5 | CI workflow run + local `pip-audit` | Yes | Phase 3 Task 4 |
| AC2.6 | CI workflow run + local `uvx ty check` | Yes | Phase 3 Task 5 |
| AC2.7 | Local negative test (introduce violation, verify ruff catches it, revert) | Manual | Phase 3 Task 3 |
| AC3.1 | CI workflow run (test-all job green) | Yes | Phase 3 Task 6 |
| AC3.2 | CI workflow run (test_word_count in logs) | Yes | Phase 3 Task 6 |
| AC3.3 | Structural (pytest + Actions default behaviour) | Inherent | N/A |
| AC4.1 | CI workflow run (e2e job green) | Yes | Phase 3 Task 6 |
| AC4.2 | CI workflow run (implicit — app must start) | Yes (implicit) | Phase 3 Task 6 |
| AC4.3 | CI workflow run (implicit — no secrets configured) | Yes (implicit) | Phase 3 Task 6 |
| AC5.1 | Static inspection of pyproject.toml + local ruff | Yes (grep + ruff) | Phase 1 Task 1 |
| AC5.2 | Static inspection of pyproject.toml + pre-commit config | Yes (grep) | Phase 1 Task 3 |
| AC5.3 | Static inspection of pyproject.toml per-file-ignores | Yes (grep) | Phase 1 Task 1 |
| AC5.4 | Local command: `uv run bandit --version` fails | Manual | Phase 1 Task 3 |
| AC6.1 | Static inspection of pyproject.toml | Yes (grep) | Phase 1 Task 4 |
| AC6.2 | CI workflow run + local `pip-audit` | Yes | Phase 1 Task 5 |

## Key Observations

1. **No unit tests are needed.** This feature is infrastructure (CI workflow + tool configuration). The "tests" are the tools themselves running in CI and passing.

2. **The CI run is the test.** For AC2.x, AC3.x, and AC4.x, the primary verification is that the corresponding CI job passes green on the PR. Each tool (ruff, vulture, pip-audit, ty, pytest, playwright) is its own test harness.

3. **Four criteria require human verification:**
   - AC1.1 (push-to-main trigger) — only verifiable after merge
   - AC1.2 (PR trigger) — verified during Phase 3 Task 6
   - AC1.3 (no trigger on non-main push) — partially verifiable via static inspection
   - AC2.4 (complexipy) — intentionally bypassed with tracking issue

4. **Two criteria are verified by negative local tests** (AC2.7 and AC5.4) where running in CI would be wasteful. These are manual one-time verifications during implementation.

5. **Three criteria are implicitly verified** (AC3.3, AC4.2, AC4.3) — they describe invariants that hold by construction. If they were violated, other criteria would fail first.
