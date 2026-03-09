"""Documentation generation and serving commands."""

from __future__ import annotations

import os
import shutil
import sys

import typer
from rich.console import Console

from promptgrimoire.cli._shared import _pre_test_db_cleanup
from promptgrimoire.cli.e2e._server import (
    _start_e2e_server,
    _stop_e2e_server,
)

console = Console()

docs_app = typer.Typer(help="Documentation generation and serving.")

_GENERATED_GUIDE_MARKDOWN = (
    "instructor-setup.md",
    "student-workflow.md",
    "your-personal-grimoire.md",
)


def _make_docs_build_and_serve(action: str | None) -> None:
    """Build MkDocs site, generate PDFs, and optionally serve or deploy."""
    import subprocess
    from pathlib import Path

    project_root = Path(__file__).resolve().parents[3]
    subprocess.run(["uv", "run", "mkdocs", "build"], cwd=project_root, check=True)

    guides_dir = project_root / "docs" / "guides"
    for guide_name in _GENERATED_GUIDE_MARKDOWN:
        md_path = guides_dir / guide_name
        pdf_path = md_path.with_suffix(".pdf")
        subprocess.run(
            [
                "pandoc",
                "--pdf-engine=lualatex",
                f"--resource-path={guides_dir}",
                "-o",
                str(pdf_path),
                str(md_path),
            ],
            check=True,
        )

    if action:
        cmd = ["uv", "run", "mkdocs", action]
        if action == "serve":
            cmd += ["--dev-addr", "localhost:8484"]
        subprocess.run(cmd, cwd=project_root, check=True)


@docs_app.command("build")
def build(
    action: str | None = typer.Argument(
        None, help="Post-build action: serve or gh-deploy"
    ),
) -> None:
    """Generate documentation guides, build MkDocs site, create PDFs."""
    import socket

    from playwright.sync_api import sync_playwright

    from promptgrimoire.docs.scripts.instructor_setup import run_instructor_guide
    from promptgrimoire.docs.scripts.personal_grimoire import (
        run_personal_grimoire_guide,
    )
    from promptgrimoire.docs.scripts.student_workflow import run_student_guide

    if shutil.which("pandoc") is None:
        print(
            "Error: 'pandoc' not found in PATH.\n"
            "Install pandoc before running make-docs."
        )
        sys.exit(1)

    _pre_test_db_cleanup()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        port = s.getsockname()[1]

    os.environ["DEV__AUTH_MOCK"] = "true"
    server_process = None
    pw = None
    browser = None
    try:
        server_process = _start_e2e_server(port)
        base_url = f"http://localhost:{port}"

        pw = sync_playwright().start()
        browser = pw.chromium.launch()
        page = browser.new_page(
            viewport={"width": 1280, "height": 800},
            device_scale_factor=4,
        )

        run_instructor_guide(page, base_url)
        run_student_guide(page, base_url)
        run_personal_grimoire_guide(page, base_url)

    finally:
        if browser is not None:
            browser.close()
        if pw is not None:
            pw.stop()
        if server_process is not None:
            _stop_e2e_server(server_process)
        os.environ.pop("DEV__AUTH_MOCK", None)

    _make_docs_build_and_serve(action)
