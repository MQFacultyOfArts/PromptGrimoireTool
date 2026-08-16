#!/usr/bin/env bash
# deploy/restart.sh — Zero-downtime deploy for PromptGrimoire
#
# Usage (as root):
#   ./deploy/restart.sh --expected-commit <40-char-sha>
#   ./deploy/restart.sh --expected-commit <40-char-sha> --skip-tests
#
# Steps:
#   1. Verify the clean checkout matches the pinned candidate
#   2. Build an exact staged Python environment and run npm ci
#   3. test gates (optional only for declared emergencies; e-stop on failure)
#   4. Update installed worker systemd unit
#   5. Update HAProxy 503 page
#   6. Application-level pre-restart (flush CRDT, navigate clients to /restarting)
#   7. HAProxy drain (stop new connections, let in-flight finish)
#   8. Wait for application-level connections to drain
#   9. Stop worker gracefully
#  10. HAProxy maintenance mode (serves friendly 503 with jittered reload)
#  11. Stop the app, atomically select the staged environment, and start it
#  12. Wait for /healthz
#  13. Start worker (after app is healthy)
#  14. HAProxy back to ready
set -euo pipefail

SOCK=${SOCK:-/run/haproxy/admin.sock}
APP_DIR=${APP_DIR:-/opt/promptgrimoire}
UV=${UV:-/home/promptgrimoire/.local/bin/uv}
# PATH for sudo -u promptgrimoire commands (uv, TinyTeX binaries)
PG_PATH=${PG_PATH:-"/home/promptgrimoire/.local/bin:/home/promptgrimoire/.TinyTeX/bin/x86_64-linux:/usr/local/bin:/usr/bin:/bin"}
HEALTHZ=${HEALTHZ:-http://127.0.0.1:8080/healthz}
MAX_WAIT=${MAX_WAIT:-60}
DEPLOY_LOCK=${DEPLOY_LOCK:-/run/lock/promptgrimoire-deploy.lock}

DRAIN_TIMEOUT=${DRAIN_TIMEOUT:-30}  # Max seconds to wait for app-level connections to drain

# Must be root (systemctl, socat to admin socket)
if [[ $EUID -ne 0 && ${RESTART_TEST_MODE:-0} != 1 ]]; then
    echo "ERROR: run as root" >&2
    exit 1
fi

SKIP_TESTS=false
EXPECTED_COMMIT=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --expected-commit)
            if [[ $# -lt 2 ]]; then
                echo "ERROR: --expected-commit requires a full commit SHA" >&2
                exit 2
            fi
            EXPECTED_COMMIT=$2
            shift 2
            ;;
        --skip-tests)
            SKIP_TESTS=true
            shift
            ;;
        *)
            echo "ERROR: unknown argument: $1" >&2
            exit 2
            ;;
    esac
done

if [[ ! "$EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]; then
    echo "ERROR: --expected-commit must be a full 40-character lowercase SHA" >&2
    exit 2
fi

# sudo preserves the caller's cwd. Pin it before changing user so service-user
# tools never inherit an inaccessible operator home directory.
cd "$APP_DIR"
source "$APP_DIR/deploy/restart_helpers.sh"

exec 9>"$DEPLOY_LOCK"
if ! flock --exclusive --nonblock 9; then
    echo "ABORT: another deployment process holds $DEPLOY_LOCK" >&2
    exit 1
fi

VENV_ROOT="$APP_DIR/.venvs"
STAGED_VENV="$VENV_ROOT/$EXPECTED_COMMIT"

step() { echo "==> $1"; }

RECOVERY="echo 'set server be_promptgrimoire/app state ready' | socat stdio $SOCK"

# After steps 1-3 fail: server is still running, nothing to recover.
# After steps 5-12 fail: HAProxy may be in drain/maint. Print recovery.
haproxy_touched=false
worker_stopped=false
app_stopped=false
venv_switched=false
previous_venv=""
cleanup() {
    status=$?
    if [[ "$status" -eq 0 ]]; then
        return
    fi
    if [[ "$haproxy_touched" == "true" ]]; then
        echo "" >&2
        echo "HAProxy may be in drain or maintenance mode." >&2
        echo "To restore normal traffic:" >&2
        echo "  $RECOVERY" >&2
    fi
    if [[ "$worker_stopped" == "true" ]]; then
        echo "The export worker remains stopped." >&2
        echo "After the application is healthy, restart it with:" >&2
        echo "  systemctl start promptgrimoire-worker.service" >&2
    fi
    if [[ "$app_stopped" == "true" ]]; then
        echo "The application remains stopped." >&2
    fi
    if [[ "$venv_switched" == "true" ]]; then
        echo "The environment transition began (previous: $previous_venv; candidate: $STAGED_VENV)." >&2
        echo "Keep HAProxy in maintenance until the application is healthy or the environment is rolled back." >&2
    fi
}
trap cleanup EXIT

# 1. Verify the exact candidate selected by the operator. The script does not
# fetch or pull: origin/main can move after review, but the deployed tree cannot.
step "Verifying pinned candidate"
CURRENT_COMMIT=$(sudo -u promptgrimoire env PATH="$PG_PATH" \
    git -C "$APP_DIR" rev-parse HEAD)
if [[ "$CURRENT_COMMIT" != "$EXPECTED_COMMIT" ]]; then
    echo "ERROR: checkout $CURRENT_COMMIT does not match expected $EXPECTED_COMMIT" >&2
    exit 1
fi
if [[ -n "$(sudo -u promptgrimoire env PATH="$PG_PATH" git -C "$APP_DIR" status --porcelain)" ]]; then
    echo "ERROR: production worktree is not clean" >&2
    exit 1
fi

# Production requires one standalone export worker and no in-process worker.
# Validate this before dependency sync or any live-service mutation.
step "Verifying production worker topology"
if ! worker_units=$(systemctl list-unit-files --no-legend promptgrimoire-worker.service); then
    echo "ABORT: could not query promptgrimoire-worker.service" >&2
    exit 1
fi
if ! grep -qE '^promptgrimoire-worker\.service[[:space:]]' <<< "$worker_units"; then
    echo "ABORT: required promptgrimoire-worker.service is not installed" >&2
    exit 1
fi

require_setting() {
    local key=$1
    local expected=$2
    local actual

    if ! actual=$(read_required_env_value "$APP_DIR/.env" "$key"); then
        echo "ABORT: $key must be defined exactly once in $APP_DIR/.env" >&2
        exit 1
    fi
    if [[ "$actual" != "$expected" ]]; then
        echo "ABORT: $key must be $expected for the production worker topology" >&2
        exit 1
    fi
}

require_setting FEATURES__WORKER_IN_PROCESS false
require_setting EXPORT__MAX_CONCURRENT_COMPILATIONS 1
require_setting DATABASE__USE_NULL_POOL false
if ! PRE_RESTART_TOKEN=$(read_required_env_value "$APP_DIR/.env" ADMIN__PRE_RESTART_TOKEN); then
    echo "ABORT: ADMIN__PRE_RESTART_TOKEN must be defined exactly once and non-empty" >&2
    exit 1
fi

if [[ ! -x "$APP_DIR/.venv/bin/python" ]]; then
    echo "ABORT: current application environment has no executable .venv/bin/python" >&2
    exit 1
fi
current_venv=$(readlink -f "$APP_DIR/.venv")
if [[ "$current_venv" == "$STAGED_VENV" ]]; then
    echo "ABORT: commit $EXPECTED_COMMIT is already the selected Python environment" >&2
    exit 1
fi
if [[ -e "$APP_DIR/.venv.next" || -L "$APP_DIR/.venv.next" ]]; then
    echo "ABORT: stale $APP_DIR/.venv.next must be investigated before deployment" >&2
    exit 1
fi

app_exec=$(systemctl show promptgrimoire.service --property=ExecStart --value)
if [[ "$app_exec" != *"/uv run --locked --no-sync python run_prod.py"* ]]; then
    echo "ABORT: promptgrimoire.service must use uv run --locked --no-sync" >&2
    exit 1
fi

# 2. Build an exact candidate environment without mutating the live .venv.
step "Building staged Python environment with uv sync --locked"
install -d -m 0755 -o promptgrimoire -g promptgrimoire "$VENV_ROOT"
sudo -u promptgrimoire env PATH="$PG_PATH" UV_PROJECT_ENVIRONMENT="$STAGED_VENV" \
    "$UV" --directory "$APP_DIR" sync --locked

# 3. Tests (e-stop)
if [[ "$SKIP_TESTS" == "false" ]]; then
    step "Installing locked JS test dependencies"
    sudo -u promptgrimoire env HOME=/home/promptgrimoire PATH="$PG_PATH" \
        npm --prefix "$APP_DIR" ci --include=dev

    step "Running unit tests (e-stop — will abort deploy on failure)"
    if ! sudo -u promptgrimoire env PATH="$PG_PATH" UV_PROJECT_ENVIRONMENT="$STAGED_VENV" \
        "$UV" --directory "$APP_DIR" run --locked --no-sync grimoire test all; then
        echo "ABORT: test gate failed — not restarting" >&2
        exit 1
    fi
    step "Smoke-testing PDF export (CJK + emoji + annotations)"
    if ! sudo -u promptgrimoire env PATH="$PG_PATH" UV_PROJECT_ENVIRONMENT="$STAGED_VENV" \
        "$UV" --directory "$APP_DIR" run --locked --no-sync grimoire test smoke-export; then
        echo "ABORT: PDF smoke test failed — not restarting" >&2
        exit 1
    fi
else
    step "Skipping tests (--skip-tests)"
fi

step "Revalidating tested candidate"
CURRENT_COMMIT=$(sudo -u promptgrimoire env PATH="$PG_PATH" \
    git -C "$APP_DIR" rev-parse HEAD)
if [[ "$CURRENT_COMMIT" != "$EXPECTED_COMMIT" ]]; then
    echo "ABORT: checkout changed after testing" >&2
    exit 1
fi
if [[ -n "$(sudo -u promptgrimoire env PATH="$PG_PATH" git -C "$APP_DIR" status --porcelain)" ]]; then
    echo "ABORT: production worktree changed after testing" >&2
    exit 1
fi

# 4. Refresh the mandatory worker installation from the tracked unit file.
step "Updating export worker systemd unit"
install -m 0644 "$APP_DIR/deploy/promptgrimoire-worker.service" /etc/systemd/system/promptgrimoire-worker.service
systemctl daemon-reload

# 5. Update HAProxy 503 page (picks up jittered reload, etc.)
step "Updating HAProxy 503 page"
cp "$APP_DIR/deploy/503.http" /etc/haproxy/errors/503.http

# 6. Application-level pre-restart (flush CRDT state, navigate clients)
step "Triggering application-level pre-restart"
if ! pre_restart_response=$(curl -sfS -X POST \
        -H "Authorization: Bearer $PRE_RESTART_TOKEN" \
        http://127.0.0.1:8080/api/pre-restart); then
    echo "ABORT: pre-restart flush endpoint failed" >&2
    exit 1
fi
if ! initial_count=$(parse_json_count "$pre_restart_response" initial_count); then
    echo "ABORT: pre-restart response has no valid initial_count" >&2
    exit 1
fi
echo "  Initial connected clients: $initial_count"

# 7. Drain — stop sending new connections, let in-flight requests finish
haproxy_touched=true
step "HAProxy → drain (new connections blocked, in-flight finishing)"
echo "set server be_promptgrimoire/app state drain" | socat stdio "$SOCK"

# 8. Wait for application-level connections to drain
if [[ "$initial_count" -gt 0 ]]; then
    threshold=$(( (initial_count * 5 + 99) / 100 ))  # ceil(5%)
    step "Waiting for connections to drain (threshold: ≤${threshold}, timeout: ${DRAIN_TIMEOUT}s)"
    drain_elapsed=0
    while [[ $drain_elapsed -lt $DRAIN_TIMEOUT ]]; do
        sleep 1
        drain_elapsed=$((drain_elapsed + 1))
        if ! connection_response=$(curl -sfS \
            -H "Authorization: Bearer $PRE_RESTART_TOKEN" \
            http://127.0.0.1:8080/api/connection-count); then
            echo "ABORT: connection-count endpoint failed during drain" >&2
            exit 1
        fi
        if ! current=$(parse_json_count "$connection_response" count); then
            echo "ABORT: connection-count response has no valid count" >&2
            exit 1
        fi
        if [[ "$current" -le "$threshold" ]]; then
            echo "  Drained to $current connections (≤${threshold}) after ${drain_elapsed}s"
            sleep 2  # Grace period
            break
        fi
        echo "  ${drain_elapsed}s: $current connections remaining"
    done
    if [[ $drain_elapsed -ge $DRAIN_TIMEOUT ]]; then
        echo "  Timeout after ${DRAIN_TIMEOUT}s — proceeding with restart"
    fi
fi

# 9-14. Stop, switch environment, start, verify health, and restore traffic.
restart_runtime
