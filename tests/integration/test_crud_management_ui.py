"""NiceGUI User-harness tests for CRUD management delete guards.

Replaces the Playwright E2E tests with lightweight in-process tests that
exercise the same UI paths using NiceGUI's simulated User.  These need a
test database but NOT a browser.

Acceptance Criteria:
- crud-management-229.AC2.5: Delete confirmation dialog workflow
- crud-management-229.AC6.2: Delete Unit button visible for coordinator
- crud-management-229.AC6.5: Delete Unit button hidden for non-coordinators

Traceability:
- Issue: #229 (CRUD management)
- Design: docs/implementation-plans/2026-03-02-crud-management-229/phase_05.md
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from nicegui import ElementFilter
from nicegui.element import Element

from promptgrimoire.config import get_settings

if TYPE_CHECKING:
    from nicegui.element import Element
    from nicegui.testing.user import User

pytestmark = [
    pytest.mark.skipif(
        not get_settings().dev.test_database_url,
        reason="DEV__TEST_DATABASE_URL not configured",
    ),
    # NiceGUI User harness conflicts with xdist (same as Playwright E2E).
    # Excluded from test-all via -m "not e2e"; run directly with -p no:xdist.
    pytest.mark.e2e,
]


# ---------------------------------------------------------------------------
# data-testid helpers
# ---------------------------------------------------------------------------
# NiceGUI's ``ElementFilter(marker=...)`` checks ``.mark()`` markers, not
# ``data-testid`` props.  Since this codebase sets ``data-testid`` via
# ``.props('data-testid="..."')``, we need custom helpers to locate
# elements by their ``data-testid`` value.


def _is_in_open_dialog(el: Element) -> bool:
    """Check whether *el* is inside a dialog that is currently open."""
    from nicegui import ui

    parent = el.parent_slot.parent if el.parent_slot else None
    while parent is not None:
        if isinstance(parent, ui.dialog):
            return parent.value  # True when open
        parent = parent.parent_slot.parent if parent.parent_slot else None
    return True  # Not inside a dialog — always "visible"


def _find_by_testid(user: User, testid: str) -> Element | None:
    """Return the first element whose ``data-testid`` prop matches *testid*.

    Skips elements inside closed dialogs.
    """
    with user:
        for el in ElementFilter():
            if not el.visible:
                continue
            if el.props.get("data-testid") != testid:
                continue
            if not _is_in_open_dialog(el):
                continue
            return el
    return None


async def _should_see_testid(user: User, testid: str, *, retries: int = 5) -> None:
    """Assert that a visible element with the given ``data-testid`` exists."""
    for _ in range(retries):
        if _find_by_testid(user, testid) is not None:
            return
        await asyncio.sleep(0.1)
    raise AssertionError(f"expected to see an element with data-testid={testid!r}")


async def _should_not_see_testid(user: User, testid: str, *, retries: int = 5) -> None:
    """Assert that no visible element with the given ``data-testid`` exists."""
    for _ in range(retries):
        if _find_by_testid(user, testid) is None:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"expected NOT to see an element with data-testid={testid!r}")


def _click_testid(user: User, testid: str) -> None:
    """Click the first visible element matching ``data-testid``."""
    el = _find_by_testid(user, testid)
    if el is None:
        raise AssertionError(
            f"cannot click: no visible element with data-testid={testid!r}"
        )
    from nicegui import events

    # TODO(2026-03): Replace with public API when NiceGUI exposes a click()
    # method that works outside the User.find() marker-based lookup.  We use
    # the same pattern as NiceGUI's UserInteraction.click() internally.
    # See: https://github.com/zauberzeug/nicegui/issues/XXXX
    for listener in el._event_listeners.values():
        if listener.element_id != el.id:
            continue
        event_arguments = events.GenericEventArguments(
            sender=el, client=el.client, args=None
        )
        events.handle_event(listener.handler, event_arguments)


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------


async def _authenticate(user: User, *, email: str) -> None:
    """Establish an authenticated session for the simulated user.

    Instead of hitting ``/auth/callback`` (whose ``ui.navigate.to("/")``
    creates a background ``user.open()`` that replaces the httpx session
    cookie and loses the storage written by the callback), we:

    1. Open the login page to establish a session cookie.
    2. Ensure the User record exists in the DB.
    3. Write ``auth_user`` directly into ``app.storage.user``.

    This mirrors what ``_set_session_user()`` does in production auth.
    """
    from promptgrimoire.auth.mock import MOCK_INSTRUCTOR_EMAILS
    from promptgrimoire.db.users import find_or_create_user

    # 1. Establish a session (any page will do)
    await user.open("/login")

    # 2. Ensure user record exists in DB
    user_record, _ = await find_or_create_user(
        email=email,
        display_name=email.split("@", maxsplit=1)[0],
    )

    # 3. Build the auth_user dict and inject into session storage
    roles = ["stytch_member"]
    if email in MOCK_INSTRUCTOR_EMAILS:
        roles.append("instructor")

    with user:
        from nicegui import app as _app

        _app.storage.user["auth_user"] = {
            "email": email,
            "member_id": f"mock-member-{email}",
            "organization_id": "mock-org-123",
            "session_token": f"mock-session-{email}",
            "roles": roles,
            "name": email.split("@", maxsplit=1)[0].replace(".", " ").title(),
            "display_name": email.split("@", maxsplit=1)[0].replace(".", " ").title(),
            "auth_method": "mock",
            "user_id": str(user_record.id),
            "is_admin": False,
        }


# ---------------------------------------------------------------------------
# DB helpers -- create test entities directly via the service layer
# ---------------------------------------------------------------------------


async def _create_course() -> tuple[UUID, str]:
    """Create a course with a unique code. Returns (course_id, code)."""
    from promptgrimoire.db.courses import create_course

    uid = uuid4().hex[:8]
    code = f"DEL{uid.upper()}"
    course = await create_course(
        code=code, name=f"Delete Test {uid}", semester="2026-S1"
    )
    return course.id, code


async def _enroll(course_id: UUID, email: str, role: str) -> UUID:
    """Ensure user exists and enroll them in the course. Returns user_id."""
    from promptgrimoire.db.courses import enroll_user
    from promptgrimoire.db.users import find_or_create_user

    user_record, _ = await find_or_create_user(
        email=email, display_name=email.split("@", maxsplit=1)[0]
    )
    await enroll_user(course_id=course_id, user_id=user_record.id, role=role)
    return user_record.id


async def _create_week(course_id: UUID, title: str = "Test Week") -> UUID:
    """Create a week in the given course. Returns week_id."""
    from promptgrimoire.db.weeks import create_week

    week = await create_week(course_id=course_id, week_number=1, title=title)
    return week.id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDeleteWeekConfirmationDialog:
    """Verify the delete confirmation dialog appears and cancel preserves state."""

    @pytest.mark.asyncio
    async def test_cancel_preserves_week(self, nicegui_user: User) -> None:
        """Click delete on a week, cancel, and verify the week survives (AC2.5).

        Steps:
        1. Create course + enrollment + week via DB.
        2. Authenticate and open the course detail page.
        3. Click the delete button on the week card.
        4. Verify the confirmation dialog (confirm/cancel buttons).
        5. Click cancel.
        6. Verify the week text is still visible.
        """
        email = "instructor@uni.edu"
        course_id, _code = await _create_course()
        await _enroll(course_id, email, "coordinator")
        week_title = "Week to Not Delete"
        week_id = await _create_week(course_id, title=week_title)

        await _authenticate(nicegui_user, email=email)
        await nicegui_user.open(f"/courses/{course_id}")

        # The week header shows "Week 1: Week to Not Delete"
        await nicegui_user.should_see(content=week_title)

        # Click the delete-week button
        _click_testid(nicegui_user, f"delete-week-btn-{week_id}")
        await asyncio.sleep(0.1)

        # Confirmation dialog should be visible
        await _should_see_testid(nicegui_user, "confirm-delete-btn")
        await _should_see_testid(nicegui_user, "cancel-delete-btn")

        # Click cancel
        _click_testid(nicegui_user, "cancel-delete-btn")
        await asyncio.sleep(0.1)

        # Dialog should close -- confirm button gone
        await _should_not_see_testid(nicegui_user, "confirm-delete-btn")

        # Week should still be visible
        await nicegui_user.should_see(content=week_title)


class TestDeleteWeekSuccess:
    """Verify that confirming delete actually removes the week."""

    @pytest.mark.asyncio
    async def test_delete_removes_week(self, nicegui_user: User) -> None:
        """Create a week, delete it via UI, verify it disappears (AC2.1).

        Steps:
        1. Create course + enrollment + week via DB.
        2. Authenticate and open the course detail page.
        3. Click delete, then confirm.
        4. Verify the week text disappears.
        """
        email = "instructor@uni.edu"
        course_id, _code = await _create_course()
        await _enroll(course_id, email, "coordinator")
        week_title = "Week to Delete"
        week_id = await _create_week(course_id, title=week_title)

        await _authenticate(nicegui_user, email=email)
        await nicegui_user.open(f"/courses/{course_id}")

        await nicegui_user.should_see(content=week_title)

        # Click delete
        _click_testid(nicegui_user, f"delete-week-btn-{week_id}")
        await asyncio.sleep(0.1)

        # Confirm deletion
        await _should_see_testid(nicegui_user, "confirm-delete-btn")
        _click_testid(nicegui_user, "confirm-delete-btn")
        await asyncio.sleep(0.3)

        # Week should disappear
        await nicegui_user.should_not_see(content=week_title)


class TestDeleteUnitButtonVisibility:
    """Verify Delete Unit button visibility based on enrollment role."""

    @pytest.mark.asyncio
    async def test_visible_for_coordinator(self, nicegui_user: User) -> None:
        """Coordinator should see the Delete Unit button (AC6.2)."""
        email = "instructor@uni.edu"
        course_id, _code = await _create_course()
        await _enroll(course_id, email, "coordinator")

        await _authenticate(nicegui_user, email=email)
        await nicegui_user.open(f"/courses/{course_id}")

        await _should_see_testid(nicegui_user, "delete-unit-btn")

    @pytest.mark.asyncio
    async def test_hidden_for_instructor_role(self, nicegui_user: User) -> None:
        """Non-coordinator instructor should NOT see Delete Unit button (AC6.5).

        Steps:
        1. Create course.
        2. Enroll a coordinator (required to make the course accessible).
        3. Enroll a second user with "instructor" role.
        4. Authenticate as the instructor and open the course.
        5. Verify Delete Unit button is absent.
        """
        uid = uuid4().hex[:8]
        instructor_email = f"instr-{uid}@test.example.edu.au"

        course_id, code = await _create_course()
        # Course needs a coordinator (required by _resolve_course_detail)
        await _enroll(course_id, "coordinator@uni.edu", "coordinator")
        # Enroll the test user as instructor (not coordinator)
        await _enroll(course_id, instructor_email, "instructor")

        await _authenticate(nicegui_user, email=instructor_email)
        await nicegui_user.open(f"/courses/{course_id}")

        # Page should load (we see the course code as evidence)
        await nicegui_user.should_see(content=code)

        # Delete Unit button should NOT be visible
        await _should_not_see_testid(nicegui_user, "delete-unit-btn")

    @pytest.mark.asyncio
    async def test_delete_unit_redirects_to_course_list(
        self, nicegui_user: User
    ) -> None:
        """Confirming unit deletion navigates to /courses (AC6.2).

        Steps:
        1. Create course and enroll a coordinator.
        2. Authenticate and open the course detail page.
        3. Click the Delete Unit button.
        4. Confirm deletion in the dialog.
        5. Verify the user is redirected to /courses (back_history and page content).
        """
        email = "instructor@uni.edu"
        course_id, _code = await _create_course()
        await _enroll(course_id, email, "coordinator")

        await _authenticate(nicegui_user, email=email)
        await nicegui_user.open(f"/courses/{course_id}")

        # Delete Unit button must be present
        await _should_see_testid(nicegui_user, "delete-unit-btn")

        # Click delete unit
        _click_testid(nicegui_user, "delete-unit-btn")
        await asyncio.sleep(0.1)

        # Confirmation dialog must appear
        await _should_see_testid(nicegui_user, "confirm-delete-btn")

        # Confirm deletion
        _click_testid(nicegui_user, "confirm-delete-btn")

        # Wait for: DB deletion + on_success callback + background navigation task
        for _ in range(20):
            if (
                nicegui_user.back_history
                and nicegui_user.back_history[-1] == "/courses"
            ):
                break
            await asyncio.sleep(0.1)

        history = nicegui_user.back_history
        assert history[-1] == "/courses", (
            f"expected redirect to /courses, but back_history is {history!r}"
        )
        # The courses list renders with the "Units" page title
        await nicegui_user.should_see(content="Units")


# ---------------------------------------------------------------------------
# Workspace-level DB helpers
# ---------------------------------------------------------------------------


async def _create_activity(week_id: UUID, title: str = "Test Activity") -> UUID:
    """Create an activity in the given week. Returns activity_id."""
    from promptgrimoire.db.activities import create_activity

    activity = await create_activity(week_id=week_id, title=title)
    return activity.id


async def _clone_workspace(activity_id: UUID, user_id: UUID) -> UUID:
    """Clone the activity's template workspace for a user. Returns workspace_id."""
    from promptgrimoire.db.workspaces import clone_workspace_from_activity

    ws, _doc_map = await clone_workspace_from_activity(activity_id, user_id)
    return ws.id


# ---------------------------------------------------------------------------
# Workspace deletion tests
# ---------------------------------------------------------------------------


class TestWorkspaceDelete:
    """Verify workspace deletion from the course detail page.

    Acceptance Criteria:
    - crud-management-229.AC3.1: Owner can delete their workspace
    - crud-management-229.AC3.2: Confirmation dialog before deletion
    - crud-management-229.AC3.3: After deletion, activity shows "Start as Student"
    """

    @pytest.mark.asyncio
    async def test_delete_workspace_from_course_page(self, nicegui_user: User) -> None:
        """Delete a student workspace via UI and verify it reverts to start state.

        AC3.1: Owner can delete their workspace.
        AC3.2: Confirmation dialog appears before deletion.
        AC3.3: After deletion, "Start as Student" appears instead of "Resume".

        Steps:
        1. Create course + week + activity via DB.
        2. Enroll user as student.
        3. Clone a workspace for that user.
        4. Authenticate and open the course detail page.
        5. Verify "Resume" button is visible.
        6. Click the delete-workspace button.
        7. Verify confirmation dialog appears.
        8. Click confirm.
        9. Verify "Start as Student" appears (workspace gone).
        """
        course_id, _code = await _create_course()
        # Need a coordinator so _resolve_course_detail succeeds
        await _enroll(course_id, "coordinator@uni.edu", "coordinator")

        uid = uuid4().hex[:8]
        student_email = f"student-{uid}@test.example.edu.au"
        student_user_id = await _enroll(course_id, student_email, "student")

        week_id = await _create_week(course_id, title="Week with Activity")
        # Publish the week so students can see it
        from promptgrimoire.db.weeks import publish_week

        await publish_week(week_id)
        activity_id = await _create_activity(week_id, title="Activity to Test")
        ws_id = await _clone_workspace(activity_id, student_user_id)

        await _authenticate(nicegui_user, email=student_email)
        await nicegui_user.open(f"/courses/{course_id}")

        # Resume button should be visible (user has a workspace)
        await _should_see_testid(nicegui_user, f"resume-btn-{activity_id}")

        # Click the delete-workspace button
        _click_testid(nicegui_user, f"delete-workspace-btn-{ws_id}")
        await asyncio.sleep(0.1)

        # Confirmation dialog should appear
        await _should_see_testid(nicegui_user, "confirm-delete-workspace-btn")
        await _should_see_testid(nicegui_user, "cancel-delete-workspace-btn")

        # Click confirm
        _click_testid(nicegui_user, "confirm-delete-workspace-btn")

        # Wait for async delete + refreshable rebuild
        for _ in range(20):
            if (
                _find_by_testid(
                    nicegui_user,
                    f"start-activity-btn-{activity_id}",
                )
                is not None
            ):
                break
            await asyncio.sleep(0.15)

        # After deletion, "Start as Student" button should appear
        await _should_see_testid(nicegui_user, f"start-activity-btn-{activity_id}")

        # Resume button should be gone
        await _should_not_see_testid(nicegui_user, f"resume-btn-{activity_id}")

    @pytest.mark.asyncio
    async def test_non_owner_cannot_see_delete_button(self, nicegui_user: User) -> None:
        """Student B cannot see a delete button for student A's workspace (AC3.4).

        The delete-workspace button is only rendered inside the
        ``if act.id in user_workspace_map:`` branch in ``_render_activity_row``,
        which is keyed to the *viewing* user's own workspaces.  A student who
        has not yet started an activity never enters that branch, so they will
        see "Start as Student" with no delete button — even if a peer has
        already cloned the same activity.

        Steps:
        1. Create course + week + activity.
        2. Enroll student A and have them clone a workspace.
        3. Enroll student B (no workspace).
        4. Authenticate as student B and open the course page.
        5. Verify no delete-workspace button for student A's workspace exists.
        6. Verify "Start as Student" is shown (student B's view).
        """
        course_id, _code = await _create_course()
        await _enroll(course_id, "coordinator@uni.edu", "coordinator")

        uid = uuid4().hex[:8]
        student_a_email = f"student-a-{uid}@test.example.edu.au"
        student_b_email = f"student-b-{uid}@test.example.edu.au"

        student_a_id = await _enroll(course_id, student_a_email, "student")
        await _enroll(course_id, student_b_email, "student")

        week_id = await _create_week(course_id, title="Shared Week")
        from promptgrimoire.db.weeks import publish_week

        await publish_week(week_id)
        activity_id = await _create_activity(week_id, title="Shared Activity")

        # Student A clones a workspace
        ws_id = await _clone_workspace(activity_id, student_a_id)

        # Authenticate as student B (no workspace)
        await _authenticate(nicegui_user, email=student_b_email)
        await nicegui_user.open(f"/courses/{course_id}")

        # Student B sees Start as Student, not Resume
        await _should_see_testid(nicegui_user, f"start-activity-btn-{activity_id}")

        # Student A's delete button is NOT visible to student B
        await _should_not_see_testid(nicegui_user, f"delete-workspace-btn-{ws_id}")

    # NOTE(AC3.2 navigator gap): Full navigator delete-from-card flow is not
    # tested here because the NiceGUI User harness cannot drive the full
    # navigator query stack (UNION ALL CTE across multiple tables) without
    # standing up additional fixtures that duplicate existing integration
    # coverage.  The function signature and existence are verified by
    # tests/unit/test_navigator_delete.py.  Manual UAT covers the full flow.
