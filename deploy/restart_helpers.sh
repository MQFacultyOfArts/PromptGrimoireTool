#!/usr/bin/env bash
# Testable validation and service-transition helpers for deploy/restart.sh.

read_required_env_value() {
    local env_file=$1
    local key=$2
    local -a values=()

    [[ -r "$env_file" ]] || return 1
    [[ "$key" =~ ^[A-Z0-9_]+$ ]] || return 1
    mapfile -t values < <(sed -n "s/^${key}=//p" "$env_file")
    [[ ${#values[@]} -eq 1 && -n "${values[0]}" ]] || return 1
    printf '%s\n' "${values[0]}"
}

parse_json_count() {
    local json=$1
    local field=$2

    jq -er --arg field "$field" '
        .[$field]
        | if type == "number" and . >= 0 and floor == . then
            tostring
          else
            error("required count is not a non-negative integer")
          end
    ' <<< "$json"
}

restart_runtime() {
    step "Stopping export worker (graceful drain)"
    if ! systemctl stop promptgrimoire-worker.service; then
        echo "ABORT: promptgrimoire-worker failed to stop" >&2
        return 1
    fi
    if systemctl is-active --quiet promptgrimoire-worker.service; then
        echo "ABORT: promptgrimoire-worker remains active after stop" >&2
        return 1
    fi
    worker_stopped=true

    step "HAProxy → maintenance mode"
    echo "set server be_promptgrimoire/app state maint" | socat stdio "$SOCK"

    step "Stopping promptgrimoire"
    systemctl stop promptgrimoire.service
    app_stopped=true

    local nicegui_storage="$APP_DIR/.nicegui"
    step "Pruning stale NiceGUI storage files"
    if [[ -d "$nicegui_storage" ]]; then
        local stale_count
        stale_count=$(find "$nicegui_storage" -name "storage-user-*.json" -mtime +7 | wc -l)
        if [[ "$stale_count" -gt 0 ]]; then
            find "$nicegui_storage" -name "storage-user-*.json" -mtime +7 -delete
            echo "  Removed $stale_count stale storage files"
        else
            echo "  No stale storage files to remove"
        fi
    else
        echo "  No .nicegui directory found — skipping"
    fi

    previous_venv=$(readlink -f "$APP_DIR/.venv")
    ln -s ".venvs/$EXPECTED_COMMIT" "$APP_DIR/.venv.next"
    if [[ ! -L "$APP_DIR/.venv" ]]; then
        local legacy_venv
        legacy_venv="$VENV_ROOT/legacy-$(date +%Y%m%d-%H%M%S)-$$"
        venv_switched=true
        mv "$APP_DIR/.venv" "$legacy_venv"
        previous_venv=$legacy_venv
    fi
    mv -Tf "$APP_DIR/.venv.next" "$APP_DIR/.venv"
    venv_switched=true

    step "Starting promptgrimoire"
    if ! systemctl start promptgrimoire.service; then
        echo "ERROR: promptgrimoire failed to start" >&2
        return 1
    fi
    # Read by restart.sh's EXIT trap.
    # shellcheck disable=SC2034
    app_stopped=false

    step "Waiting for /healthz (max ${MAX_WAIT}s)"
    elapsed=0
    until curl -sf "$HEALTHZ" > /dev/null 2>&1; do
        sleep 1
        elapsed=$((elapsed + 1))
        if [[ $elapsed -ge $MAX_WAIT ]]; then
            echo "ERROR: /healthz not responding after ${MAX_WAIT}s" >&2
            echo "Server may be down — HAProxy still in maintenance mode" >&2
            echo "Manual recovery: echo 'set server be_promptgrimoire/app state ready' | socat stdio $SOCK" >&2
            return 1
        fi
    done

    step "Starting export worker"
    if ! systemctl start promptgrimoire-worker.service; then
        echo "ERROR: promptgrimoire-worker failed to start" >&2
        return 1
    fi
    if ! systemctl is-active --quiet promptgrimoire-worker.service; then
        echo "ERROR: promptgrimoire-worker failed to start" >&2
        return 1
    fi
    # Read by restart.sh's EXIT trap.
    # shellcheck disable=SC2034
    worker_stopped=false

    step "HAProxy → ready"
    echo "set server be_promptgrimoire/app state ready" | socat stdio "$SOCK"
    # Read by restart.sh's EXIT trap.
    # shellcheck disable=SC2034
    haproxy_touched=false
    # shellcheck disable=SC2034
    venv_switched=false

    echo "Deploy complete (${elapsed}s startup; previous environment: $previous_venv)"
}
