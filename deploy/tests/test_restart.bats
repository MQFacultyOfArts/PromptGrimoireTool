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
