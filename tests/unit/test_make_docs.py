"""Tests for make_docs() CLI function.

Covers acceptance criteria AC4.1-AC4.5, AC6.1, AC7.1, AC7.2, and AC8.1.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

import promptgrimoire.cli as cli_module


@pytest.fixture
def _mock_happy_path():
    """Patch all external dependencies so make_docs() can run to completion.

    Mocks Playwright launch chain, guide functions, subprocess calls,
    and server lifecycle. Yields a dict of key mocks for assertions.
    """
    mock_process = MagicMock(name="server_process")
    mock_page = MagicMock(name="page")
    mock_browser = MagicMock(name="browser")
    mock_browser.new_page.return_value = mock_page
    mock_pw = MagicMock(name="pw")
    mock_pw.chromium.launch.return_value = mock_browser

    with (
        patch("shutil.which", return_value="/usr/bin/pandoc"),
        patch.object(cli_module, "_pre_test_db_cleanup"),
        patch.object(
            cli_module, "_start_e2e_server", return_value=mock_process
        ) as mock_start,
        patch.object(cli_module, "_stop_e2e_server") as mock_stop,
        patch("playwright.sync_api.sync_playwright") as mock_sync_pw,
        patch(
            "promptgrimoire.docs.scripts.instructor_setup.run_instructor_guide"
        ) as mock_instructor,
        patch(
            "promptgrimoire.docs.scripts.student_workflow.run_student_guide"
        ) as mock_student,
        patch("subprocess.run") as mock_subprocess_run,
    ):
        mock_sync_pw.return_value.start.return_value = mock_pw
        yield {
            "start": mock_start,
            "stop": mock_stop,
            "process": mock_process,
            "page": mock_page,
            "browser": mock_browser,
            "pw": mock_pw,
            "sync_pw": mock_sync_pw,
            "instructor": mock_instructor,
            "student": mock_student,
            "subprocess_run": mock_subprocess_run,
        }


class TestMakeDocsServerLifecycle:
    """AC4.1: Server starts with mock auth, Playwright launches, guides run."""

    def test_starts_server_with_mock_auth(self, _mock_happy_path, monkeypatch):
        mocks = _mock_happy_path
        monkeypatch.delenv("DEV__AUTH_MOCK", raising=False)

        captured_env: dict[str, str | None] = {}

        def _capture_env_on_start(_port):
            captured_env["DEV__AUTH_MOCK"] = os.environ.get("DEV__AUTH_MOCK")
            return mocks["start"].return_value

        mocks["start"].side_effect = _capture_env_on_start

        cli_module.make_docs()

        mocks["start"].assert_called_once()
        (port,), _ = mocks["start"].call_args
        assert isinstance(port, int)
        assert port > 0
        assert captured_env["DEV__AUTH_MOCK"] == "true"

    def test_launches_playwright_with_correct_viewport(self, _mock_happy_path):
        mocks = _mock_happy_path

        cli_module.make_docs()

        mocks["sync_pw"].assert_called_once()
        mocks["pw"].chromium.launch.assert_called_once()
        mocks["browser"].new_page.assert_called_once_with(
            viewport={"width": 1280, "height": 800},
            device_scale_factor=4,
        )

    def test_both_guides_called_with_page_and_base_url(self, _mock_happy_path):
        mocks = _mock_happy_path

        cli_module.make_docs()

        mocks["instructor"].assert_called_once()
        page_arg, base_url_arg = mocks["instructor"].call_args[0]
        assert page_arg is mocks["page"]
        assert base_url_arg.startswith("http://localhost:")

        mocks["student"].assert_called_once()
        page_arg, base_url_arg = mocks["student"].call_args[0]
        assert page_arg is mocks["page"]
        assert base_url_arg.startswith("http://localhost:")


class TestMakeDocsOutputProduction:
    """AC4.3: Pipeline produces markdown files and screenshots."""

    def test_produces_output_files(self, _mock_happy_path, tmp_path):
        mocks = _mock_happy_path
        md_file = tmp_path / "guides" / "instructor-setup.md"
        screenshot = tmp_path / "guides" / "screenshots" / "instructor-setup-01.png"

        def _create_instructor_output(_page, _base_url):
            md_file.parent.mkdir(parents=True, exist_ok=True)
            md_file.write_text("# Instructor Setup\n")
            screenshot.parent.mkdir(parents=True, exist_ok=True)
            screenshot.write_bytes(b"PNG")

        mocks["instructor"].side_effect = _create_instructor_output

        cli_module.make_docs()

        assert md_file.exists()
        assert screenshot.exists()


class TestMakeDocsGuideOrder:
    """AC4.2: Instructor guide runs before student guide."""

    def test_instructor_runs_before_student(self, _mock_happy_path):
        mocks = _mock_happy_path
        call_order: list[str] = []

        def _record_instructor(*_args, **_kwargs):
            call_order.append("instructor")

        def _record_student(*_args, **_kwargs):
            call_order.append("student")

        mocks["instructor"].side_effect = _record_instructor
        mocks["student"].side_effect = _record_student

        cli_module.make_docs()

        assert call_order == ["instructor", "student"]


class TestMakeDocsErrorHandling:
    """AC4.4: Guide exception propagates (non-zero exit)."""

    def test_guide_exception_propagates(self, _mock_happy_path):
        mocks = _mock_happy_path
        mocks["instructor"].side_effect = RuntimeError("Guide failed")

        with pytest.raises(RuntimeError, match="Guide failed"):
            cli_module.make_docs()


class TestMakeDocsDependencyChecks:
    """AC4.5: Missing pandoc causes early exit without starting server."""

    def test_exits_if_pandoc_missing(self, capsys):
        with (
            patch("shutil.which", return_value=None),
            patch.object(cli_module, "_pre_test_db_cleanup"),
            patch.object(cli_module, "_start_e2e_server") as mock_start,
            patch.object(cli_module, "_stop_e2e_server"),
        ):
            with pytest.raises(SystemExit) as exc_info:
                cli_module.make_docs()

            assert exc_info.value.code == 1
            captured = capsys.readouterr()
            assert "pandoc" in captured.out.lower()
            mock_start.assert_not_called()


class TestMakeDocsCleanup:
    """Playwright and server are cleaned up in all cases."""

    def test_cleanup_on_success(self, _mock_happy_path):
        mocks = _mock_happy_path

        cli_module.make_docs()

        mocks["browser"].close.assert_called_once()
        mocks["pw"].stop.assert_called_once()
        mocks["stop"].assert_called_once_with(mocks["process"])

    def test_cleanup_on_guide_failure(self, _mock_happy_path):
        mocks = _mock_happy_path
        mocks["instructor"].side_effect = RuntimeError("boom")

        with pytest.raises(RuntimeError):
            cli_module.make_docs()

        mocks["browser"].close.assert_called_once()
        mocks["pw"].stop.assert_called_once()
        mocks["stop"].assert_called_once_with(mocks["process"])

    def test_env_var_cleared_after_completion(self, _mock_happy_path, monkeypatch):
        monkeypatch.delenv("DEV__AUTH_MOCK", raising=False)

        cli_module.make_docs()

        assert os.environ.get("DEV__AUTH_MOCK") is None


class TestMakeDocsMkdocsBuild:
    """AC6.1: mkdocs build is called after guide functions complete."""

    def test_mkdocs_build_called_with_cwd(self, _mock_happy_path):
        mocks = _mock_happy_path

        cli_module.make_docs()

        mkdocs_calls = [
            c
            for c in mocks["subprocess_run"].call_args_list
            if c[0][0][:3] == ["uv", "run", "mkdocs"]
        ]
        assert len(mkdocs_calls) == 1
        assert mkdocs_calls[0][0][0] == ["uv", "run", "mkdocs", "build"]
        assert mkdocs_calls[0][1]["check"] is True
        assert "cwd" in mkdocs_calls[0][1]

    def test_mkdocs_build_runs_after_guides(self, _mock_happy_path):
        mocks = _mock_happy_path
        call_order: list[str] = []

        def _record_instructor(*_args, **_kwargs):
            call_order.append("instructor")

        def _record_student(*_args, **_kwargs):
            call_order.append("student")

        def _record_subprocess(cmd, **_kwargs):
            if cmd[:3] == ["uv", "run", "mkdocs"]:
                call_order.append("mkdocs")
            elif cmd[0] == "pandoc":
                call_order.append("pandoc")

        mocks["instructor"].side_effect = _record_instructor
        mocks["student"].side_effect = _record_student
        mocks["subprocess_run"].side_effect = _record_subprocess

        cli_module.make_docs()

        assert "instructor" in call_order
        assert "student" in call_order
        assert "mkdocs" in call_order
        mkdocs_idx = call_order.index("mkdocs")
        assert call_order.index("instructor") < mkdocs_idx
        assert call_order.index("student") < mkdocs_idx


class TestMakeDocsPandocPdf:
    """AC7.1, AC7.2: Pandoc generates PDFs with --resource-path."""

    def test_pandoc_called_for_each_guide(self, _mock_happy_path):
        mocks = _mock_happy_path

        cli_module.make_docs()

        pandoc_calls = [
            c for c in mocks["subprocess_run"].call_args_list if c[0][0][0] == "pandoc"
        ]
        assert len(pandoc_calls) == 2

        input_files = [c[0][0][-1] for c in pandoc_calls]
        assert any("instructor-setup.md" in f for f in input_files)
        assert any("student-workflow.md" in f for f in input_files)

    def test_pandoc_includes_resource_path(self, _mock_happy_path):
        """AC7.2: --resource-path is critical for image resolution."""
        mocks = _mock_happy_path

        cli_module.make_docs()

        pandoc_calls = [
            c for c in mocks["subprocess_run"].call_args_list if c[0][0][0] == "pandoc"
        ]
        for pandoc_call in pandoc_calls:
            cmd = pandoc_call[0][0]
            assert any(arg.startswith("--resource-path") for arg in cmd), (
                f"Missing --resource-path in: {cmd}"
            )

    def test_pandoc_runs_after_mkdocs(self, _mock_happy_path):
        mocks = _mock_happy_path
        call_order: list[str] = []

        def _record_subprocess(cmd, **_kwargs):
            if cmd[:3] == ["uv", "run", "mkdocs"]:
                call_order.append("mkdocs")
            elif cmd[0] == "pandoc":
                call_order.append("pandoc")

        mocks["subprocess_run"].side_effect = _record_subprocess

        cli_module.make_docs()

        assert "mkdocs" in call_order
        assert "pandoc" in call_order
        assert call_order.index("mkdocs") < call_order.index("pandoc")
