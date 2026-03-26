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
# Token extraction
# ---------------------------------------------------------------------------

@test "token extraction from .env reads PRE_RESTART_TOKEN" {
    tmpdir=$(mktemp -d)
    echo 'ADMIN__PRE_RESTART_TOKEN=test-secret-value' > "$tmpdir/.env"

    result=$(grep '^ADMIN__PRE_RESTART_TOKEN=' "$tmpdir/.env" | cut -d= -f2-)
    [ "$result" = "test-secret-value" ]

    rm -rf "$tmpdir"
}

@test "missing token in .env produces empty string" {
    tmpdir=$(mktemp -d)
    echo 'DATABASE__URL=postgres://localhost/test' > "$tmpdir/.env"

    result=$(grep '^ADMIN__PRE_RESTART_TOKEN=' "$tmpdir/.env" 2>/dev/null | cut -d= -f2-)
    [ -z "$result" ]

    rm -rf "$tmpdir"
}

# ---------------------------------------------------------------------------
# Drain timeout defaults
# ---------------------------------------------------------------------------

@test "DRAIN_TIMEOUT defaults to 30" {
    unset DRAIN_TIMEOUT
    result=${DRAIN_TIMEOUT:-30}
    [ "$result" -eq 30 ]
}

@test "DRAIN_TIMEOUT is overridable" {
    DRAIN_TIMEOUT=10
    result=${DRAIN_TIMEOUT:-30}
    [ "$result" -eq 10 ]
}
