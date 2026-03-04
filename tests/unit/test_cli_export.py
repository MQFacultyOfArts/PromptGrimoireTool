"""Tests for the export CLI subcommand."""

from __future__ import annotations

import re
import tempfile
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from promptgrimoire.cli import app

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    return _ANSI_RE.sub("", text)


class TestExportLogHelp:
    """The 'export log' command exposes --tex, --both, and optional user_id."""

    def test_help_shows_options(self) -> None:
        result = runner.invoke(app, ["export", "log", "--help"])
        assert result.exit_code == 0
        plain = _strip_ansi(result.output)
        assert "--tex" in plain
        assert "--both" in plain

    def test_help_shows_user_id_argument(self) -> None:
        result = runner.invoke(app, ["export", "log", "--help"])
        assert "user_id" in _strip_ansi(result.output).lower()


class TestFindExportDir:
    """_find_export_dir resolves the correct directory."""

    def test_finds_specific_user_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        export_dir = tmp_path / "promptgrimoire_export_user123"
        export_dir.mkdir()
        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))

        from promptgrimoire.cli.export import _find_export_dir

        assert _find_export_dir("user123") == export_dir

    def test_exits_when_user_dir_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))

        from promptgrimoire.cli.export import _find_export_dir

        with pytest.raises(SystemExit):
            _find_export_dir("nonexistent")

    def test_finds_most_recent_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import os

        old_dir = tmp_path / "promptgrimoire_export_old"
        old_dir.mkdir()
        new_dir = tmp_path / "promptgrimoire_export_new"
        new_dir.mkdir()
        # Set deterministic mtime: old_dir in the past, new_dir in the future
        os.utime(old_dir, (1_000_000, 1_000_000))
        os.utime(new_dir, (2_000_000, 2_000_000))
        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))

        from promptgrimoire.cli.export import _find_export_dir

        assert _find_export_dir(None) == new_dir

    def test_exits_when_no_dirs_exist(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))

        from promptgrimoire.cli.export import _find_export_dir

        with pytest.raises(SystemExit):
            _find_export_dir(None)


class TestExportLogCommand:
    """Integration tests for the 'export log' command via CliRunner."""

    def test_shows_log_content(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        export_dir = tmp_path / "promptgrimoire_export_abc"
        export_dir.mkdir()
        (export_dir / "annotated_document.log").write_text(
            "This is LaTeX output\n! Error here\n"
        )
        (export_dir / "annotated_document.tex").write_text("\\documentclass{article}\n")
        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))

        result = runner.invoke(app, ["export", "log", "abc"])
        assert result.exit_code == 0, f"output={result.output!r}"
        assert "Export Directory" in result.output

    def test_errors_when_log_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        export_dir = tmp_path / "promptgrimoire_export_abc"
        export_dir.mkdir()
        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))

        result = runner.invoke(app, ["export", "log", "abc"])
        assert result.exit_code != 0

    def test_tex_flag_shows_tex(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        export_dir = tmp_path / "promptgrimoire_export_abc"
        export_dir.mkdir()
        (export_dir / "annotated_document.tex").write_text("\\documentclass{article}\n")
        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))

        result = runner.invoke(app, ["export", "log", "--tex", "abc"])
        assert result.exit_code == 0

    def test_tex_flag_errors_when_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        export_dir = tmp_path / "promptgrimoire_export_abc"
        export_dir.mkdir()
        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))

        result = runner.invoke(app, ["export", "log", "--tex", "abc"])
        assert result.exit_code != 0

    def test_both_flag_shows_context(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        export_dir = tmp_path / "promptgrimoire_export_abc"
        export_dir.mkdir()
        log_text = (
            "Some output\n"
            "! LaTeX Error: Undefined control sequence.\n"
            "l.42 \\badcommand\n"
        )
        (export_dir / "annotated_document.log").write_text(log_text)
        (export_dir / "annotated_document.tex").write_text(
            "\n".join(f"Line {i}" for i in range(1, 60)) + "\n"
        )
        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))

        result = runner.invoke(app, ["export", "log", "--both", "abc"])
        assert result.exit_code == 0
