"""Tests for cli/testing.py — test runner commands and streaming helpers.

Tests cover:
- Pure parsing helpers (_parse_collection, _is_summary_boundary, _parse_result)
- Phase-dispatch helpers (_handle_collecting_phase, _handle_running_phase)
- _xdist_worker_count calculation
- _stream_plain output filtering
- Typer command --help outputs
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from typer.testing import CliRunner

if TYPE_CHECKING:
    import pytest

from promptgrimoire.cli import app

runner = CliRunner()


def _capture_run_pytest(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """Capture `_run_pytest` arguments without starting subprocesses."""
    from promptgrimoire.cli import testing

    captured: dict[str, object] = {}

    def _fake_run_pytest(
        title: str,
        log_path,
        default_args: list[str],
        extra_args: list[str] | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> int:
        captured["title"] = title
        captured["log_path"] = log_path
        captured["default_args"] = default_args
        captured["extra_args"] = extra_args
        captured["extra_env"] = extra_env
        return 0

    monkeypatch.setattr(testing, "_run_pytest", _fake_run_pytest)
    monkeypatch.setattr(testing, "_run_bats", lambda: 0)
    return captured


def _marker_expression(default_args: list[str]) -> str:
    """Return the pytest marker expression from a command arg list."""
    marker_index = default_args.index("-m")
    return default_args[marker_index + 1]


def _captured_default_args(captured: dict[str, object]) -> list[str]:
    """Return captured default args with a concrete type for test assertions."""
    default_args = captured["default_args"]
    assert isinstance(default_args, list)
    assert all(isinstance(arg, str) for arg in default_args)
    return [arg for arg in default_args if isinstance(arg, str)]


def _captured_extra_args(captured: dict[str, object]) -> list[str]:
    """Return captured extra args with a concrete type for test assertions."""
    extra_args = captured["extra_args"]
    assert isinstance(extra_args, list)
    assert all(isinstance(arg, str) for arg in extra_args)
    return [arg for arg in extra_args if isinstance(arg, str)]


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
    """Xdist worker count returns 'auto'."""

    def test_returns_auto(self) -> None:
        from promptgrimoire.cli.testing import _xdist_worker_count

        assert _xdist_worker_count() == "auto"


# ---------------------------------------------------------------------------
# _stream_plain output filtering
# ---------------------------------------------------------------------------
class TestStreamPlain:
    """_stream_plain suppresses pre-summary output except FAILED/ERROR."""

    def _make_mock_process(self, lines: list[str], returncode: int = 0):
        """Create a mock Popen with stdout as a list of lines."""
        from unittest.mock import MagicMock

        proc = MagicMock()
        proc.stdout = lines
        proc.returncode = returncode
        proc.wait.return_value = None
        return proc

    def test_failed_line_printed_before_summary(self, capsys) -> None:
        import io

        from promptgrimoire.cli.testing import _stream_plain

        lines = [
            "===== test session starts =====\n",
            "tests/unit/test_foo.py::test_bar PASSED\n",
            "tests/unit/test_baz.py::test_qux FAILED\n",
            "===== 1 failed =====\n",
            "FAILURES\n",
        ]
        proc = self._make_mock_process(lines)
        log = io.StringIO()
        _stream_plain(proc, log)

        out = capsys.readouterr().out
        assert "FAILED" in out
        assert "PASSED" not in out

    def test_lines_suppressed_before_second_separator(self, capsys) -> None:
        import io

        from promptgrimoire.cli.testing import _stream_plain

        lines = [
            "===== test session starts =====\n",
            "collecting ... collected 5 items\n",
            "tests/test_a.py::test_1 PASSED\n",
        ]
        proc = self._make_mock_process(lines)
        log = io.StringIO()
        _stream_plain(proc, log)

        out = capsys.readouterr().out
        assert "collecting" not in out
        assert "PASSED" not in out

    def test_all_lines_printed_after_second_separator(self, capsys) -> None:
        import io

        from promptgrimoire.cli.testing import _stream_plain

        lines = [
            "===== test session starts =====\n",
            "tests/test_a.py PASSED\n",
            "===== 1 passed =====\n",
            "summary details here\n",
        ]
        proc = self._make_mock_process(lines)
        log = io.StringIO()
        _stream_plain(proc, log)

        out = capsys.readouterr().out
        assert "1 passed" in out
        assert "summary details" in out

    def test_all_lines_written_to_log(self) -> None:
        import io

        from promptgrimoire.cli.testing import _stream_plain

        lines = ["line1\n", "line2\n", "line3\n"]
        proc = self._make_mock_process(lines)
        log = io.StringIO()
        _stream_plain(proc, log)

        assert log.getvalue() == "line1\nline2\nline3\n"


# ---------------------------------------------------------------------------
# _dispatch_progress_line phase-state-machine
# ---------------------------------------------------------------------------
class TestDispatchProgressLine:
    """_dispatch_progress_line routes lines through collecting/running/summary."""

    def test_summary_phase_passthrough(self, capsys) -> None:
        from unittest.mock import MagicMock

        from rich.progress import TaskID

        from promptgrimoire.cli.testing import _dispatch_progress_line

        progress = MagicMock()
        phase, _count, _done = _dispatch_progress_line(
            "summary line",
            "summary line\n",
            "summary",
            None,
            0,
            progress,
            TaskID(0),
        )
        assert phase == "summary"
        out = capsys.readouterr().out
        assert "summary line" in out

    def test_collecting_to_running_transition(self) -> None:
        from unittest.mock import MagicMock

        from rich.progress import TaskID

        from promptgrimoire.cli.testing import _dispatch_progress_line

        progress = MagicMock()
        phase, count, _done = _dispatch_progress_line(
            "collected 42 items",
            "collected 42 items\n",
            "collecting",
            None,
            0,
            progress,
            TaskID(0),
        )
        assert phase == "running"
        assert count == 42

    def test_running_to_summary_transition(self) -> None:
        from unittest.mock import MagicMock

        from rich.progress import TaskID

        from promptgrimoire.cli.testing import _dispatch_progress_line

        progress = MagicMock()
        phase, _count, _done = _dispatch_progress_line(
            "=" * 20,
            "=" * 20 + "\n",
            "running",
            10,
            5,
            progress,
            TaskID(0),
        )
        assert phase == "summary"
        progress.stop.assert_called_once()


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

    def test_test_smoke_help(self) -> None:
        result = runner.invoke(app, ["test", "smoke", "--help"])
        assert result.exit_code == 0, result.output

    def test_placeholder_absent(self) -> None:
        """The placeholder command should no longer exist."""
        result = runner.invoke(app, ["test", "placeholder"])
        # Should fail because placeholder is removed
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# CLI test command wiring
# ---------------------------------------------------------------------------
class TestTestingCommands:
    """CLI test commands pass the expected lane exclusion arguments."""

    def test_test_all_excludes_e2e_and_nicegui_ui(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured = _capture_run_pytest(monkeypatch)

        result = runner.invoke(app, ["test", "all"])

        assert result.exit_code == 0, result.output
        default_args = _captured_default_args(captured)
        assert _marker_expression(default_args) == (
            "not e2e and not nicegui_ui and not latexmk_full and not smoke"
        )
        assert "tests/unit" in default_args
        assert captured["title"] == (
            "Unit Tests (excludes smoke, E2E, NiceGUI UI, latexmk)"
        )

    def test_test_all_sets_latexmk_skip_guard(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`test all` enables the latexmk skip guard only for that invocation."""
        captured = _capture_run_pytest(monkeypatch)

        result = runner.invoke(app, ["test", "all"])

        assert result.exit_code == 0, result.output
        assert captured["extra_env"] == {"GRIMOIRE_TEST_SKIP_LATEXMK": "1"}

    def test_test_changed_excludes_e2e_and_nicegui_ui(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from promptgrimoire.cli import testing

        monkeypatch.setattr(testing, "_depper_base_ref", lambda: "abc123def456")
        captured = _capture_run_pytest(monkeypatch)

        result = runner.invoke(app, ["test", "changed"])

        assert result.exit_code == 0, result.output
        default_args = _captured_default_args(captured)
        assert _marker_expression(default_args) == "not e2e and not nicegui_ui"
        assert "--depper-base-branch=abc123def456" in default_args
        assert "abc123def456" in str(captured["title"])

    def test_test_smoke_selects_smoke_marker(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured = _capture_run_pytest(monkeypatch)

        result = runner.invoke(app, ["test", "smoke"])

        assert result.exit_code == 0, result.output
        default_args = _captured_default_args(captured)
        assert _marker_expression(default_args) == "smoke"

    def test_test_smoke_runs_serial(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Smoke tests run serially — no -n flag in default args."""
        captured = _capture_run_pytest(monkeypatch)

        result = runner.invoke(app, ["test", "smoke"])

        assert result.exit_code == 0, result.output
        default_args = _captured_default_args(captured)
        assert "-n" not in default_args

    def test_test_smoke_clears_addopts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Smoke command clears addopts to prevent double-exclusion."""
        captured = _capture_run_pytest(monkeypatch)

        result = runner.invoke(app, ["test", "smoke"])

        assert result.exit_code == 0, result.output
        default_args = _captured_default_args(captured)
        assert "-o" in default_args
        addopts_idx = default_args.index("-o")
        assert default_args[addopts_idx + 1] == "addopts="

    def test_test_all_fixtures_removed(self) -> None:
        """AC4.2: all-fixtures command no longer exists."""
        result = runner.invoke(app, ["test", "all-fixtures"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# -x / --ff passthrough
# ---------------------------------------------------------------------------
class TestPytestFlagPassthrough:
    """-x and --ff flags are forwarded to pytest via extra_args."""

    def test_test_all_exit_first(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured = _capture_run_pytest(monkeypatch)
        result = runner.invoke(app, ["test", "all", "-x"])
        assert result.exit_code == 0, result.output
        assert "-x" in _captured_extra_args(captured)

    def test_test_all_failed_first(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured = _capture_run_pytest(monkeypatch)
        result = runner.invoke(app, ["test", "all", "--ff"])
        assert result.exit_code == 0, result.output
        assert "--ff" in _captured_extra_args(captured)

    def test_test_all_both_flags(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured = _capture_run_pytest(monkeypatch)
        result = runner.invoke(app, ["test", "all", "-x", "--ff"])
        assert result.exit_code == 0, result.output
        extra = _captured_extra_args(captured)
        assert "-x" in extra
        assert "--ff" in extra

    def test_no_flags_no_injection(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured = _capture_run_pytest(monkeypatch)
        result = runner.invoke(app, ["test", "all"])
        assert result.exit_code == 0, result.output
        extra = _captured_extra_args(captured)
        assert "-x" not in extra
        assert "--ff" not in extra


class TestNiceguiUiFileWhitelist:
    """Guard: every nicegui_ui-marked test file must be in _NICEGUI_UI_FILES.

    If a test file uses ``pytest.mark.nicegui_ui`` but is NOT in the
    whitelist, ``grimoire test run <file>`` routes it through the plain
    pytest runner (no NiceGUI app, no /login route) → 404 on auth.
    """

    def test_all_nicegui_ui_files_in_whitelist(self) -> None:
        """Scan integration tests for nicegui_ui marker, verify whitelist."""
        from pathlib import Path

        from promptgrimoire.cli.testing import _NICEGUI_UI_FILES

        integration_dir = Path("tests/integration")
        missing: list[str] = []

        for py_file in sorted(integration_dir.glob("test_*.py")):
            source = py_file.read_text()
            if "nicegui_ui" in source and py_file.name not in _NICEGUI_UI_FILES:
                missing.append(py_file.name)

        assert not missing, (
            f"Test files with nicegui_ui marker missing from "
            f"_NICEGUI_UI_FILES in cli/testing.py: {missing}\n"
            f"Add them so 'grimoire test run' routes to the NiceGUI lane."
        )
