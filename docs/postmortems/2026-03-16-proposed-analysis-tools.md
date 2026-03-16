# Proposed Incident Analysis Tools

*Derived from the 2026-03-16 afternoon analysis. These scripts generalise the ad-hoc commands used during investigation into reusable tools for future incidents.*

## Rationale

During the 2026-03-16 analysis, we repeatedly ran similar `jq`/`grep`/`awk` pipelines with minor variations. Several errors in the original analysis (wrong time window, missed PG errors due to UTC offset, inflated counts from unfiltered JSONL) would have been prevented by standardised tooling that enforces correct filtering.

## Proposed Scripts

### 1. `scripts/incident_jsonl.py` — JSONL Log Analyser

**Purpose:** Parse structlog JSONL and produce error/warning breakdowns filtered to a specific time window.

**Input:** JSONL file path, start time (AEDT), end time (AEDT).

**Output:**
- Total entries by log level
- Error events grouped by `event` field, sorted by count
- Warning events grouped by `event` field, sorted by count
- INVALIDATE events summarised (count, peak `checked_out`, peak `overflow`, distinct pool configs detected)
- DB rollback events with traceback summary (if `exc_info` present)

**Why this prevents past mistakes:**
- Enforces AEDT→UTC conversion (the main source of errors in the original analysis)
- Always filters to the specified window (prevents 28-hour JSONL contamination)
- Detects mixed pool configurations (`size=5` vs `size=10`) and flags them
- Outputs the filter parameters used, so the methodology is self-documenting

**Key design decisions:**
- Python, not shell — `jq` pipelines are fragile and hard to compose
- Accepts AEDT times (what humans use) and converts internally to UTC (what the JSONL stores)
- Should use `typer` CLI consistent with the project's `grimoire` CLI pattern
- Pure functional core: parsing and aggregation are testable without file I/O

### 2. `scripts/incident_haproxy.py` — HAProxy Log Analyser

**Purpose:** Parse HAProxy access logs and produce status code breakdown, 5xx timeline, and request latency percentiles.

**Input:** HAProxy log file path, optional time window (AEDT).

**Output:**
- Total requests by HTTP status code
- 5xx errors grouped by minute with request paths
- Response time percentiles (p50, p95, p99) per status code
- Concurrent connection count over time (from `ac/fc/bc/sc/rc` fields)
- WebSocket upgrade count (101 responses)

**Why this prevents past mistakes:**
- Counts ALL status codes (the original analysis missed 500, 501, 502, 505, 506, 508)
- Extracts response time from the HAProxy log format fields (the original analysis only noted this for 504s)
- HAProxy timestamps are AEDT (local), so no timezone conversion needed — but the script should note this

**Key design decisions:**
- Parse the custom log format defined in `/etc/haproxy/haproxy.cfg`
- The log format is: `%ci:%cp [%tr] %ft %b/%s %TR/%Tw/%Tc/%Tr/%Ta %ST %B %CC %CS %tsc %ac/%fc/%bc/%sc/%rc %sq/%bq %hr %hs %{+Q}r`
- Regex parsing, not split — the format has variable-width fields

### 3. `scripts/incident_pglog.py` — PostgreSQL Log Analyser

**Purpose:** Parse PostgreSQL log and produce error/fatal summary filtered to a time window.

**Input:** PG log file path, start time (AEDT), end time (AEDT).

**Output:**
- ERROR and FATAL entries grouped by message pattern (constraint name, error type)
- Timeline of errors by minute
- Correlation hints: PG backend PIDs that appear in multiple errors
- DETAIL and STATEMENT lines associated with each error

**Why this prevents past mistakes:**
- Enforces AEDT→UTC conversion (PG logs are UTC, the original analysis missed afternoon errors because of this)
- Groups multi-line PG entries (ERROR + DETAIL + STATEMENT) into single logical events
- Flags FATAL entries separately (connection losses are operationally different from constraint violations)

### 4. `scripts/incident_summary.py` — Combined Incident Report Generator

**Purpose:** Run all three analysers on a set of log files and produce a combined markdown summary.

**Input:** Directory containing log files (or individual file paths), time window (AEDT).

**Output:** Markdown file with:
- Data source inventory (files, line counts, time coverage)
- Methodology section (commands/filters used, automatically generated)
- Error breakdown table (merged across all sources)
- Timeline (merged events from all sources on a single timeline)
- Cross-correlation notes (e.g., PG FATALs near INVALIDATE spikes)

**Why this helps:**
- Self-documenting: the methodology section is generated from the actual analysis parameters
- Cross-source correlation is where the original analysis was weakest (PG FATALs at 15:50/15:52/16:10 correlating with INVALIDATE churn was missed entirely)
- Produces a draft that can be reviewed and annotated, not a final report

## What These Tools Do NOT Do

- **They do not replace human judgment.** They produce counts and timelines. Interpretation, confidence levels, and causal analysis remain human responsibilities.
- **They do not access the production server.** They operate on local copies of log files. Log collection remains a manual step per the incident playbook.
- **They do not correlate with Beszel metrics.** Beszel does not have an export API we currently use. If we add Prometheus/Grafana, this could change.
- **They do not handle the Discord webhook log.** Discord delivery data is not available in machine-parseable form.

## Implementation Notes

- All scripts should live in `scripts/` alongside `extract_workspace.py`
- Use `typer` for CLI, consistent with the `grimoire` CLI
- Pure functional cores (parse → aggregate → format) with thin I/O shells
- Unit-testable against fixture log snippets
- No production dependencies — these are developer/operator tools

## Open Questions

1. Should these be subcommands of `grimoire` (e.g., `uv run grimoire incident analyse`) or standalone scripts?
2. Should the JSONL analyser also handle the journal format (structured text with `[level]` prefix), or should we always use the JSONL?
3. Do we want a `grimoire incident collect` command that SSHes to the server and pulls logs? This would standardise the collection step but adds SSH key management complexity.
