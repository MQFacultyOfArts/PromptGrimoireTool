"""Course management pages.

Routes:
- /courses - List courses (instructors see all, students see enrolled)
- /courses/new - Create a new course (instructors only)
- /courses/{id} - View course details with weeks
- /courses/{id}/weeks/new - Add a week (instructors only)

Route: /courses
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING
from uuid import UUID

from nicegui import app, ui

if TYPE_CHECKING:
    from promptgrimoire.db.models import Week


def _get_current_user() -> dict | None:
    """Get current authenticated user from session storage."""
    return app.storage.user.get("auth_user")


def _get_member_id() -> str | None:
    """Get Stytch member_id from session."""
    user = _get_current_user()
    if user:
        return user.get("member_id") or user.get("email")
    return None


def _is_db_available() -> bool:
    """Check if database is configured."""
    return bool(os.environ.get("DATABASE_URL"))


async def _check_auth() -> bool:
    """Check authentication and redirect if not logged in."""
    if not _get_current_user():
        ui.navigate.to("/login")
        return False
    return True


@ui.page("/courses")
async def courses_list_page() -> None:
    """List courses page."""
    if not await _check_auth():
        return

    if not _is_db_available():
        ui.label("Database not configured").classes("text-red-500")
        return

    from promptgrimoire.db.courses import list_courses, list_member_enrollments
    from promptgrimoire.db.engine import init_db
    from promptgrimoire.db.models import CourseRole

    await init_db()

    member_id = _get_member_id()

    ui.label("Courses").classes("text-2xl font-bold mb-4")

    # Get enrolled courses for this member
    enrollments = await list_member_enrollments(member_id) if member_id else []
    enrollment_map = {e.course_id: e for e in enrollments}

    # Check if user is instructor in any course (can create new courses)
    is_instructor = any(
        e.role in (CourseRole.coordinator, CourseRole.instructor) for e in enrollments
    )

    if is_instructor:
        ui.button(
            "New Course", on_click=lambda: ui.navigate.to("/courses/new")
        ).classes("mb-4")

    # List courses user is enrolled in
    courses = await list_courses()
    enrolled_courses = [c for c in courses if c.id in enrollment_map]

    if not enrolled_courses:
        ui.label("You are not enrolled in any courses.").classes("text-gray-500")
    else:
        with ui.column().classes("gap-2 w-full max-w-2xl"):
            for course in enrolled_courses:
                enrollment = enrollment_map[course.id]
                with (
                    ui.card()
                    .classes("w-full cursor-pointer hover:bg-gray-50")
                    .on("click", lambda c=course: ui.navigate.to(f"/courses/{c.id}"))
                ):
                    with ui.row().classes("items-center justify-between w-full"):
                        with ui.column().classes("gap-1"):
                            ui.label(f"{course.code} - {course.name}").classes(
                                "font-semibold"
                            )
                            ui.label(f"Semester: {course.semester}").classes(
                                "text-sm text-gray-500"
                            )
                        ui.badge(enrollment.role.value).classes("ml-2")


@ui.page("/courses/new")
async def create_course_page() -> None:
    """Create a new course page."""
    if not await _check_auth():
        return

    if not _is_db_available():
        ui.label("Database not configured").classes("text-red-500")
        return

    from promptgrimoire.db.courses import create_course, enroll_member
    from promptgrimoire.db.engine import init_db
    from promptgrimoire.db.models import CourseRole

    await init_db()

    ui.label("Create New Course").classes("text-2xl font-bold mb-4")

    code = ui.input("Course Code", placeholder="e.g., LAWS1100").classes("w-64")
    name = ui.input("Course Name", placeholder="e.g., Contracts").classes("w-64")
    semester = ui.input("Semester", placeholder="e.g., 2025-S1").classes("w-64")

    async def submit() -> None:
        if not code.value or not name.value or not semester.value:
            ui.notify("All fields are required", type="negative")
            return

        course = await create_course(
            code=code.value,
            name=name.value,
            semester=semester.value,
        )

        # Auto-enroll creator as coordinator
        member_id = _get_member_id()
        if member_id:
            await enroll_member(
                course_id=course.id,
                member_id=member_id,
                role=CourseRole.coordinator,
            )

        ui.notify(f"Created course: {course.code}", type="positive")
        ui.navigate.to(f"/courses/{course.id}")

    with ui.row().classes("gap-2 mt-4"):
        ui.button("Create", on_click=submit)
        ui.button("Cancel", on_click=lambda: ui.navigate.to("/courses")).props("flat")


@ui.page("/courses/{course_id}")
async def course_detail_page(course_id: str) -> None:
    """Course detail page with weeks."""
    if not await _check_auth():
        return

    if not _is_db_available():
        ui.label("Database not configured").classes("text-red-500")
        return

    from promptgrimoire.db.courses import get_course_by_id, get_enrollment
    from promptgrimoire.db.engine import init_db
    from promptgrimoire.db.models import CourseRole
    from promptgrimoire.db.weeks import get_visible_weeks

    await init_db()

    try:
        cid = UUID(course_id)
    except ValueError:
        ui.label("Invalid course ID").classes("text-red-500")
        return

    course = await get_course_by_id(cid)
    if not course:
        ui.label("Course not found").classes("text-red-500")
        return

    member_id = _get_member_id()
    enrollment = (
        await get_enrollment(course_id=cid, member_id=member_id) if member_id else None
    )

    if not enrollment:
        ui.label("You are not enrolled in this course").classes("text-red-500")
        return

    # Permission levels:
    # - can_manage: create weeks, manage enrollments (coordinator/instructor only)
    # - can_view_drafts: see unpublished weeks, publish/unpublish (includes tutors)
    can_manage = enrollment.role in (CourseRole.coordinator, CourseRole.instructor)
    can_view_drafts = enrollment.role in (
        CourseRole.coordinator,
        CourseRole.instructor,
        CourseRole.tutor,
    )

    # Header
    with ui.row().classes("items-center gap-4 mb-4"):
        ui.button(icon="arrow_back", on_click=lambda: ui.navigate.to("/courses")).props(
            "flat round"
        )
        ui.label(f"{course.code} - {course.name}").classes("text-2xl font-bold")
        ui.badge(enrollment.role.value)

    ui.label(f"Semester: {course.semester}").classes("text-gray-500 mb-4")

    # Week management for coordinators/instructors only
    if can_manage:
        with ui.row().classes("gap-2 mb-4"):
            ui.button(
                "Add Week",
                on_click=lambda: ui.navigate.to(f"/courses/{course_id}/weeks/new"),
            )
            ui.button(
                "Manage Enrollments",
                on_click=lambda: ui.navigate.to(f"/courses/{course_id}/enrollments"),
            ).props("flat")

    # Weeks list
    ui.label("Weeks").classes("text-xl font-semibold mb-2")

    weeks = (
        await get_visible_weeks(course_id=cid, member_id=member_id) if member_id else []
    )

    if not weeks:
        ui.label("No weeks available yet.").classes("text-gray-500")
    else:
        with ui.column().classes("gap-2 w-full max-w-2xl"):
            for week in weeks:
                await _render_week_card(week, can_view_drafts, can_manage)


async def _render_week_card(
    week: Week, can_view_drafts: bool, can_manage: bool
) -> None:
    """Render a week card.

    Args:
        week: The Week to render.
        can_view_drafts: Whether to show draft/published status.
        can_manage: Whether to show publish/unpublish buttons.
    """
    from promptgrimoire.db.weeks import publish_week, unpublish_week

    with ui.card().classes("w-full"):
        with ui.row().classes("items-center justify-between w-full"):
            with ui.column().classes("gap-1"):
                ui.label(f"Week {week.week_number}: {week.title}").classes(
                    "font-semibold"
                )
                if can_view_drafts:
                    status = "Published" if week.is_published else "Draft"
                    if week.visible_from:
                        status += (
                            f" (visible from {week.visible_from.strftime('%Y-%m-%d')})"
                        )
                    ui.label(status).classes("text-sm text-gray-500")

            if can_manage:
                with ui.row().classes("gap-1"):
                    if week.is_published:

                        async def unpub(wid=week.id) -> None:
                            await unpublish_week(wid)
                            ui.navigate.to(ui.context.client.page.path)

                        ui.button("Unpublish", on_click=unpub).props("flat dense")
                    else:

                        async def pub(wid=week.id) -> None:
                            await publish_week(wid)
                            ui.navigate.to(ui.context.client.page.path)

                        ui.button("Publish", on_click=pub).props("flat dense")


@ui.page("/courses/{course_id}/weeks/new")
async def create_week_page(course_id: str) -> None:
    """Create a new week page."""
    if not await _check_auth():
        return

    if not _is_db_available():
        ui.label("Database not configured").classes("text-red-500")
        return

    from promptgrimoire.db.courses import get_course_by_id, get_enrollment
    from promptgrimoire.db.engine import init_db
    from promptgrimoire.db.models import CourseRole
    from promptgrimoire.db.weeks import create_week, list_weeks

    await init_db()

    try:
        cid = UUID(course_id)
    except ValueError:
        ui.label("Invalid course ID").classes("text-red-500")
        return

    course = await get_course_by_id(cid)
    if not course:
        ui.label("Course not found").classes("text-red-500")
        return

    member_id = _get_member_id()
    enrollment = (
        await get_enrollment(course_id=cid, member_id=member_id) if member_id else None
    )

    if not enrollment or enrollment.role not in (
        CourseRole.coordinator,
        CourseRole.instructor,
    ):
        ui.label("Only instructors can add weeks").classes("text-red-500")
        return

    # Get existing weeks to suggest next week number
    existing_weeks = await list_weeks(course_id=cid)
    next_week_num = max((w.week_number for w in existing_weeks), default=0) + 1

    ui.label(f"Add Week to {course.code}").classes("text-2xl font-bold mb-4")

    week_number = ui.number("Week Number", value=next_week_num, min=1, max=52).classes(
        "w-32"
    )
    title = ui.input("Title", placeholder="e.g., Introduction to Contracts").classes(
        "w-64"
    )

    async def submit() -> None:
        if not title.value:
            ui.notify("Title is required", type="negative")
            return

        await create_week(
            course_id=cid,
            week_number=int(week_number.value),
            title=title.value,
        )

        ui.notify(f"Created Week {int(week_number.value)}", type="positive")
        ui.navigate.to(f"/courses/{course_id}")

    with ui.row().classes("gap-2 mt-4"):
        ui.button("Create", on_click=submit)
        ui.button(
            "Cancel", on_click=lambda: ui.navigate.to(f"/courses/{course_id}")
        ).props("flat")


@ui.page("/courses/{course_id}/enrollments")
async def manage_enrollments_page(course_id: str) -> None:
    """Manage course enrollments page."""
    if not await _check_auth():
        return

    if not _is_db_available():
        ui.label("Database not configured").classes("text-red-500")
        return

    from promptgrimoire.db.courses import (
        enroll_member,
        get_course_by_id,
        get_enrollment,
        list_course_enrollments,
        unenroll_member,
    )
    from promptgrimoire.db.engine import init_db
    from promptgrimoire.db.models import CourseRole

    await init_db()

    try:
        cid = UUID(course_id)
    except ValueError:
        ui.label("Invalid course ID").classes("text-red-500")
        return

    course = await get_course_by_id(cid)
    if not course:
        ui.label("Course not found").classes("text-red-500")
        return

    member_id = _get_member_id()
    enrollment = (
        await get_enrollment(course_id=cid, member_id=member_id) if member_id else None
    )

    if not enrollment or enrollment.role not in (
        CourseRole.coordinator,
        CourseRole.instructor,
    ):
        ui.label("Only instructors can manage enrollments").classes("text-red-500")
        return

    ui.label(f"Enrollments for {course.code}").classes("text-2xl font-bold mb-4")

    # Add enrollment form
    with ui.card().classes("mb-4 p-4"):
        ui.label("Add Enrollment").classes("font-semibold mb-2")
        with ui.row().classes("gap-2 items-end"):
            new_member_id = ui.input("Member ID or Email").classes("w-64")
            new_role = ui.select(
                "Role",
                options=[r.value for r in CourseRole],
                value=CourseRole.student.value,
            ).classes("w-32")

            async def add_enrollment() -> None:
                if not new_member_id.value:
                    ui.notify("Member ID is required", type="negative")
                    return
                await enroll_member(
                    course_id=cid,
                    member_id=new_member_id.value,
                    role=CourseRole(new_role.value),
                )
                ui.notify("Enrollment added", type="positive")
                ui.navigate.to(ui.context.client.page.path)

            ui.button("Add", on_click=add_enrollment)

    # List current enrollments
    enrollments = await list_course_enrollments(cid)

    if not enrollments:
        ui.label("No enrollments").classes("text-gray-500")
    else:
        with ui.column().classes("gap-2 w-full max-w-2xl"):
            for e in enrollments:
                with ui.card().classes("w-full"):
                    with ui.row().classes("items-center justify-between w-full"):
                        with ui.column().classes("gap-1"):
                            ui.label(e.member_id).classes("font-semibold")
                            ui.label(
                                f"Enrolled: {e.created_at.strftime('%Y-%m-%d')}"
                            ).classes("text-sm text-gray-500")
                        with ui.row().classes("gap-2 items-center"):
                            ui.badge(e.role.value)

                            async def remove(mid=e.member_id) -> None:
                                await unenroll_member(course_id=cid, member_id=mid)
                                ui.notify("Enrollment removed", type="positive")
                                ui.navigate.to(ui.context.client.page.path)

                            ui.button(icon="delete", on_click=remove).props(
                                "flat round dense color=negative"
                            )

    ui.button(
        "Back to Course", on_click=lambda: ui.navigate.to(f"/courses/{course_id}")
    ).classes("mt-4")
