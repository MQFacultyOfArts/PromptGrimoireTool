"""Instructor setup guide -- produces markdown with annotated screenshots.

Drives a Playwright browser through the full instructor setup workflow:
login, create unit, add week, create activity, configure tags, enrol
student, and verify student view. Each step uses the Guide DSL to emit
narrative markdown with highlighted screenshots.
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
    """Enrol the instructor in the course via manage-users CLI.

    The navigator's 'Start' button only appears for activities in
    enrolled courses, so the instructor must be enrolled before
    navigating to the annotation page.
    """
    subprocess.run(
        [
            "uv",
            "run",
            "manage-users",
            "enroll",
            "instructor@uni.edu",
            "TRAN8034",
            "S1 2026",
        ],
        capture_output=True,
        check=False,
    )


_SEED_TEMPLATE_TAGS_SCRIPT = """\
import asyncio
from sqlmodel import select
from promptgrimoire.db.engine import get_session
from promptgrimoire.db.models import (
    Activity, Course, Tag, TagGroup, Week, Workspace,
)

async def main():
    async with get_session() as s:
        c = (await s.exec(
            select(Course).where(
                Course.code == "{code}",
                Course.semester == "{semester}",
            )
        )).first()
        if not c:
            return
        a = (await s.exec(
            select(Activity).join(Week).where(Week.course_id == c.id)
        )).first()
        if not a:
            return
        wid = a.template_workspace_id
        if (await s.exec(select(TagGroup).where(TagGroup.workspace_id == wid))).first():
            return
        g = TagGroup(workspace_id=wid, name="Translation Analysis",
                     color="#4a90d9", order_index=0)
        s.add(g)
        await s.flush()
        tags = [("Source Text Features", "#1f77b4"),
                ("Translation Strategy", "#2ca02c"),
                ("Cultural Adaptation", "#d62728")]
        for i, (n, cl) in enumerate(tags):
            s.add(Tag(workspace_id=wid, group_id=g.id, name=n,
                      color=cl, locked=False, order_index=i))
        await s.flush()
        w = await s.get(Workspace, wid)
        if w:
            w.next_tag_order = len(tags)
            w.next_group_order = 1
            s.add(w)
            await s.flush()

asyncio.run(main())
"""


def _seed_template_tags(course_code: str, semester: str) -> None:
    """Seed tags into the activity's template workspace via DB.

    Runs in a separate subprocess because the NiceGUI server already
    owns the event loop — ``asyncio.run()`` cannot be called from a
    running loop. The bash script used the same subprocess pattern.
    """
    script = _SEED_TEMPLATE_TAGS_SCRIPT.format(code=course_code, semester=semester)
    subprocess.run(
        ["uv", "run", "python", "-c", script],
        capture_output=True,
        check=False,
    )


def _create_demo_student() -> None:
    """Create and enrol a demo student for the student view step."""
    for cmd in [
        [
            "uv",
            "run",
            "manage-users",
            "create",
            "student-demo@test.example.edu.au",
            "--name",
            "Demo Student",
        ],
        [
            "uv",
            "run",
            "manage-users",
            "enroll",
            "student-demo@test.example.edu.au",
            "TRAN8034",
            "S1 2026",
        ],
    ]:
        subprocess.run(cmd, capture_output=True, check=False)


# ---------------------------------------------------------------------------
# Per-step functions (extracted to keep run_instructor_guide under 50 stmts)
# ---------------------------------------------------------------------------


def _step_create_unit(page: Page, base_url: str, guide: Guide) -> str:
    """Step 2: Navigate to /courses/new, fill form, submit.

    Returns the course detail URL for later navigation.
    """
    with guide.step("Step 2: Creating a Unit") as g:
        g.note("Navigate to Units and create a new unit for your class.")
        page.goto(f"{base_url}/courses/new")
        page.get_by_test_id("course-code-input").wait_for(
            state="visible", timeout=10000
        )
        page.get_by_test_id("course-code-input").fill("TRAN8034")
        page.get_by_test_id("course-name-input").fill("Translation Technologies")
        page.get_by_test_id("course-semester-input").fill("S1 2026")
        g.screenshot(
            "Create unit form with code, name, and semester fields",
            highlight=[
                "course-code-input",
                "course-name-input",
                "course-semester-input",
            ],
        )
        g.note("Enter the unit code, name, and semester, then click Create.")
        page.get_by_test_id("create-course-btn").click()
        page.wait_for_url(re.compile(r"/courses/[0-9a-f-]+"), timeout=10000)
    return page.url


def _step_add_week(page: Page, guide: Guide) -> None:
    """Step 3: Add and publish a week."""
    with guide.step("Step 3: Adding a Week") as g:
        page.get_by_test_id("add-week-btn").click()
        page.wait_for_url(re.compile(r"/courses/[0-9a-f-]+/weeks/new"), timeout=10000)
        page.get_by_test_id("week-number-input").fill("3")
        page.get_by_test_id("week-title-input").fill("Source Text Analysis")
        page.get_by_test_id("create-week-btn").click()
        page.wait_for_url(re.compile(r"/courses/[0-9a-f-]+$"), timeout=10000)
        g.note("Create a week by entering the week number and title.")

        page.get_by_test_id("publish-week-btn").click()
        page.wait_for_timeout(1000)
        g.note("Publish the week to make it visible to students.")


def _step_create_activity(page: Page, guide: Guide) -> None:
    """Step 4: Create an activity within the week."""
    with guide.step("Step 4: Creating an Activity") as g:
        page.get_by_test_id("add-activity-btn").click()
        page.wait_for_url(
            re.compile(r"/courses/[0-9a-f-]+/weeks/[0-9a-f-]+/activities/new"),
            timeout=10000,
        )
        page.get_by_test_id("activity-title-input").fill("Source Text Analysis with AI")
        page.get_by_test_id("activity-description-input").fill(
            "Analyse a source text using AI conversation tools, "
            "then annotate your conversation in the Grimoire."
        )
        page.get_by_test_id("create-activity-btn").click()
        page.wait_for_url(re.compile(r"/courses/[0-9a-f-]+$"), timeout=10000)
        g.note(
            "Create an activity within the week. Students will create "
            "workspaces from this activity."
        )


def _step_configure_tags(page: Page, base_url: str, guide: Guide) -> None:
    """Step 5: Open annotation workspace, create tag group and tags."""
    with guide.step("Step 5: Configuring Tags") as g:
        g.note(
            "Tags help students categorise their annotations. "
            "Configure tag groups and tags for the activity."
        )

        # Enrol instructor so navigator shows Start button
        _enrol_instructor()

        # Navigate home and start the activity to create a workspace
        page.goto(base_url)
        page.wait_for_timeout(2000)
        start_btn = page.locator('[data-testid^="start-activity-btn"]')
        start_btn.first.wait_for(state="visible", timeout=10000)
        start_btn.first.click()

        # Wait for annotation page
        page.wait_for_url(re.compile(r"/annotation\?workspace_id="), timeout=15000)

        _add_sample_content(page)
        _create_tag_group_and_tags(page, g)

        # Close tag management dialog
        page.get_by_test_id("tag-management-done-btn").click()
        page.wait_for_timeout(1000)

        # Seed tags into template workspace for student inheritance
        _seed_template_tags("TRAN8034", "S1 2026")


def _step_enrol_student(page: Page, course_url: str, guide: Guide) -> None:
    """Step 6: Navigate to enrollment page and enrol a student."""
    with guide.step("Step 6: Enrolling Students") as g:
        g.note("Navigate to the unit's enrollment page to add students.")
        # Navigate back to the course detail page
        page.goto(course_url)
        page.get_by_test_id("manage-enrollments-btn").wait_for(
            state="visible", timeout=10000
        )

        page.get_by_test_id("manage-enrollments-btn").click()
        page.wait_for_url(re.compile(r"/courses/[0-9a-f-]+/enrollments"), timeout=10000)

        page.get_by_test_id("enrollment-email-input").fill("student@uni.edu")
        page.get_by_test_id("add-enrollment-btn").click()

        # Wait for success notification
        page.get_by_text(re.compile(r"Enrollment added")).wait_for(
            state="visible", timeout=5000
        )
        g.screenshot(
            "Enrollment page showing student added",
            highlight=["enrollment-email-input", "add-enrollment-btn"],
        )
        g.note(
            "Add student email addresses to enrol them in the unit. "
            "Students will see the unit and its activities on their "
            "Navigator after enrolment."
        )

        page.get_by_test_id("back-to-unit-btn").click()
        page.wait_for_url(re.compile(r"/courses/[0-9a-f-]+$"), timeout=10000)

        # Also enrol the demo student for step 7 verification
        _create_demo_student()


def _add_sample_content(page: Page) -> None:
    """Add sample content so the tag toolbar renders.

    Uses ``.q-editor__content`` to locate Quasar QEditor's inner
    content-editable div. This is a known exception to the data-testid
    convention: Quasar renders this div internally and our code cannot
    attach a data-testid to it. The same pattern is used in E2E tests
    (annotation_helpers.py, test_instructor_workflow.py).
    """
    content_input = page.get_by_test_id("content-editor").locator(".q-editor__content")
    content_input.wait_for(state="visible", timeout=5000)
    content_input.fill(
        "What is source text analysis in translation? "
        "Source text analysis examines the original document to "
        "identify key features, register, and cultural context "
        "before translation begins."
    )
    page.get_by_test_id("add-document-btn").click()

    confirm_btn = page.get_by_test_id("confirm-content-type-btn")
    confirm_btn.wait_for(state="visible", timeout=5000)
    confirm_btn.click()

    page.get_by_test_id("tag-settings-btn").wait_for(state="visible", timeout=10000)


def _create_tag_group_and_tags(page: Page, guide: Guide) -> None:
    """Open tag management, create a group with three tags, screenshot."""
    page.get_by_test_id("tag-settings-btn").click()
    page.get_by_test_id("add-tag-group-btn").wait_for(state="visible", timeout=5000)

    # Add a tag group
    page.get_by_test_id("add-tag-group-btn").click()
    page.wait_for_timeout(1000)

    # Find the new group header and name it
    group_header = page.locator('[data-testid^="tag-group-header-"]').first
    group_header.wait_for(state="visible", timeout=5000)
    testid = group_header.get_attribute("data-testid") or ""
    group_id = testid.removeprefix("tag-group-header-")

    page.get_by_test_id(f"group-name-input-{group_id}").click()
    page.get_by_test_id(f"group-name-input-{group_id}").fill("Translation Analysis")
    page.wait_for_timeout(500)

    # Add tags
    for tag_name in [
        "Source Text Features",
        "Translation Strategy",
        "Cultural Adaptation",
    ]:
        page.get_by_test_id(f"group-add-tag-btn-{group_id}").click()
        page.wait_for_timeout(1000)
        last_input = page.locator('[data-testid^="tag-name-input-"]').last
        last_input.click()
        last_input.fill(tag_name)

    guide.screenshot(
        "Tag groups and tags configured for the activity",
        highlight=["add-tag-group-btn"],
    )
    guide.note(
        "Configure tag groups and tags. Students' workspaces will "
        "inherit this tag configuration."
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def run_instructor_guide(page: Page, base_url: str) -> None:
    """Run the instructor setup guide, producing markdown and screenshots."""
    with Guide("Instructor Setup", GUIDE_OUTPUT_DIR, page) as guide:
        # Step 1: Login and Navigator
        with guide.step("Step 1: Login and Navigator") as g:
            _authenticate(page, base_url, "instructor@uni.edu")
            g.note(
                "After logging in, you see the Navigator. As a new instructor "
                "with no units configured, it will be empty."
            )

        # Steps 2-5: course setup
        course_url = _step_create_unit(page, base_url, guide)
        _step_add_week(page, guide)
        _step_create_activity(page, guide)
        _step_configure_tags(page, base_url, guide)

        # Step 6: Enrollment UI
        _step_enrol_student(page, course_url, guide)

        # Step 7: Verifying the Student View
        with guide.step("Step 7: Verifying the Student View") as g:
            g.note("Re-authenticate as a student to verify the activity is visible.")
            _authenticate(page, base_url, "student-demo@test.example.edu.au")
            g.note(
                "The student can see the unit and activity on their "
                "Navigator. They can click Start to create a workspace."
            )
