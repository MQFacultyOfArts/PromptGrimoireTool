"""E2E regressions for ChatCraft fixture ingest."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from playwright.sync_api import expect

from tests.conftest import load_conversation_fixture
from tests.e2e.annotation_helpers import wait_for_text_walker
from tests.e2e.conftest import _authenticate_page

if TYPE_CHECKING:
    from playwright.sync_api import Browser, Page


def _create_empty_workspace_via_db(user_email: str) -> str:
    """Create an empty workspace for paste-path testing."""
    from sqlalchemy import create_engine, text

    db_url = os.environ.get("DATABASE__URL", "")
    if not db_url:
        msg = "DATABASE__URL not configured"
        raise RuntimeError(msg)

    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
    engine = create_engine(sync_url)
    workspace_id = str(uuid4())

    with engine.begin() as conn:
        row = conn.execute(
            text('SELECT id FROM "user" WHERE email = :email'),
            {"email": user_email},
        ).first()
        if not row:
            msg = f"User not found in DB: {user_email}"
            raise RuntimeError(msg)

        conn.execute(
            text(
                "INSERT INTO workspace"
                " (id, enable_save_as_draft, created_at, updated_at)"
                " VALUES (CAST(:id AS uuid), false, now(), now())"
            ),
            {"id": workspace_id},
        )
        conn.execute(
            text(
                "INSERT INTO acl_entry"
                " (id, workspace_id, user_id, permission, created_at)"
                " VALUES (gen_random_uuid(),"
                " CAST(:ws AS uuid), :uid, 'owner', now())"
            ),
            {"ws": workspace_id, "uid": row[0]},
        )

    engine.dispose()
    return workspace_id


def _simulate_html_paste(page: Page, html_content: str) -> None:
    """Paste HTML into the content editor using the browser clipboard."""
    editor = page.get_by_test_id("content-editor").locator(".q-editor__content")
    expect(editor).to_be_visible(timeout=5000)
    editor.click()

    page.evaluate(
        """(html) => {
            const plainText = html.replace(/<[^>]*>/g, '');
            return navigator.clipboard.write([
                new ClipboardItem({
                    'text/html': new Blob([html], { type: 'text/html' }),
                    'text/plain': new Blob([plainText], { type: 'text/plain' })
                })
            ]);
        }""",
        html_content,
    )

    page.keyboard.press("Control+v")
    expect(editor).to_contain_text("Content pasted", timeout=5000)


@pytest.mark.e2e
class TestChatCraftIngest232:
    """Regression coverage for issue 232's ChatCraft fixture."""

    def test_chatcraft_paste_preserves_all_turns_and_roles(
        self,
        browser: Browser,
        app_server: str,
    ) -> None:
        """Clipboard paste keeps all ChatCraft turns and role labels intact."""
        context = browser.new_context(permissions=["clipboard-read", "clipboard-write"])
        page = context.new_page()

        try:
            user_email = _authenticate_page(page, app_server)
            workspace_id = _create_empty_workspace_via_db(user_email)
            page.goto(f"{app_server}/annotation?workspace_id={workspace_id}")

            _simulate_html_paste(
                page, load_conversation_fixture("chatcraft_sonnet-232")
            )
            page.get_by_test_id("add-document-btn").click()
            wait_for_text_walker(page, timeout=30000)

            doc = page.locator("#doc-container")
            expect(doc).to_contain_text("Hi Sonnet. Trying to repro a bug report.")
            expect(doc.locator("[data-speaker]")).to_have_count(10)
            expect(doc.locator('[data-speaker="system"]')).to_have_count(1)
            expect(doc.locator('[data-speaker="user"]')).to_have_count(4)
            expect(doc.locator('[data-speaker="assistant"]')).to_have_count(5)
            expect(doc).not_to_contain_text("<ChatCraft />")
            expect(doc).not_to_contain_text("Activity Denubis")
        finally:
            page.goto("about:blank")
            page.close()
            context.close()

    def test_chatcraft_paste_preserves_nested_blockquotes_and_code_blocks(
        self,
        browser: Browser,
        app_server: str,
    ) -> None:
        """The surviving final assistant card retains its nested rich content."""
        context = browser.new_context(permissions=["clipboard-read", "clipboard-write"])
        page = context.new_page()

        try:
            user_email = _authenticate_page(page, app_server)
            workspace_id = _create_empty_workspace_via_db(user_email)
            page.goto(f"{app_server}/annotation?workspace_id={workspace_id}")

            _simulate_html_paste(
                page, load_conversation_fixture("chatcraft_sonnet-232")
            )
            page.get_by_test_id("add-document-btn").click()
            wait_for_text_walker(page, timeout=30000)

            final_assistant = page.locator(
                '#doc-container [data-speaker="assistant"]'
            ).last
            expect(final_assistant).to_contain_text("The above summary is nested:")
            expect(final_assistant.locator("blockquote")).to_have_count(2)
            expect(final_assistant.locator("blockquote blockquote")).to_have_count(1)
            expect(final_assistant.locator("pre")).to_have_count(2)
            expect(final_assistant).to_contain_text("def dedupe_speaker_markers")
            expect(final_assistant).to_contain_text("dedupeSpeakerMarkers")
        finally:
            page.goto("about:blank")
            page.close()
            context.close()
