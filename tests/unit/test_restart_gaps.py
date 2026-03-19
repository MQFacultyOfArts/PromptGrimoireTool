"""Tests for enrich_restart_gaps() downtime duration computation."""

from __future__ import annotations

from scripts.incident.analysis import enrich_restart_gaps


class TestEnrichRestartGaps:
    def test_first_epoch_none(self) -> None:
        """AC4.2: First epoch has restart_gap_seconds = None."""
        epochs = [
            {"start_utc": "2026-03-15T10:00:00Z", "end_utc": "2026-03-15T12:00:00Z"}
        ]
        enrich_restart_gaps(epochs)
        assert epochs[0]["restart_gap_seconds"] is None

    def test_gap_computed(self) -> None:
        """AC4.1: Gap is difference between epoch 2 start and epoch 1 end."""
        epochs = [
            {"start_utc": "2026-03-15T10:00:00Z", "end_utc": "2026-03-15T12:00:00Z"},
            {"start_utc": "2026-03-15T12:05:00Z", "end_utc": "2026-03-15T14:00:00Z"},
        ]
        enrich_restart_gaps(epochs)
        assert epochs[0]["restart_gap_seconds"] is None
        assert epochs[1]["restart_gap_seconds"] == 300.0  # 5 minutes

    def test_zero_gap(self) -> None:
        """AC4.3: Immediate restart has restart_gap_seconds == 0."""
        epochs = [
            {"start_utc": "2026-03-15T10:00:00Z", "end_utc": "2026-03-15T12:00:00Z"},
            {"start_utc": "2026-03-15T12:00:00Z", "end_utc": "2026-03-15T14:00:00Z"},
        ]
        enrich_restart_gaps(epochs)
        assert epochs[1]["restart_gap_seconds"] == 0.0

    def test_multiple_epochs(self) -> None:
        """Each gap computed from correct predecessor pair."""
        epochs = [
            {"start_utc": "2026-03-15T10:00:00Z", "end_utc": "2026-03-15T11:00:00Z"},
            {"start_utc": "2026-03-15T11:02:00Z", "end_utc": "2026-03-15T12:00:00Z"},
            {"start_utc": "2026-03-15T12:10:00Z", "end_utc": "2026-03-15T13:00:00Z"},
        ]
        enrich_restart_gaps(epochs)
        assert epochs[0]["restart_gap_seconds"] is None
        assert epochs[1]["restart_gap_seconds"] == 120.0  # 2 minutes
        assert epochs[2]["restart_gap_seconds"] == 600.0  # 10 minutes
