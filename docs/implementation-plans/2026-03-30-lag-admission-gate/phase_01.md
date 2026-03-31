# Lag-Based Admission Gate Implementation Plan

**Goal:** Core admission state module with AIMD cap computation, FIFO queue, queue tokens, and entry tickets — independent of NiceGUI.

**Architecture:** Module-level `AdmissionState` dataclass holding all admission state. Pure functions operate on this state. No NiceGUI imports. The diagnostic loop and page_route (later phases) call into this module.

**Tech Stack:** Python 3.14, pydantic BaseModel (for config), collections.deque, uuid, time.monotonic

**Scope:** 5 phases from original design (phase 1 of 5)

**Codebase verified:** 2026-03-30

---

## Acceptance Criteria Coverage

This phase implements and tests:

### lag-admission-gate.AC1: Cap adjusts dynamically based on event loop lag
- **lag-admission-gate.AC1.1 Success:** Cap increases by `batch_size` when lag < `lag_increase_ms` and admitted count >= cap - batch_size
- **lag-admission-gate.AC1.2 Success:** Cap unchanged when lag is between `lag_increase_ms` and `lag_decrease_ms` (hysteresis band)
- **lag-admission-gate.AC1.3 Success:** Cap halves when lag > `lag_decrease_ms`
- **lag-admission-gate.AC1.4 Success:** After restart, cap starts at `initial_cap` and ramps up naturally via AIMD as lag stays low
- **lag-admission-gate.AC1.5 Edge:** Cap never drops below `initial_cap` even under sustained high lag
- **lag-admission-gate.AC1.6 Edge:** Cap does not increase when admitted count is well below current cap (no speculative growth)

### lag-admission-gate.AC2: FIFO queue with batch admission and entry tickets
- **lag-admission-gate.AC2.1 Success:** Users arriving when at cap are added to queue in arrival order and receive an opaque queue token (UUID4)
- **lag-admission-gate.AC2.2 Success:** When cap rises above admitted count, queued users are popped in FIFO order up to available capacity and granted entry tickets
- **lag-admission-gate.AC2.3 Success:** Batch admission admits multiple users per diagnostic cycle (not one-at-a-time)
- **lag-admission-gate.AC2.4 Failure:** Users in queue longer than `queue_timeout_seconds` (default 1800s / 30 min) are dropped from queue
- **lag-admission-gate.AC2.5 Edge:** User already in queue is not double-enqueued on subsequent page loads — same token returned, same position preserved
- **lag-admission-gate.AC2.6 Success:** Admitted user holds an entry ticket valid for `ticket_validity_seconds` (default 600s / 10 min); page_route consumes the ticket on first page load
- **lag-admission-gate.AC2.7 Edge:** User who closes tab and returns while still in queue sees their existing queue position (not re-queued at back)
- **lag-admission-gate.AC2.8 Edge:** User who closes tab and returns after batch admission (ticket still valid) passes through gate directly — sees main page, not queue
- **lag-admission-gate.AC2.9 Edge:** User who returns after ticket expires is treated as a fresh arrival — enters if under cap, queues if at cap

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: AdmissionConfig sub-model in config.py

**Verifies:** None (infrastructure — config plumbing)

**Files:**
- Modify: `src/promptgrimoire/config.py`

**Implementation:**

Add `AdmissionConfig` BaseModel sub-model following the existing pattern (e.g. `AppConfig`, `ExportConfig`). Place it after `ExportConfig` (around line 122).

```python
class AdmissionConfig(BaseModel):
    """Dynamic admission gate configuration (AIMD algorithm)."""

    initial_cap: int = 20
    batch_size: int = 20
    lag_increase_ms: int = 10
    lag_decrease_ms: int = 50
    queue_timeout_seconds: int = 1800
    ticket_validity_seconds: int = 600
```

Add the sub-model to the `Settings` class (after the existing sub-model fields, around line 316):

```python
admission: AdmissionConfig = AdmissionConfig()
```

Environment variables will map to: `ADMISSION__INITIAL_CAP`, `ADMISSION__BATCH_SIZE`, `ADMISSION__LAG_INCREASE_MS`, `ADMISSION__LAG_DECREASE_MS`, `ADMISSION__QUEUE_TIMEOUT_SECONDS`, `ADMISSION__TICKET_VALIDITY_SECONDS`.

**Verification:**

Run: `uv run grimoire test all`
Expected: All existing tests pass (no regressions from adding a config field with defaults)

**Commit:** `feat: add AdmissionConfig sub-model for lag-based admission gate`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: AdmissionState dataclass and AIMD logic

**Verifies:** lag-admission-gate.AC1.1, lag-admission-gate.AC1.2, lag-admission-gate.AC1.3, lag-admission-gate.AC1.4, lag-admission-gate.AC1.5, lag-admission-gate.AC1.6, lag-admission-gate.AC2.1, lag-admission-gate.AC2.2, lag-admission-gate.AC2.3, lag-admission-gate.AC2.4, lag-admission-gate.AC2.5, lag-admission-gate.AC2.6, lag-admission-gate.AC2.7, lag-admission-gate.AC2.8, lag-admission-gate.AC2.9

**Files:**
- Create: `src/promptgrimoire/admission.py`
- Create: `tests/unit/test_admission.py`

**Implementation:**

Create `src/promptgrimoire/admission.py` with:

1. `AdmissionState` dataclass (not frozen — state mutates) with fields:
   - `cap: int` — current admission cap, initialised to `initial_cap`
   - `initial_cap: int` — floor value, cap never drops below this
   - `batch_size: int`
   - `lag_increase_ms: int`
   - `lag_decrease_ms: int`
   - `queue_timeout_seconds: int`
   - `ticket_validity_seconds: int`
   - `_queue: deque[UUID]` — FIFO queue of user_ids awaiting admission
   - `_enqueue_times: dict[UUID, float]` — monotonic enqueue time per user_id (for expiry)
   - `_tokens: dict[str, UUID]` — queue token (str) → user_id mapping
   - `_user_tokens: dict[UUID, str]` — user_id → queue token reverse map (for dedup/reconnect)
   - `_tickets: dict[UUID, float]` — user_id → monotonic expiry time for entry tickets

2. `update_cap(self, lag_ms: float, admitted_count: int) -> None`:
   - If `lag_ms > self.lag_decrease_ms`: `self.cap = max(self.cap // 2, self.initial_cap)`
   - Elif `lag_ms < self.lag_increase_ms` and `admitted_count >= self.cap - self.batch_size`: `self.cap += self.batch_size`
   - Else: no change (hysteresis band, or admitted well below cap)

3. `enqueue(self, user_id: UUID) -> str`:
   - If `user_id in self._user_tokens`: return existing token (dedup — AC2.5, AC2.7)
   - Generate `token = uuid4().hex`
   - Append `user_id` to `self._queue`
   - Store `self._enqueue_times[user_id] = time.monotonic()`
   - Store `self._tokens[token] = user_id` and `self._user_tokens[user_id] = token`
   - Return token

4. `admit_batch(self, admitted_count: int) -> list[UUID]`:
   - `available = self.cap - admitted_count`
   - If `available <= 0` or queue empty: return `[]`
   - Pop up to `available` user_ids from left of `self._queue`
   - For each popped user_id:
     - Create entry ticket: `self._tickets[user_id] = time.monotonic() + self.ticket_validity_seconds`
     - Remove from `_enqueue_times`
     - Leave `_tokens` and `_user_tokens` intact (status endpoint needs them to report `admitted: true`)
   - Return list of admitted user_ids

5. `try_enter(self, user_id: UUID) -> bool`:
   - If `user_id not in self._tickets`: return `False`
   - If `self._tickets[user_id] < time.monotonic()`: expired — remove ticket, return `False`
   - Consume ticket: delete from `_tickets`, clean up token maps (`_tokens`, `_user_tokens`)
   - Return `True`

6. `get_queue_status(self, token: str) -> dict`:
   - If token not in `self._tokens`: return `{"position": 0, "total": 0, "admitted": False, "expired": True}`
   - `user_id = self._tokens[token]`
   - If `user_id in self._tickets` (admitted but not yet entered):
     - If ticket expired: clean up, return expired
     - Else: return `{"position": 0, "total": len(self._queue), "admitted": True, "expired": False}`
   - If `user_id in self._enqueue_times` (still in queue):
     - Calculate position (1-indexed): iterate `self._queue` to find index. This is O(n) on queue depth. Acceptable because: (a) the gate caps queue growth (users expire after `queue_timeout_seconds`), (b) realistic queue depths are tens to low hundreds, not thousands, (c) the poll interval is 5s so each user triggers one scan per 5s. At 200 queued users, worst case is 200 * 200 / 5 = 8000 iterations/second — trivial for Python.
     - Return `{"position": pos, "total": len(self._queue), "admitted": False, "expired": False}`
   - Else: token exists but user not in queue or tickets — stale, return expired

7. `sweep_expired(self) -> None`:
   - `now = time.monotonic()`
   - Sweep expired queue entries: collect expired user_ids first (`[uid for uid, t in self._enqueue_times.items() if now - t > self.queue_timeout_seconds]`), then delete each from `_enqueue_times`, `_queue`, `_tokens`, `_user_tokens` in a second pass. Do NOT mutate dicts during iteration — Python raises `RuntimeError`.
   - Sweep expired tickets: collect expired user_ids first (`[uid for uid, exp in self._tickets.items() if exp < now]`), then delete each from `_tickets`, `_tokens`, `_user_tokens` in a second pass.
   - For removing from `_queue` (deque): rebuild the deque excluding expired user_ids, e.g. `self._queue = deque(uid for uid in self._queue if uid not in expired_set)`.

8. Module-level `_state: AdmissionState | None = None` singleton.

9. `init_admission(config: AdmissionConfig) -> None`: Creates `_state` from config values.

10. `get_admission_state() -> AdmissionState`: Returns `_state`, raises `RuntimeError` if not initialised.

**Testing:**

Tests must verify each AC listed above. Test file: `tests/unit/test_admission.py`.

**AIMD cap tests (AC1.*):**
- lag-admission-gate.AC1.1: Create state with `initial_cap=20, batch_size=20, lag_increase_ms=10, lag_decrease_ms=50`. Call `update_cap(lag_ms=5.0, admitted_count=15)` (15 >= 20-20=0). Assert cap increased to 40.
- lag-admission-gate.AC1.2: Call `update_cap(lag_ms=30.0, admitted_count=15)` (hysteresis). Assert cap unchanged.
- lag-admission-gate.AC1.3: Set cap to 100. Call `update_cap(lag_ms=60.0, admitted_count=50)`. Assert cap halved to 50.
- lag-admission-gate.AC1.4: Fresh state starts at `initial_cap=20`. Verify cap == 20 before any updates.
- lag-admission-gate.AC1.5: Set cap to 20 (== initial_cap). Call `update_cap(lag_ms=60.0, ...)` repeatedly. Assert cap stays at 20.
- lag-admission-gate.AC1.6: Cap is 100, admitted is 10 (well below 100-20=80). Call `update_cap(lag_ms=5.0, admitted_count=10)`. Assert cap unchanged (10 < 80, not near cap).

**Queue and ticket tests (AC2.*):**
- lag-admission-gate.AC2.1: Enqueue 3 users. Verify tokens returned, queue order matches insertion order.
- lag-admission-gate.AC2.2: Enqueue 3, call `admit_batch(admitted_count=0)` with cap=2. Verify first 2 popped, third remains. Verify popped users have tickets.
- lag-admission-gate.AC2.3: Enqueue 5, cap=5, `admit_batch(admitted_count=0)`. Verify all 5 admitted in one call.
- lag-admission-gate.AC2.4: Enqueue user, mock `time.monotonic` to advance past `queue_timeout_seconds`. Call `sweep_expired()`. Verify user removed from queue and token maps.
- lag-admission-gate.AC2.5: Enqueue same user_id twice. Verify same token returned, queue length is 1.
- lag-admission-gate.AC2.6: Enqueue, admit. Verify `try_enter(user_id)` returns True and consumes ticket.
- lag-admission-gate.AC2.7: Same as AC2.5 — second enqueue returns same token, position unchanged.
- lag-admission-gate.AC2.8: Enqueue, admit, then `try_enter()` returns True (simulates "come back from coffee").
- lag-admission-gate.AC2.9: Enqueue, admit, advance time past ticket_validity_seconds, `try_enter()` returns False.

Use `unittest.mock.patch("time.monotonic")` or pass a clock function to make time-dependent tests deterministic.

**Verification:**

Run: `uv run grimoire test run tests/unit/test_admission.py`
Expected: All tests pass

Run: `uv run grimoire test all`
Expected: All tests pass (no regressions)

**Commit:** `feat: add AdmissionState with AIMD cap, FIFO queue, and entry tickets`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->
