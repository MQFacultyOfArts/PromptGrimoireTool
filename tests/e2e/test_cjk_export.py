"""E2E test: CJK + annotated table export download (#351).

Validates that a workspace containing CJK text and annotations inside
table cells can be exported without crash. The downloaded .tex file
must contain \\annotref{} (not \\annot{}) inside longtable regions.

AC4.2: E2E export download completes for CJK workspace.
"""

from __future__ import annotations

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
