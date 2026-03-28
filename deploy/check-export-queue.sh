#!/usr/bin/env bash
# check-export-queue.sh — Alert to Discord when the export queue exceeds a
# depth threshold. Run via cron every 2 minutes.
#
# Usage:
#   */2 * * * * /opt/promptgrimoire/deploy/check-export-queue.sh
#
# Requires: ALERTING__DISCORD_WEBHOOK_URL in /opt/promptgrimoire/.env
# Exits silently if webhook URL is not configured.

set -euo pipefail

THRESHOLD="${EXPORT_QUEUE_THRESHOLD:-10}"
DB_NAME="${DB_NAME:-promptgrimoire}"
DB_USER="${DB_USER:-promptgrimoire}"
ENV_FILE="${ENV_FILE:-/opt/promptgrimoire/.env}"

# Read webhook URL from .env
WEBHOOK_URL=""
if [[ -f "$ENV_FILE" ]]; then
    # || true: grep exits 1 when the key is absent; under set -e that would abort
    # the script before the empty-string guard below. Intentional divergence from
    # check-pg-connections.sh, which has no BATS coverage for the missing-key case.
    WEBHOOK_URL=$(grep -E '^ALERTING__DISCORD_WEBHOOK_URL=' "$ENV_FILE" | cut -d= -f2- | tr -d "'\"" || true)
fi

if [[ -z "$WEBHOOK_URL" ]]; then
    exit 0
fi

# Query export_job table for queued/running job count and oldest timestamp
RESULT=$(psql -U "$DB_USER" -d "$DB_NAME" -tA -c \
    "SELECT count(*) AS depth, COALESCE(min(created_at)::text, 'none') AS oldest FROM export_job WHERE status IN ('queued', 'running');")

# psql -tA returns "depth|oldest" — split on pipe
# DEPTH is an integer; strip whitespace. OLDEST is a timestamp; preserve spaces.
DEPTH=$(echo "$RESULT" | cut -d'|' -f1 | tr -d '[:space:]')
OLDEST=$(echo "$RESULT" | cut -d'|' -f2)

if [[ "$DEPTH" -le "$THRESHOLD" ]]; then
    exit 0
fi

HOSTNAME=$(hostname)
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Post Discord embed matching the app's alert style
curl -s -o /dev/null -H "Content-Type: application/json" -d "{
  \"embeds\": [{
    \"title\": \"[WARNING] Export queue depth exceeded\",
    \"description\": \"**${DEPTH}** jobs queued or running (threshold: ${THRESHOLD})\",
    \"color\": 16776960,
    \"fields\": [
      {\"name\": \"Queue depth\", \"value\": \"${DEPTH}\", \"inline\": true},
      {\"name\": \"Oldest queued\", \"value\": \"${OLDEST}\", \"inline\": true},
      {\"name\": \"server\", \"value\": \"${HOSTNAME}\", \"inline\": true}
    ],
    \"timestamp\": \"${TIMESTAMP}\"
  }]
}" "$WEBHOOK_URL"
