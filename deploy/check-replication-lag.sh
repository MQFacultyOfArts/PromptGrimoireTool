#!/usr/bin/env bash
# check-replication-lag.sh — Alert to Discord when streaming replication lag
# exceeds a threshold or the standby is disconnected. Run via cron every 2 minutes.
#
# Usage:
#   */2 * * * * /opt/promptgrimoire/deploy/check-replication-lag.sh
#
# Requires: ALERTING__DISCORD_WEBHOOK_URL in /opt/promptgrimoire/.env
# Exits silently if webhook URL is not configured.

set -euo pipefail

THRESHOLD="${REPLICATION_LAG_THRESHOLD:-300}"
DB_NAME="${DB_NAME:-promptgrimoire}"
DB_USER="${DB_USER:-promptgrimoire}"
ENV_FILE="${ENV_FILE:-/opt/promptgrimoire/.env}"
# Filter by application_name set in the standby's primary_conninfo.
# pg_stat_replication does NOT have a slot_name column in PG16;
# application_name is the correct identifier for filtering standbys.
STANDBY_APP="${STANDBY_APP:-nci_standby}"

# Read webhook URL from .env
WEBHOOK_URL=""
if [[ -f "$ENV_FILE" ]]; then
    WEBHOOK_URL=$(grep -E '^ALERTING__DISCORD_WEBHOOK_URL=' "$ENV_FILE" | cut -d= -f2- | tr -d "'\"" || true)
fi

if [[ -z "$WEBHOOK_URL" ]]; then
    exit 0
fi

# Query pg_stat_replication for replay lag, filtering by application_name.
# STANDBY_APP must not contain single quotes (default 'nci_standby' is safe).
RESULT=$(psql -U "$DB_USER" -d "$DB_NAME" -tA -c \
    "SELECT COALESCE(EXTRACT(EPOCH FROM replay_lag)::integer, -1) AS lag_seconds, state, application_name FROM pg_stat_replication WHERE application_name = '$STANDBY_APP';")

HOSTNAME=$(hostname)
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# No rows returned — standby is disconnected
if [[ -z "$RESULT" ]]; then
    curl -s -o /dev/null -H "Content-Type: application/json" -d "{
      \"embeds\": [{
        \"title\": \"[CRITICAL] Standby disconnected\",
        \"description\": \"No active replication for standby **${STANDBY_APP}**\",
        \"color\": 16711680,
        \"fields\": [
          {\"name\": \"Standby\", \"value\": \"${STANDBY_APP}\", \"inline\": true},
          {\"name\": \"server\", \"value\": \"${HOSTNAME}\", \"inline\": true}
        ],
        \"timestamp\": \"${TIMESTAMP}\"
      }]
    }" "$WEBHOOK_URL"
    exit 0
fi

# Parse psql output: lag_seconds|state|application_name
LAG_SECONDS=$(echo "$RESULT" | cut -d'|' -f1 | tr -d '[:space:]')
STATE=$(echo "$RESULT" | cut -d'|' -f2 | tr -d '[:space:]')
APP=$(echo "$RESULT" | cut -d'|' -f3 | tr -d '[:space:]')

# lag_seconds = -1 means replay_lag is NULL (standby connected, no writes pending — normal)
if [[ "$LAG_SECONDS" -eq -1 ]]; then
    exit 0
fi

# Lag within threshold — all good
if [[ "$LAG_SECONDS" -le "$THRESHOLD" ]]; then
    exit 0
fi

# Lag exceeds threshold — alert
curl -s -o /dev/null -H "Content-Type: application/json" -d "{
  \"embeds\": [{
    \"title\": \"[WARNING] Replication lag exceeded\",
    \"description\": \"Replay lag **${LAG_SECONDS}s** exceeds threshold (${THRESHOLD}s)\",
    \"color\": 16776960,
    \"fields\": [
      {\"name\": \"Lag (seconds)\", \"value\": \"${LAG_SECONDS}\", \"inline\": true},
      {\"name\": \"State\", \"value\": \"${STATE}\", \"inline\": true},
      {\"name\": \"Standby\", \"value\": \"${APP}\", \"inline\": true},
      {\"name\": \"server\", \"value\": \"${HOSTNAME}\", \"inline\": true}
    ],
    \"timestamp\": \"${TIMESTAMP}\"
  }]
}" "$WEBHOOK_URL"
exit 0
