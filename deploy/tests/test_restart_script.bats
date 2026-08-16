#!/usr/bin/env bats

RESTART="$BATS_TEST_DIRNAME/../restart.sh"
EXPECTED_COMMIT=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa

setup() {
    TEST_ROOT="$BATS_TEST_TMPDIR/script-$BATS_TEST_NUMBER"
    APP_DIR="$TEST_ROOT/app"
    FAKEBIN="$TEST_ROOT/bin"
    COMMAND_LOG="$TEST_ROOT/commands.log"
    mkdir -p "$APP_DIR/deploy" "$APP_DIR/.venvs/previous/bin" "$FAKEBIN"
    ln -s .venvs/previous "$APP_DIR/.venv"
    : > "$APP_DIR/.venvs/previous/bin/python"
    chmod +x "$APP_DIR/.venvs/previous/bin/python"
    cp "$BATS_TEST_DIRNAME/../restart_helpers.sh" "$APP_DIR/deploy/"
    cp "$BATS_TEST_DIRNAME/../promptgrimoire-worker.service" "$APP_DIR/deploy/"
    : > "$APP_DIR/deploy/503.http"
    cat > "$APP_DIR/.env" <<'EOF'
FEATURES__WORKER_IN_PROCESS=false
EXPORT__MAX_CONCURRENT_COMPILATIONS=1
DATABASE__USE_NULL_POOL=false
ADMIN__PRE_RESTART_TOKEN=test-token
EOF
    : > "$COMMAND_LOG"

    make_shim sudo 'shift 2; exec "$@"'
    make_shim git '
        [[ " $* " == *" rev-parse HEAD "* ]] && { echo "$EXPECTED_COMMIT"; exit; }
        [[ " $* " == *" status --porcelain "* ]] && exit
    '
    make_shim uv '
        echo "uv $*" >> "$COMMAND_LOG"
        if [[ " $* " == *" sync --locked"* ]]; then
            mkdir -p "$UV_PROJECT_ENVIRONMENT/bin"
            : > "$UV_PROJECT_ENVIRONMENT/bin/python"
            chmod +x "$UV_PROJECT_ENVIRONMENT/bin/python"
        elif [[ " $* " == *"grimoire test all"* && "${FAIL_TEST_GATE:-0}" == 1 ]]; then
            exit 1
        fi
    '
    make_shim systemctl '
        echo "systemctl $*" >> "$COMMAND_LOG"
        case "$*" in
            "list-unit-files --no-legend promptgrimoire-worker.service")
                echo "promptgrimoire-worker.service enabled" ;;
            "show promptgrimoire.service --property=ExecStart --value")
                echo "/opt/uv run --locked --no-sync python run_prod.py" ;;
            "start promptgrimoire.service")
                [[ "${FAIL_APP_START:-0}" != 1 ]] ;;
            "is-active --quiet promptgrimoire-worker.service")
                [[ ! -e "$TEST_ROOT/worker-stopped" ]] ;;
            "stop promptgrimoire-worker.service")
                : > "$TEST_ROOT/worker-stopped" ;;
            "start promptgrimoire-worker.service")
                rm -f "$TEST_ROOT/worker-stopped" ;;
        esac
    '
    make_shim install '
        echo "install $*" >> "$COMMAND_LOG"
        if [[ "$1" == -d ]]; then
            mkdir -p "${@: -1}"
        fi
    '
    make_shim cp 'echo "cp $*" >> "$COMMAND_LOG"'
    make_shim npm 'echo "npm $*" >> "$COMMAND_LOG"'
    make_shim curl '
        echo "curl $*" >> "$COMMAND_LOG"
        if [[ "$*" == *"/api/pre-restart"* ]]; then
            echo "{\"initial_count\":0}"
        elif [[ "$*" == *"/healthz"* ]]; then
            [[ "${FAIL_HEALTH:-0}" != 1 ]]
        fi
    '
    make_shim socat 'read -r command; echo "socat $command" >> "$COMMAND_LOG"'
    make_shim sleep ':'
    make_shim flock ':'
}

make_shim() {
    local name=$1 body=$2
    {
        echo '#!/usr/bin/env bash'
        echo 'set -euo pipefail'
        printf '%s\n' "$body"
    } > "$FAKEBIN/$name"
    chmod +x "$FAKEBIN/$name"
}

run_restart() {
    run env \
        PATH="$FAKEBIN:$PATH" \
        APP_DIR="$APP_DIR" \
        UV="$FAKEBIN/uv" \
        PG_PATH="$FAKEBIN:$PATH" \
        DEPLOY_LOCK="$TEST_ROOT/deploy.lock" \
        SOCK="$TEST_ROOT/haproxy.sock" \
        MAX_WAIT=1 \
        RESTART_TEST_MODE=1 \
        EXPECTED_COMMIT="$EXPECTED_COMMIT" \
        COMMAND_LOG="$COMMAND_LOG" \
        TEST_ROOT="$TEST_ROOT" \
        FAIL_TEST_GATE="${FAIL_TEST_GATE:-0}" \
        FAIL_APP_START="${FAIL_APP_START:-0}" \
        FAIL_HEALTH="${FAIL_HEALTH:-0}" \
        bash "$RESTART" --expected-commit "$EXPECTED_COMMIT"
}

line_of() {
    grep -n -m1 "$1" "$COMMAND_LOG" | cut -d: -f1
}

@test "complete restart orders gate, mutation, health, worker, and ready" {
    run_restart

    [ "$status" -eq 0 ]
    [ "$(readlink "$APP_DIR/.venv")" = ".venvs/$EXPECTED_COMMIT" ]
    [ "$(line_of 'grimoire test all')" -lt "$(line_of 'stop promptgrimoire-worker')" ]
    [ "$(line_of 'stop promptgrimoire-worker')" -lt "$(line_of 'stop promptgrimoire.service')" ]
    [ "$(line_of 'start promptgrimoire.service')" -lt "$(line_of '/healthz')" ]
    [ "$(line_of '/healthz')" -lt "$(line_of 'start promptgrimoire-worker')" ]
    [ "$(line_of 'start promptgrimoire-worker')" -lt "$(line_of 'state ready')" ]
}

@test "failed test gate leaves live services and environment untouched" {
    FAIL_TEST_GATE=1
    run_restart

    [ "$status" -ne 0 ]
    [ "$(readlink "$APP_DIR/.venv")" = ".venvs/previous" ]
    ! grep -q 'stop promptgrimoire-worker' "$COMMAND_LOG"
    ! grep -q '^socat ' "$COMMAND_LOG"
}

@test "application start failure exercises EXIT recovery report" {
    FAIL_APP_START=1
    run_restart

    [ "$status" -ne 0 ]
    [[ "$output" == *"HAProxy may be in drain or maintenance mode."* ]]
    [[ "$output" == *"The application remains stopped."* ]]
    [[ "$output" == *"The environment transition began"* ]]
    ! grep -q 'state ready' "$COMMAND_LOG"
}

@test "health failure keeps maintenance and exercises EXIT recovery report" {
    FAIL_HEALTH=1
    run_restart

    [ "$status" -ne 0 ]
    [[ "$output" == *"HAProxy may be in drain or maintenance mode."* ]]
    ! grep -q 'start promptgrimoire-worker.service' "$COMMAND_LOG"
    ! grep -q 'state ready' "$COMMAND_LOG"
}
