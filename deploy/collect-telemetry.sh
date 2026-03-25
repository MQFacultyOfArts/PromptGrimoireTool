#!/usr/bin/env bash
# collect-telemetry.sh — Package time-windowed telemetry for incident analysis.
#
# Usage:
#   collect-telemetry.sh --start "2026-03-16 14:50" --end "2026-03-16 17:20"
#
# Requires root (reads journal, copies system logs).
# Produces /tmp/telemetry-YYYYMMDD-HHMM.tar.gz with manifest.json.

set -euo pipefail

# -------------------------------------------------------------------
# Configuration — edit these if log paths change on the server
# -------------------------------------------------------------------
APP_DIR="${APP_DIR:-/opt/promptgrimoire}"
JSONL_LOG="${JSONL_LOG:-$APP_DIR/logs/sessions/promptgrimoire.jsonl}"
HAPROXY_LOG="${HAPROXY_LOG:-/var/log/haproxy.log}"
PG_LOG_DIR="${PG_LOG_DIR:-/var/log/postgresql}"
PGBOUNCER_LOG="${PGBOUNCER_LOG:-/var/log/pgbouncer/pgbouncer.log}"
# PostgreSQL logging_collector writes to log_directory relative to the data
# directory (default: "log" → /var/lib/postgresql/*/main/log/).  Detect this
# automatically so we collect jsonlog output regardless of configuration.
PG_COLLECTOR_DIR="${PG_COLLECTOR_DIR:-}"
if [[ -z "$PG_COLLECTOR_DIR" ]]; then
    # Ask the running cluster for its data directory + log_directory.
    # Connect via Unix socket directly to PG (not through PgBouncer) using
    # the postgres superuser.  -h /var/run/postgresql ensures we bypass
    # PgBouncer even if PGHOST or .pg_service.conf redirect the default.
    _pg_data=$(sudo -u postgres psql -h /var/run/postgresql -qtAX -c "SHOW data_directory;" 2>/dev/null || true)
    _pg_logdir=$(sudo -u postgres psql -h /var/run/postgresql -qtAX -c "SHOW log_directory;" 2>/dev/null || true)
    if [[ -n "$_pg_data" ]] && [[ -n "$_pg_logdir" ]]; then
        if [[ "$_pg_logdir" == /* ]]; then
            # Absolute path
            PG_COLLECTOR_DIR="$_pg_logdir"
        else
            # Relative to data directory
            PG_COLLECTOR_DIR="$_pg_data/$_pg_logdir"
        fi
        [[ -d "$PG_COLLECTOR_DIR" ]] || PG_COLLECTOR_DIR=""
    fi
fi
UNIT_NAME="${UNIT_NAME:-promptgrimoire.service}"
DB_NAME="${DB_NAME:-promptgrimoire}"
DB_USER="${DB_USER:-promptgrimoire}"

# -------------------------------------------------------------------
# Helpers (same pattern as restart.sh)
# -------------------------------------------------------------------
step() { echo "==> $1"; }
warn() { echo "WARNING: $1" >&2; WARNINGS+=("$1"); }

usage() {
    cat >&2 <<EOF
Usage: $0 --start "YYYY-MM-DD HH:MM" --end "YYYY-MM-DD HH:MM"

Times are interpreted as local (server timezone).
Produces /tmp/telemetry-YYYYMMDD-HHMM.tar.gz
EOF
    exit 1
}

# -------------------------------------------------------------------
# Argument parsing
# -------------------------------------------------------------------
START=""
END=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --start) START="$2"; shift 2 ;;
        --end)   END="$2";   shift 2 ;;
        *)       usage ;;
    esac
done

[[ -z "$START" || -z "$END" ]] && usage

# -------------------------------------------------------------------
# Root guard (same pattern as restart.sh)
# -------------------------------------------------------------------
if [[ "${COLLECT_TELEMETRY_ALLOW_NON_ROOT:-0}" != "1" && $EUID -ne 0 ]]; then
    echo "ERROR: Must run as root (need journal + log access)." >&2
    exit 1
fi

# -------------------------------------------------------------------
# Prepare workspace
# -------------------------------------------------------------------
TIMESTAMP=$(date +%Y%m%d-%H%M)
WORKDIR=$(mktemp -d "/tmp/telemetry-${TIMESTAMP}.XXXXXX")
trap 'rm -rf "$WORKDIR"' EXIT
WARNINGS=()

step "Collecting telemetry for window: $START → $END"
step "Working directory: $WORKDIR"

# Compute requested UTC bounds and buffered filter bounds.
REQUEST_START_EPOCH=$(date -d "$START" +%s)
REQUEST_END_EPOCH=$(date -d "$END" +%s)
FILTER_START_EPOCH=$((REQUEST_START_EPOCH - 300))
FILTER_END_EPOCH=$((REQUEST_END_EPOCH + 300))

REQUEST_START_UTC=$(date -u -d "@$REQUEST_START_EPOCH" +"%Y-%m-%dT%H:%M:%SZ")
REQUEST_END_UTC=$(date -u -d "@$REQUEST_END_EPOCH" +"%Y-%m-%dT%H:%M:%SZ")
FILTER_START_LOCAL=$(date -d "@$FILTER_START_EPOCH" +"%Y-%m-%dT%H:%M:%S%:z")
FILTER_END_LOCAL=$(date -d "@$FILTER_END_EPOCH" +"%Y-%m-%dT%H:%M:%S%:z")
FILTER_START_UTC=$(date -u -d "@$FILTER_START_EPOCH" +"%Y-%m-%dT%H:%M:%SZ")
FILTER_END_UTC=$(date -u -d "@$FILTER_END_EPOCH" +"%Y-%m-%dT%H:%M:%SZ")

step "Filter window (UTC): $FILTER_START_UTC → $FILTER_END_UTC"

# -------------------------------------------------------------------
# 1. Export systemd journal as JSON
# -------------------------------------------------------------------
step "Exporting systemd journal (JSON)..."
JOURNAL_FILE="$WORKDIR/journal.json"
JOURNAL_METHOD="journalctl --since/--until"
if ! journalctl --unit="$UNIT_NAME" --output=json \
    --since="$START" --until="$END" \
    > "$JOURNAL_FILE" 2>"$WORKDIR/journal.stderr"; then
    warn "journalctl failed (see journal.stderr in tarball)"
    JOURNAL_METHOD="journalctl (failed)"
    touch "$JOURNAL_FILE"
fi
# --since/--until use local time by default, matching our local input.
# Empty window → empty file (AC1.5).

# -------------------------------------------------------------------
# 2. Filter application JSONL log by timestamp window
#    Collects current log + rotated .1, .2, … files (oldest first).
# -------------------------------------------------------------------
step "Filtering structlog JSONL..."
JSONL_FILE="$WORKDIR/structlog.jsonl"
JSONL_METHOD="not collected"
JSONL_SOURCES=""

# Gather rotated files in reverse numeric order (oldest first), then current.
# Rotated logs are named .1, .2, … — sort -rV gives highest number first (oldest).
jsonl_inputs=()
while IFS= read -r rotated; do
    [[ -f "$rotated" ]] && jsonl_inputs+=("$rotated")
done < <(printf '%s\n' "${JSONL_LOG}".[0-9]* | sort -rV)
if [[ -f "$JSONL_LOG" ]]; then
    jsonl_inputs+=("$JSONL_LOG")
fi

if [[ ${#jsonl_inputs[@]} -gt 0 ]]; then
    JSONL_SOURCES=$(printf '%s, ' "${jsonl_inputs[@]}")
    JSONL_SOURCES=${JSONL_SOURCES%, }
    step "  Found ${#jsonl_inputs[@]} JSONL file(s): $JSONL_SOURCES"
    if command -v jq &>/dev/null; then
        JSONL_METHOD="jq timestamp filter"
        if ! cat "${jsonl_inputs[@]}" | jq -c \
            "select(.timestamp >= \"$FILTER_START_UTC\" and .timestamp <= \"$FILTER_END_UTC\")" \
            > "$JSONL_FILE" 2>"$WORKDIR/jsonl.stderr"; then
            warn "jq filtering failed (see jsonl.stderr in tarball)"
            JSONL_METHOD="jq (failed, full copy)"
            cat "${jsonl_inputs[@]}" > "$JSONL_FILE"
        fi
    else
        warn "jq not found, copying full JSONL files"
        JSONL_METHOD="full copy (jq unavailable)"
        cat "${jsonl_inputs[@]}" > "$JSONL_FILE"
    fi
else
    warn "JSONL log not found at $JSONL_LOG (checked rotated files too)"
    JSONL_METHOD="missing"
    touch "$JSONL_FILE"
fi

# -------------------------------------------------------------------
# 3. Filter HAProxy log by rsyslog timestamp prefix
#    Collects current log + rotated .1, .2, … files (oldest first).
# -------------------------------------------------------------------
step "Filtering HAProxy log..."
HAPROXY_FILE="$WORKDIR/haproxy.log"
HAPROXY_METHOD="not collected"
HAPROXY_SOURCES=""

# Gather rotated files in reverse numeric order (oldest first), then current.
# Excludes .gz (logrotate compressed archives). sort -rV gives highest number first.
haproxy_inputs=()
while IFS= read -r rotated; do
    [[ -f "$rotated" && "$rotated" != *.gz ]] && haproxy_inputs+=("$rotated")
done < <(printf '%s\n' "${HAPROXY_LOG}".[0-9]* | sort -rV)
if [[ -f "$HAPROXY_LOG" ]]; then
    haproxy_inputs+=("$HAPROXY_LOG")
fi

if [[ ${#haproxy_inputs[@]} -gt 0 ]]; then
    HAPROXY_SOURCES=$(printf '%s, ' "${haproxy_inputs[@]}")
    HAPROXY_SOURCES=${HAPROXY_SOURCES%, }
    step "  Found ${#haproxy_inputs[@]} HAProxy file(s): $HAPROXY_SOURCES"
    HAPROXY_METHOD="awk timestamp filter"
    if ! cat "${haproxy_inputs[@]}" | awk -v start="$FILTER_START_LOCAL" -v end="$FILTER_END_LOCAL" \
        '{ ts = substr($1, 1, 25); if (ts >= start && ts <= end) print }' \
        > "$HAPROXY_FILE" 2>"$WORKDIR/haproxy.stderr"; then
        warn "HAProxy awk filtering failed (see haproxy.stderr in tarball)"
        HAPROXY_METHOD="awk (failed)"
    fi
else
    warn "HAProxy log not found at $HAPROXY_LOG"
    HAPROXY_METHOD="missing"
    touch "$HAPROXY_FILE"
fi

# -------------------------------------------------------------------
# 4. Collect PostgreSQL logs (current + rotated, within time window)
# -------------------------------------------------------------------
step "Collecting PostgreSQL logs..."
PG_METHOD="not collected"
PG_SOURCE=""
PG_COUNT=0

# Search two directories:
#   PG_LOG_DIR      — syslog/logrotate-managed (e.g., /var/log/postgresql/)
#                     Files: postgresql-16-main.log, .log.1, .log.2.gz, etc.
#   PG_COLLECTOR_DIR — PostgreSQL logging_collector output
#                     (e.g., /var/lib/postgresql/16/main/log/)
#                     Files: postgresql-YYYY-MM-DD_HHMMSS.json/.log (daily)
#
# Concatenate all matching files in chronological order into one output file
# per extension (.json, .log).  Decompress .gz on the fly.

_pg_collect_from_dir() {
    local dir="$1" ext="$2" output="$3"
    [[ -d "$dir" ]] || return 1

    local found=0
    # Find all files matching *.${ext}* (includes rotated: .1, .2.gz, etc.)
    # Sort by name (works for both logrotate numbering and date-stamped names)
    while IFS= read -r f; do
        [[ -n "$f" ]] || continue
        if [[ "$f" == *.gz ]]; then
            zcat "$f" >> "$output" 2>/dev/null && found=1
        else
            # Skip empty files (e.g., current .log after rotation)
            [[ -s "$f" ]] || continue
            cat "$f" >> "$output" 2>/dev/null && found=1
        fi
        PG_SOURCE="${PG_SOURCE:+$PG_SOURCE, }$f"
    done < <(find "$dir" -maxdepth 1 -name "postgresql*.${ext}*" -type f 2>/dev/null | sort)

    return $((1 - found))
}

_pg_collect() {
    local ext="$1" output="$2"
    local found=0
    # Collect from syslog-managed directory
    _pg_collect_from_dir "$PG_LOG_DIR" "$ext" "$output" && found=1
    # Collect from logging_collector directory (if different)
    if [[ -n "${PG_COLLECTOR_DIR:-}" ]] && [[ "$PG_COLLECTOR_DIR" != "$PG_LOG_DIR" ]]; then
        _pg_collect_from_dir "$PG_COLLECTOR_DIR" "$ext" "$output" && found=1
    fi
    return $((1 - found))
}

# Collect JSON logs (PostgreSQL jsonlog destination)
if _pg_collect "json" "$WORKDIR/postgresql.json"; then
    PG_COUNT=$((PG_COUNT + 1))
fi

# Collect plain text logs (syslog/stderr destination)
if _pg_collect "log" "$WORKDIR/postgresql.log"; then
    PG_COUNT=$((PG_COUNT + 1))
fi

# Remove empty output files
for f in "$WORKDIR/postgresql.json" "$WORKDIR/postgresql.log"; do
    if [[ -f "$f" ]] && [[ ! -s "$f" ]]; then
        rm -f "$f"
        PG_COUNT=$((PG_COUNT - 1))
    fi
done

if [[ $PG_COUNT -gt 0 ]]; then
    PG_METHOD="concatenated rotated logs"
    step "  Collected PostgreSQL logs from: $PG_SOURCE"
else
    warn "No PostgreSQL log content found in $PG_LOG_DIR"
    PG_METHOD="missing"
    PG_SOURCE="none"
fi

# -------------------------------------------------------------------
# 4b. Copy PgBouncer log
# -------------------------------------------------------------------
step "Collecting PgBouncer log..."
PGBOUNCER_METHOD="not collected"
PGBOUNCER_SOURCE="none"

if [[ -f "$PGBOUNCER_LOG" ]] && [[ -s "$PGBOUNCER_LOG" ]]; then
    cp "$PGBOUNCER_LOG" "$WORKDIR/pgbouncer.log"
    PGBOUNCER_METHOD="full copy"
    PGBOUNCER_SOURCE="$PGBOUNCER_LOG"
    step "  Collected PgBouncer log from: $PGBOUNCER_LOG"
else
    # Check for rotated logs
    _pgb_dir=$(dirname "$PGBOUNCER_LOG")
    _pgb_base=$(basename "$PGBOUNCER_LOG")
    if [[ -d "$_pgb_dir" ]]; then
        _pgb_found=0
        while IFS= read -r f; do
            [[ -n "$f" ]] || continue
            if [[ "$f" == *.gz ]]; then
                zcat "$f" >> "$WORKDIR/pgbouncer.log" 2>/dev/null && _pgb_found=1
            else
                [[ -s "$f" ]] || continue
                cat "$f" >> "$WORKDIR/pgbouncer.log" 2>/dev/null && _pgb_found=1
            fi
            PGBOUNCER_SOURCE="${PGBOUNCER_SOURCE:+$PGBOUNCER_SOURCE, }$f"
        done < <(find "$_pgb_dir" -maxdepth 1 -name "${_pgb_base}*" -type f 2>/dev/null | sort)
        if [[ $_pgb_found -eq 1 ]]; then
            PGBOUNCER_METHOD="concatenated rotated logs"
            step "  Collected PgBouncer logs from: $PGBOUNCER_SOURCE"
        fi
    fi
    if [[ "$PGBOUNCER_METHOD" == "not collected" ]]; then
        warn "PgBouncer log not found at $PGBOUNCER_LOG"
    fi
fi

# Remove empty output file
if [[ -f "$WORKDIR/pgbouncer.log" ]] && [[ ! -s "$WORKDIR/pgbouncer.log" ]]; then
    rm -f "$WORKDIR/pgbouncer.log"
    PGBOUNCER_METHOD="empty"
fi

# -------------------------------------------------------------------
# 5. Snapshot application database counts
# -------------------------------------------------------------------
step "Snapshotting database counts..."
DB_SNAPSHOT_FILE="$WORKDIR/db-snapshot.json"
DB_METHOD="not collected"

# Run as the app user (peer auth) to avoid password prompts.
DB_QUERY="SELECT json_build_object(
  'snapshot_utc', now() AT TIME ZONE 'UTC',
  'global', (SELECT json_build_object(
    'users', (SELECT count(*) FROM \"user\"),
    'workspaces', (SELECT count(*) FROM workspace),
    'courses', (SELECT count(*) FROM course),
    'enrollments', (SELECT count(*) FROM course_enrollment),
    'activities', (SELECT count(*) FROM activity),
    'documents', (SELECT count(*) FROM workspace_document),
    'tags', (SELECT count(*) FROM tag),
    'tag_groups', (SELECT count(*) FROM tag_group),
    'acl_entries', (SELECT count(*) FROM acl_entry)
  )),
  'growth_by_day', (SELECT json_agg(row_to_json(t)) FROM (
    SELECT date(created_at AT TIME ZONE 'Australia/Sydney') as day,
           count(*) as workspaces,
           count(DISTINCT activity_id) as activities_used
    FROM workspace GROUP BY 1 ORDER BY 1
  ) t),
  'users_by_day', (SELECT json_agg(row_to_json(t)) FROM (
    SELECT date(created_at AT TIME ZONE 'Australia/Sydney') as day, count(*) as users
    FROM \"user\" GROUP BY 1 ORDER BY 1
  ) t),
  'crdt_sizes', (SELECT json_build_object(
    'total_with_crdt', count(*),
    'avg_bytes', avg(length(crdt_state)),
    'max_bytes', max(length(crdt_state)),
    'p50_bytes', percentile_cont(0.5) WITHIN GROUP (ORDER BY length(crdt_state)),
    'p95_bytes', percentile_cont(0.95) WITHIN GROUP (ORDER BY length(crdt_state)),
    'p99_bytes', percentile_cont(0.99) WITHIN GROUP (ORDER BY length(crdt_state))
  ) FROM workspace WHERE crdt_state IS NOT NULL AND length(crdt_state) > 0),
  'by_course', (SELECT json_agg(row_to_json(t)) FROM (
    SELECT c.code, c.name,
           count(DISTINCT a.id) as activities,
           count(DISTINCT ws.id) as workspaces,
           count(DISTINCT ae.user_id) as users_with_acl,
           count(DISTINCT tg.id) as tag_groups,
           count(DISTINCT tag.id) as tags
    FROM course c
    LEFT JOIN week w ON w.course_id = c.id
    LEFT JOIN activity a ON a.week_id = w.id
    LEFT JOIN workspace ws ON ws.activity_id = a.id
    LEFT JOIN acl_entry ae ON ae.workspace_id = ws.id
    LEFT JOIN tag_group tg ON tg.workspace_id = ws.id
    LEFT JOIN tag ON tag.group_id = tg.id
    GROUP BY c.id, c.code, c.name ORDER BY c.code
  ) t),
  'tags_per_workspace', (SELECT json_build_object(
    'avg', avg(tc),
    'max', max(tc),
    'p50', percentile_cont(0.5) WITHIN GROUP (ORDER BY tc),
    'p95', percentile_cont(0.95) WITHIN GROUP (ORDER BY tc)
  ) FROM (SELECT count(*) as tc FROM tag GROUP BY workspace_id) sub)
);"

# shellcheck disable=SC2024  # script runs as root; sudo -u de-escalates, redirect is fine
if sudo -u "$DB_USER" psql -At "$DB_NAME" -c "$DB_QUERY" > "$DB_SNAPSHOT_FILE" 2>"$WORKDIR/db-snapshot.stderr"; then
    DB_METHOD="psql snapshot"
    # Pretty-print if jq available.
    if command -v jq &>/dev/null; then
        jq . "$DB_SNAPSHOT_FILE" > "$DB_SNAPSHOT_FILE.tmp" \
            && mv "$DB_SNAPSHOT_FILE.tmp" "$DB_SNAPSHOT_FILE"
    fi
    step "  Database snapshot captured"
else
    warn "Database snapshot failed (see db-snapshot.stderr in tarball)"
    DB_METHOD="failed"
    touch "$DB_SNAPSHOT_FILE"
fi

# -------------------------------------------------------------------
# 6. Build manifest.json
# -------------------------------------------------------------------
step "Building manifest.json..."

SERVER_HOSTNAME=$(hostname -f)
SERVER_TZ=$(timedatectl show --property=Timezone --value)
COLLECTION_TS=$(date --utc +"%Y-%m-%dT%H:%M:%SZ")

# UTC bounds for manifest reflect the requested window, not the collector buffer.
START_UTC="$REQUEST_START_UTC"
END_UTC="$REQUEST_END_UTC"

# Build per-file metadata.
file_entry() {
    local filepath="$1"
    local source_path="$2"
    local method="$3"
    local fname
    fname=$(basename "$filepath")
    local sha256
    sha256=$(sha256sum "$filepath" | cut -d' ' -f1)
    local fsize
    fsize=$(stat --format="%s" "$filepath")
    local mtime
    mtime=$(stat --format="%Y" "$filepath")
    printf '{"filename":"%s","sha256":"%s","size":%s,"mtime":%s,"source_path":"%s","method":"%s"}' \
        "$fname" "$sha256" "$fsize" "$mtime" "$source_path" "$method"
}

# Collect file entries into a JSON array.
# Include all files in WORKDIR except manifest.json and .stderr files.
FILES_JSON="["
first=true
for f in "$WORKDIR"/*; do
    fname=$(basename "$f")
    [[ "$fname" == "manifest.json" ]] && continue
    [[ "$fname" == *.stderr ]] && continue
    if [[ "$first" == true ]]; then
        first=false
    else
        FILES_JSON+=","
    fi
    # Determine source path and method for each file.
    case "$fname" in
        journal.json)     FILES_JSON+=$(file_entry "$f" "journalctl" "$JOURNAL_METHOD") ;;
        structlog.jsonl)  FILES_JSON+=$(file_entry "$f" "${JSONL_SOURCES:-$JSONL_LOG}" "$JSONL_METHOD") ;;
        haproxy.log)      FILES_JSON+=$(file_entry "$f" "${HAPROXY_SOURCES:-$HAPROXY_LOG}" "$HAPROXY_METHOD") ;;
        postgresql*)      FILES_JSON+=$(file_entry "$f" "${PG_SOURCE:-unknown}" "$PG_METHOD") ;;
        pgbouncer.log)    FILES_JSON+=$(file_entry "$f" "${PGBOUNCER_SOURCE:-unknown}" "$PGBOUNCER_METHOD") ;;
        db-snapshot.json) FILES_JSON+=$(file_entry "$f" "$DB_NAME" "$DB_METHOD") ;;
        *)                FILES_JSON+=$(file_entry "$f" "unknown" "unknown") ;;
    esac
done
FILES_JSON+="]"

# Collect warnings into a JSON array.
WARNINGS_JSON="["
wfirst=true
for w in "${WARNINGS[@]+"${WARNINGS[@]}"}"; do
    if [[ "$wfirst" == true ]]; then
        wfirst=false
    else
        WARNINGS_JSON+=","
    fi
    WARNINGS_JSON+="\"$w\""
done
WARNINGS_JSON+="]"

# Assemble manifest.
cat > "$WORKDIR/manifest.json" <<MANIFEST_EOF
{
    "hostname": "$SERVER_HOSTNAME",
    "timezone": "$SERVER_TZ",
    "collection_timestamp": "$COLLECTION_TS",
    "requested_window": {
        "start_local": "$START",
        "end_local": "$END",
        "start_utc": "$START_UTC",
        "end_utc": "$END_UTC"
    },
    "files": $FILES_JSON,
    "warnings": $WARNINGS_JSON
}
MANIFEST_EOF

# Pretty-print with jq if available (non-fatal if missing).
if command -v jq &>/dev/null; then
    jq . "$WORKDIR/manifest.json" > "$WORKDIR/manifest.json.tmp" \
        && mv "$WORKDIR/manifest.json.tmp" "$WORKDIR/manifest.json"
fi

# Include any stderr files in the tarball for diagnostics.

# -------------------------------------------------------------------
# 7. Create tarball
# -------------------------------------------------------------------
TARBALL="/tmp/telemetry-${TIMESTAMP}.tar.gz"
step "Creating tarball: $TARBALL"

tar -czf "$TARBALL" -C "$WORKDIR" .

# Cancel the cleanup trap — we want the tarball to survive.
trap - EXIT
rm -rf "$WORKDIR"

# Report warnings at end for visibility.
if [[ ${#WARNINGS[@]} -gt 0 ]]; then
    echo ""
    echo "WARNINGS during collection:"
    for w in "${WARNINGS[@]}"; do
        echo "  - $w"
    done
fi

step "Done. Tarball: $TARBALL"
echo ""
echo "Next steps (run locally):"
echo ""
echo "  # 1. Copy tarball"
echo "  scp grimoire.drbbs.org:$TARBALL /tmp/"
echo ""
echo "  # 2. Fetch Beszel metrics (requires SSH tunnel: ssh -L 8090:localhost:8090 brian.fedarch.org)"
echo "  uv run scripts/incident_db.py beszel --start \"$START\" --end \"$END\" --hub http://localhost:8090 --db incident.db"
echo ""
echo "  # 3. Ingest tarball + GitHub data"
echo "  uv run scripts/incident_db.py ingest /tmp/$(basename "$TARBALL") --db incident.db"
echo "  uv run scripts/incident_db.py github --start \"$START\" --end \"$END\" --db incident.db"
echo ""
echo "  # 4. Generate review (db-snapshot.json is inside the tarball)"
echo "  tar xzf /tmp/$(basename "$TARBALL") ./db-snapshot.json -O > /tmp/db-snapshot.json"
echo "  uv run scripts/incident_db.py review --db incident.db --counts-json /tmp/db-snapshot.json --output /tmp/review.md"
