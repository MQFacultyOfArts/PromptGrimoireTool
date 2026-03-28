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
#   4. Update HAProxy 503 page
#   5. Application-level pre-restart (flush CRDT, navigate clients to /restarting)
#   6. HAProxy drain (stop new connections, let in-flight finish)
#   7. Wait for application-level connections to drain
#   8. HAProxy maintenance mode (serves friendly 503 with jittered reload)
#   9. systemctl restart
#  10. Wait for /healthz
#  11. HAProxy back to ready
set -euo pipefail

SOCK=/run/haproxy/admin.sock
APP_DIR=/opt/promptgrimoire
UV=/home/promptgrimoire/.local/bin/uv
# PATH for sudo -u promptgrimoire commands (uv, TinyTeX binaries)
PG_PATH="/home/promptgrimoire/.local/bin:/home/promptgrimoire/.TinyTeX/bin/x86_64-linux:/usr/local/bin:/usr/bin:/bin"
HEALTHZ=http://127.0.0.1:8080/healthz
MAX_WAIT=60

# Application-level drain token (for pre-restart + connection-count endpoints)
PRE_RESTART_TOKEN=$(grep '^ADMIN__PRE_RESTART_TOKEN=' "$APP_DIR/.env" 2>/dev/null | cut -d= -f2- || true)
DRAIN_TIMEOUT=${DRAIN_TIMEOUT:-30}  # Max seconds to wait for app-level connections to drain

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
# After steps 4-11 fail: HAProxy may be in drain/maint. Print recovery.
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
sudo -u promptgrimoire env PATH="$PG_PATH" git -C "$APP_DIR" pull --rebase

# 2. Sync dependencies
step "uv sync"
sudo -u promptgrimoire env PATH="$PG_PATH" "$UV" --directory "$APP_DIR" sync

# 2b. Prune stale NiceGUI user-storage files (> 7 days old)
NICEGUI_STORAGE="$APP_DIR/.nicegui"
step "Pruning stale NiceGUI storage files"
if [[ -d "$NICEGUI_STORAGE" ]]; then
    stale_count=$(find "$NICEGUI_STORAGE" -name "storage-user-*.json" -mtime +7 | wc -l)
    if [[ "$stale_count" -gt 0 ]]; then
        find "$NICEGUI_STORAGE" -name "storage-user-*.json" -mtime +7 -delete
        echo "  Removed $stale_count stale storage files"
    else
        echo "  No stale storage files to remove"
    fi
else
    echo "  No .nicegui directory found — skipping"
fi

# 3. Tests (e-stop)
if [[ "$SKIP_TESTS" == "false" ]]; then
    step "Running unit tests (e-stop — will abort deploy on failure)"
    if ! grimoire-run grimoire test all; then
        echo "ABORT: unit tests failed — not restarting" >&2
        exit 1
    fi
    step "Smoke-testing PDF export (CJK + emoji + annotations)"
    if ! grimoire-run grimoire test smoke-export; then
        echo "ABORT: PDF smoke test failed — not restarting" >&2
        exit 1
    fi
else
    step "Skipping tests (--skip-tests)"
fi

# 4. Update HAProxy 503 page (picks up jittered reload, etc.)
step "Updating HAProxy 503 page"
cp "$APP_DIR/deploy/503.http" /etc/haproxy/errors/503.http

# 5. Application-level pre-restart (flush CRDT state, navigate clients)
step "Triggering application-level pre-restart"
if [[ -z "$PRE_RESTART_TOKEN" ]]; then
    echo "  WARNING: ADMIN__PRE_RESTART_TOKEN not set in .env — skipping pre-restart" >&2
    initial_count=0
else
    pre_restart_response=$(curl -sf -X POST \
        -H "Authorization: Bearer $PRE_RESTART_TOKEN" \
        http://127.0.0.1:8080/api/pre-restart 2>&1) || {
        echo "  WARNING: pre-restart endpoint failed — proceeding with restart" >&2
        pre_restart_response=""
    }
    initial_count=$(echo "$pre_restart_response" | grep -o '"initial_count":[0-9]*' | cut -d: -f2 || true)
    initial_count=${initial_count:-0}
    echo "  Initial connected clients: $initial_count"
fi

# 6. Drain — stop sending new connections, let in-flight requests finish
haproxy_touched=true
step "HAProxy → drain (new connections blocked, in-flight finishing)"
echo "set server be_promptgrimoire/app state drain" | socat stdio "$SOCK"

# 7. Wait for application-level connections to drain
if [[ "$initial_count" -gt 0 ]] && [[ -n "$PRE_RESTART_TOKEN" ]]; then
    threshold=$(( (initial_count * 5 + 99) / 100 ))  # ceil(5%)
    step "Waiting for connections to drain (threshold: ≤${threshold}, timeout: ${DRAIN_TIMEOUT}s)"
    drain_elapsed=0
    while [[ $drain_elapsed -lt $DRAIN_TIMEOUT ]]; do
        sleep 1
        drain_elapsed=$((drain_elapsed + 1))
        current=$(curl -sf \
            -H "Authorization: Bearer $PRE_RESTART_TOKEN" \
            http://127.0.0.1:8080/api/connection-count 2>/dev/null \
            | grep -o '"count":[0-9]*' | cut -d: -f2 || true)
        current=${current:-0}
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

# 8. Maintenance mode (serves friendly 503 page)
step "HAProxy → maintenance mode"
echo "set server be_promptgrimoire/app state maint" | socat stdio "$SOCK"

# 9. Restart
step "Restarting promptgrimoire"
systemctl restart promptgrimoire

# 10. Wait for healthy
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

# 11. Back to ready
step "HAProxy → ready"
echo "set server be_promptgrimoire/app state ready" | socat stdio "$SOCK"
haproxy_touched=false

echo "Deploy complete (${elapsed}s startup)"
