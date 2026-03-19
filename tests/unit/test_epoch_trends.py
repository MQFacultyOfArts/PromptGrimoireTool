"""Tests for compute_trends() and _safe_delta() in analysis.py."""

from __future__ import annotations

import pytest
from scripts.incident.analysis import _safe_delta, compute_trends


def _epoch(
    commit: str,
    *,
    is_crash_bounce: bool = False,
    error_rate: float | None = None,
    rate_5xx: float | None = None,
    memory_peak_bytes: int | None = None,
    mean_cpu: float | None = None,
    active_users: int | None = None,
) -> dict:
    """Build an epoch dict with the fields compute_trends expects."""
    return {
        "commit": commit,
        "is_crash_bounce": is_crash_bounce,
        "error_rate": error_rate,
        "rate_5xx": rate_5xx,
        "memory_peak_bytes": memory_peak_bytes,
        "mean_cpu": mean_cpu,
        "active_users": active_users,
    }


# -- _safe_delta -----------------------------------------------------------


class TestSafeDelta:
    def test_normal_values(self) -> None:
        result = _safe_delta(30.0, 10.0)
        assert result["value"] == 30.0
        assert result["previous"] == 10.0
        assert result["delta"] == 20.0
        assert result["pct_change"] == pytest.approx(200.0)

    def test_current_none(self) -> None:
        result = _safe_delta(None, 10.0)
        assert result["value"] is None
        assert result["previous"] == 10.0
        assert result["delta"] is None
        assert result["pct_change"] is None

    def test_previous_none(self) -> None:
        result = _safe_delta(5.0, None)
        assert result["value"] == 5.0
        assert result["previous"] is None
        assert result["delta"] is None
        assert result["pct_change"] is None

    def test_both_none(self) -> None:
        result = _safe_delta(None, None)
        assert result["delta"] is None
        assert result["pct_change"] is None

    def test_previous_zero(self) -> None:
        """Division by zero yields pct_change=None."""
        result = _safe_delta(5.0, 0.0)
        assert result["delta"] == 5.0
        assert result["pct_change"] is None


# -- compute_trends ---------------------------------------------------------


class TestComputeTrends:
    def test_three_epochs_deltas(self) -> None:
        """Correct deltas and pct_change between consecutive non-crash epochs."""
        epochs = [
            _epoch(
                "aaa",
                error_rate=10.0,
                rate_5xx=2.0,
                memory_peak_bytes=1_000_000_000,
                mean_cpu=10.0,
                active_users=5,
            ),
            _epoch(
                "bbb",
                error_rate=20.0,
                rate_5xx=4.0,
                memory_peak_bytes=1_500_000_000,
                mean_cpu=25.0,
                active_users=8,
            ),
            _epoch(
                "ccc",
                error_rate=30.0,
                rate_5xx=6.0,
                memory_peak_bytes=2_000_000_000,
                mean_cpu=50.0,
                active_users=10,
            ),
        ]

        trends = compute_trends(epochs)

        assert len(trends) == 2
        # First trend: bbb vs aaa
        t0 = trends[0]
        assert t0["epoch_index"] == 1
        assert t0["commit"] == "bbb"
        assert t0["metrics"]["error_rate"]["delta"] == pytest.approx(10.0)
        assert t0["metrics"]["error_rate"]["pct_change"] == pytest.approx(100.0)
        assert t0["metrics"]["memory_peak_bytes"]["delta"] == 500_000_000
        # Second trend: ccc vs bbb
        t1 = trends[1]
        assert t1["epoch_index"] == 2
        assert t1["commit"] == "ccc"
        assert t1["metrics"]["mean_cpu"]["delta"] == pytest.approx(25.0)
        assert t1["metrics"]["mean_cpu"]["pct_change"] == pytest.approx(100.0)

    def test_first_epoch_no_trend(self) -> None:
        """First epoch produces no trend entry."""
        epochs = [
            _epoch("aaa", error_rate=10.0),
        ]
        trends = compute_trends(epochs)
        assert trends == []

    def test_crash_bounce_excluded(self) -> None:
        """Crash-bounce epochs are skipped; trend compares around them."""
        epochs = [
            _epoch(
                "aaa",
                error_rate=10.0,
                rate_5xx=1.0,
                memory_peak_bytes=1_000_000_000,
                mean_cpu=10.0,
                active_users=5,
            ),
            _epoch(
                "bbb",
                is_crash_bounce=True,
                error_rate=99.0,
                rate_5xx=99.0,
                memory_peak_bytes=99,
                mean_cpu=99.0,
                active_users=99,
            ),
            _epoch(
                "ccc",
                error_rate=30.0,
                rate_5xx=3.0,
                memory_peak_bytes=2_000_000_000,
                mean_cpu=30.0,
                active_users=10,
            ),
        ]

        trends = compute_trends(epochs)

        # Only one trend: ccc vs aaa (index 2 in original list)
        assert len(trends) == 1
        t = trends[0]
        assert t["epoch_index"] == 2
        assert t["commit"] == "ccc"
        assert t["metrics"]["error_rate"]["previous"] == pytest.approx(10.0)
        assert t["metrics"]["error_rate"]["delta"] == pytest.approx(20.0)

    def test_none_metric_values(self) -> None:
        """None metric values produce delta=None, pct_change=None, no error."""
        epochs = [
            _epoch("aaa", error_rate=10.0),
            _epoch("bbb", error_rate=None),
        ]

        trends = compute_trends(epochs)

        assert len(trends) == 1
        m = trends[0]["metrics"]["error_rate"]
        assert m["value"] is None
        assert m["previous"] == 10.0
        assert m["delta"] is None
        assert m["pct_change"] is None
        assert m["is_anomaly"] is False

    def test_anomaly_detected(self) -> None:
        """error_rate >100% increase AND current > 5/hr -> is_anomaly=True."""
        epochs = [
            _epoch("aaa", error_rate=10.0),
            _epoch("bbb", error_rate=25.0),  # 150% increase, current > 5
        ]

        trends = compute_trends(epochs)

        assert trends[0]["metrics"]["error_rate"]["is_anomaly"] is True

    def test_anomaly_below_absolute_floor(self) -> None:
        """error_rate >100% increase but current < 5/hr -> is_anomaly=False."""
        epochs = [
            _epoch("aaa", error_rate=1.0),
            _epoch("bbb", error_rate=3.0),  # 200% increase, but current=3 < floor=5
        ]

        trends = compute_trends(epochs)

        assert trends[0]["metrics"]["error_rate"]["is_anomaly"] is False

    def test_active_users_never_anomalous(self) -> None:
        """active_users is never flagged as anomalous regardless of change."""
        epochs = [
            _epoch("aaa", active_users=1),
            _epoch("bbb", active_users=1000),  # massive increase
        ]

        trends = compute_trends(epochs)

        assert trends[0]["metrics"]["active_users"]["is_anomaly"] is False
