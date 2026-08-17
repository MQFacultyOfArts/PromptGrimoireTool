"""Tests for scripts/profile_workspace.py's pure statistics helper.

``_compute_stats`` is the one function in this Playwright-driven profiling
script that has no browser/server dependency, so it's the only part
covered here. It backs the ``_MIN_VALUES_FOR_STDEV`` threshold introduced
when naming the PLR2004 magic value (see
``docs/design-plans/2026-04-23-ty-sa-typing-cleanup.md``).
"""

from __future__ import annotations

from scripts.profile_workspace import _compute_stats


def test_compute_stats_omits_stdev_below_threshold() -> None:
    """A single value has no stdev; two or more values do."""
    single = _compute_stats([42.0])
    assert single["count"] == 1
    assert single["mean"] == 42.0
    assert "stdev" not in single

    pair = _compute_stats([10.0, 20.0])
    assert pair["count"] == 2
    assert pair["mean"] == 15.0
    assert pair["stdev"] == 7.1


def test_compute_stats_empty_input() -> None:
    """Empty input yields an empty stats dict, not an error."""
    assert _compute_stats([]) == {}
