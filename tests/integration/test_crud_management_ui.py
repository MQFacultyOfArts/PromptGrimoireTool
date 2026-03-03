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
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from nicegui import ElementFilter
from nicegui.element import Element
from nicegui.testing.user_simulation import user_simulation

from promptgrimoire.config import get_settings

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

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

_MAIN_FILE = Path(__file__).parent / "nicegui_test_app.py"


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

    for listener in el._event_listeners.values():
        if listener.element_id != el.id:
            continue
        event_arguments = events.GenericEventArguments(
            sender=el, client=el.client, args=None
        )
        events.handle_event(listener.handler, event_arguments)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def user() -> AsyncGenerator[User]:
    """Yield a NiceGUI simulated User connected to the test app.

    Uses ``user_simulation(main_file=...)`` so all @ui.page routes
    registered by ``promptgrimoire.pages`` are available.
    """
    async with user_simulation(main_file=_MAIN_FILE) as u:
        yield u


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
    async def test_cancel_preserves_week(self, user: User) -> None:
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

        await _authenticate(user, email=email)
        await user.open(f"/courses/{course_id}")

        # The week header shows "Week 1: Week to Not Delete"
        await user.should_see(content=week_title)

        # Click the delete-week button
        _click_testid(user, f"delete-week-btn-{week_id}")
        await asyncio.sleep(0.1)

        # Confirmation dialog should be visible
        await _should_see_testid(user, "confirm-delete-btn")
        await _should_see_testid(user, "cancel-delete-btn")

        # Click cancel
        _click_testid(user, "cancel-delete-btn")
        await asyncio.sleep(0.1)

        # Dialog should close -- confirm button gone
        await _should_not_see_testid(user, "confirm-delete-btn")

        # Week should still be visible
        await user.should_see(content=week_title)


class TestDeleteWeekSuccess:
    """Verify that confirming delete actually removes the week."""

    @pytest.mark.asyncio
    async def test_delete_removes_week(self, user: User) -> None:
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

        await _authenticate(user, email=email)
        await user.open(f"/courses/{course_id}")

        await user.should_see(content=week_title)

        # Click delete
        _click_testid(user, f"delete-week-btn-{week_id}")
        await asyncio.sleep(0.1)

        # Confirm deletion
        await _should_see_testid(user, "confirm-delete-btn")
        _click_testid(user, "confirm-delete-btn")
        await asyncio.sleep(0.3)

        # Week should disappear
        await user.should_not_see(content=week_title)


class TestDeleteUnitButtonVisibility:
    """Verify Delete Unit button visibility based on enrollment role."""

    @pytest.mark.asyncio
    async def test_visible_for_coordinator(self, user: User) -> None:
        """Coordinator should see the Delete Unit button (AC6.2)."""
        email = "instructor@uni.edu"
        course_id, _code = await _create_course()
        await _enroll(course_id, email, "coordinator")

        await _authenticate(user, email=email)
        await user.open(f"/courses/{course_id}")

        await _should_see_testid(user, "delete-unit-btn")

    @pytest.mark.asyncio
    async def test_hidden_for_instructor_role(self, user: User) -> None:
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

        await _authenticate(user, email=instructor_email)
        await user.open(f"/courses/{course_id}")

        # Page should load (we see the course code as evidence)
        await user.should_see(content=code)

        # Delete Unit button should NOT be visible
        await _should_not_see_testid(user, "delete-unit-btn")
