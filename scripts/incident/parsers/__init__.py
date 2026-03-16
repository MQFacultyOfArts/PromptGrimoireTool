"""Shared helpers for incident log parsers."""

from __future__ import annotations

from datetime import datetime, timedelta


def in_window(
    ts_utc: str, window_start: str, window_end: str, buffer_minutes: int = 5
) -> bool:
    """Check if a UTC timestamp falls within the window (with buffer on each side).

    Parses ISO 8601 strings, subtracts *buffer_minutes* from start and adds to
    end, then returns whether *ts_utc* is in the expanded range (inclusive).
    """
    ts = datetime.fromisoformat(ts_utc)
    start = datetime.fromisoformat(window_start) - timedelta(minutes=buffer_minutes)
    end = datetime.fromisoformat(window_end) + timedelta(minutes=buffer_minutes)
    return start <= ts <= end
