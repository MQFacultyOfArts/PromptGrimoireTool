"""Tests for admission state clearing on restart paths.

Verifies lag-admission-gate.AC1.4: after restart, cap starts at initial_cap
and ramps up naturally via AIMD as lag stays low.
"""

from __future__ import annotations

from typing import Any

from promptgrimoire.admission import AdmissionState, init_admission
from promptgrimoire.config import AdmissionConfig


def _make_state(*, cap: int | None = None, **overrides: Any) -> AdmissionState:
    """Build an AdmissionState from AdmissionConfig defaults with overrides."""
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


class TestAdmissionRestartClearing:
    """AC1.4: clear() produces fresh state equivalent to post-restart."""

    def test_init_admission_creates_fresh_state_at_initial_cap(self) -> None:
        """init_admission() with default config: cap == initial_cap (20)."""
        import promptgrimoire.admission as mod

        old = mod._state
        try:
            mod._state = None
            config = AdmissionConfig()
            init_admission(config)
            state = mod._state
            assert state is not None
            assert state.cap == 20
            assert state.initial_cap == 20
            assert state.queue_depth == 0
            assert state.ticket_count == 0
        finally:
            mod._state = old

    def test_aimd_ramp_up_from_initial_cap(self) -> None:
        """Starting from initial_cap=20, repeated low-lag updates ramp up by batch_size.

        Sequence: 20 -> 40 -> 60 -> 80 -> 100.
        """
        state = _make_state()  # cap=20, batch_size=20
        assert state.cap == 20

        # Each call: lag_ms=5.0 (< lag_increase_ms=10), admitted_count near cap
        state.update_cap(lag_ms=5.0, admitted_count=15)
        assert state.cap == 40

        state.update_cap(lag_ms=5.0, admitted_count=35)
        assert state.cap == 60

        state.update_cap(lag_ms=5.0, admitted_count=55)
        assert state.cap == 80

        state.update_cap(lag_ms=5.0, admitted_count=75)
        assert state.cap == 100
