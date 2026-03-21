"""RED tests — expose known bugs before fixing them.

Each test documents a specific bug found during review.
All tests in this file should FAIL against the current code.
After fixes, they should pass (GREEN).
"""

from __future__ import annotations

from scripts.incident.parsers import in_window
from scripts.incident.parsers.journal import parse_journal
from scripts.incident.parsers.jsonl import parse_jsonl
from scripts.incident.provenance import format_to_table


class TestBugTimestampFormatMismatch:
    """Bug: parsers produce mixed ts_utc formats that mis-sort.

    Journal uses +00:00, JSONL passes through raw (Z suffix).
    String comparison of Z vs +00:00 misorders timeline because
    '+' (0x2B) sorts before 'Z' (0x5A) in ASCII.
    """

    def test_journal_and_jsonl_produce_same_format(self) -> None:
        """Both parsers must produce identically-formatted ts_utc."""
        journal_line = (
            '{"__REALTIME_TIMESTAMP":"1710536535000000",'
            '"PRIORITY":"6","_PID":"1","MESSAGE":"test"}\n'
        )
        jsonl_line = (
            '{"timestamp":"2024-03-15T21:02:15.000000Z",'
            '"level":"info","event":"test"}\n'
        )
        window_start = "2024-03-15T20:00:00Z"
        window_end = "2024-03-15T22:00:00Z"

        journal_events = parse_journal(journal_line.encode(), window_start, window_end)
        jsonl_events = parse_jsonl(jsonl_line.encode(), window_start, window_end)

        assert len(journal_events) == 1
        assert len(jsonl_events) == 1

        j_ts = journal_events[0]["ts_utc"]
        jl_ts = jsonl_events[0]["ts_utc"]

        # Both must end with Z (not +00:00) for consistent string sort
        assert j_ts.endswith("Z"), f"journal ts_utc ends with wrong suffix: {j_ts}"
        assert jl_ts.endswith("Z"), f"jsonl ts_utc ends with wrong suffix: {jl_ts}"


class TestBugInWindowHasHiddenBuffer:
    """Bug: in_window adds ±5min buffer, contaminating stored data.

    Events outside the requested window get stored permanently
    with no flag to distinguish them from in-window events.
    """

    def test_one_second_outside_is_excluded(self) -> None:
        """1 second past the end should NOT be in-window."""
        result = in_window(
            "2026-03-16T06:00:01Z",
            "2026-03-16T04:00:00Z",
            "2026-03-16T06:00:00Z",
        )
        assert result is False, "in_window includes events outside the window"


class TestBugRotatedPgFilenamesRejected:
    """Bug: format_to_table only accepts exact filenames.

    Rotated PG log files like postgresql-16-main.log are rejected
    with ValueError, breaking ingest for multi-file PG collection.
    """

    def test_rotated_pg_text_log(self) -> None:
        assert format_to_table("postgresql-16-main.log") == "pglog"

    def test_rotated_pg_json_log(self) -> None:
        assert format_to_table("postgresql-16-main.json") == "pglog"

    def test_prev_pg_log(self) -> None:
        assert format_to_table("postgresql-prev.json") == "pglog"


class TestBugJsonlCrashOnBadTimestamp:
    """Bug: JSONL parser crashes on valid JSON with non-string timestamp.

    A line like {"timestamp": null, "level": "info", "event": "x"}
    is valid JSON but will crash the parser when it tries string ops
    on the timestamp value.
    """

    def test_null_timestamp_skipped_not_crash(self) -> None:
        line = b'{"timestamp": null, "level": "info", "event": "x"}\n'
        result = parse_jsonl(line, "2026-03-16T00:00:00Z", "2026-03-16T23:59:59Z")
        assert result == []

    def test_integer_timestamp_skipped_not_crash(self) -> None:
        line = b'{"timestamp": 1710536535, "level": "info", "event": "x"}\n'
        result = parse_jsonl(line, "2026-03-16T00:00:00Z", "2026-03-16T23:59:59Z")
        assert result == []


class TestBugHaproxyIpv6Dropped:
    """Bug: HAProxy parser regex is IPv4-only.

    IPv6 client addresses like [::1]:12345 or
    [2001:db8::1]:12345 are counted as unparseable.
    """

    def test_ipv6_localhost_parsed(self) -> None:
        line = (
            "2026-03-16T16:06:45+11:00 grimoire haproxy[2345]: "
            "::1:45678 [16/Mar/2026:16:06:45.123 +1100] "
            "http-in backend/srv01 10/2/5/150/167 200 1234 "
            "- - ---- 1/1/1/1/0 0/0 {|} {|} "
            '"GET /healthz HTTP/1.1"\n'
        )
        from scripts.incident.parsers.haproxy import parse_haproxy

        events, unparseable = parse_haproxy(
            line.encode(),
            "2026-03-16T04:00:00Z",
            "2026-03-16T06:30:00Z",
            "Australia/Sydney",
        )
        assert len(events) == 1, (
            f"IPv6 line was unparseable (unparseable={unparseable})"
        )
        assert events[0]["client_ip"] == "::1"
