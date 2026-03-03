"""Tests for cli/testing.py — test runner commands and streaming helpers.

Tests cover:
- Pure parsing helpers (_parse_collection, _is_summary_boundary, _parse_result)
- Phase-dispatch helpers (_handle_collecting_phase, _handle_running_phase)
- _xdist_worker_count calculation
- _stream_plain output filtering
- Typer command --help outputs
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from typer.testing import CliRunner

if TYPE_CHECKING:
    import pytest

from promptgrimoire.cli import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# _parse_collection
# ---------------------------------------------------------------------------
class TestParseCollection:
    """Extract test count from pytest collection lines."""

    def test_collected_items(self) -> None:
        from promptgrimoire.cli.testing import _parse_collection

        assert _parse_collection("collected 42 items") == 42

    def test_collected_single_item(self) -> None:
        from promptgrimoire.cli.testing import _parse_collection

        assert _parse_collection("collected 1 item") == 1

    def test_collected_with_deselected(self) -> None:
        from promptgrimoire.cli.testing import _parse_collection

        assert _parse_collection("collected 10 items / 3 deselected") == 7

    def test_xdist_items(self) -> None:
        from promptgrimoire.cli.testing import _parse_collection

        assert _parse_collection("[8 items]") == 8

    def test_no_match_returns_none(self) -> None:
        from promptgrimoire.cli.testing import _parse_collection

        assert _parse_collection("some random line") is None


# ---------------------------------------------------------------------------
# _is_summary_boundary
# ---------------------------------------------------------------------------
class TestIsSummaryBoundary:
    """Detect start of pytest post-execution output."""

    def test_separator_line(self) -> None:
        from promptgrimoire.cli.testing import _is_summary_boundary

        assert _is_summary_boundary("=" * 20) is True

    def test_failures_keyword(self) -> None:
        from promptgrimoire.cli.testing import _is_summary_boundary

        assert _is_summary_boundary("FAILURES") is True

    def test_errors_keyword(self) -> None:
        from promptgrimoire.cli.testing import _is_summary_boundary

        assert _is_summary_boundary("ERRORS") is True

    def test_normal_line(self) -> None:
        from promptgrimoire.cli.testing import _is_summary_boundary

        assert _is_summary_boundary("tests/unit/test_foo.py::test_bar PASSED") is False


# ---------------------------------------------------------------------------
# _parse_result
# ---------------------------------------------------------------------------
class TestParseResult:
    """Parse pytest result keywords and percentages."""

    def test_passed_keyword(self) -> None:
        from promptgrimoire.cli.testing import _parse_result

        advance, is_fail = _parse_result("tests/test_foo.py::test_bar PASSED", 10)
        assert advance == 1
        assert is_fail is False

    def test_failed_keyword(self) -> None:
        from promptgrimoire.cli.testing import _parse_result

        advance, is_fail = _parse_result("tests/test_foo.py::test_bar FAILED", 10)
        assert advance == 1
        assert is_fail is True

    def test_error_keyword(self) -> None:
        from promptgrimoire.cli.testing import _parse_result

        advance, is_fail = _parse_result("ERROR tests/test_foo.py", 10)
        assert advance == 1
        assert is_fail is True

    def test_percentage_progress(self) -> None:
        from promptgrimoire.cli.testing import _parse_result

        advance, is_fail = _parse_result("[ 50%]", 100)
        assert advance == 50
        assert is_fail is False

    def test_no_match(self) -> None:
        from promptgrimoire.cli.testing import _parse_result

        advance, is_fail = _parse_result("some random line", 10)
        assert advance == 0
        assert is_fail is False

    def test_percentage_without_total(self) -> None:
        from promptgrimoire.cli.testing import _parse_result

        advance, is_fail = _parse_result("[ 50%]", None)
        assert advance == 0
        assert is_fail is False


# ---------------------------------------------------------------------------
# _handle_collecting_phase
# ---------------------------------------------------------------------------
class TestHandleCollectingPhase:
    """Phase-dispatch helper for the collecting phase."""

    def test_no_collection_line(self) -> None:
        from promptgrimoire.cli.testing import _handle_collecting_phase

        count, transition = _handle_collecting_phase("random line", None)
        assert count is None
        assert transition is False

    def test_collection_detected(self) -> None:
        from promptgrimoire.cli.testing import _handle_collecting_phase

        count, transition = _handle_collecting_phase("collected 42 items", None)
        assert count == 42
        assert transition is True

    def test_zero_collected(self) -> None:
        from promptgrimoire.cli.testing import _handle_collecting_phase

        count, transition = _handle_collecting_phase("collected 0 items", None)
        assert count == 0
        assert transition is True


# ---------------------------------------------------------------------------
# _handle_running_phase
# ---------------------------------------------------------------------------
class TestHandleRunningPhase:
    """Phase-dispatch helper for the running phase."""

    def test_summary_boundary_detected(self) -> None:
        from promptgrimoire.cli.testing import _handle_running_phase

        done, enter_summary = _handle_running_phase(
            "=" * 20,
            progress=None,
            task_id=None,
            total=10,
            done_count=5,
        )
        assert enter_summary is True
        # done_count unchanged when entering summary
        assert done == 5

    def test_result_line_advances(self) -> None:
        from promptgrimoire.cli.testing import _handle_running_phase

        done, enter_summary = _handle_running_phase(
            "tests/test_foo.py::test_bar PASSED",
            progress=None,
            task_id=None,
            total=10,
            done_count=3,
        )
        assert done == 4
        assert enter_summary is False

    def test_no_result_no_advance(self) -> None:
        from promptgrimoire.cli.testing import _handle_running_phase

        done, enter_summary = _handle_running_phase(
            "some random output",
            progress=None,
            task_id=None,
            total=10,
            done_count=3,
        )
        assert done == 3
        assert enter_summary is False


# ---------------------------------------------------------------------------
# _xdist_worker_count
# ---------------------------------------------------------------------------
class TestXdistWorkerCount:
    """Calculate xdist worker count."""

    def test_returns_string(self) -> None:
        from promptgrimoire.cli.testing import _xdist_worker_count

        result = _xdist_worker_count()
        assert isinstance(result, str)
        assert int(result) > 0

    def test_caps_at_16(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from promptgrimoire.cli.testing import _xdist_worker_count

        monkeypatch.setattr(os, "cpu_count", lambda: 64)
        assert int(_xdist_worker_count()) <= 16

    def test_halves_cpu_count(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from promptgrimoire.cli.testing import _xdist_worker_count

        monkeypatch.setattr(os, "cpu_count", lambda: 8)
        assert _xdist_worker_count() == "4"

    def test_fallback_when_cpu_count_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from promptgrimoire.cli.testing import _xdist_worker_count

        monkeypatch.setattr(os, "cpu_count", lambda: None)
        assert _xdist_worker_count() == "2"  # 4 // 2


# ---------------------------------------------------------------------------
# Typer command --help
# ---------------------------------------------------------------------------
class TestTestCommandHelp:
    """All test subcommands respond to --help."""

    def test_test_all_help(self) -> None:
        result = runner.invoke(app, ["test", "all", "--help"])
        assert result.exit_code == 0, result.output
        assert "unit" in result.output.lower() or "integration" in result.output.lower()

    def test_test_changed_help(self) -> None:
        result = runner.invoke(app, ["test", "changed", "--help"])
        assert result.exit_code == 0, result.output

    def test_test_all_fixtures_help(self) -> None:
        result = runner.invoke(app, ["test", "all-fixtures", "--help"])
        assert result.exit_code == 0, result.output

    def test_placeholder_absent(self) -> None:
        """The placeholder command should no longer exist."""
        result = runner.invoke(app, ["test", "placeholder"])
        # Should fail because placeholder is removed
        assert result.exit_code != 0
