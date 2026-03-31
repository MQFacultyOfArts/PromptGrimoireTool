# Lag-Based Admission Gate Implementation Plan

**Goal:** Clean admission state on both restart paths; verify post-restart ramp-up behaviour.

**Architecture:** Add `clear()` method to AdmissionState, call it from `graceful_memory_shutdown()` and `pre_restart_handler()`. Post-restart, `init_admission()` creates fresh state with cap at `initial_cap` — natural ramp-up via AIMD.

**Tech Stack:** Python 3.14

**Scope:** 5 phases from original design (phase 5 of 5)

**Codebase verified:** 2026-03-30

---

## Acceptance Criteria Coverage

This phase implements and tests:

### lag-admission-gate.AC1: Cap adjusts dynamically based on event loop lag
- **lag-admission-gate.AC1.4 Success:** After restart, cap starts at `initial_cap` and ramps up naturally via AIMD as lag stays low

### lag-admission-gate.AC3: Gate only affects new authenticated users
- **lag-admission-gate.AC3.4 Edge:** User who disconnects and reconnects within 15s `reconnect_timeout` remains in `_registry` and is not gated

---

<!-- START_TASK_1 -->
### Task 1: Add clear() method and priority re-enqueue to AdmissionState

**Verifies:** None (infrastructure — method for restart paths to call; UX kindness for re-admitted users)

**Files:**
- Modify: `src/promptgrimoire/admission.py`
- Modify: `tests/unit/test_admission_state.py` (add priority re-enqueue tests)

**Implementation:**

**1a. `clear()` method:**

Add a `clear()` method to `AdmissionState` that resets all mutable state:

```python
def clear(self) -> None:
    """Reset all admission state. Called before restart."""
    self._queue.clear()
    self._enqueue_times.clear()
    self._tokens.clear()
    self._user_tokens.clear()
    self._tickets.clear()
    self.cap = self.initial_cap
```

This is intentionally simple — it doesn't need to notify queued users (they'll be navigated to `/restarting` by the restart handler before this is called).

**1b. Priority re-enqueue for previously-admitted users:**

A user who waited in the queue and was admitted, but whose browser tab closed before they consumed their ticket, currently hits `enqueue()` idempotency — it returns the stale token from `_user_tokens`. But that token maps to a user with no queue position and no ticket (both cleaned up by `sweep_expired`). `get_queue_status` on that stale token returns `expired: True`, forcing them to re-queue from scratch. That's unkind — they already waited.

Fix: in `enqueue()`, when the user is found in `_user_tokens`, check whether the token is still valid (user is in `_queue` or `_tickets`). If the token is stale (neither), clean up the old mapping and re-enqueue at the **front** of the queue (`appendleft`) with a fresh token. They waited already; they go to the front.

```python
def enqueue(self, user_id: UUID) -> str:
    """Add user to FIFO queue; returns opaque queue token.

    Idempotent: re-enqueuing the same user_id returns the
    existing token without changing queue position.

    Priority: if a previously-admitted user returns after their
    ticket expired (tab closed), they are placed at the front
    of the queue — they already waited once.
    """
    if user_id in self._user_tokens:
        # Check if existing token is still valid
        if user_id in self._enqueue_times or user_id in self._tickets:
            return self._user_tokens[user_id]
        # Stale — previously admitted user returning after tab close.
        # Clean up old mapping and re-enqueue at front.
        self._cleanup_token_maps(user_id)

    token = uuid4().hex
    if user_id in self._user_tokens:
        # Should not reach here after cleanup, but defensive
        return self._user_tokens[user_id]

    # Priority: appendleft if user had a stale token (cleaned above),
    # append normally for fresh users. We can detect this by checking
    # whether we just cleaned up — but simpler: always use appendleft
    # for users who previously had an entry (the cleanup path above),
    # and append for genuinely new users.
    # Since we cleaned up above, the user is no longer in _user_tokens.
    # Track whether this is a priority re-enqueue:
    self._queue.append(user_id)
    self._enqueue_times[user_id] = time.monotonic()
    self._tokens[token] = user_id
    self._user_tokens[user_id] = token
    return token
```

Actually, simpler approach — track the cleanup and branch on it:

```python
def enqueue(self, user_id: UUID) -> str:
    priority = False
    if user_id in self._user_tokens:
        if user_id in self._enqueue_times or user_id in self._tickets:
            return self._user_tokens[user_id]  # Still valid
        # Stale — clean up and re-enqueue at front
        self._cleanup_token_maps(user_id)
        priority = True

    token = uuid4().hex
    if priority:
        self._queue.appendleft(user_id)
    else:
        self._queue.append(user_id)
    self._enqueue_times[user_id] = time.monotonic()
    self._tokens[token] = user_id
    self._user_tokens[user_id] = token
    return token
```

**Testing (add to existing test_admission_state.py):**

- `test_enqueue_stale_user_gets_priority`: Enqueue user, admit them (creates ticket), expire the ticket via `sweep_expired`, then enqueue again. Verify: user is at position 1 (front), gets a new token, old token is invalid.
- `test_enqueue_valid_user_is_idempotent`: Enqueue user (still in queue). Enqueue again. Verify: same token, same position.

**Verification:**

Run: `uv run grimoire test all`
Expected: All tests pass

**Commit:** `feat: add AdmissionState.clear() and priority re-enqueue for returning users`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Wire admission clearing into both restart paths

**Verifies:** lag-admission-gate.AC1.4

**Files:**
- Modify: `src/promptgrimoire/diagnostics.py` (graceful_memory_shutdown, around line 268)
- Modify: `src/promptgrimoire/pages/restart.py` (pre_restart_handler, around line 126)
- Create: `tests/unit/test_admission_restart.py`

**Implementation:**

**In `diagnostics.py:graceful_memory_shutdown()`** — add admission clearing between `_persist_dirty_workspaces()` (line 268) and `_navigate_clients_to_restarting()` (line 271):

```python
from promptgrimoire.admission import get_admission_state

# Clear admission queue before navigating clients to /restarting
try:
    get_admission_state().clear()
except RuntimeError:
    pass  # Admission not initialised — nothing to clear
```

The try/except handles the edge case where graceful_memory_shutdown fires before admission is initialised (unlikely but defensive).

**In `pages/restart.py:pre_restart_handler()`** — add admission clearing in the pre-restart sequence, after persisting CRDT and before navigating clients:

```python
from promptgrimoire.admission import get_admission_state

# Clear admission queue
try:
    get_admission_state().clear()
except RuntimeError:
    pass
```

**Testing:**

Test file: `tests/unit/test_admission_restart.py`

- lag-admission-gate.AC1.4: Create AdmissionState, modify cap (set to 100), enqueue users, create tickets. Call `clear()`. Verify: cap == initial_cap, queue empty, tokens empty, tickets empty. This proves post-restart state is fresh.
- Verify that `init_admission()` with default config creates state with `cap == initial_cap` (20). This is the post-restart starting point.
- Verify AIMD ramp-up: starting from initial_cap=20, repeated `update_cap(lag_ms=5.0, admitted_count=15)` calls increase cap by batch_size each time (20 → 40 → 60 → ...).

Note: AC3.4 (reconnect_timeout) is verified by the NiceGUI `reconnect_timeout=15.0` setting in `ui.run()` — this is a framework property, not something the admission gate controls. The gate's behaviour is: if user_id is in `client_registry._registry`, they pass through (already tested in Phase 3). The 15s grace period keeping them in the registry is NiceGUI's responsibility.

**Verification:**

Run: `uv run grimoire test run tests/unit/test_admission_restart.py`
Expected: All tests pass

Run: `uv run grimoire test all`
Expected: All tests pass

**Commit:** `feat: clear admission state on pre-restart and memory threshold restart`
<!-- END_TASK_2 -->
