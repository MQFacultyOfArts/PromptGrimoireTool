"""Tests for the latexmk-stage guard used by the CLI harness."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from promptgrimoire.export.pdf import compile_latex
from tests.conftest import requires_full_latexmk, requires_latexmk

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.asyncio
async def test_requires_latexmk_short_circuits_at_compile_call(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The guard runs pre-compile setup, then stops at compile_latex()."""

    tex_path = tmp_path / "test.tex"
    tex_path.write_text(
        "\\documentclass{article}\n\\begin{document}\nHello\n\\end{document}\n"
    )
    events: list[str] = []

    @requires_latexmk
    async def _compile_stage_test() -> None:
        events.append("before-compile")
        await compile_latex(tex_path, output_dir=tmp_path)
        events.append("after-compile")

    monkeypatch.setenv("GRIMOIRE_TEST_SKIP_LATEXMK", "1")

    await _compile_stage_test()

    assert events == ["before-compile"]


def test_requires_full_latexmk_marks_suite_for_deselection() -> None:
    """Fixture-heavy compile tests should be excluded via marker filtering."""

    @requires_full_latexmk
    class _FixtureHeavyCompileTests:
        def test_placeholder(self) -> None:
            pytest.fail("full compile tests should be deselected from `test all`")

    marks = getattr(_FixtureHeavyCompileTests, "pytestmark", [])
    assert any(mark.name == "latexmk_full" for mark in marks)
