"""Tests for _build_test_header() — branch and DB info in test runner header.

Verifies AC2.1: Test output header shows current branch name and resolved
database name in both Rich panel content and plain-text log header.
"""

from __future__ import annotations

from datetime import datetime

from rich.text import Text

from promptgrimoire.cli import _build_test_header


class TestBuildTestHeaderBranch:
    """Header includes branch name."""

    def test_branch_name_in_rich_text(self) -> None:
        rich_text, _ = _build_test_header(
            title="Test",
            branch="165-auto-create-branch-db",
            db_name="promptgrimoire_test",
            start_time=datetime(2026, 2, 14, 10, 0, 0),
            command_str="pytest -v",
        )
        assert "165-auto-create-branch-db" in rich_text.plain

    def test_branch_name_in_log_header(self) -> None:
        _, log_header = _build_test_header(
            title="Test",
            branch="165-auto-create-branch-db",
            db_name="promptgrimoire_test",
            start_time=datetime(2026, 2, 14, 10, 0, 0),
            command_str="pytest -v",
        )
        assert "165-auto-create-branch-db" in log_header


class TestBuildTestHeaderDbName:
    """Header includes database name."""

    def test_db_name_in_rich_text(self) -> None:
        rich_text, _ = _build_test_header(
            title="Test",
            branch="main",
            db_name="promptgrimoire_test_165",
            start_time=datetime(2026, 2, 14, 10, 0, 0),
            command_str="pytest -v",
        )
        assert "promptgrimoire_test_165" in rich_text.plain

    def test_db_name_in_log_header(self) -> None:
        _, log_header = _build_test_header(
            title="Test",
            branch="main",
            db_name="promptgrimoire_test_165",
            start_time=datetime(2026, 2, 14, 10, 0, 0),
            command_str="pytest -v",
        )
        assert "promptgrimoire_test_165" in log_header


class TestBuildTestHeaderDetachedHead:
    """Header handles detached HEAD (branch=None)."""

    def test_detached_in_rich_text(self) -> None:
        rich_text, _ = _build_test_header(
            title="Test",
            branch=None,
            db_name="promptgrimoire_test",
            start_time=datetime(2026, 2, 14, 10, 0, 0),
            command_str="pytest -v",
        )
        assert "detached/unknown" in rich_text.plain

    def test_detached_in_log_header(self) -> None:
        _, log_header = _build_test_header(
            title="Test",
            branch=None,
            db_name="promptgrimoire_test",
            start_time=datetime(2026, 2, 14, 10, 0, 0),
            command_str="pytest -v",
        )
        assert "detached/unknown" in log_header


class TestBuildTestHeaderNoDb:
    """Header handles no test database configured."""

    def test_not_configured_in_rich_text(self) -> None:
        rich_text, _ = _build_test_header(
            title="Test",
            branch="main",
            db_name="not configured",
            start_time=datetime(2026, 2, 14, 10, 0, 0),
            command_str="pytest -v",
        )
        assert "not configured" in rich_text.plain

    def test_not_configured_in_log_header(self) -> None:
        _, log_header = _build_test_header(
            title="Test",
            branch="main",
            db_name="not configured",
            start_time=datetime(2026, 2, 14, 10, 0, 0),
            command_str="pytest -v",
        )
        assert "not configured" in log_header


class TestBuildTestHeaderReturnTypes:
    """Return value is a 2-tuple of (Text, str)."""

    def test_returns_tuple(self) -> None:
        result = _build_test_header(
            title="Test",
            branch="main",
            db_name="db",
            start_time=datetime(2026, 2, 14, 10, 0, 0),
            command_str="pytest",
        )
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_first_element_is_rich_text(self) -> None:
        rich_text, _ = _build_test_header(
            title="Test",
            branch="main",
            db_name="db",
            start_time=datetime(2026, 2, 14, 10, 0, 0),
            command_str="pytest",
        )
        assert isinstance(rich_text, Text)

    def test_second_element_is_str(self) -> None:
        _, log_header = _build_test_header(
            title="Test",
            branch="main",
            db_name="db",
            start_time=datetime(2026, 2, 14, 10, 0, 0),
            command_str="pytest",
        )
        assert isinstance(log_header, str)
