"""RED tests for Codex round 3 findings."""

from __future__ import annotations

from typing import TYPE_CHECKING

from scripts.incident.parsers.haproxy import parse_haproxy

if TYPE_CHECKING:
    from pathlib import Path


class TestHaproxyAdminFallbackTooBroad:
    """The admin regex accepts any rsyslog-prefixed line, hiding parse drift."""

    def test_malformed_http_line_is_unparseable_not_admin(self) -> None:
        """A broken HTTP-like line should be unparseable, not an admin event."""
        line = (
            "2026-03-16T15:00:00+11:00 host haproxy[123]: "
            "192.0.2.1:12345 BROKEN LINE WITHOUT BRACKETS\n"
        )
        events, unparseable = parse_haproxy(
            line.encode(),
            "2026-03-16T03:00:00Z",
            "2026-03-16T05:00:00Z",
            "Australia/Sydney",
        )
        assert unparseable == 1, (
            f"Malformed line accepted as event (got {len(events)} events, "
            f"0 unparseable). Admin fallback is too broad."
        )
        assert len(events) == 0


class TestTimezoneCLIValidation:
    """--timezone with invalid IANA name should give a CLI error, not crash."""

    def test_invalid_timezone_gives_cli_error(self) -> None:
        from scripts.incident_db import app
        from typer.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "timeline",
                "--start",
                "2026-03-16 16:00",
                "--end",
                "2026-03-16 17:00",
                "--timezone",
                "Not/AZone",
                "--db",
                "nonexistent.db",
            ],
        )
        assert result.exit_code != 0
        assert "ZoneInfoNotFoundError" not in (result.output + str(result.exception))

    def test_beszel_invalid_timezone_gives_cli_error(self) -> None:
        from scripts.incident_db import app
        from typer.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "beszel",
                "--start",
                "2026-03-16 16:00",
                "--end",
                "2026-03-16 17:00",
                "--timezone",
                "Not/AZone",
                "--db",
                "nonexistent.db",
            ],
        )
        assert result.exit_code != 0
        assert "ZoneInfoNotFoundError" not in (result.output + str(result.exception))


class TestBeszelDedup:
    """Beszel dedup path should be tested."""

    def test_beszel_dedup_message(self, tmp_path: Path) -> None:
        import sqlite3

        from scripts.incident.schema import create_schema

        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        create_schema(conn)
        conn.execute(
            """INSERT INTO sources
               (filename, format, sha256, size, mtime, hostname, timezone,
                window_start_utc, window_end_utc)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "beszel-api",
                "beszel",
                "test-sha",
                0,
                0,
                "hub",
                "UTC",
                "2026-03-16T00:00:00.000000Z",
                "2026-03-16T01:00:00.000000Z",
            ),
        )
        conn.commit()
        conn.close()

        from scripts.incident_db import app
        from typer.testing import CliRunner

        runner = CliRunner()
        # The sha256 for beszel is derived from hub:start:end
        # We can't easily match it, but we can test that a second
        # invocation with the same window is a no-op
        # This test just verifies the dedup path exists and doesn't crash
        # (it will try to connect to localhost:8090 which may not exist)
        # So we test _resolve_timezone + _aedt_to_utc + sha check
        # by pre-inserting a source with the expected sha
        import hashlib

        sha = hashlib.sha256(
            b"http://localhost:8090:2026-03-16T00:00:00.000000Z:2026-03-16T01:00:00.000000Z"
        ).hexdigest()
        conn = sqlite3.connect(db_path)
        conn.execute(
            "UPDATE sources SET sha256 = ? WHERE format = 'beszel'",
            (sha,),
        )
        conn.commit()
        conn.close()

        result = runner.invoke(
            app,
            [
                "beszel",
                "--start",
                "2026-03-16 11:00",
                "--end",
                "2026-03-16 12:00",
                "--timezone",
                "Australia/Sydney",
                "--db",
                str(db_path),
            ],
        )
        assert result.exit_code == 0
        assert "Already fetched" in result.output
