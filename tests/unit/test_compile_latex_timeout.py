"""Tests for compile_latex timeout and concurrency behaviour.

Verifies:
- Timeout kills the entire process group (not just parent), preventing
  orphaned lualatex processes from leaking memory.
- Semaphore caps concurrent compilations at 2.

Regression tests for 2026-03-15 production OOM outage.
"""

from __future__ import annotations

import asyncio
import os
import textwrap
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from promptgrimoire.export.pdf import (
    LaTeXCompilationError,
    compile_latex,
)

if TYPE_CHECKING:
    from collections.abc import Coroutine
    from pathlib import Path
    from typing import Any


@pytest.mark.asyncio
async def test_timeout_kills_process_group(tmp_path: Path) -> None:
    """On timeout, compile_latex must kill the entire process group.

    Simulates latexmk by spawning a shell script that forks a child
    (mimicking latexmk -> lualatex). Verifies that both parent and child
    are dead after the timeout fires.
    """
    # Script that spawns a child and both sleep forever
    script = tmp_path / "fake_latexmk.sh"
    child_pid_file = tmp_path / "child.pid"
    script.write_text(
        textwrap.dedent(f"""\
        #!/bin/bash
        # Spawn a "lualatex" child that sleeps
        sleep 300 &
        echo $! > {child_pid_file}
        # Parent also sleeps
        sleep 300
        """)
    )
    script.chmod(0o755)

    tex_path = tmp_path / "test.tex"
    tex_path.write_text(r"\documentclass{article}\begin{document}x\end{document}")

    original_wait_for = asyncio.wait_for

    async def short_wait_for(
        coro: Coroutine[Any, Any, Any],
        timeout: float | None = None,  # noqa: ARG001
    ) -> Any:
        return await original_wait_for(coro, timeout=1)

    with (
        patch("promptgrimoire.export.pdf.get_latexmk_path", return_value=str(script)),
        patch.object(asyncio, "wait_for", short_wait_for),
        pytest.raises(LaTeXCompilationError, match="timed out"),
    ):
        await compile_latex(tex_path, output_dir=tmp_path)

    # Give the OS a moment to clean up
    await asyncio.sleep(0.2)

    # Verify the child process was also killed
    assert child_pid_file.exists(), "Child PID file should have been written"
    child_pid = int(child_pid_file.read_text().strip())

    # Check that the child is dead (os.kill with signal 0 probes without killing)
    with pytest.raises(OSError):
        os.kill(child_pid, 0)


@pytest.mark.asyncio
async def test_semaphore_caps_concurrent_compilations(tmp_path: Path) -> None:
    """Only 2 LaTeX compilations may run concurrently; a 3rd must wait.

    Uses a fake latexmk that signals when it starts and then blocks
    until released. Verifies the semaphore prevents more than 2
    concurrent subprocess launches.
    """
    # Track how many fake compilations are running concurrently
    running = asyncio.Event()
    concurrent_count = 0
    max_concurrent = 0
    release = asyncio.Event()

    async def fake_run_latexmk(tex_path: Path, output_dir: Path) -> Path:
        nonlocal concurrent_count, max_concurrent
        concurrent_count += 1
        max_concurrent = max(max_concurrent, concurrent_count)
        if concurrent_count >= 2:
            running.set()
        try:
            await release.wait()
        finally:
            concurrent_count -= 1
        # Create a fake PDF so compile_latex doesn't complain
        pdf_path = output_dir / (tex_path.stem + ".pdf")
        pdf_path.write_bytes(b"%PDF-1.4 fake")
        return pdf_path

    # Create 3 distinct tex files
    tex_paths = []
    for i in range(3):
        d = tmp_path / f"job{i}"
        d.mkdir()
        tex = d / "test.tex"
        tex.write_text(r"\documentclass{article}\begin{document}x\end{document}")
        tex_paths.append(tex)

    with patch("promptgrimoire.export.pdf._run_latexmk", side_effect=fake_run_latexmk):
        # Launch 3 concurrent compile_latex calls
        tasks = [
            asyncio.create_task(compile_latex(tp, output_dir=tp.parent))
            for tp in tex_paths
        ]

        # Wait until 2 are running (semaphore should block the 3rd)
        await asyncio.wait_for(running.wait(), timeout=2)
        await asyncio.sleep(0.05)  # let the 3rd task attempt to acquire

        assert concurrent_count == 2, (
            f"Expected 2 concurrent, got {concurrent_count}. "
            "Semaphore is not limiting concurrency."
        )

        # Release all and let them finish
        release.set()
        await asyncio.gather(*tasks)

    assert max_concurrent == 2, (
        f"Peak concurrency was {max_concurrent}, expected 2. "
        "Semaphore did not cap concurrent compilations."
    )
