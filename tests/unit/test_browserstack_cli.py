"""Tests for BrowserStack CLI integration."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING, Any

import click
import pytest
import typer

if TYPE_CHECKING:
    from pathlib import Path


class TestResolveBrowserstackConfig:
    """Profile resolution maps names to YAML files."""

    def test_default_profile_resolves_to_supported(self) -> None:
        from promptgrimoire.cli.e2e._browserstack import resolve_browserstack_config

        path = resolve_browserstack_config(None)
        assert path.name == "supported.yml"
        assert path.exists()

    def test_safari_profile(self) -> None:
        from promptgrimoire.cli.e2e._browserstack import resolve_browserstack_config

        path = resolve_browserstack_config("safari")
        assert path.name == "safari.yml"
        assert path.exists()

    def test_firefox_profile(self) -> None:
        from promptgrimoire.cli.e2e._browserstack import resolve_browserstack_config

        path = resolve_browserstack_config("firefox")
        assert path.name == "firefox.yml"
        assert path.exists()

    def test_unsupported_profile(self) -> None:
        from promptgrimoire.cli.e2e._browserstack import resolve_browserstack_config

        path = resolve_browserstack_config("unsupported")
        assert path.name == "unsupported.yml"
        assert path.exists()

    def test_unknown_profile_raises(self) -> None:
        from promptgrimoire.cli.e2e._browserstack import resolve_browserstack_config

        with pytest.raises(typer.BadParameter, match="Unknown BrowserStack profile"):
            resolve_browserstack_config("chrome")


class TestRunBrowserstackSuite:
    """Suite runner constructs correct commands and cleans up."""

    @pytest.fixture
    def _patch_infra(self, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
        """Patch server lifecycle and DB cleanup, return capture dict."""
        captured: dict[str, Any] = {}

        class _FakeServer:
            pid = 999

        def _fake_pre_test_db_cleanup() -> None:
            return None

        def _fake_allocate_ports(_n: int) -> list[int]:
            return [5555]

        def _fake_start_server(_port: int) -> _FakeServer:
            captured["server_started"] = True
            return _FakeServer()

        def _fake_stop_server(_server: object) -> None:
            captured["server_stopped"] = True

        monkeypatch.setattr(
            "promptgrimoire.cli.e2e._browserstack._pre_test_db_cleanup",
            _fake_pre_test_db_cleanup,
        )
        monkeypatch.setattr(
            "promptgrimoire.cli.e2e._browserstack._allocate_ports",
            _fake_allocate_ports,
        )
        monkeypatch.setattr(
            "promptgrimoire.cli.e2e._browserstack._start_e2e_server",
            _fake_start_server,
        )
        monkeypatch.setattr(
            "promptgrimoire.cli.e2e._browserstack._stop_e2e_server",
            _fake_stop_server,
        )

        # Provide fake BrowserStack credentials via settings
        from unittest.mock import MagicMock

        from pydantic import SecretStr

        fake_bs = MagicMock()
        fake_bs.username = "test_user"
        fake_bs.access_key = SecretStr("test_key")
        fake_settings = MagicMock()
        fake_settings.browserstack = fake_bs
        monkeypatch.setattr(
            "promptgrimoire.cli.e2e._browserstack.get_settings",
            lambda: fake_settings,
        )

        return captured

    def test_command_starts_with_browserstack_sdk_pytest(
        self,
        monkeypatch: pytest.MonkeyPatch,
        _patch_infra: dict[str, Any],
        tmp_path: Path,
    ) -> None:
        from promptgrimoire.cli.e2e._browserstack import run_browserstack_suite

        captured_cmd: list[str] = []

        class _FakeProc:
            pid = 12345

            def wait(self) -> int:
                return 0

            def poll(self) -> int:
                return 0

        def _fake_popen(cmd: list[str], **_kw: Any) -> _FakeProc:
            captured_cmd.extend(cmd)
            return _FakeProc()

        monkeypatch.setattr(subprocess, "Popen", _fake_popen)

        config = tmp_path / "test.yml"
        config.write_text("framework: pytest")

        exit_code = run_browserstack_suite(
            config_path=config,
            user_args=["-k", "smoke"],
            marker_expr="e2e",
        )

        assert exit_code == 0
        assert captured_cmd[0] == "browserstack-sdk"
        assert captured_cmd[1] == "pytest"
        assert "-m" in captured_cmd
        idx = captured_cmd.index("-m")
        assert captured_cmd[idx + 1] == "e2e"
        assert "-k" in captured_cmd

    def test_unsupported_marker_uses_browser_gate(
        self,
        monkeypatch: pytest.MonkeyPatch,
        _patch_infra: dict[str, Any],
        tmp_path: Path,
    ) -> None:
        from promptgrimoire.cli.e2e._browserstack import run_browserstack_suite

        captured_cmd: list[str] = []

        class _FakeProc:
            pid = 12345

            def wait(self) -> int:
                return 0

            def poll(self) -> int:
                return 0

        def _fake_popen(cmd: list[str], **_kw: Any) -> _FakeProc:
            captured_cmd.extend(cmd)
            return _FakeProc()

        monkeypatch.setattr(subprocess, "Popen", _fake_popen)

        config = tmp_path / "unsupported.yml"
        config.write_text("framework: pytest")

        run_browserstack_suite(
            config_path=config,
            user_args=[],
            marker_expr="browser_gate",
        )

        idx = captured_cmd.index("-m")
        assert captured_cmd[idx + 1] == "browser_gate"

    def test_config_file_set_in_env(
        self,
        monkeypatch: pytest.MonkeyPatch,
        _patch_infra: dict[str, Any],
        tmp_path: Path,
    ) -> None:
        from promptgrimoire.cli.e2e._browserstack import run_browserstack_suite

        captured_env: dict[str, str] = {}

        class _FakeProc:
            pid = 12345

            def wait(self) -> int:
                return 0

            def poll(self) -> int:
                return 0

        def _fake_popen(
            _cmd: list[str], *, env: dict[str, str], **_kw: Any
        ) -> _FakeProc:
            captured_env.update(env)
            return _FakeProc()

        monkeypatch.setattr(subprocess, "Popen", _fake_popen)

        config = tmp_path / "test.yml"
        config.write_text("framework: pytest")

        run_browserstack_suite(
            config_path=config,
            user_args=[],
        )

        assert captured_env["BROWSERSTACK_CONFIG_FILE"] == str(config)
        assert captured_env["E2E_BASE_URL"] == "http://localhost:5555"
        assert captured_env["BROWSERSTACK_USERNAME"] == "test_user"
        assert captured_env["BROWSERSTACK_ACCESS_KEY"] == "test_key"

    def test_server_stopped_on_subprocess_failure(
        self,
        monkeypatch: pytest.MonkeyPatch,
        _patch_infra: dict[str, Any],
        tmp_path: Path,
    ) -> None:
        from promptgrimoire.cli.e2e._browserstack import run_browserstack_suite

        def _fake_popen(_cmd: list[str], **_kw: Any) -> None:
            msg = "BrowserStack connection failed"
            raise OSError(msg)

        monkeypatch.setattr(subprocess, "Popen", _fake_popen)

        config = tmp_path / "test.yml"
        config.write_text("framework: pytest")

        with pytest.raises(OSError, match="BrowserStack connection failed"):
            run_browserstack_suite(config_path=config, user_args=[])

        assert _patch_infra["server_started"] is True
        assert _patch_infra["server_stopped"] is True


class TestBrowserstackCredentialCheck:
    """Missing credentials fail before any server starts."""

    def test_missing_credentials_exits(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from unittest.mock import MagicMock

        from pydantic import SecretStr

        from promptgrimoire.cli.e2e import browserstack, e2e_app

        fake_bs = MagicMock()
        fake_bs.username = ""
        fake_bs.access_key = SecretStr("")
        fake_settings = MagicMock()
        fake_settings.browserstack = fake_bs
        monkeypatch.setattr(
            "promptgrimoire.config.get_settings",
            lambda: fake_settings,
        )

        ctx = typer.Context(typer.main.get_command(e2e_app))
        ctx.args = []

        with pytest.raises((SystemExit, click.exceptions.Exit)):
            browserstack(ctx, profile=None)

    def test_missing_access_key_exits(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from unittest.mock import MagicMock

        from pydantic import SecretStr

        from promptgrimoire.cli.e2e import browserstack, e2e_app

        fake_bs = MagicMock()
        fake_bs.username = "test_user"
        fake_bs.access_key = SecretStr("")
        fake_settings = MagicMock()
        fake_settings.browserstack = fake_bs
        monkeypatch.setattr(
            "promptgrimoire.config.get_settings",
            lambda: fake_settings,
        )

        ctx = typer.Context(typer.main.get_command(e2e_app))
        ctx.args = []

        with pytest.raises((SystemExit, click.exceptions.Exit)):
            browserstack(ctx, profile=None)
