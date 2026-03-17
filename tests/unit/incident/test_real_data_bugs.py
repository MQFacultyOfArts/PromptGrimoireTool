"""RED tests — bugs found by ingesting real production data.

Each test uses fixtures extracted from the actual 2026-03-16 tarball.
"""

from __future__ import annotations

import json

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
