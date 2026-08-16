#!/usr/bin/env bats

HELPERS="$BATS_TEST_DIRNAME/../restart_helpers.sh"
EXPECTED_COMMIT=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa

setup() {
    TEST_ROOT="$BATS_TEST_TMPDIR/runtime-$BATS_TEST_NUMBER"
    APP_DIR="$TEST_ROOT/app"
    VENV_ROOT="$APP_DIR/.venvs"
    STAGED_VENV="$VENV_ROOT/$EXPECTED_COMMIT"
    FAKEBIN="$TEST_ROOT/bin"
    COMMAND_LOG="$TEST_ROOT/commands.log"
    WORKER_STARTED="$TEST_ROOT/worker-started"
    mkdir -p "$STAGED_VENV" "$FAKEBIN"
    : > "$COMMAND_LOG"

    cat > "$FAKEBIN/systemctl" <<'EOF'
#!/usr/bin/env bash
echo "systemctl $*" >> "$COMMAND_LOG"
if [[ "$*" == "stop promptgrimoire-worker.service" && "${FAIL_WORKER_STOP:-0}" == 1 ]]; then
    exit 1
fi
if [[ "$*" == "start promptgrimoire-worker.service" ]]; then
    touch "$WORKER_STARTED"
fi
if [[ "$*" == "is-active --quiet promptgrimoire-worker.service" ]]; then
    [[ -e "$WORKER_STARTED" ]]
    exit
fi
EOF
    cat > "$FAKEBIN/curl" <<'EOF'
#!/usr/bin/env bash
echo "curl $*" >> "$COMMAND_LOG"
[[ "${FAIL_HEALTH:-0}" != 1 ]]
EOF
    cat > "$FAKEBIN/socat" <<'EOF'
#!/usr/bin/env bash
read -r command
echo "socat $command" >> "$COMMAND_LOG"
EOF
    cat > "$FAKEBIN/sleep" <<'EOF'
#!/usr/bin/env bash
echo "sleep $*" >> "$COMMAND_LOG"
EOF
    chmod +x "$FAKEBIN/systemctl" "$FAKEBIN/curl" "$FAKEBIN/socat" "$FAKEBIN/sleep"
}

run_runtime() {
    # Variables intentionally expand inside the child bash.
    # shellcheck disable=SC2016
    run env \
        PATH="$FAKEBIN:$PATH" \
        APP_DIR="$APP_DIR" \
        VENV_ROOT="$VENV_ROOT" \
        STAGED_VENV="$STAGED_VENV" \
        EXPECTED_COMMIT="$EXPECTED_COMMIT" \
        COMMAND_LOG="$COMMAND_LOG" \
        WORKER_STARTED="$WORKER_STARTED" \
        FAIL_WORKER_STOP="${FAIL_WORKER_STOP:-0}" \
        FAIL_HEALTH="${FAIL_HEALTH:-0}" \
        SOCK="$TEST_ROOT/haproxy.sock" \
        HEALTHZ=http://127.0.0.1:8080/healthz \
        MAX_WAIT=1 \
        bash -c '
            set -euo pipefail
            source "$1"
            step() { echo "==> $1"; }
            worker_stopped=false
            app_stopped=false
            venv_switched=false
            haproxy_touched=true
            previous_venv=""
            elapsed=0
            restart_runtime
        ' _ "$HELPERS"
}

@test "runtime transition succeeds from a legacy environment directory" {
    mkdir -p "$APP_DIR/.venv/bin"

    run_runtime

    [ "$status" -eq 0 ]
    [ "$(readlink "$APP_DIR/.venv")" = ".venvs/$EXPECTED_COMMIT" ]
    legacy=$(find "$VENV_ROOT" -maxdepth 1 -type d -name 'legacy-*' -print -quit)
    [ -n "$legacy" ]
    grep -q 'systemctl start promptgrimoire.service' "$COMMAND_LOG"
    grep -q 'systemctl start promptgrimoire-worker.service' "$COMMAND_LOG"
    grep -q 'socat set server be_promptgrimoire/app state ready' "$COMMAND_LOG"
}

@test "runtime transition replaces an existing environment symlink" {
    mkdir -p "$VENV_ROOT/previous"
    ln -s .venvs/previous "$APP_DIR/.venv"

    run_runtime

    [ "$status" -eq 0 ]
    [ "$(readlink "$APP_DIR/.venv")" = ".venvs/$EXPECTED_COMMIT" ]
    legacy=$(find "$VENV_ROOT" -maxdepth 1 -type d -name 'legacy-*' -print -quit)
    [ -z "$legacy" ]
}

@test "worker stop failure aborts before maintenance or environment mutation" {
    mkdir -p "$VENV_ROOT/previous"
    ln -s .venvs/previous "$APP_DIR/.venv"
    FAIL_WORKER_STOP=1

    run_runtime

    [ "$status" -ne 0 ]
    [ "$(readlink "$APP_DIR/.venv")" = ".venvs/previous" ]
    run grep -q '^socat ' "$COMMAND_LOG"
    [ "$status" -ne 0 ]
    run grep -q 'systemctl stop promptgrimoire.service' "$COMMAND_LOG"
    [ "$status" -ne 0 ]
}

@test "failed health remains in maintenance with the candidate selected" {
    mkdir -p "$VENV_ROOT/previous"
    ln -s .venvs/previous "$APP_DIR/.venv"
    FAIL_HEALTH=1

    run_runtime

    [ "$status" -ne 0 ]
    runtime_output=$output
    [ "$(readlink "$APP_DIR/.venv")" = ".venvs/$EXPECTED_COMMIT" ]
    grep -q 'socat set server be_promptgrimoire/app state maint' "$COMMAND_LOG"
    run grep -q 'socat set server be_promptgrimoire/app state ready' "$COMMAND_LOG"
    [ "$status" -ne 0 ]
    run grep -q 'systemctl start promptgrimoire-worker.service' "$COMMAND_LOG"
    [ "$status" -ne 0 ]
    [[ "$runtime_output" == *"Manual recovery:"* ]]
}
