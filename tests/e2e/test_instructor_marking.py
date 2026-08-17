"""E2E test: instructor marking journey via enrollment-derived staff access.

Covers a workflow live classes hit every week that previously had no
end-to-end coverage: an instructor opens a student's workspace to mark it
without ever receiving an explicit ACL grant. Access must come from
``CourseEnrollment``-derived staff permission (the ``is_staff`` branch of
``_resolve_enrollment_permission`` inside ``resolve_annotation_context``),
a path flagged as untested by a DBA review.

The "instructor" persona deliberately uses a plain, non-privileged
mock-auth identity -- not ``instructor@uni.edu`` or ``admin@example.com``.
Both of those get elevated ``roles``/``is_admin`` from
``src/promptgrimoire/auth/mock.py``, and ``is_admin`` alone short-circuits
``resolve_annotation_context`` straight to ``"owner"`` before enrollment
is ever consulted. A test built on either identity could pass for the
wrong reason. Course creation auto-enrols the creator with the
``coordinator`` course role (``CourseRoleRef.is_staff=True``), which is
what actually earns them access to the student's workspace later --
resolved fresh from ``course_enrollment`` on each request, with no ACL
row ever created for them.

Journey:
1. Instructor creates a course, week, and activity with template content,
   publishes the week, and enrols a student.
2. Student clones the activity workspace, highlights text, and adds a
   comment (identifiable content). "Share with class" is left off --
   staff access does not depend on it, unlike peer access.
3. Instructor navigates directly to the student's workspace URL with no
   explicit ACL grant. Editor-level capability (the tag toolbar) and the
   student's comment are both visible.
4. Instructor adds a marking comment on the student's highlight.
5. The marking comment syncs live (CRDT broadcast) to the student's
   still-open page.
6. Final invariant check: no explicit ACLEntry was ever created for the
   instructor on this workspace.
"""

from __future__ import annotations

import contextlib
import re
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from playwright.sync_api import expect
from sqlalchemy import create_engine, text

from promptgrimoire.docs.helpers import wait_for_text_walker
from tests.e2e.card_helpers import add_comment_to_highlight, expand_card
from tests.e2e.conftest import _authenticate_page
from tests.e2e.course_helpers import (
    add_activity,
    add_week,
    create_course,
    enrol_student,
    publish_week,
)
from tests.e2e.highlight_tools import create_highlight, find_text_range
from tests.e2e.page_interactions import clone_activity_workspace
from tests.e2e.tag_helpers import _seed_tags_for_workspace

if TYPE_CHECKING:
    from playwright.sync_api import Browser, Page
    from pytest_subtests import SubTests

TEMPLATE_TEXT = "The plaintiff suffered injury at the workplace on Tuesday morning."
STUDENT_COMMENT = "Initial submission notes: causation is unclear here."
INSTRUCTOR_COMMENT = "Marking feedback: expand on causation before Friday."


# ---------------------------------------------------------------------------
# DB helper -- proves the instructor never received an explicit ACL row
# ---------------------------------------------------------------------------


def _has_acl_entry(workspace_id: str, email: str) -> bool:
    """Check whether an explicit ACLEntry row exists for (workspace, user).

    This test never calls the shared ``_grant_workspace_access`` helper
    for the instructor persona -- their access must come solely from
    enrollment-derived staff permission. This check turns that omission
    into a positive, falsifiable assertion instead of leaving it implicit.
    """
    from promptgrimoire.config import get_settings

    settings_url = get_settings().database.url
    if not settings_url:
        return False
    db_url = str(settings_url)
    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
    engine = create_engine(sync_url)
    try:
        with engine.begin() as conn:
            row = conn.execute(
                text(
                    'SELECT 1 FROM acl_entry ae JOIN "user" u ON u.id = ae.user_id'
                    " WHERE ae.workspace_id = CAST(:ws AS uuid) AND u.email = :email"
                ),
                {"ws": workspace_id, "email": email},
            ).first()
            return row is not None
    finally:
        engine.dispose()


# ---------------------------------------------------------------------------
# Phase helpers -- extracted to keep the test method under 50 statements
# ---------------------------------------------------------------------------


def _fill_template_workspace(page: Page) -> None:
    """Click Create Template, add content, seed tags."""
    page.locator('[data-testid^="template-btn-"]').first.click()
    page.wait_for_url(re.compile(r"/annotation\?workspace_id="), timeout=10000)

    content_input = page.get_by_test_id("content-editor").locator(".q-editor__content")
    content_input.wait_for(state="visible", timeout=5000)
    content_input.fill(TEMPLATE_TEXT)

    page.get_by_test_id("add-document-btn").click()

    confirm = page.get_by_test_id("confirm-content-type-btn")
    confirm.wait_for(state="visible", timeout=5000)
    confirm.click()

    wait_for_text_walker(page, timeout=15000)

    # Seed tags so the cloned workspace has tag buttons to highlight with.
    ws_id = page.url.split("workspace_id=")[1].split("&")[0]
    _seed_tags_for_workspace(ws_id)
    page.reload()
    wait_for_text_walker(page, timeout=15000)


def _instructor_sets_up_course(
    page: Page,
    app_server: str,
    *,
    course_code: str,
    instructor_email: str,
    student_email: str,
    subtests: SubTests,
) -> str:
    """Instructor creates course+week+activity, enrols the student.

    Course creation auto-enrols the creator as "coordinator" -- a staff
    course role -- which is the sole basis for the instructor's later
    workspace access. Returns the course_id.
    """
    with subtests.test(msg="instructor_creates_course"):
        _authenticate_page(page, app_server, email=instructor_email)
        create_course(
            page,
            app_server,
            code=course_code,
            name="Marking Journey",
            semester="2026-S1",
        )

    match = re.search(r"/courses/([0-9a-f-]+)", page.url)
    assert match, "Expected course UUID in URL"
    course_id = match.group(1)

    with subtests.test(msg="add_week_and_activity"):
        add_week(page, title="Marking Week")
        add_activity(page, title="Marking Demo")

    with subtests.test(msg="fill_template"):
        _fill_template_workspace(page)

    with subtests.test(msg="publish_week"):
        page.goto(f"{app_server}/courses/{course_id}")
        publish_week(page, "Marking Week")

    with subtests.test(msg="enrol_student"):
        enrol_student(page, email=student_email)

    return course_id


def _student_clones_and_annotates(
    page: Page,
    app_server: str,
    *,
    student_email: str,
    course_id: str,
    subtests: SubTests,
) -> str:
    """Student clones the activity workspace and adds identifiable content.

    Deliberately does not toggle "share with class": the instructor's
    later access must come purely from enrollment-derived staff
    permission, which (unlike peer access) does not depend on sharing.
    Returns the workspace_id.
    """
    with subtests.test(msg="student_clones_workspace"):
        _authenticate_page(page, app_server, email=student_email)
        workspace_id = clone_activity_workspace(
            page, app_server, course_id, "Marking Demo"
        )

    with subtests.test(msg="student_creates_highlight_and_comment"):
        create_highlight(page, *find_text_range(page, "plaintiff"))
        page.get_by_test_id("annotation-card").first.wait_for(
            state="visible", timeout=5000
        )
        add_comment_to_highlight(page, STUDENT_COMMENT)

    return workspace_id


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.cards
@pytest.mark.timeout(60)
class TestInstructorMarking:
    """Instructor marks a student's workspace reached via staff enrollment."""

    def test_instructor_marks_via_enrollment_derived_permission(
        self,
        browser: Browser,
        app_server: str,
        subtests: SubTests,
    ) -> None:
        """Instructor marks a student's submission with no explicit ACL grant.

        Steps:
        1. Instructor creates course/week/activity with template, publishes,
           enrols student (auto-enrolled "coordinator" on course creation).
        2. Student clones the activity workspace, highlights text, comments.
        3. Instructor (same identity, same browser context as step 1) opens
           the student's workspace URL directly -- no ACL grant call is ever
           made. Editor-level capability and the student's comment are both
           visible.
        4. Instructor adds a marking comment.
        5. The marking comment syncs live to the student's still-open page.
        6. No explicit ACLEntry exists for the instructor on this workspace.
        """
        uid = uuid4().hex[:8]
        instructor_email = f"marker-{uid}@test.edu"
        student_email = f"student-{uid}@test.edu"
        course_code = f"MARK-{uid}"

        instructor_ctx = browser.new_context()
        student_ctx = browser.new_context()
        instructor_page = instructor_ctx.new_page()
        student_page = student_ctx.new_page()

        try:
            course_id = _instructor_sets_up_course(
                instructor_page,
                app_server,
                course_code=course_code,
                instructor_email=instructor_email,
                student_email=student_email,
                subtests=subtests,
            )

            workspace_id = _student_clones_and_annotates(
                student_page,
                app_server,
                student_email=student_email,
                course_id=course_id,
                subtests=subtests,
            )

            with subtests.test(
                msg="instructor_accesses_via_enrollment_derived_permission"
            ):
                ws_url = f"{app_server}/annotation?workspace_id={workspace_id}"
                instructor_page.goto(ws_url)
                wait_for_text_walker(instructor_page, timeout=15000)

                # The tag toolbar only renders when state.can_annotate is
                # True -- proof the "coordinator" enrollment role resolved
                # to course.default_instructor_permission ("editor"), not
                # a silent read-only fallback.
                expect(instructor_page.get_by_test_id("tag-toolbar")).to_be_visible(
                    timeout=10000
                )

                # Comments live in the card's lazily-built detail section --
                # expand it before looking for the student's comment text.
                expand_card(instructor_page, 0)
                expect(
                    instructor_page.get_by_test_id("comment-item").filter(
                        has_text=STUDENT_COMMENT
                    )
                ).to_be_visible(timeout=5000)

            with subtests.test(msg="instructor_adds_marking_comment"):
                add_comment_to_highlight(instructor_page, INSTRUCTOR_COMMENT)
                expect(instructor_page.get_by_test_id("comment-item")).to_have_count(
                    2, timeout=5000
                )

            with subtests.test(msg="marking_comment_syncs_to_student"):
                expect(
                    student_page.locator(
                        "[data-testid='annotation-card']"
                    ).first.get_by_test_id("comment-count-badge")
                ).to_be_visible(timeout=10000)
                expand_card(student_page, 0)
                expect(
                    student_page.get_by_test_id("comment-item").filter(
                        has_text=INSTRUCTOR_COMMENT
                    )
                ).to_be_visible(timeout=5000)

            with subtests.test(msg="no_explicit_acl_grant_for_instructor"):
                assert not _has_acl_entry(workspace_id, instructor_email), (
                    "Instructor must reach the workspace via "
                    "enrollment-derived permission only -- an explicit "
                    "ACLEntry row appeared, which would mask the code "
                    "path this test exists to cover."
                )
        finally:
            for p in (instructor_page, student_page):
                with contextlib.suppress(Exception):
                    p.goto("about:blank")
            instructor_ctx.close()
            student_ctx.close()
