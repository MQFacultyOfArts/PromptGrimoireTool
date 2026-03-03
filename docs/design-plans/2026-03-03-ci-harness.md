# CI Harness Design

**GitHub Issue:** None

## Summary

This document specifies the design for a GitHub Actions CI harness for PromptGrimoire. The current codebase has a disabled workflow file that is structurally outdated — it predates the `grimoire` CLI, the Postgres service container requirement, MeCab word-count dependencies, and the managed server lifecycle used by E2E tests. The new harness replaces it with three parallel jobs: a lightweight quality job (linting, formatting, dead code detection, complexity analysis, security scanning, type checking) and two heavier jobs (unit+integration tests and Playwright E2E tests) that each spin up a Postgres 17 service container and install MeCab system dependencies. All three jobs share a common setup preamble using `uv` for dependency and Python version management.

The implementation is structured in three phases. Phase 1 migrates security scanning from standalone Bandit to ruff's built-in `S` rule set and adds `pip-audit` for dependency vulnerability scanning — consolidating tooling before the CI workflow is written. Phase 2 creates the workflow file, deleting the disabled predecessor. Phase 3 stabilises the result by fixing anything newly surfaced by the enabled checks and suppressing documented false positives. No secrets are required: Stytch authentication is replaced by mock auth in all test contexts, and no external API calls are made during the test runs.

## Definition of Done

1. **GitHub Actions workflow runs on push+PR to main** — `.github/workflows/ci.yml` triggers on push to `main` and pull requests targeting `main`
2. **Quality job passes** — ruff lint (including S/security rules), ruff format check, vulture dead code detection, complexipy cognitive complexity gate, pip-audit dependency vulnerability scan, and ty type checking all pass
3. **test-all job passes** — `uv run grimoire test all` runs unit + integration tests against a Postgres service container with MeCab system dependencies installed
4. **E2E job passes** — `uv run grimoire e2e run` runs Playwright E2E tests against a Postgres service container with MeCab and Playwright chromium installed
5. **Ruff S rules replace standalone Bandit** — ruff's `S` rule set enabled with equivalent skips (S101, S404, S603, S607); standalone bandit removed from pre-commit hooks and dev dependencies
6. **pip-audit added** — dependency vulnerability scanning integrated into quality job and added to dev dependencies

## Acceptance Criteria

### ci-harness.AC1: Workflow triggers correctly
- **ci-harness.AC1.1 Success:** Push to `main` triggers all three jobs
- **ci-harness.AC1.2 Success:** PR targeting `main` triggers all three jobs
- **ci-harness.AC1.3 Success:** Push to non-main branch does not trigger CI
- **ci-harness.AC1.4 Success:** All three jobs run in parallel (no `needs:` dependencies between them)

### ci-harness.AC2: Quality job catches issues
- **ci-harness.AC2.1 Success:** `ruff check .` passes (including S security rules)
- **ci-harness.AC2.2 Success:** `ruff format --check .` passes
- **ci-harness.AC2.3 Success:** `vulture` reports no dead code above confidence threshold
- **ci-harness.AC2.4 Success:** `complexipy` reports no functions above complexity 15
- **ci-harness.AC2.5 Success:** `pip-audit` reports no known vulnerabilities
- **ci-harness.AC2.6 Success:** `ty check` passes
- **ci-harness.AC2.7 Failure:** Introducing a ruff S violation (e.g. hardcoded password) fails the quality job

### ci-harness.AC3: test-all job runs correctly
- **ci-harness.AC3.1 Success:** `uv run grimoire test all` completes against Postgres service container
- **ci-harness.AC3.2 Success:** MeCab-dependent tests (test_word_count.py) pass
- **ci-harness.AC3.3 Failure:** A genuinely failing test fails the job

### ci-harness.AC4: E2E job runs correctly
- **ci-harness.AC4.1 Success:** `uv run grimoire e2e run` completes against Postgres with Playwright chromium
- **ci-harness.AC4.2 Success:** App starts successfully with MeCab available
- **ci-harness.AC4.3 Success:** Mock auth works (no Stytch credentials needed)

### ci-harness.AC5: Bandit-to-ruff migration
- **ci-harness.AC5.1 Success:** Ruff S rules enabled in `pyproject.toml` with equivalent skips for S101, S404, S603, S607
- **ci-harness.AC5.2 Success:** Bandit removed from dev dependencies and pre-commit config
- **ci-harness.AC5.3 Success:** `_server_script.py` has per-file-ignore for security rules
- **ci-harness.AC5.4 Failure:** `uv run bandit` fails (no longer installed)

### ci-harness.AC6: pip-audit integration
- **ci-harness.AC6.1 Success:** `pip-audit` is in dev dependencies
- **ci-harness.AC6.2 Success:** `uv run pip-audit` scans installed packages and exits 0 when clean

## Glossary

- **GitHub Actions**: GitHub's built-in CI/CD platform. Workflows are YAML files in `.github/workflows/` that run jobs on cloud runners in response to git events.
- **CI (Continuous Integration)**: Automated pipeline that runs tests and quality checks on every push or pull request, catching regressions before code merges.
- **uv**: A fast Python package and project manager (from Astral). Replaces pip/virtualenv/pyenv. `uv sync` installs dependencies from a lockfile; `uv run` executes commands in the managed environment.
- **ruff**: A fast Python linter and formatter (from Astral). Combines and replaces tools like flake8, isort, and pyupgrade. Rule sets are identified by letter prefix (e.g. `S` for security, `E` for pycodestyle errors).
- **ruff S rules**: ruff's port of the Bandit security linter. Detects common Python security anti-patterns such as hardcoded passwords, unsafe subprocess calls, and use of weak cryptographic functions.
- **Bandit**: A standalone Python security linter being replaced by ruff's S rules. B-prefixed rule codes (B101, B404, B603, B607) map to S-prefixed equivalents in ruff.
- **vulture**: A Python tool that detects dead code — functions, classes, and variables that are defined but never called. May produce false positives with framework-driven code (SQLModel fields, NiceGUI callbacks, Typer commands).
- **complexipy**: A Python tool that measures cognitive complexity of functions and fails above a configurable threshold. Cognitive complexity is a measure of how difficult code is to understand, distinct from cyclomatic complexity.
- **pip-audit**: A tool that scans installed Python packages against known CVE databases. In this project it is invoked via `uv run pip-audit` to scan the locked environment.
- **ty**: A fast Python type checker (from Astral), used here as a CI quality gate alongside ruff.
- **Playwright**: A browser automation framework used for E2E testing. The CI job installs Chromium via `playwright install --with-deps chromium`.
- **E2E (End-to-End) tests**: Tests that exercise the full application stack through a real browser, as opposed to unit or integration tests that test isolated components.
- **Postgres service container**: A Docker container running PostgreSQL that GitHub Actions spins up alongside a job. The application connects to it via `localhost:5432` during the test run.
- **MeCab**: A Japanese morphological analyser required by `word_count.py` for CJK text segmentation. It must be installed as a system package (`apt install mecab libmecab-dev`) before the application or its tests can be imported.
- **Mock auth**: A development/test mode flag (`DEV__AUTH_MOCK=true`) that bypasses Stytch authentication, allowing CI to run without Stytch API credentials.
- **pre-commit**: A framework for managing git commit hooks. Configured in `.pre-commit-config.yaml`; runs checks (ruff, bandit, complexipy, etc.) before each local commit.
- **per-file-ignore**: A ruff configuration option that suppresses specific rule codes for named files, used here to exempt `_server_script.py` from security rules that would otherwise flag its subprocess usage.
- **vulture allowlist**: A Python file (`.vulture_allowlist.py`) containing stub definitions of symbols that vulture incorrectly marks as dead. It is a documented vulture pattern for suppressing false positives from framework-driven code.
- **CVE**: Common Vulnerabilities and Exposures — a public catalogue of security vulnerabilities in software packages. pip-audit cross-references installed packages against this catalogue.

## Architecture

Three parallel GitHub Actions jobs on `ubuntu-latest` runners:

```
on: push to main, PR to main

┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│     quality      │  │    test-all     │  │       e2e       │
│                  │  │                 │  │                 │
│ ruff check .     │  │ services:       │  │ services:       │
│ ruff format      │  │   postgres:17   │  │   postgres:17   │
│ vulture          │  │                 │  │                 │
│ complexipy       │  │ apt: mecab      │  │ apt: mecab      │
│ pip-audit        │  │     libmecab-dev│  │     libmecab-dev│
│ ty check         │  │                 │  │                 │
│                  │  │ grimoire test   │  │ playwright      │
│ no services      │  │   all           │  │   install       │
│ no apt packages  │  │                 │  │ grimoire e2e    │
│                  │  │                 │  │   run            │
└─────────────────┘  └─────────────────┘  └─────────────────┘
     ~1 min               ~3-5 min             ~15 min
```

All three jobs share a common setup preamble:
1. `actions/checkout@v6.0.1`
2. `astral-sh/setup-uv@v7.2.0` with `enable-cache: true` and `cache-dependency-glob: "uv.lock"`
3. `uv python install 3.14`
4. `uv sync --all-extras`

**Postgres service container** (test-all and e2e only): `postgres:17` image with `POSTGRES_DB=promptgrimoire_test`, `POSTGRES_PASSWORD=postgres`, port 5432 exposed, health-checked via `pg_isready`.

**Environment variables** (test-all and e2e only):
- `DEV__TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/promptgrimoire_test`
- `DEV__AUTH_MOCK=true` (E2E server sets this automatically, but explicit for clarity)

**No secrets required.** Mock auth eliminates Stytch credentials. No Claude API calls in tests. No coverage upload.

**System packages** (test-all and e2e): `mecab libmecab-dev` — required because `word_count.py` imports MeCab at module level, and `tests/unit/test_word_count.py` imports from `word_count`. E2E needs it because the NiceGUI app won't start without it.

**Playwright** (e2e only): `uv run playwright install --with-deps chromium` installs the browser binary and system dependencies (fonts, etc.).

### Ruff S Rules Migration

Replace standalone Bandit with ruff's native security rule set. The current bandit config skips B101 (assert), B404/B603/B607 (subprocess/shell). Equivalent ruff ignores:

| Bandit skip | Ruff equivalent | Reason |
|-------------|----------------|--------|
| B101 | S101 | Asserts used in tests and type narrowing |
| B404 | S404 | subprocess import is intentional |
| B603 | S603 | subprocess calls with controlled args |
| B607 | S607 | partial executable paths (e.g. `uv`, `playwright`) |

These ignores apply globally. The existing `bandit.exclude` for `_server_script.py` translates to a ruff per-file-ignore entry.

### pip-audit Integration

`pip-audit` scans installed packages for known CVEs. In a uv-managed project, the invocation is:

```bash
uv run pip-audit
```

This scans the installed environment (which mirrors `uv.lock`). If vulnerabilities are found, the job fails. False positives can be suppressed via `--ignore-vuln PYSEC-YYYY-NNNN` flags or a `pyproject.toml` config section.

## Existing Patterns

The disabled workflow at `.github/workflows/ci.yml.disabled` provides the structural template. It already uses `actions/checkout@v6.0.1`, `astral-sh/setup-uv@v7.2.0`, and `uv python install 3.14`. However, it is outdated:

- Uses raw `uv run pytest` instead of `uv run grimoire test all` / `uv run grimoire e2e run`
- No Postgres service container (tests requiring DB would fail)
- No MeCab system dependencies
- No bandit/vulture/complexipy/pip-audit
- E2E job uses raw `uv run pytest tests/e2e/` instead of the CLI's managed server lifecycle

The new workflow replaces the disabled file entirely. The CLI commands (`grimoire test all`, `grimoire e2e run`) handle database cleanup (Alembic migrations + TRUNCATE), server lifecycle (port allocation, subprocess management), and retry logic internally.

Pre-commit hooks (`.pre-commit-config.yaml`) currently include standalone bandit. This will be removed as part of the ruff S migration. The complexipy hook remains in pre-commit for local developer feedback.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Ruff S Rules and Dependency Changes

**Goal:** Migrate security scanning from standalone bandit to ruff's S rule set and add pip-audit.

**Components:**
- `pyproject.toml` — add `"S"` to `[tool.ruff.lint] select`, add S101/S404/S603/S607 to appropriate ignore lists, add per-file-ignore for `_server_script.py`, add `pip-audit` to dev deps, remove `bandit` from dev deps
- `.pre-commit-config.yaml` — remove bandit hook

**Dependencies:** None (first phase)

**Done when:** `uv run ruff check .` passes with S rules enabled, `uv run pip-audit` runs without error, bandit is no longer in the dependency tree or pre-commit config
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: CI Workflow

**Goal:** Create the GitHub Actions workflow file with all three jobs.

**Components:**
- `.github/workflows/ci.yml` — new workflow file with quality, test-all, and e2e jobs
- `.github/workflows/ci.yml.disabled` — deleted (replaced by new workflow)

**Dependencies:** Phase 1 (ruff S rules must be configured before the quality job can run them)

**Done when:** Workflow file exists with correct structure; pushing to a branch or opening a PR triggers all three jobs. Quality job runs lint/format/vulture/complexipy/pip-audit/ty. Test-all job runs `uv run grimoire test all` against Postgres. E2E job runs `uv run grimoire e2e run` against Postgres with Playwright.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Verification and Stabilisation

**Goal:** Ensure all three jobs pass on the current codebase and fix any issues surfaced by newly-enabled checks.

**Components:**
- Any source files flagged by ruff S rules, vulture, or complexipy that weren't caught before
- `pyproject.toml` — possible vulture allowlist or ruff per-file-ignores if false positives arise

**Dependencies:** Phase 2 (workflow must exist to run)

**Done when:** All three CI jobs pass green on a PR to main. Any false positives are suppressed with documented rationale.
<!-- END_PHASE_3 -->

## Additional Considerations

**Postgres health check parameters:** The service container health check (`pg_isready`) uses GitHub Actions defaults. During implementation, investigate whether explicit retry count, interval, and timeout values are needed to prevent flaky failures on slow runners.

**Stabilisation strategy:** The codebase is in active cleanup (CLI migration from monolithic `cli.py` to `cli/` package). Phase 3 will likely surface issues from newly-enabled checks. Strategy: make temporary bypasses to get CI green, file a GitHub issue per bypass, and resolve them as the migration completes. Do not block CI enablement on pre-existing code quality issues.

**Vulture false positives:** Vulture at 80% confidence may flag SQLModel fields, NiceGUI callbacks, or Typer commands that are used via framework magic rather than direct Python calls. If this happens, create a vulture allowlist file (`.vulture_allowlist.py`) with the false positives. This is a known vulture pattern — the allowlist file contains variable/function stubs that tell vulture "these are used."

**pip-audit uv compatibility:** pip-audit can scan the current environment when run via `uv run pip-audit`. If this doesn't work as expected in CI (where the environment is freshly created by `uv sync`), the fallback is `uv export --format requirements-txt | uv run pip-audit -r /dev/stdin`.

**Future additions (not in scope):**
- Coverage reporting (codecov) — add when CI is stable
- `e2e slow` with TinyTeX — add as a separate scheduled/manual job when needed
- CD / deployment automation — separate design
