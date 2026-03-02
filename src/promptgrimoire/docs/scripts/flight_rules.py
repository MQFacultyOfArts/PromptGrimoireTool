"""Flight rules guide -- screenshot-driven troubleshooting reference.

Drives a Playwright browser through common confusion points and
captures annotated screenshots showing the correct workflow.
Named after NASA/git "flight rules" -- pre-computed answers to
"what do I do when X happens?"

Blocked screenshots (marked with TODO) require data-testid on
the template button in courses.py (see issue #230).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page

from promptgrimoire.docs import Guide

GUIDE_OUTPUT_DIR = Path("docs/guides")


def _authenticate(page: Page, base_url: str, email: str) -> None:
    """Authenticate via mock token and wait for redirect."""
    page.goto(f"{base_url}/auth/callback?token=mock-token-{email}")
    page.wait_for_url(lambda url: "/auth/callback" not in url, timeout=10000)


def _enrol_instructor() -> None:
    """Enrol the instructor so Navigator shows activities."""
    subprocess.run(
        [
            "uv",
            "run",
            "manage-users",
            "enroll",
            "instructor@uni.edu",
            "UNIT1234",
            "S1 2026",
        ],
        capture_output=True,
        check=False,
    )


def _ensure_unit_exists(page: Page, base_url: str) -> str:
    """Create a unit if it doesn't exist. Return course URL."""
    page.goto(f"{base_url}/courses/new")
    page.get_by_test_id("course-code-input").wait_for(state="visible", timeout=10000)
    page.get_by_test_id("course-code-input").fill("UNIT1234")
    page.get_by_test_id("course-name-input").fill("AI in Professional Practice")
    page.get_by_test_id("course-semester-input").fill("S1 2026")
    page.get_by_test_id("create-course-btn").click()
    page.wait_for_url(re.compile(r"/courses/[0-9a-f-]+"), timeout=10000)
    return page.url


def _ensure_week_and_activity(page: Page) -> None:
    """Add a week and activity if they don't exist."""
    page.get_by_test_id("add-week-btn").click()
    page.wait_for_url(
        re.compile(r"/courses/[0-9a-f-]+/weeks/new"),
        timeout=10000,
    )
    page.get_by_test_id("week-number-input").fill("1")
    page.get_by_test_id("week-title-input").fill("Getting Started")
    page.get_by_test_id("create-week-btn").click()
    page.wait_for_url(re.compile(r"/courses/[0-9a-f-]+$"), timeout=10000)
    page.get_by_test_id("publish-week-btn").click()
    page.wait_for_timeout(1000)

    page.get_by_test_id("add-activity-btn").click()
    page.wait_for_url(
        re.compile(
            r"/courses/[0-9a-f-]+/weeks/[0-9a-f-]+"
            r"/activities/new"
        ),
        timeout=10000,
    )
    page.get_by_test_id("activity-title-input").fill("Annotate Your Conversation")
    page.get_by_test_id("activity-description-input").fill(
        "Upload and annotate an AI conversation."
    )
    page.get_by_test_id("create-activity-btn").click()
    page.wait_for_url(re.compile(r"/courses/[0-9a-f-]+$"), timeout=10000)


# -----------------------------------------------------------------
# Flight rule sections
# -----------------------------------------------------------------


def _rule_template_vs_instance(
    page: Page,
    base_url: str,  # noqa: ARG001 — needed once #230 adds template-btn testid
    course_url: str,
    guide: Guide,
) -> None:
    """I configured tags but students can't see them."""
    with guide.step("I configured tags but students can't see them") as g:
        g.note(
            "**Diagnosis:** You configured tags in your own "
            "workspace (a student instance), not the template. "
            "Tags set on instances only affect that workspace."
        )
        g.note(
            "**Fix:** Go to **Unit Settings** and click the "
            "green **Create Template** or **Edit Template** "
            "button next to the activity. This opens the "
            "template workspace (purple chip). Configure tags "
            "there -- students will inherit them when they "
            "start the activity."
        )

        # Show the Unit Settings page with the template button
        page.goto(course_url)
        page.wait_for_timeout(2000)
        # TODO(#230): screenshot with highlight on template-btn
        # once data-testid is added to courses.py
        g.screenshot(
            "Unit Settings page showing Create Template button",
        )


def _rule_chip_colours(
    page: Page,
    base_url: str,  # noqa: ARG001 — needed once #230 adds template-btn testid
    course_url: str,
    guide: Guide,
) -> None:
    """How do I know if I'm in a template or instance?"""
    with guide.step("How do I know if I'm in a template or instance?") as g:
        g.note("Look at the coloured chip near the top of the annotation page:")
        g.note(
            "- **Purple chip** saying "
            '"Template: [activity name]" -- '
            "you are editing the template. Changes here "
            "propagate to new student workspaces."
        )
        g.note(
            "- **Blue chip** showing the activity name -- "
            "you are in a student workspace. Changes here "
            "are private to this workspace."
        )

        # Navigate to template workspace to show purple chip
        # TODO(#230): navigate via template-btn data-testid
        # For now, take a screenshot of the course page
        page.goto(course_url)
        page.wait_for_timeout(2000)
        g.screenshot(
            "Purple chip = template, blue chip = instance",
        )


def _rule_start_vs_template(
    page: Page,
    base_url: str,
    guide: Guide,
) -> None:
    """I clicked Start but wanted the template."""
    with guide.step("I clicked Start but wanted the template") as g:
        g.note(
            "The **Start** button on the Navigator creates "
            "your own student workspace (blue chip). To "
            "configure the activity for students, go to "
            "**Unit Settings** instead and click the green "
            "**Create Template** / **Edit Template** button."
        )
        g.note(
            "Your student workspace is not wasted -- it is "
            "just your own working copy. It won't be visible "
            "to students unless you explicitly share it."
        )

        # Show Navigator with Start button highlighted
        _enrol_instructor()
        page.goto(base_url)
        page.wait_for_timeout(2000)
        start_btn = page.locator('[data-testid^="start-activity-btn"]')
        if start_btn.count() > 0:
            g.screenshot(
                "Start button creates a student workspace, not the template",
                highlight=["start-activity-btn"],
            )


def _rule_import_tags(
    guide: Guide,
) -> None:
    """Tag import from another activity shows nothing."""
    with guide.step("Tag import from another activity shows nothing") as g:
        g.note(
            "The tag import dropdown lists other activities' "
            "**template** workspaces. If the source activity's "
            "template has no tags (because you configured tags "
            "in your own workspace instead), the import will "
            "find nothing."
        )
        g.note(
            "**Fix:** Open the source activity's template "
            "(Unit Settings → Edit Template), configure tags "
            "there, then try the import again."
        )


# -----------------------------------------------------------------
# Main entry point
# -----------------------------------------------------------------


def run_flight_rules_guide(page: Page, base_url: str) -> None:
    """Run the flight rules guide."""
    with Guide("Flight Rules", GUIDE_OUTPUT_DIR, page) as guide:
        guide.note(
            "Pre-computed answers to common questions. "
            'Named after NASA\'s "flight rules" -- '
            "what to do when something unexpected happens."
        )

        # Set up prerequisite data
        _authenticate(page, base_url, "instructor@uni.edu")
        course_url = _ensure_unit_exists(page, base_url)
        _ensure_week_and_activity(page)

        _rule_template_vs_instance(page, base_url, course_url, guide)
        _rule_chip_colours(page, base_url, course_url, guide)
        _rule_start_vs_template(page, base_url, guide)
        _rule_import_tags(guide)
