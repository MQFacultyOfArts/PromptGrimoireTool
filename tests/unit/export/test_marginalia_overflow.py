"""Tests for marginalia overflow detection and endnote fallback.

When annotations overflow the margin column, marginalia emits placement
warnings in the LaTeX log.  The export pipeline detects these warnings
and recompiles with all annotations routed to endnotes.
"""

from __future__ import annotations

from pathlib import Path

from promptgrimoire.export.pdf import (
    LaTeXCompilationError,
    has_marginalia_placement_warnings,
    inject_annot_force_endnotes,
)
from promptgrimoire.export.worker import user_facing_error


class TestHasMarginaliaPlacementWarnings:
    """Detection of marginalia placement problems in LaTeX logs."""

    def test_detects_placement_warning(self, tmp_path: Path) -> None:
        log = tmp_path / "test.log"
        log.write_text(
            "Some preamble output\n"
            "Package marginalia Warning: Problems in placement."
            " Here are the problems:\n"
            "p1 (1) Moveable item < ysep page bottom\n"
            "p1 (1) Clash: moveable items\n"
        )
        assert has_marginalia_placement_warnings(log) is True

    def test_no_warning_returns_false(self, tmp_path: Path) -> None:
        log = tmp_path / "test.log"
        log.write_text("Some preamble output\nOutput written on test.pdf (1 page)\n")
        assert has_marginalia_placement_warnings(log) is False

    def test_missing_log_returns_false(self, tmp_path: Path) -> None:
        log = tmp_path / "nonexistent.log"
        assert has_marginalia_placement_warnings(log) is False

    def test_empty_log_returns_false(self, tmp_path: Path) -> None:
        log = tmp_path / "test.log"
        log.write_text("")
        assert has_marginalia_placement_warnings(log) is False


class TestInjectAnnotForceEndnotes:
    r"""Injection of \annotforceendnotestrue into .tex files."""

    def test_injects_after_usepackage(self, tmp_path: Path) -> None:
        tex = tmp_path / "test.tex"
        tex.write_text(
            "\\documentclass{article}\n"
            "\\usepackage{promptgrimoire-export}\n"
            "\\begin{document}\n"
            "Hello\n"
            "\\end{document}\n"
        )
        inject_annot_force_endnotes(tex)
        content = tex.read_text()
        assert "\\annotforceendnotestrue" in content
        # Must appear AFTER \usepackage{promptgrimoire-export}
        pkg_pos = content.find("\\usepackage{promptgrimoire-export}")
        flag_pos = content.find("\\annotforceendnotestrue")
        assert flag_pos > pkg_pos

    def test_idempotent_injection(self, tmp_path: Path) -> None:
        """Injecting twice doesn't duplicate the flag."""
        tex = tmp_path / "test.tex"
        tex.write_text(
            "\\documentclass{article}\n"
            "\\usepackage{promptgrimoire-export}\n"
            "\\begin{document}\n"
            "\\end{document}\n"
        )
        inject_annot_force_endnotes(tex)
        inject_annot_force_endnotes(tex)
        content = tex.read_text()
        assert content.count("\\annotforceendnotestrue") == 1

    def test_no_usepackage_line_is_noop(self, tmp_path: Path) -> None:
        """If the .tex doesn't have the expected line, don't crash."""
        tex = tmp_path / "test.tex"
        tex.write_text("\\documentclass{article}\n\\begin{document}\n\\end{document}\n")
        inject_annot_force_endnotes(tex)
        content = tex.read_text()
        assert "\\annotforceendnotestrue" not in content


class TestStyForceEndnotesFlag:
    r"""The .sty file defines \ifannotforceendnotes correctly."""

    def test_flag_defined_in_sty(self) -> None:
        sty_path = (
            Path(__file__).resolve().parents[3]
            / "src"
            / "promptgrimoire"
            / "export"
            / "promptgrimoire-export.sty"
        )
        content = sty_path.read_text()
        assert r"\newif\ifannotforceendnotes" in content

    def test_annot_checks_flag(self) -> None:
        sty_path = (
            Path(__file__).resolve().parents[3]
            / "src"
            / "promptgrimoire"
            / "export"
            / "promptgrimoire-export.sty"
        )
        content = sty_path.read_text()
        assert r"\ifannotforceendnotes" in content

    def test_force_endnotes_path_has_no_marginalia(self) -> None:
        r"""When forcing endnotes, \annot must NOT call \marginalia."""
        sty_path = (
            Path(__file__).resolve().parents[3]
            / "src"
            / "promptgrimoire"
            / "export"
            / "promptgrimoire-export.sty"
        )
        content = sty_path.read_text()
        # Extract the \ifannotforceendnotes branch (up to \else\ifdim)
        start = content.find(r"\ifannotforceendnotes")
        end = content.find(r"\else\ifdim", start)
        force_branch = content[start:end]
        assert r"\marginalia" not in force_branch, (
            "Force-endnotes path must not place anything in the margin"
        )


class TestUserFacingError:
    """LaTeX errors become student-friendly messages."""

    def test_latex_error_gives_actionable_message(self) -> None:
        exc = LaTeXCompilationError(
            "LaTeX compilation failed (exit 12): PDF not created",
            tex_path=Path("/tmp/test.tex"),
            log_path=Path("/tmp/test.log"),
        )
        msg = user_facing_error(exc)
        assert "/tmp" not in msg
        assert "instructor" in msg
        assert "Retrying will not help" in msg

    def test_generic_error_passes_through(self) -> None:
        exc = RuntimeError("something broke")
        assert user_facing_error(exc) == "something broke"
