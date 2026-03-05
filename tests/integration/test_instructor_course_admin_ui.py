"""NiceGUI User-harness tests for Course Admin UI flows.

Exercises the instructor workflow for creating and managing courses
using NiceGUI's simulated User — no browser required.

Acceptance Criteria:
- e2e-instructor-workflow-split.AC3.3: Exhaustive course/activity creation edge cases
- e2e-instructor-workflow-split.AC3.4: Tests run via nicegui_user, no Playwright

Traceability:
- Design: docs/implementation-plans/2026-03-04-e2e-instructor-workflow-split/phase_02.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest

from promptgrimoire.config import get_settings
from tests.integration.conftest import _authenticate
from tests.integration.nicegui_helpers import (
    _click_testid,
    _find_value_element_by_testid,
    _set_input_value,
    _should_not_see_testid,
    _should_see_testid,
    wait_for,
)

if TYPE_CHECKING:
    from nicegui.testing.user import User

pytestmark = [
    pytest.mark.skipif(
        not get_settings().dev.test_database_url,
        reason="DEV__TEST_DATABASE_URL not configured",
    ),
    # NiceGUI User harness runs in a dedicated UI lane outside xdist.
    pytest.mark.nicegui_ui,
]


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


async def _create_course() -> tuple[UUID, str]:
    """Create a course with a unique code. Returns (course_id, code)."""
    from promptgrimoire.db.courses import create_course

    uid = uuid4().hex[:8]
    code = f"ADM{uid.upper()}"
    course = await create_course(
        code=code, name=f"Admin Test {uid}", semester="2026-S1"
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


class TestCreateCourseValidation:
    """Verify Create Course form validation and success path (AC3.3)."""

    @pytest.mark.asyncio
    async def test_empty_fields_rejected(self, nicegui_user: User) -> None:
        """Submitting with empty fields should show a validation notification.

        Steps:
        1. Authenticate as instructor.
        2. Navigate to /courses/new.
        3. Click Create without filling any fields.
        4. Verify the "All fields are required" notification appears.
        """
        email = "instructor@uni.edu"
        await _authenticate(nicegui_user, email=email)
        await nicegui_user.open("/courses/new")

        # Page should show "Create New Unit"
        await nicegui_user.should_see(content="Create New Unit")

        # Click Create without filling fields
        _click_testid(nicegui_user, "create-course-btn")

        # Should see the validation notification
        await nicegui_user.should_see("All fields are required")

    @pytest.mark.asyncio
    async def test_create_course_success(self, nicegui_user: User) -> None:
        """Fill all fields and create a course successfully.

        Steps:
        1. Authenticate as instructor.
        2. Navigate to /courses/new.
        3. Fill in code, name, semester.
        4. Click Create.
        5. Verify navigation to the new course detail page.
        """
        email = "instructor@uni.edu"
        await _authenticate(nicegui_user, email=email)
        await nicegui_user.open("/courses/new")

        uid = uuid4().hex[:8]
        code = f"NEW{uid.upper()}"

        _set_input_value(nicegui_user, "course-code-input", code)
        _set_input_value(nicegui_user, "course-name-input", f"New Unit {uid}")
        _set_input_value(nicegui_user, "course-semester-input", "2026-S1")

        _click_testid(nicegui_user, "create-course-btn")

        # Wait for navigation to the course detail page
        await wait_for(
            lambda: (
                nicegui_user.back_history
                and "/courses/" in nicegui_user.back_history[-1]
                and nicegui_user.back_history[-1] != "/courses/new"
            )
        )

        # Should have navigated away from /courses/new
        history = nicegui_user.back_history
        assert history[-1] != "/courses/new", (
            f"expected navigation away from /courses/new, but history is {history!r}"
        )


class TestAddWeekAndPublish:
    """Verify adding a week and publishing it (AC3.3)."""

    @pytest.mark.asyncio
    async def test_add_week_and_publish(self, nicegui_user: User) -> None:
        """Create a week via the UI, then publish it.

        Steps:
        1. Create course + enroll coordinator via DB.
        2. Authenticate and open course detail page.
        3. Navigate to Add Week page.
        4. Fill in week number and title.
        5. Click Create.
        6. Verify navigation back to course detail.
        7. Re-open the course page, verify the week appears.
        8. Click Publish on the week.
        9. Verify the Unpublish button appears (indicating published state).
        """
        email = "instructor@uni.edu"
        course_id, _code = await _create_course()
        await _enroll(course_id, email, "coordinator")

        await _authenticate(nicegui_user, email=email)
        await nicegui_user.open(f"/courses/{course_id}")

        # Should see the course page with "No weeks available yet."
        await nicegui_user.should_see(content="Weeks")

        # Navigate to Add Week page
        await nicegui_user.open(f"/courses/{course_id}/weeks/new")
        await nicegui_user.should_see(content="Add Week")

        # Fill in the form (week_number already defaults to 1)
        _set_input_value(nicegui_user, "week-title-input", "Introduction Week")

        # Click Create
        _click_testid(nicegui_user, "create-week-btn")

        # Wait for navigation back to course detail
        await wait_for(
            lambda: (
                nicegui_user.back_history
                and nicegui_user.back_history[-1] == f"/courses/{course_id}"
            )
        )

        # Re-open the course detail page to see the week
        await nicegui_user.open(f"/courses/{course_id}")

        # Week should be visible
        await nicegui_user.should_see(content="Introduction Week")

        # Week should be in Draft state (not published yet)
        await nicegui_user.should_see(content="Draft")

        # Click Publish
        _click_testid(nicegui_user, "publish-week-btn")

        # After publishing, should see "Published" and the Unpublish button
        await _should_see_testid(nicegui_user, "unpublish-week-btn")


class TestAddActivity:
    """Verify adding an activity to a week (AC3.3)."""

    @pytest.mark.asyncio
    async def test_add_activity(self, nicegui_user: User) -> None:
        """Create an activity via the UI.

        Steps:
        1. Create course + enroll coordinator + create week via DB.
        2. Authenticate and open course detail page.
        3. Navigate to Add Activity page.
        4. Fill in title and description.
        5. Click Create.
        6. Verify navigation back to course detail.
        7. Re-open course page and verify the activity appears.
        """
        email = "instructor@uni.edu"
        course_id, _code = await _create_course()
        await _enroll(course_id, email, "coordinator")
        week_id = await _create_week(course_id, title="Week with Activity")

        # Publish the week so it appears in the course view
        from promptgrimoire.db.weeks import publish_week

        await publish_week(week_id)

        await _authenticate(nicegui_user, email=email)
        await nicegui_user.open(f"/courses/{course_id}")

        # Week should be visible
        await nicegui_user.should_see(content="Week with Activity")

        # Navigate to Add Activity page
        await nicegui_user.open(f"/courses/{course_id}/weeks/{week_id}/activities/new")
        await nicegui_user.should_see(content="Add Activity")

        # Fill in the form
        _set_input_value(nicegui_user, "activity-title-input", "Annotate Case Study")
        _set_input_value(
            nicegui_user,
            "activity-description-input",
            "Annotate the provided case study document.",
        )

        # Click Create
        _click_testid(nicegui_user, "create-activity-btn")

        # Wait for navigation back to course detail
        await wait_for(
            lambda: (
                nicegui_user.back_history
                and nicegui_user.back_history[-1] == f"/courses/{course_id}"
            )
        )

        # Re-open the course detail page to see the activity
        await nicegui_user.open(f"/courses/{course_id}")

        # Activity should be visible — use generous retries because the course
        # detail page runs multiple async DB queries (weeks + activities) that
        # may not complete within the default 0.3 s on resource-constrained CI.
        await nicegui_user.should_see(content="Annotate Case Study", retries=10)


class TestCourseSettingsCopyProtection:
    """Verify toggling course-level default copy protection (AC3.3)."""

    @pytest.mark.asyncio
    async def test_toggle_copy_protection(self, nicegui_user: User) -> None:
        """Open course settings and toggle the default copy protection switch.

        Steps:
        1. Create course + enroll coordinator via DB.
        2. Authenticate and open course detail page.
        3. Click Unit Settings button.
        4. Verify the settings dialog opens.
        5. Click the copy protection switch to toggle it.
        6. Click Save.
        7. Verify the settings dialog closes.
        8. Re-open settings and verify the switch reflects the saved state.
        """
        email = "instructor@uni.edu"
        course_id, _code = await _create_course()
        await _enroll(course_id, email, "coordinator")

        await _authenticate(nicegui_user, email=email)
        await nicegui_user.open(f"/courses/{course_id}")

        # Wait for the course detail page to fully render
        await _should_see_testid(nicegui_user, "course-settings-btn")

        # Click Unit Settings button
        _click_testid(nicegui_user, "course-settings-btn")

        # Settings dialog should be open with the title
        await _should_see_testid(nicegui_user, "course-settings-title")

        # Find the copy protection switch and read its current value
        cp_switch = _find_value_element_by_testid(
            nicegui_user, "course-default_copy_protection-switch"
        )
        assert cp_switch is not None, "copy protection switch not found"
        original_value = cp_switch.value

        # Click the switch to toggle it
        _click_testid(nicegui_user, "course-default_copy_protection-switch")

        # Verify the switch value changed
        def switch_value_changed() -> bool:
            switch = _find_value_element_by_testid(
                nicegui_user, "course-default_copy_protection-switch"
            )
            return switch is not None and switch.value != original_value

        await wait_for(switch_value_changed)

        cp_switch_after = _find_value_element_by_testid(
            nicegui_user, "course-default_copy_protection-switch"
        )
        assert cp_switch_after is not None
        assert cp_switch_after.value != original_value, (
            "expected switch value to toggle"
        )

        # Click Save
        _click_testid(nicegui_user, "save-course-settings-btn")

        # Dialog should close
        await _should_not_see_testid(nicegui_user, "course-settings-title")

        # Verify the "Unit settings saved" notification
        await nicegui_user.should_see("Unit settings saved")

        # Re-open settings to verify persistence
        _click_testid(nicegui_user, "course-settings-btn")
        await _should_see_testid(nicegui_user, "course-settings-title")

        cp_switch_reopened = _find_value_element_by_testid(
            nicegui_user, "course-default_copy_protection-switch"
        )
        assert cp_switch_reopened is not None
        assert cp_switch_reopened.value != original_value, (
            "expected toggled value to persist after save"
        )


class TestEnrollStudent:
    """Verify enrolling a student via the enrollment management page (AC3.3)."""

    @pytest.mark.asyncio
    async def test_enroll_student(self, nicegui_user: User) -> None:
        """Enroll a student via the enrollment form.

        Steps:
        1. Create course + enroll coordinator via DB.
        2. Authenticate and navigate to the enrollments page.
        3. Fill in student email in the enrollment form.
        4. Click Add.
        5. Verify the enrollment success notification.
        6. Verify the enrolled student appears in the list.
        """
        email = "instructor@uni.edu"
        course_id, _code = await _create_course()
        await _enroll(course_id, email, "coordinator")

        await _authenticate(nicegui_user, email=email)
        await nicegui_user.open(f"/courses/{course_id}/enrollments")

        # Should see the enrollments page
        await nicegui_user.should_see(content="Enrollments for")
        await nicegui_user.should_see(content="Add Enrollment")

        # Fill in student email
        uid = uuid4().hex[:8]
        student_email = f"student-{uid}@test.example.edu.au"
        _set_input_value(nicegui_user, "enrollment-email-input", student_email)

        # Click Add button
        _click_testid(nicegui_user, "add-enrollment-btn")

        # Should see success notification
        await nicegui_user.should_see("Enrollment added")

        # The enrolled student should appear in the list
        await nicegui_user.should_see(content=student_email)
