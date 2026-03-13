"""Fixture loading helpers for annotation E2E tests.

Provides functions to load HTML fixtures into workspaces via
UI interactions (paste, form submission).
"""

from __future__ import annotations

import gzip
import re
from typing import TYPE_CHECKING

from playwright.sync_api import expect

from promptgrimoire.docs.helpers import wait_for_text_walker
from tests.e2e.paste_helpers import simulate_paste
from tests.e2e.tag_helpers import _seed_tags_for_workspace

if TYPE_CHECKING:
    from pathlib import Path

    from playwright.sync_api import Page


def setup_workspace_with_content(
    page: Page,
    app_server: str,
    content: str,
    *,
    timeout: int = 15000,
    seed_tags: bool = True,
) -> None:
    """Navigate to annotation page, create workspace, and add content.

    Common setup pattern shared by all annotation tests:
    1. Navigate to /annotation
    2. Click create workspace
    3. Wait for workspace URL
    4. Fill content
    5. Submit and wait for text walker initialisation
    6. Optionally seed Legal Case Brief tags

    Args:
        page: Playwright page (can be from any browser context).
        app_server: Base URL of the app server.
        content: Text content to add as document.
        timeout: Max wait for text walker init (ms).
        seed_tags: If True (default), seed Legal Case Brief
            tags into the workspace after content is loaded.

    Traceability:
        Extracted from repetitive setup code across 15+ test classes.
    """
    page.goto(f"{app_server}/annotation")
    page.get_by_test_id("create-workspace-btn").click()
    page.wait_for_url(re.compile(r"workspace_id="))

    content_input = page.get_by_test_id("content-editor").locator(".q-editor__content")
    content_input.fill(content)
    page.get_by_test_id("add-document-btn").click()

    # Confirm the content type dialog
    confirm_btn = page.get_by_test_id("confirm-content-type-btn")
    confirm_btn.wait_for(state="visible", timeout=5000)
    confirm_btn.click()

    # Wait for the text walker to initialise
    wait_for_text_walker(page, timeout=timeout)

    if seed_tags:
        workspace_id = page.url.split("workspace_id=")[1].split("&")[0]
        _seed_tags_for_workspace(workspace_id)
        page.reload()
        wait_for_text_walker(page, timeout=timeout)


# Alias kept for callers that imported the _highlight_api variant.
# Both functions are now identical (char spans are gone).
setup_workspace_with_content_highlight_api = setup_workspace_with_content


def _load_fixture_via_paste(
    page: Page,
    app_server: str,
    fixture_path: Path,
    *,
    seed_tags: bool = True,
) -> None:
    """Load an HTML fixture into a new workspace via clipboard paste.

    Expects an already-authenticated page. Creates a new workspace, loads
    the HTML fixture via clipboard paste (simulating real user interaction),
    handles content type confirmation, and waits for text walker readiness.

    Args:
        page: Playwright page (must be already authenticated).
        app_server: Base URL of the app server.
        fixture_path: Path to HTML fixture (.html or .html.gz).
        seed_tags: If True (default), seed Legal Case Brief
            tags into the workspace after content is loaded.

    Note:
        Uses synthetic paste events (``paste_helpers.simulate_paste``) so
        no clipboard permissions are needed.  Works on both Chromium and
        Firefox.

    Traceability:
        Part of E2E test migration (#156) to unify fixture loading patterns
        and reduce test code duplication.
    """
    # Navigate and create workspace
    page.goto(f"{app_server}/annotation")
    page.get_by_test_id("create-workspace-btn").click()
    page.wait_for_url(re.compile(r"workspace_id="))

    # Read fixture HTML (handle both .html.gz and plain .html)
    if fixture_path.suffix == ".gz":
        with gzip.open(fixture_path, "rt", encoding="utf-8") as f:
            html_content = f.read()
    else:
        html_content = fixture_path.read_text(encoding="utf-8")

    # Focus the editor and dispatch synthetic paste event
    editor = page.get_by_test_id("content-editor").locator(".q-editor__content")
    expect(editor).to_be_visible()
    editor.click()

    simulate_paste(page, html_content)

    # Wait for "Content pasted" confirmation
    expect(editor).to_contain_text("Content pasted", timeout=5000)

    # Click "Add Document" button. For pasted HTML, the content type dialog
    # is skipped (content_form.py auto-detects paste as HTML). The app
    # processes the input and navigates back to the annotation page.
    page.get_by_test_id("add-document-btn").click()

    # Wait for text walker readiness (large fixtures like AustLII need time).
    wait_for_text_walker(page, timeout=30000)

    if seed_tags:
        workspace_id = page.url.split("workspace_id=")[1].split("&")[0]
        _seed_tags_for_workspace(workspace_id)
        page.reload()
        wait_for_text_walker(page, timeout=30000)

        # After seeding tags via SQL and reloading, wait for the tag
        # toolbar to render with at least one button before returning.
        toolbar = page.locator("[data-testid='tag-toolbar']")
        expect(toolbar).to_be_visible(timeout=10000)
        expect(toolbar.locator("button").first).to_be_visible(timeout=10000)
