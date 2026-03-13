"""BrowserStack E2E runner — single-process invocation with SDK tunnel."""

from __future__ import annotations

import os
import signal
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

    The SDK subprocess runs in its own process group so that Ctrl+C kills the
    entire tree (SDK + multiprocessing children + Playwright drivers).
    """
    _pre_test_db_cleanup()

    port = _allocate_ports(1)[0]
    # BrowserStack Local tunnel routes bs-local.com → 127.0.0.1.
    # Tests must navigate to bs-local.com, not localhost, per BrowserStack docs.
    url = f"http://bs-local.com:{port}"
    # Set before _start_e2e_server so the server subprocess inherits it.
    # The server script uses this to force polling-only Socket.IO transport
    # (WebSocket upgrades fail through the BrowserStack Local tunnel).
    os.environ["E2E_BROWSERSTACK"] = "1"
    server_process = _start_e2e_server(port)
    console.print(f"[green]Server ready at {url}[/]")

    proc = None
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
            "E2E_BROWSERSTACK": "1",
        }

        console.print(f"[blue]BrowserStack config: {config_path}[/]")
        proc = subprocess.Popen(
            cmd,
            env=env,
            start_new_session=True,
        )
        return proc.wait()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted — killing BrowserStack process tree[/]")
        if proc is not None:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            proc.wait()
        return 130
    finally:
        if proc is not None and proc.poll() is None:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            proc.wait()
        _stop_e2e_server(server_process)
