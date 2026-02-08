"""Course management pages.

Routes:
- /courses - List courses (instructors see all, students see enrolled)
- /courses/new - Create a new course (instructors only)
- /courses/{id} - View course details with weeks
- /courses/{id}/weeks/new - Add a week (instructors only)
- /courses/{id}/weeks/{week_id}/activities/new - Add an activity (instructors only)

Route: /courses
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode
from uuid import UUID

from nicegui import app, ui

from promptgrimoire.db.activities import create_activity, list_activities_for_week
from promptgrimoire.db.courses import (
    create_course,
    enroll_user,
    get_course_by_id,
    get_enrollment,
    list_course_enrollments,
    list_courses,
    list_user_enrollments,
    unenroll_user,
)
from promptgrimoire.db.engine import init_db
from promptgrimoire.db.models import CourseRole
from promptgrimoire.db.users import find_or_create_user, get_user_by_id
from promptgrimoire.db.weeks import (
    create_week,
    get_visible_weeks,
    list_weeks,
    publish_week,
    unpublish_week,
)
from promptgrimoire.pages.registry import page_route

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

# Track connected clients per course for broadcasting updates
# course_id -> {client_id -> weeks_list_refresh_func}
_course_clients: dict[UUID, dict[str, Callable[[], Any]]] = {}


def _broadcast_weeks_refresh(
    course_id: UUID, exclude_client: str | None = None
) -> None:
    """Broadcast weeks list refresh to all clients viewing a course."""
    if course_id not in _course_clients:
        return

    for client_id, refresh_func in list(_course_clients[course_id].items()):
        if client_id != exclude_client:
            try:
                refresh_func()
            except Exception:
                # Client may have disconnected
                _course_clients[course_id].pop(client_id, None)


def _get_current_user() -> dict | None:
    """Get current authenticated user from session storage."""
    return app.storage.user.get("auth_user")


def _get_user_id() -> UUID | None:
    """Get local User UUID from session."""
    user = _get_current_user()
    if user and user.get("user_id"):
        return UUID(user["user_id"])
    return None


def _is_admin() -> bool:
    """Check if current user is an admin."""
    user = _get_current_user()
    return bool(user and user.get("is_admin"))


def _is_db_available() -> bool:
    """Check if database is configured."""
    return bool(os.environ.get("DATABASE_URL"))


async def _check_auth() -> bool:
    """Check authentication and redirect if not logged in."""
    if not _get_current_user():
        ui.navigate.to("/login")
        return False
    return True


@page_route("/courses", title="Courses", icon="school", order=20)
async def courses_list_page() -> None:
    """List courses page."""
    if not await _check_auth():
        return

    if not _is_db_available():
        ui.label("Database not configured").classes("text-red-500")
        return

    await init_db()

    user_id = _get_user_id()
    if not user_id:
        ui.label(
            "User not found in local database. Please log out and log in again."
        ).classes("text-red-500")
        return

    ui.label("Courses").classes("text-2xl font-bold mb-4")

    # Get enrolled courses for this user
    enrollments = await list_user_enrollments(user_id)
    enrollment_map = {e.course_id: e for e in enrollments}

    # Check if user is instructor in any course (or is org admin)
    is_instructor = _is_admin() or any(
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

    await init_db()

    user_id = _get_user_id()
    if not user_id:
        ui.label(
            "User not found in local database. Please log out and log in again."
        ).classes("text-red-500")
        return

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
        await enroll_user(
            course_id=course.id,
            user_id=user_id,
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

    await init_db()

    try:
        cid = UUID(course_id)
    except ValueError:
        ui.label("Invalid course ID").classes("text-red-500")
        return

    # Track this client for broadcasting updates
    await ui.context.client.connected()
    client = ui.context.client
    client_id = str(id(client))

    course = await get_course_by_id(cid)
    if not course:
        ui.label("Course not found").classes("text-red-500")
        return

    user_id = _get_user_id()
    if not user_id:
        ui.label(
            "User not found in local database. Please log out and log in again."
        ).classes("text-red-500")
        return

    enrollment = await get_enrollment(course_id=cid, user_id=user_id)

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

    # Weeks list - refreshable for in-place updates
    ui.label("Weeks").classes("text-xl font-semibold mb-2")

    @ui.refreshable
    async def weeks_list() -> None:
        """Render the weeks list with publish/unpublish controls."""
        weeks = await get_visible_weeks(course_id=cid, user_id=user_id)

        if not weeks:
            ui.label("No weeks available yet.").classes("text-gray-500")
            return

        with ui.column().classes("gap-2 w-full max-w-2xl"):
            for week in weeks:
                with ui.card().classes("w-full"):
                    with ui.row().classes("items-center justify-between w-full"):
                        with ui.column().classes("gap-1"):
                            ui.label(f"Week {week.week_number}: {week.title}").classes(
                                "font-semibold"
                            )
                            if can_view_drafts:
                                status = "Published" if week.is_published else "Draft"
                                if week.visible_from:
                                    date_str = week.visible_from.strftime("%Y-%m-%d")
                                    status += f" (visible from {date_str})"
                                ui.label(status).classes("text-sm text-gray-500")

                        if can_manage:
                            with ui.row().classes("gap-1"):
                                if week.is_published:

                                    async def unpub(wid: UUID = week.id) -> None:
                                        await unpublish_week(wid)
                                        weeks_list.refresh()
                                        _broadcast_weeks_refresh(cid, client_id)

                                    ui.button("Unpublish", on_click=unpub).props(
                                        "flat dense"
                                    )
                                else:

                                    async def pub(wid: UUID = week.id) -> None:
                                        await publish_week(wid)
                                        weeks_list.refresh()
                                        _broadcast_weeks_refresh(cid, client_id)

                                    ui.button("Publish", on_click=pub).props(
                                        "flat dense"
                                    )

                    # Activity list under each week
                    activities = await list_activities_for_week(week.id)
                    if activities:
                        with ui.column().classes("ml-4 gap-1 mt-2"):
                            for act in activities:
                                with ui.row().classes("items-center gap-2"):
                                    ui.icon("assignment").classes("text-gray-400")
                                    _qs = urlencode(
                                        {"workspace_id": str(act.template_workspace_id)}
                                    )
                                    ui.link(
                                        act.title,
                                        f"/annotation?{_qs}",
                                    ).classes("text-sm")
                    elif can_manage:
                        ui.label("No activities yet").classes(
                            "text-xs text-gray-400 ml-4 mt-1"
                        )

                    if can_manage:
                        ui.button(
                            "Add Activity",
                            on_click=lambda wid=week.id: ui.navigate.to(
                                f"/courses/{course_id}/weeks/{wid}/activities/new"
                            ),
                        ).props("flat dense size=sm").classes("ml-4 mt-1")

    await weeks_list()

    # Register this client for receiving broadcasts
    if cid not in _course_clients:
        _course_clients[cid] = {}
    _course_clients[cid][client_id] = weeks_list.refresh

    # Cleanup on disconnect
    def on_disconnect() -> None:
        if cid in _course_clients:
            _course_clients[cid].pop(client_id, None)
            if not _course_clients[cid]:
                del _course_clients[cid]

    client.on_disconnect(on_disconnect)


@ui.page("/courses/{course_id}/weeks/new")
async def create_week_page(course_id: str) -> None:
    """Create a new week page."""
    if not await _check_auth():
        return

    if not _is_db_available():
        ui.label("Database not configured").classes("text-red-500")
        return

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

    user_id = _get_user_id()
    if not user_id:
        ui.label(
            "User not found in local database. Please log out and log in again."
        ).classes("text-red-500")
        return

    enrollment = await get_enrollment(course_id=cid, user_id=user_id)

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


@ui.page("/courses/{course_id}/weeks/{week_id}/activities/new")
async def create_activity_page(course_id: str, week_id: str) -> None:
    """Create a new activity page."""
    if not await _check_auth():
        return

    if not _is_db_available():
        ui.label("Database not configured").classes("text-red-500")
        return

    await init_db()

    try:
        cid = UUID(course_id)
        wid = UUID(week_id)
    except ValueError:
        ui.label("Invalid course or week ID").classes("text-red-500")
        return

    course = await get_course_by_id(cid)
    if not course:
        ui.label("Course not found").classes("text-red-500")
        return

    user_id = _get_user_id()
    if not user_id:
        ui.label(
            "User not found in local database. Please log out and log in again."
        ).classes("text-red-500")
        return

    enrollment = await get_enrollment(course_id=cid, user_id=user_id)

    if not enrollment or enrollment.role not in (
        CourseRole.coordinator,
        CourseRole.instructor,
    ):
        ui.label("Only instructors can add activities").classes("text-red-500")
        return

    ui.label(f"Add Activity to {course.code}").classes("text-2xl font-bold mb-4")

    title = ui.input(
        "Title", placeholder="e.g., Annotate Becky Bennett Interview"
    ).classes("w-96")
    description = ui.textarea(
        "Description (optional)",
        placeholder="Markdown description of the activity",
    ).classes("w-96")

    async def submit() -> None:
        if not title.value:
            ui.notify("Title is required", type="negative")
            return

        await create_activity(
            week_id=wid,
            title=title.value,
            description=description.value or None,
        )

        ui.notify(f"Created activity: {title.value}", type="positive")
        _broadcast_weeks_refresh(cid)
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

    user_id = _get_user_id()
    if not user_id:
        ui.label(
            "User not found in local database. Please log out and log in again."
        ).classes("text-red-500")
        return

    enrollment = await get_enrollment(course_id=cid, user_id=user_id)

    if not enrollment or enrollment.role not in (
        CourseRole.coordinator,
        CourseRole.instructor,
    ):
        ui.label("Only instructors can manage enrollments").classes("text-red-500")
        return

    ui.label(f"Enrollments for {course.code}").classes("text-2xl font-bold mb-4")

    # Enrollments list - refreshable for in-place updates
    @ui.refreshable
    async def enrollments_list() -> None:
        """Render the enrollments list with add/remove controls."""
        enrollments = await list_course_enrollments(cid)

        if not enrollments:
            ui.label("No enrollments").classes("text-gray-500")
            return

        with ui.column().classes("gap-2 w-full max-w-2xl"):
            for e in enrollments:
                # Look up user for display
                enrolled_user = await get_user_by_id(e.user_id)
                display_name = (
                    enrolled_user.display_name if enrolled_user else "Unknown"
                )
                email = enrolled_user.email if enrolled_user else str(e.user_id)

                with ui.card().classes("w-full"):
                    with ui.row().classes("items-center justify-between w-full"):
                        with ui.column().classes("gap-1"):
                            ui.label(display_name).classes("font-semibold")
                            ui.label(email).classes("text-sm text-gray-500")
                            ui.label(
                                f"Enrolled: {e.created_at.strftime('%Y-%m-%d')}"
                            ).classes("text-xs text-gray-400")
                        with ui.row().classes("gap-2 items-center"):
                            ui.badge(e.role.value)

                            async def remove(uid: UUID = e.user_id) -> None:
                                await unenroll_user(course_id=cid, user_id=uid)
                                ui.notify("Enrollment removed", type="positive")
                                enrollments_list.refresh()

                            ui.button(icon="delete", on_click=remove).props(
                                "flat round dense color=negative"
                            )

    # Add enrollment form - now uses email to find or create user
    with ui.card().classes("mb-4 p-4"):
        ui.label("Add Enrollment").classes("font-semibold mb-2")
        ui.label(
            "Enter email address. User will be created if they don't exist yet."
        ).classes("text-sm text-gray-500 mb-2")
        with ui.row().classes("gap-2 items-end"):
            new_email = ui.input("Email Address").classes("w-64")
            new_role = ui.select(
                options=[r.value for r in CourseRole],
                value=CourseRole.student.value,
                label="Role",
            ).classes("w-32")

            async def add_enrollment() -> None:
                if not new_email.value:
                    ui.notify("Email is required", type="negative")
                    return

                # Find or create user by email
                new_user, created = await find_or_create_user(
                    email=new_email.value,
                    display_name=new_email.value.split("@")[0],
                )

                try:
                    await enroll_user(
                        course_id=cid,
                        user_id=new_user.id,
                        role=CourseRole(new_role.value),
                    )
                    msg = "Enrollment added"
                    if created:
                        msg += " (new user created)"
                    ui.notify(msg, type="positive")
                    new_email.value = ""  # Clear input after add
                    enrollments_list.refresh()
                except Exception as e:
                    ui.notify(f"Failed to enroll: {e}", type="negative")

            ui.button("Add", on_click=add_enrollment)

    # Render the enrollments list
    await enrollments_list()

    ui.button(
        "Back to Course", on_click=lambda: ui.navigate.to(f"/courses/{course_id}")
    ).classes("mt-4")
