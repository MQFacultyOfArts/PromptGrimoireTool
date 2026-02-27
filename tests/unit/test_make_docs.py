"""Tests for make_docs() CLI function."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

import promptgrimoire.cli as cli_module


def _which_side_effect(*, missing: str | None = None) -> object:
    """Return a side_effect callable for shutil.which.

    When *missing* is set, that tool returns None; all others return a fake path.
    """

    def _side_effect(name: str) -> str | None:
        if name == missing:
            return None
        return f"/usr/bin/{name}"

    return _side_effect


@pytest.fixture
def _mock_happy_path():
    """Patch all external dependencies so make_docs() can run to completion.

    Yields a dict of the key mocks for assertions.
    """
    mock_process = MagicMock(name="server_process")

    with (
        patch("shutil.which", side_effect=_which_side_effect()),
        patch.object(cli_module, "_pre_test_db_cleanup"),
        patch.object(
            cli_module, "_start_e2e_server", return_value=mock_process
        ) as mock_start,
        patch.object(cli_module, "_stop_e2e_server") as mock_stop,
        patch("subprocess.run") as mock_run,
    ):
        # All subprocess.run calls succeed by default
        mock_run.return_value = MagicMock(returncode=0)
        yield {
            "start": mock_start,
            "stop": mock_stop,
            "run": mock_run,
            "process": mock_process,
        }


class TestMakeDocsServerLifecycle:
    """AC1.1: Server starts with mock auth and a free port."""

    def test_make_docs_starts_server_with_mock_auth(
        self, _mock_happy_path, monkeypatch
    ):
        mocks = _mock_happy_path
        monkeypatch.delenv("DEV__AUTH_MOCK", raising=False)

        # Capture env state at the moment _start_e2e_server is called
        captured_env: dict[str, str | None] = {}

        original_start = mocks["start"]

        def _capture_env_on_start(_port):
            captured_env["DEV__AUTH_MOCK"] = os.environ.get("DEV__AUTH_MOCK")
            return original_start.return_value

        mocks["start"].side_effect = _capture_env_on_start

        cli_module.make_docs()

        # _start_e2e_server called once with an integer port
        mocks["start"].assert_called_once()
        (port,), _kwargs = mocks["start"].call_args
        assert isinstance(port, int)
        assert port > 0

        # DEV__AUTH_MOCK was set before server started
        assert captured_env["DEV__AUTH_MOCK"] == "true"

    def test_make_docs_invokes_scripts_with_base_url(self, _mock_happy_path):
        mocks = _mock_happy_path

        cli_module.make_docs()

        # At least two subprocess.run calls for the shell scripts
        run_calls = mocks["run"].call_args_list
        script_calls = [c for c in run_calls if "generate-" in str(c)]
        assert len(script_calls) >= 2

        # Each script call should receive the base_url as an argument
        for c in script_calls:
            args_list = c[0][0]  # positional arg 0, element 0
            assert any("http://localhost:" in str(a) for a in args_list)


class TestMakeDocsCleanup:
    """AC1.2: Server and Rodney are stopped even when a script fails."""

    def test_make_docs_stops_server_on_script_failure(self, _mock_happy_path):
        mocks = _mock_happy_path

        # Make script calls fail (but not rodney start/stop)
        def _run_side_effect(cmd, **_kwargs):
            result = MagicMock(returncode=0)
            if cmd[0] == "bash":
                result.returncode = 1
            return result

        mocks["run"].side_effect = _run_side_effect

        with pytest.raises(SystemExit):
            cli_module.make_docs()

        # _stop_e2e_server must still be called
        mocks["stop"].assert_called_once_with(mocks["process"])

        # rodney stop --local must be called in finally block
        rodney_stop_calls = [
            c for c in mocks["run"].call_args_list if c[0][0][:2] == ["rodney", "stop"]
        ]
        assert len(rodney_stop_calls) == 1


class TestMakeDocsRodneyLifecycle:
    """Rodney start/stop lifecycle is correct."""

    def test_make_docs_rodney_start_stop_lifecycle(self, _mock_happy_path):
        mocks = _mock_happy_path

        cli_module.make_docs()

        all_calls = mocks["run"].call_args_list
        cmd_summaries = [c[0][0][:2] for c in all_calls]

        # rodney start --local called
        assert ["rodney", "start"] in cmd_summaries

        # rodney stop --local called
        assert ["rodney", "stop"] in cmd_summaries

        # start before scripts, stop after
        start_idx = cmd_summaries.index(["rodney", "start"])
        stop_idx = cmd_summaries.index(["rodney", "stop"])
        script_indices = [i for i, c in enumerate(cmd_summaries) if c[0] == "bash"]
        assert all(start_idx < si for si in script_indices)
        assert all(stop_idx > si for si in script_indices)


class TestMakeDocsDependencyChecks:
    """AC1.4 / AC1.5: Missing tools cause early exit without starting server."""

    def test_make_docs_exits_if_rodney_missing(self, capsys):
        with (
            patch("shutil.which", side_effect=_which_side_effect(missing="rodney")),
            patch.object(cli_module, "_pre_test_db_cleanup"),
            patch.object(cli_module, "_start_e2e_server") as mock_start,
            patch.object(cli_module, "_stop_e2e_server"),
        ):
            with pytest.raises(SystemExit) as exc_info:
                cli_module.make_docs()

            assert exc_info.value.code == 1
            captured = capsys.readouterr()
            assert "rodney" in captured.out.lower()
            mock_start.assert_not_called()

    def test_make_docs_exits_if_showboat_missing(self, capsys):
        with (
            patch("shutil.which", side_effect=_which_side_effect(missing="showboat")),
            patch.object(cli_module, "_pre_test_db_cleanup"),
            patch.object(cli_module, "_start_e2e_server") as mock_start,
            patch.object(cli_module, "_stop_e2e_server"),
        ):
            with pytest.raises(SystemExit) as exc_info:
                cli_module.make_docs()

            assert exc_info.value.code == 1
            captured = capsys.readouterr()
            assert "showboat" in captured.out.lower()
            mock_start.assert_not_called()
