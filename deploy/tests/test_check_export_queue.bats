#!/usr/bin/env bats
# Unit tests for deploy/check-export-queue.sh
#
# These tests exercise the queue depth alerting script with stubbed psql
# and curl to avoid needing a real database or Discord webhook.

SCRIPT="$BATS_TEST_DIRNAME/../check-export-queue.sh"

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

# Helper: create psql stub returning a given depth|oldest result
_stub_psql() {
    local result="$1"
    cat >"$BIN_DIR/psql" <<STUB
#!/usr/bin/env bash
echo "$result"
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
# Queue depth below threshold
# ---------------------------------------------------------------------------

@test "exits 0 when queue depth is below default threshold (10)" {
    _write_env
    _stub_psql "5|2026-03-28 01:00:00+00"
    _run_script
    [ "$status" -eq 0 ]
    [ ! -f "$CURL_LOG" ]
}

@test "exits 0 when queue depth equals threshold" {
    _write_env
    _stub_psql "10|2026-03-28 01:00:00+00"
    _run_script
    [ "$status" -eq 0 ]
    [ ! -f "$CURL_LOG" ]
}

@test "exits 0 when queue depth is zero" {
    _write_env
    _stub_psql "0|none"
    _run_script
    [ "$status" -eq 0 ]
    [ ! -f "$CURL_LOG" ]
}

# ---------------------------------------------------------------------------
# Queue depth above threshold — alert fires
# ---------------------------------------------------------------------------

@test "calls curl when queue depth exceeds default threshold" {
    _write_env
    _stub_psql "15|2026-03-28 01:00:00+00"
    _run_script
    [ "$status" -eq 0 ]
    [ -f "$CURL_LOG" ]
    grep -q "discord.test/webhook" "$CURL_LOG"
}

@test "Discord embed includes queue depth count" {
    _write_env
    _stub_psql "15|2026-03-28 01:00:00+00"
    _run_script
    [ "$status" -eq 0 ]
    grep -q '"15"' "$CURL_LOG"
}

@test "Discord embed includes oldest timestamp" {
    _write_env
    _stub_psql "15|2026-03-28 01:00:00+00"
    _run_script
    [ "$status" -eq 0 ]
    # Assert the full timestamp string — not just the date prefix — to catch
    # whitespace-stripping bugs that collapse "2026-03-28 01:00:00" into
    # "2026-03-2801:00:00".
    grep -q "2026-03-28 01:00:00" "$CURL_LOG"
}

# ---------------------------------------------------------------------------
# EXPORT_QUEUE_THRESHOLD override
# ---------------------------------------------------------------------------

@test "EXPORT_QUEUE_THRESHOLD overrides default threshold" {
    _write_env
    _stub_psql "3|2026-03-28 01:00:00+00"
    _run_script EXPORT_QUEUE_THRESHOLD=2
    [ "$status" -eq 0 ]
    [ -f "$CURL_LOG" ]
    grep -q "discord.test/webhook" "$CURL_LOG"
}

@test "EXPORT_QUEUE_THRESHOLD=20 suppresses alert for depth 15" {
    _write_env
    _stub_psql "15|2026-03-28 01:00:00+00"
    _run_script EXPORT_QUEUE_THRESHOLD=20
    [ "$status" -eq 0 ]
    [ ! -f "$CURL_LOG" ]
}

# ---------------------------------------------------------------------------
# SQL query correctness
# ---------------------------------------------------------------------------

@test "script queries export_job table with correct status filter" {
    grep -q 'export_job' "$SCRIPT"
    grep -qE "status IN \('queued', 'running'\)" "$SCRIPT"
}

# ---------------------------------------------------------------------------
# Default threshold value
# ---------------------------------------------------------------------------

@test "default threshold is 10" {
    run grep -oP 'EXPORT_QUEUE_THRESHOLD:-\K[0-9]+' "$SCRIPT"
    [ "$status" -eq 0 ]
    [ "$output" = "10" ]
}
