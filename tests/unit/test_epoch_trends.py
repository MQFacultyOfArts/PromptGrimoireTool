"""Tests for compute_trends() and _safe_delta() in analysis.py."""

from __future__ import annotations

import pytest
from scripts.incident.analysis import _safe_delta, compute_trends


def _epoch(
    commit: str,
    *,
    is_crash_bounce: bool = False,
    error_ratio: float | None = None,
    warning_ratio: float | None = None,
    five_xx_ratio: float | None = None,
    memory_peak_bytes: int | None = None,
    mean_cpu: float | None = None,
    active_users: int | None = None,
    total_requests: int = 0,
    pr_title: str = "",
) -> dict:
    """Build an epoch dict with the fields compute_trends expects."""
    return {
        "commit": commit,
        "is_crash_bounce": is_crash_bounce,
        "error_ratio": error_ratio,
        "warning_ratio": warning_ratio,
        "5xx_ratio": five_xx_ratio,
        "memory_peak_bytes": memory_peak_bytes,
        "mean_cpu": mean_cpu,
        "active_users": active_users,
        "total_requests": total_requests,
        "pr_title": pr_title,
    }


# -- _safe_delta -----------------------------------------------------------


class TestSafeDelta:
    def test_normal_values(self) -> None:
        result = _safe_delta(30.0, 10.0)
        assert result["value"] == 30.0
        assert result["previous"] == 10.0
        assert result["delta"] == 20.0

    def test_no_pct_change(self) -> None:
        """_safe_delta does not return pct_change."""
        result = _safe_delta(30.0, 10.0)
        assert "pct_change" not in result

    def test_current_none(self) -> None:
        result = _safe_delta(None, 10.0)
        assert result["delta"] is None

    def test_previous_none(self) -> None:
        result = _safe_delta(5.0, None)
        assert result["delta"] is None

    def test_both_none(self) -> None:
        result = _safe_delta(None, None)
        assert result["delta"] is None


# -- compute_trends ---------------------------------------------------------


class TestComputeTrends:
    def test_three_epochs_deltas(self) -> None:
        """Correct deltas between consecutive non-crash epochs."""
        epochs = [
            _epoch(
                "aaa",
                error_ratio=0.01,
                warning_ratio=0.05,
                five_xx_ratio=0.002,
                mean_cpu=10.0,
                active_users=5,
                total_requests=10000,
            ),
            _epoch(
                "bbb",
                error_ratio=0.02,
                warning_ratio=0.03,
                five_xx_ratio=0.004,
                mean_cpu=25.0,
                active_users=8,
                total_requests=20000,
            ),
            _epoch(
                "ccc",
                error_ratio=0.005,
                warning_ratio=0.02,
                five_xx_ratio=0.001,
                mean_cpu=15.0,
                active_users=10,
                total_requests=30000,
            ),
        ]

        trends = compute_trends(epochs)

        assert len(trends) == 2
        t0 = trends[0]
        assert t0["commit"] == "bbb"
        assert t0["metrics"]["error_ratio"]["delta"] == pytest.approx(0.01)
        assert t0["total_requests"] == 20000
        t1 = trends[1]
        assert t1["metrics"]["error_ratio"]["delta"] == pytest.approx(-0.015)

    def test_first_epoch_no_trend(self) -> None:
        epochs = [_epoch("aaa", error_ratio=0.01)]
        assert compute_trends(epochs) == []

    def test_crash_bounce_excluded(self) -> None:
        epochs = [
            _epoch("aaa", error_ratio=0.01),
            _epoch("bbb", is_crash_bounce=True, error_ratio=0.99),
            _epoch("ccc", error_ratio=0.02),
        ]
        trends = compute_trends(epochs)
        assert len(trends) == 1
        assert trends[0]["commit"] == "ccc"
        assert trends[0]["metrics"]["error_ratio"]["previous"] == pytest.approx(0.01)

    def test_none_metric_values(self) -> None:
        epochs = [
            _epoch("aaa", error_ratio=0.01),
            _epoch("bbb", error_ratio=None),
        ]
        trends = compute_trends(epochs)
        m = trends[0]["metrics"]["error_ratio"]
        assert m["delta"] is None
        assert m["is_anomaly"] is False

    def test_anomaly_above_floor(self) -> None:
        """error_ratio > 5% floor -> is_anomaly=True."""
        epochs = [
            _epoch("aaa", error_ratio=0.01),
            _epoch("bbb", error_ratio=0.08),  # 8% > 5% floor
        ]
        trends = compute_trends(epochs)
        assert trends[0]["metrics"]["error_ratio"]["is_anomaly"] is True

    def test_anomaly_below_floor(self) -> None:
        """error_ratio < 5% floor -> is_anomaly=False."""
        epochs = [
            _epoch("aaa", error_ratio=0.01),
            _epoch("bbb", error_ratio=0.03),  # 3% < 5% floor
        ]
        trends = compute_trends(epochs)
        assert trends[0]["metrics"]["error_ratio"]["is_anomaly"] is False

    def test_5xx_anomaly(self) -> None:
        """5xx_ratio > 1% floor -> is_anomaly=True."""
        epochs = [
            _epoch("aaa", five_xx_ratio=0.001),
            _epoch("bbb", five_xx_ratio=0.02),  # 2% > 1% floor
        ]
        trends = compute_trends(epochs)
        assert trends[0]["metrics"]["5xx_ratio"]["is_anomaly"] is True

    def test_active_users_never_anomalous(self) -> None:
        epochs = [
            _epoch("aaa", active_users=1),
            _epoch("bbb", active_users=1000),
        ]
        trends = compute_trends(epochs)
        assert trends[0]["metrics"]["active_users"]["is_anomaly"] is False

    def test_warning_ratio_never_anomalous(self) -> None:
        epochs = [
            _epoch("aaa", warning_ratio=0.001),
            _epoch("bbb", warning_ratio=0.50),  # 50% warnings
        ]
        trends = compute_trends(epochs)
        assert trends[0]["metrics"]["warning_ratio"]["is_anomaly"] is False

    def test_pr_title_and_total_requests_included(self) -> None:
        epochs = [
            _epoch("aaa", error_ratio=0.01, pr_title="Fix login", total_requests=5000),
            _epoch(
                "bbb", error_ratio=0.02, pr_title="Add feature", total_requests=8000
            ),
        ]
        trends = compute_trends(epochs)
        assert trends[0]["pr_title"] == "Add feature"
        assert trends[0]["total_requests"] == 8000
