"""E2E test: browser-suggested filename for PDF export.

Validates that the annotation page's PDF export suggests a descriptive
filename to the browser, not the old ``workspace_{uuid}`` pattern.

Acceptance Criteria:
- pdf-export-filename-271.AC5.3: Suggested filename matches the naming policy.
- pdf-export-filename-271.AC5.4: Old ``workspace_{uuid}`` basename is rejected.
- pdf-export-filename-271.AC4.3: Annotate and Respond tabs yield the same filename.

Traceability:
- Issue: #271 (PDF export filename convention)
- Design: docs/design-plans/2026-03-08-pdf-export-filename-271.md
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from playwright.sync_api import Browser

from tests.e2e.annotation_helpers import (
    _create_workspace_for_filename_export,
    export_annotation_tex_text,
    wait_for_text_walker,
)
from tests.e2e.conftest import _authenticate_page


# The expected filename stem is built literally from the deterministic
# metadata in _create_workspace_for_filename_export().
#
# Date assumption: the E2E server and the Playwright runner share the
# same host, so server-local date == test-runner-local date. If this
# harness ever becomes distributed (server on a different machine or
# timezone), freeze or inject the date explicitly instead of relying on
# host-local coincidence. The right injection point on the server side
# is `_server_local_export_date` in
# `src/promptgrimoire/pages/annotation/pdf_export.py`.
def _expected_stem() -> str:
    today = datetime.now().strftime("%Y%m%d")
    return f"LAWS5000_Lovelace_Ada_Final_Essay_Week_3_Response_{today}"


@pytest.mark.e2e
class TestPdfExportFilename:
    """Browser-boundary filename assertions for PDF export."""

    def test_fast_lane_descriptive_stem(
        self,
        browser: Browser,
        app_server: str,
    ) -> None:
        """Fast lane: descriptive stem preserved even when download is .tex.

        AC5.3: suggested filename matches naming policy.
        AC5.4: old workspace_{uuid} pattern is NOT used.
        """
        context = browser.new_context()
        page = context.new_page()

        try:
            email = _authenticate_page(page, app_server)
            workspace_id = _create_workspace_for_filename_export(email)

            page.goto(f"{app_server}/annotation?workspace_id={workspace_id}")
            wait_for_text_walker(page, timeout=15000)

            result = export_annotation_tex_text(page)
            stem = _expected_stem()

            # The download may be .tex (fast lane) or .pdf (slow lane).
            # Either way, the descriptive stem must be present.
            assert result.suggested_filename in (
                f"{stem}.tex",
                f"{stem}.pdf",
            ), (
                f"Expected stem '{stem}' with .tex or .pdf extension, "
                f"got: {result.suggested_filename!r}"
            )

            # Regression: must NOT match the old workspace_{uuid} pattern
            assert not re.match(r"workspace_[0-9a-f-]+\.", result.suggested_filename), (
                f"Filename still uses old workspace_{{uuid}} pattern: "
                f"{result.suggested_filename!r}"
            )
        finally:
            page.goto("about:blank")
            page.close()
            context.close()

    def test_slow_lane_exact_pdf_filename(
        self,
        browser: Browser,
        app_server: str,
    ) -> None:
        """Slow lane: exact .pdf filename suggested by the browser.

        AC5.3: exact filename assertion at the browser boundary.

        Requires real LaTeX compilation. Skip if E2E_SKIP_LATEXMK=1
        (the default for ``uv run grimoire e2e run``).
        """
        if os.environ.get("E2E_SKIP_LATEXMK", "1") != "0":
            pytest.skip(
                "run via `uv run grimoire e2e slow` for exact .pdf suggested filename"
            )

        context = browser.new_context()
        page = context.new_page()

        try:
            email = _authenticate_page(page, app_server)
            workspace_id = _create_workspace_for_filename_export(email)

            page.goto(f"{app_server}/annotation?workspace_id={workspace_id}")
            wait_for_text_walker(page, timeout=15000)

            result = export_annotation_tex_text(page)
            stem = _expected_stem()

            assert result.is_pdf is True, (
                f"Expected compiled PDF in slow lane, got .tex "
                f"(suggested: {result.suggested_filename!r})"
            )
            assert result.suggested_filename == f"{stem}.pdf", (
                f"Expected '{stem}.pdf', got: {result.suggested_filename!r}"
            )
        finally:
            page.goto("about:blank")
            page.close()
            context.close()

    def test_cross_tab_filename_consistency(
        self,
        browser: Browser,
        app_server: str,
    ) -> None:
        """Annotate and Respond tabs yield the same suggested filename.

        AC4.3: export filename is consistent across tabs for the same
        workspace on the same date.
        """
        context = browser.new_context()
        page = context.new_page()

        try:
            email = _authenticate_page(page, app_server)
            workspace_id = _create_workspace_for_filename_export(email)

            page.goto(f"{app_server}/annotation?workspace_id={workspace_id}")
            wait_for_text_walker(page, timeout=15000)

            # Export from Annotate tab (default)
            result_annotate = export_annotation_tex_text(page)

            # Switch to Respond tab and export again
            page.get_by_test_id("tab-respond").click()
            # Wait for respond tab to load
            page.locator("[data-testid='milkdown-editor-container']").wait_for(
                state="visible", timeout=10000
            )

            result_respond = export_annotation_tex_text(page)

            assert (
                result_annotate.suggested_filename == result_respond.suggested_filename
            ), (
                f"Annotate tab suggested {result_annotate.suggested_filename!r} "
                f"but Respond tab suggested {result_respond.suggested_filename!r}"
            )

            # Also verify it's descriptive (not workspace_{uuid})
            assert not re.match(
                r"workspace_[0-9a-f-]+\.", result_annotate.suggested_filename
            ), (
                f"Filename still uses old workspace_{{uuid}} pattern: "
                f"{result_annotate.suggested_filename!r}"
            )
        finally:
            page.goto("about:blank")
            page.close()
            context.close()
