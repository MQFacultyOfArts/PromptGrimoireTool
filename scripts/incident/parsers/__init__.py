"""Shared helpers for incident log parsers."""

from __future__ import annotations

from datetime import UTC, datetime


def normalise_utc(ts: datetime) -> str:
    """Convert to UTC and produce canonical ``YYYY-MM-DDTHH:MM:SS.ffffffZ``.

    Converts the input to UTC first, then formats with Z suffix.
    """
    utc_dt = ts.astimezone(UTC)
    return utc_dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def in_window(ts_utc: str, window_start: str, window_end: str) -> bool:
    """Check if a UTC timestamp falls within the window (inclusive).

    Parses ISO 8601 strings and returns whether *ts_utc* is in the range.
    """
    ts = datetime.fromisoformat(ts_utc)
    start = datetime.fromisoformat(window_start)
    end = datetime.fromisoformat(window_end)
    return start <= ts <= end
