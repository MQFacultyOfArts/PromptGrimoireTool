# Epoch Analysis Implementation Plan — Phase 6: Report Generation and CLI

**Goal:** `incident_db.py review` CLI command that orchestrates all analysis functions from Phases 2-5 and produces a self-contained markdown report.

**Architecture:** `render_review_report()` in `analysis.py` assembles markdown from all analysis results. The `review` CLI subcommand in `incident_db.py` orchestrates: epoch extraction, enrichment, per-epoch queries, user metrics, trend analysis, and report rendering. Output to stdout or file.

**Tech Stack:** Typer CLI, Python string formatting for markdown, Rich for terminal summary

**Scope:** 6 phases from original design (phase 6 of 6)

**Codebase verified:** 2026-03-18

---

## Acceptance Criteria Coverage

This phase implements and tests:

### epoch-analysis.AC6: Report generation
- **epoch-analysis.AC6.1 Success:** `review` command produces markdown with all sections: source inventory, epoch timeline, per-epoch analysis, user activity, trends
- **epoch-analysis.AC6.2 Failure:** Missing `--counts-json` omits the static counts section gracefully (no error)

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: `render_review_report()` — markdown report assembly

**Verifies:** epoch-analysis.AC6.1, epoch-analysis.AC6.2

**Files:**
- Modify: `scripts/incident/analysis.py` (add function)
- Test: `tests/unit/test_report_render.py` (unit)

**Implementation:**

Add to `scripts/incident/analysis.py`:

```python
def render_review_report(
    sources: list[dict],
    epochs: list[dict],
    epoch_analyses: list[dict],
    summative_users: dict,
    trends: list[dict],
    static_counts: dict | None = None,
) -> str:
```

**Parameters:**
- `sources`: from `query_sources(conn)` — existing function in queries.py
- `epochs`: enriched epoch list from `extract_epochs` + `enrich_*`
- `epoch_analyses`: list of dicts, one per epoch, each containing results from all five per-epoch query functions plus user metrics
- `summative_users`: from `query_summative_users(conn)`
- `trends`: from `compute_trends(epochs)`
- `static_counts`: from `load_static_counts(path)` — None if not provided

**Markdown sections:**

```markdown
# Operational Review Report

**Generated:** {datetime}
**Database:** {db_path}
**Window:** {first_epoch_start} — {last_epoch_end}

## Source Inventory

| Source | Format | Events | Window |
|--------|--------|--------|--------|
{for each source}

## Static DB Counts (if static_counts is not None)

| Table | Count |
|-------|-------|
{for each key/value in static_counts}

## Epoch Timeline

| # | Commit | PR | Start | End | Duration | Events | Memory Peak | CPU |
|---|--------|----|-------|-----|----------|--------|-------------|-----|
{for each epoch, mark crash-bounces with ⚡}

## Per-Epoch Analysis

### Epoch {n}: {commit} ({pr_title or "no PR"})

**Duration:** {duration} | **Events:** {count} {⚡ CRASH-BOUNCE if applicable}

#### Errors
| Level | Event | Count | /hour |
{error rows, or "No errors in this epoch."}

#### HTTP Traffic (HAProxy)
| Status | Count |
{status code rows}
Total: {total} requests ({rpm}/min) | 5xx: {count_5xx} ({rate_5xx}/hr)
Response times: p50={p50}ms p95={p95}ms p99={p99}ms

#### System Resources (Beszel)
| Metric | Mean | Max |
| CPU % | {mean_cpu} | {max_cpu} |
| Memory % | {mean_mem} | {max_mem} |
| Load | {mean_load} | {max_load} |

#### PostgreSQL Errors
{pg error rows, or "No PG errors."}

#### Journal Anomalies (priority ≤ 3)
{journal anomaly rows, or "No journal anomalies."}

#### User Activity
| Metric | Count |
| Unique logins | {n} |
| Active users | {n} |
| Active workspaces | {n} |
| Workspace-interacting users | {n} |

{repeat for each epoch}

## User Activity Summary

| Metric | Total | {of N if static_counts} |
| Unique logins | {n} | |
| Active users | {n} | {of M total users} |
| Active workspaces | {n} | {of M total workspaces} |

## Trend Analysis

| Epoch | Error Rate | 5xx Rate | Memory Peak | Mean CPU | Active Users |
|-------|------------|----------|-------------|----------|--------------|
{for each epoch: value (Δ +/-N, +/-N%) — flag anomalies with ⚠️}
```

**Return:** Complete markdown string.

**Testing:**

Tests must verify:
- epoch-analysis.AC6.1: Given mock data for all sections, produces valid markdown with all expected headers
- epoch-analysis.AC6.2: When `static_counts` is None, the "Static DB Counts" section is omitted

Test approach: Create minimal mock data, call render function, verify output contains expected section headers and data formatting.

**Verification:**

```bash
uv run pytest tests/unit/test_report_render.py -v
```

**Commit:** `feat: add markdown report renderer for operational review`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: `review` CLI subcommand — orchestration

**Verifies:** epoch-analysis.AC6.1, epoch-analysis.AC6.2

**Files:**
- Modify: `scripts/incident_db.py` (add `review` command)
- Test: `tests/unit/test_review_cli.py` (unit)

**Implementation:**

Add a new `@app.command()` function `review` to `scripts/incident_db.py`:

```python
@app.command()
def review(
    db: Path = typer.Option(Path("incident.db"), help="SQLite database path"),
    counts_json: Path | None = typer.Option(None, help="JSON file with static DB counts"),
    output: Path | None = typer.Option(None, help="Output file (stdout if omitted)"),
) -> None:
```

**Orchestration logic:**

1. Open DB with `sqlite3.connect(db)`. Note: analysis functions in `analysis.py` should set `conn.row_factory = sqlite3.Row` internally as needed (following `extract_epochs` pattern from Phase 2). The CLI does not need to set row_factory globally — each query function manages its own.
2. `create_schema(conn)` to ensure migration
3. `sources = query_sources(conn)`
4. `epochs = extract_epochs(conn)`
5. If no epochs: print "No epochs found. Is the database populated with JSONL events?" and return
6. `enrich_epochs_journal(conn, epochs)`
7. `enrich_epochs_github(conn, epochs)`
8. For each epoch, run all five query functions + user metrics, collect into `epoch_analyses` list:
   ```python
   epoch_analyses = []
   for epoch in epochs:
       analysis = {
           "errors": query_epoch_errors(conn, epoch["start_utc"], epoch["end_utc"], epoch["duration_seconds"]),
           "haproxy": query_epoch_haproxy(conn, epoch["start_utc"], epoch["end_utc"], epoch["duration_seconds"]),
           "resources": query_epoch_resources(conn, epoch["start_utc"], epoch["end_utc"]),
           "pg": query_epoch_pg(conn, epoch["start_utc"], epoch["end_utc"]),
           "journal_anomalies": query_epoch_journal_anomalies(conn, epoch["start_utc"], epoch["end_utc"]),
           "users": query_epoch_users(conn, epoch["start_utc"], epoch["end_utc"]),
       }
       # Attach key metrics to epoch dict for trend computation
       # For crash-bounce epochs, set rates to None (not 0) so trend analysis skips them
       # rather than treating them as "zero errors" which would create false negative deltas
       if epoch["is_crash_bounce"]:
           epoch["error_rate"] = None
           epoch["rate_5xx"] = None
       else:
           epoch["error_rate"] = sum(e["per_hour"] or 0 for e in analysis["errors"])
           epoch["rate_5xx"] = analysis["haproxy"].get("rate_5xx")
       # memory_peak_bytes already set by enrich_epochs_journal() in step 6
       epoch["mean_cpu"] = analysis["resources"].get("mean_cpu")
       epoch["active_users"] = analysis["users"]["active_users"]
       epoch_analyses.append(analysis)
   ```
9. `summative_users = query_summative_users(conn)`
10. `trends = compute_trends(epochs)`
11. `static_counts = load_static_counts(counts_json)`
12. `report = render_review_report(sources, epochs, epoch_analyses, summative_users, trends, static_counts)`
13. Output: if `--output` provided, write to file; otherwise print to stdout
14. Print Rich summary to stderr: "Review report: {n} epochs, {n} with anomalies, written to {path or stdout}"

**Error handling:**
- Missing `--counts-json` file: catch `FileNotFoundError`, print warning, continue without static counts (AC6.2)
- Empty DB: early return with message

**Testing:**

Tests must verify:
- epoch-analysis.AC6.1: Full orchestration produces markdown (mock all analysis functions)
- epoch-analysis.AC6.2: Missing counts-json produces no error, report generated without static counts section

Test approach: Mock the analysis functions, verify orchestration calls them in correct order, verify output.

**Verification:**

```bash
uv run pytest tests/unit/test_review_cli.py -v
```

**Commit:** `feat: add review CLI subcommand for operational review reports`

## UAT Steps

1. Run full review against `incident.db` (after Phases 1-5 complete):
```bash
uv run scripts/incident_db.py review --db incident.db --output /tmp/review_report.md
```
2. Verify: Report written to `/tmp/review_report.md`
3. Open report in a markdown viewer and check:
   - Source Inventory table lists all 5+ sources
   - Epoch Timeline shows multiple epochs with commit hashes
   - Per-Epoch Analysis sections have error, HAProxy, resource, user data
   - Trend Analysis table shows deltas with anomaly flags
4. Run without --counts-json:
```bash
uv run scripts/incident_db.py review --db incident.db --output /tmp/review_no_counts.md
```
5. Verify: No error, "Static DB Counts" section absent from report

## Complexity Check

```bash
uv run complexipy scripts/incident/analysis.py scripts/incident_db.py
```
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->
