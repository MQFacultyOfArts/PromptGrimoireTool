"""E2E tests for the workspace navigator page.

Verifies the navigator page at ``/`` renders workspace sections correctly,
handles authentication, provides workspace navigation, supports search,
supports inline title rename, and supports infinite scroll pagination.

Acceptance Criteria:
- workspace-navigator-196.AC2.5: Unauthenticated redirect to login
- workspace-navigator-196.AC1.1: My Work section renders with workspace entries
- workspace-navigator-196.AC1.2: Unstarted Work section visible with activity entries
- workspace-navigator-196.AC1.7: Empty sections not rendered in DOM
- workspace-navigator-196.AC2.1: Title click navigates to annotation page
- workspace-navigator-196.AC2.3: Start button clones and navigates
- workspace-navigator-196.AC3.2: FTS fires at >=3 chars with snippet
- workspace-navigator-196.AC3.5: Clearing search restores full unfiltered list
- workspace-navigator-196.AC3.6: No results shows message with clear option
- workspace-navigator-196.AC8.4: Short queries (<3 chars) do not trigger FTS
- workspace-navigator-196.AC4.1: Pencil icon activates inline title edit
- workspace-navigator-196.AC4.2: Enter or blur saves the new title
- workspace-navigator-196.AC4.3: Escape cancels edit without saving
- workspace-navigator-196.AC4.4: New workspaces default title to activity name
- workspace-navigator-196.AC4.5: Pencil click does not navigate
- workspace-navigator-196.AC5.1: Initial load shows first 50 rows
- workspace-navigator-196.AC5.2: Infinite scroll loads more rows into correct sections
- workspace-navigator-196.AC5.4: Fewer than 50 rows -- no additional loading
- workspace-navigator-196.AC5.5: Multi-page scroll without duplicates

Traceability:
- Issue: #196 (Workspace Navigator)
- Design: docs/implementation-plans/2026-02-24-workspace-navigator-196/phase_04.md
- Design: docs/implementation-plans/2026-02-24-workspace-navigator-196/phase_05.md
- Design: docs/implementation-plans/2026-02-24-workspace-navigator-196/phase_06.md
- Design: docs/implementation-plans/2026-02-24-workspace-navigator-196/phase_07.md
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from playwright.sync_api import expect

from tests.e2e.annotation_helpers import (
    _create_workspace_via_db,
    wait_for_text_walker,
)
from tests.e2e.conftest import _authenticate_page
from tests.e2e.course_helpers import (
    add_activity,
    add_week,
    configure_course_setting,
    create_course,
    enrol_student,
    publish_week,
)

if TYPE_CHECKING:
    from playwright.sync_api import Browser, Locator, Page
    from pytest_subtests import SubTests


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fill_template_workspace(page: Page) -> None:
    """Click Create Template, add content for cloning.

    Expects the page to be on a course detail page with an activity
    showing a "Create Template" button.
    """
    page.get_by_role(
        "button",
        name=re.compile(r"Create Template|Edit Template"),
    ).click()
    page.wait_for_url(re.compile(r"/annotation\?workspace_id="), timeout=10000)

    content_input = page.get_by_placeholder(
        "Paste HTML content or type plain text here..."
    )
    content_input.wait_for(state="visible", timeout=5000)
    content_input.fill("Navigator test content for template workspace.")

    page.get_by_role("button", name=re.compile(r"add document", re.IGNORECASE)).click()

    confirm = page.get_by_role("button", name=re.compile(r"confirm", re.IGNORECASE))
    confirm.wait_for(state="visible", timeout=5000)
    confirm.click()

    wait_for_text_walker(page, timeout=15000)


def _get_section_header_texts(page: Page) -> list[str]:
    """Read all navigator section header texts from the page."""
    section_headers = page.locator(".navigator-section-header")
    return [section_headers.nth(i).inner_text() for i in range(section_headers.count())]


def _assert_activity_not_in_unstarted(page: Page, activity_title: str) -> None:
    """Assert no Start-button card contains the given activity title."""
    start_btns = page.locator(".navigator-start-btn")
    for i in range(start_btns.count()):
        parent_card = start_btns.nth(i).locator(
            "xpath=ancestor::div[contains(@class, 'q-card')]"
        )
        card_text = parent_card.inner_text()
        assert activity_title not in card_text, (
            f"Activity '{activity_title}' should not be in "
            f"Unstarted after cloning. Card text: {card_text}"
        )


def _student_start_and_verify(
    browser: Browser,
    app_server: str,
    *,
    student_email: str,
    activity_title: str,
    subtests: SubTests,
) -> None:
    """Student clicks Start, verifies clone navigation, and section move.

    Extracted to keep test method under PLR0915 statement limit.
    """
    student_ctx = browser.new_context()
    student_page = student_ctx.new_page()

    try:
        _authenticate_page(student_page, app_server, email=student_email)

        with subtests.test(msg="unstarted_shows_activity"):
            student_page.goto(f"{app_server}/")
            student_page.wait_for_timeout(2000)

            header_texts = _get_section_header_texts(student_page)
            assert "Unstarted Work" in header_texts, (
                f"Expected 'Unstarted Work', got: {header_texts}"
            )

            activity_label = student_page.get_by_text(activity_title, exact=False)
            expect(activity_label.first).to_be_visible(timeout=5000)

        with subtests.test(msg="start_navigates_to_annotation"):
            start_btn = student_page.locator(".navigator-start-btn").first
            expect(start_btn).to_be_visible(timeout=5000)
            start_btn.click()

            student_page.wait_for_url(
                re.compile(r"/annotation\?workspace_id="),
                timeout=15000,
            )
            assert "/annotation" in student_page.url, (
                f"Expected /annotation URL, got: {student_page.url}"
            )

        with subtests.test(msg="activity_moves_to_my_work"):
            student_page.goto(f"{app_server}/")
            student_page.wait_for_timeout(2000)

            header_texts = _get_section_header_texts(student_page)
            assert "My Work" in header_texts, (
                f"Expected 'My Work' after cloning, got: {header_texts}"
            )

            action_btns = student_page.locator(".navigator-action-btn")
            expect(action_btns.first).to_be_visible(timeout=5000)

            _assert_activity_not_in_unstarted(student_page, activity_title)

    finally:
        student_page.goto("about:blank")
        student_page.close()
        student_ctx.close()


def _create_workspaces_bulk(
    user_email: str,
    count: int,
    *,
    content_prefix: str = "Bulk workspace content",
) -> list[str]:
    """Create multiple workspaces via a single DB transaction.

    Much faster than calling ``_create_workspace_via_db`` in a loop
    because it reuses a single engine and transaction.

    Returns a list of workspace_id strings.
    """
    import uuid

    from sqlalchemy import create_engine, text

    from promptgrimoire.config import get_settings

    db_url = str(get_settings().database.url)
    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
    engine = create_engine(sync_url)

    workspace_ids: list[str] = []

    with engine.begin() as conn:
        row = conn.execute(
            text('SELECT id FROM "user" WHERE email = :email'),
            {"email": user_email},
        ).first()
        if not row:
            msg = f"User not found in DB: {user_email}"
            raise RuntimeError(msg)
        user_id = row[0]

        for i in range(count):
            workspace_id = str(uuid.uuid4())
            doc_id = str(uuid.uuid4())
            workspace_ids.append(workspace_id)

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
                    "content": f"<p>{content_prefix} {i}</p>",
                    "source_type": "text",
                },
            )
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
    return workspace_ids


def _scroll_navigator_to_bottom(page: Page) -> None:
    """Scroll the navigator scroll area to the bottom.

    The navigator uses a plain ``overflow-y: auto`` div (not Quasar
    QScrollArea), so ``scrollTop`` can be set directly on the element.
    ``evaluate()`` is required because Playwright has no native API to
    set ``scrollTop`` on an arbitrary scrollable div.

    Explicitly dispatches a ``scroll`` event after setting ``scrollTop``
    to ensure NiceGUI's event listener picks up the change.
    """
    page.locator(".navigator-scroll-area").evaluate(
        "el => { el.scrollTop = el.scrollHeight;"
        " el.dispatchEvent(new Event('scroll')); }"
    )


def _scroll_navigator_to_top(page: Page) -> None:
    """Scroll the navigator scroll area to the top.

    Sets ``scrollTop`` to 0 and dispatches a scroll event so the
    NiceGUI event handler fires.
    """
    page.locator(".navigator-scroll-area").evaluate(
        "el => { el.scrollTop = 0; el.dispatchEvent(new Event('scroll')); }"
    )


def _count_workspace_entries(page: Page) -> int:
    """Count visible workspace entries on the navigator page.

    Counts elements with ``data-workspace-id`` attribute (workspace
    entries in My Work, Shared With Me, Shared in Unit sections).
    Does not count unstarted activity entries.
    """
    return page.locator("[data-workspace-id]").count()


def _clear_search_input(page: Page, search_input: Locator) -> None:
    """Clear the search input by selecting all text and deleting it."""
    search_input.click()
    page.keyboard.press("Control+a")
    page.keyboard.press("Backspace")


def _type_in_search(
    page: Page,
    search_input: Locator,
    text: str,
) -> None:
    """Type text into the search input using keyboard events.

    Uses click + select-all + delete + type to ensure Quasar's
    ``update:model-value`` Vue event fires correctly
    (Playwright's ``fill()`` may not trigger it).
    """
    _clear_search_input(page, search_input)
    page.keyboard.type(text, delay=30)


def _search_subtests(
    page: Page,
    app_server: str,
    *,
    subtests: SubTests,
    workspace_id_a: str,
    workspace_id_b: str,
    search_query_a: str,
    nonsense_query: str,
) -> None:
    """Run search sub-assertions to keep test method under PLR0915 limit.

    Extracted from ``test_search_filters_and_restores``.

    Parameters
    ----------
    search_query_a:
        Full search term that matches workspace A's content.
        Must be a complete word (PostgreSQL FTS uses stemming,
        not prefix matching).
    """
    # Navigate to navigator page and wait for render
    page.goto(f"{app_server}/")
    page.wait_for_timeout(2000)

    # Verify both workspaces are visible initially
    ws_a = page.locator(f'[data-workspace-id="{workspace_id_a}"]')
    ws_b = page.locator(f'[data-workspace-id="{workspace_id_b}"]')
    expect(ws_a).to_be_visible(timeout=5000)
    expect(ws_b).to_be_visible(timeout=5000)

    # Locate the search input (NiceGUI ui.input -> nested <input>)
    search_input = page.locator(".navigator-search-input input")
    expect(search_input).to_be_visible(timeout=5000)

    # --- AC8.4: Short query does NOT trigger FTS ---
    with subtests.test(msg="short_query_no_filter"):
        _type_in_search(page, search_input, "ab")
        # Wait longer than the debounce (500ms) + render time
        page.wait_for_timeout(1500)

        # Both workspaces should still be visible (no filtering)
        expect(ws_a).to_be_visible(timeout=3000)
        expect(ws_b).to_be_visible(timeout=3000)

        # No "no results" message should appear
        no_results = page.locator(".navigator-no-results")
        expect(no_results).to_have_count(0)

    # Clear search before next sub-test
    _clear_search_input(page, search_input)
    page.wait_for_timeout(1000)

    # --- AC3.2: FTS fires at 3+ chars, filters, shows snippet ---
    with subtests.test(msg="fts_filters_with_snippet"):
        _type_in_search(page, search_input, search_query_a)
        # Wait for debounce (500ms) + DB query + render
        page.wait_for_timeout(3000)

        # Workspace A should be visible (matches query)
        expect(ws_a).to_be_visible(timeout=5000)

        # Workspace B should NOT be visible (does not match)
        expect(ws_b).to_have_count(0, timeout=5000)

        # A snippet should be rendered with <mark> tags
        snippet = page.locator(".navigator-snippet")
        expect(snippet.first).to_be_visible(timeout=5000)

    # --- AC3.5: Clearing search restores full view ---
    with subtests.test(msg="clear_restores_full_view"):
        _clear_search_input(page, search_input)
        # Wait for restore
        page.wait_for_timeout(2000)

        # Both workspaces should be visible again
        expect(ws_a).to_be_visible(timeout=5000)
        expect(ws_b).to_be_visible(timeout=5000)

        # No snippets should be visible
        snippets = page.locator(".navigator-snippet")
        expect(snippets).to_have_count(0, timeout=3000)

    # --- AC3.6: No results shows message, Clear button restores ---
    with subtests.test(msg="no_results_shows_message"):
        _type_in_search(page, search_input, nonsense_query)
        # Wait for debounce + query + render
        page.wait_for_timeout(3000)

        # "No workspaces match" message should appear
        no_results = page.locator(".navigator-no-results")
        expect(no_results).to_be_visible(timeout=5000)

        # Neither workspace should be visible
        expect(ws_a).to_have_count(0, timeout=3000)
        expect(ws_b).to_have_count(0, timeout=3000)

    with subtests.test(msg="clear_button_restores"):
        # Click the "Clear search" button
        clear_btn = page.locator(".navigator-clear-search-btn")
        expect(clear_btn).to_be_visible(timeout=3000)
        clear_btn.click()

        # Wait for restore
        page.wait_for_timeout(2000)

        # Both workspaces should reappear
        expect(ws_a).to_be_visible(timeout=5000)
        expect(ws_b).to_be_visible(timeout=5000)

        # No results message should be gone
        no_results = page.locator(".navigator-no-results")
        expect(no_results).to_have_count(0, timeout=3000)


def _locate_title_elements(
    page: Page,
    workspace_id: str,
) -> tuple[Locator, Locator]:
    """Locate pencil icon and native title ``<input>`` for a workspace.

    NiceGUI ``.props('data-workspace-id="..."')`` on a ``ui.input`` places
    the attribute on the **native** ``<input>`` element inside Quasar's
    q-input component (not on the outer ``<label>`` root).

    Returns
    -------
    (pencil, native_input):
        pencil: The edit-title icon button.
        native_input: The native ``<input>`` element.  Call
            ``.input_value()`` / ``.fill()`` / ``.press()`` directly.
            To check Quasar field classes (``q-field--outlined``,
            ``q-field--borderless``), use ``_get_quasar_root()``.
    """
    pencil = page.locator(f'[data-testid="edit-title-{workspace_id}"]')
    native_input = page.locator(f'[data-workspace-id="{workspace_id}"]')
    return pencil, native_input


def _get_quasar_root(native_input: Locator) -> Locator:
    """Navigate from native ``<input>`` up to the Quasar q-input root.

    Quasar q-input renders as ``<label class="q-field ..."> ... <input>``.
    The root ``<label>`` carries Quasar state classes like
    ``q-field--outlined`` and ``q-field--borderless``.
    """
    return native_input.locator("xpath=ancestor::label[contains(@class, 'q-field')]")


def _rename_edit_subtests(
    page: Page,
    *,
    subtests: SubTests,
    workspace_id: str,
    pencil: Locator,
    native: Locator,
) -> str:
    """Run pencil-click, escape, and enter-save sub-assertions.

    Returns the new title saved via Enter (needed for persistence check).

    Parameters
    ----------
    native:
        Locator for the native ``<input>`` element (carries
        ``data-workspace-id``).  Use ``_get_quasar_root()`` to
        reach the Quasar ``<label>`` for class assertions.
    """
    q_root = _get_quasar_root(native)

    # --- AC4.5: Pencil click does NOT navigate ---
    with subtests.test(msg="pencil_click_no_navigate"):
        expect(pencil).to_be_visible(timeout=5000)
        current_url = page.url
        pencil.click()
        page.wait_for_timeout(500)
        assert page.url == current_url, (
            f"Pencil click should not navigate. "
            f"URL changed from {current_url} to {page.url}"
        )

    # --- AC4.1: Input becomes editable after pencil click ---
    with subtests.test(msg="input_becomes_editable"):
        # Quasar adds "q-field--outlined" when outlined prop is set
        # and removes "q-field--borderless" when borderless is removed.
        classes = q_root.get_attribute("class") or ""
        assert "q-field--outlined" in classes, (
            f"Expected outlined after pencil click, classes: {classes}"
        )

    # --- AC4.3: Escape cancels edit ---
    with subtests.test(msg="escape_cancels_edit"):
        original_value = native.input_value()
        native.fill("Title That Should Be Cancelled")
        page.wait_for_timeout(200)
        native.press("Escape")
        page.wait_for_timeout(500)

        reverted = native.input_value()
        assert reverted == original_value, (
            f"Expected revert to '{original_value}' after Escape, got '{reverted}'"
        )
        classes_after = q_root.get_attribute("class") or ""
        assert "q-field--borderless" in classes_after, (
            f"Expected borderless after Escape, classes: {classes_after}"
        )

    # --- AC4.2 (Enter): Save via Enter ---
    # Reload to get a clean component state after the Escape test.
    # The Escape handler resets editing=False and restores readonly props,
    # but a subsequent pencil click may race with pending blur events.
    new_title = f"Renamed Title {workspace_id[:8]}"
    with subtests.test(msg="enter_saves_title"):
        page.reload()
        page.wait_for_timeout(2000)
        # Re-locate after reload
        pencil = page.locator(f'[data-testid="edit-title-{workspace_id}"]')
        native = page.locator(f'[data-workspace-id="{workspace_id}"]')
        q_root = _get_quasar_root(native)

        pencil.click()
        expect(native).to_be_editable(timeout=5000)
        native.fill(new_title)
        page.wait_for_timeout(200)
        native.press("Enter")
        page.wait_for_timeout(1000)

        saved = native.input_value()
        assert saved == new_title, f"Expected '{new_title}' after Enter, got '{saved}'"
        classes_after = q_root.get_attribute("class") or ""
        assert "q-field--borderless" in classes_after, (
            f"Expected borderless after save, classes: {classes_after}"
        )

    return new_title


def _rename_persist_and_blur_subtests(
    page: Page,
    *,
    subtests: SubTests,
    workspace_id: str,
    expected_title: str,
) -> None:
    """Verify title persistence after refresh and blur-save."""
    # --- Persistence after refresh ---
    with subtests.test(msg="title_persists_after_refresh"):
        page.reload()
        page.wait_for_timeout(2000)
        native = page.locator(f'[data-workspace-id="{workspace_id}"]')
        expect(native).to_be_visible(timeout=5000)
        persisted = native.input_value()
        assert persisted == expected_title, (
            f"Expected '{expected_title}' after refresh, got '{persisted}'"
        )

    # --- AC4.2 (blur): Save via blur ---
    with subtests.test(msg="blur_saves_title"):
        pencil = page.locator(f'[data-testid="edit-title-{workspace_id}"]')
        native = page.locator(f'[data-workspace-id="{workspace_id}"]')
        pencil.click()
        # Wait for async handler to remove readonly
        expect(native).to_be_editable(timeout=5000)

        blur_title = f"Blur Saved {workspace_id[:8]}"
        native.fill(blur_title)
        page.wait_for_timeout(200)

        # Click elsewhere to trigger blur
        page.locator(".navigator-section-header").first.click()
        page.wait_for_timeout(1000)

        blur_value = native.input_value()
        assert blur_value == blur_title, (
            f"Expected '{blur_title}' after blur, got '{blur_value}'"
        )


def _setup_course_with_activity(
    page: Page,
    app_server: str,
    *,
    course_code: str,
    course_name: str,
    activity_title: str,
    student_email: str,
) -> str:
    """Create course, week, activity with template; publish and enrol student.

    Returns the course_id extracted from the URL.
    """
    create_course(
        page,
        app_server,
        code=course_code,
        name=course_name,
        semester="2026-S1",
    )

    match = re.search(r"/courses/([0-9a-f-]+)", page.url)
    assert match, f"Expected course UUID in URL, got: {page.url}"
    course_id = match.group(1)

    # Enable sharing so shared_in_unit works if needed later
    configure_course_setting(page, toggle_label="Default allow sharing", enabled=True)

    add_week(page, title="Navigator Week")
    add_activity(page, title=activity_title)

    _fill_template_workspace(page)

    # Navigate back to course detail page
    page.go_back()
    page.wait_for_url(re.compile(r"/courses/[0-9a-f-]+"), timeout=10000)

    publish_week(page, "Navigator Week")
    enrol_student(page, email=student_email)

    return course_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestNavigator:
    """E2E tests for the workspace navigator page."""

    def test_unauthenticated_redirect(self, fresh_page: Page, app_server: str) -> None:
        """AC2.5: Unauthenticated access to / redirects to /login."""
        fresh_page.goto(f"{app_server}/")
        expect(fresh_page).to_have_url(re.compile(r"/login"), timeout=10000)

    def test_navigator_renders_my_work(
        self,
        browser: Browser,
        app_server: str,
        subtests: SubTests,
    ) -> None:
        """AC1.1, AC1.7, AC2.1: My Work section with owned workspace.

        Steps:
        1. Authenticate as student.
        2. Create a workspace owned by the student via DB.
        3. Navigate to /.
        4. Verify "My Work" section header appears.
        5. Verify workspace entry is visible.
        6. Verify empty sections (Unstarted, Shared With Me) are absent.
        7. Click workspace title, verify navigation to annotation page.
        """
        context = browser.new_context()
        page = context.new_page()

        try:
            uid = uuid4().hex[:8]
            email = f"nav-mywork-{uid}@test.example.edu.au"
            _authenticate_page(page, app_server, email=email)

            # Create a workspace owned by this student
            workspace_id = _create_workspace_via_db(
                user_email=email,
                html_content="<p>My navigator test workspace content</p>",
                seed_tags=False,
            )

            with subtests.test(msg="my_work_section_renders"):
                page.goto(f"{app_server}/")
                page.wait_for_timeout(2000)

                header_texts = _get_section_header_texts(page)
                assert "My Work" in header_texts, (
                    f"Expected 'My Work' in section headers, got: {header_texts}"
                )

            with subtests.test(msg="workspace_entry_visible"):
                ws_link = page.locator(f'[data-workspace-id="{workspace_id}"]')
                expect(ws_link).to_be_visible(timeout=5000)

            with subtests.test(msg="empty_sections_absent"):
                header_texts = _get_section_header_texts(page)
                assert "Unstarted Work" not in header_texts, (
                    "Unstarted Work should not appear for unenrolled student"
                )
                assert "Shared With Me" not in header_texts, (
                    "Shared With Me should not appear when no shared workspaces"
                )

            with subtests.test(msg="title_click_navigates"):
                ws_link = page.locator(f'[data-workspace-id="{workspace_id}"]')
                ws_link.click()
                page.wait_for_url(
                    re.compile(rf"workspace_id={workspace_id}"),
                    timeout=10000,
                )
                assert "/annotation" in page.url, (
                    f"Expected /annotation in URL, got: {page.url}"
                )

            with subtests.test(msg="action_button_navigates"):
                # AC2.2: clicking Resume/Open/View button navigates to workspace
                page.goto(f"{app_server}/")
                page.wait_for_timeout(2000)

                action_btn = page.locator(".navigator-action-btn").first
                expect(action_btn).to_be_visible(timeout=5000)
                action_btn.click()
                page.wait_for_url(
                    re.compile(rf"workspace_id={workspace_id}"),
                    timeout=10000,
                )
                assert "/annotation" in page.url, (
                    f"Expected /annotation in URL, got: {page.url}"
                )

        finally:
            page.goto("about:blank")
            page.close()
            context.close()

    def test_navigator_renders_unstarted_work(
        self,
        browser: Browser,
        app_server: str,
        subtests: SubTests,
    ) -> None:
        """AC1.2: Student sees Unstarted Work for published activities.

        Steps:
        1. Instructor creates course with published activity.
        2. Student is enrolled.
        3. Student navigates to /.
        4. Verify "Unstarted Work" section appears with activity title.
        """
        uid = uuid4().hex[:8]
        student_email = f"nav-unstarted-{uid}@test.example.edu.au"
        activity_title = f"Nav Activity {uid}"

        # --- Instructor sets up course ---
        instructor_ctx = browser.new_context()
        instructor_page = instructor_ctx.new_page()

        try:
            with subtests.test(msg="instructor_creates_course"):
                _authenticate_page(
                    instructor_page, app_server, email="instructor@uni.edu"
                )
                _setup_course_with_activity(
                    instructor_page,
                    app_server,
                    course_code=f"NAV-{uid}",
                    course_name=f"Navigator Test {uid}",
                    activity_title=activity_title,
                    student_email=student_email,
                )
        finally:
            instructor_page.goto("about:blank")
            instructor_page.close()
            instructor_ctx.close()

        # --- Student checks navigator ---
        student_ctx = browser.new_context()
        student_page = student_ctx.new_page()

        try:
            _authenticate_page(student_page, app_server, email=student_email)

            with subtests.test(msg="unstarted_section_renders"):
                student_page.goto(f"{app_server}/")
                student_page.wait_for_timeout(2000)

                header_texts = _get_section_header_texts(student_page)
                assert "Unstarted Work" in header_texts, (
                    f"Expected 'Unstarted Work' in section headers, got: {header_texts}"
                )

            with subtests.test(msg="activity_title_visible"):
                activity_label = student_page.get_by_text(activity_title, exact=False)
                expect(activity_label.first).to_be_visible(timeout=5000)

            with subtests.test(msg="start_button_visible"):
                start_btn = student_page.locator(".navigator-start-btn")
                expect(start_btn.first).to_be_visible(timeout=5000)

        finally:
            student_page.goto("about:blank")
            student_page.close()
            student_ctx.close()

    def test_start_activity_clones_and_navigates(
        self,
        browser: Browser,
        app_server: str,
        subtests: SubTests,
    ) -> None:
        """AC2.3: Start button clones activity template and navigates.

        Steps:
        1. Instructor creates course with published activity + template.
        2. Student is enrolled.
        3. Student navigates to /.
        4. Verify "Unstarted Work" shows the activity.
        5. Click Start.
        6. Verify navigation to /annotation?workspace_id=...
        7. Navigate back to /.
        8. Verify activity now appears under "My Work", not "Unstarted Work".
        """
        uid = uuid4().hex[:8]
        student_email = f"nav-start-{uid}@test.example.edu.au"
        activity_title = f"Start Activity {uid}"

        # --- Instructor sets up course ---
        instructor_ctx = browser.new_context()
        instructor_page = instructor_ctx.new_page()

        try:
            with subtests.test(msg="instructor_creates_course"):
                _authenticate_page(
                    instructor_page, app_server, email="instructor@uni.edu"
                )
                _setup_course_with_activity(
                    instructor_page,
                    app_server,
                    course_code=f"START-{uid}",
                    course_name=f"Start Test {uid}",
                    activity_title=activity_title,
                    student_email=student_email,
                )
        finally:
            instructor_page.goto("about:blank")
            instructor_page.close()
            instructor_ctx.close()

        # --- Student: clone via Start button ---
        _student_start_and_verify(
            browser,
            app_server,
            student_email=student_email,
            activity_title=activity_title,
            subtests=subtests,
        )

    def test_search_filters_and_restores(
        self,
        browser: Browser,
        app_server: str,
        subtests: SubTests,
    ) -> None:
        """AC3.2, AC3.5, AC3.6, AC8.4: Search filters, restores, and handles edge cases.

        Steps:
        1. Create two workspaces with distinct content for the same user.
        2. Navigate to /.
        3. AC8.4: Type 2 chars -- verify no filtering (both workspaces visible).
        4. AC3.2: Type 3+ chars matching one workspace's content. Wait for
           debounce. Verify only matching workspace visible with snippet.
        5. AC3.5: Clear search. Verify full unfiltered view returns.
        6. AC3.6: Type a query matching nothing. Verify "No workspaces match"
           message. Click "Clear search" button. Verify full view returns.
        """
        context = browser.new_context()
        page = context.new_page()

        try:
            uid = uuid4().hex[:8]
            email = f"nav-search-{uid}@test.example.edu.au"
            _authenticate_page(page, app_server, email=email)

            # Use complete English words so PostgreSQL FTS can match
            # them. FTS stems and does not support prefix matching,
            # so partial words like "zygomo" won't match.
            # Each workspace uses a unique marker phrase.
            marker_a = f"xylophone{uid}"
            marker_b = f"marimba{uid}"

            workspace_id_a = _create_workspace_via_db(
                user_email=email,
                html_content=(f"<p>The {marker_a} flower has bilateral symmetry.</p>"),
                seed_tags=False,
            )
            workspace_id_b = _create_workspace_via_db(
                user_email=email,
                html_content=(f"<p>A {marker_b} approach to economics.</p>"),
                seed_tags=False,
            )

            _search_subtests(
                page,
                app_server,
                subtests=subtests,
                workspace_id_a=workspace_id_a,
                workspace_id_b=workspace_id_b,
                # Search for the full marker word so FTS can match it
                search_query_a=marker_a,
                nonsense_query=f"xyznonexistent{uid}",
            )

        finally:
            page.goto("about:blank")
            page.close()
            context.close()

    def test_inline_title_rename(
        self,
        browser: Browser,
        app_server: str,
        subtests: SubTests,
    ) -> None:
        """AC4.1-AC4.3, AC4.5: Inline title rename via pencil icon.

        Steps:
        1. Authenticate and create an owned workspace via DB.
        2. Navigate to /.
        3. AC4.5: Click pencil -- URL does not change.
        4. AC4.1: Verify input switches to editable (outlined).
        5. AC4.3: Type new title, press Escape -- reverts.
        6. AC4.2: Type new title, press Enter -- saves.
        7. Refresh page -- title persists.
        8. AC4.2: Type title, blur -- saves.
        """
        context = browser.new_context()
        page = context.new_page()

        try:
            uid = uuid4().hex[:8]
            email = f"nav-rename-{uid}@test.example.edu.au"
            _authenticate_page(page, app_server, email=email)

            workspace_id = _create_workspace_via_db(
                user_email=email,
                html_content="<p>Rename test content</p>",
                seed_tags=False,
            )

            page.goto(f"{app_server}/")
            page.wait_for_timeout(2000)

            pencil, native_input = _locate_title_elements(page, workspace_id)

            new_title = _rename_edit_subtests(
                page,
                subtests=subtests,
                workspace_id=workspace_id,
                pencil=pencil,
                native=native_input,
            )

            _rename_persist_and_blur_subtests(
                page,
                subtests=subtests,
                workspace_id=workspace_id,
                expected_title=new_title,
            )

        finally:
            page.goto("about:blank")
            page.close()
            context.close()

    def test_default_title_on_start(
        self,
        browser: Browser,
        app_server: str,
        subtests: SubTests,
    ) -> None:
        """AC4.4: Cloned workspace defaults title to activity name.

        Steps:
        1. Instructor creates course with published activity.
        2. Student is enrolled.
        3. Student clicks Start on the activity.
        4. Student navigates back to /.
        5. Verify workspace title matches the activity title.
        """
        uid = uuid4().hex[:8]
        student_email = f"nav-deftitle-{uid}@test.example.edu.au"
        activity_title = f"Annotate Becky Bennett {uid}"

        # --- Instructor sets up course ---
        instructor_ctx = browser.new_context()
        instructor_page = instructor_ctx.new_page()

        try:
            with subtests.test(msg="instructor_creates_course"):
                _authenticate_page(
                    instructor_page,
                    app_server,
                    email="instructor@uni.edu",
                )
                _setup_course_with_activity(
                    instructor_page,
                    app_server,
                    course_code=f"DEFT-{uid}",
                    course_name=f"Default Title Test {uid}",
                    activity_title=activity_title,
                    student_email=student_email,
                )
        finally:
            instructor_page.goto("about:blank")
            instructor_page.close()
            instructor_ctx.close()

        # --- Student: Start activity, then check title ---
        student_ctx = browser.new_context()
        student_page = student_ctx.new_page()

        try:
            _authenticate_page(student_page, app_server, email=student_email)

            with subtests.test(msg="start_activity"):
                student_page.goto(f"{app_server}/")
                student_page.wait_for_timeout(2000)

                start_btn = student_page.locator(".navigator-start-btn").first
                expect(start_btn).to_be_visible(timeout=5000)
                start_btn.click()

                student_page.wait_for_url(
                    re.compile(r"/annotation\?workspace_id="),
                    timeout=15000,
                )

            with subtests.test(msg="title_matches_activity"):
                student_page.goto(f"{app_server}/")
                student_page.wait_for_timeout(2000)

                # The workspace title input should display the
                # activity title as the default.  The NiceGUI wrapper
                # div has .navigator-title-input; the native <input>
                # is nested inside the Quasar q-input within it.
                wrapper = student_page.locator(".navigator-title-input")
                expect(wrapper.first).to_be_visible(timeout=5000)
                native = wrapper.first.locator("input").first
                title_value = native.input_value()
                assert title_value == activity_title, (
                    f"Expected default title '{activity_title}', got '{title_value}'"
                )

        finally:
            student_page.goto("about:blank")
            student_page.close()
            student_ctx.close()

    def test_infinite_scroll_loads_more_rows(
        self,
        browser: Browser,
        app_server: str,
        subtests: SubTests,
    ) -> None:
        """AC5.1, AC5.2, AC5.5: Infinite scroll pagination loads more rows.

        Sub-tests:
        1. Create 60 workspaces. Initial load shows ~50. Scroll loads more.
        2. No duplicate workspace IDs after scrolling.
        3. Multiple scrolls load all 60 rows.
        """
        context = browser.new_context()
        page = context.new_page()

        try:
            uid = uuid4().hex[:8]
            email = f"nav-scroll-{uid}@test.example.edu.au"
            _authenticate_page(page, app_server, email=email)

            # --- AC5.1 + AC5.2: more than 50 rows, scroll loads more ---
            with subtests.test(msg="initial_load_capped_at_50"):
                _create_workspaces_bulk(email, 60, content_prefix=f"Scroll test {uid}")
                page.goto(f"{app_server}/")
                page.wait_for_timeout(3000)

                initial_count = _count_workspace_entries(page)
                assert initial_count <= 50, (
                    f"Expected at most 50 entries on initial load, got {initial_count}"
                )
                assert initial_count >= 40, (
                    f"Expected at least 40 entries on initial load, got {initial_count}"
                )

            with subtests.test(msg="scroll_loads_more"):
                _scroll_navigator_to_bottom(page)
                # Wait for async load + re-render
                page.wait_for_timeout(3000)

                after_scroll_count = _count_workspace_entries(page)
                assert after_scroll_count > initial_count, (
                    f"Expected more rows after scroll. "
                    f"Before: {initial_count}, after: {after_scroll_count}"
                )

            # --- AC5.5: no duplicate workspace IDs ---
            with subtests.test(msg="no_duplicate_entries"):
                all_ws_ids = page.locator("[data-workspace-id]").evaluate_all(
                    "els => els.map(el => el.getAttribute('data-workspace-id'))"
                )
                unique_ids = set(all_ws_ids)
                assert len(unique_ids) == len(all_ws_ids), (
                    f"Duplicate workspace IDs found. "
                    f"Total: {len(all_ws_ids)}, unique: {len(unique_ids)}"
                )

            # --- AC5.5: scroll again to load remaining rows ---
            with subtests.test(msg="scroll_loads_all_rows"):
                # Keep scrolling until all 60 rows are loaded
                for _ in range(5):
                    _scroll_navigator_to_bottom(page)
                    page.wait_for_timeout(2000)

                final_count = _count_workspace_entries(page)
                assert final_count == 60, (
                    f"Expected all 60 rows after multiple scrolls, got {final_count}"
                )

        finally:
            page.goto("about:blank")
            page.close()
            context.close()

    def test_infinite_scroll_no_extra_load_under_50(
        self,
        browser: Browser,
        app_server: str,
        subtests: SubTests,
    ) -> None:
        """AC5.4: Fewer than 50 rows -- no additional loading on scroll.

        Creates 10 workspaces, verifies all are visible, scrolls to bottom,
        verifies count unchanged.
        """
        context = browser.new_context()
        page = context.new_page()

        try:
            uid = uuid4().hex[:8]
            email = f"nav-noscroll-{uid}@test.example.edu.au"
            _authenticate_page(page, app_server, email=email)

            _create_workspaces_bulk(email, 10, content_prefix=f"NoScroll {uid}")

            page.goto(f"{app_server}/")
            page.wait_for_timeout(3000)

            with subtests.test(msg="all_rows_visible"):
                initial_count = _count_workspace_entries(page)
                assert initial_count == 10, f"Expected 10 entries, got {initial_count}"

            with subtests.test(msg="scroll_no_additional_load"):
                _scroll_navigator_to_bottom(page)
                page.wait_for_timeout(2000)

                after_count = _count_workspace_entries(page)
                assert after_count == 10, (
                    f"Expected count unchanged at 10 after scroll, got {after_count}"
                )

        finally:
            page.goto("about:blank")
            page.close()
            context.close()

    def test_pagination_disabled_during_search(
        self,
        browser: Browser,
        app_server: str,
        subtests: SubTests,
    ) -> None:
        """AC5.2 (search interaction): Pagination disabled during search.

        Steps:
        1. Create 60 workspaces (triggers pagination).
        2. Type a search query that matches a subset.
        3. Scroll to bottom -- verify no extra rows loaded.
        4. Clear search -- verify full paginated view restores.
        5. Scroll to bottom -- verify pagination resumes.
        """
        context = browser.new_context()
        page = context.new_page()

        try:
            uid = uuid4().hex[:8]
            email = f"nav-searchpag-{uid}@test.example.edu.au"
            _authenticate_page(page, app_server, email=email)

            # Create 57 generic workspaces + 3 with a searchable marker.
            marker = f"searchpagmarker{uid}"
            _create_workspaces_bulk(email, 57, content_prefix=f"Generic content {uid}")
            # Create 3 workspaces with a searchable marker word
            for i in range(3):
                _create_workspace_via_db(
                    user_email=email,
                    html_content=f"<p>The {marker} document number {i}.</p>",
                    seed_tags=False,
                )

            page.goto(f"{app_server}/")
            page.wait_for_timeout(3000)

            # Variables shared across subtests
            search_count = 0

            search_input = page.locator(".navigator-search-input input")
            expect(search_input).to_be_visible(timeout=5000)

            # --- Search filters to subset ---
            with subtests.test(msg="search_filters_results"):
                # Focus search input via JS to avoid pointer interception
                # in headless mode when many cards fill the scroll area.
                _scroll_navigator_to_top(page)
                page.wait_for_timeout(500)
                search_input.focus()
                page.keyboard.type(marker, delay=30)
                # Wait for debounce (500ms) + DB query + render
                page.wait_for_timeout(3000)

                search_count = _count_workspace_entries(page)
                assert search_count <= 3, (
                    f"Expected at most 3 search results, got {search_count}"
                )

            # --- Scroll during search does NOT load more ---
            with subtests.test(msg="scroll_during_search_no_load"):
                _scroll_navigator_to_bottom(page)
                page.wait_for_timeout(2000)

                after_scroll_count = _count_workspace_entries(page)
                assert after_scroll_count == search_count, (
                    f"Expected no additional rows during search. "
                    f"Before scroll: {search_count}, "
                    f"after: {after_scroll_count}"
                )

            # --- Clear search restores paginated view ---
            with subtests.test(msg="clear_search_restores_pagination"):
                # Clear search via JS focus + Ctrl+A + Backspace
                search_input.focus()
                page.keyboard.press("Control+a")
                page.keyboard.press("Backspace")
                page.wait_for_timeout(2000)

                restored_count = _count_workspace_entries(page)
                assert restored_count >= 40, (
                    f"Expected restored paginated view (>=40 entries), "
                    f"got {restored_count}"
                )
                assert restored_count <= 50, (
                    f"Expected restored view to show at most 50 (one page), "
                    f"got {restored_count}"
                )

            # --- Scroll after clearing search loads more ---
            with subtests.test(msg="scroll_after_clear_loads_more"):
                before_scroll = _count_workspace_entries(page)
                _scroll_navigator_to_bottom(page)
                # Timer polls every 500ms; allow time for poll + DB + render.
                # Re-scroll after a pause in case content grew from the first load.
                page.wait_for_timeout(2000)
                _scroll_navigator_to_bottom(page)
                page.wait_for_timeout(2000)

                after_scroll = _count_workspace_entries(page)
                assert after_scroll > before_scroll, (
                    f"Expected more rows after scroll post-clear. "
                    f"Before: {before_scroll}, after: {after_scroll}"
                )

        finally:
            page.goto("about:blank")
            page.close()
            context.close()
