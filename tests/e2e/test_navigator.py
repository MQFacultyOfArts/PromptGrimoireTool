"""E2E tests for the workspace navigator page.

Verifies the navigator page at ``/`` renders workspace sections correctly,
handles authentication, provides workspace navigation, and supports search.

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

Traceability:
- Issue: #196 (Workspace Navigator)
- Design: docs/implementation-plans/2026-02-24-workspace-navigator-196/phase_04.md
- Design: docs/implementation-plans/2026-02-24-workspace-navigator-196/phase_05.md
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

                # "My Work" section header should be visible
                section_headers = page.locator(".navigator-section-header")
                header_texts = [
                    section_headers.nth(i).inner_text()
                    for i in range(section_headers.count())
                ]
                assert "My Work" in header_texts, (
                    f"Expected 'My Work' in section headers, got: {header_texts}"
                )

            with subtests.test(msg="workspace_entry_visible"):
                # The workspace link should be present with data-workspace-id
                ws_link = page.locator(f'[data-workspace-id="{workspace_id}"]')
                expect(ws_link).to_be_visible(timeout=5000)

            with subtests.test(msg="empty_sections_absent"):
                # "Unstarted Work" should NOT appear (student not enrolled)
                header_texts = [
                    section_headers.nth(i).inner_text()
                    for i in range(section_headers.count())
                ]
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

                section_headers = student_page.locator(".navigator-section-header")
                header_texts = [
                    section_headers.nth(i).inner_text()
                    for i in range(section_headers.count())
                ]
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
