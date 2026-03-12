"""Using PromptGrimoire flight-rules guide.

Generates a single-page reference document organised by feature domain.
Each entry answers a first-person question ("I want to..." or "Why is...?")
with screenshots captured from a live application instance.

Requires data state from instructor + student guides (UNIT1234, activity,
workspace, tags). Runs after all sequential guides in the build pipeline.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page  # annotation-only; safe with PEP 563

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from promptgrimoire.docs import Guide
from promptgrimoire.docs.helpers import wait_for_text_walker

GUIDE_OUTPUT_DIR = Path("docs/guides")

# ---------------------------------------------------------------------------
# Authentication helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Prerequisite validation
# ---------------------------------------------------------------------------


def _ensure_prerequisites(page: Page, base_url: str) -> str:
    """Ensure UNIT1234 exists and return the course detail URL.

    Authenticates as the instructor, checks the Navigator for UNIT1234.
    If missing, runs the instructor guide to create it. Returns the
    course URL for entries that need Unit Settings navigation.
    """
    _enrol_instructor()
    _authenticate(page, base_url, "instructor@uni.edu")

    try:
        page.locator('[data-testid^="start-activity-btn"]').first.wait_for(
            state="visible",
            timeout=5000,
        )
        unit_visible = page.locator("text=UNIT1234").count() > 0
    except PlaywrightTimeoutError:
        unit_visible = False

    if not unit_visible:
        from promptgrimoire.docs.scripts.instructor_setup import (  # noqa: PLC0415
            run_instructor_guide,
        )

        run_instructor_guide(page, base_url)
        _enrol_instructor()
        _authenticate(page, base_url, "instructor@uni.edu")

    # Navigate to course detail page via /courses and find UNIT1234
    page.goto(f"{base_url}/courses")
    page.wait_for_timeout(2000)
    unit_link = page.locator("a", has_text="UNIT1234").first
    unit_link.wait_for(state="visible", timeout=10000)
    unit_link.click()
    page.wait_for_url(re.compile(r"/courses/[0-9a-f-]+"), timeout=10000)
    return page.url


# ---------------------------------------------------------------------------
# Getting Started
# ---------------------------------------------------------------------------


def _entry_log_in(page: Page, base_url: str, guide: Guide) -> None:
    """I want to log in for the first time."""
    with guide.step("I want to log in for the first time", level=3) as g:
        g.note(
            "Navigate to the application URL. You will be prompted to "
            "enter your email address for a magic link login."
        )
        page.goto(f"{base_url}/auth/login")
        page.wait_for_timeout(1000)
        g.screenshot("Login page", highlight=["email-input"])
        g.note(
            "Enter your university email address and click **Send Magic Link**. "
            "Check your inbox for the login link."
        )
        g.note(
            "See [Student Workflow - Step 1](student-workflow.md#step-1-logging-in) "
            "for a step-by-step walkthrough."
        )


def _entry_no_activities(page: Page, base_url: str, guide: Guide) -> None:
    """I don't see any activities after logging in."""
    with guide.step("I don't see any activities after logging in", level=3) as g:
        g.note(
            "**Diagnosis:** You are not enrolled in any units, or the "
            "instructor has not yet published any weeks with activities."
        )
        g.note(
            "**Fix:** Check with your instructor that you are enrolled "
            "in the correct unit and semester. The instructor can verify "
            "your enrolment in Unit Settings."
        )
        # Show empty Navigator
        _authenticate(page, base_url, "instructor@uni.edu")
        g.screenshot("Navigator with no activities visible")
        g.note(
            "See [Instructor Setup - Step 6]"
            "(instructor-setup.md#step-6-enrolling-students) "
            "for how instructors add students to a unit."
        )


# ---------------------------------------------------------------------------
# Workspaces
# ---------------------------------------------------------------------------


def _entry_create_workspace(page: Page, base_url: str, guide: Guide) -> None:
    """I want to create a workspace for an activity."""
    with guide.step("I want to create a workspace for an activity", level=3) as g:
        g.note(
            "On the Navigator, find the activity your instructor assigned. "
            "Click **Start** to create your own workspace."
        )
        _authenticate(page, base_url, "student-demo@test.example.edu.au")
        page.locator('[data-testid^="start-activity-btn"]').first.wait_for(
            state="visible", timeout=10000
        )
        g.screenshot(
            "Navigator showing Start button for the activity",
            highlight=["start-activity-btn"],
        )
        g.note(
            "Your workspace inherits the tag configuration set by your "
            "instructor. You can start annotating immediately."
        )
        g.note(
            "See [Student Workflow - Step 3]"
            "(student-workflow.md#step-3-creating-a-workspace) "
            "for the full walkthrough."
        )


def _entry_tags_not_visible(page: Page, course_url: str, guide: Guide) -> None:
    """I configured tags but students can't see them."""
    with guide.step("I configured tags but students can't see them", level=3) as g:
        g.note(
            "**Diagnosis:** You configured tags in your own workspace "
            "(a student instance), not the template. Tags set on instances "
            "only affect that workspace."
        )
        g.note(
            "**Fix:** Go to **Unit Settings** and click the green "
            "**Create Template** or **Edit Template** button next to "
            "the activity. This opens the template workspace (purple "
            "chip). Configure tags there -- students will inherit them "
            "when they start the activity."
        )
        page.goto(course_url)
        page.wait_for_timeout(2000)
        g.screenshot(
            "Unit Settings page showing Create Template button",
            highlight=["template-btn"],
        )
        g.note(
            "See [Instructor Setup - Step 5]"
            "(instructor-setup.md#step-5-configuring-tags-in-the-template) "
            "for a complete walkthrough."
        )


def _entry_start_vs_template(page: Page, base_url: str, guide: Guide) -> None:
    """I clicked Start but wanted the template."""
    with guide.step("I clicked Start but wanted the template", level=3) as g:
        g.note(
            "The **Start** button on the Navigator creates your own "
            "student workspace (blue chip). To configure the activity "
            "for students, go to **Unit Settings** instead and click "
            "the green **Create Template** / **Edit Template** button."
        )
        g.note(
            "Your student workspace is not wasted -- it is just your "
            "own working copy. It won't be visible to students unless "
            "you explicitly share it."
        )
        _enrol_instructor()
        _authenticate(page, base_url, "instructor@uni.edu")
        page.goto(base_url)
        page.wait_for_timeout(2000)
        start_btn = page.locator('[data-testid^="start-activity-btn"]')
        if start_btn.count() > 0:
            g.screenshot(
                "Start button creates a student workspace, not the template",
                highlight=["start-activity-btn"],
            )


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


def _entry_create_tag_group(page: Page, course_url: str, guide: Guide) -> None:
    """I want to create a tag group for my activity."""
    with guide.step("I want to create a tag group for my activity", level=3) as g:
        g.note(
            "Open the template workspace from **Unit Settings**, then "
            "click the gear icon to open tag management."
        )
        page.goto(course_url)
        page.wait_for_timeout(2000)
        template_btn = page.locator('[data-testid^="template-btn-"]').first
        template_btn.wait_for(state="visible", timeout=10000)
        template_btn.click()
        page.wait_for_url(re.compile(r"/annotation\?workspace_id="), timeout=15000)
        page.get_by_test_id("tag-settings-btn").wait_for(state="visible", timeout=10000)
        page.get_by_test_id("tag-settings-btn").click()
        page.get_by_test_id("add-tag-group-btn").wait_for(state="visible", timeout=5000)
        g.screenshot(
            "Tag management dialog with Add Group button",
            highlight=["add-tag-group-btn"],
        )
        g.note(
            "Click **Add Group** to create a new tag group, then add "
            "tags within the group. Students will inherit this tag "
            "vocabulary when they start the activity."
        )
        g.note(
            "See [Instructor Setup - Step 5]"
            "(instructor-setup.md#step-5-configuring-tags-in-the-template) "
            "for a complete walkthrough."
        )
        # Close dialog to leave clean state
        page.get_by_test_id("tag-management-done-btn").click()
        page.wait_for_timeout(1000)


def _entry_import_tags(guide: Guide) -> None:
    """Tag import from another activity shows nothing."""
    with guide.step("Tag import from another activity shows nothing", level=3) as g:
        g.note(
            "**Diagnosis:** The tag import dropdown lists other activities' "
            "**template** workspaces. If the source activity's template "
            "has no tags (because you configured tags in your own "
            "workspace instead), the import will find nothing."
        )
        g.note(
            "**Fix:** Open the source activity's template "
            "(Unit Settings -> Edit Template), configure tags there, "
            "then try the import again."
        )


# ---------------------------------------------------------------------------
# Annotating
# ---------------------------------------------------------------------------


def _entry_highlight_text(page: Page, base_url: str, guide: Guide) -> None:
    """I want to highlight text and apply a tag."""
    with guide.step("I want to highlight text and apply a tag", level=3) as g:
        g.note(
            "Select text in your conversation by clicking and dragging. "
            "A tag menu appears -- click a tag to apply it."
        )
        # Navigate to existing student workspace
        _authenticate(page, base_url, "student-demo@test.example.edu.au")
        page.goto(base_url)
        page.wait_for_timeout(2000)

        # Click Start to open an existing workspace (or create one)
        start_btn = page.locator('[data-testid^="start-activity-btn"]').first
        start_btn.wait_for(state="visible", timeout=10000)
        start_btn.click()

        wait_for_text_walker(page, timeout=15000)

        g.screenshot(
            "Tag toolbar appearing after text selection",
            highlight=["tag-toolbar"],
        )
        g.note(
            "See [Student Workflow - Step 5]"
            "(student-workflow.md#step-5-annotating---creating-a-highlight) "
            "for a detailed walkthrough."
        )


def _entry_add_comment(page: Page, guide: Guide) -> None:
    """I want to add a comment to my highlight."""
    with guide.step("I want to add a comment to my highlight", level=3) as g:
        g.note(
            "Click on a highlight in the sidebar to expand it, then "
            "type your comment in the text input and click the post button."
        )
        card = page.locator("[data-testid='annotation-card']").first
        card.wait_for(state="visible", timeout=5000)
        g.screenshot(
            "Comment input on an annotation card",
            highlight=["comment-input"],
        )
        g.note(
            "Comments let you record your analysis and reasoning. "
            "They appear below each highlight in the sidebar."
        )
        g.note(
            "See [Student Workflow - Step 6]"
            "(student-workflow.md#step-6-adding-a-comment) "
            "for a detailed walkthrough."
        )


# ---------------------------------------------------------------------------
# Organising
# ---------------------------------------------------------------------------


def _entry_organise_by_tag(page: Page, guide: Guide) -> None:
    """I want to view my highlights grouped by tag."""
    with guide.step("I want to view my highlights grouped by tag", level=3) as g:
        g.note(
            "Click the **Organise** tab to see your highlights arranged "
            "in columns by tag. You can drag highlights between columns "
            "to reclassify them."
        )
        page.get_by_test_id("tab-organise").click()
        page.get_by_test_id("organise-columns").wait_for(state="visible", timeout=10000)
        page.wait_for_timeout(1000)
        g.screenshot(
            "Organise tab with highlights grouped by tag",
            highlight=["organise-columns"],
        )
        g.note(
            "See [Student Workflow - Step 7]"
            "(student-workflow.md#step-7-organising-by-tag) "
            "for more details."
        )
        # Switch back to Annotate tab
        page.get_by_test_id("tab-annotate").click()
        page.wait_for_timeout(1000)


# ---------------------------------------------------------------------------
# Responding
# ---------------------------------------------------------------------------


def _entry_write_response(page: Page, guide: Guide) -> None:
    """I want to write a response using my highlights as reference."""
    with guide.step(
        "I want to write a response using my highlights as reference",
        level=3,
    ) as g:
        g.note(
            "Click the **Respond** tab. Your highlights appear in the "
            "reference panel on the right; write your analysis in the "
            "markdown editor on the left."
        )
        page.get_by_test_id("tab-respond").click()
        page.get_by_test_id("milkdown-editor-container").wait_for(
            state="visible", timeout=10000
        )
        g.screenshot(
            "Respond tab with editor and reference panel",
            highlight=["milkdown-editor-container", "respond-reference-panel"],
        )
        g.note(
            "See [Student Workflow - Step 8]"
            "(student-workflow.md#step-8-writing-your-response) "
            "for a detailed walkthrough."
        )
        # Switch back to Annotate tab
        page.get_by_test_id("tab-annotate").click()
        page.wait_for_timeout(1000)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def _entry_export_pdf(page: Page, guide: Guide) -> None:
    """I want to export my work as PDF."""
    with guide.step("I want to export my work as PDF", level=3) as g:
        g.note(
            "On the Annotate tab, click the **Export PDF** button. "
            "The export includes your conversation with highlights, "
            "comments, organised notes, and written response."
        )
        page.get_by_test_id("export-pdf-btn").wait_for(state="visible", timeout=5000)
        g.screenshot(
            "Export PDF button on the annotation page",
            highlight=["export-pdf-btn"],
        )


# ---------------------------------------------------------------------------
# Unit Settings
# ---------------------------------------------------------------------------


def _entry_create_unit(page: Page, base_url: str, guide: Guide) -> None:
    """I want to create a unit and activity."""
    with guide.step("I want to create a unit and activity", level=3) as g:
        g.note(
            "Navigate to **Units** and click **New Unit**. Fill in the "
            "unit code, name, and semester, then add weeks and activities."
        )
        _authenticate(page, base_url, "instructor@uni.edu")
        page.goto(f"{base_url}/courses")
        page.wait_for_timeout(2000)
        g.screenshot("Units page")
        g.note(
            "See [Instructor Setup](instructor-setup.md#step-1-login-and-navigator) "
            "for the full step-by-step guide to creating a unit, adding weeks and "
            "activities, configuring tags, and enrolling students."
        )


def _entry_chip_colours(guide: Guide) -> None:
    """How do I know if I'm in a template or instance?"""
    with guide.step("How do I know if I'm in a template or instance?", level=3) as g:
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
        g.note(
            "The chip is visible at the top of every annotation page. "
            "If you are unsure which workspace you are in, check the chip "
            "colour before making any tag or content changes."
        )


# ---------------------------------------------------------------------------
# Enrolment
# ---------------------------------------------------------------------------


def _entry_enrol_students(page: Page, course_url: str, guide: Guide) -> None:
    """I want to enrol students in my unit."""
    with guide.step("I want to enrol students in my unit", level=3) as g:
        g.note(
            "In Unit Settings, click **Manage Enrolments**. Enter "
            "student email addresses to add them to the unit."
        )
        page.goto(course_url)
        page.get_by_test_id("manage-enrollments-btn").wait_for(
            state="visible", timeout=10000
        )
        g.screenshot(
            "Manage Enrolments button in Unit Settings",
            highlight=["manage-enrollments-btn"],
        )
        g.note(
            "See [Instructor Setup - Step 6]"
            "(instructor-setup.md#step-6-enrolling-students) "
            "for a detailed walkthrough."
        )


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------


def _entry_find_workspace(page: Page, base_url: str, guide: Guide) -> None:
    """I want to find my workspace."""
    with guide.step("I want to find my workspace", level=3) as g:
        g.note(
            "The Navigator is your home page. It shows all your "
            "workspaces organised by unit and activity."
        )
        _authenticate(page, base_url, "student-demo@test.example.edu.au")
        page.goto(base_url)
        page.wait_for_timeout(2000)
        g.screenshot(
            "Navigator showing workspaces",
        )
        g.note(
            "Click on a workspace to open it. Your most recent "
            "workspaces appear at the top."
        )


def _entry_search_workspaces(page: Page, guide: Guide) -> None:
    """I want to search across my workspaces."""
    with guide.step("I want to search across my workspaces", level=3) as g:
        g.note(
            "Use the search bar at the top of the Navigator to find "
            "workspaces by content, tag, or comment text."
        )
        search_input = page.get_by_test_id("navigator-search-input")
        search_input.wait_for(state="visible", timeout=5000)
        g.screenshot(
            "Search bar on the Navigator",
            highlight=["navigator-search-input"],
        )
        g.note(
            "Full-text search looks across your highlights, tags, "
            "comments, and response text."
        )


# ---------------------------------------------------------------------------
# Sharing
# ---------------------------------------------------------------------------


def _entry_share_workspace(page: Page, guide: Guide) -> None:
    """I want to share my workspace with someone."""
    with guide.step("I want to share my workspace with someone", level=3) as g:
        g.note(
            "Open the workspace you want to share. Click the **Share** "
            "button in the toolbar to open the sharing dialog."
        )
        share_btn = page.get_by_test_id("share-button")
        share_btn.wait_for(state="visible", timeout=5000)
        g.screenshot(
            "Share button in the workspace toolbar",
            highlight=["share-button"],
        )
        g.note(
            "Enter the email address of the person you want to share "
            "with. They will see your workspace on their Navigator."
        )


# ---------------------------------------------------------------------------
# File Upload
# ---------------------------------------------------------------------------


def _entry_upload_document(page: Page, guide: Guide) -> None:
    """I want to upload a document instead of pasting."""
    with guide.step("I want to upload a document instead of pasting", level=3) as g:
        g.note(
            "Instead of pasting text, you can upload a PDF or Word "
            "document. Click the **Upload** button next to the paste "
            "editor."
        )
        upload_btn = page.get_by_test_id("add-document-btn")
        upload_btn.wait_for(state="visible", timeout=5000)
        g.screenshot(
            "Upload button for document import",
            highlight=["add-document-btn"],
        )
        g.note(
            "Supported formats: PDF (.pdf) and Word (.docx). "
            "The document is converted to annotatable text automatically."
        )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def run_using_promptgrimoire_guide(page: Page, base_url: str) -> None:
    """Run the Using PromptGrimoire flight-rules guide."""
    course_url = _ensure_prerequisites(page, base_url)

    with Guide("Using PromptGrimoire", GUIDE_OUTPUT_DIR, page) as guide:
        guide.note(
            "Quick answers to common tasks and problems. "
            "Each entry shows you exactly what to click, with screenshots "
            "from the live application."
        )

        guide.section("Getting Started")
        _entry_log_in(page, base_url, guide)
        _entry_no_activities(page, base_url, guide)

        guide.section("Workspaces")
        _entry_create_workspace(page, base_url, guide)
        _entry_tags_not_visible(page, course_url, guide)
        _entry_start_vs_template(page, base_url, guide)

        guide.section("Tags")
        _entry_create_tag_group(page, course_url, guide)
        _entry_import_tags(guide)

        guide.section("Annotating")
        _entry_highlight_text(page, base_url, guide)
        _entry_add_comment(page, guide)

        guide.section("Organising")
        _entry_organise_by_tag(page, guide)

        guide.section("Responding")
        _entry_write_response(page, guide)

        guide.section("Export")
        _entry_export_pdf(page, guide)

        guide.section("Unit Settings")
        _entry_create_unit(page, base_url, guide)
        _entry_chip_colours(guide)

        guide.section("Enrolment")
        _entry_enrol_students(page, course_url, guide)

        guide.section("Navigation")
        _entry_find_workspace(page, base_url, guide)
        _entry_search_workspaces(page, guide)

        guide.section("Sharing")
        _entry_share_workspace(page, guide)

        guide.section("File Upload")
        _entry_upload_document(page, guide)
