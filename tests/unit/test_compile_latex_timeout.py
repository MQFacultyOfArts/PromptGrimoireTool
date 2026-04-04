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
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from promptgrimoire.export.pdf import (
    LaTeXCompilationError,
    compile_latex,
    reset_compile_semaphore,
)

if TYPE_CHECKING:
    from collections.abc import Coroutine
    from typing import Any


@pytest.fixture(autouse=True)
def _reset_semaphore() -> None:
    """Ensure a fresh semaphore for each test — prevents cross-test leakage."""
    reset_compile_semaphore()


@pytest.mark.asyncio
async def test_timeout_kills_process_group(tmp_path: Path) -> None:
    """On timeout, compile_latex must kill the entire process group.

    Simulates latexmk by spawning a shell script that forks a child
    (mimicking latexmk -> lualatex). Verifies that both parent and child
    are dead after the timeout fires.
    """
    # Simulate latexmk spawning lualatex via os.fork().  Bash's &
    # operator creates separate process groups in Docker runtimes
    # (gh act with tini), which doesn't model latexmk's actual
    # fork behaviour.  os.fork() keeps the child in the parent's
    # process group, matching production semantics.
    script = tmp_path / "fake_latexmk.py"
    child_pid_file = tmp_path / "child.pid"
    diag_file = tmp_path / "diag.txt"
    script.write_text(
        textwrap.dedent(f"""\
        #!/usr/bin/env python3
        import os, time
        parent_pid = os.getpid()
        parent_pgid = os.getpgrp()
        child = os.fork()
        if child == 0:
            child_pgid = os.getpgrp()
            with open("{diag_file}", "w") as f:
                f.write(f"parent_pid={{parent_pid}} parent_pgid={{parent_pgid}} "
                        f"child_pid={{os.getpid()}} child_pgid={{child_pgid}}\\n")
            time.sleep(300)
        else:
            with open("{child_pid_file}", "w") as f:
                f.write(str(child))
            time.sleep(300)
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

    killpg_calls: list[tuple[int, int]] = []
    original_killpg = os.killpg

    def _recording_killpg(pgid: int, sig: int) -> None:
        killpg_calls.append((pgid, sig))
        original_killpg(pgid, sig)

    with (
        patch("promptgrimoire.export.pdf.get_latexmk_path", return_value=str(script)),
        patch.object(asyncio, "wait_for", short_wait_for),
        patch("promptgrimoire.export.pdf.os.killpg", _recording_killpg),
        pytest.raises(LaTeXCompilationError, match="timed out"),
    ):
        await compile_latex(tex_path, output_dir=tmp_path)

    # Verify the child process was killed.  SIGKILL delivery is
    # asynchronous — the kernel queues the signal but the target must be
    # scheduled to receive it.  We wait for the /proc entry to show the
    # process is dead (zombie 'Z') or gone (fully reaped).  os.kill(pid, 0)
    # succeeds on zombies, so /proc/PID/stat is the authoritative check.
    assert child_pid_file.exists(), "Child PID file should have been written"
    child_pid = int(child_pid_file.read_text().strip())
    proc_stat = Path(f"/proc/{child_pid}/stat")

    deadline = asyncio.get_event_loop().time() + 2.0
    while asyncio.get_event_loop().time() < deadline:
        if not proc_stat.exists():
            break  # Fully reaped
        stat_fields = proc_stat.read_text().split()
        state = stat_fields[2] if len(stat_fields) > 2 else "?"
        if state == "Z":
            break  # Zombie — killed but not yet reaped (Docker/tini)
        await asyncio.sleep(0.05)
    else:
        state = "?"
        if proc_stat.exists():
            stat_fields = proc_stat.read_text().split()
            state = stat_fields[2] if len(stat_fields) > 2 else "?"
        pytest.fail(
            f"Child {child_pid} still in state '{state}' after 2s. "
            f"killpg_calls={killpg_calls}"
        )


@pytest.mark.asyncio
async def test_semaphore_caps_concurrent_compilations(tmp_path: Path) -> None:
    """Only 2 LaTeX compilations may run concurrently; a 3rd must wait.

    Load-invariant: no sleeps, no timeouts, no mid-flight observation.

    Each fake latexmk increments a concurrent counter on entry, then
    waits on a shared ``rendezvous`` event.  The second task to enter
    sets the event, proving both tasks are inside simultaneously.
    All tasks (including the 3rd, which enters after the first two
    finish) proceed once the event is set.

    If the semaphore is broken and allows 3 concurrent entries,
    ``max_concurrent`` will be 3.  If it works, it will be exactly 2.
    """
    rendezvous = asyncio.Event()
    max_concurrent = 0
    concurrent_count = 0
    entered_count = 0

    async def fake_run_latexmk(tex_path: Path, output_dir: Path) -> Path:
        nonlocal concurrent_count, max_concurrent, entered_count
        concurrent_count += 1
        max_concurrent = max(max_concurrent, concurrent_count)
        entered_count += 1
        if entered_count >= 2:
            rendezvous.set()
        try:
            await rendezvous.wait()
        finally:
            concurrent_count -= 1
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
        tasks = [
            asyncio.create_task(compile_latex(tp, output_dir=tp.parent))
            for tp in tex_paths
        ]
        await asyncio.gather(*tasks)

    assert max_concurrent == 2, (
        f"Peak concurrency was {max_concurrent}, expected 2. "
        "Semaphore did not cap concurrent compilations."
    )
