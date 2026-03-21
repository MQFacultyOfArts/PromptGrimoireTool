# Epoch Analysis Design

**GitHub Issue:** None

## Summary

The epoch analysis tool automates a post-incident review methodology for the PromptGrimoire production server. When the server restarts — whether from a crash, OOM kill, or deliberate deploy — each restart creates a distinct period of continuous operation tied to a specific git commit. These periods are called "epochs." The tool identifies epoch boundaries automatically by detecting commit hash transitions in the structured application logs already stored in the incident SQLite database, then profiles each epoch independently: how many errors occurred, what the HTTP traffic looked like, what resources the server consumed, and how many users were active. Across all epochs it computes trend deltas to surface deteriorating behaviour before it becomes a crisis.

The tool extends the existing `incident_db.py` CLI with two new subcommands. The `github` subcommand fetches merged pull request metadata from the GitHub REST API and caches it in the incident database, allowing each epoch to be annotated with the PR that introduced its code. The `review` subcommand orchestrates the full analysis pipeline — epoch extraction, enrichment from journal shutdown messages and GitHub PR data, five categories of per-epoch SQL aggregate queries, user activity metrics, and cross-epoch trend comparison — and emits a self-contained markdown report. The entire implementation is SQL-first and follows the codebase's existing functional core / imperative shell split: pure query functions in a new `analysis.py` module, CLI orchestration in `incident_db.py`.

## Definition of Done

Add an `analysis.py` module to `scripts/incident/` with pure query functions, plus new CLI subcommands on `incident_db.py`, that automate the 3-day operational review methodology: restart extraction, epoch segmentation (by commit hash boundaries), per-epoch error/HAProxy/resource profiling, and deploy correlation via GitHub PR metadata.

- `incident_db.py github --start ... --end ...` fetches merged PR metadata via httpx (auth token from `gh auth token` or `GITHUB_TOKEN` env), caches in SQLite `github_events` table
- `incident_db.py review --db incident.db` produces a markdown report covering: restart timeline with memory/CPU peaks, epoch-segmented error rates and HAProxy profiles, PR-to-restart correlation, resource trend analysis
- Works against the existing `incident.db` (3.6M events, 5 sources)
- Usable both for periodic health checks and mid-incident "what broke when" queries
- Follows existing patterns: pure query functions, functional core / imperative shell, Rich output + markdown

**Out of scope:** Changes to the telemetry collector, changes to existing parsers, live triage alerting, Beszel dashboard integration.

## Acceptance Criteria

### epoch-analysis.AC1: GitHub PR metadata ingestion
- **epoch-analysis.AC1.1 Success:** `github` command fetches merged PRs within the time window and stores them in `github_events` table
- **epoch-analysis.AC1.2 Success:** Token resolution falls back from `GITHUB_TOKEN` env to `gh auth token` subprocess
- **epoch-analysis.AC1.3 Success:** Re-ingesting the same window deduplicates (no duplicate rows)
- **epoch-analysis.AC1.4 Failure:** Missing token (no env, no gh) produces clear error message, not a stack trace

### epoch-analysis.AC2: Epoch extraction and enrichment
- **epoch-analysis.AC2.1 Success:** Commit hash transitions in JSONL correctly identify epoch boundaries with start/end timestamps
- **epoch-analysis.AC2.2 Success:** Journal `Consumed` messages are matched to epoch boundaries, providing memory peak and CPU consumed
- **epoch-analysis.AC2.3 Success:** GitHub PR metadata is attached to epochs by matching commit hash prefixes
- **epoch-analysis.AC2.4 Edge:** Epochs with no matching PR (direct pushes, pre-GitHub-fetch) show "no PR" rather than failing

### epoch-analysis.AC3: Per-epoch analysis queries
- **epoch-analysis.AC3.1 Success:** Error counts grouped by level and event type, normalised to errors/hour
- **epoch-analysis.AC3.2 Success:** HAProxy status code distribution with p50/p95/p99 response times
- **epoch-analysis.AC3.3 Success:** Beszel resource stats (mean/max CPU, memory, load) per epoch
- **epoch-analysis.AC3.4 Edge:** Epochs shorter than 5 minutes flagged as crash-bounces, not analysed for rates

### epoch-analysis.AC4: User activity metrics
- **epoch-analysis.AC4.1 Success:** Per-epoch unique logins, active users, active workspaces, workspace-interacting users
- **epoch-analysis.AC4.2 Success:** Summative totals across full window (union, not sum of per-epoch)
- **epoch-analysis.AC4.3 Success:** Static DB counts from `--counts-json` displayed as "N of M total" context

### epoch-analysis.AC5: Trend analysis
- **epoch-analysis.AC5.1 Success:** Each epoch shows delta and percentage change vs previous for error rate, 5xx rate, memory peak, mean CPU, active users
- **epoch-analysis.AC5.2 Success:** Anomalous spikes (>100% increase) flagged in the report

### epoch-analysis.AC6: Report generation
- **epoch-analysis.AC6.1 Success:** `review` command produces markdown with all sections: source inventory, epoch timeline, per-epoch analysis, user activity, trends
- **epoch-analysis.AC6.2 Failure:** Missing `--counts-json` omits the static counts section gracefully (no error)

## Glossary

- **epoch**: A continuous period of server operation bounded by a restart. Begins at first JSONL event after startup, ends at last event before the next restart. Each epoch corresponds to a single deployed git commit.
- **epoch boundary**: The timestamp in JSONL where the `commit` field changes, indicating a restart between deployments.
- **crash-bounce**: An epoch shorter than five minutes — the server started but crashed or was restarted almost immediately. Flagged separately and excluded from rate normalisation.
- **JSONL events**: Structured JSON log lines from the application, one object per line, stored in `jsonl_events` table.
- **HAProxy**: Reverse proxy in front of the application. Access logs provide HTTP status codes and response times per epoch.
- **Beszel**: Lightweight server monitoring agent. Samples CPU, memory, and load at regular intervals.
- **journal**: Linux systemd journal, capturing process-level events including `Consumed` shutdown messages.
- **`Consumed` message**: systemd journal entry at service stop, reporting CPU consumed and peak memory. Used to enrich epoch boundaries.
- **`LAG` window function**: SQL analytic function comparing a row's value to the preceding row's. Detects commit hash transitions without full table scan.
- **functional core / imperative shell**: Pattern separating pure computation (core) from I/O and orchestration (shell). Query functions in `analysis.py` are the core; `incident_db.py` subcommands are the shell.
- **p50/p95/p99**: Response time percentiles. p50 = median, p95 = 95th percentile, p99 = 99th. Approximated in SQLite via offset subqueries.
- **`merge_commit_sha`**: SHA-1 hash GitHub assigns to a PR's merge commit. Correlates a PR with an epoch's running commit.
- **Rich**: Python library for formatted terminal output (tables, colour).
- **Typer**: Python CLI framework. Subcommands defined via `@app.command()`.
- **httpx**: Async-capable Python HTTP client. Used for GitHub REST API calls.
- **`gh auth token`**: GitHub CLI command outputting the authenticated user's access token. Fallback when `GITHUB_TOKEN` env is not set.
- **rate normalisation**: Expressing counts as per-hour rates so epochs of different durations can be compared fairly.
- **trend delta**: Difference in a metric between consecutive epochs, as absolute value and percentage change.

## Architecture

SQL-first analysis engine. Epoch boundaries are extracted from `jsonl_events` using SQL window functions (`LAG` on the `commit` field in `extra_json`). Each epoch represents a period where the server ran a single git commit. Per-epoch statistics are computed by SQL aggregate queries windowed on the epoch's UTC time bounds.

**Data flow:**

1. `extract_epochs(conn)` — SQL query detects commit hash transitions in JSONL data, returns epoch list with start/end timestamps and commit hash
2. `enrich_epochs_journal(conn, epochs)` — joins each epoch boundary against journal `Consumed` messages to attach memory peak and CPU consumed
3. `enrich_epochs_github(epochs, repo, token)` — httpx call to GitHub REST API, matches `merge_commit_sha` prefix against epoch commit hashes, attaches PR number and title
4. Per-epoch analysis queries — five SQL aggregate functions, each taking `(conn, start_utc, end_utc)`:
   - `query_epoch_errors()` — JSONL events by level and event type, normalised to errors/hour
   - `query_epoch_haproxy()` — HAProxy events by status code, response time percentiles, requests/minute
   - `query_epoch_resources()` — Beszel metrics: mean/max CPU%, memory%, load
   - `query_epoch_pg()` — PG events by level and error type
   - `query_epoch_journal_anomalies()` — Journal events with priority <= 3 (ERROR+)
5. `query_epoch_users()` — JSONL events: unique logins, active users, active workspaces per epoch
6. `render_review_report(sources, epochs, epoch_analyses, summative_users, trends, static_counts)` — assembles all results into markdown

**GitHub PR correlation:** The `github` subcommand fetches merged PRs via `GET /repos/{owner}/{repo}/pulls?state=closed` with httpx. Auth token sourced from `GITHUB_TOKEN` env var, falling back to `gh auth token` subprocess. Results cached in a `github_events` table in the incident SQLite DB. The `review` command reads from this cached table.

**Static DB counts:** The `review` command accepts `--counts-json` with a JSON file containing production PostgreSQL counts (users, workspaces, courses, etc.). These are displayed in the report header as context for the activity metrics.

## Existing Patterns

Investigation confirmed the following patterns in `scripts/incident/`:

- **Pure query functions** (`queries.py`): `query_sources(conn)`, `query_timeline(conn, start, end)`, `query_breakdown(conn)` — all take `sqlite3.Connection`, return `list[dict]`. New analysis functions follow this pattern.
- **Functional core / imperative shell**: Parsers are pure functions returning `list[dict]`, DB orchestration in `ingest.py`. Analysis follows the same split — pure SQL query functions in `analysis.py`, CLI orchestration in `incident_db.py`.
- **Typer CLI** (`incident_db.py`): Each subcommand is `@app.command()`. Options via `typer.Option()`. Output dispatch via `_output()` helper.
- **Rich tables** for terminal output, with `--json` and `--csv` flags for machine-readable output.
- **Schema migrations** (`schema.py`): Lightweight `ALTER TABLE` migrations in `_migrate_*()` functions, called from `create_schema()`. New `github_events` table follows this pattern.
- **Timestamp canonicalisation**: All `ts_utc` values use `normalise_utc()` for microsecond-precision UTC format. GitHub API timestamps will be normalised the same way.
- **Beszel fetcher pattern** (`parsers/beszel.py`): httpx call to external API, results inserted into a dedicated table. GitHub fetcher follows this exact pattern.

No new patterns introduced. No divergence from existing code.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Schema and GitHub Fetcher
**Goal:** Add `github_events` table and `incident_db.py github` subcommand

**Components:**
- Schema addition in `scripts/incident/schema.py` — `github_events` table (ts_utc, pr_number, commit_oid, title, author) + index + migration function
- Timeline view update — UNION ALL `github_events` into existing view
- GitHub fetcher in `scripts/incident/parsers/github.py` — httpx call to REST API, pagination, token resolution (`GITHUB_TOKEN` env → `gh auth token` fallback), `normalise_utc()` on `merged_at`
- CLI subcommand `github` in `scripts/incident_db.py` — `--start`, `--end`, `--repo` (auto-detect from git remote), `--token` (env/gh fallback), `--db`

**Dependencies:** None (first phase)

**Done when:** `incident_db.py github --start "2026-03-15 00:00" --end "2026-03-18 20:37" --db test.db` fetches PRs, stores them, and `sources` shows the new source. Covers epoch-analysis.AC1.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Epoch Extraction
**Goal:** Extract epoch boundaries from JSONL commit hash transitions

**Components:**
- `extract_epochs(conn)` in `scripts/incident/analysis.py` — SQL with `LAG` window function on `json_extract(extra_json, '$.commit')`, returns list of epoch dicts with start/end UTC, commit hash, event count
- `enrich_epochs_journal(conn, epochs)` in `scripts/incident/analysis.py` — matches epoch end boundaries against journal `Consumed` messages (regex parse for memory peak, CPU consumed, swap)
- `enrich_epochs_github(conn, epochs)` in `scripts/incident/analysis.py` — joins epoch commit hashes against `github_events` table, attaches PR number and title

**Dependencies:** Phase 1 (github_events table)

**Done when:** Given the existing `incident.db`, `extract_epochs()` returns 12 epochs matching the known commit hashes, enriched with journal metadata and GitHub PR titles. Covers epoch-analysis.AC2.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Per-Epoch Analysis Queries
**Goal:** Five SQL aggregate queries windowed by epoch boundaries

**Components:**
- `query_epoch_errors(conn, start_utc, end_utc)` in `analysis.py` — JSONL events grouped by level and event, with error/hour normalisation
- `query_epoch_haproxy(conn, start_utc, end_utc)` in `analysis.py` — HAProxy events by status code, total requests, 5xx count/rate, response time p50/p95/p99
- `query_epoch_resources(conn, start_utc, end_utc)` in `analysis.py` — Beszel mean/max for CPU%, memory%, load_1
- `query_epoch_pg(conn, start_utc, end_utc)` in `analysis.py` — PG events by level and error_type
- `query_epoch_journal_anomalies(conn, start_utc, end_utc)` in `analysis.py` — journal events with priority <= 3

**Dependencies:** Phase 2 (epoch list provides time bounds)

**Done when:** Each query returns correct aggregates for known epochs in `incident.db`. Epochs shorter than 5 minutes flagged as crash-bounces. Covers epoch-analysis.AC3.
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: User Activity Metrics
**Goal:** Per-epoch and summative user/workspace activity from JSONL

**Components:**
- `query_epoch_users(conn, start_utc, end_utc)` in `analysis.py` — unique logins (events matching `Login successful%`), active users (distinct user_id), active workspaces (distinct workspace_id), users who touched workspaces (distinct user_id where workspace_id also set)
- `query_summative_users(conn)` in `analysis.py` — same metrics across full window
- Static counts parser — accepts `--counts-json` path, reads JSON dict of production DB counts

**Dependencies:** Phase 2 (epoch boundaries)

**Done when:** Per-epoch user counts match manual SQL verification. Summative totals are correct union across epochs. Static counts rendered when JSON provided. Covers epoch-analysis.AC4.
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: Trend Analysis
**Goal:** Cross-epoch comparison for growing-problem detection

**Components:**
- `compute_trends(epochs)` in `analysis.py` — for each epoch, compute delta and percentage change vs previous epoch for: error rate, 5xx rate, memory peak, mean CPU, active users. Flag anomalous spikes (>100% increase or absolute thresholds)
- Short-epoch detection — epochs < 5 minutes flagged as crash-bounces, excluded from trend analysis but noted in report

**Dependencies:** Phase 3 (per-epoch stats), Phase 4 (user metrics)

**Done when:** Trend data correctly identifies the known Mar 15 crash loop and the pool_size=80 config change epoch. Covers epoch-analysis.AC5.
<!-- END_PHASE_5 -->

<!-- START_PHASE_6 -->
### Phase 6: Report Generation and CLI
**Goal:** `incident_db.py review` command producing markdown report

**Components:**
- `render_review_report(epochs, trends, summative_users, static_counts)` in `analysis.py` — assembles markdown report with sections: Source Inventory, Epoch Timeline, Per-Epoch Analysis, User Activity, Trends
- CLI subcommand `review` in `scripts/incident_db.py` — orchestrates all analysis functions, accepts `--db`, `--counts-json`, `--output` (file or stdout)
- Source inventory section auto-generated from `query_sources(conn)`

**Dependencies:** All previous phases

**Done when:** `incident_db.py review --db incident.db --counts-json counts.json --output report.md` produces a complete markdown report. Report renders correctly in a markdown viewer. Covers epoch-analysis.AC6.
<!-- END_PHASE_6 -->

## Additional Considerations

**Epoch gaps:** If the server was down between epochs (no JSONL events), the gap appears as missing time between one epoch's last event and the next epoch's first event. The report notes these gaps but does not create synthetic "down" epochs.

**HAProxy percentiles:** SQLite lacks a native `PERCENTILE` function. Response time percentiles are approximated via `ORDER BY ta_ms LIMIT 1 OFFSET (count * 0.95)` subquery pattern.

**Commit hash matching:** The app logs short hashes (7+ chars via `git rev-parse --short HEAD`); GitHub provides full 40-char SHAs. Epoch-to-PR correlation uses prefix matching (`merge_commit_sha` starts with epoch commit hash). False positive risk is negligible at this repo size. Direct pushes and lagged deploys produce "no PR" (AC2.4), not errors.

**`--counts-json` schema:** Expected format is a JSON object with string keys matching table names and integer values. Example: `{"users": 1936, "workspaces": 1151, "courses": 11, ...}`. Generated by running a psql query on the production server. Staleness is the operator's responsibility — for mid-incident triage this flag is typically omitted; for periodic reviews it should be generated at the same time as telemetry collection.

**Rate limiting:** GitHub REST API allows 5000 requests/hour with auth. A single `review` run fetches at most a few pages of PRs. No rate limiting concern for this use case.
