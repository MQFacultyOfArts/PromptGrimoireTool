"""Using PromptGrimoire flight-rules guide.

Generates a single-page reference document organised by feature domain.
Each entry answers a first-person question ("I want to..." or "Why is...?")
with screenshots captured from a live application instance.

Requires data state from instructor + student guides (UNIT1234, activity,
workspace, tags). Runs after all sequential guides in the build pipeline.
"""

from __future__ import annotations

import contextlib
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page  # annotation-only; safe with PEP 563

from promptgrimoire.docs import Guide
from promptgrimoire.docs.helpers import wait_for_text_walker
from promptgrimoire.docs.seed import seed_user_and_enrol

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
    seed_user_and_enrol("instructor@uni.edu", "Instructor")


# ---------------------------------------------------------------------------
# Prerequisite validation
# ---------------------------------------------------------------------------


def _ensure_prerequisites(page: Page, base_url: str) -> str:
    """Ensure UNIT1234 exists and return the course detail URL.

    Authenticates as the instructor, checks the Navigator for UNIT1234.
    If missing, runs the instructor guide to create it. Returns the
    course URL for entries that need Unit Settings navigation.
    """
    _authenticate(page, base_url, "instructor@uni.edu")

    # Enrol the instructor BEFORE checking /courses — the courses page
    # filters by enrollment, so without enrollment UNIT1234 won't appear.
    # Suppress RuntimeError if course doesn't exist yet (first run).
    with contextlib.suppress(RuntimeError):
        _enrol_instructor()

    page.goto(f"{base_url}/courses")
    # Courses page renders ui.card() with ui.label(), not <a> tags.
    unit_card = page.locator('[data-testid^="course-card-"]', has_text="UNIT1234").first
    unit_visible = unit_card.count() > 0

    if not unit_visible:
        from promptgrimoire.docs.scripts.instructor_setup import (  # noqa: PLC0415
            run_instructor_guide,
        )

        run_instructor_guide(page, base_url)
        _authenticate(page, base_url, "instructor@uni.edu")
        page.goto(f"{base_url}/courses")
        unit_card = page.locator(
            '[data-testid^="course-card-"]', has_text="UNIT1234"
        ).first

    unit_card.wait_for(state="visible", timeout=10000)
    unit_card.click()
    page.wait_for_url(re.compile(r"/courses/[0-9a-f-]+"), timeout=10000)
    return page.url


# ---------------------------------------------------------------------------
# Getting Started
# ---------------------------------------------------------------------------


def _entry_log_in(guide: Guide) -> None:
    """I want to log in for the first time."""
    with guide.step(
        "I want to log in for the first time", level=3, text_only=True
    ) as g:
        g.note(
            "Navigate to the application URL. The production login page offers "
            "AAF SSO as the primary login method, with Google, GitHub, and magic "
            "link as alternatives. Use whichever method your institution supports."
        )
        g.note(
            "For magic link login, enter your university email address and click "
            "**Send Magic Link**. Check your inbox for the login link."
        )
        g.note(
            "See [Student Workflow - Step 1](student-workflow.md#step-1-logging-in) "
            "for a step-by-step walkthrough."
        )


def _entry_no_activities(guide: Guide) -> None:
    """I don't see any activities after logging in."""
    with guide.step(
        "I don't see any activities after logging in", level=3, text_only=True
    ) as g:
        g.note(
            "**Diagnosis:** You are not enrolled in any units, or the "
            "instructor has not yet published any weeks with activities."
        )
        g.note(
            "**Fix:** Check with your instructor that you are enrolled "
            "in the correct unit and semester. The instructor can verify "
            "your enrolment in Unit Settings."
        )
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
        # Use a fresh student who hasn't started any activities yet —
        # student-demo already created a workspace in the student guide.
        seed_user_and_enrol("fresh-student@test.example.edu.au", "Fresh Student")
        _authenticate(page, base_url, "fresh-student@test.example.edu.au")
        page.locator('[data-testid^="start-activity-btn"]').first.wait_for(
            state="visible", timeout=10000
        )
        g.screenshot(
            "Navigator showing Start button for the activity",
            highlight=["start-activity-btn"],
        )
        g.note(
            "Your workspace inherits the tag configuration set by your "
            "instructor. You can start annotating immediately -- "
            "assuming the instructor has added content to the template. "
            "If the template has no documents, you will see a content "
            "form to paste or upload your own text first."
        )
        g.note(
            "See [Student Workflow - Step 3]"
            "(student-workflow.md#step-3-creating-a-workspace) "
            "for the full walkthrough."
        )


def _entry_tags_not_visible(
    page: Page, base_url: str, course_url: str, guide: Guide
) -> None:
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
        _authenticate(page, base_url, "instructor@uni.edu")
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
        # Students already cloned the template, so a warning dialog appears.
        continue_btn = page.get_by_test_id("template-clone-warning-continue-btn")
        continue_btn.wait_for(state="visible", timeout=5000)
        continue_btn.click()
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
    with guide.step(
        "Tag import from another activity shows nothing", level=3, text_only=True
    ) as g:
        g.note(
            "**Diagnosis:** The tag import dropdown lists any workspace "
            "you can read that contains tags. If no workspaces with tags "
            "appear, either no readable workspace has tags configured, or "
            "you configured tags in your own workspace instead of the template."
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
        # Navigate to existing student workspace — student-demo already
        # created a workspace in the student guide, so open it via Navigator.
        _authenticate(page, base_url, "student-demo@test.example.edu.au")
        page.goto(base_url)
        page.locator('[data-testid^="open-workspace-btn-"]').first.wait_for(
            state="visible", timeout=10000
        )
        page.locator('[data-testid^="open-workspace-btn-"]').first.click()

        wait_for_text_walker(page, timeout=15000)

        g.screenshot(
            "Tag toolbar appearing after text selection",
            highlight=["tag-toolbar"],
        )
        g.note(
            "See [Student Workflow - Step 4]"
            "(student-workflow.md#step-4-annotating---creating-a-highlight) "
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
        # Expand card detail to reveal comment input
        card.get_by_test_id("card-expand-btn").click()
        card.get_by_test_id("card-detail").wait_for(state="visible", timeout=5000)
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
            "(student-workflow.md#step-5-adding-a-comment) "
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
            "(student-workflow.md#step-6-organising-by-tag) "
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
            "reference panel on the left; write your analysis in the "
            "markdown editor on the right."
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
            "(student-workflow.md#step-7-writing-your-response) "
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
            "A progress indicator shows the export status "
            '("Export queued…" → "Compiling PDF…"). '
            "When compilation finishes, a **Download your PDF** button appears. "
            "Click it to download your PDF.\n\n"
            "You can close or reload the page while the PDF is compiling — "
            "the download button will appear when you return. "
            "The download link is available for 24 hours."
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
    with guide.step(
        "How do I know if I'm in a template or instance?", level=3, text_only=True
    ) as g:
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
            "On the unit detail page, click **Manage Enrollments**. "
            "This opens a separate enrolment page where you can enter "
            "student email addresses individually, or upload a bulk "
            "XLSX spreadsheet to add many students at once."
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


def _entry_after_enrolment(page: Page, base_url: str, guide: Guide) -> None:
    """I've enrolled students. What happens next?"""
    with guide.step("I've enrolled students. What happens next?", level=3) as g:
        g.note(
            "Once students are enrolled, they log in and see the "
            "Navigator -- their home page. Any **published** activities "
            "in the unit appear automatically with a **Start** button."
        )
        _authenticate(page, base_url, "student-demo@test.example.edu.au")
        page.locator(
            '[data-testid^="start-activity-btn"],[data-testid^="open-workspace-btn-"]'
        ).first.wait_for(state="visible", timeout=10000)
        g.screenshot(
            "Student Navigator showing enrolled unit and activities",
        )
        g.note(
            "When a student clicks **Start**, the application clones "
            "your template workspace -- they get their own copy with "
            "the content and tag configuration you set up. Students "
            "cannot see or modify the template itself."
        )
        g.note(
            "**What to check before telling students to log in:**\n\n"
            "1. The week containing the activity is **published** "
            "(unpublished weeks are invisible to students)\n"
            "2. The template workspace has **content** added "
            "(otherwise students get an empty workspace)\n"
            "3. **Tags** are configured on the template "
            "(students inherit the tag vocabulary)"
        )


def _entry_clean_up_test_activities(guide: Guide) -> None:
    """How do I clean up my test activities?"""
    with guide.step(
        "How do I clean up my test activities?", level=3, text_only=True
    ) as g:
        g.note(
            "While learning the system you may have created test "
            "activities or clicked **Start** on your own activities. "
            "Now you want to tidy up, but the delete button says "
            "workspaces exist."
        )
        g.note(
            "**Why this happens:** Clicking **Start** on an activity "
            "creates a student workspace (a clone of the template). "
            "Even though you are the instructor, the system treats "
            "this as a student workspace -- and activities cannot be "
            "deleted while student workspaces exist."
        )
        g.note(
            "**How to clean up:**\n\n"
            "1. **Delete student workspaces first.** On the Navigator, "
            "find the workspace you created by clicking Start. Click "
            "the trash icon on the workspace card to delete it.\n"
            "2. **Then delete the activity, week, or unit directly.** "
            "Once no student workspaces remain, you can delete at any "
            "level -- deleting a week cascades to its activities, and "
            "deleting a unit cascades to its weeks and activities."
        )
        g.note(
            "The rule is: **student workspaces block deletion** at every "
            "level (activity, week, and unit). You must clear them first. "
            "But the structural entities themselves cascade automatically "
            "-- you do not need to delete activities before weeks, or "
            "weeks before units."
        )
        g.note(
            "**Admin shortcut:** Admin users have a **force-delete** "
            "option that purges student workspaces and cascades "
            "automatically -- no need to manually delete workspaces first."
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
            highlight=["open-workspace-btn"],
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
        # Navigate from Navigator into an existing workspace.
        page.locator('[data-testid^="open-workspace-btn-"]').first.wait_for(
            state="visible", timeout=10000
        )
        page.locator('[data-testid^="open-workspace-btn-"]').first.click()
        wait_for_text_walker(page, timeout=15000)
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
        g.note(
            "**Note:** The Share button is only visible to workspace "
            "owners and privileged users (instructors and admins). "
            "Sharing by email only works for users who already have "
            "an account -- the system cannot send invitations to "
            "addresses with no existing account."
        )


# ---------------------------------------------------------------------------
# File Upload
# ---------------------------------------------------------------------------


def _entry_upload_document(guide: Guide) -> None:
    """I want to upload a document instead of pasting."""
    with guide.step(
        "I want to upload a document instead of pasting", level=3, text_only=True
    ) as g:
        g.note(
            "When you first open a workspace that has no content yet, "
            "you see the content form. Below the paste editor there is "
            "an **Upload** button for importing files directly."
        )
        g.note(
            "Supported formats: PDF (.pdf), Word (.docx), Markdown (.md), "
            "HTML, and plain text. The document is converted to annotatable "
            "text automatically."
        )
        g.note(
            "The upload option appears on the initial content form when a "
            "workspace has no documents. It also reappears as **Add Document** "
            "when multi-document mode is enabled for the activity."
        )


def _entry_paste_sources(guide: Guide) -> None:
    """What AI platforms can I paste conversations from?"""
    with guide.step(
        "What AI platforms can I paste conversations from?", level=3, text_only=True
    ) as g:
        g.note(
            "PromptGrimoire automatically detects the source platform when you "
            "paste a conversation and strips the native UI chrome (buttons, labels, "
            "avatars). Speaker turns are re-labelled with uniform **User:** and "
            "**Assistant:** markers so you can annotate consistently regardless "
            "of where the conversation came from."
        )
        g.note(
            "**Supported platforms (auto-detected):**\n\n"
            "- **ChatGPT** (OpenAI) -- copy the conversation page in your browser\n"
            "- **Claude** (Anthropic) -- copy the conversation page in your browser\n"
            "- **Gemini** (Google) -- copy the conversation page in your browser\n"
            "- **AI Studio** (Google) -- copy the conversation page in your browser\n"
            "- **OpenRouter** -- copy the conversation page in your browser\n"
            "- **ChatCraft** -- copy the conversation page in your browser\n"
            "- **ScienceOS** -- copy the conversation page in your browser\n"
            "- **Wikimedia** -- copy the conversation page in your browser\n"
            "- **Plain text** -- any platform not listed above; paste as-is"
        )
        g.note(
            "**How to paste:** Open your workspace, click into the content area, "
            "and paste (Ctrl+V / Cmd+V). The pipeline detects the format from "
            "the clipboard structure -- HTML with recognisable platform markers "
            "is preprocessed automatically; plain text is wrapped in paragraphs."
        )
        g.note(
            "**File upload alternative:** PDF (.pdf) and Word (.docx) files "
            "can be uploaded directly using the **Upload** button on the "
            "initial content form. The document is converted to annotatable "
            "HTML automatically. See [I want to upload a document instead "
            "of pasting]"
            "(#i-want-to-upload-a-document-instead-of-pasting) for details."
        )
        g.note(
            "**If your platform is not listed:** paste as plain text. The content "
            "will be imported without automatic speaker labelling. You can still "
            "annotate all the text; you will just need to identify turns manually."
        )


# ---------------------------------------------------------------------------
# Word Count
# ---------------------------------------------------------------------------


def _entry_word_count(guide: Guide) -> None:
    """Why does my response show a word count, and what do the colours mean?"""
    with guide.step(
        "Why does my response show a word count, and what do the colours mean?",
        level=3,
        text_only=True,
    ) as g:
        g.note(
            "When an instructor has configured word limits for an activity, a "
            "**word count badge** appears in the annotation page header while "
            "you write your response on the **Respond** tab. The badge shows "
            "your current count and, if a limit is set, the target."
        )
        g.note(
            "**Badge colours:**\n\n"
            "- **Grey** -- within acceptable range\n"
            "- **Amber** -- approaching the limit (within 10%)\n"
            "- **Red** -- over the word limit, or below the word minimum"
        )
        g.note(
            "Word counting uses multilingual tokenisation: Latin and Korean text "
            "use Unicode word-break rules (UAX #29), Chinese uses dictionary-based "
            "segmentation (jieba), and Japanese uses morphological analysis (MeCab). "
            "Zero-width characters and markdown link URLs are stripped before counting "
            "to prevent gaming the count."
        )
        g.note(
            "**On PDF export:** if your response violates the word limit or falls "
            "below the minimum, a red violation badge is prepended to your exported "
            "PDF showing the current count and the configured threshold. If you are "
            "within limits, a neutral italic line shows the count instead. "
            "If no limits are configured, no badge appears."
        )
        g.note(
            "Word limits are set by your instructor in the activity template. "
            "Contact your instructor if you believe the limit is incorrect or "
            "if you need an extension."
        )


# ---------------------------------------------------------------------------
# Activities and Templates
# ---------------------------------------------------------------------------


def _entry_student_uploads(guide: Guide) -> None:
    """How do I get students to upload their own documents?"""
    with guide.step(
        "How do I get students to upload their own documents?",
        level=3,
        text_only=True,
    ) as g:
        g.note("There are two approaches, depending on how much control you need.")
        g.note(
            "**Path A -- Empty activity template.** Create an activity but "
            "do not upload a document to the template. When students click "
            "**Start**, they get a blank workspace with the upload form. "
            "You still control the tag set and other activity policies "
            "(word limits, sharing) via the template."
        )
        g.note(
            "If you want students to upload and annotate multiple sources, "
            "create one activity per source (e.g. *Source 1*, *Source 2*, "
            "*Source 3*). Each activity can have its own tag set. Students "
            "upload one document into each."
        )
        g.note(
            "**Path B -- Personal workspace with placement.** Students "
            "create their own workspace from the Navigator and upload "
            "whatever they like. They then use the **placement chip** in "
            "the workspace header to attach it to a unit, week, and "
            "activity. This is fully student-driven -- no tag constraints "
            "from the activity template."
        )
        g.note(
            "See [Your Personal Grimoire - Connect to Your Unit]"
            "(your-personal-grimoire.md#connect-to-your-unit) "
            "for a walkthrough of the placement chip."
        )
        g.note(
            "**Which to choose:** Path A when you want consistent tagging "
            "across the cohort. Path B when students are choosing their own "
            "source material and you want maximum flexibility."
        )
        g.note(
            "**Note on copy protection:** copy protection prevents students "
            "from copying text out of their workspace. This is useful when "
            "the source document is instructor-provided, but has no practical "
            "purpose when students uploaded the document themselves -- they "
            "already have the original."
        )


# ---------------------------------------------------------------------------
# Copy Protection
# ---------------------------------------------------------------------------


def _entry_copy_protection(guide: Guide) -> None:
    """Why can't I select or copy text from my workspace?"""
    with guide.step(
        "Why can't I select or copy text from my workspace?", level=3, text_only=True
    ) as g:
        g.note(
            "Your instructor has enabled **copy protection** on this activity. "
            "When active, the application intercepts copy, cut, right-click "
            "(context menu), drag, and print actions on the conversation text. "
            "A toast notification appears to explain why the action was blocked. "
            "An amber **Protected** chip is visible in the workspace header."
        )
        g.note(
            "Copy protection also suppresses the browser print dialog "
            "(Ctrl+P / Cmd+P). If you need a printable copy of your work, "
            "use the **Export PDF** button instead -- the PDF is not affected "
            "by copy protection."
        )
        g.note(
            "**Who bypasses copy protection:** instructors, coordinators, and "
            "system administrators are not subject to copy protection. "
            "The restriction applies only to students. If you are an instructor "
            "and see the Protected chip, check that your account has the correct "
            "role assigned in the authentication system."
        )
        g.note(
            "**Turning copy protection on or off (instructors):** go to "
            "**Unit Settings** and open the unit settings dialog to toggle the "
            "default for the whole unit. Individual activities can override the "
            "unit default: in the activity row, use the per-activity "
            "copy protection selector -- **Inherit from unit**, **On**, or **Off**."
        )


# ---------------------------------------------------------------------------
# Collaboration
# ---------------------------------------------------------------------------


def _entry_peer_viewing(guide: Guide) -> None:
    """How do other students view my workspace?"""
    with guide.step(
        "How do other students view my workspace?", level=3, text_only=True
    ) as g:
        g.note("There are two ways a classmate can see your workspace:")
        g.note(
            "**1. Share with class toggle.** If your instructor has enabled "
            "peer sharing for the activity, a **Share with class** toggle "
            "appears in your workspace toolbar. Switching it on lets every "
            "enrolled student in the unit view your workspace. They get "
            "**peer** access -- read-only. They can see your highlights, "
            "comments, tags, and response, but cannot change anything."
        )
        g.note(
            "**2. Share by email.** The workspace owner (and instructors) "
            "can click **Share** in the toolbar to open the sharing dialog. "
            "Enter a classmate's email address and choose **Viewer** or "
            "**Editor** permission. Viewer is read-only; Editor allows them "
            "to add highlights and comments alongside you."
        )
        g.note(
            "**What peer access means:** A student with peer access sees "
            "your workspace on their Navigator. They can read everything in "
            "it, but the workspace remains yours -- they cannot delete "
            "highlights, change tags, or modify your response."
        )
        g.note(
            "**If the toggle is missing:** The instructor has not enabled "
            "peer sharing for the activity. Contact your instructor to ask "
            "them to turn on sharing in the activity settings."
        )


def _entry_collaboration(guide: Guide) -> None:
    """Can multiple people work in the same workspace at the same time?"""
    with guide.step(
        "Can multiple people work in the same workspace at the same time?",
        level=3,
        text_only=True,
    ) as g:
        g.note(
            "Yes. PromptGrimoire uses **CRDT** (Conflict-free Replicated "
            "Data Type) synchronisation, so multiple people can be in the "
            "same workspace simultaneously without overwriting each other's "
            "work. Changes merge automatically -- no locking, no "
            '"someone else is editing" warnings.'
        )
        g.note(
            "**What syncs in real time:**\n\n"
            "- Highlights (creating, deleting, moving between tags)\n"
            "- Comments on highlights\n"
            "- Tags and tag groups\n"
            "- General notes\n"
            "- Response draft (the markdown editor on the Respond tab)"
        )
        g.note(
            "**Who is connected?** The toolbar shows a small badge -- "
            "for example **2 users** -- counting everyone currently "
            "viewing the workspace. Each connected user is assigned a "
            "distinct colour for their cursor and presence indicator."
        )
        g.note(
            "**Common use case:** An instructor opens a student's workspace "
            "to leave comments at the same time the student is working. "
            "Both see each other's changes appear within seconds."
        )
        g.note(
            "**Note:** Real-time sync requires an active connection. If you "
            "lose connectivity, your changes are queued locally and sync "
            "when the connection is restored. Work is never lost."
        )


# ---------------------------------------------------------------------------
# Additional Enrolment
# ---------------------------------------------------------------------------


def _entry_bulk_enrolment(guide: Guide) -> None:
    """I want to enrol a whole cohort at once from Moodle."""
    with guide.step(
        "I want to enrol a whole cohort at once from Moodle", level=3, text_only=True
    ) as g:
        g.note(
            "In **Manage Enrolments**, scroll past the single-email form to "
            "the **Bulk Enrol Students** section. Click the upload area and "
            "select your XLSX file."
        )
        g.note(
            "**Where to get the file:** Export your class list from Moodle using "
            "**Gradebook -> Export -> Excel spreadsheet**. The parser expects these "
            "columns (case-insensitive): **First name**, **Last name**, "
            "**ID number**, and **Email address**. An optional **Groups** column "
            "is supported -- values like `[Tutorial 1], [Lab A]` are parsed "
            "automatically. Extra columns are ignored."
        )
        g.note(
            "After upload, a notification reports how many students were enrolled "
            "and how many were skipped because they were already in the unit."
        )
        g.note(
            "**Student ID conflicts:** If a student's Moodle ID number differs "
            "from the one already stored (e.g., a re-enrolment with a corrected "
            "ID), the upload stops and lists the conflicts. Tick "
            "**Override student ID conflicts** before uploading to force the "
            "new ID to win."
        )
        g.note(
            "If the file fails validation, the upload reports every error before "
            "stopping -- for example, invalid email addresses or duplicate rows. "
            "Fix the XLSX and re-upload; the widget resets automatically."
        )


def _entry_enrolment_invitations(guide: Guide) -> None:
    """I enrolled a student but they don't have an account yet."""
    with guide.step(
        "I enrolled a student but they don't have an account yet",
        level=3,
        text_only=True,
    ) as g:
        g.note(
            "You can enrol any email address even if the person has never logged "
            "in. When you click **Add** with an unknown email, the system creates "
            "a placeholder account in the local database and shows "
            '**"Enrollment added (new user created)"**.'
        )
        g.note(
            "The student does **not** receive any automatic notification. Tell "
            "them the application URL and ask them to log in. When they "
            "authenticate for the first time -- via AAF, Google, GitHub, or magic "
            "link -- their session is matched to the placeholder by email address "
            "and the enrolment activates immediately."
        )
        g.note(
            "Until the student logs in, their name in the enrolment list is "
            "derived from the email prefix (e.g. `jsmith` from `jsmith@uni.edu`). "
            "It updates to their real display name on first login."
        )
        g.note(
            "**Bulk upload:** The same behaviour applies to the XLSX bulk upload -- "
            "students who have never logged in receive placeholder accounts. "
            "There is no separate invitation step required."
        )


def _entry_sso_login(guide: Guide) -> None:
    """How do I log in with my university (AAF) credentials?"""
    with guide.step(
        "How do I log in with my university (AAF) credentials?",
        level=3,
        text_only=True,
    ) as g:
        g.note(
            "Click **Login with AAF** on the login page. You will be redirected "
            "to the Australian Access Federation (AAF) identity hub, where you "
            "select your institution and authenticate with your usual university "
            "username and password. After a successful login you are returned to "
            "PromptGrimoire automatically."
        )
        g.note(
            "**AAF is the recommended login method in production.** It uses "
            "your institution's own identity provider (SAML 2.0) so no separate "
            "PromptGrimoire password is required. Roles (e.g. `instructor`) are "
            "derived from the SAML attributes passed by your institution."
        )
        g.note("**Alternative methods** are available if AAF is not available to you:")
        g.note(
            "- **Google or GitHub** -- OAuth login, available on the same login page.\n"
            "- **Magic link** -- enter your Macquarie University email "
            "(`@mq.edu.au` or `@students.mq.edu.au`) and a one-time login link "
            "will be sent to your inbox. Magic links are restricted to MQ email "
            "domains."
        )
        g.note(
            'If you see **"SSO not configured"**, contact your system '
            "administrator -- the AAF connection ID has not been set up in the "
            "deployment environment."
        )


# ---------------------------------------------------------------------------
# Additional Unit Settings
# ---------------------------------------------------------------------------


def _entry_rename_entities(guide: Guide) -> None:
    """I want to rename a week, activity, or unit."""
    with guide.step(
        "I want to rename a week, activity, or unit", level=3, text_only=True
    ) as g:
        g.note(
            "**Renaming a week:** In Unit Settings, click the **Edit** "
            "button next to the week heading. A dialog opens where you "
            "can update the week number and title. Click **Save** to apply."
        )
        g.note(
            "**Renaming an activity:** In Unit Settings, click the **Edit** "
            "button next to the activity. A dialog opens where you can update "
            "the activity title and description. Click **Save** to apply."
        )
        g.note(
            "**Unit code and name:** The unit code and name are set when the "
            "unit is first created and cannot be changed through the UI. "
            "**Unit Settings** (the gear icon) only offers default policy "
            "toggles -- copy protection, sharing, and word count enforcement. "
            "If the code or name must change, an administrator can update it "
            "via the database."
        )
        g.note(
            "**Edit buttons are only visible to instructors** with manage "
            "permission on the unit. Students do not see Edit buttons."
        )


def _entry_students_no_work(
    page: Page, base_url: str, course_url: str, guide: Guide
) -> None:
    """What does 'Students with no work' mean?"""
    with guide.step("What does 'Students with no work' mean?", level=3) as g:
        g.note(
            "On the Unit Settings page, an expandable panel labelled "
            "**Students with no work (N)** lists enrolled students who "
            "have not yet clicked **Start** on any activity in the unit. "
            "The number in parentheses is the count of those students."
        )
        _authenticate(page, base_url, "instructor@uni.edu")
        page.goto(course_url)
        page.get_by_test_id("students-no-work").wait_for(state="visible", timeout=10000)
        g.screenshot(
            "Students with no work expansion on Unit Settings",
            highlight=["students-no-work"],
        )
        g.note(
            "**This does not mean anything is wrong.** It simply means "
            "those students have not started a workspace yet. Once you "
            "**publish** a week containing activities, students can see "
            "the activities on their Navigator and click **Start** to "
            "create their own workspace."
        )
        g.note(
            "See [I want to make my activity visible to students]"
            "(#i-want-to-make-my-activity-visible-to-students) "
            "for how to publish."
        )


def _entry_publish_activity(guide: Guide) -> None:
    """I want to make my activity visible to students."""
    with guide.step(
        "I want to make my activity visible to students", level=3, text_only=True
    ) as g:
        g.note(
            "Activities live inside **weeks**, and weeks have a "
            "**Published** / **Draft** status. Students can only see "
            "activities in published weeks -- draft weeks are invisible "
            "to them."
        )
        g.note(
            "To publish: go to **Unit Settings**, find the week "
            "containing your activity, and click the **Publish** button "
            "next to the week heading. The status changes to "
            "**Published** and the activities in that week immediately "
            "appear on every enrolled student's Navigator with a "
            "**Start** button."
        )
        g.note(
            "**Before publishing, check that:**\n\n"
            "1. The template workspace has **content** added "
            "(otherwise students get an empty workspace)\n"
            "2. **Tags** are configured on the template "
            "(students inherit the tag vocabulary)\n"
            "3. Students are **enrolled** in the unit"
        )
        g.note(
            "See [I've enrolled students. What happens next?]"
            "(#ive-enrolled-students-what-happens-next) "
            "for what students see after publishing."
        )


def _entry_pdf_filename(guide: Guide) -> None:
    """What will my exported PDF be named?"""
    with guide.step(
        "What will my exported PDF be named?", level=3, text_only=True
    ) as g:
        g.note(
            "The PDF filename is assembled automatically from your "
            "workspace metadata in this order:\n\n"
            "``{UnitCode}_{LastName}_{FirstName}_{ActivityTitle}"
            "_{WorkspaceTitle}_{YYYYMMDD}.pdf``"
        )
        g.note(
            "**How each segment is derived:**\n\n"
            "- **Unit code** -- the code set when the unit was created "
            "(e.g. ``LAWS1100``)\n"
            "- **Last name / First name** -- taken from your display name; "
            "the system uses the last token as surname and the first token "
            "as given name\n"
            "- **Activity title** -- the title of the activity your workspace "
            "belongs to\n"
            "- **Workspace title** -- your workspace's title; omitted when "
            "it is the same as the activity title (the default for cloned "
            "workspaces)\n"
            "- **Date** -- the server's local date at export time, formatted "
            "``YYYYMMDD``"
        )
        g.note(
            "All segments are made filesystem-safe: special characters and "
            "spaces are replaced with underscores, and non-ASCII characters "
            "are transliterated. The total filename is capped at 100 "
            "characters; if it is too long, the workspace title is trimmed "
            "first, then the activity title, and finally the given name is "
            "reduced to an initial."
        )
        g.note(
            "**Fallbacks when metadata is missing:** ``Unplaced`` (no unit), "
            "``Loose_Work`` (no activity), ``Workspace`` (no workspace title), "
            "``Unknown_Unknown`` (no display name)."
        )
        g.note(
            "To influence the filename, rename your workspace title before "
            "exporting -- the new title will appear as the "
            "workspace segment."
        )


def _entry_paragraph_numbers_export(guide: Guide) -> None:
    """How do paragraph numbers appear in PDF export?"""
    with guide.step(
        "How do paragraph numbers appear in PDF export?",
        level=3,
        text_only=True,
    ) as g:
        g.note(
            "When a workspace uses auto-numbering, the exported PDF "
            "shows small grey paragraph numbers in the left margin. "
            "These match the on-screen paragraph numbers. "
            "Source-number mode documents (e.g. AustLII judgments) "
            "already display numbers as list items, so no margin "
            "numbers are added.\n\n"
            "Verified by ``test_paragraph_markers.py`` (marker "
            "injection) and ``test_paranumber_latex.py`` (LaTeX "
            "rendering)."
        )
        g.note(
            "**Endnote cross-references:** Long annotations that "
            "overflow into the endnotes section have clickable "
            "links. Click the superscript number in the body text "
            "to jump to the corresponding endnote. Click the number "
            "in the endnote to jump back to the body location.\n\n"
            "Verified by ``test_endnote_crossref.py``."
        )


# ---------------------------------------------------------------------------
# Additional Annotating
# ---------------------------------------------------------------------------


def _entry_overlapping_highlights(guide: Guide) -> None:
    """Can I apply two different tags to the same text?"""
    with guide.step(
        "Can I apply two different tags to the same text?", level=3, text_only=True
    ) as g:
        g.note(
            "Yes. Overlapping highlights are fully supported. You can select a "
            "passage and apply multiple tags -- the highlighted regions can overlap "
            "partially or completely."
        )
        g.note(
            "**How they display in the browser:** each tag has its own "
            "semi-transparent highlight colour (using the browser's CSS Custom "
            "Highlight API). Where two highlights overlap, both transparent colours "
            "layer on top of each other, producing a blended shade. An underline "
            "in the tag colour is also applied, so you can distinguish tags even "
            "where the background blending is subtle."
        )
        g.note(
            "**How they display in PDF export:** the export pipeline uses an "
            "event-sweep algorithm to split the document into non-overlapping "
            "character regions, then renders each region with all active highlight "
            "colours blended. Regions covered by three or more overlapping highlights "
            "receive a dark neutral colour (#333333) to remain legible. "
            "Annotation markers (numbered superscripts) are placed at the end "
            "of each highlight."
        )
        g.note(
            "**Practical advice:** overlapping highlights are useful when a single "
            "passage is relevant to more than one analytical category. If you find "
            "yourself applying every tag to every turn, consider whether your tag "
            "vocabulary needs refinement."
        )


# ---------------------------------------------------------------------------
# Additional Organising
# ---------------------------------------------------------------------------


def _entry_locate_button(guide: Guide) -> None:
    """What does the Locate button do on the Organise tab?"""
    with guide.step(
        "What does the Locate button do on the Organise tab?",
        level=3,
        text_only=True,
    ) as g:
        g.note(
            "Each highlight card on the **Organise** tab and the reference "
            "panel on the **Respond** tab has a small map-pin icon button "
            "(tooltip: **Locate in document**)."
        )
        g.note(
            "Clicking **Locate** does two things:\n\n"
            "1. **Switches you to the Annotate tab** -- the tab containing "
            "the source document\n"
            "2. **Scrolls to the highlight** in the document and briefly "
            "flashes it gold so you can find it instantly"
        )
        g.note(
            "This is useful when you are on the Organise or Respond tab "
            "and want to re-read the surrounding context for a highlight "
            "without manually hunting for it in the document."
        )
        g.note(
            "Locate is per-client only -- it navigates your own view and "
            "does not affect other users who are in the same workspace."
        )


def _entry_view_student_work(guide: Guide) -> None:
    """How can I see the work students did for my activity?"""
    with guide.step(
        "How can I see the work students did for my activity?",
        level=3,
        text_only=True,
    ) as g:
        g.note(
            "As an instructor, student workspaces appear on your "
            "**Navigator** (the home page) under a **Shared in Unit** "
            "section grouped by unit. You do not need students to "
            "explicitly share their work -- the system shows all "
            "student workspaces in units where you are enrolled as "
            "an instructor."
        )
        g.note(
            "**Path 1 -- Scroll the Navigator.** Go to Home and scroll "
            "down past your own workspaces. Student workspaces appear "
            "grouped under the unit name."
        )
        g.note(
            "**Path 2 -- Search.** Type the unit code (e.g. ``EDST4``) "
            "into the search bar at the top of the Navigator. This "
            "filters to everything in that unit -- your workspaces and "
            "all student workspaces."
        )
        g.note(
            "**Important: your account must have the instructor role.** "
            "The Navigator only shows all student workspaces if the "
            "system recognises you as a privileged user (instructor or "
            "admin). If you are teaching a unit but your account does "
            "not have the instructor role assigned, you will only see "
            "workspaces that students have explicitly shared. Ask your "
            "system administrator to verify your role is set correctly "
            "in the authentication system."
        )
        g.note(
            "**Common mistake: checking the Unit Settings page.** "
            "The Unit Settings page (``/courses/...``) only shows "
            "workspaces that students have explicitly toggled "
            "**Share with class**. Most students will not have done "
            "this. The Navigator is the correct place to see all "
            "student work."
        )
        g.note(
            "**If you see no student workspaces at all:**\n\n"
            "1. Check that your account has the **instructor role** -- "
            "without it, the system treats you as a regular user\n"
            "2. Check **Students with no work** in Unit Settings -- "
            "if all students are listed there, none have clicked "
            "**Start** yet\n"
            "3. Confirm the week is **published** -- students cannot "
            "see activities in draft weeks\n"
            "4. Confirm students are **enrolled** -- unenrolled "
            "students cannot see the unit"
        )
        g.note(
            "See [I want to find my workspace]"
            "(#i-want-to-find-my-workspace) for a screenshot of the "
            "Navigator, and [What does 'Students with no work' mean?]"
            "(#what-does-students-with-no-work-mean) for the "
            "diagnostic panel."
        )


def _entry_drag_organise(guide: Guide) -> None:
    """I want to reorder or reclassify highlights on the Organise tab."""
    with guide.step(
        "I want to reorder or reclassify highlights on the Organise tab",
        level=3,
        text_only=True,
    ) as g:
        g.note(
            "On the **Organise** tab, highlight cards are draggable. "
            "Grab a card by clicking and holding, then drag it to its "
            "new position."
        )
        g.note(
            "**Drag within a column** to reorder highlights under the "
            "same tag. The new order is saved and will persist across "
            "sessions and for collaborators in the same workspace."
        )
        g.note(
            "**Drag between columns** to reassign a highlight to a "
            "different tag. The card moves to the target column and the "
            "highlight's tag is updated in the shared document."
        )
        g.note(
            "All drag operations sync live to every connected client "
            "via the shared CRDT document -- collaborators see the "
            "updated order and tag assignments immediately without "
            "needing to reload."
        )
        g.note(
            "If you need to scroll the Organise tab horizontally to "
            "reach a column that is off-screen, scroll the row of "
            "columns first, then drag. The columns scroll independently "
            "of the page."
        )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def _run_screenshot_sections(
    page: Page,
    base_url: str,
    course_url: str,
    guide: Guide,
) -> None:
    """Sections that drive the live browser for screenshots."""
    guide.section("Getting Started")
    _entry_log_in(guide)
    _entry_sso_login(guide)
    _entry_no_activities(guide)

    guide.section("Workspaces")
    _entry_create_workspace(page, base_url, guide)
    _entry_start_vs_template(page, base_url, guide)

    guide.section("Tags")
    _entry_create_tag_group(page, course_url, guide)
    _entry_import_tags(guide)

    guide.section("Annotating")
    _entry_highlight_text(page, base_url, guide)
    _entry_add_comment(page, guide)
    _entry_overlapping_highlights(guide)

    guide.section("Organising")
    _entry_organise_by_tag(page, guide)
    _entry_locate_button(guide)
    _entry_drag_organise(guide)

    guide.section("Responding")
    _entry_write_response(page, guide)
    _entry_word_count(guide)

    guide.section("Export")
    _entry_export_pdf(page, guide)
    _entry_pdf_filename(guide)
    _entry_paragraph_numbers_export(guide)


def _run_management_sections(
    page: Page,
    base_url: str,
    course_url: str,
    guide: Guide,
) -> None:
    """Unit settings, enrolment, navigation, sharing, and reference sections."""
    guide.section("Unit Settings")
    _entry_create_unit(page, base_url, guide)
    _entry_rename_entities(guide)
    _entry_students_no_work(page, base_url, course_url, guide)
    _entry_view_student_work(guide)
    _entry_publish_activity(guide)

    guide.section("Activities and Templates")
    _entry_chip_colours(guide)
    _entry_tags_not_visible(page, base_url, course_url, guide)
    _entry_copy_protection(guide)
    _entry_student_uploads(guide)

    guide.section("Enrolment")
    _entry_enrol_students(page, course_url, guide)
    _entry_after_enrolment(page, base_url, guide)
    _entry_bulk_enrolment(guide)
    _entry_enrolment_invitations(guide)

    guide.section("Housekeeping")
    _entry_clean_up_test_activities(guide)

    guide.section("Navigation")
    _entry_find_workspace(page, base_url, guide)
    _entry_search_workspaces(page, guide)

    guide.section("Sharing & Collaboration")
    _entry_share_workspace(page, guide)
    _entry_peer_viewing(guide)
    _entry_collaboration(guide)

    guide.section("Content Input")
    _entry_upload_document(guide)
    _entry_paste_sources(guide)


def run_using_promptgrimoire_guide(page: Page, base_url: str) -> None:
    """Run the Using PromptGrimoire flight-rules guide."""
    course_url = _ensure_prerequisites(page, base_url)

    with Guide("Using PromptGrimoire", GUIDE_OUTPUT_DIR, page) as guide:
        guide.note(
            "Quick answers to common tasks and problems. "
            "Each entry shows you exactly what to click, with screenshots "
            "from the live application."
        )
        _run_screenshot_sections(page, base_url, course_url, guide)
        _run_management_sections(page, base_url, course_url, guide)
