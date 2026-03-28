#!/usr/bin/env bats
# Unit tests for deploy/check-replication-lag.sh
#
# These tests exercise the replication lag alerting script with stubbed psql
# and curl to avoid needing a real database or Discord webhook.

SCRIPT="$BATS_TEST_DIRNAME/../check-replication-lag.sh"

setup() {
    TEST_ROOT=$(mktemp -d)
    BIN_DIR="$TEST_ROOT/bin"
    ENV_DIR="$TEST_ROOT/app"

    mkdir -p "$BIN_DIR" "$ENV_DIR"

    # Stub hostname
    cat >"$BIN_DIR/hostname" <<'STUB'
#!/usr/bin/env bash
echo "grimoire.test"
STUB
    chmod +x "$BIN_DIR/hostname"

    # Default: no curl calls recorded
    CURL_LOG="$TEST_ROOT/curl.log"

    # Stub curl that logs its arguments
    cat >"$BIN_DIR/curl" <<STUB
#!/usr/bin/env bash
echo "\$@" >> "$CURL_LOG"
STUB
    chmod +x "$BIN_DIR/curl"
}

teardown() {
    rm -rf "$TEST_ROOT"
}

# Helper: create .env with webhook URL
_write_env() {
    echo "ALERTING__DISCORD_WEBHOOK_URL=https://discord.test/webhook" > "$ENV_DIR/.env"
}

# Helper: create psql stub returning a given result line
_stub_psql() {
    local result="$1"
    cat >"$BIN_DIR/psql" <<STUB
#!/usr/bin/env bash
echo "$result"
STUB
    chmod +x "$BIN_DIR/psql"
}

# Helper: create psql stub returning empty output (no rows)
_stub_psql_empty() {
    cat >"$BIN_DIR/psql" <<'STUB'
#!/usr/bin/env bash
# Return nothing — simulates zero rows from pg_stat_replication
STUB
    chmod +x "$BIN_DIR/psql"
}

# Helper: run the script with stubs on PATH
_run_script() {
    run env \
        PATH="$BIN_DIR:$PATH" \
        ENV_FILE="$ENV_DIR/.env" \
        DB_NAME="testdb" \
        DB_USER="testuser" \
        "$@" \
        bash "$SCRIPT"
}

# ---------------------------------------------------------------------------
# Webhook not configured
# ---------------------------------------------------------------------------

@test "exits 0 when .env file does not exist" {
    _run_script ENV_FILE="$TEST_ROOT/nonexistent/.env"
    [ "$status" -eq 0 ]
    [ -z "$output" ]
}

@test "exits 0 when ALERTING__DISCORD_WEBHOOK_URL is missing from .env" {
    echo "DATABASE__URL=postgres://localhost/test" > "$ENV_DIR/.env"
    _run_script
    [ "$status" -eq 0 ]
    [ -z "$output" ]
}

@test "exits 0 when ALERTING__DISCORD_WEBHOOK_URL is empty in .env" {
    echo "ALERTING__DISCORD_WEBHOOK_URL=" > "$ENV_DIR/.env"
    _run_script
    [ "$status" -eq 0 ]
    [ -z "$output" ]
}

# ---------------------------------------------------------------------------
# Lag within threshold — no alert
# ---------------------------------------------------------------------------

@test "exits 0 when lag is within default threshold (300s)" {
    _write_env
    _stub_psql "120|streaming|nci_standby"
    _run_script
    [ "$status" -eq 0 ]
    [ ! -f "$CURL_LOG" ]
}

@test "exits 0 when lag equals threshold" {
    _write_env
    _stub_psql "300|streaming|nci_standby"
    _run_script
    [ "$status" -eq 0 ]
    [ ! -f "$CURL_LOG" ]
}

@test "exits 0 when lag is zero" {
    _write_env
    _stub_psql "0|streaming|nci_standby"
    _run_script
    [ "$status" -eq 0 ]
    [ ! -f "$CURL_LOG" ]
}

@test "exits 0 when lag is NULL (no pending writes, lag_seconds=-1)" {
    _write_env
    _stub_psql "-1|streaming|nci_standby"
    _run_script
    [ "$status" -eq 0 ]
    [ ! -f "$CURL_LOG" ]
}

# ---------------------------------------------------------------------------
# Lag exceeds threshold — alert fires
# ---------------------------------------------------------------------------

@test "calls curl when lag exceeds default threshold" {
    _write_env
    _stub_psql "600|streaming|nci_standby"
    _run_script
    [ "$status" -eq 0 ]
    [ -f "$CURL_LOG" ]
    grep -q "discord.test/webhook" "$CURL_LOG"
}

@test "Discord embed includes lag seconds" {
    _write_env
    _stub_psql "600|streaming|nci_standby"
    _run_script
    [ "$status" -eq 0 ]
    grep -q '"600"' "$CURL_LOG"
}

@test "Discord embed includes replication state" {
    _write_env
    _stub_psql "600|streaming|nci_standby"
    _run_script
    [ "$status" -eq 0 ]
    grep -q '"streaming"' "$CURL_LOG"
}

@test "Discord embed includes slot name" {
    _write_env
    _stub_psql "600|streaming|nci_standby"
    _run_script
    [ "$status" -eq 0 ]
    grep -q '"nci_standby"' "$CURL_LOG"
}

# ---------------------------------------------------------------------------
# Standby disconnected — no rows returned
# ---------------------------------------------------------------------------

@test "alerts when no replication rows returned (standby disconnected)" {
    _write_env
    _stub_psql_empty
    _run_script
    [ "$status" -eq 0 ]
    [ -f "$CURL_LOG" ]
    grep -q "discord.test/webhook" "$CURL_LOG"
}

@test "disconnected alert includes CRITICAL severity" {
    _write_env
    _stub_psql_empty
    _run_script
    [ "$status" -eq 0 ]
    grep -q "CRITICAL" "$CURL_LOG"
}

@test "disconnected alert mentions slot name" {
    _write_env
    _stub_psql_empty
    _run_script
    [ "$status" -eq 0 ]
    grep -q "nci_standby" "$CURL_LOG"
}

# ---------------------------------------------------------------------------
# REPLICATION_LAG_THRESHOLD override
# ---------------------------------------------------------------------------

@test "REPLICATION_LAG_THRESHOLD overrides default threshold" {
    _write_env
    _stub_psql "150|streaming|nci_standby"
    _run_script REPLICATION_LAG_THRESHOLD=100
    [ "$status" -eq 0 ]
    [ -f "$CURL_LOG" ]
    grep -q "discord.test/webhook" "$CURL_LOG"
}

@test "REPLICATION_LAG_THRESHOLD=1000 suppresses alert for lag 600" {
    _write_env
    _stub_psql "600|streaming|nci_standby"
    _run_script REPLICATION_LAG_THRESHOLD=1000
    [ "$status" -eq 0 ]
    [ ! -f "$CURL_LOG" ]
}

# ---------------------------------------------------------------------------
# Default threshold value
# ---------------------------------------------------------------------------

@test "default threshold is 300 seconds" {
    run grep -oP 'REPLICATION_LAG_THRESHOLD:-\K[0-9]+' "$SCRIPT"
    [ "$status" -eq 0 ]
    [ "$output" = "300" ]
}

# ---------------------------------------------------------------------------
# SLOT_NAME override env variable
# ---------------------------------------------------------------------------

@test "SLOT_NAME override appears in disconnected-alert curl payload" {
    _write_env
    _stub_psql_empty
    _run_script SLOT_NAME=custom_slot
    [ "$status" -eq 0 ]
    [ -f "$CURL_LOG" ]
    grep -q "custom_slot" "$CURL_LOG"
}

# ---------------------------------------------------------------------------
# SQL query correctness
# ---------------------------------------------------------------------------

@test "script queries pg_stat_replication with slot filter" {
    grep -q 'pg_stat_replication' "$SCRIPT"
    grep -q 'slot_name' "$SCRIPT"
    grep -q 'replay_lag' "$SCRIPT"
}
