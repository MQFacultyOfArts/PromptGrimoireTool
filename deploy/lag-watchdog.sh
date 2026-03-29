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
CRITICAL="${LAG_CRITICAL:-1000}"  # ms — instant restart, no strikes
SERVICE="promptgrimoire"

prev_lag=0
strike_count=0
cooldown_until=0  # epoch seconds — suppress strikes until this time

echo "lag-watchdog: instant restart >${CRITICAL}ms, escalating restart >${WARN}ms x2"
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
    now=$(date +%s)

    # Cooldown: suppress strikes for 2 minutes after a restart
    if [ "$now" -lt "$cooldown_until" ]; then
        if [ "$lag" -gt "$WARN" ]; then
            echo "  ❄ cooldown (lag=${lag}ms, $(( cooldown_until - now ))s remaining)"
        fi
        prev_lag="$lag"
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
        systemctl restart "$SERVICE"
        strike_count=0
        prev_lag=0
        cooldown_until=$(( $(date +%s) + 120 ))
        continue
    fi

    # Rule 2: escalating above warn threshold — 2 consecutive increasing readings
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
            systemctl restart "$SERVICE"
            strike_count=0
            prev_lag=0
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
done
