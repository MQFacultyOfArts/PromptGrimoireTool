"""Shared helper functions for annotation E2E tests.

These helpers extract common patterns used across annotation test files,
reducing duplication and ensuring consistent test setup.

Traceability:
- Epic: #92 (Annotation Workspace Platform)
- Issue: #93 (Seam A: Workspace Model)
- Design: docs/design-plans/2026-01-30-workspace-model.md
- Test consolidation: docs/design-plans/2026-01-31-test-suite-consolidation.md
"""

from __future__ import annotations

import gzip
import os
import re
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from playwright.sync_api import expect

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page

# Legal Case Brief tag seed data
# (mirrors cli.py:_seed_tags_for_activity).
_SEED_GROUP_DEFS: list[tuple[str, str, list[tuple[str, str]]]] = [
    (
        "Case ID",
        "#4a90d9",
        [
            ("Jurisdiction", "#1f77b4"),
            ("Procedural History", "#ff7f0e"),
            ("Decision", "#e377c2"),
            ("Order", "#7f7f7f"),
        ],
    ),
    (
        "Analysis",
        "#d9534f",
        [
            ("Legally Relevant Facts", "#2ca02c"),
            ("Legal Issues", "#d62728"),
            ("Reasons", "#9467bd"),
            ("Court's Reasoning", "#8c564b"),
        ],
    ),
    (
        "Sources",
        "#5cb85c",
        [
            ("Domestic Sources", "#bcbd22"),
            ("Reflection", "#17becf"),
        ],
    ),
]


def seed_tag_id(workspace_id: str, tag_name: str) -> str:
    """Compute the deterministic UUID for a seeded tag.

    Uses the same uuid5 derivation as ``_seed_tags_for_workspace()``,
    so the returned ID matches the ``id`` column in the ``tag`` table
    after seeding.  Useful for constructing ``data-testid`` selectors
    in Playwright tests (e.g. ``f"tag-name-input-{seed_tag_id(ws, 'Jurisdiction')}"``)
    """
    ws_ns = uuid.UUID(workspace_id)
    return str(uuid.uuid5(ws_ns, f"seed-tag-{tag_name}"))


def seed_group_id(workspace_id: str, group_name: str) -> str:
    """Compute the deterministic UUID for a seeded tag group.

    Uses the same uuid5 derivation as ``_seed_tags_for_workspace()``.
    """
    ws_ns = uuid.UUID(workspace_id)
    return str(uuid.uuid5(ws_ns, f"seed-group-{group_name}"))


def _seed_tags_for_workspace(workspace_id: str) -> None:
    """Seed Legal Case Brief tags into a workspace via sync DB connection.

    Inserts 3 tag groups and 10 tags using raw SQL with
    ``ON CONFLICT (id) DO NOTHING`` so the operation is idempotent.

    Deterministic UUIDs are derived from the workspace_id using uuid5
    so re-seeding the same workspace always produces the same rows.

    Follows the sync DB pattern of ``_grant_workspace_access()`` in
    ``conftest.py``.

    Args:
        workspace_id: UUID string of the target workspace.
    """
    from sqlalchemy import create_engine, text

    db_url = os.environ.get("DATABASE__URL", "")
    if not db_url:
        return
    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
    engine = create_engine(sync_url)

    ws_ns = uuid.UUID(workspace_id)

    with engine.begin() as conn:
        for group_idx, (group_name, group_color, tags) in enumerate(_SEED_GROUP_DEFS):
            group_id = uuid.uuid5(ws_ns, f"seed-group-{group_name}")
            conn.execute(
                text(
                    "INSERT INTO tag_group"
                    " (id, workspace_id, name,"
                    " color, order_index, created_at)"
                    " VALUES (:id, CAST(:ws AS uuid),"
                    " :name, :color, :order_index, now())"
                    " ON CONFLICT (id) DO NOTHING"
                ),
                {
                    "id": str(group_id),
                    "ws": workspace_id,
                    "name": group_name,
                    "color": group_color,
                    "order_index": group_idx,
                },
            )

            for tag_idx, (tag_name, tag_color) in enumerate(tags):
                tag_id = uuid.uuid5(ws_ns, f"seed-tag-{tag_name}")
                conn.execute(
                    text(
                        "INSERT INTO tag"
                        " (id, workspace_id, group_id,"
                        " name, color, locked,"
                        " order_index, created_at)"
                        " VALUES"
                        " (:id, CAST(:ws AS uuid),"
                        " CAST(:gid AS uuid),"
                        " :name, :color, :locked,"
                        " :order_index, now())"
                        " ON CONFLICT (id) DO NOTHING"
                    ),
                    {
                        "id": str(tag_id),
                        "ws": workspace_id,
                        "gid": str(group_id),
                        "name": tag_name,
                        "color": tag_color,
                        "locked": False,
                        "order_index": tag_idx,
                    },
                )

        # Update atomic counters so the next create_tag()/create_tag_group()
        # claims the correct order_index (not 0, which would collide).
        total_tags = sum(len(tags) for _, _, tags in _SEED_GROUP_DEFS)
        total_groups = len(_SEED_GROUP_DEFS)
        conn.execute(
            text(
                "UPDATE workspace"
                " SET next_tag_order = :tag_count,"
                "     next_group_order = :group_count"
                " WHERE id = CAST(:ws AS uuid)"
            ),
            {
                "tag_count": total_tags,
                "group_count": total_groups,
                "ws": workspace_id,
            },
        )

    engine.dispose()


def _create_workspace_via_db(
    user_email: str,
    html_content: str,
    *,
    source_type: str = "text",
    seed_tags: bool = True,
) -> str:
    """Create a workspace with content via direct DB operations.

    Creates workspace, document, and ACL entry in a single transaction,
    then optionally seeds Legal Case Brief tags.

    This bypasses the UI and input pipeline, so the caller must provide
    pre-processed HTML content (e.g. ``<p>My text here</p>``).

    Use this for tests that need a workspace but are NOT testing workspace
    creation itself.  Tests that test the creation flow (e.g. instructor
    workflow) should continue using ``setup_workspace_with_content()``.

    Args:
        user_email: Email of the authenticated user (must exist in DB).
        html_content: Pre-processed HTML content for the document.
        source_type: Content type (``"text"``, ``"html"``, etc.).
        seed_tags: If True (default), seed Legal Case Brief tags.

    Returns:
        workspace_id as string.

    Raises:
        RuntimeError: If DATABASE__URL is not configured or user not found.
    """
    from sqlalchemy import create_engine, text

    db_url = os.environ.get("DATABASE__URL", "")
    if not db_url:
        msg = "DATABASE__URL not configured"
        raise RuntimeError(msg)
    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
    engine = create_engine(sync_url)

    workspace_id = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())

    with engine.begin() as conn:
        # Look up user
        row = conn.execute(
            text('SELECT id FROM "user" WHERE email = :email'),
            {"email": user_email},
        ).first()
        if not row:
            msg = f"User not found in DB: {user_email}"
            raise RuntimeError(msg)
        user_id = row[0]

        # Create workspace
        conn.execute(
            text(
                "INSERT INTO workspace"
                " (id, enable_save_as_draft, created_at, updated_at)"
                " VALUES (CAST(:id AS uuid), false, now(), now())"
            ),
            {"id": workspace_id},
        )

        # Create workspace document
        conn.execute(
            text(
                "INSERT INTO workspace_document"
                " (id, workspace_id, type, content,"
                "  source_type, order_index, created_at)"
                " VALUES (CAST(:id AS uuid), CAST(:ws AS uuid),"
                " :type, :content, :source_type, 0, now())"
            ),
            {
                "id": doc_id,
                "ws": workspace_id,
                "type": "source",
                "content": html_content,
                "source_type": source_type,
            },
        )

        # Create ACL entry (owner permission)
        conn.execute(
            text(
                "INSERT INTO acl_entry"
                " (id, workspace_id, user_id, permission, created_at)"
                " VALUES (gen_random_uuid(),"
                " CAST(:ws AS uuid), :uid, 'owner', now())"
            ),
            {"ws": workspace_id, "uid": user_id},
        )

    engine.dispose()

    if seed_tags:
        _seed_tags_for_workspace(workspace_id)

    return workspace_id


def get_user_id_by_email(email: str) -> str:
    """Return a user's UUID (as string) from their email.

    Uses a direct sync DB query so sync Playwright tests can resolve
    deterministic anonymised labels for assertions.

    Args:
        email: User email address.

    Returns:
        User UUID as a string.

    Raises:
        RuntimeError: If DATABASE__URL is missing or user is not found.
    """
    from sqlalchemy import create_engine, text

    db_url = os.environ.get("DATABASE__URL", "")
    if not db_url:
        msg = "DATABASE__URL not configured"
        raise RuntimeError(msg)
    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
    engine = create_engine(sync_url)

    with engine.begin() as conn:
        row = conn.execute(
            text('SELECT id FROM "user" WHERE email = :email'),
            {"email": email.lower()},
        ).first()
    engine.dispose()

    if not row:
        msg = f"User not found in DB: {email}"
        raise RuntimeError(msg)
    return str(row[0])


def navigate_home_via_drawer(page: Page) -> None:
    """Navigate to ``/`` using the shared ``page_layout`` nav drawer.

    Opens the drawer via the header menu button if it isn't already
    visible, then clicks the "Home" nav item.  Pages that use
    ``page_layout()`` get this drawer automatically.

    Args:
        page: Playwright page with ``page_layout`` rendered.
    """
    home_link = page.locator(".q-item").filter(has_text="Home")
    if not home_link.first.is_visible():
        page.locator(".q-header .q-btn").first.click()
        page.wait_for_timeout(500)
    expect(home_link.first).to_be_visible(timeout=5000)
    home_link.first.click()


def scroll_to_char(page: Page, char_offset: int) -> None:
    """Scroll the document so that the given character offset is visible.

    Uses ``scrollToCharOffset()`` from annotation-highlight.js.
    After scrolling, waits briefly for card positioning to update
    (cards are hidden when their highlight is off-screen).

    Args:
        page: Playwright page.
        char_offset: Character index to scroll into view.
    """
    wait_for_text_walker(page, timeout=10000)
    page.evaluate(
        """(charIdx) => {
            const c = document.getElementById('doc-container');
            if (!c) return;
            const nodes = walkTextNodes(c);
            scrollToCharOffset(nodes, charIdx, charIdx);
        }""",
        char_offset,
    )
    page.wait_for_timeout(500)


def select_chars(page: Page, start_char: int, end_char: int) -> None:
    """Select a character range using mouse events.

    Uses the text walker (annotation-highlight.js) to convert char offsets
    to screen coordinates, then performs a mouse click-drag selection.

    Ensures the text walker is ready before attempting coordinate lookup,
    since tab switches can momentarily destroy and rebuild the DOM.

    Args:
        page: Playwright page.
        start_char: Index of first character to select.
        end_char: Index of last character to select (inclusive).
    """
    # Ensure text walker and doc-container are ready (tab switches can
    # rebuild the DOM after _textNodes was cached).
    wait_for_text_walker(page, timeout=10000)

    # Get bounding rectangles for start and end positions via text walker.
    # charOffsetToRect() handles StaticRange -> live Range conversion
    # internally (charOffsetToRange() returns StaticRange which does NOT
    # have getBoundingClientRect()).
    coords = page.evaluate(
        """([startChar, endChar]) => {
            const container = document.getElementById('doc-container');
            if (!container || typeof walkTextNodes === 'undefined') return null;
            const nodes = walkTextNodes(container);
            const startRect = charOffsetToRect(nodes, startChar);
            const endRect = charOffsetToRect(nodes, endChar);
            if (startRect.width === 0 && startRect.height === 0) return null;
            if (endRect.width === 0 && endRect.height === 0) return null;
            return {
                startX: startRect.left + 1,
                startY: startRect.top + startRect.height / 2,
                endX: endRect.right - 1,
                endY: endRect.top + endRect.height / 2
            };
        }""",
        [start_char, end_char],
    )
    if coords is None:
        msg = (
            "Could not get char coordinates"
            " -- text walker not loaded or offsets out of range"
        )
        raise RuntimeError(msg)

    # Scroll to the start position first so it is in viewport
    page.evaluate(
        """([startChar, endChar]) => {
            const container = document.getElementById('doc-container');
            const nodes = walkTextNodes(container);
            scrollToCharOffset(nodes, startChar, endChar);
        }""",
        [start_char, end_char],
    )
    page.wait_for_timeout(300)

    # Re-query coordinates after scroll (positions change)
    coords = page.evaluate(
        """([startChar, endChar]) => {
            const container = document.getElementById('doc-container');
            const nodes = walkTextNodes(container);
            const startRect = charOffsetToRect(nodes, startChar);
            const endRect = charOffsetToRect(nodes, endChar);
            return {
                startX: startRect.left + 1,
                startY: startRect.top + startRect.height / 2,
                endX: endRect.right - 1,
                endY: endRect.top + endRect.height / 2
            };
        }""",
        [start_char, end_char],
    )

    # Perform mouse-based selection (real user interaction)
    page.mouse.click(coords["startX"], coords["startY"])
    page.mouse.down()
    page.mouse.move(coords["endX"], coords["endY"])
    page.mouse.up()


def drag_sortable_item(source: Locator, target: Locator) -> None:
    """Drag a SortableJS item by its drag handle to the target.

    Uses Playwright's ``drag_to`` between the source's
    ``.drag-handle`` child and the *target* locator.

    Args:
        source: Locator for the draggable element
            (must contain ``.drag-handle``).
        target: Locator for the drop target element.
    """
    source_handle = source.locator(".drag-handle").first
    source_handle.drag_to(target)


def create_highlight(page: Page, start_char: int, end_char: int) -> None:
    """Select characters and click the first tag button to create a highlight.

    Args:
        page: Playwright page.
        start_char: Index of first character to select.
        end_char: Index of last character to select.
    """
    select_chars(page, start_char, end_char)
    tag_button = page.locator("[data-testid='tag-toolbar'] button").first
    tag_button.click()


def create_highlight_with_tag(
    page: Page, start_char: int, end_char: int, tag_index: int
) -> None:
    """Select characters and click a specific tag button to create a highlight.

    Args:
        page: Playwright page.
        start_char: Index of first character to select.
        end_char: Index of last character to select.
        tag_index: 0-based index of tag button to click
            (0=Jurisdiction, 1=Procedural History, etc).
    """
    select_chars(page, start_char, end_char)
    tag_button = page.locator("[data-testid='tag-toolbar'] button").nth(tag_index)
    tag_button.click()


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
    page.get_by_role("button", name=re.compile("create", re.IGNORECASE)).click()
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
    page.wait_for_timeout(200)

    if seed_tags:
        workspace_id = page.url.split("workspace_id=")[1].split("&")[0]
        _seed_tags_for_workspace(workspace_id)
        page.reload()
        wait_for_text_walker(page, timeout=timeout)


# Alias kept for callers that imported the _highlight_api variant.
# Both functions are now identical (char spans are gone).
setup_workspace_with_content_highlight_api = setup_workspace_with_content


def select_text_range(page: Page, text: str) -> None:
    """Select a text substring in the document container by evaluating JS.

    Uses the browser's native selection API to select the given text
    within ``#doc-container``. This approach works without char spans.

    Args:
        page: Playwright page.
        text: The text substring to select.
    """
    page.evaluate(
        """(text) => {
            const container = document.getElementById('doc-container');
            const walker = document.createTreeWalker(
                container, NodeFilter.SHOW_TEXT, null
            );
            let node;
            while ((node = walker.nextNode())) {
                const idx = node.textContent.indexOf(text);
                if (idx >= 0) {
                    const range = document.createRange();
                    range.setStart(node, idx);
                    range.setEnd(node, idx + text.length);
                    const sel = window.getSelection();
                    sel.removeAllRanges();
                    sel.addRange(range);
                    // Trigger mouseup to fire selection handler
                    container.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
                    return;
                }
            }
            throw new Error('Text not found: ' + text);
        }""",
        text,
    )
    page.wait_for_timeout(200)


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
        The browser context MUST have been created with clipboard permissions:
        ``permissions=["clipboard-read", "clipboard-write"]``
        This is the caller's responsibility.

    Traceability:
        Part of E2E test migration (#156) to unify fixture loading patterns
        and reduce test code duplication.
    """
    # Navigate and create workspace
    page.goto(f"{app_server}/annotation")
    page.get_by_role("button", name=re.compile("create", re.IGNORECASE)).click()
    page.wait_for_url(re.compile(r"workspace_id="))

    # Read fixture HTML (handle both .html.gz and plain .html)
    if fixture_path.suffix == ".gz":
        with gzip.open(fixture_path, "rt", encoding="utf-8") as f:
            html_content = f.read()
    else:
        html_content = fixture_path.read_text(encoding="utf-8")

    # Focus the editor
    editor = page.get_by_test_id("content-editor").locator(".q-editor__content")
    expect(editor).to_be_visible()
    editor.click()

    # Write HTML to clipboard (same pattern as test_html_paste_whitespace.py)
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
    page.wait_for_timeout(100)

    # Trigger paste
    page.keyboard.press("Control+v")
    page.wait_for_timeout(500)

    # Wait for "Content pasted" confirmation
    expect(editor).to_contain_text("Content pasted", timeout=5000)

    # Click "Add Document" button. For pasted HTML, the content type dialog
    # is skipped (content_form.py auto-detects paste as HTML). The app
    # processes the input and navigates back to the annotation page.
    page.get_by_role("button", name=re.compile("add document", re.IGNORECASE)).click()

    # Wait for text walker readiness (large fixtures like AustLII need time).
    wait_for_text_walker(page, timeout=30000)

    if seed_tags:
        workspace_id = page.url.split("workspace_id=")[1].split("&")[0]
        _seed_tags_for_workspace(workspace_id)
        page.reload()
        wait_for_text_walker(page, timeout=30000)


def wait_for_text_walker(page: Page, *, timeout: int = 15000) -> None:
    """Wait for the text walker to initialise (readiness gate).

    This is a synchronisation wait, not a test assertion. It ensures
    the text walker has built its node map before any interactions that
    depend on character offsets or highlight rendering.

    Args:
        page: Playwright page.
        timeout: Maximum wait time in milliseconds.
    """
    try:
        page.wait_for_function(
            "() => document.getElementById('doc-container')"
            " && window._textNodes && window._textNodes.length > 0",
            timeout=timeout,
        )
    except Exception as exc:
        if "Timeout" not in type(exc).__name__:
            raise
        # Capture diagnostic state for debugging
        url = page.url
        diag = page.evaluate(
            "() => {"
            " const d = document.getElementById('doc-container');"
            " return {"
            "   doc: d ? d.innerHTML.substring(0, 200) : 'NO #doc-container',"
            "   walkDefined: typeof walkTextNodes !== 'undefined',"
            "   textNodes: window._textNodes ? window._textNodes.length : null,"
            "   scripts: Array.from(document.querySelectorAll('script[src]'))"
            "     .map(s => s.src).filter(s => s.includes('annotation'))"
            " }; }"
        )
        msg = (
            f"Text walker timeout ({timeout}ms). URL: {url}"
            f" doc-container: {diag['doc']!r}"
            f" walkTextNodes defined: {diag['walkDefined']}"
            f" _textNodes: {diag['textNodes']}"
            f" annotation scripts: {diag['scripts']}"
        )
        raise type(exc)(msg) from None


# ---------------------------------------------------------------------------
# Comment helpers
# ---------------------------------------------------------------------------


def add_comment_to_highlight(page: Page, text: str, *, card_index: int = 0) -> None:
    """Add a comment to an annotation card via the Post button.

    Args:
        page: Playwright page with an annotation workspace loaded.
        text: Comment text to post.
        card_index: 0-based index of the annotation card.
    """
    card = page.locator("[data-testid='annotation-card']").nth(card_index)
    card.wait_for(state="visible", timeout=10000)

    comment_input = card.get_by_test_id("comment-input")
    comment_input.fill(text)
    card.get_by_role("button", name="Post").click()

    card.locator("[data-testid='comment']", has_text=text).wait_for(
        state="visible", timeout=10000
    )


def get_comment_authors(page: Page, *, card_index: int = 0) -> list[str]:
    """Get author names from comments on an annotation card.

    Args:
        page: Playwright page with an annotation workspace loaded.
        card_index: 0-based index of the annotation card.

    Returns:
        List of author display names in DOM order.
    """
    card = page.locator("[data-testid='annotation-card']").nth(card_index)
    card.wait_for(state="visible", timeout=10000)
    labels = card.locator("[data-testid='comment-author']")
    return [labels.nth(i).inner_text() for i in range(labels.count())]


def count_comment_delete_buttons(page: Page, *, card_index: int = 0) -> int:
    """Count visible delete buttons on an annotation card.

    Args:
        page: Playwright page with an annotation workspace loaded.
        card_index: 0-based index of the annotation card.

    Returns:
        Number of delete buttons visible.
    """
    card = page.locator("[data-testid='annotation-card']").nth(card_index)
    card.wait_for(state="visible", timeout=10000)
    return card.locator("[data-testid='comment-delete']").count()


# ---------------------------------------------------------------------------
# Sharing helpers
# ---------------------------------------------------------------------------


def toggle_share_with_class(page: Page) -> None:
    """Toggle the 'Share with class' switch on.

    Waits for the toggle to be visible and clicks it if not
    already enabled.  Expects the annotation workspace page.
    """
    toggle = page.locator('[data-testid="share-with-class-toggle"]')
    toggle.wait_for(state="visible", timeout=5000)
    if toggle.get_attribute("aria-checked") != "true":
        toggle.click()
    page.wait_for_timeout(500)


def clone_activity_workspace(
    page: Page,
    app_server: str,
    course_id: str,
    activity_title: str,
) -> str:
    """Navigate to course, clone activity workspace.

    Args:
        page: Authenticated Playwright page.
        app_server: Base URL of the test server.
        course_id: UUID string of the course.
        activity_title: Title of the activity to clone.

    Returns:
        workspace_id as string.
    """
    page.goto(f"{app_server}/courses/{course_id}")

    label = page.get_by_text(activity_title)
    label.wait_for(state="visible", timeout=10000)
    card = label.locator("xpath=ancestor::div[contains(@class, 'q-card')]")
    card.get_by_role("button", name="Start Activity").first.click()

    page.wait_for_url(
        re.compile(r"/annotation\?workspace_id="),
        timeout=15000,
    )
    wait_for_text_walker(page, timeout=15000)

    return page.url.split("workspace_id=")[1].split("&")[0]


# ---------------------------------------------------------------------------
# PDF export
# ---------------------------------------------------------------------------


def export_pdf_text(page: Page) -> str:
    """Click Export PDF, download, extract text via pymupdf.

    Args:
        page: Playwright page with annotation workspace loaded.

    Returns:
        Extracted text from the PDF with soft-hyphen breaks removed.

    Raises:
        pytest.skip: If export times out (TinyTeX not installed).
    """
    import pytest
    from playwright.sync_api import (
        TimeoutError as PlaywrightTimeoutError,
    )

    try:
        with page.expect_download(timeout=120000) as dl:
            page.get_by_role("button", name="Export PDF").click()

        download = dl.value
        pdf_path = download.path()
        pdf_bytes = Path(pdf_path).read_bytes()
        assert len(pdf_bytes) > 5_000, f"PDF too small: {len(pdf_bytes)} bytes"

        import pymupdf

        doc = pymupdf.open(pdf_path)
        pdf_text = "".join(p.get_text() for p in doc)
        doc.close()

        return re.sub(r"-\n", "", pdf_text)
    except PlaywrightTimeoutError:
        pytest.skip("PDF export timed out (TinyTeX not installed?)")


def export_annotation_tex_text(page: Page) -> str:
    """Click Export PDF and return the downloaded TeX source.

    The E2E server monkey-patches ``compile_latex`` to a no-op, so clicking
    Export PDF produces a ``.tex`` file instead of a ``.pdf``.  This exercises
    the **exact same data-gathering path** as the real export (PageState with
    live CRDT), avoiding stale-data bugs from separate API endpoints.

    Args:
        page: Playwright page with an annotation workspace loaded.

    Returns:
        Generated LaTeX source as text.
    """
    with page.expect_download(timeout=60000) as dl:
        page.get_by_role("button", name="Export PDF").click()

    download = dl.value
    tex_path = download.path()
    return Path(tex_path).read_text(encoding="utf-8")
