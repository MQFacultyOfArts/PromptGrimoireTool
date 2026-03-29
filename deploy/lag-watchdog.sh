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

WARN="${LAG_WARN:-50}"       # ms — same as ⚠ display threshold
SERVICE="promptgrimoire"

prev_lag=0
strike_count=0

echo "lag-watchdog: restart when ⚠ (>${WARN}ms) AND increasing, 2 in a row"
echo "---"

journalctl -u "$SERVICE" -f --output cat | while IFS= read -r line; do
    output=$(echo "$line" | jq -r '
        if .event == "memory_diagnostic" then
            [
                (.timestamp[:19] + "Z" | fromdateiso8601 + 39600 | strftime("%H:%M:%S")),
                (.current_rss_bytes/1048576 | floor | tostring) + "MB",
                (.clients_connected | tostring) + " users",
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

    if [ "$lag" -gt "$WARN" ] && [ "$lag" -gt "$prev_lag" ] && [ "$prev_lag" -gt "$WARN" ]; then
        # Both readings above warn AND increasing — escalating, not recovering
        strike_count=$((strike_count + 1))
        echo "  ⚡ STRIKE ${strike_count}/2 (${prev_lag}ms → ${lag}ms, users=${users})"

        if [ "$strike_count" -ge 2 ]; then
            echo ""
            echo "=========================================="
            echo "  🔴 WATCHDOG RESTART"
            echo "  Sustained escalating lag: ${prev_lag}ms → ${lag}ms"
            echo "  $(date '+%H:%M:%S') — restarting ${SERVICE}"
            echo "=========================================="
            echo ""
            systemctl restart "$SERVICE"
            strike_count=0
        fi
    else
        if [ "$strike_count" -gt 0 ]; then
            echo "  ✓ reset (lag=${lag}ms, prev=${prev_lag}ms)"
        fi
        strike_count=0
    fi
    prev_lag="$lag"
done
