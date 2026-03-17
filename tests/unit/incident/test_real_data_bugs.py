"""RED tests — bugs found by ingesting real production data.

Each test uses fixtures extracted from the actual 2026-03-16 tarball.
"""

from __future__ import annotations

import json

from scripts.incident.parsers.haproxy import parse_haproxy
from scripts.incident.parsers.journal import parse_journal
from scripts.incident.parsers.pglog import parse_pglog_text


class TestBugJournalMessageByteArray:
    """Bug: journal MESSAGE field can be a byte array, not a string.

    systemd journal --output=json emits MESSAGE as an array of integers
    when the content contains non-UTF-8 or binary data (e.g. ANSI escapes).
    The parser crashes with 'type list is not supported' on INSERT.
    """

    def test_byte_array_message_decoded(self) -> None:
        line = json.dumps(
            {
                "__REALTIME_TIMESTAMP": "1773633004357212",
                "PRIORITY": "6",
                "_PID": "885075",
                "_SYSTEMD_UNIT": "promptgrimoire.service",
                "MESSAGE": [
                    105,
                    110,
                    102,
                    111,
                    32,
                    80,
                    114,
                    111,
                    99,
                    101,
                    115,
                    115,
                    101,
                    100,
                ],
            }
        )
        result = parse_journal(
            line.encode(),
            "2026-03-16T03:00:00Z",
            "2026-03-16T04:00:00Z",
        )
        assert len(result) == 1
        assert isinstance(result[0]["message"], str)
        assert result[0]["message"] == "info Processed"


class TestBugPgLogFormatMismatch:
    """Bug: PG text parser regex doesn't match actual production format.

    Actual: 2026-03-14 13:19:49.544 UTC [2482047] LOG:  checkpoint starting
    Expected by regex: 2026-03-14 13:19:49 UTC [2482047]: LOG:  checkpoint starting

    Differences from our regex:
    1. Timestamp has milliseconds (.544)
    2. No colon after the closing bracket — it's [PID] LEVEL: not [PID]: LEVEL:
    """

    def test_actual_production_pg_line_parsed(self) -> None:
        line = "2026-03-14 13:19:49.544 UTC [2482047] LOG:  checkpoint starting: time\n"
        result = parse_pglog_text(
            line.encode(),
            "2026-03-14T13:00:00Z",
            "2026-03-14T14:00:00Z",
        )
        assert len(result) == 1
        assert result[0]["pid"] == 2482047
        assert result[0]["level"] == "LOG"
        assert "checkpoint starting" in result[0]["message"]

    def test_multiline_error_with_detail(self) -> None:
        """Real PG format: ERROR + DETAIL + STATEMENT, same PID + timestamp."""
        lines = (
            "2026-03-16 04:32:52.123 UTC [1234] ERROR:  "
            "duplicate key value violates unique constraint\n"
            "2026-03-16 04:32:52.123 UTC [1234] DETAIL:  "
            "Key (workspace_id, name)=(abc, test) already exists.\n"
            "2026-03-16 04:32:52.123 UTC [1234] STATEMENT:  "
            "INSERT INTO tag VALUES ($1, $2)\n"
        )
        result = parse_pglog_text(
            lines.encode(),
            "2026-03-16T04:00:00Z",
            "2026-03-16T05:00:00Z",
        )
        assert len(result) == 1
        assert result[0]["level"] == "ERROR"
        assert result[0]["detail"] is not None
        assert result[0]["statement"] is not None


class TestBugHaproxySslHandshakeDropped:
    """Bug: SSL handshake failure lines counted as unparseable.

    These are valid log entries with timestamps and client IPs.
    Format: rsyslog_ts hostname haproxy[pid]: IP:port [inner_ts] frontend/bind: message
    """

    def test_ssl_handshake_failure_parsed(self) -> None:
        line = (
            "2026-03-16T14:51:45.407280+11:00 prompt-grimoire "
            "haproxy[1000797]: 212.102.40.218:27290 "
            "[16/Mar/2026:14:51:45.218] fe_https/1: "
            "SSL handshake failure\n"
        )
        events, unparseable = parse_haproxy(
            line.encode(),
            "2026-03-16T03:00:00Z",
            "2026-03-16T04:00:00Z",
            "Australia/Sydney",
        )
        assert unparseable == 0, "SSL handshake line wrongly counted as unparseable"
        assert len(events) == 1
        assert events[0]["client_ip"] == "212.102.40.218"
        assert events[0]["status_code"] == 0
        assert events[0]["method"] is None
        assert "SSL handshake failure" in (events[0]["path"] or "")


class TestBugHaproxyTimestampFormat:
    """Bug: HAProxy parser uses .isoformat() producing +00:00 suffix.

    All other parsers use normalise_utc() producing Z suffix.
    Mixed formats cause timeline misordering (+ < Z in ASCII).
    """

    def test_haproxy_ts_utc_ends_with_z(self) -> None:
        line = (
            "2026-03-16T16:06:45.123456+11:00 prompt-grimoire "
            "haproxy[2345]: 192.0.2.100:45678 "
            "[16/Mar/2026:16:06:45.123 +1100] "
            "fe_https~ be_promptgrimoire/app "
            "10/2/5/150/167 200 1234 "
            "- - ---- 1/1/1/1/0 0/0 {|} {|} "
            '"GET /healthz HTTP/1.1"\n'
        )
        events, _ = parse_haproxy(
            line.encode(),
            "2026-03-16T04:00:00Z",
            "2026-03-16T06:30:00Z",
            "Australia/Sydney",
        )
        assert len(events) == 1
        ts = events[0]["ts_utc"]
        assert ts.endswith("Z"), f"HAProxy ts_utc has wrong suffix: {ts}"


class TestBugPgTextTimestampFormat:
    """Bug: PG text parser hardcodes +00:00 instead of using normalise_utc."""

    def test_pg_text_ts_utc_ends_with_z(self) -> None:
        line = "2026-03-16 04:32:52.000 UTC [1234] LOG:  test\n"
        result = parse_pglog_text(
            line.encode(),
            "2026-03-16T04:00:00Z",
            "2026-03-16T05:00:00Z",
        )
        assert len(result) == 1
        ts = result[0]["ts_utc"]
        assert ts.endswith("Z"), f"PG text ts_utc has wrong suffix: {ts}"
