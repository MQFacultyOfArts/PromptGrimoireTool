#!/usr/bin/env bats
# Literal source patterns must not expand.
# shellcheck disable=SC2016
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
# Fail-closed restart prerequisites
# ---------------------------------------------------------------------------

@test "restart requires the pre-restart token before touching HAProxy" {
    token_line=$(grep -n 'read_required_env_value.*ADMIN__PRE_RESTART_TOKEN' "$SCRIPT" | head -1 | cut -d: -f1)
    haproxy_line=$(grep -n '^haproxy_touched=true' "$SCRIPT" | head -1 | cut -d: -f1)

    [ -n "$token_line" ]
    [ -n "$haproxy_line" ]
    [ "$token_line" -lt "$haproxy_line" ]
    run grep -q 'skipping pre-restart' "$SCRIPT"
    [ "$status" -ne 0 ]
}

@test "restart validates both endpoint count fields" {
    grep -q 'parse_json_count.*initial_count' "$SCRIPT"
    grep -q 'parse_json_count.*count' "$SCRIPT"
    run grep -q 'current=${current:-0}' "$SCRIPT"
    [ "$status" -ne 0 ]
    run grep -q 'initial_count=${initial_count:-0}' "$SCRIPT"
    [ "$status" -ne 0 ]
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

@test "restart.sh requires the standalone worker unit" {
    grep -q 'list-unit-files.*promptgrimoire-worker' "$SCRIPT"
    grep -q 'ABORT: required promptgrimoire-worker.service is not installed' "$SCRIPT"
}

@test "restart.sh updates an installed worker unit before restarting it" {
    install_line=$(grep -n 'install -m 0644.*promptgrimoire-worker\.service' "$SCRIPT" | head -1 | cut -d: -f1)
    reload_line=$(grep -n '^systemctl daemon-reload' "$SCRIPT" | head -1 | cut -d: -f1)
    restart_line=$(grep -n '^restart_runtime$' "$SCRIPT" | head -1 | cut -d: -f1)
    [ -n "$install_line" ]
    [ -n "$reload_line" ]
    [ -n "$restart_line" ]
    [ "$install_line" -lt "$reload_line" ]
    [ "$reload_line" -lt "$restart_line" ]
}

# ---------------------------------------------------------------------------
# Reproducible candidate and environment
# ---------------------------------------------------------------------------

@test "restart.sh requires a pinned full commit before dependency sync" {
    verify_line=$(grep -n 'CURRENT_COMMIT.*EXPECTED_COMMIT' "$SCRIPT" | head -1 | cut -d: -f1)
    sync_line=$(grep -n -F 'UV_PROJECT_ENVIRONMENT="$STAGED_VENV"' "$SCRIPT" | head -1 | cut -d: -f1)
    [ -n "$verify_line" ]
    [ -n "$sync_line" ]
    [ "$verify_line" -lt "$sync_line" ]
    grep -q 'sync --locked' "$SCRIPT"
}

@test "restart.sh runs deploy gates from the locked project directory" {
    run grep -F 'run --locked --no-sync grimoire test all' "$SCRIPT"
    [ "$status" -eq 0 ]
    run grep -F 'run --locked --no-sync grimoire test smoke-export' "$SCRIPT"
    [ "$status" -eq 0 ]
}

@test "restart.sh pins an accessible working directory before changing user" {
    cd_line=$(grep -n 'cd "$APP_DIR"' "$SCRIPT" | head -1 | cut -d: -f1)
    sudo_line=$(grep -n '^CURRENT_COMMIT=.*sudo -u promptgrimoire' "$SCRIPT" | head -1 | cut -d: -f1)

    [ -n "$cd_line" ]
    [ -n "$sudo_line" ]
    [ "$cd_line" -lt "$sudo_line" ]
}

@test "restart.sh installs locked JS test dependencies before the test gate" {
    npm_line=$(grep -n -F 'npm --prefix "$APP_DIR" ci --include=dev' "$SCRIPT" | head -1 | cut -d: -f1)
    gate_line=$(grep -n -F 'run --locked --no-sync grimoire test all' "$SCRIPT" | head -1 | cut -d: -f1)
    [ -n "$npm_line" ]
    [ -n "$gate_line" ]
    [ "$npm_line" -lt "$gate_line" ]
}

@test "restart.sh takes an exclusive deployment lock" {
    grep -q 'flock --exclusive --nonblock' "$SCRIPT"
}

@test "restart.sh revalidates the candidate after tests" {
    gate_line=$(grep -n 'run --locked --no-sync grimoire test all' "$SCRIPT" | head -1 | cut -d: -f1)
    revalidate_line=$(grep -n 'Revalidating tested candidate' "$SCRIPT" | head -1 | cut -d: -f1)

    [ -n "$gate_line" ]
    [ -n "$revalidate_line" ]
    [ "$revalidate_line" -gt "$gate_line" ]
}
