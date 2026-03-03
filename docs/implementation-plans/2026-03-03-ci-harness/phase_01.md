# CI Harness Implementation Plan — Phase 1

**Goal:** Migrate security scanning from standalone Bandit to ruff's S rule set and add pip-audit for dependency vulnerability scanning.

**Architecture:** Update ruff config in pyproject.toml to enable S rules with equivalent skips. Remove bandit from pre-commit hooks. Add pip-audit as a dev dependency.

**Tech Stack:** ruff (S rules), pip-audit, uv

**Scope:** 3 phases from original design (phase 1 of 3)

**Codebase verified:** 2026-03-03

---

## Acceptance Criteria Coverage

This phase implements and tests:

### ci-harness.AC5: Bandit-to-ruff migration
- **ci-harness.AC5.1 Success:** Ruff S rules enabled in `pyproject.toml` with equivalent skips for S101, S404, S603, S607
- **ci-harness.AC5.2 Success:** Bandit removed from dev dependencies and pre-commit config
- **ci-harness.AC5.3 Success:** `_server_script.py` has per-file-ignore for security rules
- **ci-harness.AC5.4 Failure:** `uv run bandit` fails (no longer installed)

### ci-harness.AC6: pip-audit integration
- **ci-harness.AC6.1 Success:** `pip-audit` is in dev dependencies
- **ci-harness.AC6.2 Success:** `uv run pip-audit` scans installed packages and exits 0 when clean

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: Enable ruff S rules in pyproject.toml

**Verifies:** ci-harness.AC5.1, ci-harness.AC5.3

**Files:**
- Modify: `pyproject.toml` lines 59–78 (ruff lint select/ignore)
- Modify: `pyproject.toml` lines 80–81 (per-file-ignores for tests)
- Modify: `pyproject.toml` lines 128–133 (per-file-ignores for _server_script.py)

**Step 1: Add `"S"` to the ruff lint select list**

In `pyproject.toml` at `[tool.ruff.lint]`, add `"S"` to the `select` array:

```toml
select = [
    "E",      # pycodestyle errors
    "W",      # pycodestyle warnings
    "F",      # Pyflakes
    "I",      # isort
    "B",      # flake8-bugbear
    "C4",     # flake8-comprehensions
    "UP",     # pyupgrade
    "ARG",    # flake8-unused-arguments
    "S",      # flake8-bandit (security)
    "SIM",    # flake8-simplify
    "TCH",    # flake8-type-checking
    "PTH",    # flake8-use-pathlib
    "ERA",    # eradicate (commented code)
    "PL",     # Pylint
    "RUF",    # Ruff-specific
]
```

**Step 2: Add S404, S603, S607 to the global ignore list**

These correspond to the existing Bandit skips for subprocess usage — the CLI modules use subprocess extensively for running pytest, servers, and build tools. Add to the existing `ignore` array:

```toml
ignore = [
    "PLR0913",  # Too many arguments
    "PLR2004",  # Magic value comparison
    "S404",     # subprocess import (CLI tooling uses subprocess intentionally)
    "S603",     # subprocess call without shell check (controlled args in CLI)
    "S607",     # partial executable path (uv, playwright, etc.)
]
```

Note: S101 (assert) is NOT globally ignored — it goes in per-file-ignores for tests only (Step 3).

**Step 3: Add S101 to per-file-ignores for test files**

In `[tool.ruff.lint.per-file-ignores]`, add `"S101"` to the existing `tests/**/*.py` entry:

```toml
"tests/**/*.py" = [
    "PLC0415",  # Allow imports inside test functions (needed for mocking)
    "S101",     # Assertions are the primary test mechanism
]
```

**Step 4: Add S rules to per-file-ignores for `_server_script.py`**

The server script has intentional test secrets, `/tmp` paths, and bare `except:pass`. Add security rule ignores to its existing entry at lines 128–133:

```toml
"src/promptgrimoire/cli/e2e/_server_script.py" = [
    # Standalone subprocess script — not a regular importable module.
    # Intentional late imports, module-level side effects, global state.
    "PLC0415", "E402", "I001", "B023", "PTH123", "ARG001",
    "SIM115", "PLR0915", "PLW0602", "PLW0603", "RUF100",
    # Security rules: intentional test secrets, /tmp paths, bare except.
    "S101", "S108", "S110",
]
```

- `S101`: assert used for watchdog canary
- `S108`: `/tmp` path usage (intentional for watchdog diagnostics)
- `S110`: bare `except:pass` (intentional in watchdog thread)

**Step 5: Verify ruff passes with S rules enabled**

Run:
```bash
uv run ruff check .
```

Expected: Clean pass (or new S-rule violations to address in Task 2).

If there are new violations, note them — they will be addressed in Task 2.

**Step 6: Commit**

```bash
git add pyproject.toml
git commit -m "chore: enable ruff S (security) rules, replacing bandit"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Fix any ruff S violations surfaced by enabling the rules

**Verifies:** ci-harness.AC5.1 (S rules pass clean)

**Files:**
- Any source files flagged by `uv run ruff check .` after Task 1
- Possibly `pyproject.toml` if additional per-file-ignores are needed

**Step 1: Run ruff check and capture violations**

```bash
uv run ruff check . --select S
```

Review the output. For each violation:

- **If it's a genuine issue** (e.g., hardcoded password, insecure hash): fix the code.
- **If it's a false positive** in CLI/dev tooling: add a per-file-ignore with a comment explaining why.
- **If it's in a file already in per-file-ignores**: add the S rule to that file's ignore list.

**Step 2: Re-run ruff to verify clean**

```bash
uv run ruff check .
```

Expected: No violations.

**Step 3: Commit fixes**

```bash
git add -u  # stage modified files only
git commit -m "fix: resolve ruff S-rule violations"
```

If no violations were found in Step 1, skip this task entirely.
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Remove bandit from pre-commit and pyproject.toml config

**Verifies:** ci-harness.AC5.2, ci-harness.AC5.4

**Files:**
- Modify: `.pre-commit-config.yaml` lines 42–46 (remove bandit hook)
- Modify: `pyproject.toml` lines 182–186 (remove `[tool.bandit]` section)

**Step 1: Remove the bandit hook from `.pre-commit-config.yaml`**

Delete lines 42–46 (the entire bandit repo entry):

```yaml
  - repo: https://github.com/PyCQA/bandit
    rev: 1.9.4
    hooks:
      - id: bandit
        args: ["-c", "pyproject.toml"]
```

**Step 2: Remove the `[tool.bandit]` section from `pyproject.toml`**

Delete lines 182–186:

```toml
[tool.bandit]
  skips = ["B101", "B404", "B603", "B607"]
  # _server_script.py is a standalone subprocess script with intentional
  # test secrets, /tmp paths, and bare except:pass — exclude from scanning.
  exclude_dirs = ["src/promptgrimoire/cli/e2e/_server_script.py"]
```

**Step 3: Verify pre-commit still works**

```bash
uv run pre-commit run --all-files
```

Expected: All hooks pass. The bandit hook should no longer appear in the output.

**Step 4: Verify `uv run bandit` fails (no longer installed)**

```bash
uv run bandit --version
```

Expected: Error (bandit was never a dev dependency — it was only used via pre-commit's isolated environment).

**Step 5: Commit**

```bash
git add .pre-commit-config.yaml pyproject.toml
git commit -m "chore: remove bandit config (replaced by ruff S rules)"
```
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 4-5) -->
<!-- START_TASK_4 -->
### Task 4: Add pip-audit to dev dependencies

**Verifies:** ci-harness.AC6.1

**Files:**
- Modify: `pyproject.toml` (dev dependency group)
- Modify: `uv.lock` (auto-updated by uv)

**Step 1: Add pip-audit**

```bash
uv add --dev pip-audit
```

**Step 2: Verify installation**

```bash
uv run pip-audit --version
```

Expected: Version output (e.g., `pip-audit 2.9.0`).

**Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "deps: add pip-audit for dependency vulnerability scanning"
```
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Run pip-audit and verify clean scan

**Verifies:** ci-harness.AC6.2

**Files:** None (verification only)

**Step 1: Run pip-audit**

```bash
uv run pip-audit
```

Expected: Clean scan with no known vulnerabilities. Output like:

```
No known vulnerabilities found
```

**Step 2: If vulnerabilities are found**

If pip-audit reports vulnerabilities:

- **If the vulnerable package can be upgraded:** Run `uv add <package>@latest` and re-scan.
- **If no fix is available yet:** Document the vulnerability and suppress with `--ignore-vuln`:

```bash
uv run pip-audit --ignore-vuln PYSEC-YYYY-NNNN
```

Note: pip-audit does not support pyproject.toml configuration. Any `--ignore-vuln` flags will need to be passed in the CI workflow command directly.

**Step 3: Commit if any changes were made**

```bash
git add -u
git commit -m "deps: resolve pip-audit findings"
```
<!-- END_TASK_5 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_TASK_6 -->
### Task 6: Update .ed3d/implementation-plan-guidance.md

**Verifies:** None (documentation)

**Files:**
- Modify: `.ed3d/implementation-plan-guidance.md` lines 120–121

**Step 1: Update pre-commit hooks list**

In the "Pre-commit Hooks" section (line 114), update the list to reflect the removal of bandit:

Replace line 120:
```
5. `bandit` - security linting
```

With:
```
5. (removed — security scanning now handled by ruff S rules)
```

Or simply remove the line and renumber.

**Step 2: Commit**

```bash
git add .ed3d/implementation-plan-guidance.md
git commit -m "docs: update implementation guidance — bandit replaced by ruff S rules"
```
<!-- END_TASK_6 -->
