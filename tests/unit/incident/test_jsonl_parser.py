"""Tests for structlog JSONL parser.

Verifies:
- AC2.4: Timestamp stored as-is (ISO 8601 UTC string matches input)
- AC3.3: user_id, workspace_id, exc_info appear in dedicated dict keys,
         remaining fields in extra_json
- AC3.5: JSONL line with "exc_info": null produces Python None, NOT string "null"
"""

from __future__ import annotations

import json

from scripts.incident.parsers.jsonl import parse_jsonl

# ---------------------------------------------------------------------------
# Fixtures — realistic structlog lines
# ---------------------------------------------------------------------------

_WINDOW_START = "2026-03-16T03:50:00Z"
_WINDOW_END = "2026-03-16T06:20:00Z"


def _line(**overrides: object) -> bytes:
    """Build a single JSONL line with sensible defaults."""
    record: dict[str, object] = {
        "timestamp": "2026-03-16T04:00:00Z",
        "level": "error",
        "event": "database_connection_failed",
        "logger": "promptgrimoire.db",
        "pid": 12345,
        "branch": "main",
        "commit": "a1b2c3d",
        "version": "0.1.0+a1b2c3d",
        "user_id": "user-123",
        "workspace_id": "ws-456",
        "request_path": "/annotation/ws-456",
        "exc_info": "ValueError: connection refused\nTraceback...",
    }
    record.update(overrides)
    return json.dumps(record).encode() + b"\n"


# ---------------------------------------------------------------------------
# AC2.4: Timestamp passthrough
# ---------------------------------------------------------------------------


class TestTimestampPassthrough:
    """AC2.4: Timestamp stored as-is (already UTC)."""

    def test_timestamp_matches_input(self) -> None:
        data = _line(timestamp="2026-03-15T08:42:17.123456Z")
        results = parse_jsonl(data, "2026-03-15T08:00:00Z", "2026-03-15T09:00:00Z")
        assert len(results) == 1
        assert results[0]["ts_utc"] == "2026-03-15T08:42:17.123456Z"

    def test_timestamp_preserved_exactly(self) -> None:
        """No normalisation — whatever the input says, that's what we store."""
        ts = "2026-03-16T04:00:00.000000Z"
        data = _line(timestamp=ts)
        results = parse_jsonl(data, _WINDOW_START, _WINDOW_END)
        assert results[0]["ts_utc"] == ts


# ---------------------------------------------------------------------------
# AC3.3: Field extraction
# ---------------------------------------------------------------------------


class TestFieldExtraction:
    """AC3.3: Dedicated columns extracted; remainder in extra_json."""

    def test_dedicated_fields_extracted(self) -> None:
        data = _line()
        results = parse_jsonl(data, _WINDOW_START, _WINDOW_END)
        assert len(results) == 1
        row = results[0]
        assert row["level"] == "error"
        assert row["event"] == "database_connection_failed"
        assert row["user_id"] == "user-123"
        assert row["workspace_id"] == "ws-456"
        assert row["request_path"] == "/annotation/ws-456"
        assert row["exc_info"] == "ValueError: connection refused\nTraceback..."

    def test_extra_json_contains_remaining_fields(self) -> None:
        data = _line()
        results = parse_jsonl(data, _WINDOW_START, _WINDOW_END)
        extra = json.loads(results[0]["extra_json"])
        assert extra["logger"] == "promptgrimoire.db"
        assert extra["pid"] == 12345
        assert extra["branch"] == "main"
        assert extra["commit"] == "a1b2c3d"
        assert extra["version"] == "0.1.0+a1b2c3d"

    def test_extra_json_excludes_extracted_fields(self) -> None:
        data = _line()
        results = parse_jsonl(data, _WINDOW_START, _WINDOW_END)
        extra = json.loads(results[0]["extra_json"])
        # These 7 fields should NOT appear in extra_json
        for key in (
            "timestamp",
            "level",
            "event",
            "user_id",
            "workspace_id",
            "request_path",
            "exc_info",
        ):
            assert key not in extra, f"{key} should not be in extra_json"

    def test_missing_optional_fields_are_none(self) -> None:
        """Lines without user_id etc. should store None."""
        minimal = (
            json.dumps(
                {
                    "timestamp": "2026-03-16T04:00:00Z",
                    "level": "info",
                    "event": "startup",
                }
            ).encode()
            + b"\n"
        )
        results = parse_jsonl(minimal, _WINDOW_START, _WINDOW_END)
        row = results[0]
        assert row["user_id"] is None
        assert row["workspace_id"] is None
        assert row["request_path"] is None
        assert row["exc_info"] is None

    def test_custom_bindings_go_to_extra_json(self) -> None:
        """Arbitrary structlog bindings end up in extra_json."""
        data = _line(custom_field="hello", another_thing=42)
        results = parse_jsonl(data, _WINDOW_START, _WINDOW_END)
        extra = json.loads(results[0]["extra_json"])
        assert extra["custom_field"] == "hello"
        assert extra["another_thing"] == 42


# ---------------------------------------------------------------------------
# AC3.5: exc_info null handling
# ---------------------------------------------------------------------------


class TestExcInfoNull:
    """AC3.5: JSON null → Python None, not string 'null'."""

    def test_exc_info_null_is_python_none(self) -> None:
        data = _line(exc_info=None)
        results = parse_jsonl(data, _WINDOW_START, _WINDOW_END)
        assert results[0]["exc_info"] is None

    def test_exc_info_absent_is_python_none(self) -> None:
        """Key missing entirely → also None."""
        record = {
            "timestamp": "2026-03-16T04:00:00Z",
            "level": "info",
            "event": "test",
        }
        data = json.dumps(record).encode() + b"\n"
        results = parse_jsonl(data, _WINDOW_START, _WINDOW_END)
        assert results[0]["exc_info"] is None

    def test_exc_info_string_preserved(self) -> None:
        data = _line(exc_info="RuntimeError: boom")
        results = parse_jsonl(data, _WINDOW_START, _WINDOW_END)
        assert results[0]["exc_info"] == "RuntimeError: boom"


# ---------------------------------------------------------------------------
# Time-window filtering
# ---------------------------------------------------------------------------


class TestTimeWindowFiltering:
    def test_event_inside_window_included(self) -> None:
        data = _line(timestamp="2026-03-16T04:00:00Z")
        results = parse_jsonl(data, _WINDOW_START, _WINDOW_END)
        assert len(results) == 1

    def test_event_outside_window_excluded(self) -> None:
        data = _line(timestamp="2026-03-16T01:00:00Z")
        results = parse_jsonl(data, _WINDOW_START, _WINDOW_END)
        assert len(results) == 0

    def test_event_in_buffer_zone_included(self) -> None:
        """5-minute buffer: event at 03:47 is within 5 min of start 03:50."""
        data = _line(timestamp="2026-03-16T03:47:00Z")
        results = parse_jsonl(data, _WINDOW_START, _WINDOW_END)
        assert len(results) == 1

    def test_event_outside_buffer_excluded(self) -> None:
        """Event at 03:44 is outside the 5-min buffer before 03:50."""
        data = _line(timestamp="2026-03-16T03:44:00Z")
        results = parse_jsonl(data, _WINDOW_START, _WINDOW_END)
        assert len(results) == 0

    def test_event_after_end_buffer_included(self) -> None:
        """5-minute buffer after end: event at 06:23 is within buffer of 06:20."""
        data = _line(timestamp="2026-03-16T06:23:00Z")
        results = parse_jsonl(data, _WINDOW_START, _WINDOW_END)
        assert len(results) == 1

    def test_event_after_end_buffer_excluded(self) -> None:
        """Event at 06:26 is outside the 5-min buffer after 06:20."""
        data = _line(timestamp="2026-03-16T06:26:00Z")
        results = parse_jsonl(data, _WINDOW_START, _WINDOW_END)
        assert len(results) == 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_input_returns_empty(self) -> None:
        assert parse_jsonl(b"", _WINDOW_START, _WINDOW_END) == []

    def test_blank_lines_skipped(self) -> None:
        data = b"\n\n" + _line() + b"\n\n"
        results = parse_jsonl(data, _WINDOW_START, _WINDOW_END)
        assert len(results) == 1

    def test_malformed_json_skipped(self) -> None:
        good = _line()
        data = b"not json{{\n" + good
        results = parse_jsonl(data, _WINDOW_START, _WINDOW_END)
        assert len(results) == 1

    def test_multiple_lines(self) -> None:
        lines = (
            _line(timestamp="2026-03-16T04:00:00Z", event="first")
            + _line(timestamp="2026-03-16T04:01:00Z", event="second")
            + _line(timestamp="2026-03-16T04:02:00Z", event="third")
        )
        results = parse_jsonl(lines, _WINDOW_START, _WINDOW_END)
        assert len(results) == 3
        assert [r["event"] for r in results] == ["first", "second", "third"]

    def test_missing_timestamp_skipped(self) -> None:
        """Lines without timestamp field are skipped."""
        bad = json.dumps({"level": "info", "event": "no_ts"}).encode() + b"\n"
        good = _line()
        data = bad + good
        results = parse_jsonl(data, _WINDOW_START, _WINDOW_END)
        assert len(results) == 1
