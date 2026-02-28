"""Tests for systemcolor and systemturn environment in the LaTeX style file.

Ensures that promptgrimoire-export.sty defines:
1. \\definecolor{systemcolor}{HTML}{E65100} for system message turn markers
2. \\newmdenv[...]{systemturn} mdframed environment for system message borders
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
        r"""The .sty must define a \newmdenv{systemturn} environment."""
        assert r"{systemturn}" in sty_content, (
            ".sty must define systemturn mdframed environment."
        )
        assert "newmdenv" in sty_content and "systemturn" in sty_content, (
            "systemturn must be defined via \\newmdenv."
        )

    def test_systemturn_uses_systemcolor(self, sty_content: str) -> None:
        """The systemturn environment must use systemcolor for its border."""
        # Find the systemturn block and verify it references systemcolor
        system_env_start = sty_content.find(r"{systemturn}")
        assert system_env_start != -1, "systemturn environment must exist"

        # Look backwards from {systemturn} to find the newmdenv block start
        block_start = sty_content.rfind(r"\newmdenv[", 0, system_env_start)
        assert block_start != -1, "systemturn must be defined via \\newmdenv["

        block = sty_content[block_start : system_env_start + len("{systemturn}")]
        assert "linecolor=systemcolor" in block, (
            "systemturn environment must use linecolor=systemcolor."
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
