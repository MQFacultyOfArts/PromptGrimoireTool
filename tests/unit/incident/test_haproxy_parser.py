"""Tests for HAProxy log parser.

Verifies:
- AC2.3: rsyslog prefix timestamp converts to correct UTC (AEDT +11:00 -> UTC)
- AC3.1: Extract status code, all 5 timing fields, method, path, client IP
- AC3.4: Unparseable lines counted and returned, not silently dropped
- Time-window filtering excludes events outside UTC bounds
- Different timezone offsets produce correct UTC (AEST +10 vs AEDT +11)
"""

from __future__ import annotations

from scripts.incident.parsers.haproxy import parse_haproxy

# Window that contains the fixture timestamps (2026-03-16T05:00-06:00 UTC)
WINDOW_START = "2026-03-16T05:00:00+00:00"
WINDOW_END = "2026-03-16T06:00:00+00:00"
TZ = "Australia/Sydney"

# Realistic fixture line from the plan (AEDT = UTC+11)
FIXTURE_LINE = (
    "2026-03-16T16:06:45+11:00 grimoire haproxy[2345]: "
    "192.0.2.100:45678 [16/Mar/2026:16:06:45.123 +1100] "
    "http-in backend/srv01 10/2/5/150/167 504 0 - - ---- "
    '1/1/1/1/0 0/0 {|} {|} "GET /annotation/ws-xyz HTTP/1.1"'
)


class TestTimestampConversion:
    """AC2.3: rsyslog prefix converts to correct UTC."""

    def test_aedt_to_utc(self) -> None:
        """2026-03-16T16:06:45+11:00 -> 2026-03-16T05:06:45+00:00."""
        data = FIXTURE_LINE.encode()

        events, _unparseable = parse_haproxy(data, WINDOW_START, WINDOW_END, TZ)

        assert len(events) == 1
        assert events[0]["ts_utc"].startswith("2026-03-16T05:06:45")
        assert "+00:00" in events[0]["ts_utc"]

    def test_aest_offset(self) -> None:
        """AEST (+10:00) produces different UTC than AEDT (+11:00)."""
        # Same local time but AEST (+10) instead of AEDT (+11)
        # 16:06:45+10:00 -> 06:06:45 UTC
        aest_line = FIXTURE_LINE.replace("+11:00", "+10:00").replace("+1100", "+1000")
        # Widen window to include 06:06 UTC
        wide_start = "2026-03-16T05:00:00+00:00"
        wide_end = "2026-03-16T07:00:00+00:00"

        events, _ = parse_haproxy(aest_line.encode(), wide_start, wide_end, TZ)

        assert len(events) == 1
        assert events[0]["ts_utc"].startswith("2026-03-16T06:06:45")


class TestFieldExtraction:
    """AC3.1: Extract all required fields from a real log line."""

    def test_status_code(self) -> None:
        events, _ = parse_haproxy(FIXTURE_LINE.encode(), WINDOW_START, WINDOW_END, TZ)

        assert events[0]["status_code"] == 504

    def test_timing_fields(self) -> None:
        events, _ = parse_haproxy(FIXTURE_LINE.encode(), WINDOW_START, WINDOW_END, TZ)
        ev = events[0]

        assert ev["tr_ms"] == 10
        assert ev["tw_ms"] == 2
        assert ev["tc_ms"] == 5
        assert ev["tr_resp_ms"] == 150
        assert ev["ta_ms"] == 167

    def test_request_method_and_path(self) -> None:
        events, _ = parse_haproxy(FIXTURE_LINE.encode(), WINDOW_START, WINDOW_END, TZ)

        assert events[0]["method"] == "GET"
        assert events[0]["path"] == "/annotation/ws-xyz"

    def test_client_ip(self) -> None:
        events, _ = parse_haproxy(FIXTURE_LINE.encode(), WINDOW_START, WINDOW_END, TZ)

        assert events[0]["client_ip"] == "192.0.2.100"

    def test_backend_and_server(self) -> None:
        events, _ = parse_haproxy(FIXTURE_LINE.encode(), WINDOW_START, WINDOW_END, TZ)

        assert events[0]["backend"] == "backend"
        assert events[0]["server"] == "srv01"

    def test_bytes_read(self) -> None:
        events, _ = parse_haproxy(FIXTURE_LINE.encode(), WINDOW_START, WINDOW_END, TZ)

        assert events[0]["bytes_read"] == 0


class TestUnparseableLines:
    """AC3.4: Unparseable lines counted, not silently dropped."""

    def test_garbage_lines_counted(self) -> None:
        """5 lines, 2 garbage -> 3 events, unparseable_count=2."""
        good_lines = []
        for i in range(3):
            good_lines.append(
                f"2026-03-16T16:0{i}:00+11:00 grimoire haproxy[2345]: "
                f"192.0.2.{i}:45678 [16/Mar/2026:16:0{i}:00.000 +1100] "
                f"http-in backend/srv01 10/2/5/150/167 200 1234 - - ---- "
                f'1/1/1/1/0 0/0 {{|}} {{|}} "GET /page/{i} HTTP/1.1"'
            )
        garbage = ["this is not a log line", "neither is this"]

        all_lines = good_lines + garbage
        data = "\n".join(all_lines).encode()

        events, unparseable = parse_haproxy(data, WINDOW_START, WINDOW_END, TZ)

        assert len(events) == 3
        assert unparseable == 2

    def test_all_garbage_returns_empty(self) -> None:
        data = b"garbage line 1\ngarbage line 2\n"

        events, unparseable = parse_haproxy(data, WINDOW_START, WINDOW_END, TZ)

        assert events == []
        assert unparseable == 2


class TestTimeWindowFiltering:
    """Events outside the UTC window are excluded."""

    def test_event_inside_window(self) -> None:
        events, _ = parse_haproxy(FIXTURE_LINE.encode(), WINDOW_START, WINDOW_END, TZ)
        assert len(events) == 1

    def test_event_outside_window(self) -> None:
        """Event 12 hours before window is excluded."""
        early_line = FIXTURE_LINE.replace(
            "2026-03-16T16:06:45+11:00", "2026-03-16T04:00:00+11:00"
        ).replace("16/Mar/2026:16:06:45.123 +1100", "16/Mar/2026:04:00:00.000 +1100")

        events, _ = parse_haproxy(early_line.encode(), WINDOW_START, WINDOW_END, TZ)
        assert len(events) == 0

    def test_event_before_start_excluded(self) -> None:
        """Event 3 minutes before window_start is excluded (no buffer)."""
        # 05:00 UTC - 3min = 04:57 UTC = 15:57 AEDT
        before_line = FIXTURE_LINE.replace(
            "2026-03-16T16:06:45+11:00", "2026-03-16T15:57:00+11:00"
        ).replace("16/Mar/2026:16:06:45.123 +1100", "16/Mar/2026:15:57:00.000 +1100")

        events, _ = parse_haproxy(before_line.encode(), WINDOW_START, WINDOW_END, TZ)
        assert len(events) == 0


class TestEdgeCases:
    """Empty input, blank lines."""

    def test_empty_input(self) -> None:
        events, unparseable = parse_haproxy(b"", WINDOW_START, WINDOW_END, TZ)
        assert events == []
        assert unparseable == 0

    def test_blank_lines_skipped(self) -> None:
        data = f"\n\n{FIXTURE_LINE}\n\n".encode()

        events, unparseable = parse_haproxy(data, WINDOW_START, WINDOW_END, TZ)
        assert len(events) == 1
        assert unparseable == 0

    def test_post_request(self) -> None:
        """POST request with path extraction."""
        post_line = FIXTURE_LINE.replace(
            '"GET /annotation/ws-xyz HTTP/1.1"',
            '"POST /api/submit HTTP/1.1"',
        )
        events, _ = parse_haproxy(post_line.encode(), WINDOW_START, WINDOW_END, TZ)

        assert events[0]["method"] == "POST"
        assert events[0]["path"] == "/api/submit"
