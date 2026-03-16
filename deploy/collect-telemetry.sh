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
APP_DIR="/opt/promptgrimoire"
JSONL_LOG="$APP_DIR/logs/sessions/promptgrimoire.jsonl"
HAPROXY_LOG="/var/log/haproxy.log"
PG_LOG_DIR="/var/log/postgresql"
UNIT_NAME="promptgrimoire.service"

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
if [[ $EUID -ne 0 ]]; then
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

# Compute filter bounds from local input times.
# IMPORTANT: `date --utc -d "NAIVE"` treats input as UTC, not local.
# Parse as local first (gets offset), then convert to UTC for output.
FILTER_START_LOCAL=$(date -d "$START" +"%Y-%m-%dT%H:%M:%S%:z")
FILTER_END_LOCAL=$(date -d "$END" +"%Y-%m-%dT%H:%M:%S%:z")
FILTER_START_UTC=$(date -u -d "$FILTER_START_LOCAL" +"%Y-%m-%dT%H:%M:%SZ")
FILTER_END_UTC=$(date -u -d "$FILTER_END_LOCAL" +"%Y-%m-%dT%H:%M:%SZ")

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
# -------------------------------------------------------------------
step "Filtering structlog JSONL..."
JSONL_FILE="$WORKDIR/structlog.jsonl"
JSONL_METHOD="not collected"
if [[ -f "$JSONL_LOG" ]]; then
    if command -v jq &>/dev/null; then
        JSONL_METHOD="jq timestamp filter"
        if ! jq -c "select(.timestamp >= \"$FILTER_START_UTC\" and .timestamp <= \"$FILTER_END_UTC\")" \
            "$JSONL_LOG" > "$JSONL_FILE" 2>"$WORKDIR/jsonl.stderr"; then
            warn "jq filtering failed (see jsonl.stderr in tarball)"
            JSONL_METHOD="jq (failed, full copy)"
            cp "$JSONL_LOG" "$JSONL_FILE"
        fi
    else
        warn "jq not found, copying full JSONL file"
        JSONL_METHOD="full copy (jq unavailable)"
        cp "$JSONL_LOG" "$JSONL_FILE"
    fi
else
    warn "JSONL log not found at $JSONL_LOG"
    JSONL_METHOD="missing"
    touch "$JSONL_FILE"
fi

# -------------------------------------------------------------------
# 3. Filter HAProxy log by rsyslog timestamp prefix
#    Collects current log + rotated .1 file if it exists.
# -------------------------------------------------------------------
step "Filtering HAProxy log..."
HAPROXY_FILE="$WORKDIR/haproxy.log"
HAPROXY_METHOD="not collected"
HAPROXY_SOURCES=""
if [[ -f "$HAPROXY_LOG" ]] || [[ -f "${HAPROXY_LOG}.1" ]]; then
    HAPROXY_METHOD="awk timestamp filter"
    # Concatenate current + rotated (if exists) before filtering.
    {
        [[ -f "${HAPROXY_LOG}.1" ]] && cat "${HAPROXY_LOG}.1" && HAPROXY_SOURCES="${HAPROXY_LOG}.1"
        [[ -f "$HAPROXY_LOG" ]] && cat "$HAPROXY_LOG" && HAPROXY_SOURCES="${HAPROXY_SOURCES:+$HAPROXY_SOURCES, }${HAPROXY_LOG}"
    } | awk -v start="$FILTER_START_LOCAL" -v end="$FILTER_END_LOCAL" \
        '{ ts = substr($1, 1, 25); if (ts >= start && ts <= end) print }' \
        > "$HAPROXY_FILE" 2>"$WORKDIR/haproxy.stderr"
    if [[ $? -ne 0 ]]; then
        warn "HAProxy awk filtering failed (see haproxy.stderr in tarball)"
        HAPROXY_METHOD="awk (failed)"
    fi
else
    warn "HAProxy log not found at $HAPROXY_LOG"
    HAPROXY_METHOD="missing"
    touch "$HAPROXY_FILE"
fi

# -------------------------------------------------------------------
# 4. Copy PostgreSQL log (most recent .json or .log, plus rotated)
# -------------------------------------------------------------------
step "Copying PostgreSQL logs..."
PG_METHOD="not collected"
PG_SOURCE=""
PG_COUNT=0
# Copy ALL .json and .log files — both formats may exist during a transition.
for pg_file in $(find "$PG_LOG_DIR" -name "*.json" -o -name "*.log" 2>/dev/null | sort); do
    pg_basename=$(basename "$pg_file")
    cp "$pg_file" "$WORKDIR/$pg_basename"
    PG_SOURCE="${PG_SOURCE:+$PG_SOURCE, }$pg_file"
    PG_COUNT=$((PG_COUNT + 1))
done
if [[ $PG_COUNT -gt 0 ]]; then
    PG_METHOD="full copy ($PG_COUNT files)"
    step "  Copied $PG_COUNT PostgreSQL log file(s)"
else
    warn "No PostgreSQL log found in $PG_LOG_DIR"
    PG_METHOD="missing"
    PG_SOURCE="none"
fi

# -------------------------------------------------------------------
# 5. Build manifest.json
# -------------------------------------------------------------------
step "Building manifest.json..."

SERVER_HOSTNAME=$(hostname -f)
SERVER_TZ=$(timedatectl show --property=Timezone --value)
COLLECTION_TS=$(date --utc +"%Y-%m-%dT%H:%M:%SZ")

# UTC bounds for manifest (reuse the correctly-computed filter bounds).
START_UTC="$FILTER_START_UTC"
END_UTC="$FILTER_END_UTC"

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
        structlog.jsonl)  FILES_JSON+=$(file_entry "$f" "$JSONL_LOG" "$JSONL_METHOD") ;;
        haproxy.log)      FILES_JSON+=$(file_entry "$f" "${HAPROXY_SOURCES:-$HAPROXY_LOG}" "$HAPROXY_METHOD") ;;
        postgresql*)      FILES_JSON+=$(file_entry "$f" "${PG_SOURCE:-unknown}" "$PG_METHOD") ;;
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
# 6. Create tarball
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
echo "To copy to your local machine:"
echo "  scp grimoire.drbbs.org:$TARBALL ."
