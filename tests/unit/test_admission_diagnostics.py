"""Tests for admission gate integration with diagnostic loop.

Verifies lag-admission-gate.AC5.1: memory_diagnostic structlog event includes
admission_cap, admission_admitted, admission_queue_depth, admission_tickets.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from structlog.testing import capture_logs

from promptgrimoire.admission import AdmissionState
from promptgrimoire.diagnostics import _enrich_snapshot_with_admission


def _make_admission_state(
    *,
    cap: int = 200,
    initial_cap: int = 100,
    batch_size: int = 10,
    lag_increase_ms: int = 50,
    lag_decrease_ms: int = 200,
    queue_timeout_seconds: int = 300,
    ticket_validity_seconds: int = 30,
) -> AdmissionState:
    return AdmissionState(
        enabled=True,
        cap=cap,
        initial_cap=initial_cap,
        batch_size=batch_size,
        lag_increase_ms=lag_increase_ms,
        lag_decrease_ms=lag_decrease_ms,
        queue_timeout_seconds=queue_timeout_seconds,
        ticket_validity_seconds=ticket_validity_seconds,
    )


class TestDiagnosticCycleAdmissionFields:
    """AC5.1: diagnostic snapshot includes admission fields."""

    def _make_snapshot(self, *, lag_ms: float = 10.0) -> dict[str, Any]:
        return {
            "current_rss_bytes": 1_000_000_000,
            "peak_rss_bytes": 1_500_000_000,
            "clients_total": 50,
            "clients_connected": 45,
            "asyncio_tasks_total": 100,
            "app_ws_registry": 10,
            "app_ws_presence_workspaces": 5,
            "app_ws_presence_clients": 10,
            "event_loop_lag_ms": lag_ms,
        }

    def test_snapshot_contains_admission_fields(self) -> None:
        """AC5.1: snapshot has admission_cap, admission_admitted,
        admission_queue_depth, admission_tickets after processing."""
        state = _make_admission_state(cap=200)
        snapshot = self._make_snapshot()

        _enrich_snapshot_with_admission(snapshot, state, admitted_count=42)

        assert snapshot["admission_cap"] == 200
        assert snapshot["admission_admitted"] == 42
        assert snapshot["admission_queue_depth"] == 0
        assert snapshot["admission_tickets"] == 0

    def test_snapshot_reflects_queue_depth(self) -> None:
        """AC5.1: admission_queue_depth reflects queued users."""
        state = _make_admission_state(cap=5)
        # Enqueue some users
        for _ in range(5):
            state.enqueue(uuid4())

        # Use lag between thresholds (no AIMD change) and
        # admitted_count >= cap so admit_batch has zero capacity.
        snapshot = self._make_snapshot(lag_ms=100.0)
        _enrich_snapshot_with_admission(snapshot, state, admitted_count=5)

        assert snapshot["admission_queue_depth"] == 5

    def test_snapshot_reflects_ticket_count(self) -> None:
        """AC5.1: admission_tickets reflects outstanding tickets."""
        state = _make_admission_state(cap=200)
        # Enqueue users then admit them to create tickets
        for _ in range(3):
            state.enqueue(uuid4())
        state.admit_batch(admitted_count=0)

        snapshot = self._make_snapshot()
        _enrich_snapshot_with_admission(snapshot, state, admitted_count=42)

        assert snapshot["admission_tickets"] == 3

    def test_update_cap_called_with_lag(self) -> None:
        """_enrich_snapshot_with_admission updates cap based on lag."""
        # High lag should halve the cap
        state = _make_admission_state(cap=200, lag_decrease_ms=200)
        snapshot = self._make_snapshot(lag_ms=300.0)

        _enrich_snapshot_with_admission(snapshot, state, admitted_count=50)

        assert state.cap == 100  # halved from 200
        assert snapshot["admission_cap"] == 100

    def test_admit_batch_runs_during_enrichment(self) -> None:
        """_enrich_snapshot_with_admission admits queued users."""
        state = _make_admission_state(cap=200)
        for _ in range(3):
            state.enqueue(uuid4())

        snapshot = self._make_snapshot()
        # admitted_count=100, cap=200 => 100 available => all 3 admitted
        _enrich_snapshot_with_admission(snapshot, state, admitted_count=100)

        assert snapshot["admission_queue_depth"] == 0
        assert snapshot["admission_tickets"] == 3

    def test_sweep_expired_runs_during_enrichment(self) -> None:
        """_enrich_snapshot_with_admission sweeps expired entries."""
        state = _make_admission_state(cap=200, queue_timeout_seconds=0)
        state.enqueue(uuid4())
        # queue_timeout_seconds=0 means the entry is expired immediately

        snapshot = self._make_snapshot()
        _enrich_snapshot_with_admission(snapshot, state, admitted_count=50)

        assert snapshot["admission_queue_depth"] == 0


class TestDiagnosticLoopAdmissionIntegration:
    """Integration: start_diagnostic_logger logs admission fields."""

    async def test_diagnostic_log_includes_admission_fields(self) -> None:
        """AC5.1: memory_diagnostic structlog event includes all admission fields."""
        from promptgrimoire.admission import init_admission
        from promptgrimoire.config import AdmissionConfig

        config = AdmissionConfig()
        init_admission(config)

        mock_client_class = MagicMock()
        mock_client_class.instances = {}

        # Mock the registry to have a known count
        mock_registry: dict[str, set[str]] = {"user1": {"c1"}, "user2": {"c2", "c3"}}

        with (
            patch("nicegui.Client", mock_client_class),
            patch(
                "promptgrimoire.diagnostics.asyncio.all_tasks",
                return_value=set(),
            ),
            patch(
                "promptgrimoire.diagnostics.measure_event_loop_lag",
                return_value=5.0,
            ),
            patch(
                "promptgrimoire.auth.client_registry._registry",
                mock_registry,
            ),
            capture_logs() as cap_logs,
        ):
            from promptgrimoire.diagnostics import start_diagnostic_logger

            # Run one cycle by cancelling after first iteration
            task = asyncio.create_task(
                start_diagnostic_logger(
                    interval_seconds=0.01,
                    memory_restart_threshold_mb=0,  # disable restart
                )
            )
            await asyncio.sleep(0.05)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        # Find the memory_diagnostic event
        diag_events = [e for e in cap_logs if e.get("event") == "memory_diagnostic"]
        assert len(diag_events) >= 1, (
            f"Expected memory_diagnostic event, got: {cap_logs}"
        )

        event = diag_events[0]
        assert "admission_cap" in event
        assert "admission_admitted" in event
        assert "admission_queue_depth" in event
        assert "admission_tickets" in event
        assert event["admission_admitted"] == 2  # 2 users in registry
