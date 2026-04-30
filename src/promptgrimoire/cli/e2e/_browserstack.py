"""BrowserStack E2E runner — quarantined.

The ``browserstack-sdk`` dependency was removed on 2026-04-30 in response
to a vendor concern. This module is preserved so the CLI command and
profile-resolution helper remain importable, but ``run_browserstack_suite``
short-circuits with a clear error rather than spawning the SDK subprocess.
To revive: re-add ``browserstack-sdk`` to ``pyproject.toml``, restore
``BrowserstackConfig`` in ``config.py``, and recover this file from git
history (commit prior to the quarantine).
"""

from __future__ import annotations

from pathlib import Path

import typer

from promptgrimoire.cli._shared import console

QUARANTINE_MESSAGE = (
    "BrowserStack support is quarantined: the browserstack-sdk dependency and "
    "BROWSERSTACK__* config were removed on 2026-04-30. The CLI command is "
    "preserved for discoverability, but no SDK invocation will occur."
)

_BROWSERSTACK_PROFILES: dict[str | None, str] = {
    None: "browserstack/supported.yml",
    "safari": "browserstack/safari.yml",
    "firefox": "browserstack/firefox.yml",
    "unsupported": "browserstack/unsupported.yml",
}


def resolve_browserstack_config(profile: str | None) -> Path:
    """Look up a BrowserStack profile name and return the YAML config path.

    Retained because it does not depend on the SDK; used by tests verifying
    the profile-name → file mapping is intact for revival.
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
    """Quarantine stub. Prints a notice and exits non-zero without invoking the SDK."""
    del config_path, user_args, marker_expr
    console.print(f"[red]{QUARANTINE_MESSAGE}[/]")
    raise typer.Exit(code=1)
