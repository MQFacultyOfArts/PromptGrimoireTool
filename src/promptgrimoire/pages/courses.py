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
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode
from uuid import UUID

from nicegui import app, ui

from promptgrimoire.auth.anonymise import anonymise_author
from promptgrimoire.config import get_settings
from promptgrimoire.db.acl import list_peer_workspaces_with_owners
from promptgrimoire.db.activities import (
    create_activity,
    list_activities_for_week,
    update_activity,
)
from promptgrimoire.db.courses import (
    create_course,
    enroll_user,
    get_course_by_id,
    get_enrollment,
    list_course_enrollments,
    list_courses,
    list_students_without_workspaces,
    list_user_enrollments,
    unenroll_user,
    update_course,
)
from promptgrimoire.db.engine import init_db
from promptgrimoire.db.roles import get_all_roles, get_staff_roles
from promptgrimoire.db.users import find_or_create_user, get_user_by_id
from promptgrimoire.db.weeks import (
    create_week,
    get_visible_weeks,
    list_weeks,
    publish_week,
    unpublish_week,
)
from promptgrimoire.db.workspace_documents import workspaces_with_documents
from promptgrimoire.db.workspaces import (
    check_clone_eligibility,
    clone_workspace_from_activity,
    get_user_workspace_for_activity,
    resolve_tristate,
)
from promptgrimoire.pages.registry import page_route

if TYPE_CHECKING:
    from collections.abc import Callable

    from promptgrimoire.db.models import Activity, Course, Workspace

logger = logging.getLogger(__name__)

# -- Role sets for permission checks --
# Roles that can create weeks, manage enrollments, edit templates
_MANAGER_ROLES = frozenset({"coordinator", "instructor"})

# Track connected clients per course for broadcasting updates
# course_id -> {client_id -> weeks_list_refresh_func}
_course_clients: dict[UUID, dict[str, Callable[[], Any]]] = {}


async def _build_peer_map(
    activities: list[Activity],
    course: Course,
    user_id: UUID,
    is_staff: bool,
) -> dict[UUID, list[tuple[str, str, str]]]:
    """Build activity_id -> [(ws_id_str, title, display_name)] for peer workspaces.

    Pre-processes anonymisation so the renderer needs no domain imports.
    Returns empty dict for activities where sharing is disabled or no
    peers have shared.
    """
    peer_map: dict[UUID, list[tuple[str, str, str]]] = {}
    for act in activities:
        if not resolve_tristate(act.allow_sharing, course.default_allow_sharing):
            continue
        peers = await list_peer_workspaces_with_owners(act.id, user_id)
        if not peers:
            continue
        anon = resolve_tristate(act.anonymous_sharing, course.default_anonymous_sharing)
        peer_map[act.id] = [
            (
                str(ws.id),
                ws.title or "Untitled Workspace",
                anonymise_author(
                    author=name,
                    user_id=str(uid),
                    viewing_user_id=str(user_id),
                    anonymous_sharing=anon,
                    viewer_is_privileged=is_staff,
                    author_is_privileged=False,
                ),
            )
            for ws, name, uid in peers
        ]
    return peer_map


# -- Tri-state settings UI config --


def _tri_state_options(on_label: str = "On", off_label: str = "Off") -> dict[str, str]:
    """Build a tri-state options dict for activity settings selects."""
    return {"inherit": "Inherit from unit", "on": on_label, "off": off_label}


# (UI label, model attribute name, on_label, off_label)
_ACTIVITY_TRI_STATE_FIELDS: list[tuple[str, str, str, str]] = [
    ("Copy protection (overrides unit default)", "copy_protection", "On", "Off"),
    (
        "Allow sharing (overrides unit default)",
        "allow_sharing",
        "Allowed",
        "Not allowed",
    ),
    (
        "Allow tag creation (overrides unit default)",
        "allow_tag_creation",
        "Allowed",
        "Not allowed",
    ),
]

# (UI label, model attribute name)
_COURSE_DEFAULT_FIELDS: list[tuple[str, str]] = [
    ("Default copy protection", "default_copy_protection"),
    ("Default allow sharing", "default_allow_sharing"),
    ("Anonymous sharing by default", "default_anonymous_sharing"),
    ("Default allow tag creation", "default_allow_tag_creation"),
]

_ANONYMOUS_SHARING_OPTIONS: dict[str, str] = {
    "inherit": "Inherit from unit",
    "on": "Anonymous",
    "off": "Named",
}


def _model_to_ui(value: bool | None) -> str:
    """Convert model tri-state value to UI select key.

    None -> "inherit", True -> "on", False -> "off".
    """
    if value is None:
        return "inherit"
    return "on" if value else "off"


def _ui_to_model(value: str) -> bool | None:
    """Convert UI select key to model tri-state value.

    "inherit" -> None, "on" -> True, "off" -> False.
    """
    if value == "inherit":
        return None
    return value == "on"


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


async def open_course_settings(course: Course) -> None:
    """Open a dialog to edit course settings.

    Shows boolean switches for each default policy field, driven by
    _COURSE_DEFAULT_FIELDS config.
    """
    with ui.dialog() as dialog, ui.card().classes("w-96"):
        ui.label(f"Unit Settings: {course.name}").classes("text-lg font-bold")

        switches: dict[str, ui.switch] = {}
        for label, attr in _COURSE_DEFAULT_FIELDS:
            switches[attr] = ui.switch(label, value=getattr(course, attr))

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancel", on_click=dialog.close).props("flat")

            async def save() -> None:
                kwargs = {
                    attr: switches[attr].value for _, attr in _COURSE_DEFAULT_FIELDS
                }
                await update_course(course.id, **kwargs)
                for _, attr in _COURSE_DEFAULT_FIELDS:
                    setattr(course, attr, kwargs[attr])
                dialog.close()
                ui.notify("Unit settings saved", type="positive")

            ui.button("Save", on_click=save).props("color=primary")

    dialog.open()


async def open_activity_settings(activity: Activity) -> None:
    """Open a dialog to edit per-activity settings.

    Shows tri-state selects for each policy field, driven by
    _ACTIVITY_TRI_STATE_FIELDS config.
    """
    with ui.dialog() as dialog, ui.card().classes("w-96"):
        ui.label(f"Activity Settings: {activity.title}").classes("text-lg font-bold")

        selects: dict[str, ui.select] = {}
        for label, attr, on_text, off_text in _ACTIVITY_TRI_STATE_FIELDS:
            selects[attr] = ui.select(
                options=_tri_state_options(on_text, off_text),
                value=_model_to_ui(getattr(activity, attr)),
                label=label,
            ).classes("w-full")

        anon_select = ui.select(
            options=_ANONYMOUS_SHARING_OPTIONS,
            value=_model_to_ui(activity.anonymous_sharing),
            label="Anonymity (overrides unit default)",
        ).classes("w-full")

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancel", on_click=dialog.close).props("flat")

            async def save() -> None:
                kwargs = {
                    attr: _ui_to_model(selects[attr].value)
                    for _, attr, *_ in _ACTIVITY_TRI_STATE_FIELDS
                }
                # anonymous_sharing uses a custom options set, not in the loop
                kwargs["anonymous_sharing"] = _ui_to_model(anon_select.value)
                await update_activity(activity.id, **kwargs)  # type: ignore[invalid-argument-type]  -- kwargs keys are tri-state field names only
                for attr, value in kwargs.items():
                    setattr(activity, attr, value)
                dialog.close()
                ui.notify("Activity settings saved", type="positive")

            ui.button("Save", on_click=save).props("color=primary")

    dialog.open()


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
    return bool(get_settings().database.url)


async def _check_auth() -> bool:
    """Check authentication and redirect if not logged in."""
    if not _get_current_user():
        ui.navigate.to("/login")
        return False
    return True


@page_route("/courses", title="Units", icon="school", order=20)
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

    with ui.row().classes("items-center mb-4 gap-2"):
        ui.button(icon="home", on_click=lambda: ui.navigate.to("/")).props(
            "flat round"
        ).tooltip("Home")
        ui.label("Units").classes("text-2xl font-bold")

    # Get enrolled courses for this user
    enrollments = await list_user_enrollments(user_id)
    enrollment_map = {e.course_id: e for e in enrollments}

    # Check if user is instructor in any course (or is org admin)
    is_instructor = _is_admin() or any(e.role in _MANAGER_ROLES for e in enrollments)

    if is_instructor:
        ui.button("New Unit", on_click=lambda: ui.navigate.to("/courses/new")).classes(
            "mb-4"
        )

    # List courses user is enrolled in
    courses = await list_courses()
    enrolled_courses = [c for c in courses if c.id in enrollment_map]

    if not enrolled_courses:
        ui.label("You are not enrolled in any units.").classes("text-gray-500")
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
                        ui.badge(enrollment.role).classes("ml-2")


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

    ui.label("Create New Unit").classes("text-2xl font-bold mb-4")

    code = ui.input("Unit Code", placeholder="e.g., LAWS1100").classes("w-64")
    name = ui.input("Unit Name", placeholder="e.g., Contracts").classes("w-64")
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
            role="coordinator",
        )

        ui.notify(f"Created unit: {course.code}", type="positive")
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
        ui.label("Invalid unit ID").classes("text-red-500")
        return

    # Track this client for broadcasting updates
    await ui.context.client.connected()
    client = ui.context.client
    client_id = str(id(client))

    course = await get_course_by_id(cid)
    if not course:
        ui.label("Unit not found").classes("text-red-500")
        return

    user_id = _get_user_id()
    if not user_id:
        ui.label(
            "User not found in local database. Please log out and log in again."
        ).classes("text-red-500")
        return

    enrollment = await get_enrollment(course_id=cid, user_id=user_id)

    if not enrollment:
        ui.label("You are not enrolled in this unit").classes("text-red-500")
        return

    # Permission levels:
    # - can_manage: create weeks, manage enrollments (coordinator/instructor only)
    # - can_view_drafts: see unpublished weeks, publish/unpublish (includes tutors)
    can_manage = enrollment.role in _MANAGER_ROLES
    staff_roles = await get_staff_roles()
    can_view_drafts = enrollment.role in staff_roles

    # Header
    with ui.row().classes("items-center gap-4 mb-4"):
        ui.button(icon="home", on_click=lambda: ui.navigate.to("/")).props(
            "flat round"
        ).tooltip("Home")
        ui.button(icon="arrow_back", on_click=lambda: ui.navigate.to("/courses")).props(
            "flat round"
        )
        ui.label(f"{course.code} - {course.name}").classes("text-2xl font-bold")
        ui.badge(enrollment.role)
        if can_manage:
            ui.button(
                icon="settings",
                on_click=lambda: open_course_settings(course),
            ).props("flat round").tooltip("Settings")

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

    async def _build_user_workspace_map(
        activities: list[Activity], uid: UUID | None
    ) -> dict[UUID, Workspace]:
        """Build activity_id -> owned Workspace map for Resume detection.

        # TODO: Batch into single query if activity count per week grows
        """
        result: dict[UUID, Workspace] = {}
        if uid is None:
            return result
        for act in activities:
            existing = await get_user_workspace_for_activity(act.id, uid)
            if existing is not None:
                result[act.id] = existing
        return result

    def _render_activity_row(
        act: Activity,
        *,
        can_manage: bool,
        populated_templates: set[UUID],
        user_workspace_map: dict[UUID, Workspace],
        peer_workspaces: list[tuple[str, str, str]] | None = None,
    ) -> None:
        """Render a single Activity row with template/start or resume buttons."""
        with ui.row().classes("items-center gap-2"):
            ui.icon("assignment").classes("text-gray-400")
            ui.label(act.title).classes("text-sm font-medium")

            if can_manage:
                has_content = act.template_workspace_id in populated_templates
                btn_label = "Edit Template" if has_content else "Create Template"
                btn_icon = "edit" if has_content else "add"
                _qs = urlencode({"workspace_id": str(act.template_workspace_id)})
                ui.button(
                    btn_label,
                    icon=btn_icon,
                    on_click=lambda qs=_qs: ui.navigate.to(f"/annotation?{qs}"),
                ).props("flat dense size=sm color=secondary")
                ui.button(
                    icon="settings",
                    on_click=lambda a=act: open_activity_settings(a),
                ).props("flat round dense size=sm").tooltip("Settings")

            if act.id in user_workspace_map:
                # User already has a workspace — show Resume
                ws = user_workspace_map[act.id]
                qs = urlencode({"workspace_id": str(ws.id)})
                ui.button(
                    "Resume",
                    icon="play_arrow",
                    on_click=lambda q=qs: ui.navigate.to(f"/annotation?{q}"),
                ).props("flat dense size=sm color=primary")
            else:
                # No workspace yet — show Start Activity
                async def start_activity(aid: UUID = act.id) -> None:
                    uid = _get_user_id()
                    if uid is None:
                        ui.notify("Please log in to start an activity", type="warning")
                        return

                    existing = await get_user_workspace_for_activity(aid, uid)
                    if existing is not None:
                        qs = urlencode({"workspace_id": str(existing.id)})
                        ui.navigate.to(f"/annotation?{qs}")
                        return

                    error = await check_clone_eligibility(aid, uid)
                    if error is not None:
                        ui.notify(error, type="negative")
                        return

                    clone, _doc_map = await clone_workspace_from_activity(aid, uid)
                    qs = urlencode({"workspace_id": str(clone.id)})
                    ui.navigate.to(f"/annotation?{qs}")

                ui.button("Start Activity", on_click=start_activity).props(
                    "flat dense size=sm color=primary"
                )

        # Peer workspace list (gated by allow_sharing in _build_peer_map)
        if peer_workspaces:
            with ui.column().classes("ml-8 mt-1 gap-0"):
                ui.label("Peer Workspaces").classes("text-xs font-medium text-gray-500")
                for ws_id, title, display_name in peer_workspaces:
                    qs = urlencode({"workspace_id": ws_id})
                    with ui.row().classes("items-center gap-1"):
                        ui.icon("person").classes("text-gray-300 text-sm")
                        ui.link(
                            f"{display_name} — {title}",
                            target=f"/annotation?{qs}",
                        ).classes("text-xs text-blue-600")

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
                    # TODO: Batch into single query if week count grows
                    activities = await list_activities_for_week(week.id)
                    if activities:
                        populated = (
                            await workspaces_with_documents(
                                {a.template_workspace_id for a in activities}
                            )
                            if can_manage
                            else set()
                        )
                        ws_map = await _build_user_workspace_map(activities, user_id)
                        peer_map = await _build_peer_map(
                            activities, course, user_id, can_view_drafts
                        )
                        with ui.column().classes("ml-4 gap-1 mt-2"):
                            for act in activities:
                                _render_activity_row(
                                    act,
                                    can_manage=can_manage,
                                    populated_templates=populated,
                                    user_workspace_map=ws_map,
                                    peer_workspaces=peer_map.get(act.id),
                                )
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

    # Students with no workspaces (staff only)
    if can_view_drafts:
        no_work = await list_students_without_workspaces(cid)
        if no_work:
            with ui.expansion(
                f"Students with no work ({len(no_work)})",
                icon="warning",
            ).classes("w-full max-w-2xl mt-4"):
                with ui.element("ul").classes("ml-4"):
                    for name, email in no_work:
                        with ui.element("li"):
                            ui.label(f"{name} ({email})")

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
        ui.label("Invalid unit ID").classes("text-red-500")
        return

    course = await get_course_by_id(cid)
    if not course:
        ui.label("Unit not found").classes("text-red-500")
        return

    user_id = _get_user_id()
    if not user_id:
        ui.label(
            "User not found in local database. Please log out and log in again."
        ).classes("text-red-500")
        return

    enrollment = await get_enrollment(course_id=cid, user_id=user_id)

    if not enrollment or enrollment.role not in _MANAGER_ROLES:
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
        ui.label("Invalid unit or week ID").classes("text-red-500")
        return

    course = await get_course_by_id(cid)
    if not course:
        ui.label("Unit not found").classes("text-red-500")
        return

    user_id = _get_user_id()
    if not user_id:
        ui.label(
            "User not found in local database. Please log out and log in again."
        ).classes("text-red-500")
        return

    enrollment = await get_enrollment(course_id=cid, user_id=user_id)

    if not enrollment or enrollment.role not in _MANAGER_ROLES:
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
        ui.label("Invalid unit ID").classes("text-red-500")
        return

    course = await get_course_by_id(cid)
    if not course:
        ui.label("Unit not found").classes("text-red-500")
        return

    user_id = _get_user_id()
    if not user_id:
        ui.label(
            "User not found in local database. Please log out and log in again."
        ).classes("text-red-500")
        return

    enrollment = await get_enrollment(course_id=cid, user_id=user_id)

    if not enrollment or enrollment.role not in _MANAGER_ROLES:
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
                            ui.badge(e.role)

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
        all_roles = list(await get_all_roles())
        with ui.row().classes("gap-2 items-end"):
            new_email = ui.input("Email Address").classes("w-64")
            new_role = ui.select(
                options=all_roles,
                value="student",
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
                        role=new_role.value,
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
        "Back to Unit", on_click=lambda: ui.navigate.to(f"/courses/{course_id}")
    ).classes("mt-4")
