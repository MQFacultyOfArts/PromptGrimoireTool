"""Shared helper functions for course management E2E tests.

These helpers drive the courses UI (create course, add week, add activity,
configure copy protection, publish week) via Playwright locators.  All
functions expect an **already-authenticated** page.

The helpers match the actual page routes in ``src/promptgrimoire/pages/courses.py``:
- ``/courses``               -- course list
- ``/courses/new``           -- create course form (separate page, not dialog)
- ``/courses/{id}``          -- course detail with weeks
- ``/courses/{id}/weeks/new``            -- add week form (separate page)
- ``/courses/{id}/weeks/{wid}/activities/new`` -- add activity form
- Course settings dialog     -- opened via gear icon on course detail page

Traceability:
- Issue: #156 (E2E test migration)
- Design: docs/design-plans/2026-02-14-156-e2e-test-migration.md Phase 3
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page


def create_course(
    page: Page,
    app_server: str,
    *,
    code: str,
    name: str,
    semester: str,
) -> None:
    """Navigate to /courses/new, fill the form, and submit.

    After submission the page redirects to the course detail page
    (``/courses/{id}``).  This function waits for that redirect.

    Args:
        page: Authenticated Playwright page.
        app_server: Base URL of the test server.
        code: Course code (e.g. ``"LAWS1100"``).
        name: Course name (e.g. ``"Contracts"``).
        semester: Semester string (e.g. ``"2026-S1"``).
    """
    page.goto(f"{app_server}/courses/new")

    # The form uses placeholder text for identification
    page.get_by_placeholder("e.g., LAWS1100").fill(code)
    page.get_by_placeholder("e.g., Contracts").fill(name)
    page.get_by_placeholder("e.g., 2025-S1").fill(semester)

    page.get_by_role("button", name="Create").click()

    # Wait for redirect to course detail page
    page.wait_for_url(re.compile(r"/courses/[0-9a-f-]+"), timeout=10000)


def add_week(
    page: Page,
    *,
    week_number: int | None = None,
    title: str,
) -> None:
    """Click "Add Week" on the course detail page, fill the form, submit.

    The "Add Week" button navigates to ``/courses/{id}/weeks/new``.
    The form auto-fills the next week number, so ``week_number`` is
    optional (only override when the default is wrong).

    After submission, redirects back to the course detail page.

    Args:
        page: Authenticated Playwright page on a course detail page.
        week_number: Override for the week number input.  ``None`` keeps
            the auto-suggested value.
        title: Week title (e.g. ``"Introduction to Contracts"``).
    """
    page.get_by_role("button", name="Add Week").click()

    # Wait for the week creation page
    page.wait_for_url(re.compile(r"/courses/[0-9a-f-]+/weeks/new"), timeout=10000)

    if week_number is not None:
        number_input = page.get_by_label("Week Number")
        number_input.fill(str(week_number))

    page.get_by_placeholder("e.g., Introduction to Contracts").fill(title)

    page.get_by_role("button", name="Create").click()

    # Wait for redirect back to course detail page
    page.wait_for_url(re.compile(r"/courses/[0-9a-f-]+$"), timeout=10000)


def add_activity(page: Page, *, title: str, description: str = "") -> None:
    """Click "Add Activity" on a week card, fill the form, submit.

    The "Add Activity" button navigates to
    ``/courses/{id}/weeks/{wid}/activities/new``.

    After submission, redirects back to the course detail page.

    Args:
        page: Authenticated Playwright page on a course detail page.
        title: Activity title (e.g. ``"Annotate Becky"``).
        description: Optional activity description.
    """
    page.get_by_role("button", name="Add Activity").click()

    # Wait for the activity creation page
    page.wait_for_url(
        re.compile(r"/courses/[0-9a-f-]+/weeks/[0-9a-f-]+/activities/new"),
        timeout=10000,
    )

    page.get_by_placeholder("e.g., Annotate Becky Bennett Interview").fill(title)

    if description:
        page.get_by_placeholder("Markdown description of the activity").fill(
            description
        )

    page.get_by_role("button", name="Create").click()

    # Wait for redirect back to course detail page
    page.wait_for_url(re.compile(r"/courses/[0-9a-f-]+$"), timeout=10000)


def configure_course_setting(page: Page, *, toggle_label: str, enabled: bool) -> None:
    """Open course settings dialog and set a toggle by label.

    The settings dialog is opened via the gear icon button on the
    course detail page header.

    Args:
        page: Authenticated Playwright page on a course detail page.
        toggle_label: Text label of the toggle to set.
        enabled: Whether the toggle should be on or off.
    """
    # Click the settings gear icon button — NiceGUI icon-only buttons have no
    # accessible name, so locate via the Material Icon text inside the button.
    page.locator("button").filter(
        has=page.locator("i.q-icon", has_text="settings")
    ).click()

    # Wait for the dialog to appear
    dialog_title = page.get_by_text("Unit Settings:")
    dialog_title.wait_for(state="visible", timeout=5000)

    # NiceGUI ui.switch renders as Quasar q-toggle — scope to the component.
    # Quasar manages state via Vue reactivity; the hidden checkbox's checked
    # property is unreliable. Use aria-checked on the inner div instead.
    toggle = page.locator(".q-toggle").filter(has_text=toggle_label)

    is_currently_on = toggle.get_attribute("aria-checked") == "true"
    if is_currently_on != enabled:
        toggle.click()

    page.get_by_role("button", name="Save").click()

    # Wait for the dialog to close and success notification
    dialog_title.wait_for(state="hidden", timeout=5000)


def configure_course_copy_protection(page: Page, *, enabled: bool) -> None:
    """Open course settings dialog and set copy protection."""
    configure_course_setting(
        page, toggle_label="Default copy protection", enabled=enabled
    )


def enrol_student(page: Page, *, email: str) -> None:
    """Navigate to manage enrollments and add a student.

    Expects the page to be on a course detail page (``/courses/{id}``).
    Navigates to the enrollments page, fills the email, and clicks Add.
    Waits for the success notification before returning.

    Args:
        page: Authenticated Playwright page on a course detail page.
        email: Student email address to enrol.
    """
    page.get_by_role("button", name="Manage Enrollments").click()
    page.wait_for_url(re.compile(r"/courses/[0-9a-f-]+/enrollments"), timeout=10000)

    page.get_by_label("Email Address").fill(email)

    page.get_by_role("button", name="Add").click()

    # Wait for success notification
    page.get_by_text(re.compile(r"Enrollment added")).wait_for(
        state="visible", timeout=5000
    )

    # Navigate back to course detail page
    page.get_by_role("button", name="Back to Course").click()
    page.wait_for_url(re.compile(r"/courses/[0-9a-f-]+$"), timeout=10000)


def publish_week(page: Page, week_title: str) -> None:
    """Find a week card and click its Publish button.

    Weeks are rendered as cards with the format
    ``"Week N: <title>"``.  The Publish button is a flat dense
    button within the same card.

    Args:
        page: Authenticated Playwright page on a course detail page.
        week_title: The title text to locate the week card
            (e.g. ``"Introduction to Contracts"``).
    """
    # Find the week label containing the title, then scope to its card ancestor
    week_label = page.get_by_text(re.compile(rf"Week \d+:\s*{re.escape(week_title)}"))
    week_label.wait_for(state="visible", timeout=5000)

    # Navigate up to the card container — the card is a .q-card ancestor
    card = week_label.locator("xpath=ancestor::div[contains(@class, 'q-card')]")

    # Click the Publish button within that card
    card.get_by_role("button", name="Publish").click()

    # Wait for the button text to change to "Unpublish" (indicates success)
    card.get_by_role("button", name="Unpublish").wait_for(state="visible", timeout=5000)
