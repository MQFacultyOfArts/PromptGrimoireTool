#!/usr/bin/env bash
# watch-class-load.sh — live class-load numbers during a tutorial session.
# Run on the prod host:
#
#   /opt/promptgrimoire/deploy/watch-class-load.sh            # refresh every 60s
#   /opt/promptgrimoire/deploy/watch-class-load.sh --once     # single snapshot
#   COURSE_CODE=LAWS1000 WATCH_INTERVAL=30 .../watch-class-load.sh
#
# Reads the app's structured JSON log (memory_diagnostic / page_load_profile
# events) and counts student workspaces per activity from PostgreSQL.
# Requires: jq, psql peer access as $DB_USER.

set -euo pipefail

INTERVAL="${WATCH_INTERVAL:-60}"
COURSE_CODE="${COURSE_CODE:-LAWS1000}"
DB_NAME="${DB_NAME:-promptgrimoire}"
DB_USER="${DB_USER:-promptgrimoire}"
LOG_DIR="${GRIMOIRE_LOG_DIR:-/opt/promptgrimoire/logs}"

# Newest JSONL wins: the log file name is branch-suffixed on non-main.
log_file() {
    find "$LOG_DIR" -maxdepth 1 -name 'promptgrimoire*.jsonl' \
        -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-
}

# Parse the tail of the JSONL log, skipping any malformed lines.
recent_events() {
    tail -5000 "$1" | jq -R 'fromjson? // empty'
}

server_section() {
    local file="$1"
    # Last diagnostic snapshot (emitted every ~5 min by the app).
    recent_events "$file" | jq -r '
        select(.event == "memory_diagnostic") |
        [ .timestamp,
          "clients=\(.clients_connected)/\(.clients_total)",
          "users=\(.users_authenticated)",
          "lag_ms=\(.event_loop_lag_ms)",
          "adm cap=\(.admission_cap) adm=\(.admission_admitted) q=\(.admission_queue_depth)",
          "rss_mb=\((.current_rss_bytes // 0) / 1048576 | floor)"
        ] | join("  ")' | tail -1
}

page_load_section() {
    local file="$1" since="$2"
    recent_events "$file" | jq -rs --arg since "$since" '
        [ .[] | select(.event == "page_load_profile" and .timestamp >= $since) ]
        | if length == 0 then "  no page loads in window"
          else ( [.[].total_ms] | sort ) as $t |
            "  loads=\(length)  " +
            "p50_ms=\($t[(length / 2 | floor)])  " +
            "max_ms=\($t[-1])"
          end'
}

error_section() {
    local file="$1" since="$2"
    recent_events "$file" | jq -rs --arg since "$since" '
        [ .[] | select((.level == "error" or .level == "critical")
                       and .timestamp >= $since) ]
        | if length == 0 then "  no errors in window"
          else "  errors=\(length)  last: \(.[-1].event)" end'
}

activity_section() {
    psql -U "$DB_USER" -d "$DB_NAME" -X --pset=footer=off -c "
        SELECT a.title,
               count(DISTINCT w.id) AS ws_total,
               count(DISTINCT w.id) FILTER (
                   WHERE w.updated_at >= now() - interval '12 hours'
               ) AS ws_12h,
               count(DISTINCT w.id) FILTER (
                   WHERE w.updated_at >= now() - interval '10 minutes'
               ) AS ws_10m,
               count(DISTINCT ae.user_id) FILTER (
                   WHERE w.updated_at >= now() - interval '12 hours'
               ) AS students_12h
        FROM activity a
        JOIN week wk ON wk.id = a.week_id
        JOIN course c ON c.id = wk.course_id
        LEFT JOIN workspace w
            ON w.activity_id = a.id AND w.id <> a.template_workspace_id
        LEFT JOIN acl_entry ae
            ON ae.workspace_id = w.id AND ae.permission = 'owner'
        WHERE c.code ILIKE '%${COURSE_CODE}%'
        GROUP BY a.id, a.title
        ORDER BY ws_10m DESC, ws_12h DESC, a.title;"
}

snapshot() {
    local file since_10m
    file=$(log_file)
    since_10m=$(date -u -d '-10 minutes' +%Y-%m-%dT%H:%M:%S)

    echo "=== $(date '+%H:%M:%S %Z')  (course: ${COURSE_CODE}) ==="
    if [[ -n "$file" ]]; then
        echo "server   $(server_section "$file")"
        echo "loads (10m):"
        page_load_section "$file" "$since_10m"
        echo "errors (10m):"
        error_section "$file" "$since_10m"
    else
        echo "server   no log file found under $LOG_DIR"
    fi
    echo "activities:"
    activity_section
    echo
}

if [[ "${1:-}" == "--once" ]]; then
    snapshot
    exit 0
fi

while true; do
    snapshot
    sleep "$INTERVAL"
done
