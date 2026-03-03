"""CliRunner help tests for all Typer sub-apps and import boundary guard."""

from __future__ import annotations

import importlib

from typer.testing import CliRunner

from promptgrimoire.cli import app

runner = CliRunner()


def test_grimoire_help() -> None:
    """Root app --help lists all sub-apps."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for name in ("test", "e2e", "admin", "seed", "export", "docs"):
        assert name in result.output


def test_grimoire_test_help() -> None:
    result = runner.invoke(app, ["test", "--help"])
    assert result.exit_code == 0


def test_grimoire_e2e_help() -> None:
    result = runner.invoke(app, ["e2e", "--help"])
    assert result.exit_code == 0


def test_grimoire_admin_help() -> None:
    result = runner.invoke(app, ["admin", "--help"])
    assert result.exit_code == 0


def test_grimoire_seed_help() -> None:
    result = runner.invoke(app, ["seed", "--help"])
    assert result.exit_code == 0


def test_grimoire_export_help() -> None:
    result = runner.invoke(app, ["export", "--help"])
    assert result.exit_code == 0


def test_grimoire_docs_help() -> None:
    result = runner.invoke(app, ["docs", "--help"])
    assert result.exit_code == 0


def test_old_import_path_not_exported() -> None:
    """Guard: old function names must NOT be importable from promptgrimoire.cli."""
    mod = importlib.import_module("promptgrimoire.cli")
    for name in ("test_all", "test_changed", "seed_data", "manage_users", "make_docs"):
        assert not hasattr(mod, name), f"promptgrimoire.cli should not export {name!r}"
