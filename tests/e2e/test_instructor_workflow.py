"""E2E test: instructor course setup workflow.

Narrative persona test covering the full instructor journey:
authenticate -> create course -> add week -> create activity ->
configure copy protection -> edit template workspace -> publish week ->
manage tags (create, lock, reorder, import) -> student clone verification.

Each step is a discrete subtest checkpoint using pytest-subtests.

Acceptance Criteria:
- 156-e2e-test-migration.AC3.1: Persona test covering course setup flow
- 156-e2e-test-migration.AC3.6: Uses pytest-subtests for checkpoints
- 156-e2e-test-migration.AC4.1: No CSS.highlights assertions
- 156-e2e-test-migration.AC5.1: Creates own workspace (no shared state)
- 156-e2e-test-migration.AC5.2: UUID-suffixed course code for isolation
- tags-qa-95.AC2: Instructor tag management (create, lock, reorder, import)
- tags-qa-95.AC3: Student clone tag verification

Traceability:
- Issue: #156 (E2E test migration), #95 (Annotation tags QA)
- Design: docs/design-plans/2026-02-14-156-e2e-test-migration.md Phase 3
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from playwright.sync_api import expect

from tests.e2e.annotation_helpers import (
    _seed_tags_for_workspace,
    seed_group_id,
    seed_tag_id,
    select_chars,
    wait_for_text_walker,
)
from tests.e2e.conftest import _authenticate_page
from tests.e2e.course_helpers import (
    add_activity,
    add_week,
    configure_course_copy_protection,
    create_course,
    enrol_student,
    publish_week,
)

if TYPE_CHECKING:
    from playwright.sync_api import Browser, Page
    from pytest_subtests import SubTests


def _fill_template_workspace(page: Page) -> None:
    """Click Create Template, add content, and verify rendering.

    Extracted to keep test method statement count under the limit.
    Expects the page to be on a course detail page with a freshly
    created activity showing a "Create Template" button.
    """
    # Click "Create Template" to open the template workspace
    page.get_by_role(
        "button",
        name=re.compile(r"Create Template|Edit Template"),
    ).click()

    # Wait for the annotation page to load
    page.wait_for_url(
        re.compile(r"/annotation\?workspace_id="),
        timeout=10000,
    )

    # Fill content in the editor (QEditor with placeholder)
    content_input = page.get_by_test_id("content-editor").locator(".q-editor__content")
    content_input.wait_for(state="visible", timeout=5000)
    content_input.fill("Becky Bennett suffered a workplace injury.")

    # Click "Add Document" button
    page.get_by_test_id("add-document-btn").click()

    # Confirm content type dialog
    confirm_btn = page.get_by_test_id("confirm-content-type-btn")
    confirm_btn.wait_for(state="visible", timeout=5000)
    confirm_btn.click()

    # Wait for text walker to initialise (content rendered)
    page.wait_for_function(
        "() => window._textNodes && window._textNodes.length > 0",
        timeout=10000,
    )

    # Verify document content is visible
    doc_container = page.locator("#doc-container")
    doc_container.wait_for(state="visible", timeout=5000)
    assert doc_container.inner_text().strip(), (
        "Document container should have visible text"
    )

    # Seed tags into the template workspace so Phase 2 subtests
    # start with a known 10-tag set (same as standalone workspaces).
    workspace_id = page.url.split("workspace_id=")[1].split("&")[0]
    _seed_tags_for_workspace(workspace_id)
    page.reload()
    page.wait_for_function(
        "() => window._textNodes && window._textNodes.length > 0",
        timeout=10000,
    )


def _extract_course_id(page: Page) -> str:
    """Extract the course UUID from the current page URL.

    Expects the page URL to contain ``/courses/{uuid}``.
    """
    match = re.search(r"/courses/([0-9a-f-]+)", page.url)
    assert match, f"Expected course UUID in URL, got: {page.url}"
    return match.group(1)


def _student_clones_and_sees_content(
    browser: Browser,
    app_server: str,
    *,
    student_email: str,
    course_id: str,
    activity_title: str,
    expected_text: str,
) -> None:
    """Log in as student, navigate to course, clone workspace, verify content.

    Creates a separate browser context for the student. Verifies the
    cloned workspace contains the template content.
    """
    student_ctx = browser.new_context()
    student_page = student_ctx.new_page()
    try:
        _authenticate_page(student_page, app_server, email=student_email)

        # Navigate to the course detail page
        student_page.goto(f"{app_server}/courses/{course_id}")

        # Find and click "Start Activity" for the activity
        activity_label = student_page.get_by_text(activity_title)
        activity_label.wait_for(state="visible", timeout=10000)
        card = activity_label.locator("xpath=ancestor::div[contains(@class, 'q-card')]")
        card.get_by_role("button", name="Start Activity").first.click()

        # Wait for redirect to annotation page with cloned workspace
        student_page.wait_for_url(
            re.compile(r"/annotation\?workspace_id="),
            timeout=15000,
        )

        # Wait for text walker to initialise (content rendered)
        student_page.wait_for_function(
            "() => window._textNodes && window._textNodes.length > 0",
            timeout=10000,
        )

        # Verify cloned content is visible
        doc_container = student_page.locator("#doc-container")
        doc_container.wait_for(state="visible", timeout=5000)
        visible_text = doc_container.inner_text().strip()
        assert expected_text in visible_text, (
            f"Expected '{expected_text}' in cloned workspace, got: {visible_text!r}"
        )
    finally:
        student_page.close()
        student_ctx.close()


def _verify_copy_protection_enabled(page: Page) -> None:
    """Re-open course settings and verify copy protection is on.

    Opens the settings dialog, checks the switch state, then
    closes the dialog via Cancel.
    """
    page.get_by_test_id("course-settings-btn").click()
    dialog_title = page.get_by_test_id("course-settings-title")
    dialog_title.wait_for(state="visible", timeout=5000)

    toggle = page.locator(".q-toggle").filter(has_text="Default copy protection")
    assert toggle.get_attribute("aria-checked") == "true", (
        "Copy protection switch should be ON after enabling"
    )

    # Close the dialog without saving
    page.get_by_role("button", name="Cancel").click()
    dialog_title.wait_for(state="hidden", timeout=5000)


def _find_tag_input_by_name(page: Page, tag_name: str) -> str:
    """Find a tag's UUID by its name in the management dialog.

    Iterates tag name inputs in the open management dialog and returns
    the tag UUID extracted from the data-testid attribute.

    Args:
        page: Playwright page with management dialog open.
        tag_name: Exact tag name to find.

    Returns:
        Tag UUID string.
    """
    dialog = page.locator("[data-testid='tag-management-dialog']")
    inputs = dialog.locator("[data-testid^='tag-name-input-']")
    # NiceGUI puts data-testid directly on the <input> element, not a wrapper
    inputs.first.wait_for(state="attached", timeout=10000)
    count = inputs.count()
    for i in range(count):
        el = inputs.nth(i)
        val = el.input_value()
        if val == tag_name:
            testid = el.get_attribute("data-testid") or ""
            return testid.replace("tag-name-input-", "")
    raise AssertionError(f"Tag '{tag_name}' not found in management dialog")


# ---------------------------------------------------------------------------
# Instructor tag subtests (AC2.1-AC2.5) — extracted for PLR0915 compliance
# ---------------------------------------------------------------------------


def _instructor_open_template(page: Page, app_server: str, course_id: str) -> str:
    """Navigate to template workspace, return workspace_id."""
    page.goto(f"{app_server}/courses/{course_id}")
    page.wait_for_timeout(500)
    activity_card = page.get_by_text("Annotate Becky").locator(
        "xpath=ancestor::div[contains(@class, 'q-card')]"
    )
    activity_card.get_by_role("button", name=re.compile(r"Edit Template")).click()
    page.wait_for_url(re.compile(r"/annotation\?workspace_id="), timeout=10000)
    wait_for_text_walker(page, timeout=15000)
    template_ws_id = page.url.split("workspace_id=")[1].split("&")[0]
    toolbar = page.locator("[data-testid='tag-toolbar']")
    expect(toolbar).to_be_visible(timeout=5000)
    return template_ws_id


def _instructor_quick_create_tag(page: Page) -> None:
    """AC2.1: Create tag via quick-create dialog."""
    toolbar = page.locator("[data-testid='tag-toolbar']")
    toolbar.locator("button").filter(
        has=page.locator("i.q-icon", has_text="add")
    ).click()
    dialog = page.locator("[data-testid='tag-quick-create-dialog']")
    expect(dialog).to_be_visible(timeout=5000)
    dialog.get_by_test_id("tag-quick-create-name-input").fill(
        "Statutory Interpretation"
    )
    dialog.get_by_role("button", name="Create").click()
    expect(dialog).to_be_hidden(timeout=5000)
    expect(toolbar).to_contain_text("Statutory Interpretation", timeout=5000)


def _instructor_add_tag_via_management(page: Page, template_ws_id: str) -> None:
    """AC2.2: Add a named tag via management dialog, verify toolbar shows name."""
    toolbar = page.locator("[data-testid='tag-toolbar']")
    toolbar.locator("button").filter(
        has=page.locator("i.q-icon", has_text="settings")
    ).click()
    dialog = page.locator("[data-testid='tag-management-dialog']")
    expect(dialog).to_be_visible(timeout=5000)

    name_inputs = dialog.locator("[data-testid^='tag-name-input-']")
    count_before = name_inputs.count()

    analysis_gid = seed_group_id(template_ws_id, "Analysis")
    add_btn = dialog.locator(f"[data-testid='group-add-tag-btn-{analysis_gid}']")

    # Add tag — the backend creates it with a default name ("New tag")
    add_btn.click()
    page.wait_for_timeout(500)
    expect(name_inputs).to_have_count(count_before + 1, timeout=3000)

    # Find the newly created tag's input within the Analysis group section.
    # We scope to the group section to avoid accidentally picking up ungrouped
    # tags (e.g. "Statutory Interpretation") at the bottom of the dialog.
    # The group header's ancestor nicegui-column wraps: header + tags + add-btn.
    analysis_header = dialog.locator(f"[data-testid='tag-group-header-{analysis_gid}']")
    analysis_header.wait_for(state="visible", timeout=3000)
    group_section = analysis_header.locator(
        "xpath=ancestor::div[contains(@class,'nicegui-column')][1]"
    )
    # The last name input within this group section is the newly added tag
    new_input = group_section.locator("[data-testid^='tag-name-input-']").last
    new_input.wait_for(state="visible", timeout=3000)
    # Fill with a specific name and blur to trigger save-on-blur
    new_input.clear()
    new_input.fill("Facts")
    new_input.blur()
    # Wait for the blur-save WebSocket round-trip before closing the dialog
    page.wait_for_timeout(800)

    # Close dialog — Done button refreshes toolbar and closes
    dialog.locator("[data-testid='tag-management-done-btn']").click()
    expect(dialog).to_be_hidden(timeout=5000)

    # Toolbar must show the new tag name after dialog closes
    expect(toolbar).to_contain_text("Facts", timeout=5000)

    # Reopen and verify count + name persisted
    toolbar.locator("button").filter(
        has=page.locator("i.q-icon", has_text="settings")
    ).click()
    dialog = page.locator("[data-testid='tag-management-dialog']")
    expect(dialog).to_be_visible(timeout=5000)
    name_inputs = dialog.locator("[data-testid^='tag-name-input-']")
    expect(name_inputs).to_have_count(count_before + 1, timeout=3000)
    dialog.locator("[data-testid='tag-management-done-btn']").click()
    expect(dialog).to_be_hidden(timeout=5000)


def _instructor_lock_tag(page: Page, template_ws_id: str) -> None:
    """AC2.3: Lock a tag, verify persistence."""
    toolbar = page.locator("[data-testid='tag-toolbar']")
    toolbar.locator("button").filter(
        has=page.locator("i.q-icon", has_text="settings")
    ).click()
    dialog = page.locator("[data-testid='tag-management-dialog']")
    expect(dialog).to_be_visible(timeout=5000)

    jurisdiction_id = seed_tag_id(template_ws_id, "Jurisdiction")
    lock_btn = dialog.locator(f"[data-testid='tag-lock-icon-{jurisdiction_id}']")
    expect(lock_btn).to_be_visible(timeout=3000)
    lock_btn.click()
    page.wait_for_timeout(500)

    # Close and reopen to verify lock persisted
    dialog.locator("[data-testid='tag-management-done-btn']").click()
    expect(dialog).to_be_hidden(timeout=5000)

    toolbar.locator("button").filter(
        has=page.locator("i.q-icon", has_text="settings")
    ).click()
    dialog = page.locator("[data-testid='tag-management-dialog']")
    expect(dialog).to_be_visible(timeout=5000)
    lock_icon = dialog.locator(f"[data-testid='tag-lock-icon-{jurisdiction_id}']")
    expect(lock_icon).to_be_visible(timeout=3000)
    expect(lock_icon.locator("i.q-icon")).to_have_text("lock")
    dialog.locator("[data-testid='tag-management-done-btn']").click()
    expect(dialog).to_be_hidden(timeout=5000)


def _instructor_reorder_groups(page: Page, template_ws_id: str) -> None:
    """AC2.4: Reorder tag groups, verify persistence."""
    toolbar = page.locator("[data-testid='tag-toolbar']")
    toolbar.locator("button").filter(
        has=page.locator("i.q-icon", has_text="settings")
    ).click()
    dialog = page.locator("[data-testid='tag-management-dialog']")
    expect(dialog).to_be_visible(timeout=5000)

    sources_gid = seed_group_id(template_ws_id, "Sources")
    analysis_gid = seed_group_id(template_ws_id, "Analysis")

    # Click "move up" on Sources group to swap it above Analysis.
    move_up_btn = dialog.locator(f"[data-testid='group-move-up-{sources_gid}']")
    expect(move_up_btn).to_be_visible(timeout=3000)
    move_up_btn.click()
    page.wait_for_timeout(500)

    # Close and reopen to verify order persisted
    dialog.locator("[data-testid='tag-management-done-btn']").click()
    expect(dialog).to_be_hidden(timeout=5000)

    toolbar.locator("button").filter(
        has=page.locator("i.q-icon", has_text="settings")
    ).click()
    dialog = page.locator("[data-testid='tag-management-dialog']")
    expect(dialog).to_be_visible(timeout=5000)
    all_headers = dialog.locator("[data-testid^='tag-group-header-']")
    header_testids = [
        all_headers.nth(i).get_attribute("data-testid") or ""
        for i in range(all_headers.count())
    ]
    sources_idx = next(i for i, t in enumerate(header_testids) if sources_gid in t)
    analysis_idx = next(i for i, t in enumerate(header_testids) if analysis_gid in t)
    assert sources_idx < analysis_idx, (
        f"Sources (idx={sources_idx}) should appear before "
        f"Analysis (idx={analysis_idx}) after reorder"
    )
    dialog.locator("[data-testid='tag-management-done-btn']").click()
    expect(dialog).to_be_hidden(timeout=5000)


def _instructor_import_tags(page: Page, app_server: str, course_id: str) -> None:
    """AC2.5: Import tags from first activity into second activity."""
    # Navigate back to course page and create second activity
    page.goto(f"{app_server}/courses/{course_id}")
    page.wait_for_timeout(500)
    add_activity(page, title="Case Brief Practice")

    # Fill second activity's template
    activity_card = page.get_by_text("Case Brief Practice").locator(
        "xpath=ancestor::div[contains(@class, 'q-card')]"
    )
    activity_card.get_by_role("button", name=re.compile(r"Create Template")).click()
    page.wait_for_url(re.compile(r"/annotation\?workspace_id="), timeout=10000)
    content_input = page.get_by_test_id("content-editor").locator(".q-editor__content")
    content_input.wait_for(state="visible", timeout=5000)
    content_input.fill("The court held that the duty of care was breached.")
    page.get_by_test_id("add-document-btn").click()
    confirm_btn = page.get_by_test_id("confirm-content-type-btn")
    confirm_btn.wait_for(state="visible", timeout=5000)
    confirm_btn.click()
    wait_for_text_walker(page, timeout=15000)

    # Open management dialog and import from first activity
    toolbar = page.locator("[data-testid='tag-toolbar']")
    toolbar.locator("button").filter(
        has=page.locator("i.q-icon", has_text="settings")
    ).click()
    dialog = page.locator("[data-testid='tag-management-dialog']")
    expect(dialog).to_be_visible(timeout=5000)

    import_section = dialog.locator("[data-testid='tag-import-section']")
    expect(import_section).to_be_visible(timeout=5000)
    import_section.get_by_test_id("tag-import-source-select").click()
    page.wait_for_timeout(300)
    page.locator(".q-item").filter(has_text="Annotate Becky").click()
    page.wait_for_timeout(300)
    import_section.get_by_role("button", name="Import").click()
    page.wait_for_timeout(1000)

    # Verify imported tags appear
    name_inputs = dialog.locator("[data-testid^='tag-name-input-']")
    assert name_inputs.count() > 0, "Expected imported tags in dialog"
    dialog.locator("[data-testid='tag-management-done-btn']").click()
    expect(dialog).to_be_hidden(timeout=5000)
    expect(toolbar).to_contain_text("Jurisdiction", timeout=5000)


def _run_instructor_tag_subtests(
    page: Page,
    app_server: str,
    course_id: str,
    subtests: SubTests,
) -> str:
    """Run instructor tag management subtests on the template workspace.

    Returns the template workspace ID for use in student verification.
    """
    with subtests.test(msg="instructor_opens_template_workspace"):
        template_ws_id = _instructor_open_template(page, app_server, course_id)

    with subtests.test(msg="instructor_creates_tag_via_quick_create"):
        _instructor_quick_create_tag(page)

    with subtests.test(msg="instructor_adds_tags_via_management"):
        _instructor_add_tag_via_management(page, template_ws_id)

    with subtests.test(msg="instructor_locks_tag"):
        _instructor_lock_tag(page, template_ws_id)

    with subtests.test(msg="instructor_reorders_tag_groups"):
        _instructor_reorder_groups(page, template_ws_id)

    with subtests.test(msg="instructor_imports_tags"):
        _instructor_import_tags(page, app_server, course_id)

    return template_ws_id


# ---------------------------------------------------------------------------
# Student tag subtests (AC3.1-AC3.6) — extracted for PLR0915 compliance
# ---------------------------------------------------------------------------


def _student_verify_cloned_tags(student_page: Page) -> None:
    """AC3.1: Student sees cloned tags in toolbar."""
    toolbar = student_page.locator("[data-testid='tag-toolbar']")
    expect(toolbar).to_be_visible(timeout=5000)
    expect(toolbar).to_contain_text("Jurisdiction", timeout=3000)
    expect(toolbar).to_contain_text("Statutory Interpretation", timeout=3000)


def _student_verify_locked_readonly(student_page: Page) -> None:
    """AC3.2: Locked tag shows lock icon and readonly input."""
    toolbar = student_page.locator("[data-testid='tag-toolbar']")
    toolbar.locator("button").filter(
        has=student_page.locator("i.q-icon", has_text="settings")
    ).click()
    dialog = student_page.locator("[data-testid='tag-management-dialog']")
    expect(dialog).to_be_visible(timeout=5000)

    jurisdiction_id = _find_tag_input_by_name(student_page, "Jurisdiction")
    lock_icon = dialog.locator(f"[data-testid='tag-lock-icon-{jurisdiction_id}']")
    expect(lock_icon).to_be_visible(timeout=3000)

    name_input = dialog.locator(f"[data-testid='tag-name-input-{jurisdiction_id}']")
    expect(name_input).to_have_attribute("readonly", "")

    dialog.locator("[data-testid='tag-management-done-btn']").click()
    expect(dialog).to_be_hidden(timeout=5000)


def _student_edit_unlocked_tag(student_page: Page) -> None:
    """AC3.3: Student edits unlocked tag name (blur-save)."""
    toolbar = student_page.locator("[data-testid='tag-toolbar']")
    toolbar.locator("button").filter(
        has=student_page.locator("i.q-icon", has_text="settings")
    ).click()
    dialog = student_page.locator("[data-testid='tag-management-dialog']")
    expect(dialog).to_be_visible(timeout=5000)

    si_tag_id = _find_tag_input_by_name(student_page, "Statutory Interpretation")
    name_input = dialog.locator(f"[data-testid='tag-name-input-{si_tag_id}']")
    name_input.clear()
    name_input.fill("Key Principles")
    name_input.blur()
    student_page.wait_for_timeout(500)

    # Close and reopen to verify persistence
    dialog.locator("[data-testid='tag-management-done-btn']").click()
    expect(dialog).to_be_hidden(timeout=5000)

    toolbar.locator("button").filter(
        has=student_page.locator("i.q-icon", has_text="settings")
    ).click()
    dialog = student_page.locator("[data-testid='tag-management-dialog']")
    expect(dialog).to_be_visible(timeout=5000)
    _find_tag_input_by_name(student_page, "Key Principles")
    dialog.locator("[data-testid='tag-management-done-btn']").click()
    expect(dialog).to_be_hidden(timeout=5000)


def _student_reorder_tags(student_page: Page) -> None:
    """AC3.4: Student reorders tags within a group."""
    toolbar = student_page.locator("[data-testid='tag-toolbar']")
    toolbar.locator("button").filter(
        has=student_page.locator("i.q-icon", has_text="settings")
    ).click()
    dialog = student_page.locator("[data-testid='tag-management-dialog']")
    expect(dialog).to_be_visible(timeout=5000)

    # Use move-down button on the first tag to swap positions 0 and 1
    move_down_btns = dialog.locator("[data-testid^='tag-move-down-']")
    if move_down_btns.count() >= 1:
        move_down_btns.first.click()
        student_page.wait_for_timeout(500)

    dialog.locator("[data-testid='tag-management-done-btn']").click()
    expect(dialog).to_be_hidden(timeout=5000)


def _parse_tag_name_from_button(btn_text: str) -> str:
    """Extract the tag name from a toolbar button label.

    Toolbar buttons have labels like "[2] Procedural History".
    Strips the leading "[N] " shortcut prefix if present.

    Uses text_content() (not inner_text()) to get the raw DOM text without
    CSS text-transform (Quasar buttons default to uppercase visually, but
    text_content() returns the original case for comparison).

    Args:
        btn_text: text_content() of the toolbar button element.

    Returns:
        Tag name with shortcut prefix removed.
    """
    stripped = btn_text.strip()
    if "] " in stripped:
        return stripped.split("] ", 1)[1].strip()
    return stripped


def _student_keyboard_shortcuts(student_page: Page) -> None:
    """AC3.5 + AC3.6: Keyboard shortcuts apply the correct reordered tag."""
    toolbar = student_page.locator("[data-testid='tag-toolbar']")

    # Read the tag name at shortcut position "2" (2nd tag button, 0-indexed=1).
    # Use text_content() (not inner_text()) to get raw DOM text without
    # Quasar's uppercase CSS text-transform applied.
    key2_btn = toolbar.locator("[data-tag-id]").nth(1)
    key2_btn.wait_for(state="visible", timeout=5000)
    key2_raw = key2_btn.text_content() or ""
    key2_tag_name = _parse_tag_name_from_button(key2_raw)

    # Read the tag name at shortcut position "3" (3rd tag button, 0-indexed=2)
    key3_btn = toolbar.locator("[data-tag-id]").nth(2)
    key3_btn.wait_for(state="visible", timeout=5000)
    key3_raw = key3_btn.text_content() or ""
    key3_tag_name = _parse_tag_name_from_button(key3_raw)

    # AC3.5: Press "2" with text selected — highlight created with tag at position 2
    select_chars(student_page, 0, 5)
    student_page.keyboard.press("2")
    student_page.wait_for_timeout(500)

    first_card = student_page.locator("[data-testid='annotation-card']").first
    expect(first_card).to_be_visible(timeout=3000)

    # The card's tag select should show the tag name for shortcut "2"
    first_card_select = first_card.get_by_test_id("tag-select")
    expect(first_card_select).to_contain_text(key2_tag_name, timeout=3000)

    # AC3.6: Press "3" with text selected — highlight created with tag at position 3
    select_chars(student_page, 10, 20)
    student_page.keyboard.press("3")
    student_page.wait_for_timeout(500)

    cards = student_page.locator("[data-testid='annotation-card']")
    expect(cards).to_have_count(2, timeout=3000)

    # The second card's tag select should show the tag name for shortcut "3"
    second_card = cards.nth(1)
    second_card_select = second_card.get_by_test_id("tag-select")
    expect(second_card_select).to_contain_text(key3_tag_name, timeout=3000)


def _run_student_tag_subtests(
    browser: Browser,
    app_server: str,
    course_id: str,
    student_email: str,
    subtests: SubTests,
) -> None:
    """Run student tag verification subtests.

    Creates a new student browser context, clones the activity,
    and verifies the tag configuration matches the instructor's setup.
    """
    student_ctx = browser.new_context()
    student_page = student_ctx.new_page()
    try:
        _authenticate_page(student_page, app_server, email=student_email)
        student_page.goto(f"{app_server}/courses/{course_id}")

        activity_label = student_page.get_by_text("Annotate Becky")
        activity_label.wait_for(state="visible", timeout=10000)
        card = activity_label.locator("xpath=ancestor::div[contains(@class, 'q-card')]")
        card.get_by_role("button", name="Start Activity").first.click()
        student_page.wait_for_url(
            re.compile(r"/annotation\?workspace_id="), timeout=15000
        )
        wait_for_text_walker(student_page, timeout=15000)

        with subtests.test(msg="student_sees_cloned_tags"):
            _student_verify_cloned_tags(student_page)

        with subtests.test(msg="student_locked_tag_readonly"):
            _student_verify_locked_readonly(student_page)

        with subtests.test(msg="student_edits_unlocked_tag"):
            _student_edit_unlocked_tag(student_page)

        with subtests.test(msg="student_reorders_tags"):
            _student_reorder_tags(student_page)

        with subtests.test(msg="student_keyboard_shortcuts"):
            _student_keyboard_shortcuts(student_page)
    finally:
        student_page.close()
        student_ctx.close()


@pytest.mark.e2e
class TestInstructorWorkflow:
    """Instructor persona: course setup from scratch."""

    def test_full_course_setup(
        self,
        browser: Browser,
        app_server: str,
        subtests: SubTests,
    ) -> None:
        """Walk through complete course setup as an instructor.

        Creates a course, adds a week and activity, configures copy
        protection, edits the template workspace, publishes, then
        exercises tag management and student clone verification.
        """
        # Unique suffix for xdist isolation
        uid = uuid4().hex[:8]
        course_code = f"TEST-{uid}"
        course_name = f"E2E Workflow {uid}"
        semester = "2026-S1"

        context = browser.new_context()
        page = context.new_page()

        try:
            with subtests.test(msg="authenticate_as_instructor"):
                _authenticate_page(page, app_server, email="instructor@uni.edu")
                # Verify auth succeeded -- not redirected to login
                assert "/login" not in page.url, "Auth should succeed"

            with subtests.test(msg="create_course"):
                create_course(
                    page,
                    app_server,
                    code=course_code,
                    name=course_name,
                    semester=semester,
                )
                page.get_by_text(f"{course_code} - {course_name}").wait_for(
                    state="visible", timeout=5000
                )

            with subtests.test(msg="add_week"):
                add_week(page, title="Introduction")
                page.get_by_text(re.compile(r"Week \d+:\s*Introduction")).wait_for(
                    state="visible", timeout=5000
                )

            with subtests.test(msg="create_activity"):
                add_activity(page, title="Annotate Becky")
                page.get_by_text("Annotate Becky").wait_for(
                    state="visible", timeout=5000
                )

            with subtests.test(msg="configure_copy_protection"):
                configure_course_copy_protection(page, enabled=True)
                _verify_copy_protection_enabled(page)

            with subtests.test(msg="edit_template_workspace"):
                _fill_template_workspace(page)

            with subtests.test(msg="publish_week"):
                # Navigate back to the course detail page
                page.go_back()
                page.wait_for_url(
                    re.compile(r"/courses/[0-9a-f-]+"),
                    timeout=10000,
                )
                publish_week(page, "Introduction")
                unpub_btn = page.get_by_test_id("unpublish-week-btn")
                assert unpub_btn.is_visible(), "Unpublish button should be visible"

            # --- Bridge: instructor-to-student handoff ---
            student_email = f"student-{uid}@test.edu"
            course_id = _extract_course_id(page)

            with subtests.test(msg="enrol_student"):
                enrol_student(page, email=student_email)

            with subtests.test(msg="student_clones_and_sees_content"):
                _student_clones_and_sees_content(
                    browser,
                    app_server,
                    student_email=student_email,
                    course_id=course_id,
                    activity_title="Annotate Becky",
                    expected_text="Becky Bennett",
                )

            # --- Phase 2: Instructor tag management ---
            _run_instructor_tag_subtests(page, app_server, course_id, subtests)

            # --- Phase 2: Student clone tag verification ---
            student2_email = f"student2-{uid}@test.edu"

            with subtests.test(msg="enrol_second_student"):
                page.goto(f"{app_server}/courses/{course_id}")
                page.wait_for_timeout(500)
                enrol_student(page, email=student2_email)

            _run_student_tag_subtests(
                browser,
                app_server,
                course_id,
                student2_email,
                subtests,
            )

        finally:
            page.close()
            context.close()
