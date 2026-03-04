"""E2E tests for the annotation canvas: student and instructor interactions.

Exercises DOM-heavy interactions on a pre-seeded workspace, bypassing all
UI-based setup. Tests the Custom Highlight API, keyboard shortcuts, and
tag management dialog from both student and instructor perspectives.

Acceptance Criteria:
- e2e-instructor-workflow-split.AC4.1: Navigate to pre-seeded workspace, apply tag
- e2e-instructor-workflow-split.AC4.2: Locked tag shows lock icon, readonly input
- e2e-instructor-workflow-split.AC4.3: Keyboard shortcuts apply correct tag

Traceability:
- Design: docs/implementation-plans/2026-03-04-e2e-instructor-workflow-split/phase_03.md
"""

from __future__ import annotations

import os
import uuid
from typing import TYPE_CHECKING

from playwright.sync_api import expect

from tests.e2e.annotation_helpers import (
    _create_workspace_via_db,
    seed_tag_id,
    select_chars,
    wait_for_text_walker,
)

if TYPE_CHECKING:
    from playwright.sync_api import Page


def _lock_tag_in_db(workspace_id: str, tag_name: str) -> None:
    """Lock a seeded tag via direct SQL update.

    Uses the deterministic UUID from ``seed_tag_id`` to set
    ``locked = true`` on the tag row.

    Args:
        workspace_id: UUID string of the workspace.
        tag_name: Name of the seeded tag to lock.
    """
    from sqlalchemy import create_engine, text

    db_url = os.environ.get("DATABASE__URL", "")
    if not db_url:
        return
    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
    engine = create_engine(sync_url)

    ws_ns = uuid.UUID(workspace_id)
    tag_id = str(uuid.uuid5(ws_ns, f"seed-tag-{tag_name}"))

    with engine.begin() as conn:
        conn.execute(
            text("UPDATE tag SET locked = true WHERE id = CAST(:id AS uuid)"),
            {"id": tag_id},
        )
    engine.dispose()


def _parse_tag_name_from_button(btn_text: str) -> str:
    """Extract the tag name from a toolbar button label.

    Toolbar buttons have labels like "[2] Procedural History".
    Strips the leading "[N] " shortcut prefix if present.

    Args:
        btn_text: text_content() of the toolbar button element.

    Returns:
        Tag name with shortcut prefix removed.
    """
    stripped = btn_text.strip()
    if "] " in stripped:
        return stripped.split("] ", 1)[1].strip()
    return stripped


class TestAnnotationCanvas:
    """Canvas-level E2E tests using pre-seeded workspaces."""

    def test_student_canvas_interactions(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """AC4.1-AC4.3: Student applies tags and verifies locked tag behaviour.

        Steps:
        1. Create workspace via DB with seeded tags
        2. Lock the "Jurisdiction" tag via DB
        3. Navigate to annotation page
        4. Verify locked tag shows lock icon and readonly input
        5. Verify keyboard shortcuts apply correct tags
        """
        page = authenticated_page

        # Create a workspace owned by a known email. Re-authenticate
        # the page with this email so DB lookup succeeds.
        page_email = f"e2e-canvas-student-{uuid.uuid4().hex[:8]}@test.example.edu.au"

        # Re-authenticate the existing page with our known email
        page.goto(f"{app_server}/auth/callback?token=mock-token-{page_email}")
        page.wait_for_url(lambda url: "/auth/callback" not in url, timeout=10000)

        # Step 1: Create workspace via DB with seeded tags
        workspace_id = _create_workspace_via_db(
            user_email=page_email,
            html_content=(
                "<p>The plaintiff alleged that the defendant breached "
                "their duty of care in the workplace setting.</p>"
            ),
            seed_tags=True,
        )

        # Step 2: Lock the "Jurisdiction" tag
        _lock_tag_in_db(workspace_id, "Jurisdiction")

        # Step 3: Navigate to annotation page
        page.goto(f"{app_server}/annotation?workspace_id={workspace_id}")
        wait_for_text_walker(page, timeout=15000)

        toolbar = page.locator("[data-testid='tag-toolbar']")
        expect(toolbar).to_be_visible(timeout=5000)

        # ------------------------------------------------------------------
        # AC4.2: Verify locked "Jurisdiction" tag in Tag Management dialog
        # ------------------------------------------------------------------
        toolbar.locator("button").filter(
            has=page.locator("i.q-icon", has_text="settings")
        ).click()
        dialog = page.locator("[data-testid='tag-management-dialog']")
        expect(dialog).to_be_visible(timeout=5000)

        jurisdiction_id = seed_tag_id(workspace_id, "Jurisdiction")

        # Lock icon should be visible (student view renders ui.icon("lock")
        # directly with the data-testid on the <i> element itself)
        lock_icon = dialog.locator(f"[data-testid='tag-lock-icon-{jurisdiction_id}']")
        expect(lock_icon).to_be_visible(timeout=3000)

        # Name input should be readonly
        name_input = dialog.locator(f"[data-testid='tag-name-input-{jurisdiction_id}']")
        expect(name_input).to_have_attribute("readonly", "")

        # Close the dialog
        dialog.locator("[data-testid='tag-management-done-btn']").click()
        expect(dialog).to_be_hidden(timeout=5000)

        # ------------------------------------------------------------------
        # AC4.1 + AC4.3: Keyboard shortcuts apply correct tag
        # ------------------------------------------------------------------

        # Read the tag name at shortcut position "2" (2nd button, 0-indexed=1)
        key2_btn = toolbar.locator("[data-tag-id]").nth(1)
        key2_btn.wait_for(state="visible", timeout=5000)
        key2_raw = key2_btn.text_content() or ""
        key2_tag_name = _parse_tag_name_from_button(key2_raw)

        # Read the tag name at shortcut position "3" (3rd button, 0-indexed=2)
        key3_btn = toolbar.locator("[data-tag-id]").nth(2)
        key3_btn.wait_for(state="visible", timeout=5000)
        key3_raw = key3_btn.text_content() or ""
        key3_tag_name = _parse_tag_name_from_button(key3_raw)

        # Press "2" with text selected -- highlight created with tag at position 2
        select_chars(page, 0, 5)
        page.keyboard.press("2")
        page.wait_for_timeout(500)

        first_card = page.locator("[data-testid='annotation-card']").first
        expect(first_card).to_be_visible(timeout=5000)

        first_card_select = first_card.get_by_test_id("tag-select")
        expect(first_card_select).to_contain_text(key2_tag_name, timeout=3000)

        # Press "3" with text selected -- highlight created with tag at position 3
        select_chars(page, 10, 20)
        page.keyboard.press("3")
        page.wait_for_timeout(500)

        cards = page.locator("[data-testid='annotation-card']")
        expect(cards).to_have_count(2, timeout=3000)

        second_card = cards.nth(1)
        second_card_select = second_card.get_by_test_id("tag-select")
        expect(second_card_select).to_contain_text(key3_tag_name, timeout=3000)
