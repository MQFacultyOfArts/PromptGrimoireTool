# CI Harness Implementation Plan — Phase 3

**Goal:** Ensure all three CI jobs pass on the current codebase. Fix genuine issues. Temporarily bypass pre-existing violations with documented rationale. File a GitHub issue for each bypass.

**Architecture:** Run each quality check locally. For checks that fail on pre-existing code (not code introduced by this branch), add temporary bypasses and file issues. The stabilisation strategy is: bypass-then-issue — don't block CI enablement on pre-existing code quality debt.

**Tech Stack:** ruff, vulture, complexipy, pip-audit, ty, GitHub CLI (`gh`)

**Scope:** 3 phases from original design (phase 3 of 3)

**Codebase verified:** 2026-03-03

**Pre-existing findings from local runs:**
- **complexipy:** 59 functions exceed complexity 15 (exit code 1). Largest: `course_detail_page` at 130. These are all pre-existing — the pre-commit hook blocks new violations but existing code was never cleaned up.
- **vulture:** 4 findings — `exc_val` and `exc_tb` unused in `docs/guide.py` `__exit__` methods (required by Python `__exit__` protocol but unused). Exit code 3.
- **ruff S rules:** Not yet tested (depends on Phase 1 completing first).
- **pip-audit:** Not yet tested (depends on Phase 1 completing first).

---

## Acceptance Criteria Coverage

This phase implements and tests:

### ci-harness.AC2: Quality job catches issues
- **ci-harness.AC2.1 Success:** `ruff check .` passes (including S security rules)
- **ci-harness.AC2.3 Success:** `vulture` reports no dead code above confidence threshold
- **ci-harness.AC2.4 Success:** `complexipy` reports no functions above complexity 15
- **ci-harness.AC2.7 Failure:** Introducing a ruff S violation (e.g. hardcoded password) fails the quality job

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Fix vulture findings

**Verifies:** ci-harness.AC2.3

**Files:**
- Modify: `src/promptgrimoire/docs/guide.py` lines 86–87, 173–174

**Step 1: Identify the vulture findings**

Run:
```bash
uv run vulture src/promptgrimoire --min-confidence 80
```

Expected output:
```
src/promptgrimoire/docs/guide.py:86: unused variable 'exc_val' (100% confidence)
src/promptgrimoire/docs/guide.py:87: unused variable 'exc_tb' (100% confidence)
src/promptgrimoire/docs/guide.py:173: unused variable 'exc_val' (100% confidence)
src/promptgrimoire/docs/guide.py:174: unused variable 'exc_tb' (100% confidence)
```

These are `__exit__` method parameters required by the context manager protocol. They must exist in the signature but are not used. The standard Python convention is to prefix with underscore.

**Step 2: Rename parameters to `_exc_val` and `_exc_tb`**

In `src/promptgrimoire/docs/guide.py`, rename the unused parameters in both `__exit__` methods:

```python
def __exit__(self, exc_type, _exc_val, _exc_tb):
```

**Step 3: Verify vulture passes**

```bash
uv run vulture src/promptgrimoire --min-confidence 80
```

Expected: No output, exit code 0.

**Step 4: Commit**

```bash
git add src/promptgrimoire/docs/guide.py
git commit -m "fix: prefix unused __exit__ params to satisfy vulture"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Bypass complexipy in CI, file issue

**Verifies:** ci-harness.AC2.4 (temporary bypass)

**Files:**
- Modify: `.github/workflows/ci.yml` (remove or comment out complexipy step)

**Context:** 59 functions exceed complexity 15. These are all pre-existing — the pre-commit hook blocks new violations, but the codebase was never retroactively cleaned up. Fixing 59 functions is a major refactoring effort that should not block CI enablement.

**Step 1: Remove the complexipy step from the quality job**

In `.github/workflows/ci.yml`, remove or comment out the complexipy step:

```yaml
      # TEMPORARILY DISABLED — 59 pre-existing violations.
      # See GitHub issue for tracking. Re-enable after cleanup.
      # - name: Run complexipy (cognitive complexity)
      #   run: uv run complexipy src/promptgrimoire --max-complexity-allowed 15
```

**Step 2: File a GitHub issue for the bypass**

```bash
gh issue create \
  --title "CI: re-enable complexipy after complexity cleanup" \
  --body "$(cat <<'EOF'
## Context

The CI harness (`.github/workflows/ci.yml`) has complexipy temporarily disabled because 59 functions in `src/promptgrimoire/` exceed the cognitive complexity threshold of 15.

The pre-commit hook blocks new violations, but existing code was never retroactively cleaned up. The CLI migration (#211) is actively fixing the CLI module functions. Once the backlog of violations is reduced to a manageable number, complexipy should be re-enabled in CI.

## Current violations

Run `uv run complexipy src/promptgrimoire --max-complexity-allowed 15` to see the full list.

Worst offenders:
- `course_detail_page`: 130
- `_setup_client_sync`: 63
- `_render_tag_row`: 38
- `_detect_block_boundaries`: 36

## Done when

- [ ] `uv run complexipy src/promptgrimoire --max-complexity-allowed 15` exits 0
- [ ] complexipy step uncommented in `.github/workflows/ci.yml`
EOF
)" \
  --label "tech-debt"
```

**Step 3: Commit the workflow change**

```bash
git add .github/workflows/ci.yml
git commit -m "chore: temporarily disable complexipy in CI (pre-existing violations)"
```
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_3 -->
### Task 3: Verify ruff S rules pass clean

**Verifies:** ci-harness.AC2.1

**Files:** None (verification only)

**Precondition:** Phase 1 must be complete (S rules enabled and violations fixed in Phase 1 Tasks 1–2).

**Step 1: Verify ruff passes with all rules including S**

```bash
uv run ruff check .
```

Expected: No violations, exit code 0. If ruff reports any S-rule violations, something regressed since Phase 1 — investigate and fix before proceeding.
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Run pip-audit and handle findings

**Verifies:** ci-harness.AC2.5

**Files:**
- Possibly: `pyproject.toml`, `uv.lock` (if upgrading deps)
- Possibly: `.github/workflows/ci.yml` (if adding `--ignore-vuln` flags)

**Precondition:** Phase 1 must be complete (pip-audit installed).

**Step 1: Run pip-audit**

```bash
uv run pip-audit
```

**Step 2: If vulnerabilities are found**

For each vulnerability:
- **If fix available:** Upgrade the package: `uv add <package>@latest`
- **If no fix available and low severity:** Add `--ignore-vuln <ID>` to the CI step and file an issue
- **If no fix available and high severity:** Discuss with the team

If `--ignore-vuln` flags are needed, update the CI workflow step:

```yaml
      - name: Run pip-audit (dependency vulnerabilities)
        run: uv run pip-audit --ignore-vuln PYSEC-YYYY-NNNN
```

**Step 3: Commit if changes were needed**

```bash
git add -u
git commit -m "deps: resolve pip-audit findings"
```
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Run full quality check suite locally

**Verifies:** ci-harness.AC2.1–AC2.6 (except AC2.4 which is bypassed)

**Files:** None (verification only)

**Step 1: Run each check in order**

```bash
uv run ruff check .
uv run ruff format --check .
uv run vulture  # reads config from pyproject.toml [tool.vulture]
# complexipy skipped (59 pre-existing violations, tracked in issue)
uv run pip-audit
uvx ty check
```

**Step 2: Verify all pass with exit code 0**

Each command should exit 0. If any fails, fix the issue before proceeding.

**Step 3: Run the test suite locally**

```bash
uv run grimoire test all
```

Expected: All tests pass (this verifies the test infrastructure works before CI runs it).
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Push branch, open PR, and verify CI triggers

**Verifies:** ci-harness.AC1.1, ci-harness.AC1.2, ci-harness.AC3.1, ci-harness.AC4.1

**Files:** None (verification only)

**Important:** CI only triggers on pushes to `main` and PRs targeting `main`. Pushing to a feature branch alone does NOT trigger CI. A PR must exist (or be created) before the push will trigger a workflow run.

**Step 1: Open a PR targeting main (if not already open)**

```bash
gh pr create --title "feat: CLI typer migration and CI harness" --body "..."
```

If a PR already exists for this branch, skip this step.

**Step 2: Push the branch**

```bash
git push origin cli-typer-211
```

With a PR open, this push will trigger the CI workflow.

**Step 3: Monitor CI**

```bash
gh run list --branch cli-typer-211 --limit 3
```

Wait for all three jobs to report. Check each:

```bash
gh run view <run-id>
```

**Step 4: If any job fails**

- Read the log: `gh run view <run-id> --log-failed`
- Fix the issue locally
- Push again
- Repeat until all three jobs pass green

**Step 5: When all three jobs pass**

CI harness is complete. The workflow is validated end-to-end.
<!-- END_TASK_6 -->

---

## UAT Steps

1. [ ] Ensure a PR targeting `main` is open for this branch
2. [ ] Push the latest changes: `git push origin cli-typer-211`
3. [ ] Navigate to the PR on GitHub and verify three CI jobs appear: `quality`, `test-all`, `e2e`
4. [ ] Verify the `quality` job log shows: ruff check, ruff format, vulture, pip-audit, and ty check all ran and passed
5. [ ] Verify the `test-all` job log shows: `uv run grimoire test all` completed with tests passing
6. [ ] Verify the `e2e` job log shows: Playwright chromium installed, `uv run grimoire e2e run` completed with tests passing
7. [ ] Verify the `quality` job does NOT run complexipy (temporarily disabled)

## Evidence Required

- [ ] Screenshot or link to PR showing all three jobs green
- [ ] CI run URL from `gh run view`
