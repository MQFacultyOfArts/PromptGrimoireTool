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

from promptgrimoire.docs.helpers import wait_for_text_walker

if TYPE_CHECKING:
    from playwright.sync_api import Page

    from promptgrimoire.docs import Guide

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
    except Exception:
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
