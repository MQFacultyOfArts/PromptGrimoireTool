"""BrowserStack E2E runner — single-process invocation with SDK tunnel."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import typer

from promptgrimoire.cli._shared import _pre_test_db_cleanup, console
from promptgrimoire.cli.e2e._server import _start_e2e_server, _stop_e2e_server
from promptgrimoire.cli.e2e._workers import _allocate_ports
from promptgrimoire.config import get_settings

_BROWSERSTACK_PROFILES: dict[str | None, str] = {
    None: "browserstack/supported.yml",
    "safari": "browserstack/safari.yml",
    "firefox": "browserstack/firefox.yml",
    "unsupported": "browserstack/unsupported.yml",
}


def resolve_browserstack_config(profile: str | None) -> Path:
    """Look up a BrowserStack profile name and return the YAML config path.

    Raises ``typer.BadParameter`` for unknown profiles or missing files.
    """
    rel_path = _BROWSERSTACK_PROFILES.get(profile)
    if rel_path is None:
        valid = ", ".join(repr(k) for k in _BROWSERSTACK_PROFILES if k is not None)
        msg = f"Unknown BrowserStack profile: {profile!r}. Valid profiles: {valid}"
        raise typer.BadParameter(msg)

    config_path = Path(rel_path).resolve()
    if not config_path.exists():
        msg = f"BrowserStack config not found: {config_path}"
        raise typer.BadParameter(msg)

    return config_path


def run_browserstack_suite(
    *,
    config_path: Path,
    user_args: list[str],
    marker_expr: str = "e2e",
) -> int:
    """Run the E2E suite via ``browserstack-sdk pytest`` against a local server.

    Starts a NiceGUI server, runs a single blocking subprocess with the
    BrowserStack SDK, and guarantees server cleanup in a finally block.
    """
    _pre_test_db_cleanup()

    port = _allocate_ports(1)[0]
    url = f"http://localhost:{port}"
    server_process = _start_e2e_server(port)
    console.print(f"[green]Server ready at {url}[/]")

    try:
        cmd = [
            "browserstack-sdk",
            "pytest",
            "tests/e2e/",
            "-m",
            marker_expr,
            "-v",
            "--tb=short",
            *user_args,
        ]

        bs = get_settings().browserstack
        env = {
            **os.environ,
            "E2E_BASE_URL": url,
            "BROWSERSTACK_CONFIG_FILE": str(config_path),
            "BROWSERSTACK_USERNAME": bs.username,
            "BROWSERSTACK_ACCESS_KEY": bs.access_key.get_secret_value(),
            "GRIMOIRE_TEST_HARNESS": "1",
        }

        console.print(f"[blue]BrowserStack config: {config_path}[/]")
        result = subprocess.run(cmd, env=env, check=False)
        return result.returncode
    finally:
        _stop_e2e_server(server_process)
