"""E2E test: anonymous sharing — three-perspective anonymisation.

Verifies that highlights and comments are correctly anonymised
(or not) depending on the viewer's role:

- **Instructor**: privileged viewer, sees all real names.
- **Student-owner**: workspace owner, sees own name; should see
  other students anonymised but instructor's real name.
- **Student-commenter**: peer viewer, sees own name; should see
  other students anonymised but instructor's real name.

Also verifies export TeX content (generated pre-latexmk) contains
correctly anonymised data for each perspective.

Bugs under test:
1. Owner sees other student's real name (should be anonymised).
2. Peer viewer sees instructor's name as "Unknown" (should see real name).
3. Owner can delete instructor's comments (should not be allowed).

Acceptance Criteria:
- workspace-sharing-97.AC4.7: broadcast labels respect anonymity flag
- workspace-sharing-97.Phase7: export/broadcast anonymisation

Traceability:
- Issue: #97 (Workspace Sharing & Visibility)
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from promptgrimoire.auth.anonymise import anonymise_display_name
from tests.e2e.annotation_helpers import (
    _seed_tags_for_workspace,
    add_comment_to_highlight,
    clone_activity_workspace,
    count_comment_delete_buttons,
    create_highlight,
    export_annotation_tex_text,
    get_comment_authors,
    get_user_id_by_email,
    toggle_share_with_class,
    wait_for_text_walker,
)
from tests.e2e.conftest import (
    _authenticate_page,
    _grant_workspace_access,
)
from tests.e2e.course_helpers import (
    add_activity,
    add_week,
    configure_course_setting,
    create_course,
    enrol_student,
    publish_week,
)

if TYPE_CHECKING:
    from playwright.sync_api import Browser, Page
    from pytest_subtests import SubTests


def _session_name_label(email: str) -> str:
    """Derive the title-cased session name used for comment attribution."""
    return email.split("@", maxsplit=1)[0].replace(".", " ").title()


def _expected_author_labels(
    *,
    owner_email: str,
    commenter_email: str,
) -> dict[str, str]:
    """Build expected real/anonymised labels for this test run."""
    owner_user_id = get_user_id_by_email(owner_email)
    commenter_user_id = get_user_id_by_email(commenter_email)
    return {
        "owner_real": _session_name_label(owner_email),
        "commenter_real": _session_name_label(commenter_email),
        "instructor_real": _session_name_label("instructor@uni.edu"),
        "owner_anon": anonymise_display_name(owner_user_id),
        "commenter_anon": anonymise_display_name(commenter_user_id),
    }


# ---------------------------------------------------------------------------
# Test-specific helpers
# ---------------------------------------------------------------------------


def _fill_template_workspace(page: Page) -> None:
    """Click Create Template, add content, seed tags."""
    page.get_by_role(
        "button",
        name=re.compile(r"Create Template|Edit Template"),
    ).click()
    page.wait_for_url(re.compile(r"/annotation\?workspace_id="), timeout=10000)

    content_input = page.get_by_placeholder(re.compile(r"paste|content", re.IGNORECASE))
    content_input.wait_for(state="visible", timeout=5000)
    content_input.fill(
        "The plaintiff suffered injury at the workplace on Tuesday morning."
    )

    page.get_by_role("button", name=re.compile(r"add document", re.IGNORECASE)).click()

    confirm = page.get_by_role("button", name=re.compile(r"confirm", re.IGNORECASE))
    confirm.wait_for(state="visible", timeout=5000)
    confirm.click()

    wait_for_text_walker(page, timeout=15000)

    # Seed tags so cloned workspaces have tag buttons
    ws_id = page.url.split("workspace_id=")[1].split("&")[0]
    _seed_tags_for_workspace(ws_id)
    page.reload()
    wait_for_text_walker(page, timeout=15000)


# ---------------------------------------------------------------------------
# Phase helpers — extracted to keep test method under 50 statements
# ---------------------------------------------------------------------------


def _setup_course(
    browser: Browser,
    app_server: str,
    *,
    course_code: str,
    course_name: str,
    student_owner_email: str,
    student_commenter_email: str,
    subtests: SubTests,
) -> str:
    """Instructor creates course with anon+sharing, returns course_id."""
    ctx = browser.new_context()
    page = ctx.new_page()

    try:
        with subtests.test(msg="instructor_creates_course"):
            _authenticate_page(page, app_server, email="instructor@uni.edu")
            create_course(
                page,
                app_server,
                code=course_code,
                name=course_name,
                semester="2026-S1",
            )

        match = re.search(r"/courses/([0-9a-f-]+)", page.url)
        assert match, "Expected course UUID in URL"
        course_id = match.group(1)

        with subtests.test(msg="configure_anonymous_and_sharing"):
            configure_course_setting(
                page,
                toggle_label="Default allow sharing",
                enabled=True,
            )
            configure_course_setting(
                page,
                toggle_label="Anonymous sharing by default",
                enabled=True,
            )

        with subtests.test(msg="add_week_and_activity"):
            add_week(page, title="Sharing Test")
            add_activity(page, title="Anon Annotate")

        with subtests.test(msg="fill_template"):
            _fill_template_workspace(page)

        with subtests.test(msg="publish_week"):
            page.go_back()
            page.wait_for_url(re.compile(r"/courses/[0-9a-f-]+"), timeout=10000)
            publish_week(page, "Sharing Test")

        with subtests.test(msg="enrol_students"):
            enrol_student(page, email=student_owner_email)
            enrol_student(page, email=student_commenter_email)

        return course_id
    finally:
        page.close()
        ctx.close()


def _owner_creates_content(
    browser: Browser,
    app_server: str,
    *,
    student_owner_email: str,
    course_id: str,
    subtests: SubTests,
) -> str:
    """Student-owner clones, shares, highlights+comments.

    Returns workspace_id.
    """
    ctx = browser.new_context()
    page = ctx.new_page()

    try:
        with subtests.test(msg="owner_clones_workspace"):
            _authenticate_page(page, app_server, email=student_owner_email)
            workspace_id = clone_activity_workspace(
                page, app_server, course_id, "Anon Annotate"
            )

        with subtests.test(msg="owner_shares_with_class"):
            toggle_share_with_class(page)

        with subtests.test(msg="owner_creates_highlight_and_comment"):
            create_highlight(page, 0, 13)
            page.wait_for_timeout(500)
            add_comment_to_highlight(page, "Owner's comment here")

        return workspace_id
    finally:
        page.close()
        ctx.close()


def _user_adds_comment(
    browser: Browser,
    app_server: str,
    *,
    email: str,
    workspace_id: str,
    comment_text: str,
    subtests: SubTests,
    subtest_label: str,
) -> None:
    """Authenticate as user, visit workspace, add comment."""
    ctx = browser.new_context()
    page = ctx.new_page()

    try:
        with subtests.test(msg=subtest_label):
            _authenticate_page(page, app_server, email=email)
            ws_url = f"{app_server}/annotation?workspace_id={workspace_id}"
            page.goto(ws_url)
            wait_for_text_walker(page, timeout=15000)
            add_comment_to_highlight(page, comment_text)
    finally:
        page.close()
        ctx.close()


def _assert_tex_is_valid(tex_text: str, perspective: str) -> None:
    """Assert TeX output is structurally valid (not vacuous)."""
    assert tex_text, f"{perspective}: TeX output is empty"
    assert r"\begin{document}" in tex_text, (
        f"{perspective}: TeX missing \\begin{{document}}"
    )
    assert r"\end{document}" in tex_text, (
        f"{perspective}: TeX missing \\end{{document}}"
    )
    assert r"\annot" in tex_text, (
        f"{perspective}: TeX has no \\annot commands (no highlights exported)"
    )


def _assert_instructor_perspective(
    browser: Browser,
    app_server: str,
    workspace_id: str,
    labels: dict[str, str],
    subtests: SubTests,
) -> None:
    """Instructor sees all real labels in web and exported TeX."""
    ctx = browser.new_context()
    page = ctx.new_page()

    try:
        _authenticate_page(page, app_server, email="instructor@uni.edu")
        ws_url = f"{app_server}/annotation?workspace_id={workspace_id}"
        page.goto(ws_url)
        wait_for_text_walker(page, timeout=15000)

        with subtests.test(msg="instructor_web_labels_are_real"):
            authors = get_comment_authors(page)
            assert len(authors) == 3, (
                "Expected 3 comments "
                "(owner+instructor+commenter), "
                f"got {len(authors)}: {authors}"
            )
            assert labels["owner_real"] in authors, (
                f"Instructor should see owner real name. Got: {authors}"
            )
            assert labels["commenter_real"] in authors, (
                f"Instructor should see commenter real name. Got: {authors}"
            )
            assert labels["instructor_real"] in authors, (
                f"Instructor should see own real name. Got: {authors}"
            )
            assert labels["owner_anon"] not in authors, (
                f"Instructor should not see owner anonymised label. Got: {authors}"
            )
            assert labels["commenter_anon"] not in authors, (
                f"Instructor should not see commenter anonymised label. Got: {authors}"
            )
            assert "Unknown" not in authors, (
                f"Instructor should not see 'Unknown'. Got: {authors}"
            )

        with subtests.test(msg="instructor_tex_labels_are_real"):
            tex_text = export_annotation_tex_text(page)
            _assert_tex_is_valid(tex_text, "instructor")
            # All three real names present
            assert labels["owner_real"] in tex_text, "Owner real name missing in TeX"
            assert labels["commenter_real"] in tex_text, (
                "Commenter real name missing in TeX"
            )
            assert labels["instructor_real"] in tex_text, (
                "Instructor real name missing in TeX"
            )
            # All three comment texts present
            assert "Owner's comment here" in tex_text, (
                "Owner comment text missing in instructor TeX"
            )
            assert "Instructor feedback" in tex_text, (
                "Instructor comment text missing in instructor TeX"
            )
            assert "Commenter's thought" in tex_text, (
                "Commenter comment text missing in instructor TeX"
            )
            # No anonymised names for instructor
            assert labels["owner_anon"] not in tex_text, (
                "Owner anonymised label should not appear for instructor"
            )
            assert labels["commenter_anon"] not in tex_text, (
                "Commenter anonymised label should not appear for instructor"
            )
            assert "Unknown" not in tex_text, (
                "Instructor TeX should not contain 'Unknown'"
            )
    finally:
        page.close()
        ctx.close()


def _assert_owner_perspective(
    browser: Browser,
    app_server: str,
    workspace_id: str,
    student_owner_email: str,
    labels: dict[str, str],
    subtests: SubTests,
) -> None:
    """Owner sees commenter anonymised + instructor real in web and TeX."""
    ctx = browser.new_context()
    page = ctx.new_page()

    try:
        _authenticate_page(page, app_server, email=student_owner_email)
        ws_url = f"{app_server}/annotation?workspace_id={workspace_id}"
        page.goto(ws_url)
        wait_for_text_walker(page, timeout=15000)

        with subtests.test(msg="owner_sees_three_comments"):
            authors = get_comment_authors(page)
            assert len(authors) == 3, (
                f"Expected 3 comments, got {len(authors)}: {authors}"
            )

        with subtests.test(msg="owner_web_labels_are_correct"):
            authors = get_comment_authors(page)
            assert labels["owner_real"] in authors, (
                f"Owner should see own real name. Got: {authors}"
            )
            assert labels["instructor_real"] in authors, (
                f"Owner should see instructor real name. Got: {authors}"
            )
            assert labels["commenter_anon"] in authors, (
                f"Bug 1: Owner should see commenter anonymised label. Got: {authors}"
            )
            assert labels["commenter_real"] not in authors, (
                f"Bug 1: Owner should NOT see commenter's real name. Got: {authors}"
            )
            assert labels["owner_anon"] not in authors, (
                f"Owner should not see own anonymised label. Got: {authors}"
            )
            assert "Unknown" not in authors, (
                f"Bug 2: Owner should not see 'Unknown' for instructor. Got: {authors}"
            )

        with subtests.test(msg="owner_cannot_delete_instructor_comment"):
            delete_count = count_comment_delete_buttons(page)
            assert delete_count == 1, (
                "Bug 3: Owner should only delete own "
                "comments. Expected 1 delete button, "
                f"got {delete_count}"
            )

        with subtests.test(msg="owner_tex_labels_are_correct"):
            tex_text = export_annotation_tex_text(page)
            _assert_tex_is_valid(tex_text, "owner")
            # Own real name + instructor real name
            assert labels["owner_real"] in tex_text, (
                "Owner real name missing in owner TeX"
            )
            assert labels["instructor_real"] in tex_text, (
                "Instructor real name missing in owner TeX"
            )
            assert labels["commenter_anon"] in tex_text, (
                "Bug 1: Owner TeX should contain commenter anonymised label"
            )
            # All three comment texts present
            assert "Owner's comment here" in tex_text, (
                "Owner comment text missing in owner TeX"
            )
            assert "Instructor feedback" in tex_text, (
                "Instructor comment text missing in owner TeX"
            )
            assert "Commenter's thought" in tex_text, (
                "Commenter comment text missing in owner TeX"
            )
            # Commenter real name hidden
            assert labels["commenter_real"] not in tex_text, (
                "Bug 1: Owner TeX should not contain commenter real name"
            )
            assert "Unknown" not in tex_text, (
                "Bug 2: Owner TeX should not contain 'Unknown'"
            )
    finally:
        page.close()
        ctx.close()


def _assert_commenter_perspective(
    browser: Browser,
    app_server: str,
    workspace_id: str,
    student_commenter_email: str,
    labels: dict[str, str],
    subtests: SubTests,
) -> None:
    """Commenter sees owner anonymised + instructor real in web and TeX."""
    ctx = browser.new_context()
    page = ctx.new_page()

    try:
        _authenticate_page(page, app_server, email=student_commenter_email)
        ws_url = f"{app_server}/annotation?workspace_id={workspace_id}"
        page.goto(ws_url)
        wait_for_text_walker(page, timeout=15000)

        with subtests.test(msg="commenter_sees_three_comments"):
            authors = get_comment_authors(page)
            assert len(authors) == 3, (
                f"Expected 3 comments, got {len(authors)}: {authors}"
            )

        with subtests.test(msg="commenter_web_labels_are_correct"):
            authors = get_comment_authors(page)
            assert labels["commenter_real"] in authors, (
                f"Commenter should see own real name. Got: {authors}"
            )
            assert labels["instructor_real"] in authors, (
                f"Commenter should see instructor real name. Got: {authors}"
            )
            assert labels["owner_anon"] in authors, (
                f"Commenter should see owner anonymised label. Got: {authors}"
            )
            assert labels["owner_real"] not in authors, (
                f"Commenter should NOT see owner's real name. Got: {authors}"
            )
            assert labels["commenter_anon"] not in authors, (
                f"Commenter should not see own anonymised label. Got: {authors}"
            )
            assert "Unknown" not in authors, (
                "Bug 2: Commenter should not see 'Unknown' for instructor. "
                f"Got: {authors}"
            )

        with subtests.test(msg="commenter_cannot_delete_others"):
            delete_count = count_comment_delete_buttons(page)
            assert delete_count == 1, (
                "Commenter should only delete own "
                "comments. Expected 1 delete button, "
                f"got {delete_count}"
            )

        with subtests.test(msg="commenter_tex_labels_are_correct"):
            tex_text = export_annotation_tex_text(page)
            _assert_tex_is_valid(tex_text, "commenter")
            assert labels["commenter_real"] in tex_text, (
                "Commenter real name missing in commenter TeX"
            )
            assert labels["instructor_real"] in tex_text, (
                "Instructor real name missing in commenter TeX"
            )
            assert labels["owner_anon"] in tex_text, (
                "Commenter TeX should contain owner anonymised label"
            )
            assert "Owner's comment here" in tex_text, (
                "Owner comment text missing in commenter TeX"
            )
            assert "Instructor feedback" in tex_text, (
                "Instructor comment text missing in commenter TeX"
            )
            assert "Commenter's thought" in tex_text, (
                "Commenter comment text missing in commenter TeX"
            )
            assert labels["owner_real"] not in tex_text, (
                "Commenter TeX should not contain owner real name"
            )
            assert "Unknown" not in tex_text, (
                "Commenter TeX should not contain 'Unknown'"
            )
    finally:
        page.close()
        ctx.close()


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestAnonymousSharing:
    """Three-perspective anonymous sharing verification."""

    def test_anonymous_sharing_three_perspectives(
        self,
        browser: Browser,
        app_server: str,
        subtests: SubTests,
    ) -> None:
        """Set up anonymous shared workspace, verify three perspectives.

        Steps:
        1. Instructor creates course with anon + allow sharing ON.
        2. Instructor creates activity with template, publishes.
        3. Enrols two students.
        4. Student-owner clones, shares, creates highlight + comment.
        5. Instructor visits student workspace, adds comment.
        6. Student-commenter visits shared workspace, adds comment.
        7. Each user reloads and assertions checked (UI + TeX).

        Bugs verified:
        - Bug 1: Owner must NOT see other student's real name.
        - Bug 2: Peer must NOT see instructor as "Unknown".
        - Bug 3: Owner must NOT delete instructor's comments.
        """
        uid = uuid4().hex[:8]
        owner_email = f"student-owner-{uid}@test.edu"
        commenter_email = f"student-commenter-{uid}@test.edu"

        # Phase 1: Instructor sets up course
        course_id = _setup_course(
            browser,
            app_server,
            course_code=f"ANON-{uid}",
            course_name=f"Anon Sharing {uid}",
            student_owner_email=owner_email,
            student_commenter_email=commenter_email,
            subtests=subtests,
        )

        # Phase 2: Student-owner clones, shares, creates content
        workspace_id = _owner_creates_content(
            browser,
            app_server,
            student_owner_email=owner_email,
            course_id=course_id,
            subtests=subtests,
        )

        # Grant access to instructor and commenter
        _grant_workspace_access(
            workspace_id,
            "instructor@uni.edu",
            permission="editor",
        )
        _grant_workspace_access(
            workspace_id,
            commenter_email,
            permission="peer",
        )

        # Phase 3: Instructor adds comment
        _user_adds_comment(
            browser,
            app_server,
            email="instructor@uni.edu",
            workspace_id=workspace_id,
            comment_text="Instructor feedback",
            subtests=subtests,
            subtest_label="instructor_adds_comment",
        )

        # Phase 4: Commenter adds comment
        _user_adds_comment(
            browser,
            app_server,
            email=commenter_email,
            workspace_id=workspace_id,
            comment_text="Commenter's thought",
            subtests=subtests,
            subtest_label="commenter_adds_comment",
        )

        labels = _expected_author_labels(
            owner_email=owner_email,
            commenter_email=commenter_email,
        )

        # Phase 5: Assertions from each perspective (UI + TeX)
        _assert_instructor_perspective(
            browser,
            app_server,
            workspace_id,
            labels,
            subtests,
        )
        _assert_owner_perspective(
            browser,
            app_server,
            workspace_id,
            owner_email,
            labels,
            subtests,
        )
        _assert_commenter_perspective(
            browser,
            app_server,
            workspace_id,
            commenter_email,
            labels,
            subtests,
        )
