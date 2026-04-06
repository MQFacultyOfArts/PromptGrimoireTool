"""Tests for systemcolor and systemturn environment in the LaTeX style file.

Ensures that promptgrimoire-export.sty defines:
1. \\definecolor{systemcolor}{HTML}{E65100} for system message turn markers
2. \\newtcolorbox{systemturn} tcolorbox environment for system message borders
"""

from __future__ import annotations

import pytest

from promptgrimoire.export.pdf_export import STY_SOURCE


class TestSystemTurnLatexDefinitions:
    """The .sty file must define systemcolor and systemturn environment."""

    @pytest.fixture
    def sty_content(self) -> str:
        """Read the .sty file content for assertions."""
        return STY_SOURCE.read_text(encoding="utf-8")

    def test_systemcolor_defined(self, sty_content: str) -> None:
        r"""The .sty must define \definecolor{systemcolor}{HTML}{E65100}."""
        assert r"\definecolor{systemcolor}{HTML}{E65100}" in sty_content, (
            ".sty must define systemcolor for system message turn markers."
        )

    def test_systemcolor_after_assistantcolor(self, sty_content: str) -> None:
        """systemcolor must be defined after assistantcolor for consistency."""
        assistant_pos = sty_content.find(r"\definecolor{assistantcolor}")
        system_pos = sty_content.find(r"\definecolor{systemcolor}")
        assert assistant_pos != -1, "assistantcolor must be defined"
        assert system_pos != -1, "systemcolor must be defined"
        assert system_pos > assistant_pos, (
            "systemcolor must appear after assistantcolor in the .sty file."
        )

    def test_systemturn_environment_defined(self, sty_content: str) -> None:
        r"""The .sty must define a \newtcolorbox{systemturn} environment."""
        assert r"{systemturn}" in sty_content, (
            ".sty must define systemturn tcolorbox environment."
        )

    def test_systemturn_uses_systemcolor(self, sty_content: str) -> None:
        """The systemturn environment must use systemcolor for its border."""
        block_start = sty_content.find(r"\newtcolorbox{systemturn}")
        assert block_start != -1, "systemturn must be defined via \\newtcolorbox"

        # Find the options block by matching braces
        # Skip the {systemturn} part first
        options_start = sty_content.find(
            "{", block_start + len(r"\newtcolorbox{systemturn}")
        )
        assert options_start != -1, "systemturn must have an options block"
        depth = 1
        pos = options_start + 1
        while depth > 0 and pos < len(sty_content):
            if sty_content[pos] == "{":
                depth += 1
            elif sty_content[pos] == "}":
                depth -= 1
            pos += 1
        block = sty_content[block_start:pos]
        assert "systemcolor" in block, (
            "systemturn environment must reference systemcolor for its border."
        )

    def test_systemturn_after_assistantturn(self, sty_content: str) -> None:
        """systemturn must be defined after assistantturn for consistency."""
        assistant_pos = sty_content.find(r"{assistantturn}")
        system_pos = sty_content.find(r"{systemturn}")
        assert assistant_pos != -1, "assistantturn must be defined"
        assert system_pos != -1, "systemturn must be defined"
        assert system_pos > assistant_pos, (
            "systemturn must appear after assistantturn in the .sty file."
        )

    def test_turn_environments_are_breakable(self, sty_content: str) -> None:
        """All speaker turn environments must use tcolorbox with breakable."""
        for env_name in ("userturn", "assistantturn", "systemturn"):
            env_start = sty_content.find(f"\\newtcolorbox{{{env_name}}}")
            assert env_start != -1, f"{env_name} must be defined via \\newtcolorbox"
            # Find the options block
            brace_start = sty_content.find(
                "{", env_start + len(f"\\newtcolorbox{{{env_name}}}")
            )
            brace_end = sty_content.find("}", brace_start + 1)
            options = sty_content[brace_start : brace_end + 1]
            assert "breakable" in options, (
                f"{env_name} must include 'breakable' option to handle oversized turns."
            )

    def test_no_mdframed_dependency(self, sty_content: str) -> None:
        """The .sty must not load mdframed as a package (replaced by tcolorbox)."""
        for line in sty_content.splitlines():
            stripped = line.lstrip()
            if stripped.startswith("%"):
                continue
            assert "mdframed" not in stripped, (
                f".sty must not require mdframed — use tcolorbox instead. "
                f"Found: {stripped!r}"
            )
