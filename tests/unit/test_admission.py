"""Tests for lag-based admission gate (AIMD cap, FIFO queue, entry tickets).

Verifies acceptance criteria lag-admission-gate.AC1.* and AC2.*.
"""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest

from promptgrimoire.admission import AdmissionState, get_admission_state, init_admission
from promptgrimoire.config import AdmissionConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_state(**overrides: int) -> AdmissionState:
    return AdmissionState(
        cap=overrides.get("cap", 20),
        initial_cap=overrides.get("initial_cap", 20),
        batch_size=overrides.get("batch_size", 20),
        lag_increase_ms=overrides.get("lag_increase_ms", 10),
        lag_decrease_ms=overrides.get("lag_decrease_ms", 50),
        queue_timeout_seconds=overrides.get(
            "queue_timeout_seconds",
            1800,
        ),
        ticket_validity_seconds=overrides.get(
            "ticket_validity_seconds",
            600,
        ),
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
        assert len(state._queue) == 1

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
