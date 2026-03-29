#!/usr/bin/env bats
# Unit tests for deploy/restart.sh
#
# These test argument parsing and guard clauses without
# requiring root, HAProxy, or the application installed.

SCRIPT="$BATS_TEST_DIRNAME/../restart.sh"

# ---------------------------------------------------------------------------
# Root guard
# ---------------------------------------------------------------------------

@test "non-root user is rejected" {
    if [ "$EUID" -eq 0 ]; then
        skip "running as root"
    fi
    run bash "$SCRIPT"
    [ "$status" -eq 1 ]
    [[ "$output" == *"run as root"* ]]
}

@test "non-root user is rejected even with --skip-tests" {
    if [ "$EUID" -eq 0 ]; then
        skip "running as root"
    fi
    run bash "$SCRIPT" --skip-tests
    [ "$status" -eq 1 ]
    [[ "$output" == *"run as root"* ]]
}

# ---------------------------------------------------------------------------
# Token extraction (sources the exact grep|cut line from restart.sh)
# ---------------------------------------------------------------------------

# Extract the PRE_RESTART_TOKEN assignment line from restart.sh and evaluate
# it with APP_DIR pointed at a temp directory.  This tests the actual script
# logic, not a re-implementation.
_extract_token() {
    local app_dir="$1"
    # shellcheck disable=SC2034  # APP_DIR used by eval'd line
    APP_DIR="$app_dir"
    eval "$(sed -n 's/^\(PRE_RESTART_TOKEN=.*\)/\1/p' "$SCRIPT" | head -1)"
    echo "$PRE_RESTART_TOKEN"
}

@test "token extraction from .env reads PRE_RESTART_TOKEN" {
    tmpdir=$(mktemp -d)
    echo 'ADMIN__PRE_RESTART_TOKEN=test-secret-value' > "$tmpdir/.env"

    result=$(_extract_token "$tmpdir")
    [ "$result" = "test-secret-value" ]

    rm -rf "$tmpdir"
}

@test "missing token in .env produces empty string" {
    tmpdir=$(mktemp -d)
    echo 'DATABASE__URL=postgres://localhost/test' > "$tmpdir/.env"

    result=$(_extract_token "$tmpdir")
    [ -z "$result" ]

    rm -rf "$tmpdir"
}

# ---------------------------------------------------------------------------
# Drain timeout (sources the exact DRAIN_TIMEOUT line from restart.sh)
# ---------------------------------------------------------------------------

_extract_drain_timeout() {
    eval "$(sed -n 's/^\(DRAIN_TIMEOUT=.*\)/\1/p' "$SCRIPT" | head -1)"
    echo "$DRAIN_TIMEOUT"
}

@test "DRAIN_TIMEOUT defaults to 30" {
    unset DRAIN_TIMEOUT
    result=$(_extract_drain_timeout)
    [ "$result" -eq 30 ]
}

@test "DRAIN_TIMEOUT is overridable" {
    export DRAIN_TIMEOUT=10
    result=$(_extract_drain_timeout)
    [ "$result" -eq 10 ]
}

# ---------------------------------------------------------------------------
# Worker service lifecycle
# ---------------------------------------------------------------------------

@test "restart.sh references promptgrimoire-worker service" {
    grep -q 'promptgrimoire-worker' "$SCRIPT"
}

@test "restart.sh guards worker operations with list-unit-files check" {
    grep -q 'list-unit-files.*promptgrimoire-worker' "$SCRIPT"
}

@test "restart.sh stops worker before app restart" {
    # Worker stop must appear before 'systemctl restart promptgrimoire'
    # Use '^systemctl' to avoid matching comments in the header
    stop_line=$(grep -n 'systemctl stop promptgrimoire-worker' "$SCRIPT" | head -1 | cut -d: -f1)
    restart_line=$(grep -n '^systemctl restart promptgrimoire' "$SCRIPT" | head -1 | cut -d: -f1)
    [ -n "$stop_line" ]
    [ -n "$restart_line" ]
    [ "$stop_line" -lt "$restart_line" ]
}

@test "restart.sh starts worker after healthz wait" {
    # Worker start must appear after the healthz wait loop
    # The healthz loop uses 'curl.*HEALTHZ' (variable reference)
    healthz_line=$(grep -n 'curl.*HEALTHZ' "$SCRIPT" | tail -1 | cut -d: -f1)
    start_line=$(grep -n 'systemctl start promptgrimoire-worker' "$SCRIPT" | head -1 | cut -d: -f1)
    [ -n "$healthz_line" ]
    [ -n "$start_line" ]
    [ "$start_line" -gt "$healthz_line" ]
}

@test "restart.sh verifies worker is active after start" {
    grep -q 'systemctl is-active.*promptgrimoire-worker' "$SCRIPT"
}
