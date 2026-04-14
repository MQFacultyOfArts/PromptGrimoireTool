# Worktree Setup

## Database

The app auto-suffixes the database name on feature branches (e.g. `promptgrimoire_42_add_oauth`).
You must create the suffixed database and run migrations before tests or the app will work.

1. Determine the branch-suffixed database name. `_suffix_db_url` adds a leading `_`
   before the suffix, so the pattern is `promptgrimoire_<suffix>`:

```bash
uv run python3 -c "
from promptgrimoire.config import _current_branch, _branch_db_suffix
branch = _current_branch()
suffix = _branch_db_suffix(branch)
print(f'promptgrimoire_{suffix}')
print(f'promptgrimoire_test_{suffix}')
"
```

2. Create both databases (dev and test):

```bash
createdb promptgrimoire_<suffix>
createdb promptgrimoire_test_<suffix>
```

3. Run Alembic migrations against the dev database:

```bash
uv run alembic upgrade head
```

4. Seed development data (idempotent):

```bash
uv run grimoire seed run
```

5. Update `.env` if it was copied from the main checkout:

The `DATABASE__URL` and `DEV__TEST_DATABASE_URL` values do **not** need editing.
The branch suffix is applied automatically at runtime when `DEV__BRANCH_DB_SUFFIX=true` (default).

## Rehydrating production workspaces

To load an extracted workspace JSON (from `scripts/extract_workspace.py`) into the worktree database:

```bash
uv run scripts/rehydrate_workspace.py /tmp/workspace_<uuid>.json --owner instructor@uni.edu
```

The rehydrate script respects the branch-suffixed database automatically via `get_settings()`.

## Services

PostgreSQL is shared across all worktrees via the system socket (`/var/run/postgresql`).
Do not start a separate PostgreSQL instance.

## Verification

Run the fast test suite to confirm the worktree is healthy:

```bash
uv run grimoire test all
```
