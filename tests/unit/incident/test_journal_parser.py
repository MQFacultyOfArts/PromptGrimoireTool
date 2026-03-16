"""Tests for systemd journal JSON parser.

Verifies:
- AC2.2: __REALTIME_TIMESTAMP (µs epoch) converts to correct ISO 8601 UTC in ts_utc
- Correct field extraction (priority as int, pid as int, message, unit)
- raw_json contains the full original JSON line
- Time-window filtering excludes events outside the window (exact boundary, no buffer)
- Empty input returns empty list
- Lines with missing __REALTIME_TIMESTAMP are skipped (not fatal)
"""

from __future__ import annotations

import json

from scripts.incident.parsers.journal import parse_journal

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_journal_line(
    ts_us: int = 1710536535123456,
    priority: int = 6,
    pid: int = 1234,
    unit: str = "promptgrimoire.service",
    message: str = "Started service",
    **extra: object,
) -> str:
    """Build a single journal JSON line."""
    record: dict[str, object] = {
        "__REALTIME_TIMESTAMP": str(ts_us),
        "PRIORITY": str(priority),
        "_PID": str(pid),
        "_SYSTEMD_UNIT": unit,
        "MESSAGE": message,
        **extra,
    }
    return json.dumps(record)


def _ts_us_from_iso(iso_str: str) -> int:
    """Convert ISO 8601 UTC to microseconds epoch (for building fixtures)."""
    from datetime import UTC, datetime

    dt = datetime.fromisoformat(iso_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return int(dt.timestamp() * 1_000_000)


# The reference timestamp from the plan: 1710536535123456 µs
# Actual UTC: 2024-03-15T21:02:15.123456+00:00
# (Plan stated 2024-03-16T00:42:15 which was AEST, not UTC.)
WINDOW_START = "2024-03-15T20:00:00+00:00"
WINDOW_END = "2024-03-15T22:00:00+00:00"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestTimestampConversion:
    """AC2.2: __REALTIME_TIMESTAMP converts to correct ISO 8601 UTC."""

    def test_microsecond_precision(self) -> None:
        line = _make_journal_line(ts_us=1710536535123456)
        data = line.encode()

        result = parse_journal(data, WINDOW_START, WINDOW_END)

        assert len(result) == 1
        ts = result[0]["ts_utc"]
        # Must contain the correct date/time with microseconds
        assert ts.startswith("2024-03-15T21:02:15.123456")
        assert ts.endswith("Z")

    def test_whole_second_timestamp(self) -> None:
        ts_us = _ts_us_from_iso("2024-03-15T21:30:00+00:00")
        line = _make_journal_line(ts_us=ts_us)
        data = line.encode()

        result = parse_journal(data, WINDOW_START, WINDOW_END)

        assert len(result) == 1
        assert "2024-03-15T21:30:00" in result[0]["ts_utc"]


class TestFieldExtraction:
    """Parser extracts fields with correct types."""

    def test_priority_as_int(self) -> None:
        line = _make_journal_line(priority=3)
        result = parse_journal(line.encode(), WINDOW_START, WINDOW_END)

        assert result[0]["priority"] == 3
        assert isinstance(result[0]["priority"], int)

    def test_pid_as_int(self) -> None:
        line = _make_journal_line(pid=9876)
        result = parse_journal(line.encode(), WINDOW_START, WINDOW_END)

        assert result[0]["pid"] == 9876
        assert isinstance(result[0]["pid"], int)

    def test_message_extracted(self) -> None:
        line = _make_journal_line(message="OOM killer invoked")
        result = parse_journal(line.encode(), WINDOW_START, WINDOW_END)

        assert result[0]["message"] == "OOM killer invoked"

    def test_unit_extracted(self) -> None:
        line = _make_journal_line(unit="postgresql.service")
        result = parse_journal(line.encode(), WINDOW_START, WINDOW_END)

        assert result[0]["unit"] == "postgresql.service"

    def test_raw_json_contains_full_line(self) -> None:
        line = _make_journal_line(SYSLOG_IDENTIFIER="systemd")
        result = parse_journal(line.encode(), WINDOW_START, WINDOW_END)

        raw = json.loads(result[0]["raw_json"])
        assert raw["SYSLOG_IDENTIFIER"] == "systemd"
        assert raw["__REALTIME_TIMESTAMP"] == "1710536535123456"
        assert raw["MESSAGE"] == "Started service"


class TestTimeWindowFiltering:
    """Events outside the window are excluded (exact boundary, no buffer)."""

    def test_event_inside_window(self) -> None:
        ts_us = _ts_us_from_iso("2024-03-15T21:00:00+00:00")
        line = _make_journal_line(ts_us=ts_us)

        result = parse_journal(line.encode(), WINDOW_START, WINDOW_END)
        assert len(result) == 1

    def test_event_outside_window(self) -> None:
        # 4 hours before window start -- well outside buffer
        ts_us = _ts_us_from_iso("2024-03-15T16:00:00+00:00")
        line = _make_journal_line(ts_us=ts_us)

        result = parse_journal(line.encode(), WINDOW_START, WINDOW_END)
        assert len(result) == 0

    def test_event_just_before_start_excluded(self) -> None:
        """Event 3 minutes before window_start is excluded (no buffer)."""
        ts_us = _ts_us_from_iso("2024-03-15T19:57:00+00:00")
        line = _make_journal_line(ts_us=ts_us)

        result = parse_journal(line.encode(), WINDOW_START, WINDOW_END)
        assert len(result) == 0

    def test_event_just_after_end_excluded(self) -> None:
        """Event 3 minutes after window_end is excluded (no buffer)."""
        ts_us = _ts_us_from_iso("2024-03-15T22:03:00+00:00")
        line = _make_journal_line(ts_us=ts_us)

        result = parse_journal(line.encode(), WINDOW_START, WINDOW_END)
        assert len(result) == 0

    def test_event_well_outside_window_excluded(self) -> None:
        """Event 10 minutes after window_end is excluded."""
        ts_us = _ts_us_from_iso("2024-03-15T22:10:00+00:00")
        line = _make_journal_line(ts_us=ts_us)

        result = parse_journal(line.encode(), WINDOW_START, WINDOW_END)
        assert len(result) == 0

    def test_multiple_lines_filters_correctly(self) -> None:
        inside = _make_journal_line(
            ts_us=_ts_us_from_iso("2024-03-15T21:00:00+00:00"),
            message="inside",
        )
        outside = _make_journal_line(
            ts_us=_ts_us_from_iso("2024-03-15T16:00:00+00:00"),
            message="outside",
        )
        data = f"{inside}\n{outside}\n".encode()

        result = parse_journal(data, WINDOW_START, WINDOW_END)
        assert len(result) == 1
        assert result[0]["message"] == "inside"


class TestEdgeCases:
    """Empty input, missing fields, malformed lines."""

    def test_empty_input(self) -> None:
        result = parse_journal(b"", WINDOW_START, WINDOW_END)
        assert result == []

    def test_blank_lines_skipped(self) -> None:
        line = _make_journal_line()
        data = f"\n\n{line}\n\n".encode()

        result = parse_journal(data, WINDOW_START, WINDOW_END)
        assert len(result) == 1

    def test_missing_realtime_timestamp_skipped(self) -> None:
        """Lines without __REALTIME_TIMESTAMP are skipped, not fatal."""
        bad_line = json.dumps({"MESSAGE": "no timestamp", "PRIORITY": "6"})
        good_line = _make_journal_line(message="has timestamp")
        data = f"{bad_line}\n{good_line}\n".encode()

        result = parse_journal(data, WINDOW_START, WINDOW_END)
        assert len(result) == 1
        assert result[0]["message"] == "has timestamp"

    def test_malformed_json_skipped(self) -> None:
        good_line = _make_journal_line()
        data = f"not json at all\n{good_line}\n".encode()

        result = parse_journal(data, WINDOW_START, WINDOW_END)
        assert len(result) == 1

    def test_missing_optional_fields_none(self) -> None:
        """Missing PRIORITY, _PID, _SYSTEMD_UNIT, MESSAGE produce None."""
        record = {"__REALTIME_TIMESTAMP": "1710536535123456"}
        data = json.dumps(record).encode()

        result = parse_journal(data, WINDOW_START, WINDOW_END)
        assert len(result) == 1
        assert result[0]["priority"] is None
        assert result[0]["pid"] is None
        assert result[0]["unit"] is None
        assert result[0]["message"] is None
