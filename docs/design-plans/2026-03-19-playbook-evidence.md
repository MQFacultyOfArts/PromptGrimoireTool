# Playbook Evidence Alignment Design

**GitHub Issue:** None

## Summary

Seven enhancements to the `incident_db.py review` report that close the gap between its current output and what the incident analysis playbook (`docs/postmortems/incident-analysis-playbook.md`) requires for post-incident review. The core additions are: error landscape diff (appeared/resolved error types per epoch using normalised event classes), NOSRV restart-503 visibility, pool configuration detection from INVALIDATE events, restart gap duration in the epoch timeline, and a self-documenting methodology section. All changes are to `scripts/incident/analysis.py` (query functions and renderer) and `scripts/incident_db.py` (review orchestrator). No new tables, no parser changes, no external dependencies.

## Definition of Done

The `incident_db.py review` report produces all evidence needed by the incident analysis playbook (`docs/postmortems/incident-analysis-playbook.md`):

1. Each epoch's per-epoch section shows NOSRV count (restart 503s) separately from application 5xx
2. Each epoch shows **appeared** error types (present now, absent in all prior epochs) and **resolved** error types (present in prior epochs, absent now) — with event strings normalised to collapse runtime-varying tokens (hex addresses, UUIDs, task names, PIDs) into stable classes
3. Pool configuration (pool_size, max_overflow) detected from INVALIDATE event fields if present, reported per-epoch
4. Epoch timeline shows restart gap duration (downtime between epochs)
5. Per-epoch HAProxy section shows NOSRV clustering (when during the epoch the restart 503s occurred)
6. Report includes a methodology section explaining metrics definitions, normalisation rationale, restart classification taxonomy, and references to SRE practice
7. All tables generated via `_md_table()` helper (already done by previous refactor)

Out of scope: changes to the telemetry collector, changes to existing parsers, live alerting, Beszel dashboard integration.

## Acceptance Criteria

### playbook-evidence.AC1: NOSRV visibility
- **playbook-evidence.AC1.1 Success:** Per-epoch HAProxy section displays `count_nosrv` (restart 503s with `server='<NOSRV>'`) separately from application 5xx count
- **playbook-evidence.AC1.2 Success:** NOSRV clustering shows count in first 60 seconds vs rest of epoch (e.g. "72 of 72 in first 60s")
- **playbook-evidence.AC1.3 Edge:** Epoch with zero NOSRV events omits the NOSRV line entirely

### playbook-evidence.AC2: Error landscape diff
- **playbook-evidence.AC2.1 Success:** `normalise_event(event_str)` collapses hex addresses (`0x[0-9a-f]+` → `<ADDR>`), UUIDs → `<UUID>`, `Task-\d+` → `Task-<N>`, and INVALIDATE pool state counts to produce stable class keys
- **playbook-evidence.AC2.2 Success:** Per-epoch section shows "Appeared" error types (present now, absent in all prior epochs) and "Resolved" error types (present in prior epochs, absent now)
- **playbook-evidence.AC2.3 Success:** First epoch shows all its error types as "appeared" (no prior to compare against)
- **playbook-evidence.AC2.4 Edge:** Epoch with no errors shows "No errors" for both appeared and resolved

### playbook-evidence.AC3: Pool configuration
- **playbook-evidence.AC3.1 Success:** `detect_pool_config(conn, start_utc, end_utc)` extracts `pool_size` and `max_overflow` from INVALIDATE or QueuePool event strings within the epoch window
- **playbook-evidence.AC3.2 Success:** Per-epoch section shows pool config if detected (e.g. "Pool: size=10, overflow=20")
- **playbook-evidence.AC3.3 Edge:** Epoch with no INVALIDATE/QueuePool events shows "Pool: not observed"
- **playbook-evidence.AC3.4 Edge:** If pool_size changes between consecutive epochs, the trend table flags the change

### playbook-evidence.AC4: Restart gap duration
- **playbook-evidence.AC4.1 Success:** Epoch timeline table includes a "Gap" column showing downtime duration between previous epoch's end and current epoch's start
- **playbook-evidence.AC4.2 Success:** First epoch shows "—" for gap (no predecessor)
- **playbook-evidence.AC4.3 Edge:** Gap of 0 seconds (immediate restart) displays as "0s"

### playbook-evidence.AC5: Methodology section
- **playbook-evidence.AC5.1 Success:** Report header includes methodology section explaining: epoch definition, restart classification taxonomy, request-normalised ratios, NOSRV exclusion rationale, error landscape diff semantics, anomaly threshold definitions
- **playbook-evidence.AC5.2 Success:** Methodology cites Google SRE Workbook ch. 2 (SLOs and Error Budgets) and the project's incident analysis playbook

## Glossary

- **NOSRV**: HAProxy log entry where `server='<NOSRV>'` — indicates HAProxy had no backend available (the application was restarting). These are infrastructure transients excluded from 5xx ratio calculations.
- **error class**: The normalised form of a JSONL `event` string after replacing runtime-varying tokens (memory addresses, UUIDs, task names) with placeholders. Two events are "the same class" if they normalise to the same string.
- **appeared**: An error class present in the current epoch that was not present in any prior epoch within the review window.
- **resolved**: An error class present in one or more prior epochs that is absent from the current epoch.
- **INVALIDATE**: SQLAlchemy connection pool event indicating a connection was invalidated. The event string includes `size=N` (pool_size) and `overflow=N/M` (current overflow / max_overflow), providing pool configuration visibility.
- **restart gap**: The time between the previous epoch's last event and the current epoch's first event. Represents downtime experienced by users during a restart.
- **error landscape**: The set of distinct normalised error classes observed in an epoch. The diff between consecutive landscapes reveals what changed.

## Architecture

All changes are to existing files following the functional core / imperative shell pattern:

- **Pure functions** in `analysis.py`: `normalise_event()`, `compute_error_landscape()`, `detect_pool_config()`, NOSRV clustering query
- **Renderer updates** in `analysis.py`: display NOSRV, appeared/resolved, pool config, gaps, methodology
- **Orchestration** in `incident_db.py`: wire new functions into the `review` command

### Event normalisation

`normalise_event(event: str) -> str` applies regex replacements in order:
1. `0x[0-9a-f]+` → `<ADDR>` (memory addresses)
2. UUID pattern (`[0-9a-f]{8}-[0-9a-f]{4}-...`) → `<UUID>`
3. `Task-\d+` → `Task-<N>` (asyncio task names)
4. INVALIDATE: strip `checked_in=\d+` `checked_out=\d+` `overflow=\d+/\d+`, keep `size=\d+`

The normalised string is the class key for landscape diffing.

### Error landscape computation

`compute_error_landscape(conn, epochs) -> list[dict]` iterates epochs in order, maintaining a cumulative set of all classes seen so far. For each epoch:
1. Query distinct normalised error classes in `[start_utc, end_utc]`
2. `appeared = current_classes - all_prior_classes`
3. `resolved = all_prior_classes - current_classes`
4. Add `current_classes` to `all_prior_classes`
5. Return list of `{"appeared": set, "resolved": set, "current": set}`

### Pool configuration detection

`detect_pool_config(conn, start_utc, end_utc) -> dict | None` queries:
```sql
SELECT event FROM jsonl_events
WHERE ts_utc >= ? AND ts_utc <= ?
  AND (event LIKE 'INVALIDATE%size=%' OR event LIKE 'QueuePool limit%')
LIMIT 1
```
Parses `size=(\d+)` and `overflow\s+(\d+)` (or `overflow=\d+/(\d+)`) from the event string.

### NOSRV clustering

Already computed as `count_nosrv` in `query_epoch_haproxy()`. Add a second query:
```sql
SELECT COUNT(*) FROM haproxy_events
WHERE ts_utc >= ? AND ts_utc <= ?
  AND server = '<NOSRV>'
  AND ts_utc <= ?  -- epoch_start + 60 seconds
```

### Restart gap

Computed in the review orchestrator or renderer: `epoch[i].start_utc - epoch[i-1].end_utc`. No SQL needed — arithmetic on existing epoch timestamps.

## Existing Patterns

- `query_epoch_haproxy()` already computes `count_nosrv` — just not displayed
- `_md_table()` helper already exists for table generation
- INVALIDATE events are in `jsonl_events` with the pool state embedded in the `event` string
- `enrich_restart_reasons()` already examines inter-epoch gaps — gap duration is the same timestamp arithmetic

## Implementation Phases

### Phase 1: Event normalisation and error landscape diff
**Goal:** `normalise_event()` and `compute_error_landscape()` functions with tests

**Components:**
- `normalise_event(event: str) -> str` in `analysis.py` — regex-based token replacement
- `compute_error_landscape(conn, epochs) -> list[dict]` in `analysis.py` — per-epoch appeared/resolved sets
- Tests with real event strings from the incident DB (the strings observed during brainstorming)

**Done when:** Given epochs with known error events, the landscape correctly identifies appeared and resolved classes. Normalisation collapses memory addresses, UUIDs, and task names.

### Phase 2: Pool config, NOSRV clustering, restart gaps
**Goal:** Three small query/compute functions

**Components:**
- `detect_pool_config(conn, start_utc, end_utc) -> dict | None` in `analysis.py`
- NOSRV first-60s query added to `query_epoch_haproxy()` return dict
- Restart gap computation in the review orchestrator (timestamp arithmetic)

**Done when:** Pool config detected from INVALIDATE events, NOSRV clustering shows first-60s count, gaps computed between epochs.

### Phase 3: Renderer updates and methodology section
**Goal:** Display all new data in the report, add methodology prose

**Components:**
- Per-epoch: NOSRV count + clustering, appeared/resolved error tables, pool config
- Timeline: gap duration column
- Methodology section at report top
- All tables via `_md_table()`

**Done when:** `incident_db.py review` against `incident.db` produces a report with all 7 evidence items visible.

## Additional Considerations

**Normalisation stability:** The regex replacement order matters — UUIDs contain hex digits that could match the address pattern. Apply UUID replacement before address replacement.

**Performance:** `compute_error_landscape()` queries `jsonl_events` once per epoch for distinct normalised classes. On a 3.6M-event DB this is fast because the time-window filter uses the `idx_jsonl_ts` index. Normalisation happens in Python on the result set (typically < 100 distinct event strings per epoch).

**INVALIDATE pool state variance:** Within a single epoch, INVALIDATE events may show different `checked_out` and `overflow` counts (the pool state varies under load). Only `size` and `max_overflow` (the configured limits) are stable — extract those, ignore the transient state counters.
