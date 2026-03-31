"""Tests for lag-based admission gate (AIMD cap, FIFO queue, entry tickets).

Verifies acceptance criteria lag-admission-gate.AC1.* and AC2.*.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest

from promptgrimoire.admission import AdmissionState, get_admission_state, init_admission
from promptgrimoire.config import AdmissionConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_state(*, cap: int | None = None, **overrides: Any) -> AdmissionState:
    """Build an AdmissionState from AdmissionConfig defaults with overrides.

    ``cap`` defaults to the config's ``initial_cap`` (matching production
    behaviour).  All other keyword arguments are forwarded to AdmissionConfig.
    """
    config = AdmissionConfig(**overrides)
    return AdmissionState(
        enabled=config.enabled,
        cap=cap if cap is not None else config.initial_cap,
        initial_cap=config.initial_cap,
        batch_size=config.batch_size,
        lag_increase_ms=config.lag_increase_ms,
        lag_decrease_ms=config.lag_decrease_ms,
        queue_timeout_seconds=config.queue_timeout_seconds,
        ticket_validity_seconds=config.ticket_validity_seconds,
    )


# ===========================================================================
# AIMD cap tests (AC1.*)
# ===========================================================================
class TestUpdateCap:
    """lag-admission-gate.AC1.*: Cap adjusts dynamically based on event loop lag."""

    def test_ac1_1_cap_increases_when_lag_low_and_near_cap(self) -> None:
        """AC1.1: Cap increases when lag low and near cap."""
        state = _make_state()
        state.update_cap(lag_ms=5.0, admitted_count=15)  # 15 >= 20-20=0
        assert state.cap == 40

    def test_ac1_2_cap_unchanged_in_hysteresis_band(self) -> None:
        """AC1.2: Cap unchanged when lag between lag_increase_ms and lag_decrease_ms."""
        state = _make_state()
        state.update_cap(lag_ms=30.0, admitted_count=15)
        assert state.cap == 20

    def test_ac1_3_cap_halves_on_high_lag(self) -> None:
        """AC1.3: Cap halves when lag > lag_decrease_ms."""
        state = _make_state(cap=100)
        state.update_cap(lag_ms=60.0, admitted_count=50)
        assert state.cap == 50

    def test_ac1_4_fresh_state_starts_at_initial_cap(self) -> None:
        """AC1.4: After restart, cap starts at initial_cap."""
        state = _make_state()
        assert state.cap == 20

    def test_ac1_5_cap_never_drops_below_initial(self) -> None:
        """AC1.5: Cap never drops below initial_cap even under sustained high lag."""
        state = _make_state(cap=20)
        for _ in range(10):
            state.update_cap(lag_ms=100.0, admitted_count=0)
        assert state.cap == 20

    def test_ac1_6_no_speculative_growth(self) -> None:
        """AC1.6: Cap does not increase when admitted well below cap."""
        state = _make_state(cap=100)
        state.update_cap(lag_ms=5.0, admitted_count=10)  # 10 < 100-20=80
        assert state.cap == 100


# ===========================================================================
# Queue and ticket tests (AC2.*)
# ===========================================================================
class TestQueue:
    """lag-admission-gate.AC2.*: FIFO queue with batch admission and entry tickets."""

    def test_ac2_1_enqueue_preserves_fifo_order(self) -> None:
        """AC2.1: Users queued in arrival order with tokens."""
        state = _make_state()
        users = [uuid4() for _ in range(3)]
        tokens = [state.enqueue(u) for u in users]
        # All tokens are unique non-empty strings
        assert len(set(tokens)) == 3
        assert all(isinstance(t, str) and len(t) > 0 for t in tokens)
        # Internal queue order matches insertion
        assert list(state._queue) == users

    def test_ac2_2_admit_batch_pops_fifo(self) -> None:
        """AC2.2: Queued users popped FIFO up to capacity."""
        state = _make_state(cap=2)
        users = [uuid4() for _ in range(3)]
        for u in users:
            state.enqueue(u)
        admitted = state.admit_batch(admitted_count=0)
        assert admitted == [users[0], users[1]]
        # Third user still in queue
        assert list(state._queue) == [users[2]]
        # Admitted users have tickets
        assert users[0] in state._tickets
        assert users[1] in state._tickets

    def test_ac2_3_batch_admits_multiple(self) -> None:
        """AC2.3: Batch admission admits multiple users per cycle."""
        state = _make_state(cap=5)
        users = [uuid4() for _ in range(5)]
        for u in users:
            state.enqueue(u)
        admitted = state.admit_batch(admitted_count=0)
        assert len(admitted) == 5
        assert admitted == users

    def test_admit_batch_with_admitted_count_partial(self) -> None:
        """admit_batch with admitted_count=15, cap=20, 10 queued → 5 newly admitted."""
        state = _make_state(cap=20)
        users = [uuid4() for _ in range(10)]
        for u in users:
            state.enqueue(u)
        admitted = state.admit_batch(admitted_count=15)
        assert len(admitted) == 5
        assert admitted == users[:5]
        # Remaining 5 stay in queue
        assert list(state._queue) == users[5:]

    def test_admit_batch_with_admitted_count_full(self) -> None:
        """admit_batch with admitted_count=20, cap=20, 5 queued → [] (at cap)."""
        state = _make_state(cap=20)
        users = [uuid4() for _ in range(5)]
        for u in users:
            state.enqueue(u)
        admitted = state.admit_batch(admitted_count=20)
        assert admitted == []
        # All 5 still waiting
        assert list(state._queue) == users

    def test_ac2_4_expired_queue_entries_swept(self) -> None:
        """AC2.4: Users in queue longer than queue_timeout_seconds are dropped."""
        state = _make_state(queue_timeout_seconds=1800)
        user = uuid4()
        with patch("promptgrimoire.admission.time") as mock_time:
            mock_time.monotonic.return_value = 1000.0
            token = state.enqueue(user)
            # Advance past timeout
            mock_time.monotonic.return_value = 1000.0 + 1801.0
            state.sweep_expired()
        assert user not in state._enqueue_times
        assert token not in state._tokens
        assert user not in state._user_tokens
        assert user not in state._queue

    def test_ac2_5_no_double_enqueue(self) -> None:
        """AC2.5: Same user_id enqueued twice returns same token, queue length 1."""
        state = _make_state()
        user = uuid4()
        t1 = state.enqueue(user)
        t2 = state.enqueue(user)
        assert t1 == t2
        assert state.queue_depth == 1

    def test_ac2_6_try_enter_consumes_ticket(self) -> None:
        """AC2.6: Admitted user's entry ticket is consumed by try_enter."""
        state = _make_state(cap=1)
        user = uuid4()
        state.enqueue(user)
        state.admit_batch(admitted_count=0)
        assert state.try_enter(user) is True
        # Ticket consumed — second call returns False
        assert state.try_enter(user) is False

    def test_ac2_7_reconnect_preserves_position(self) -> None:
        """AC2.7: User who returns while still in queue sees same position."""
        state = _make_state()
        users = [uuid4() for _ in range(3)]
        tokens = [state.enqueue(u) for u in users]
        # User at position 2 reconnects
        t_again = state.enqueue(users[1])
        assert t_again == tokens[1]
        # Queue unchanged
        assert list(state._queue) == users

    def test_ac2_8_return_after_admit_enters_directly(self) -> None:
        """AC2.8: Return after admission with valid ticket passes."""
        state = _make_state(cap=1)
        user = uuid4()
        state.enqueue(user)
        state.admit_batch(admitted_count=0)
        # Simulate "come back from coffee" — try_enter succeeds
        assert state.try_enter(user) is True

    def test_ac2_9_expired_ticket_treated_as_fresh(self) -> None:
        """AC2.9: User who returns after ticket expires is treated as fresh arrival."""
        state = _make_state(cap=1, ticket_validity_seconds=600)
        user = uuid4()
        with patch("promptgrimoire.admission.time") as mock_time:
            mock_time.monotonic.return_value = 1000.0
            state.enqueue(user)
            state.admit_batch(admitted_count=0)
            # Advance past ticket validity
            mock_time.monotonic.return_value = 1000.0 + 601.0
            assert state.try_enter(user) is False


# ===========================================================================
# Queue status tests
# ===========================================================================
class TestQueueStatus:
    """get_queue_status returns correct position/admitted/expired info."""

    def test_unknown_token_returns_expired(self) -> None:
        state = _make_state()
        status = state.get_queue_status("nonexistent")
        assert status == {"position": 0, "total": 0, "admitted": False, "expired": True}

    def test_queued_user_sees_position(self) -> None:
        state = _make_state()
        users = [uuid4() for _ in range(3)]
        tokens = [state.enqueue(u) for u in users]
        status = state.get_queue_status(tokens[1])
        assert status["position"] == 2
        assert status["total"] == 3
        assert status["admitted"] is False
        assert status["expired"] is False

    def test_admitted_user_sees_admitted(self) -> None:
        state = _make_state(cap=1)
        user = uuid4()
        token = state.enqueue(user)
        state.admit_batch(admitted_count=0)
        status = state.get_queue_status(token)
        assert status["admitted"] is True
        assert status["position"] == 0
        assert status["expired"] is False

    def test_queue_desync_returns_position_minus_one(self) -> None:
        """State desync: user in _enqueue_times but not _queue.

        Expect position=-1, expired=True.
        """
        state = _make_state()
        user = uuid4()
        token = state.enqueue(user)
        # Artificially remove user from _queue while keeping _enqueue_times
        state._queue.remove(user)
        status = state.get_queue_status(token)
        assert status["position"] == -1
        assert status["expired"] is True
        assert status["admitted"] is False
        # Token maps cleaned up after desync detection
        assert token not in state._tokens
        assert user not in state._user_tokens
        assert user not in state._enqueue_times

    def test_expired_ticket_in_status(self) -> None:
        state = _make_state(cap=1, ticket_validity_seconds=600)
        user = uuid4()
        with patch("promptgrimoire.admission.time") as mock_time:
            mock_time.monotonic.return_value = 1000.0
            token = state.enqueue(user)
            state.admit_batch(admitted_count=0)
            mock_time.monotonic.return_value = 1000.0 + 601.0
            status = state.get_queue_status(token)
        assert status["expired"] is True


# ===========================================================================
# Sweep expired tickets
# ===========================================================================
class TestSweepExpiredTickets:
    """sweep_expired also cleans up expired tickets."""

    def test_expired_tickets_cleaned(self) -> None:
        state = _make_state(cap=1, ticket_validity_seconds=600)
        user = uuid4()
        with patch("promptgrimoire.admission.time") as mock_time:
            mock_time.monotonic.return_value = 1000.0
            state.enqueue(user)
            state.admit_batch(admitted_count=0)
            mock_time.monotonic.return_value = 1000.0 + 601.0
            state.sweep_expired()
        assert user not in state._tickets
        assert user not in state._user_tokens


# ===========================================================================
# Module-level singleton
# ===========================================================================
class TestSingleton:
    """init_admission / get_admission_state module-level functions."""

    def test_get_before_init_raises(self) -> None:
        import promptgrimoire.admission as mod

        old = mod._state
        try:
            mod._state = None
            with pytest.raises(RuntimeError):
                get_admission_state()
        finally:
            mod._state = old

    def test_init_and_get(self) -> None:
        import promptgrimoire.admission as mod

        old = mod._state
        try:
            mod._state = None
            config = AdmissionConfig(initial_cap=10, batch_size=5)
            init_admission(config)
            s = get_admission_state()
            assert s.cap == 10
            assert s.batch_size == 5
        finally:
            mod._state = old


# ===========================================================================
# clear() method
# ===========================================================================
class TestClear:
    """AdmissionState.clear() resets all mutable state."""

    def test_clear_resets_all_state(self) -> None:
        """After clear(), all collections empty and cap == initial_cap."""
        state = _make_state(cap=100)
        users = [uuid4() for _ in range(3)]
        for u in users:
            state.enqueue(u)
        state.admit_batch(admitted_count=0)  # creates tickets
        assert state.queue_depth > 0 or state.ticket_count > 0

        state.clear()

        assert state.cap == state.initial_cap
        assert state.queue_depth == 0
        assert state.ticket_count == 0
        assert len(state._tokens) == 0
        assert len(state._user_tokens) == 0
        assert len(state._enqueue_times) == 0


# ===========================================================================
# Priority re-enqueue for returning users
# ===========================================================================
class TestPriorityReenqueue:
    """Previously-admitted users who return after ticket expiry go to front."""

    def test_enqueue_stale_user_gets_priority(self) -> None:
        """User who waited, got admitted, ticket expired: re-enqueued at front.

        The user's ticket has expired by timestamp but sweep_expired
        hasn't run yet — the _user_tokens breadcrumb still exists,
        allowing enqueue() to detect a returning user.
        """
        state = _make_state(cap=1, ticket_validity_seconds=600)
        user_a = uuid4()
        user_b = uuid4()

        with patch("promptgrimoire.admission.time") as mock_time:
            mock_time.monotonic.return_value = 1000.0
            token_a = state.enqueue(user_a)
            state.admit_batch(admitted_count=0)  # user_a gets ticket
            # admit_batch consumed the ticket entry via try_enter? No —
            # admit_batch grants a ticket. User never called try_enter.
            # Now expire the ticket by time (but don't sweep).
            mock_time.monotonic.return_value = 1000.0 + 601.0

            # user_a is in _user_tokens but NOT in _enqueue_times
            # (removed by admit_batch) and ticket is expired.
            # enqueue() should detect the stale state.
            assert user_a not in state._enqueue_times
            assert user_a in state._user_tokens

            # Enqueue user_b first (back of queue)
            state.enqueue(user_b)
            # Now user_a returns — should go to front
            new_token_a = state.enqueue(user_a)

        # New token, not the old one
        assert new_token_a != token_a
        # Old token is invalid
        assert token_a not in state._tokens
        # user_a is at position 1 (front)
        assert list(state._queue) == [user_a, user_b]

    def test_enqueue_valid_user_is_idempotent(self) -> None:
        """User still in queue gets same token, same position."""
        state = _make_state()
        user = uuid4()
        t1 = state.enqueue(user)
        t2 = state.enqueue(user)
        assert t1 == t2
        assert state.queue_depth == 1

    def test_enqueue_user_with_valid_ticket_is_idempotent(self) -> None:
        """User with valid ticket gets same token back."""
        state = _make_state(cap=1)
        user = uuid4()
        token = state.enqueue(user)
        state.admit_batch(admitted_count=0)
        # User has ticket — re-enqueue should return same token
        token2 = state.enqueue(user)
        assert token2 == token

    def test_enqueue_after_sweep_no_priority(self) -> None:
        """User returning after sweep_expired cleaned their breadcrumb: back of queue.

        When sweep runs before the user returns, _user_tokens is already
        cleaned — enqueue() treats them as a fresh arrival (back of queue).
        This is correct: the priority path only fires when the breadcrumb
        is still present (user returned before sweep ran).
        """
        state = _make_state(cap=1, ticket_validity_seconds=600)
        user_a = uuid4()
        user_b = uuid4()

        with patch("promptgrimoire.admission.time") as mock_time:
            mock_time.monotonic.return_value = 1000.0
            state.enqueue(user_a)
            state.admit_batch(admitted_count=0)  # user_a gets ticket
            # Advance past ticket validity AND run sweep
            mock_time.monotonic.return_value = 1000.0 + 601.0
            state.sweep_expired()  # cleans _user_tokens for user_a

            # user_a's breadcrumb is gone
            assert user_a not in state._user_tokens

            # Enqueue user_b first
            state.enqueue(user_b)
            # user_a returns — no breadcrumb, treated as fresh (back of queue)
            new_token = state.enqueue(user_a)

        # user_a is at position 2 (back), not front
        assert list(state._queue) == [user_b, user_a]
        # Still gets a valid token
        assert new_token in state._tokens


# ===========================================================================
# admit_batch accounts for outstanding tickets
# ===========================================================================
class TestAdmitBatchTicketAccounting:
    """admit_batch subtracts ticket_count from available capacity."""

    def test_outstanding_tickets_reduce_available(self) -> None:
        """cap=20, 15 connected, 3 holding tickets → only 2 available."""
        state = _make_state(cap=20)
        # Enqueue 10 users
        users = [uuid4() for _ in range(10)]
        for u in users:
            state.enqueue(u)
        # Admit first 3 (creates 3 tickets)
        state.admit_batch(
            admitted_count=0
        )  # admits min(20, 10)=10? No, cap=20, count=0 → 20 available
        # Actually let me set this up more carefully
        state2 = _make_state(cap=20)
        users2 = [uuid4() for _ in range(10)]
        for u in users2:
            state2.enqueue(u)
        # admitted_count=15, cap=20, 10 in queue
        # Without ticket accounting: available = 20-15 = 5, admits 5
        # With ticket accounting: available = 20-15-tickets
        # First admit some to create tickets
        admitted = state2.admit_batch(admitted_count=15)
        assert len(admitted) == 5  # 20-15-0 tickets at this point
        # Now the 5 admitted hold tickets (haven't consumed via try_enter)
        assert state2.ticket_count == 5
        # Try to admit more from the remaining 5 in queue
        # available = 20-15-5 = 0 → admits none
        admitted2 = state2.admit_batch(admitted_count=15)
        assert admitted2 == []

    def test_consumed_tickets_free_capacity(self) -> None:
        """After try_enter consumes tickets, capacity opens back up."""
        state = _make_state(cap=5)
        users = [uuid4() for _ in range(5)]
        for u in users:
            state.enqueue(u)
        # Admit all 5 (creates 5 tickets)
        state.admit_batch(admitted_count=0)
        assert state.ticket_count == 5
        # Consume 3 tickets
        for u in users[:3]:
            state.try_enter(u)
        assert state.ticket_count == 2
        # Now enqueue more
        extra = [uuid4() for _ in range(5)]
        for u in extra:
            state.enqueue(u)
        # admitted_count=3 (consumed), tickets=2 → available = 5-3-2 = 0
        admitted = state.admit_batch(admitted_count=3)
        assert admitted == []
        # admitted_count=3 + 2 tickets consumed → 5-3-0 = 2 available
        for u in users[3:]:
            state.try_enter(u)
        admitted = state.admit_batch(admitted_count=3)
        assert len(admitted) == 2


# ===========================================================================
# Full admission cycle integration test
# ===========================================================================
class TestFullAdmissionCycle:
    """Integration test exercising the complete gate → admit → enter cycle."""

    def test_full_cycle_enqueue_admit_enter(self) -> None:
        """cap=1: user A passes, user B queued, admitted by batch, enters via ticket."""
        state = _make_state(cap=1, batch_size=1)

        user_b = uuid4()

        # User A is already connected (counted in admitted_count=1 below).

        # User B arrives at cap — gets enqueued
        token_b = state.enqueue(user_b)
        status = state.get_queue_status(token_b)
        assert status["position"] == 1
        assert status["admitted"] is False

        # Diagnostic loop runs: admit_batch with admitted_count=1 (user A connected)
        admitted = state.admit_batch(admitted_count=1)
        # cap=1, admitted_count=1, ticket_count=0 → available=0
        assert admitted == []

        # Cap increases via AIMD (lag is low)
        state.update_cap(lag_ms=5.0, admitted_count=1)  # 1 >= 1-1=0 → cap increases
        assert state.cap == 2  # 1 + batch_size(1)

        # Next diagnostic cycle: admit_batch with higher cap
        admitted = state.admit_batch(admitted_count=1)
        assert admitted == [user_b]

        # User B's status now shows admitted
        status = state.get_queue_status(token_b)
        assert status["admitted"] is True

        # User B loads the page — try_enter consumes ticket
        assert state.try_enter(user_b) is True

        # Ticket consumed — second try_enter fails
        assert state.try_enter(user_b) is False

        # Token cleaned up after try_enter consumed ticket
        assert token_b not in state._tokens
