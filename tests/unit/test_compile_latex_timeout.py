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
async def test_semaphore_caps_concurrent_compilations() -> None:
    """The compilation semaphore is initialised from config with value 2.

    Verifies the semaphore's capacity directly — no timers, no sleeps.
    """
    from promptgrimoire.export.pdf import (
        _get_compile_semaphore,
        reset_compile_semaphore,
    )

    reset_compile_semaphore()
    sem = _get_compile_semaphore()

    # Default config: max_concurrent_compilations = 2
    # Acquire both slots — should succeed immediately
    acquired_1 = sem._value
    assert acquired_1 == 2, f"Semaphore should start at 2, got {acquired_1}"

    await sem.acquire()
    await sem.acquire()
    assert sem._value == 0, "Both slots consumed"

    # A third acquire must not succeed (would block), so locked() is True
    assert sem.locked(), "Semaphore should be locked after 2 acquires"

    # Release both
    sem.release()
    sem.release()
    assert sem._value == 2, "Semaphore should be back to 2"

    reset_compile_semaphore()
