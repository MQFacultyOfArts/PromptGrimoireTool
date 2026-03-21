"""Tests for PostgreSQL log parsers (text + JSON formats).

Verifies:
- AC3.2: Multi-line entries (ERROR + DETAIL + STATEMENT) grouped into single rows
- Text format: timestamp stored as-is (already UTC), PID extraction, level extraction
- Text format: single-line FATAL produces one event with no detail/statement
- Text format: different PIDs produce separate events
- JSON format: field extraction from jsonlog entries
- JSON format: timestamp "2026-03-16 04:32:52.000 GMT" converts to ISO 8601 UTC
- JSON format: missing detail/statement fields store None
- Time-window filtering works for both parsers
"""

from __future__ import annotations

import json

from scripts.incident.parsers.pglog import parse_pglog_json, parse_pglog_text

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

WINDOW_START = "2026-03-16T04:00:00+00:00"
WINDOW_END = "2026-03-16T06:00:00+00:00"

# Realistic multi-line PG text log (ERROR + DETAIL + STATEMENT, same PID)
_ERR = (
    "2026-03-16 04:32:52.000 UTC [1234] ERROR:"
    "  duplicate key value violates unique constraint"
    ' "uq_tag_workspace_name"\n'
)
_DETAIL = (
    "2026-03-16 04:32:52.000 UTC [1234] DETAIL:"
    "  Key (workspace_id, name)="
    "(dbf5feaa-1234-5678-9abc-def012345678,"
    " Important Info) already exists.\n"
)
_STMT = (
    "2026-03-16 04:32:52.000 UTC [1234] STATEMENT:"
    "  INSERT INTO tag (id, workspace_id, name)"
    " VALUES ($1, $2, $3)\n"
)
PG_TEXT_MULTILINE = _ERR + _DETAIL + _STMT

PG_TEXT_FATAL = "2026-03-16 04:50:16.000 UTC [5678] FATAL:  connection to client lost\n"

PG_TEXT_MIXED = PG_TEXT_MULTILINE + PG_TEXT_FATAL


# ---------------------------------------------------------------------------
# Text format parser tests
# ---------------------------------------------------------------------------


class TestTextMultiLineGrouping:
    """AC3.2: Multi-line entries grouped into single rows."""

    def test_error_detail_statement_grouped(self) -> None:
        result = parse_pglog_text(PG_TEXT_MULTILINE.encode(), WINDOW_START, WINDOW_END)

        assert len(result) == 1
        event = result[0]
        assert event["level"] == "ERROR"
        assert "duplicate key" in event["error_type"]
        assert event["detail"] is not None
        assert "workspace_id, name" in event["detail"]
        assert event["statement"] is not None
        assert "INSERT INTO tag" in event["statement"]

    def test_message_contains_all_text(self) -> None:
        result = parse_pglog_text(PG_TEXT_MULTILINE.encode(), WINDOW_START, WINDOW_END)

        event = result[0]
        assert "duplicate key" in event["message"]
        assert "Key (workspace_id" in event["message"]
        assert "INSERT INTO tag" in event["message"]


class TestTextSingleLine:
    """Single-line entries produce one event with no detail/statement."""

    def test_fatal_no_detail_statement(self) -> None:
        result = parse_pglog_text(PG_TEXT_FATAL.encode(), WINDOW_START, WINDOW_END)

        assert len(result) == 1
        event = result[0]
        assert event["level"] == "FATAL"
        assert "connection to client lost" in event["error_type"]
        assert event["detail"] is None
        assert event["statement"] is None


class TestTextSeparatePIDs:
    """Different PIDs produce separate events."""

    def test_two_pids_two_events(self) -> None:
        result = parse_pglog_text(PG_TEXT_MIXED.encode(), WINDOW_START, WINDOW_END)

        assert len(result) == 2
        levels = {e["level"] for e in result}
        assert levels == {"ERROR", "FATAL"}

    def test_pids_extracted_correctly(self) -> None:
        result = parse_pglog_text(PG_TEXT_MIXED.encode(), WINDOW_START, WINDOW_END)

        pids = {e["pid"] for e in result}
        assert pids == {1234, 5678}


class TestTextTimestamp:
    """PG text timestamps are already UTC -- stored as-is."""

    def test_timestamp_stored_as_utc(self) -> None:
        result = parse_pglog_text(PG_TEXT_FATAL.encode(), WINDOW_START, WINDOW_END)

        ts = result[0]["ts_utc"]
        assert "2026-03-16" in ts
        assert "04:50:16" in ts


class TestTextTimeWindowFiltering:
    """Time-window filtering excludes events outside the window."""

    def test_event_inside_window(self) -> None:
        result = parse_pglog_text(PG_TEXT_FATAL.encode(), WINDOW_START, WINDOW_END)
        assert len(result) == 1

    def test_event_outside_window(self) -> None:
        # Window is 04:00-06:00, event at 04:50 is inside
        # Use a window that excludes the event
        result = parse_pglog_text(
            PG_TEXT_FATAL.encode(),
            "2026-03-16T01:00:00+00:00",
            "2026-03-16T02:00:00+00:00",
        )
        assert len(result) == 0


class TestTextEdgeCases:
    """Edge cases for text parser."""

    def test_empty_input(self) -> None:
        result = parse_pglog_text(b"", WINDOW_START, WINDOW_END)
        assert result == []

    def test_blank_lines_skipped(self) -> None:
        data = f"\n\n{PG_TEXT_FATAL}\n\n".encode()
        result = parse_pglog_text(data, WINDOW_START, WINDOW_END)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# JSON format parser tests
# ---------------------------------------------------------------------------


def _make_pg_json_line(
    timestamp: str = "2026-03-16 04:32:52.000 GMT",
    pid: int = 1234,
    error_severity: str = "ERROR",
    message: str = (
        'duplicate key value violates unique constraint "uq_tag_workspace_name"'
    ),
    detail: str | None = None,
    statement: str | None = None,
) -> str:
    record: dict[str, object] = {
        "timestamp": timestamp,
        "pid": pid,
        "error_severity": error_severity,
        "message": message,
    }
    if detail is not None:
        record["detail"] = detail
    if statement is not None:
        record["statement"] = statement
    return json.dumps(record)


class TestJsonFieldExtraction:
    """JSON format extracts fields correctly."""

    def test_all_fields_extracted(self) -> None:
        line = _make_pg_json_line(
            detail="Key (workspace_id, name) already exists.",
            statement="INSERT INTO tag VALUES ($1, $2)",
        )
        result = parse_pglog_json(line.encode(), WINDOW_START, WINDOW_END)

        assert len(result) == 1
        event = result[0]
        assert event["pid"] == 1234
        assert event["level"] == "ERROR"
        assert "duplicate key" in event["error_type"]
        assert "already exists" in event["detail"]
        assert "INSERT INTO tag" in event["statement"]


class TestJsonTimestamp:
    """PG jsonlog timestamp conversion."""

    def test_gmt_timestamp_to_iso8601(self) -> None:
        line = _make_pg_json_line(timestamp="2026-03-16 04:32:52.000 GMT")
        result = parse_pglog_json(line.encode(), WINDOW_START, WINDOW_END)

        ts = result[0]["ts_utc"]
        assert "2026-03-16" in ts
        assert "04:32:52" in ts
        # Must indicate UTC
        assert "+00:00" in ts or "Z" in ts


class TestJsonMissingFields:
    """Entries without detail/statement store None."""

    def test_no_detail_no_statement(self) -> None:
        line = _make_pg_json_line()  # No detail or statement
        result = parse_pglog_json(line.encode(), WINDOW_START, WINDOW_END)

        assert len(result) == 1
        assert result[0]["detail"] is None
        assert result[0]["statement"] is None


class TestJsonTimeWindowFiltering:
    """Time-window filtering works for JSON format."""

    def test_event_inside_window(self) -> None:
        line = _make_pg_json_line(timestamp="2026-03-16 05:00:00.000 GMT")
        result = parse_pglog_json(line.encode(), WINDOW_START, WINDOW_END)
        assert len(result) == 1

    def test_event_outside_window(self) -> None:
        line = _make_pg_json_line(timestamp="2026-03-16 12:00:00.000 GMT")
        result = parse_pglog_json(line.encode(), WINDOW_START, WINDOW_END)
        assert len(result) == 0


class TestJsonEdgeCases:
    """Edge cases for JSON parser."""

    def test_empty_input(self) -> None:
        result = parse_pglog_json(b"", WINDOW_START, WINDOW_END)
        assert result == []

    def test_malformed_json_skipped(self) -> None:
        good = _make_pg_json_line()
        data = f"not json\n{good}\n".encode()
        result = parse_pglog_json(data, WINDOW_START, WINDOW_END)
        assert len(result) == 1

    def test_message_field_populated(self) -> None:
        """message field contains the full message text."""
        line = _make_pg_json_line(
            message="some error",
            detail="some detail",
            statement="SELECT 1",
        )
        result = parse_pglog_json(line.encode(), WINDOW_START, WINDOW_END)
        event = result[0]
        # message should contain the original message text
        assert "some error" in event["message"]
