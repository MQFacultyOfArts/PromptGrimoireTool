"""Unit tests for wargame roster parsing."""

from __future__ import annotations

import pytest


class TestParseRoster:
    """Happy-path tests for parse_roster."""

    def test_parses_full_email_team_role_rows(self) -> None:
        """AC2.1: Full roster rows become concrete RosterEntry values."""
        from promptgrimoire.wargame import RosterEntry, parse_roster

        csv_content = (
            "email,team,role\n"
            " ALICE@example.com , Team Red , viewer \n"
            "bob@example.com,Team Blue,editor\n"
        )

        result = parse_roster(csv_content)

        assert result == [
            RosterEntry(
                email="alice@example.com",
                team="Team Red",
                role="viewer",
            ),
            RosterEntry(
                email="bob@example.com",
                team="Team Blue",
                role="editor",
            ),
        ]

    def test_defaults_role_when_header_is_missing(self) -> None:
        """AC2.2: Missing role header defaults every row to editor."""
        from promptgrimoire.wargame import RosterEntry, parse_roster

        csv_content = "email,team\nalice@example.com,Red\nbob@example.com,Blue\n"

        result = parse_roster(csv_content)

        assert result == [
            RosterEntry(email="alice@example.com", team="Red", role="editor"),
            RosterEntry(email="bob@example.com", team="Blue", role="editor"),
        ]

    def test_defaults_role_when_cell_is_blank(self) -> None:
        """AC2.2: Blank role cells default that row to editor."""
        from promptgrimoire.wargame import RosterEntry, parse_roster

        csv_content = (
            "email,team,role\nalice@example.com,Red,\nbob@example.com,Blue,viewer\n"
        )

        result = parse_roster(csv_content)

        assert result == [
            RosterEntry(email="alice@example.com", team="Red", role="editor"),
            RosterEntry(email="bob@example.com", team="Blue", role="viewer"),
        ]

    def test_returns_none_for_every_team_when_team_header_is_missing(self) -> None:
        """AC2.3: Missing team header produces explicit None team values."""
        from promptgrimoire.wargame import RosterEntry, parse_roster

        csv_content = "email,role\nalice@example.com,editor\nbob@example.com,viewer\n"

        result = parse_roster(csv_content)

        assert result == [
            RosterEntry(email="alice@example.com", team=None, role="editor"),
            RosterEntry(email="bob@example.com", team=None, role="viewer"),
        ]


class TestParseRosterValidation:
    """Failure-path tests for parse_roster."""

    def test_empty_csv_reports_empty_file_error(self) -> None:
        """Empty CSV content is distinguished from a missing email header."""
        from promptgrimoire.wargame import RosterParseError, parse_roster

        with pytest.raises(RosterParseError, match="empty roster csv") as exc_info:
            parse_roster("")

        assert exc_info.value.line_numbers == ()

    def test_missing_email_header_reports_structural_header_error(self) -> None:
        """Missing email header remains a separate structural error."""
        from promptgrimoire.wargame import RosterParseError, parse_roster

        csv_content = "team,role\nRed,editor\n"

        with pytest.raises(
            RosterParseError,
            match="missing required email header",
        ) as exc_info:
            parse_roster(csv_content)

        assert exc_info.value.line_numbers == ()

    def test_duplicate_email_reports_both_physical_line_numbers(self) -> None:
        """AC2.4: Duplicate normalized emails include both line numbers."""
        from promptgrimoire.wargame import RosterParseError, parse_roster

        csv_content = (
            "email,team,role\n"
            "Alice@example.com,Red,editor\n"
            " alice@EXAMPLE.com ,Blue,viewer\n"
        )

        with pytest.raises(RosterParseError, match="duplicate email") as exc_info:
            parse_roster(csv_content)

        assert exc_info.value.line_numbers == (2, 3)
        assert "2" in str(exc_info.value)
        assert "3" in str(exc_info.value)

    def test_malformed_email_reports_its_line_number(self) -> None:
        """AC2.5: Malformed email raises with the offending line number."""
        from promptgrimoire.wargame import RosterParseError, parse_roster

        csv_content = "email,team,role\nnot-an-email,Red,editor\n"

        with pytest.raises(RosterParseError, match="malformed email") as exc_info:
            parse_roster(csv_content)

        assert exc_info.value.line_numbers == (2,)

    def test_invalid_role_reports_line_number_and_value(self) -> None:
        """AC2.6: Unsupported role raises with line number and invalid value."""
        from promptgrimoire.wargame import RosterParseError, parse_roster

        csv_content = "email,team,role\nalice@example.com,Red,observer\n"

        with pytest.raises(RosterParseError, match="observer") as exc_info:
            parse_roster(csv_content)

        assert exc_info.value.line_numbers == (2,)


class TestAutoAssignTeams:
    """Tests for auto_assign_teams."""

    def test_assigns_entries_in_strict_round_robin_order(self) -> None:
        """AC2.7: Round-robin team labels cycle by position."""
        from promptgrimoire.wargame import RosterEntry, auto_assign_teams

        entries = [
            RosterEntry(email=f"user-{index}@example.com", team=None, role="editor")
            for index in range(1, 6)
        ]

        assigned = auto_assign_teams(entries, team_count=3)

        assert assigned is not entries
        assert entries == [
            RosterEntry(email=f"user-{index}@example.com", team=None, role="editor")
            for index in range(1, 6)
        ]
        assert [entry.team for entry in assigned] == [
            "AUTO-1",
            "AUTO-2",
            "AUTO-3",
            "AUTO-1",
            "AUTO-2",
        ]
        assert [entry.email for entry in assigned] == [
            f"user-{index}@example.com" for index in range(1, 6)
        ]
        assert [entry.role for entry in assigned] == ["editor"] * 5

    def test_rejects_non_positive_team_count(self) -> None:
        """Non-positive team counts fail with ValueError."""
        from promptgrimoire.wargame import RosterEntry, auto_assign_teams

        entries = [RosterEntry(email="user@example.com", team=None, role="viewer")]

        with pytest.raises(ValueError):
            auto_assign_teams(entries, team_count=0)
