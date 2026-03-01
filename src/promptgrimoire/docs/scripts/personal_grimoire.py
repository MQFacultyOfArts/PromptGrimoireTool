"""Personal grimoire guide -- produces markdown with annotated screenshots.

Drives a Playwright browser through the loose workspace flow: an enrolled
student chooses to create a personal workspace outside the activity
structure, builds their own tag vocabulary, annotates an AI conversation,
and associates the workspace with a course activity via the placement
dialog. Each section uses the Guide DSL to emit narrative markdown with
highlighted screenshots.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page

from promptgrimoire.docs import Guide
from promptgrimoire.docs.helpers import select_chars, wait_for_text_walker

GUIDE_OUTPUT_DIR = Path("docs/guides")

_SAMPLE_HTML = (
    '<div class="conversation">'
    '<div class="user"><p><strong>Human:</strong> I\'m translating a Japanese'
    " contract clause about \u4fe1\u7fa9\u8aa0\u5b9f\u306e\u539f\u5247"
    " (shingi seijitsu no gensoku)."
    " The English term 'good faith' doesn't seem to capture the full"
    " meaning. What cultural factors should I consider?</p></div>"
    '<div class="assistant"><p><strong>Assistant:</strong> You\'ve identified'
    " a significant translation challenge. The Japanese principle of"
    " \u4fe1\u7fa9\u8aa0\u5b9f\u306e\u539f\u5247 carries cultural weight beyond"
    " the common law concept"
    " of 'good faith':</p>"
    "<ol>"
    "<li><strong>Relational obligation:</strong> In Japanese legal culture,"
    " this principle reflects an ongoing duty to maintain harmonious"
    " business relationships, not merely honest dealing at the point"
    " of contract.</li>"
    "<li><strong>Contextual interpretation:</strong> Japanese courts apply"
    " this principle more broadly than common law courts apply good faith,"
    " considering social context and the parties' relationship history.</li>"
    "<li><strong>Implied duties:</strong> The principle generates implied"
    " duties of cooperation and disclosure that go further than common"
    " law good faith typically requires.</li>"
    "</ol>"
    "<p>A translator might consider retaining the Japanese term with"
    " an explanatory gloss, or using 'good faith and fair dealing'"
    " with a translator's note explaining the broader scope.</p>"
    "</div></div>"
)


def _authenticate(page: Page, base_url: str, email: str) -> None:
    """Authenticate via mock token and wait for redirect."""
    page.goto(f"{base_url}/auth/callback?token=mock-token-{email}")
    page.wait_for_url(lambda url: "/auth/callback" not in url, timeout=10000)


def _setup_loose_student() -> None:
    """Create the loose-student user and enrol in UNIT1234."""
    for cmd in [
        [
            "uv",
            "run",
            "manage-users",
            "create",
            "loose-student@test.example.edu.au",
            "--name",
            "Loose Student",
        ],
        [
            "uv",
            "run",
            "manage-users",
            "enroll",
            "loose-student@test.example.edu.au",
            "UNIT1234",
            "S1 2026",
        ],
    ]:
        subprocess.run(cmd, capture_output=True, check=False)


def _ensure_instructor_guide_ran(page: Page, base_url: str) -> None:
    """Ensure UNIT1234 exists; run instructor guide if not.

    Authenticates as a temporary user to check the Navigator for the
    unit. If UNIT1234 is not visible, invokes the instructor guide
    to create it. Re-authentication as the guide's own user happens
    in _section_enter_grimoire().
    """
    _setup_loose_student()
    _authenticate(page, base_url, "loose-student@test.example.edu.au")

    # Wait for Navigator to render, then check for UNIT1234.
    # Use wait_for on the start-activity-btn (present when units exist)
    # with a short timeout -- if it times out, UNIT1234 is missing.
    try:
        page.locator('[data-testid^="start-activity-btn"]').first.wait_for(
            state="visible",
            timeout=5000,
        )
        unit_visible = page.locator("text=UNIT1234").count() > 0
    except Exception as exc:
        if "Timeout" not in type(exc).__name__:
            raise
        unit_visible = False

    if not unit_visible:
        from promptgrimoire.docs.scripts.instructor_setup import (  # noqa: PLC0415
            run_instructor_guide,
        )

        run_instructor_guide(page, base_url)
        # Re-setup the loose student (instructor guide may have reset state)
        _setup_loose_student()


def _section_enter_grimoire(
    page: Page,
    base_url: str,
    guide: Guide,
) -> None:
    """Section 1: Enter the Grimoire.

    Login as enrolled student, show Navigator, navigate to /annotation,
    create a loose workspace (bypassing activity Start button).
    """
    with guide.step("Enter the Grimoire") as g:
        _authenticate(page, base_url, "loose-student@test.example.edu.au")

        # Navigator: show enrolled unit with Start button
        page.locator('[data-testid^="start-activity-btn"]').first.wait_for(
            state="visible",
            timeout=10000,
        )
        g.screenshot(
            "Navigator showing your enrolled unit and activities",
            highlight=["start-activity-btn"],
        )
        g.note(
            "After logging in, you see the Navigator with your enrolled "
            "units and activities. Instead of clicking Start on an "
            "activity, you will create your own workspace — your "
            "personal grimoire."
        )

        # Navigate to /annotation directly (bypassing Start button)
        page.goto(f"{base_url}/annotation")
        page.get_by_test_id("create-workspace-btn").wait_for(
            state="visible",
            timeout=10000,
        )
        g.screenshot(
            "Annotation page with Create Workspace button",
            highlight=["create-workspace-btn"],
        )
        g.note(
            "Navigate to the annotation page directly. The Create "
            "Workspace button lets you start a workspace outside any "
            "activity — a loose workspace that belongs only to you."
        )

        # Create the loose workspace
        page.get_by_test_id("create-workspace-btn").click()
        page.get_by_test_id("content-editor").wait_for(
            state="visible",
            timeout=15000,
        )
        g.screenshot(
            "Your new loose workspace on the annotation page",
            highlight=["content-editor"],
        )
        g.note(
            "Your workspace is created. Unlike activity-based workspaces, "
            "this one has no inherited tags and no course association. "
            "It is your blank slate — a grimoire waiting to be filled."
        )


def _section_bring_conversation(page: Page, guide: Guide) -> None:
    """Section 2: Bring Your Conversation.

    Paste an AI conversation about cultural markers in Japanese legal
    text translation. Confirm content type.
    """
    with guide.step("Bring Your Conversation") as g:
        g.note(
            "Copy an AI conversation that you want to analyse. This could "
            "be from ChatGPT, Claude, or any other tool. Paste it into "
            "the editor to begin building your grimoire."
        )

        # Inject sample HTML into QEditor contenteditable div.
        # Uses .q-editor__content -- known exception: Quasar renders this
        # div internally; our code cannot attach a data-testid to it.
        # Static, hardcoded content only (not user-supplied).
        page.evaluate(
            """(html) => {
                const el = document.querySelector(
                    '[data-testid="content-editor"] .q-editor__content'
                );
                el.focus();
                el.innerHTML = html;
                el.dispatchEvent(new Event('input', {bubbles: true}));
            }""",
            _SAMPLE_HTML,
        )
        g.screenshot(
            "AI conversation pasted into the editor",
            highlight=["content-editor"],
        )
        g.note(
            "Paste your AI conversation into the editor. This "
            "conversation about cultural markers in Japanese legal "
            "translation will be the artefact you annotate."
        )

        page.get_by_test_id("add-document-btn").click()

        confirm_btn = page.get_by_test_id("confirm-content-type-btn")
        confirm_btn.wait_for(state="visible", timeout=5000)
        confirm_btn.click()

        wait_for_text_walker(page, timeout=15000)
        g.screenshot("Processed conversation with formatted turns")
        g.note(
            "Your conversation is processed and displayed with formatted "
            "turns. The grimoire now holds your artefact — ready for "
            "annotation."
        )


def _section_make_meaning(page: Page, guide: Guide) -> None:
    """Section 3: Make Meaning Through Tags.

    Open tag management, create a tag group and three tags from scratch
    (emergent folksonomy). This section mirrors the instructor guide's
    tag creation but from the student's perspective — no inherited tags.
    """
    with guide.step("Make Meaning Through Tags") as g:
        g.note(
            "Your workspace has no tags — unlike activity-based workspaces "
            "that inherit the instructor's tag vocabulary, your grimoire "
            "starts empty. You build your own analytical vocabulary: an "
            "emergent folksonomy that reflects how you see the conversation."
        )

        # Open tag management dialog
        page.get_by_test_id("tag-settings-btn").click()
        page.get_by_test_id("add-tag-group-btn").wait_for(
            state="visible",
            timeout=5000,
        )
        g.screenshot(
            "Tag management dialog with no existing tags",
            highlight=["add-tag-group-btn"],
        )
        g.note(
            "Open the tag settings to create your own tags. The dialog "
            "is empty — you are starting from scratch."
        )

        # Create tag group "My Analysis"
        page.get_by_test_id("add-tag-group-btn").click()
        page.wait_for_timeout(1000)

        group_header = page.locator('[data-testid^="tag-group-header-"]').first
        group_header.wait_for(state="visible", timeout=5000)
        testid = group_header.get_attribute("data-testid") or ""
        group_id = testid.removeprefix("tag-group-header-")

        page.get_by_test_id(f"group-name-input-{group_id}").click()
        page.get_by_test_id(f"group-name-input-{group_id}").fill("My Analysis")
        # Commit the value by pressing Tab (triggers blur/change event)
        page.keyboard.press("Tab")
        page.wait_for_timeout(500)

        # Add three tags
        for tag_name in ["AI Assumption", "Cultural Gap", "Useful Insight"]:
            page.get_by_test_id(f"group-add-tag-btn-{group_id}").click()
            page.wait_for_timeout(1000)
            last_input = page.locator('[data-testid^="tag-name-input-"]').last
            last_input.click()
            last_input.fill(tag_name)

        g.screenshot(
            "Tag group 'My Analysis' with three student-created tags",
            highlight=["tag-name-input", "group-name-input"],
        )
        g.note(
            "Create a tag group and tags that make sense for your "
            "analysis. These tags — 'AI Assumption', 'Cultural Gap', "
            "and 'Useful Insight' — reflect the student's own "
            "analytical categories, not the instructor's."
        )

        # Close tag management dialog
        page.get_by_test_id("tag-management-done-btn").click()
        page.wait_for_timeout(1000)


def _section_annotate_and_reflect(page: Page, guide: Guide) -> None:
    """Section 4: Annotate and Reflect.

    Highlight text, apply a tag, add a comment, view Organise tab.
    """
    with guide.step("Annotate and Reflect") as g:
        g.note(
            "With your tags ready, read through the conversation and "
            "annotate the parts that matter. Each highlight is a claim "
            "about the text — a moment where you assert that this "
            "passage is significant and why."
        )

        # Select text and apply first tag
        select_chars(page, 0, 50)
        page.wait_for_timeout(500)

        tag_button = page.locator("[data-testid='tag-toolbar'] button").first
        tag_button.wait_for(state="visible", timeout=5000)
        tag_button.click()
        page.locator("[data-testid='annotation-card']").first.wait_for(
            state="visible",
            timeout=5000,
        )

        g.screenshot(
            "Text highlighted and tagged with your own category",
            highlight=["tag-toolbar", "annotation-card"],
        )
        g.note(
            "Select text and click a tag to create a highlight. "
            "Your tags — not the instructor's — categorise the "
            "annotation."
        )

        # Add a comment
        card = page.locator("[data-testid='annotation-card']").first
        comment_input = card.get_by_test_id("comment-input")
        comment_input.fill(
            "The AI assumes 'good faith' is a direct equivalent, "
            "but the Japanese concept carries relational obligations "
            "that common law lacks."
        )
        card.get_by_test_id("post-comment-btn").click()
        page.wait_for_timeout(1000)

        g.screenshot(
            "Comment reflecting on the AI's cultural assumption",
            highlight=["comment-input"],
        )
        g.note(
            "Add a comment explaining your annotation. This is where "
            "reflection happens — you are not just marking text, you "
            "are articulating why it matters."
        )

        # Organise tab
        page.get_by_test_id("tab-organise").click()
        page.get_by_test_id("organise-columns").wait_for(
            state="visible",
            timeout=10000,
        )
        page.wait_for_timeout(1000)

        g.screenshot(
            "Organise tab showing highlights grouped by your tags",
            highlight=["organise-columns"],
        )
        g.note(
            "The Organise tab groups your highlights by tag. Your "
            "emergent vocabulary becomes a lens for seeing patterns "
            "across the conversation."
        )


def _section_connect_to_unit(page: Page, guide: Guide) -> None:
    """Section 5: Connect to Your Unit.

    Open the placement dialog, select UNIT1234 activity via cascading
    selects, confirm placement.
    """
    with guide.step("Connect to Your Unit") as g:
        g.note(
            "Your grimoire has grown from a blank slate into a structured "
            "analysis. Now you can connect it to your unit — associating "
            "your personal work with the course activity so your "
            "instructor can see it alongside the class work."
        )

        # Switch back to Annotate tab
        page.get_by_test_id("tab-annotate").click()
        page.wait_for_timeout(1000)

        # Open placement dialog via placement chip
        page.get_by_test_id("placement-chip").click()
        page.get_by_test_id("placement-mode").wait_for(
            state="visible",
            timeout=5000,
        )
        g.screenshot(
            "Placement dialog for associating workspace with a unit",
            highlight=["placement-mode"],
        )
        g.note(
            "Click the placement chip in the header to open the "
            "placement dialog. Your enrolled units appear in the "
            "cascading selects because you are already enrolled."
        )

        # Select "Place in Activity" mode
        page.locator(
            '[data-testid="placement-mode"] label:has-text("Place in Activity")'
        ).click()
        page.wait_for_timeout(500)

        # Select unit from the course dropdown
        course_select = page.get_by_test_id("placement-course")
        course_select.wait_for(state="visible", timeout=5000)
        course_select.click()

        # Click the UNIT1234 option in the dropdown
        page.locator('.q-menu .q-item:has-text("UNIT1234")').first.wait_for(
            state="visible",
            timeout=5000,
        )
        page.locator('.q-menu .q-item:has-text("UNIT1234")').first.click()
        page.wait_for_timeout(1000)

        # Select week
        week_select = page.get_by_test_id("placement-week")
        week_select.click()
        page.locator(".q-menu .q-item").first.wait_for(
            state="visible",
            timeout=5000,
        )
        page.locator(".q-menu .q-item").first.click()
        page.wait_for_timeout(1000)

        # Select activity
        activity_select = page.get_by_test_id("placement-activity")
        activity_select.click()
        page.locator(".q-menu .q-item").first.wait_for(
            state="visible",
            timeout=5000,
        )
        page.locator(".q-menu .q-item").first.click()
        page.wait_for_timeout(500)

        g.screenshot(
            "Cascading selects with UNIT1234, week, and activity selected",
            highlight=[
                "placement-course",
                "placement-week",
                "placement-activity",
            ],
        )
        g.note(
            "Select your unit, week, and activity from the cascading "
            "dropdowns. Your enrolment in UNIT1234 makes it available "
            "in the placement dialog."
        )

        # Confirm placement
        page.get_by_test_id("placement-confirm-btn").click()
        page.wait_for_timeout(2000)

        g.screenshot("Workspace now associated with the course activity")
        g.note(
            "Your personal grimoire is now connected to the course "
            "activity. It appears alongside other students' work in "
            "the unit, while retaining your personal tag vocabulary "
            "and annotations."
        )


def run_personal_grimoire_guide(page: Page, base_url: str) -> None:
    """Run the personal grimoire guide, producing markdown and screenshots."""
    _ensure_instructor_guide_ran(page, base_url)

    with Guide("Your Personal Grimoire", GUIDE_OUTPUT_DIR, page) as guide:
        _section_enter_grimoire(page, base_url, guide)
        _section_bring_conversation(page, guide)
        _section_make_meaning(page, guide)
        _section_annotate_and_reflect(page, guide)
        _section_connect_to_unit(page, guide)
