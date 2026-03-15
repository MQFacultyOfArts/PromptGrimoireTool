#!/usr/bin/env bash
# deploy/restart.sh — Zero-downtime deploy for PromptGrimoire
#
# Usage (as root):
#   ./deploy/restart.sh           # full deploy: pull, sync, test, restart
#   ./deploy/restart.sh --skip-tests   # skip unit tests (faster)
#
# Steps:
#   1. git pull (as promptgrimoire)
#   2. uv sync --no-dev (as promptgrimoire)
#   3. unit tests (optional, e-stop on failure)
#   4. HAProxy drain (stop new connections, let in-flight finish)
#   5. Wait for active connections to drain
#   6. HAProxy maintenance mode (serves friendly 503)
#   7. systemctl restart
#   8. Wait for /healthz
#   9. HAProxy back to ready
set -euo pipefail

SOCK=/run/haproxy/admin.sock
APP_DIR=/opt/promptgrimoire
UV=/home/promptgrimoire/.local/bin/uv
HEALTHZ=http://127.0.0.1:8080/healthz
MAX_WAIT=60
DRAIN_WAIT=10

SKIP_TESTS=false
if [[ "${1:-}" == "--skip-tests" ]]; then
    SKIP_TESTS=true
fi

# Must be root (systemctl, socat to admin socket)
if [[ $EUID -ne 0 ]]; then
    echo "ERROR: run as root" >&2
    exit 1
fi

step() { echo "==> $1"; }

RECOVERY="echo 'set server be_promptgrimoire/app state ready' | socat stdio $SOCK"

# After steps 1-3 fail: server is still running, nothing to recover.
# After steps 4-9 fail: HAProxy may be in drain/maint. Print recovery.
haproxy_touched=false
cleanup() {
    if [[ "$haproxy_touched" == "true" ]]; then
        echo "" >&2
        echo "HAProxy may be in drain or maintenance mode." >&2
        echo "To restore normal traffic:" >&2
        echo "  $RECOVERY" >&2
    fi
}
trap cleanup EXIT

# 1. Pull
step "git pull"
sudo -u promptgrimoire git -C "$APP_DIR" pull --rebase

# 2. Sync dependencies
step "uv sync --no-dev"
sudo -u promptgrimoire "$UV" --directory "$APP_DIR" sync --no-dev

# 3. Unit tests (e-stop)
if [[ "$SKIP_TESTS" == "false" ]]; then
    step "Running unit tests (e-stop — will abort deploy on failure)"
    if ! sudo -u promptgrimoire "$UV" --directory "$APP_DIR" run grimoire test all; then
        echo "ABORT: unit tests failed — not restarting" >&2
        exit 1
    fi
else
    step "Skipping tests (--skip-tests)"
fi

# 4. Drain — stop sending new connections, let in-flight requests finish
haproxy_touched=true
step "HAProxy → drain (new connections blocked, in-flight finishing)"
echo "set server be_promptgrimoire/app state drain" | socat stdio "$SOCK"

# 5. Wait for connections to drain
#    Check active sessions on the backend; once zero (or timeout), proceed.
step "Waiting for active connections to drain (max ${DRAIN_WAIT}s)"
drain_elapsed=0
while [[ $drain_elapsed -lt $DRAIN_WAIT ]]; do
    sessions=$(echo "show stat" | socat stdio "$SOCK" \
        | awk -F, '/^be_promptgrimoire,app,/ { print $5 }')
    if [[ "${sessions:-0}" -eq 0 ]]; then
        echo "    Drained after ${drain_elapsed}s"
        break
    fi
    echo "    ${sessions} active sessions, waiting..."
    sleep 1
    drain_elapsed=$((drain_elapsed + 1))
done
if [[ $drain_elapsed -ge $DRAIN_WAIT ]]; then
    echo "    Drain timeout — proceeding with ${sessions:-?} sessions still active"
fi

# 6. Maintenance mode (serves friendly 503 page)
step "HAProxy → maintenance mode"
echo "set server be_promptgrimoire/app state maint" | socat stdio "$SOCK"

# 7. Restart
step "Restarting promptgrimoire"
systemctl restart promptgrimoire

# 8. Wait for healthy
step "Waiting for /healthz (max ${MAX_WAIT}s)"
elapsed=0
until curl -sf "$HEALTHZ" > /dev/null 2>&1; do
    sleep 1
    elapsed=$((elapsed + 1))
    if [[ $elapsed -ge $MAX_WAIT ]]; then
        echo "ERROR: /healthz not responding after ${MAX_WAIT}s" >&2
        echo "Server may be down — HAProxy still in maintenance mode" >&2
        echo "Manual recovery: echo 'set server be_promptgrimoire/app state ready' | socat stdio $SOCK" >&2
        exit 1
    fi
done

# 9. Back to ready
step "HAProxy → ready"
echo "set server be_promptgrimoire/app state ready" | socat stdio "$SOCK"
haproxy_touched=false

echo "Deploy complete (${elapsed}s startup)"
