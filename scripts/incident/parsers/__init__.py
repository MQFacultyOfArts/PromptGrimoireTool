"""Shared helpers for incident log parsers."""

from __future__ import annotations

from datetime import datetime


def normalise_utc(ts: datetime) -> str:
    """Produce canonical ``YYYY-MM-DDTHH:MM:SS.ffffffZ`` format.

    Strips any tzinfo offset representation and always uses trailing ``Z``.
    """
    return ts.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def in_window(ts_utc: str, window_start: str, window_end: str) -> bool:
    """Check if a UTC timestamp falls within the window (inclusive).

    Parses ISO 8601 strings and returns whether *ts_utc* is in the range.
    """
    ts = datetime.fromisoformat(ts_utc)
    start = datetime.fromisoformat(window_start)
    end = datetime.fromisoformat(window_end)
    return start <= ts <= end
