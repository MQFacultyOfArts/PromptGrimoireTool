#!/bin/bash
# External watchdog: monitors promptgrimoire event loop lag, restarts on sustained spikes.
# Run as a separate systemd service. NOT in-process.
#
# Tails journald for memory_diagnostic events, prints a live dashboard,
# and restarts the service if lag exceeds THRESHOLD for STRIKES consecutive readings.
#
# Environment variables:
#   LAG_THRESHOLD  — lag in ms that counts as a strike (default: 1000)
#   LAG_STRIKES    — consecutive strikes before restart (default: 2)

set -euo pipefail

WARN="${LAG_WARN:-100}"      # ms — escalation strike threshold
CRITICAL="${LAG_CRITICAL:-1000}"  # ms — instant restart, no strikes
SERVICE="promptgrimoire"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TELEMETRY_WINDOW_MINUTES="${TELEMETRY_WINDOW_MINUTES:-15}"

# Capture telemetry before restarting so log rotation can't clobber evidence.
# Runs in background — restart proceeds immediately, tarball lands in /tmp/.
capture_and_restart() {
    local reason="$1"
    local end_time start_time
    end_time=$(date '+%Y-%m-%d %H:%M')
    start_time=$(date -d "${TELEMETRY_WINDOW_MINUTES} minutes ago" '+%Y-%m-%d %H:%M')

    echo "  📦 capturing telemetry [${reason}] (${start_time} → ${end_time})"
    "$SCRIPT_DIR/collect-telemetry.sh" \
        --start "$start_time" --end "$end_time" &

    systemctl restart "$SERVICE"
}

prev_lag=0
prev_users=0
strike_count=0
cooldown_until=$(( $(date +%s) + 120 ))  # suppress strikes for 2min on startup too

echo "lag-watchdog: kill >${CRITICAL}ms | escalate >${WARN}ms x2 | 2min cooldown active"
echo "---"

journalctl -u "$SERVICE" -f --output cat | while IFS= read -r line; do
    output=$(echo "$line" | jq -r '
        if .event == "memory_diagnostic" then
            [
                (.timestamp[:19] + "Z" | fromdateiso8601 + 39600 | strftime("%H:%M:%S")),
                (.current_rss_bytes/1048576 | floor | tostring) + "MB",
                (.clients_connected | tostring) + " ws ("
                    + (.users_authenticated // 0 | tostring) + " reg)",
                (.asyncio_tasks_total | tostring) + " tasks",
                (if .event_loop_lag_ms > 50 then "⚠ " else "" end)
                    + (.event_loop_lag_ms | floor | tostring) + "ms lag"
            ] | @tsv
        elif .event == "memory_restart_triggered" or .event == "graceful_shutdown" then
            "🔴 " + .event
        else
            empty
        end
    ' 2>/dev/null) || continue

    [ -z "$output" ] && continue
    echo "$output"

    # Extract lag for watchdog logic
    lag=$(echo "$line" | jq -r '
        if .event == "memory_diagnostic" then .event_loop_lag_ms // 0 | floor
        else empty end
    ' 2>/dev/null) || continue

    [ -z "$lag" ] && continue

    users=$(echo "$line" | jq -r '.clients_connected // 0' 2>/dev/null) || true
    now=$(date +%s)

    # Cooldown: suppress strikes for 2 minutes after a restart
    if [ "$now" -lt "$cooldown_until" ]; then
        if [ "$lag" -gt "$WARN" ]; then
            echo "  ❄ cooldown (lag=${lag}ms, $(( cooldown_until - now ))s remaining)"
        fi
        prev_lag="$lag"
        prev_users="$users"
        continue
    fi

    # Rule 1: over 1000ms — just kill it
    if [ "$lag" -gt "$CRITICAL" ]; then
        echo ""
        echo "=========================================="
        echo "  🔴 WATCHDOG RESTART — CRITICAL"
        echo "  lag=${lag}ms (>${CRITICAL}ms), users=${users}"
        echo "  $(date '+%H:%M:%S') — restarting ${SERVICE}"
        echo "=========================================="
        echo ""
        capture_and_restart "critical_lag=${lag}ms"
        strike_count=0
        prev_lag=0
        prev_users=0
        cooldown_until=$(( $(date +%s) + 120 ))
        continue
    fi

    # Rule 2: mass disconnect — users dropped >50% between readings (event loop blocking clients out)
    if [ "$prev_users" -gt 50 ] && [ "$users" -gt 0 ] && [ "$users" -lt $(( prev_users / 2 )) ]; then
        echo ""
        echo "=========================================="
        echo "  🔴 WATCHDOG RESTART — MASS DISCONNECT"
        echo "  users ${prev_users} → ${users} (>50% drop)"
        echo "  $(date '+%H:%M:%S') — restarting ${SERVICE}"
        echo "=========================================="
        echo ""
        capture_and_restart "mass_disconnect=${prev_users}_to_${users}"
        strike_count=0
        prev_lag=0
        prev_users=0
        cooldown_until=$(( $(date +%s) + 120 ))
        continue
    fi

    # Rule 3: escalating above warn threshold — 2 consecutive increasing readings
    if [ "$lag" -gt "$WARN" ] && [ "$lag" -gt "$prev_lag" ] && [ "$prev_lag" -gt "$WARN" ]; then
        strike_count=$((strike_count + 1))
        echo "  ⚡ STRIKE ${strike_count}/2 (${prev_lag}ms → ${lag}ms, users=${users})"

        if [ "$strike_count" -ge 2 ]; then
            echo ""
            echo "=========================================="
            echo "  🔴 WATCHDOG RESTART — ESCALATING"
            echo "  ${prev_lag}ms → ${lag}ms, users=${users}"
            echo "  $(date '+%H:%M:%S') — restarting ${SERVICE}"
            echo "=========================================="
            echo ""
            capture_and_restart "escalating_lag=${prev_lag}ms_to_${lag}ms"
            strike_count=0
            prev_lag=0
            prev_users=0
            cooldown_until=$(( $(date +%s) + 120 ))
            continue
        fi
    else
        if [ "$strike_count" -gt 0 ]; then
            echo "  ✓ reset (lag=${lag}ms, prev=${prev_lag}ms)"
        fi
        strike_count=0
    fi
    prev_lag="$lag"
    prev_users="$users"
done
