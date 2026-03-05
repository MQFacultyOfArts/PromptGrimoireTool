# CI Harness Implementation Plan — Phase 2

**Goal:** Create the GitHub Actions workflow file with three parallel jobs: quality, test-all, and e2e.

**Architecture:** Single workflow file at `.github/workflows/ci.yml` with three independent jobs. Quality job runs lint/format/security/types with no service containers. Test-all and e2e jobs each use a Postgres 17 service container and MeCab system dependencies. The CLI commands (`grimoire test all`, `grimoire e2e run`) handle database cleanup, server lifecycle, and retry logic internally.

**Tech Stack:** GitHub Actions, astral-sh/setup-uv, postgres:17 service container, Playwright chromium

**Scope:** 3 phases from original design (phase 2 of 3)

**Codebase verified:** 2026-03-03

---

## Acceptance Criteria Coverage

This phase implements and tests:

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

---

<!-- START_TASK_1 -->
### Task 1: Create `.github/workflows/ci.yml`

**Verifies:** ci-harness.AC1.1, ci-harness.AC1.2, ci-harness.AC1.3, ci-harness.AC1.4, ci-harness.AC2.1–AC2.6, ci-harness.AC3.1–AC3.2, ci-harness.AC4.1–AC4.3

**Files:**
- Create: `.github/workflows/ci.yml`

**Step 1: Create the workflow file**

Create `.github/workflows/ci.yml` with the following content:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6.0.1

      - name: Install uv
        uses: astral-sh/setup-uv@v7.2.0
        with:
          version: "latest"
          enable-cache: true
          cache-dependency-glob: "uv.lock"

      - name: Set up Python
        run: uv python install 3.14

      - name: Install dependencies
        run: uv sync --locked --all-groups

      - name: Run ruff lint (includes S security rules)
        run: uv run ruff check .

      - name: Run ruff format check
        run: uv run ruff format --check .

      - name: Run vulture (dead code detection)
        run: uv run vulture

      - name: Run complexipy (cognitive complexity)
        run: uv run complexipy

      - name: Run pip-audit (dependency vulnerabilities)
        run: uv run pip-audit

      - name: Run ty type check
        # ty is used via uvx (ephemeral install) rather than a pinned dev
        # dependency. This means CI may pick up a newer ty version than local.
        # If this causes flaky failures, pin ty in the uvx invocation or add
        # it to [dependency-groups] dev and use uv run ty check instead.
        run: uvx ty check

  test-all:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:17
        env:
          POSTGRES_DB: promptgrimoire_test
          POSTGRES_PASSWORD: postgres
        options: >-
          --health-cmd "pg_isready -U postgres"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432
    steps:
      - uses: actions/checkout@v6.0.1

      - name: Install system dependencies
        run: |
          sudo apt-get update -y
          sudo apt-get install -y mecab libmecab-dev

      - name: Install uv
        uses: astral-sh/setup-uv@v7.2.0
        with:
          version: "latest"
          enable-cache: true
          cache-dependency-glob: "uv.lock"

      - name: Set up Python
        run: uv python install 3.14

      - name: Install dependencies
        run: uv sync --locked --all-groups

      - name: Run unit and integration tests
        env:
          DEV__TEST_DATABASE_URL: postgresql+asyncpg://postgres:postgres@localhost:5432/promptgrimoire_test
        run: uv run grimoire test all

  e2e:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:17
        env:
          POSTGRES_DB: promptgrimoire_test
          POSTGRES_PASSWORD: postgres
        options: >-
          --health-cmd "pg_isready -U postgres"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432
    steps:
      - uses: actions/checkout@v6.0.1

      - name: Install system dependencies
        run: |
          sudo apt-get update -y
          sudo apt-get install -y mecab libmecab-dev

      - name: Install uv
        uses: astral-sh/setup-uv@v7.2.0
        with:
          version: "latest"
          enable-cache: true
          cache-dependency-glob: "uv.lock"

      - name: Set up Python
        run: uv python install 3.14

      - name: Install dependencies
        run: uv sync --locked --all-groups

      - name: Install Playwright browsers
        run: uv run playwright install --with-deps chromium

      - name: Run E2E tests
        env:
          DEV__TEST_DATABASE_URL: postgresql+asyncpg://postgres:postgres@localhost:5432/promptgrimoire_test
        run: uv run grimoire e2e run
```

**Key design decisions in this file:**

- **No `needs:` between jobs** — all three run in parallel (AC1.4).
- **`DEV__TEST_DATABASE_URL`** is the only env var needed. The `grimoire` CLI reads this via pydantic-settings and handles everything else: sets `DATABASE__URL`, runs Alembic migrations, truncates tables, allocates ports, starts server subprocess (for E2E).
- **Mock auth is automatic** — the E2E server subprocess sets `DEV__AUTH_MOCK=true` internally. Unit/integration tests don't need auth at all.
- **`uv sync --locked --all-groups`** — `--locked` ensures CI uses exact lockfile versions (fails if lockfile is out of date, catching drift). `--all-groups` includes dev dependency group (where pip-audit, vulture, complexipy, ruff live). Note: `--all-extras` would install optional extras, not dependency groups — wrong flag for this project.
- **Playwright browsers are NOT cached** — download time equals cache restore time on Linux. Install fresh each run.
- **`uvx ty check`** uses `uvx` (not `uv run`) because ty is a standalone tool, not a project dependency. This means ty version is unpinned — see comment in workflow for mitigation if this causes issues.

**Step 2: Verify the YAML is valid**

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"
```

Expected: No error.

**Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "feat: add CI workflow with quality, test-all, and e2e jobs"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Delete the disabled CI workflow

**Verifies:** None (cleanup)

**Files:**
- Delete: `.github/workflows/ci.yml.disabled`

**Step 1: Remove the obsolete file**

```bash
git rm .github/workflows/ci.yml.disabled
```

**Step 2: Commit**

```bash
git commit -m "chore: remove obsolete ci.yml.disabled (replaced by ci.yml)"
```
<!-- END_TASK_2 -->
