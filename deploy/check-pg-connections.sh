#!/usr/bin/env bash
# check-pg-connections.sh — Alert to Discord when idle-in-transaction connections
# exceed a threshold. Run via cron every 2 minutes.
#
# Usage:
#   */2 * * * * /opt/promptgrimoire/deploy/check-pg-connections.sh
#
# Requires: ALERTING__DISCORD_WEBHOOK_URL in /opt/promptgrimoire/.env
# Exits silently if webhook URL is not configured.

set -euo pipefail

THRESHOLD="${PG_IDLE_TX_THRESHOLD:-5}"
DB_NAME="${DB_NAME:-promptgrimoire}"
DB_USER="${DB_USER:-promptgrimoire}"
ENV_FILE="${ENV_FILE:-/opt/promptgrimoire/.env}"

# Read webhook URL from .env
WEBHOOK_URL=""
if [[ -f "$ENV_FILE" ]]; then
    WEBHOOK_URL=$(grep -E '^ALERTING__DISCORD_WEBHOOK_URL=' "$ENV_FILE" | cut -d= -f2- | tr -d "'\"")
fi

if [[ -z "$WEBHOOK_URL" ]]; then
    exit 0
fi

# Query pg_stat_activity for idle-in-transaction count
IDLE_TX=$(psql -U "$DB_USER" -d "$DB_NAME" -tA -c \
    "SELECT count(*) FROM pg_stat_activity WHERE datname = '$DB_NAME' AND state = 'idle in transaction';")

# Strip whitespace
IDLE_TX=$(echo "$IDLE_TX" | tr -d '[:space:]')

if [[ "$IDLE_TX" -le "$THRESHOLD" ]]; then
    exit 0
fi

# Get total pool stats for context
POOL_STATS=$(psql -U "$DB_USER" -d "$DB_NAME" -tA -c \
    "SELECT string_agg(state || ': ' || cnt::text, ', ' ORDER BY cnt DESC) FROM (SELECT state, count(*) AS cnt FROM pg_stat_activity WHERE datname = '$DB_NAME' GROUP BY state) sub;")

HOSTNAME=$(hostname)
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Post Discord embed matching the app's alert style
curl -s -o /dev/null -H "Content-Type: application/json" -d "{
  \"embeds\": [{
    \"title\": \"[WARNING] PostgreSQL idle-in-transaction connections\",
    \"description\": \"**${IDLE_TX}** connections idle in transaction (threshold: ${THRESHOLD})\",
    \"color\": 16776960,
    \"fields\": [
      {\"name\": \"Pool breakdown\", \"value\": \"${POOL_STATS}\", \"inline\": false},
      {\"name\": \"server\", \"value\": \"${HOSTNAME}\", \"inline\": true},
      {\"name\": \"database\", \"value\": \"${DB_NAME}\", \"inline\": true}
    ],
    \"timestamp\": \"${TIMESTAMP}\"
  }]
}" "$WEBHOOK_URL"
