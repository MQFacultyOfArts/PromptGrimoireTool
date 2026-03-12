"""Tests for Moodle XLSX enrolment parser."""

from __future__ import annotations

import pytest

from tests.conftest import make_xlsx_bytes

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

STANDARD_HEADERS = ["First name", "Last name", "ID number", "Email address", "Groups"]


def _make_standard_row(
    first: str = "Alice",
    last: str = "Smith",
    sid: str = "12345678",
    email: str = "alice.smith@students.mq.edu.au",
    groups: str = "[Tutorial 1]",
) -> list:
    return [first, last, sid, email, groups]


# ---------------------------------------------------------------------------
# AC1.1 — Valid XLSX parsed into EnrolmentEntry list
# ---------------------------------------------------------------------------


class TestValidParsing:
    def test_single_row_parsed(self) -> None:
        from promptgrimoire.enrol.xlsx_parser import parse_xlsx

        data = make_xlsx_bytes(
            STANDARD_HEADERS,
            [_make_standard_row()],
        )
        entries = parse_xlsx(data)
        assert len(entries) == 1
        entry = entries[0]
        assert entry.email == "alice.smith@students.mq.edu.au"
        assert entry.display_name == "Alice Smith"
        assert entry.student_id == "12345678"

    def test_multiple_rows(self) -> None:
        from promptgrimoire.enrol.xlsx_parser import parse_xlsx

        data = make_xlsx_bytes(
            STANDARD_HEADERS,
            [
                _make_standard_row(),
                _make_standard_row(
                    first="Bob",
                    last="Jones",
                    sid="87654321",
                    email="bob.jones@students.mq.edu.au",
                    groups="[Lab A]",
                ),
            ],
        )
        entries = parse_xlsx(data)
        assert len(entries) == 2
        assert entries[0].display_name == "Alice Smith"
        assert entries[1].display_name == "Bob Jones"


# ---------------------------------------------------------------------------
# AC1.2 — Groups column parsed into tuple
# ---------------------------------------------------------------------------


class TestGroupsParsing:
    def test_single_group(self) -> None:
        from promptgrimoire.enrol.xlsx_parser import parse_xlsx

        data = make_xlsx_bytes(
            STANDARD_HEADERS,
            [_make_standard_row(groups="[Tutorial 1]")],
        )
        entries = parse_xlsx(data)
        assert entries[0].groups == ("Tutorial 1",)

    def test_multiple_groups(self) -> None:
        from promptgrimoire.enrol.xlsx_parser import parse_xlsx

        data = make_xlsx_bytes(
            STANDARD_HEADERS,
            [_make_standard_row(groups="[Tutorial 1], [Lab A]")],
        )
        entries = parse_xlsx(data)
        assert entries[0].groups == ("Tutorial 1", "Lab A")

    def test_empty_groups_string(self) -> None:
        from promptgrimoire.enrol.xlsx_parser import parse_xlsx

        data = make_xlsx_bytes(
            STANDARD_HEADERS,
            [_make_standard_row(groups="")],
        )
        entries = parse_xlsx(data)
        assert entries[0].groups == ()


# ---------------------------------------------------------------------------
# AC1.3 — Absent Groups column yields empty tuple
# ---------------------------------------------------------------------------


class TestAbsentGroupsColumn:
    def test_no_groups_column(self) -> None:
        from promptgrimoire.enrol.xlsx_parser import parse_xlsx

        headers = ["First name", "Last name", "ID number", "Email address"]
        data = make_xlsx_bytes(
            headers,
            [["Alice", "Smith", "12345678", "alice.smith@students.mq.edu.au"]],
        )
        entries = parse_xlsx(data)
        assert entries[0].groups == ()


# ---------------------------------------------------------------------------
# AC1.4 — Blank/padding rows skipped
# ---------------------------------------------------------------------------


class TestBlankRows:
    def test_blank_rows_skipped(self) -> None:
        from promptgrimoire.enrol.xlsx_parser import parse_xlsx

        data = make_xlsx_bytes(
            STANDARD_HEADERS,
            [
                _make_standard_row(),
                [None, None, None, None, None],
                ["", "", "", "", ""],
                _make_standard_row(
                    first="Bob",
                    last="Jones",
                    sid="87654321",
                    email="bob.jones@students.mq.edu.au",
                ),
            ],
        )
        entries = parse_xlsx(data)
        assert len(entries) == 2


# ---------------------------------------------------------------------------
# AC1.5 — Case-insensitive header matching
# ---------------------------------------------------------------------------


class TestCaseInsensitiveHeaders:
    def test_uppercase_headers(self) -> None:
        from promptgrimoire.enrol.xlsx_parser import parse_xlsx

        data = make_xlsx_bytes(
            ["FIRST NAME", "LAST NAME", "ID NUMBER", "EMAIL ADDRESS", "GROUPS"],
            [_make_standard_row()],
        )
        entries = parse_xlsx(data)
        assert len(entries) == 1
        assert entries[0].display_name == "Alice Smith"

    def test_mixed_case_headers(self) -> None:
        from promptgrimoire.enrol.xlsx_parser import parse_xlsx

        data = make_xlsx_bytes(
            ["first Name", "Last name", "id Number", "email Address"],
            [["Alice", "Smith", "12345678", "alice.smith@students.mq.edu.au"]],
        )
        entries = parse_xlsx(data)
        assert len(entries) == 1


# ---------------------------------------------------------------------------
# AC1.6 — Missing required column raises EnrolmentParseError
# ---------------------------------------------------------------------------


class TestMissingColumns:
    def test_missing_email_column(self) -> None:
        from promptgrimoire.enrol.xlsx_parser import EnrolmentParseError, parse_xlsx

        data = make_xlsx_bytes(
            ["First name", "Last name", "ID number"],
            [["Alice", "Smith", "12345678"]],
        )
        with pytest.raises(EnrolmentParseError, match="email address"):
            parse_xlsx(data)

    def test_missing_multiple_columns(self) -> None:
        from promptgrimoire.enrol.xlsx_parser import EnrolmentParseError, parse_xlsx

        data = make_xlsx_bytes(
            ["First name"],
            [["Alice"]],
        )
        with pytest.raises(EnrolmentParseError) as exc_info:
            parse_xlsx(data)
        # Should mention all missing columns
        error_text = str(exc_info.value).lower()
        assert "last name" in error_text
        assert "id number" in error_text
        assert "email address" in error_text


# ---------------------------------------------------------------------------
# AC1.7 — Duplicate emails raise EnrolmentParseError with line numbers
# ---------------------------------------------------------------------------


class TestDuplicateEmails:
    def test_duplicate_emails_detected(self) -> None:
        from promptgrimoire.enrol.xlsx_parser import EnrolmentParseError, parse_xlsx

        data = make_xlsx_bytes(
            STANDARD_HEADERS,
            [
                _make_standard_row(),
                _make_standard_row(first="Bob", last="Jones", sid="87654321"),
            ],
        )
        with pytest.raises(EnrolmentParseError) as exc_info:
            parse_xlsx(data)
        error_text = str(exc_info.value)
        # Should reference both row numbers (rows 2 and 3 in XLSX 1-indexed)
        assert "2" in error_text
        assert "3" in error_text

    def test_duplicate_emails_case_insensitive(self) -> None:
        from promptgrimoire.enrol.xlsx_parser import EnrolmentParseError, parse_xlsx

        data = make_xlsx_bytes(
            STANDARD_HEADERS,
            [
                _make_standard_row(email="Alice@Test.com"),
                _make_standard_row(
                    first="Bob", last="Jones", sid="87654321", email="alice@test.com"
                ),
            ],
        )
        with pytest.raises(EnrolmentParseError, match=r"[Dd]uplicate"):
            parse_xlsx(data)


# ---------------------------------------------------------------------------
# AC2.1 — Well-formed emails accepted
# ---------------------------------------------------------------------------


class TestEmailValidation:
    def test_valid_emails_accepted(self) -> None:
        from promptgrimoire.enrol.xlsx_parser import parse_xlsx

        data = make_xlsx_bytes(
            STANDARD_HEADERS,
            [
                _make_standard_row(email="alice@example.com"),
                _make_standard_row(
                    first="Bob",
                    last="Jones",
                    sid="87654321",
                    email="bob.jones+tag@students.mq.edu.au",
                ),
            ],
        )
        entries = parse_xlsx(data)
        assert len(entries) == 2


# ---------------------------------------------------------------------------
# AC2.2 — Malformed email raises EnrolmentParseError with line number
# ---------------------------------------------------------------------------


class TestMalformedEmail:
    def test_malformed_email_raises(self) -> None:
        from promptgrimoire.enrol.xlsx_parser import EnrolmentParseError, parse_xlsx

        data = make_xlsx_bytes(
            STANDARD_HEADERS,
            [_make_standard_row(email="not-an-email")],
        )
        with pytest.raises(EnrolmentParseError) as exc_info:
            parse_xlsx(data)
        error_text = str(exc_info.value)
        assert "2" in error_text  # Row 2 in XLSX (1-indexed, header is row 1)

    def test_multiple_malformed_emails_all_reported(self) -> None:
        from promptgrimoire.enrol.xlsx_parser import EnrolmentParseError, parse_xlsx

        data = make_xlsx_bytes(
            STANDARD_HEADERS,
            [
                _make_standard_row(email="bad1"),
                _make_standard_row(
                    first="Bob", last="Jones", sid="87654321", email="bad2"
                ),
            ],
        )
        with pytest.raises(EnrolmentParseError) as exc_info:
            parse_xlsx(data)
        # Both errors collected
        assert len(exc_info.value.errors) >= 2


# ---------------------------------------------------------------------------
# AC2.3 — Student ID with mq prefix preserved as-is
# ---------------------------------------------------------------------------


class TestStudentIdPreservation:
    def test_mq_prefix_preserved(self) -> None:
        from promptgrimoire.enrol.xlsx_parser import parse_xlsx

        data = make_xlsx_bytes(
            STANDARD_HEADERS,
            [_make_standard_row(sid="mq12345678")],
        )
        entries = parse_xlsx(data)
        assert entries[0].student_id == "mq12345678"

    def test_numeric_id_preserved(self) -> None:
        from promptgrimoire.enrol.xlsx_parser import parse_xlsx

        data = make_xlsx_bytes(
            STANDARD_HEADERS,
            [_make_standard_row(sid="12345678")],
        )
        entries = parse_xlsx(data)
        assert entries[0].student_id == "12345678"
