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
SLOT_NAME="${SLOT_NAME:-nci_standby}"

# Read webhook URL from .env
WEBHOOK_URL=""
if [[ -f "$ENV_FILE" ]]; then
    WEBHOOK_URL=$(grep -E '^ALERTING__DISCORD_WEBHOOK_URL=' "$ENV_FILE" | cut -d= -f2- | tr -d "'\"" || true)
fi

if [[ -z "$WEBHOOK_URL" ]]; then
    exit 0
fi

# Query pg_stat_replication for replay lag on the target slot
RESULT=$(psql -U "$DB_USER" -d "$DB_NAME" -tA -c \
    "SELECT COALESCE(EXTRACT(EPOCH FROM replay_lag)::integer, -1) AS lag_seconds, state, COALESCE(slot_name, 'none') AS slot FROM pg_stat_replication WHERE slot_name = '$SLOT_NAME';") # SLOT_NAME must not contain single quotes (default 'nci_standby' is safe)

HOSTNAME=$(hostname)
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# No rows returned — standby is disconnected
if [[ -z "$RESULT" ]]; then
    curl -s -o /dev/null -H "Content-Type: application/json" -d "{
      \"embeds\": [{
        \"title\": \"[CRITICAL] Standby disconnected\",
        \"description\": \"No active replication for slot **${SLOT_NAME}**\",
        \"color\": 16711680,
        \"fields\": [
          {\"name\": \"Slot\", \"value\": \"${SLOT_NAME}\", \"inline\": true},
          {\"name\": \"server\", \"value\": \"${HOSTNAME}\", \"inline\": true}
        ],
        \"timestamp\": \"${TIMESTAMP}\"
      }]
    }" "$WEBHOOK_URL"
    exit 0
fi

# Parse psql output: lag_seconds|state|slot
LAG_SECONDS=$(echo "$RESULT" | cut -d'|' -f1 | tr -d '[:space:]')
STATE=$(echo "$RESULT" | cut -d'|' -f2 | tr -d '[:space:]')
SLOT=$(echo "$RESULT" | cut -d'|' -f3 | tr -d '[:space:]')

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
      {\"name\": \"Slot\", \"value\": \"${SLOT}\", \"inline\": true},
      {\"name\": \"server\", \"value\": \"${HOSTNAME}\", \"inline\": true}
    ],
    \"timestamp\": \"${TIMESTAMP}\"
  }]
}" "$WEBHOOK_URL"
exit 0
