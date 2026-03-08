# pattern: Functional Core

"""Pure roster parsing helpers for wargame team management."""

from __future__ import annotations

import csv
from dataclasses import dataclass, replace
from io import StringIO

_VALID_ROLES = frozenset({"viewer", "editor"})


@dataclass(frozen=True)
class RosterEntry:
    """Normalized roster row used by later orchestration layers."""

    email: str
    team: str | None
    role: str


class RosterParseError(Exception):
    """Structured roster parsing error with optional CSV line numbers."""

    def __init__(self, message: str, line_numbers: tuple[int, ...] = ()) -> None:
        super().__init__(message)
        self.message = message
        self.line_numbers = line_numbers

    def __str__(self) -> str:
        """Render the message with line numbers when available."""
        if not self.line_numbers:
            return self.message

        line_list = ", ".join(str(line_number) for line_number in self.line_numbers)
        return f"{self.message} (lines: {line_list})"


def _sniff_dialect(csv_content: str) -> csv.Dialect | type[csv.Dialect]:
    """Return a sniffed CSV dialect, falling back to comma-separated excel."""
    try:
        return csv.Sniffer().sniff(csv_content)
    except csv.Error:
        return csv.excel


def _get_cell(row: list[str], index: int | None) -> str:
    """Return the row cell at ``index`` or an empty string when absent."""
    if index is None or index >= len(row):
        return ""
    return row[index]


def _is_valid_email(email: str) -> bool:
    """Return True when ``email`` has exactly one @ and non-empty parts."""
    local, separator, domain = email.partition("@")
    return bool(separator and local and domain and "@" not in domain)


def parse_roster(csv_content: str) -> list[RosterEntry]:
    """Parse roster CSV content into normalized immutable roster entries.

    Parameters
    ----------
    csv_content : str
        Raw roster CSV content.

    Returns
    -------
    list[RosterEntry]
        Parsed rows in input order.

    Raises
    ------
    RosterParseError
        If the CSV is empty or lacks the required ``email`` header.
    """
    reader = csv.reader(StringIO(csv_content), dialect=_sniff_dialect(csv_content))

    try:
        headers = next(reader)
    except StopIteration as exc:
        msg = "empty roster csv"
        raise RosterParseError(msg) from exc

    normalized_headers = [header.strip().lower() for header in headers]
    if "email" not in normalized_headers:
        msg = "missing required email header"
        raise RosterParseError(msg)

    email_index = normalized_headers.index("email")
    team_index = (
        normalized_headers.index("team") if "team" in normalized_headers else None
    )
    role_index = (
        normalized_headers.index("role") if "role" in normalized_headers else None
    )

    entries: list[RosterEntry] = []
    seen_emails: dict[str, int] = {}
    for line_number, row in enumerate(reader, start=2):
        email = _get_cell(row, email_index).strip().lower()
        team_value = _get_cell(row, team_index).strip()
        role_value = _get_cell(row, role_index).strip().lower()
        if not _is_valid_email(email):
            msg = f"malformed email: {email}"
            raise RosterParseError(msg, line_numbers=(line_number,))

        if email in seen_emails:
            msg = f"duplicate email: {email}"
            raise RosterParseError(
                msg,
                line_numbers=(seen_emails[email], line_number),
            )

        if role_value and role_value not in _VALID_ROLES:
            msg = f"invalid role: {role_value}"
            raise RosterParseError(msg, line_numbers=(line_number,))

        seen_emails[email] = line_number
        entries.append(
            RosterEntry(
                email=email,
                team=team_value or None,
                role=role_value or "editor",
            )
        )

    return entries


def auto_assign_teams(entries: list[RosterEntry], team_count: int) -> list[RosterEntry]:
    """Assign synthetic team labels in strict round-robin order.

    Parameters
    ----------
    entries : list[RosterEntry]
        Parsed roster entries to assign.
    team_count : int
        Number of synthetic team buckets to cycle through.

    Returns
    -------
    list[RosterEntry]
        New roster entries with synthetic ``team`` labels.

    Raises
    ------
    ValueError
        If ``team_count`` is not positive.
    """
    if team_count <= 0:
        msg = "team_count must be positive"
        raise ValueError(msg)

    return [
        replace(entry, team=f"AUTO-{(index % team_count) + 1}")
        for index, entry in enumerate(entries)
    ]
