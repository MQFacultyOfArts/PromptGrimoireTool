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
JSONL_LOG="/home/promptgrimoire/PromptGrimoireTool/logs/promptgrimoire.jsonl"
HAPROXY_LOG="/var/log/haproxy.log"
PG_LOG_DIR="/var/log/postgresql"
UNIT_NAME="promptgrimoire.service"

# -------------------------------------------------------------------
# Helpers (same pattern as restart.sh)
# -------------------------------------------------------------------
step() { echo "==> $1"; }

usage() {
    cat >&2 <<EOF
Usage: $0 --start "YYYY-MM-DD HH:MM" --end "YYYY-MM-DD HH:MM"

Times are interpreted as local (server timezone, typically AEDT).
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

step "Collecting telemetry for window: $START → $END"
step "Working directory: $WORKDIR"

# -------------------------------------------------------------------
# 1. Export systemd journal as JSON
# -------------------------------------------------------------------
step "Exporting systemd journal (JSON)..."
JOURNAL_FILE="$WORKDIR/journal.json"
journalctl --unit="$UNIT_NAME" --output=json \
    --since="$START" --until="$END" \
    > "$JOURNAL_FILE" 2>/dev/null || true
# --since/--until use local time by default, matching our AEDT input.
# Empty window → empty file (AC1.5).

# -------------------------------------------------------------------
# Compute ISO 8601 UTC bounds with 5-minute buffer for filtering.
# Used by JSONL (jq) and HAProxy (awk) server-side filters.
# -------------------------------------------------------------------
FILTER_START_UTC=$(date --utc -d "$START - 5 minutes" +"%Y-%m-%dT%H:%M:%SZ")
FILTER_END_UTC=$(date --utc -d "$END + 5 minutes" +"%Y-%m-%dT%H:%M:%SZ")
# Also compute local ISO 8601 bounds for HAProxy (rsyslog uses local time).
FILTER_START_LOCAL=$(date -d "$START - 5 minutes" +"%Y-%m-%dT%H:%M:%S%:z")
FILTER_END_LOCAL=$(date -d "$END + 5 minutes" +"%Y-%m-%dT%H:%M:%S%:z")

step "Filter window (UTC): $FILTER_START_UTC → $FILTER_END_UTC"

# -------------------------------------------------------------------
# 2. Filter application JSONL log by timestamp window
# -------------------------------------------------------------------
step "Filtering structlog JSONL..."
JSONL_FILE="$WORKDIR/structlog.jsonl"
if [[ -f "$JSONL_LOG" ]]; then
    if command -v jq &>/dev/null; then
        # ISO 8601 timestamps sort lexicographically — jq string comparison works.
        jq -c "select(.timestamp >= \"$FILTER_START_UTC\" and .timestamp <= \"$FILTER_END_UTC\")" \
            "$JSONL_LOG" > "$JSONL_FILE" 2>/dev/null || true
    else
        # Fallback: copy in full if jq unavailable.
        echo "WARNING: jq not found, copying full JSONL file" >&2
        cp "$JSONL_LOG" "$JSONL_FILE"
    fi
else
    echo "WARNING: JSONL log not found at $JSONL_LOG" >&2
    touch "$JSONL_FILE"
fi

# -------------------------------------------------------------------
# 3. Filter HAProxy log by rsyslog timestamp prefix
# -------------------------------------------------------------------
step "Filtering HAProxy log..."
HAPROXY_FILE="$WORKDIR/haproxy.log"
if [[ -f "$HAPROXY_LOG" ]]; then
    # rsyslog ISO 8601 prefix (e.g. "2026-03-16T16:06:30+11:00") is the first
    # space-delimited field. ISO 8601 with fixed-offset sorts lexicographically.
    awk -v start="$FILTER_START_LOCAL" -v end="$FILTER_END_LOCAL" \
        '{ ts = substr($1, 1, 25); if (ts >= start && ts <= end) print }' \
        "$HAPROXY_LOG" > "$HAPROXY_FILE" 2>/dev/null || true
else
    echo "WARNING: HAProxy log not found at $HAPROXY_LOG" >&2
    touch "$HAPROXY_FILE"
fi

# -------------------------------------------------------------------
# 4. Copy PostgreSQL log (most recent)
# -------------------------------------------------------------------
step "Copying PostgreSQL log..."
PG_FILE="$WORKDIR/postgresql.log"
# Find the most recent .log file in the PG log directory.
PG_LATEST=$(find "$PG_LOG_DIR" -name "*.log" -type f -printf '%T@ %p\n' 2>/dev/null \
    | sort -rn | head -1 | cut -d' ' -f2-)
if [[ -n "$PG_LATEST" ]]; then
    cp "$PG_LATEST" "$PG_FILE"
else
    echo "WARNING: No PostgreSQL log found in $PG_LOG_DIR" >&2
    touch "$PG_FILE"
fi

# -------------------------------------------------------------------
# 5. Build manifest.json
# -------------------------------------------------------------------
step "Building manifest.json..."

SERVER_HOSTNAME=$(hostname -f)
SERVER_TZ=$(timedatectl show --property=Timezone --value)
COLLECTION_TS=$(date --utc +"%Y-%m-%dT%H:%M:%SZ")

# Convert local start/end to UTC for manifest.
# GNU date can parse "YYYY-MM-DD HH:MM" in local time and emit UTC.
START_UTC=$(date --utc -d "$START" +"%Y-%m-%dT%H:%M:%SZ")
END_UTC=$(date --utc -d "$END" +"%Y-%m-%dT%H:%M:%SZ")

# Build per-file metadata.
file_entry() {
    local filepath="$1"
    local basename
    basename=$(basename "$filepath")
    local sha256
    sha256=$(sha256sum "$filepath" | cut -d' ' -f1)
    local size
    size=$(stat --format="%s" "$filepath")
    local mtime
    mtime=$(stat --format="%Y" "$filepath")
    printf '{"filename":"%s","sha256":"%s","size":%s,"mtime":%s}' \
        "$basename" "$sha256" "$size" "$mtime"
}

# Collect file entries into a JSON array.
FILES_JSON="["
first=true
for f in "$JOURNAL_FILE" "$JSONL_FILE" "$HAPROXY_FILE" "$PG_FILE"; do
    if [[ "$first" == true ]]; then
        first=false
    else
        FILES_JSON+=","
    fi
    FILES_JSON+=$(file_entry "$f")
done
FILES_JSON+="]"

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
    "files": $FILES_JSON
}
MANIFEST_EOF

# Pretty-print with jq if available (non-fatal if missing).
if command -v jq &>/dev/null; then
    jq . "$WORKDIR/manifest.json" > "$WORKDIR/manifest.json.tmp" \
        && mv "$WORKDIR/manifest.json.tmp" "$WORKDIR/manifest.json"
fi

# -------------------------------------------------------------------
# 6. Create tarball
# -------------------------------------------------------------------
TARBALL="/tmp/telemetry-${TIMESTAMP}.tar.gz"
step "Creating tarball: $TARBALL"

tar -czf "$TARBALL" -C "$WORKDIR" .

# Cancel the cleanup trap — we want the tarball to survive.
trap - EXIT
rm -rf "$WORKDIR"

step "Done. Tarball: $TARBALL"
echo ""
echo "To copy to your local machine:"
echo "  scp grimoire.drbbs.org:$TARBALL ."
