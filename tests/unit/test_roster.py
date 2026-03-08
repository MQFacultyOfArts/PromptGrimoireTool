"""Unit tests for wargame roster parsing."""

from __future__ import annotations


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
