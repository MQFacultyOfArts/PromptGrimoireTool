# Query Optimisation and Graceful Restart — Phase 5

**Goal:** Integrate the application-level drain into the deploy script, replacing the stagger wait with the new pre-restart + polling + `/restarting` page flow.

**Architecture:** `restart.sh` calls `POST /api/pre-restart` (extracting the Bearer token from the app's `.env` file) to trigger client-side flush and navigation. It then enables HAProxy drain to block new arrivals, polls `GET /api/connection-count` until connections drop to ≤5% of initial count plus a 2-second grace period, and proceeds with `systemctl restart`. The 20-second stagger wait is removed — the `/restarting` page's client-side jitter handles thundering herd prevention.

**Tech Stack:** Bash, curl, socat (HAProxy admin), BATS (tests)

**Scope:** Phase 5 of 6 from original design

**Codebase verified:** 2026-03-26

---

## Acceptance Criteria Coverage

This phase implements and tests:

### query-optimisation-and-graceful-restart-186.AC4: Deploy script
- **query-optimisation-and-graceful-restart-186.AC4.1 Success:** `restart.sh` calls pre-restart, waits for ≤5% connections + 2s
- **query-optimisation-and-graceful-restart-186.AC4.2 Edge:** Timeout after configurable seconds proceeds with restart (don't hang forever)
- **query-optimisation-and-graceful-restart-186.AC4.3 Success:** HAProxy drain blocks new arrivals during application-level drain window

---

## Implementation Tasks

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Update `deploy/restart.sh` with application-level drain

**Verifies:** query-optimisation-and-graceful-restart-186.AC4.1, query-optimisation-and-graceful-restart-186.AC4.2, query-optimisation-and-graceful-restart-186.AC4.3

**Files:**
- Modify: `deploy/restart.sh`

**Implementation:**

The current script (146 lines) follows this sequence:
```
git pull → uv sync → tests → 503 copy → HAProxy drain → poll HAProxy sessions → HAProxy maint → restart → healthz → stagger 20s → HAProxy ready
```

The new sequence replaces steps 4-7 and removes the stagger:
```
git pull → uv sync → tests → 503 copy → pre-restart API → HAProxy drain → poll connection-count API → restart → healthz → HAProxy ready
```

**Changes to make:**

1. **Add token extraction** near the top constants (after line 29):
   ```bash
   # Application-level drain token
   PRE_RESTART_TOKEN=$(grep '^ADMIN__PRE_RESTART_TOKEN=' "$APP_DIR/.env" | cut -d= -f2-)
   DRAIN_TIMEOUT=${DRAIN_TIMEOUT:-30}  # Max seconds to wait for connections to drain
   ```

2. **Replace steps 5-7** (current lines 87-113: HAProxy drain → poll HAProxy sessions → HAProxy maint) with the new application-level drain sequence:

   **New step 5: Call pre-restart API**
   ```bash
   step "Triggering application-level pre-restart"
   if [[ -z "$PRE_RESTART_TOKEN" ]]; then
       echo "WARNING: ADMIN__PRE_RESTART_TOKEN not set in .env — skipping pre-restart" >&2
       initial_count=0
   else
       pre_restart_response=$(curl -sf -X POST \
           -H "Authorization: Bearer $PRE_RESTART_TOKEN" \
           http://127.0.0.1:8080/api/pre-restart 2>&1) || {
           echo "WARNING: pre-restart endpoint failed — proceeding with restart" >&2
           initial_count=0
       }
       initial_count=$(echo "$pre_restart_response" | grep -o '"initial_count":[0-9]*' | cut -d: -f2)
       initial_count=${initial_count:-0}
       echo "  Initial connected clients: $initial_count"
   fi
   ```

   **New step 6: HAProxy drain (block new arrivals)**
   ```bash
   step "HAProxy drain (blocking new arrivals)"
   echo "set server be_promptgrimoire/app state drain" | socat stdio "$SOCK"
   ```

   **New step 7: Poll connection count until drained**
   ```bash
   if [[ "$initial_count" -gt 0 ]] && [[ -n "$PRE_RESTART_TOKEN" ]]; then
       threshold=$(( (initial_count * 5 + 99) / 100 ))  # ceil(5%)
       step "Waiting for connections to drain (threshold: ≤${threshold}, timeout: ${DRAIN_TIMEOUT}s)"
       elapsed=0
       while [[ $elapsed -lt $DRAIN_TIMEOUT ]]; do
           sleep 1
           elapsed=$((elapsed + 1))
           current=$(curl -sf \
               -H "Authorization: Bearer $PRE_RESTART_TOKEN" \
               http://127.0.0.1:8080/api/connection-count 2>/dev/null \
               | grep -o '"count":[0-9]*' | cut -d: -f2)
           current=${current:-0}
           if [[ "$current" -le "$threshold" ]]; then
               echo "  Drained to $current connections (≤${threshold}) after ${elapsed}s"
               sleep 2  # Grace period
               break
           fi
           echo "  ${elapsed}s: $current connections remaining"
       done
       if [[ $elapsed -ge $DRAIN_TIMEOUT ]]; then
           echo "  Timeout after ${DRAIN_TIMEOUT}s — proceeding with restart"
       fi
   fi
   ```

3. **Keep HAProxy maint step** (line 111-113 unchanged):
   ```bash
   step "HAProxy maintenance mode"
   echo "set server be_promptgrimoire/app state maint" | socat stdio "$SOCK"
   ```

4. **Keep restart and healthz steps** (lines 115-131 unchanged).

5. **Remove the 20-second stagger wait** (delete lines 133-138: the `step "Stagger delay"` / `sleep $STAGGER_WAIT` block). The `/restarting` page's client-side jitter replaces this.

6. **HAProxy ready** (line 140-142 unchanged).

**Important notes:**
- The pre-restart call is best-effort: if token is missing or endpoint fails, the script warns and proceeds (don't block deploy on this)
- The JSON parsing uses `grep -o` + `cut` — no dependency on `jq` (which may not be installed on the server)
- `DRAIN_TIMEOUT` defaults to 30s, overridable via environment

**Verification:**
Run: `shellcheck deploy/restart.sh`
Expected: No errors (warnings acceptable)

Run: `uv run grimoire test bats`
Expected: All BATS tests pass

**Commit:** `feat: integrate application-level drain into restart.sh (#355)`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: BATS tests for new restart.sh drain logic

**Verifies:** query-optimisation-and-graceful-restart-186.AC4.1, query-optimisation-and-graceful-restart-186.AC4.2

**Files:**
- Modify: `deploy/tests/test_restart.bats` (add tests for new drain logic)

**Testing:**

BATS tests can't exercise the full deploy sequence (needs root, HAProxy, running app), but they can test the new parsing and drain logic in isolation.

Tests to add:

- **Test: token extraction from .env** — Create a temp .env file with `ADMIN__PRE_RESTART_TOKEN=test-secret`, source the extraction logic, verify `PRE_RESTART_TOKEN` equals `test-secret`
- **Test: missing token warns but doesn't fail** — Create a temp .env without the token line, verify the script would produce a WARNING and set `initial_count=0`
- **Test: DRAIN_TIMEOUT defaults to 30** — Verify the default is applied when env var not set
- **Test: DRAIN_TIMEOUT is overridable** — Set `DRAIN_TIMEOUT=10`, verify it's used

Follow existing BATS patterns from `deploy/tests/test_restart.bats` — `run`, `skip`, status/output assertions. Use `setup()` to create temp files and `teardown()` to clean up.

**Verification:**
Run: `uv run grimoire test bats`
Expected: All BATS tests pass (existing + new)

**Commit:** `test: add BATS tests for restart.sh application-level drain (#355)`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

---

## Complexipy Check

Not applicable — shell scripts are not checked by complexipy.

## UAT Steps

1. [ ] Review `deploy/restart.sh` diff — verify pre-restart call, HAProxy drain, connection polling, stagger removal
2. [ ] Verify: `ADMIN__PRE_RESTART_TOKEN` is set in production `.env`
3. [ ] Run: `uv run grimoire test bats` — verify BATS tests pass
4. [ ] On production: execute `deploy/restart.sh` and observe:
   - Pre-restart API called (check log for response)
   - HAProxy drain enabled
   - Connection count polled until threshold
   - Server restarted
   - Healthz responds
   - HAProxy ready
5. [ ] Verify: connected users saw `/restarting` page, not a disconnect

## Evidence Required
- [ ] `uv run grimoire test bats` output showing green
- [ ] `shellcheck deploy/restart.sh` output clean (warnings acceptable)
- [ ] Production deploy log showing the full sequence
