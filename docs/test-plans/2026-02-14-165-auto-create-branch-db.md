# Human Test Plan: Auto-create Branch Databases (#165)

## Prerequisites

- PostgreSQL running locally with superuser or createdb privileges
- `.env` configured with `DATABASE__URL` pointing to a PostgreSQL instance
- `DEV__TEST_DATABASE_URL` configured for test runner
- Dependencies installed: `uv sync`
- All automated tests passing: `uv run pytest tests/unit/test_db_schema.py tests/unit/test_cli_header.py tests/unit/test_main_startup.py -v` (22 tests, all green)

## Phase 1: App Startup on Main Branch (AC3.2 negative case)

| Step | Action | Expected |
|------|--------|----------|
| 1 | Checkout the `main` branch: `git checkout main` | Clean checkout |
| 2 | Run `uv run python -m promptgrimoire` | App starts normally |
| 3 | Observe startup output in the terminal | Output shows `PromptGrimoire v...` and `Starting application on ...` but does NOT contain any line starting with `Branch:` or containing `Database:` |
| 4 | Stop the app (Ctrl+C) | App stops cleanly |

## Phase 2: App Startup on New Feature Branch (AC3.1, AC3.2)

| Step | Action | Expected |
|------|--------|----------|
| 1 | Checkout the feature branch: `git checkout 165-auto-create-branch-db` | On feature branch |
| 2 | If the branch-specific DB exists, drop it: `dropdb promptgrimoire_165_auto_create_branch_db` (adjust name to match your `DATABASE__URL` pattern) | Database dropped (or did not exist) |
| 3 | Run `uv run python -m promptgrimoire` | App starts |
| 4 | Observe startup output | Output contains `"Created database — seeding development data..."` followed by seed-data output |
| 5 | Observe startup output | Output contains a line like `Branch: 165-auto-create-branch-db | Database: promptgrimoire_165_auto_create_branch_db` |
| 6 | Verify the database exists: `psql -l | grep promptgrimoire_165` | The branch-specific database name appears in the listing |
| 7 | Stop the app (Ctrl+C) | App stops cleanly |

## Phase 3: App Startup on Existing Feature Branch (AC3.1 idempotent)

| Step | Action | Expected |
|------|--------|----------|
| 1 | Remain on the `165-auto-create-branch-db` branch (database exists from Phase 2) | On feature branch, DB exists |
| 2 | Run `uv run python -m promptgrimoire` | App starts |
| 3 | Observe startup output | Output does NOT contain `"Created database"` or seed-data output |
| 4 | Observe startup output | Output still contains `Branch: 165-auto-create-branch-db | Database: ...` (branch info always shown on feature branches) |
| 5 | Stop the app (Ctrl+C) | App stops cleanly |

## Phase 4: Test Runner Header (AC2.1)

| Step | Action | Expected |
|------|--------|----------|
| 1 | Stay on the `165-auto-create-branch-db` branch | On feature branch |
| 2 | Run `uv run test-debug` | Test runner starts with a Rich panel at the top |
| 3 | Observe the Rich panel header in the terminal | Panel contains `Branch: 165-auto-create-branch-db` on its own line |
| 4 | Observe the Rich panel header | Panel contains `Test DB: <database_name>` where `<database_name>` matches the database path segment from `DEV__TEST_DATABASE_URL` |
| 5 | Let tests complete or cancel (Ctrl+C) | Panel was visible before test output began |

## Traceability

| Acceptance Criterion | Automated Tests | Manual Steps |
|----------------------|-----------------|--------------|
| AC1.1: `ensure_database_exists()` return value | `test_db_schema.py` (5 tests) | Phase 2 step 6 |
| AC2.1: Test header shows branch + DB | `test_cli_header.py` (11 tests) | Phase 4 steps 3-4 |
| AC3.1: Auto-create + migrate + seed | `test_main_startup.py` (4 tests) | Phase 2 steps 3-6, Phase 3 steps 2-4 |
| AC3.2: Branch info for feature branches | `test_main_startup.py` (2 tests) | Phase 1 step 3, Phase 2 step 5 |
