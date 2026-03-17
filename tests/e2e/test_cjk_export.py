"""E2E test: CJK + annotated table export download (#351).

Validates that a workspace containing CJK text and annotations inside
table cells can be exported without crash. The downloaded .tex file
must contain \\annotref{} (not \\annot{}) inside longtable regions.

The slow variant (full compilation) also exercises the luaotfload
color-emoji PNG cache path, which requires a writable cwd. This
catches regressions where the latexmk subprocess inherits a read-only
working directory (e.g. systemd ProtectSystem=strict).

AC4.2: E2E export download completes for CJK workspace.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from playwright.sync_api import Browser

from promptgrimoire.docs.helpers import wait_for_text_walker
from tests.e2e.conftest import _authenticate_page
from tests.e2e.db_fixtures import _create_workspace_via_db
from tests.e2e.export_tools import export_annotation_tex_text

FIXTURE_DIR = Path(__file__).parents[1] / "fixtures"


def _load_cjk_fixture() -> str:
    path = FIXTURE_DIR / "workspace_cjk_annotated_table.html"
    return path.read_text()


@pytest.mark.e2e
class TestCjkAnnotatedTableExport:
    """AC4.2: CJK + annotated table exports without crash."""

    def test_export_download_completes(
        self,
        browser: Browser,
        app_server: str,
    ) -> None:
        """Download completes and .tex contains \\annotref."""
        context = browser.new_context()
        page = context.new_page()

        try:
            email = _authenticate_page(page, app_server)
            html = _load_cjk_fixture()
            workspace_id = _create_workspace_via_db(
                email,
                html,
                seed_tags=False,
            )

            page.goto(
                f"{app_server}/annotation?workspace_id={workspace_id}",
            )
            wait_for_text_walker(page, timeout=15000)

            result = export_annotation_tex_text(page)

            # The fix: \annotref inside table, not \annot
            assert "\\annotref{" in result
        finally:
            page.goto("about:blank")
            page.close()
            context.close()

    def test_full_pdf_compilation(
        self,
        browser: Browser,
        app_server: str,
    ) -> None:
        """Slow lane: CJK + emoji compiles to valid PDF.

        Exercises the luaotfload color-emoji PNG cache path which
        requires a writable cwd. Catches the ProtectSystem=strict
        regression where latexmk inherits a read-only working directory.

        Run via: uv run grimoire e2e slow
        """
        if os.environ.get("E2E_SKIP_LATEXMK", "1") != "0":
            pytest.skip("run via `uv run grimoire e2e slow` for full PDF compilation")

        context = browser.new_context()
        page = context.new_page()

        try:
            email = _authenticate_page(page, app_server)
            # Use plain CJK + emoji HTML without pre-baked annotation
            # colour refs — the E2E pipeline has no matching tag defs,
            # so data-annots colour names would cause undefined-colour
            # errors during compilation.
            html = (
                "<p>日本語のテスト文書です。</p>\n"
                "<table><tr><td>項目</td><td>内容</td></tr></table>\n"
                "<p>✅ 完了 😊 よくできました</p>"
            )
            workspace_id = _create_workspace_via_db(
                email,
                html,
                seed_tags=False,
            )

            page.goto(
                f"{app_server}/annotation?workspace_id={workspace_id}",
            )
            wait_for_text_walker(page, timeout=15000)

            result = export_annotation_tex_text(page)

            assert result.is_pdf, (
                f"Expected compiled PDF, got .tex "
                f"(suggested: {result.suggested_filename!r})"
            )
            assert result.size_bytes is not None and result.size_bytes > 5000, (
                f"PDF too small ({result.size_bytes} bytes), likely corrupt"
            )
        finally:
            page.goto("about:blank")
            page.close()
            context.close()
