# Epoch Analysis Implementation Plan — Phase 1: Schema and GitHub Fetcher

**Goal:** Add `github_events` table to the incident SQLite database and a `github` CLI subcommand that fetches merged PR metadata from the GitHub REST API.

**Architecture:** New table in schema.py, new parser in parsers/github.py following the beszel.py httpx pattern, new Typer subcommand in incident_db.py. Pure fetcher function returns `list[dict]`, CLI orchestrates DB insertion with SHA256 dedup.

**Tech Stack:** httpx (sync client), GitHub REST API v3, SQLite, Typer CLI

**Scope:** 6 phases from original design (phase 1 of 6)

**Codebase verified:** 2026-03-18

---

## Acceptance Criteria Coverage

This phase implements and tests:

### epoch-analysis.AC1: GitHub PR metadata ingestion
- **epoch-analysis.AC1.1 Success:** `github` command fetches merged PRs within the time window and stores them in `github_events` table
- **epoch-analysis.AC1.2 Success:** Token resolution falls back from `GITHUB_TOKEN` env to `gh auth token` subprocess
- **epoch-analysis.AC1.3 Success:** Re-ingesting the same window deduplicates (no duplicate rows)
- **epoch-analysis.AC1.4 Failure:** Missing token (no env, no gh) produces clear error message, not a stack trace

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Add `github_events` table to schema.py and update timeline view

**Verifies:** None (infrastructure — schema DDL)

**Files:**
- Modify: `scripts/incident/schema.py` (add table DDL after `beszel_metrics`, add index, update timeline view, add migration function)

**Implementation:**

Add the `github_events` table DDL to `SCHEMA_DDL` after the `beszel_metrics` table (after line 96). The table stores merged PR metadata:

```python
CREATE TABLE IF NOT EXISTS github_events (
    id          INTEGER PRIMARY KEY,
    source_id   INTEGER REFERENCES sources(id),
    ts_utc      TEXT NOT NULL,
    pr_number   INTEGER NOT NULL,
    title       TEXT NOT NULL,
    author      TEXT NOT NULL,
    commit_oid  TEXT NOT NULL,
    url         TEXT NOT NULL
);
```

Add an index after the existing indexes (after line 102):

```python
CREATE INDEX IF NOT EXISTS idx_github_events_ts ON github_events(ts_utc);
```

Update the timeline view to include `github_events` by adding a new UNION ALL leg before the `ORDER BY ts_utc` line:

```sql
UNION ALL
SELECT source_id, ts_utc, 'github' AS source,
       'pr' AS level_or_status,
       '#' || pr_number || ' ' || title AS message,
       commit_oid AS extra
FROM github_events
```

Add a migration function `_migrate_add_github_events(conn)` following the `_migrate_sources_provenance` pattern. This handles the case where the DB was created before this table existed:

```python
def _migrate_add_github_events(conn: sqlite3.Connection) -> None:
    """Add github_events table if missing (schema v2)."""
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if "github_events" not in tables:
        conn.executescript(
            """
            CREATE TABLE github_events (
                id          INTEGER PRIMARY KEY,
                source_id   INTEGER REFERENCES sources(id),
                ts_utc      TEXT NOT NULL,
                pr_number   INTEGER NOT NULL,
                title       TEXT NOT NULL,
                author      TEXT NOT NULL,
                commit_oid  TEXT NOT NULL,
                url         TEXT NOT NULL
            );
            CREATE INDEX idx_github_events_ts ON github_events(ts_utc);
            """
        )
```

Call the migration from `create_schema()` after `_migrate_sources_provenance(conn)`:

```python
_migrate_add_github_events(conn)
```

The timeline view is recreated via `DROP VIEW IF EXISTS timeline; CREATE VIEW timeline AS ...` on every `create_schema()` call, so the new UNION ALL leg is automatically included.

**Verification:**

```bash
cd /home/brian/people/Brian/PromptGrimoireTool/.worktrees/epoch-analysis
uv run python -c "
import sqlite3
from scripts.incident.schema import create_schema
conn = sqlite3.connect(':memory:')
create_schema(conn)
tables = [r[0] for r in conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()]
assert 'github_events' in tables, f'Missing github_events, got: {tables}'
# Check timeline view includes github
view_sql = conn.execute(\"SELECT sql FROM sqlite_master WHERE name='timeline'\").fetchone()[0]
assert 'github_events' in view_sql, 'Timeline view missing github_events'
print('Schema OK: github_events table and timeline view updated')
"
```

**Commit:** `feat: add github_events table and timeline view integration`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: GitHub PR fetcher in parsers/github.py

**Verifies:** epoch-analysis.AC1.1, epoch-analysis.AC1.2, epoch-analysis.AC1.4

**Files:**
- Create: `scripts/incident/parsers/github.py`
- Test: `tests/unit/test_github_fetcher.py` (unit)

**Implementation:**

Create `scripts/incident/parsers/github.py` following the beszel.py httpx pattern. The module exports a single function:

```python
def fetch_github_prs(
    repo: str,
    start_utc: str,
    end_utc: str,
    token: str,
) -> list[dict]:
```

**Token resolution** is a separate helper (called by the CLI, not the fetcher):

```python
def resolve_github_token(token_override: str | None = None) -> str:
```

Resolution order:
1. `token_override` parameter (from `--token` CLI flag)
2. `GITHUB_TOKEN` environment variable
3. `gh auth token` subprocess (`subprocess.run(["gh", "auth", "token"], capture_output=True, text=True)`)
4. Raise `RuntimeError("No GitHub token found. Set GITHUB_TOKEN or install gh CLI.")` — the CLI catches this and calls `typer.BadParameter`.

**Fetcher logic:**
- Uses `httpx.Client()` sync context manager (matching beszel.py pattern)
- Headers: `Authorization: Bearer {token}`, `Accept: application/vnd.github+json`, `X-GitHub-Api-Version: 2022-11-28`
- Endpoint: `https://api.github.com/repos/{repo}/pulls`
- Params: `state=closed`, `sort=updated`, `direction=desc`, `per_page=100`, `page={n}`
- Pagination: increment `page` until empty response
- Filter: only include PRs where `merged_at` is not null
- Time window filter: only include PRs where `merged_at` falls within `[start_utc, end_utc]`
- Stop pagination when ALL PRs on a page have `updated_at` before `start_utc` (since results are sorted by `updated_at` desc — this is the sort key, not `merged_at`). Use `merged_at` only for the inclusion filter (must be non-null and within window).
- Each PR becomes a dict: `{"ts_utc": normalise_utc(merged_at), "pr_number": number, "title": title, "author": user["login"], "commit_oid": merge_commit_sha, "url": html_url}`
- Error handling: `httpx.HTTPStatusError` for 401/403/404 with clear messages to stderr

**Testing:**

Tests must verify:
- epoch-analysis.AC1.1: Fetcher returns correct dicts for merged PRs in window (mock httpx responses)
- epoch-analysis.AC1.2: `resolve_github_token` tries env var, then gh subprocess, in order
- epoch-analysis.AC1.4: Missing token raises RuntimeError with descriptive message

Test approach: Mock httpx.Client responses and subprocess.run for gh auth token. Test the pure fetcher function and the token resolver independently.

**Verification:**

```bash
uv run pytest tests/unit/test_github_fetcher.py -v
```

**Commit:** `feat: add GitHub PR fetcher with token resolution`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_3 -->
### Task 3: `github` CLI subcommand in incident_db.py

**Verifies:** epoch-analysis.AC1.1, epoch-analysis.AC1.3

**Files:**
- Modify: `scripts/incident_db.py` (add `github` command)
- Test: `tests/unit/test_github_cli.py` (unit)

**Implementation:**

Add a new `@app.command()` function `github` to `scripts/incident_db.py`, following the `beszel` command pattern (lines 166-255).

Signature:

```python
@app.command()
def github(
    start: str = typer.Option(..., help="Window start (local time, YYYY-MM-DD HH:MM)"),
    end: str = typer.Option(..., help="Window end (local time, YYYY-MM-DD HH:MM)"),
    repo: str = typer.Option(
        "", help="GitHub repo (owner/repo). Auto-detects from git remote if empty."
    ),
    token: str = typer.Option("", help="GitHub token. Falls back to GITHUB_TOKEN env, then gh auth token."),
    force: bool = typer.Option(False, help="Re-fetch even if window was previously ingested (bypass dedup)."),
    timezone: str | None = typer.Option(None, help="IANA timezone override"),
    db: Path = typer.Option(Path("incident.db"), help="SQLite database path"),
) -> None:
```

**Logic (following beszel pattern):**

1. Open DB, call `create_schema(conn)` to ensure migration
2. Resolve timezone via `_resolve_timezone(conn, timezone)`
3. Convert start/end to UTC via `_aedt_to_utc(start, tz_name)` and `_aedt_to_utc(end, tz_name)`
4. Resolve token via `resolve_github_token(token or None)` — catch `RuntimeError`, convert to `typer.BadParameter`
5. Auto-detect repo if empty: `subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True)`, parse `owner/repo` from URL
6. Compute SHA256 for dedup: `hashlib.sha256(f"github:{repo}:{start_utc}:{end_utc}".encode()).hexdigest()`
7. Check dedup: if `sources.sha256` matches and `--force` is not set, print message and return. If `--force` is set, delete the existing source row and its `github_events` rows before re-fetching (known limitation: the dedup key encodes the time window, not the actual PR content — if new PRs merge after the initial fetch but within the same window, `--force` is needed to pick them up)
8. Insert `sources` row (format="github", filename=repo, sha256=sha, window_start_utc, window_end_utc)
9. Call `fetch_github_prs(repo, start_utc, end_utc, token)`
10. Insert each PR as a `github_events` row with the `source_id`
11. Commit and print summary (N PRs fetched)

**Repo auto-detection helper:**

```python
def _detect_github_repo() -> str:
    """Extract owner/repo from git remote origin URL."""
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise typer.BadParameter("Cannot detect repo: no git remote 'origin'. Use --repo.")
    url = result.stdout.strip()
    # Handle both HTTPS and SSH URLs
    # https://github.com/owner/repo.git -> owner/repo
    # git@github.com:owner/repo.git -> owner/repo
    import re
    match = re.search(r"github\.com[:/](.+?)(?:\.git)?$", url)
    if not match:
        raise typer.BadParameter(f"Cannot parse GitHub repo from remote URL: {url}")
    return match.group(1)
```

**Testing:**

Tests must verify:
- epoch-analysis.AC1.1: CLI orchestrates fetch and DB insertion correctly (mock fetcher, verify rows in SQLite)
- epoch-analysis.AC1.3: Re-ingesting same window skips (dedup on sha256)

Test approach: Use an in-memory SQLite database. Mock `fetch_github_prs` to return known data. Verify rows inserted, then verify second call skips.

**Verification:**

```bash
uv run pytest tests/unit/test_github_cli.py -v
```

**Commit:** `feat: add github CLI subcommand with dedup and auto-detect`

## UAT Steps

1. Run: `uv run scripts/incident_db.py github --start "2026-03-15 00:00" --end "2026-03-18 20:37" --db /tmp/test_github.db`
2. Verify: Command outputs "Fetched N PRs" (should be >0 for this active repo)
3. Run: `uv run scripts/incident_db.py sources --db /tmp/test_github.db`
4. Verify: Output shows a "github" format source row
5. Run the same github command again (same --start/--end)
6. Verify: Dedup message printed, no duplicate rows
7. Run: `uv run scripts/incident_db.py github --start "2026-03-15 00:00" --end "2026-03-18 20:37" --db /tmp/test_github.db` with `GITHUB_TOKEN` unset and `gh` not installed
8. Verify: Clear error message (not a stack trace)

## Complexity Check

```bash
uv run complexipy scripts/incident/schema.py scripts/incident/parsers/github.py scripts/incident_db.py
```
<!-- END_TASK_3 -->
