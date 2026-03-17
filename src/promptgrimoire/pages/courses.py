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
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple
from urllib.parse import urlencode
from uuid import UUID

import structlog
from nicegui import app, ui

from promptgrimoire.auth import is_privileged_user
from promptgrimoire.auth.anonymise import anonymise_author
from promptgrimoire.config import get_settings
from promptgrimoire.db.acl import list_peer_workspaces_with_owners
from promptgrimoire.db.activities import (
    create_activity,
    delete_activity,
    list_activities_for_week,
    update_activity,
)
from promptgrimoire.db.courses import (
    create_course,
    delete_course,
    enroll_user,
    get_course_by_id,
    get_enrollment,
    list_courses,
    list_enrollment_rows,
    list_students_without_workspaces,
    list_user_enrollments,
    unenroll_user,
    update_course,
)
from promptgrimoire.db.engine import init_db
from promptgrimoire.db.enrolment import StudentIdConflictError, bulk_enrol
from promptgrimoire.db.exceptions import DeletionBlockedError
from promptgrimoire.db.roles import get_all_roles, get_staff_roles
from promptgrimoire.db.users import find_or_create_user
from promptgrimoire.db.weeks import (
    create_week,
    delete_week,
    get_visible_weeks,
    get_week_by_id,
    list_weeks,
    publish_week,
    unpublish_week,
    update_week,
)
from promptgrimoire.db.workspace_documents import workspaces_with_documents
from promptgrimoire.db.workspaces import (
    check_clone_eligibility,
    clone_workspace_from_activity,
    delete_workspace,
    get_user_workspace_for_activity,
    has_student_workspaces,
    resolve_tristate,
)
from promptgrimoire.enrol.xlsx_parser import EnrolmentParseError, parse_xlsx
from promptgrimoire.pages.layout import page_layout
from promptgrimoire.pages.registry import page_route
from promptgrimoire.pages.ui_helpers import add_option_testids

logger = structlog.get_logger()
logging.getLogger(__name__).setLevel(logging.INFO)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from promptgrimoire.db.models import (
        Activity,
        Course,
        CourseEnrollment,
        Week,
        Workspace,
    )


class _CourseDetailContext(NamedTuple):
    """Resolved context for the course detail page."""

    cid: UUID
    course: Course
    user_id: UUID
    enrollment: CourseEnrollment
    can_manage: bool
    can_view_drafts: bool
    client_id: str


_CSS_FILE = Path(__file__).resolve().parent.parent / "static" / "courses.css"

# -- Role sets for permission checks --
# Roles that can create weeks, manage enrollments, edit templates
_MANAGER_ROLES = frozenset({"coordinator", "instructor"})

# Track connected clients per course for broadcasting updates
# course_id -> {client_id -> weeks_list_refresh_func}
_course_clients: dict[UUID, dict[str, Callable[[], Any]]] = {}


async def _confirm_and_delete(
    *,
    entity_label: str,
    delete_fn: Callable[..., Any],
    entity_id: UUID,
    is_admin: bool,
    on_success: Callable[[], Any],
) -> None:
    """Show confirmation dialog, call delete_fn, handle DeletionBlockedError.

    For admins, offers force-delete when blocked by student workspaces.
    """

    async def _do_delete(*, force: bool = False) -> None:
        try:
            await delete_fn(entity_id, force=force)
        except DeletionBlockedError as e:
            logger.warning(
                "deletion_blocked",
                operation="delete_entity",
                student_workspace_count=e.student_workspace_count,
            )
            msg = f"Cannot delete: {e.student_workspace_count} student workspaces exist"
            ui.notify(msg, type="warning")
            if is_admin:
                _show_force_dialog(e.student_workspace_count)
            return
        ui.notify(
            f"Deleted {entity_label}",
            type="positive",
        )
        on_success()

    def _show_force_dialog(count: int) -> None:
        async def _force_delete_click() -> None:
            await _do_delete(force=True)

        with (
            ui.dialog() as force_dlg,
            ui.card().classes("w-96"),
        ):
            ui.label(
                f"Force delete will remove {count}"
                " student workspaces."
                " This cannot be undone."
            ).classes("text-body1")
            with ui.row().classes("justify-end w-full gap-2 mt-4"):
                ui.button(
                    "Cancel",
                    on_click=force_dlg.close,
                ).props('flat data-testid="cancel-force-delete-btn"')
                ui.button(
                    "Force Delete",
                    on_click=_force_delete_click,
                ).props('color=negative data-testid="force-delete-btn"')
        force_dlg.open()

    with (
        ui.dialog() as dlg,
        ui.card().classes("w-96"),
    ):
        ui.label(f"Delete {entity_label}? This cannot be undone.").classes("text-body1")
        with ui.row().classes("justify-end w-full gap-2 mt-4"):
            ui.button(
                "Cancel",
                on_click=dlg.close,
            ).props('flat data-testid="cancel-delete-btn"')
            ui.button(
                "Delete",
                on_click=_do_delete,
            ).props('color=negative data-testid="confirm-delete-btn"')
    dlg.open()


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


async def _start_activity_handler(aid: UUID) -> None:
    """Clone template workspace and navigate to annotation page.

    Used as the on_click handler for "Start Activity" buttons.
    """
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


async def _handle_edit_template(activity_id: UUID, template_workspace_id: UUID) -> None:
    """Navigate to template workspace, showing clone warning if students have cloned."""
    qs = urlencode({"workspace_id": str(template_workspace_id)})
    count = await has_student_workspaces(activity_id)
    if not count:
        ui.navigate.to(f"/annotation?{qs}")
        return

    with (
        ui.dialog() as dialog,
        ui.card().classes("w-96").props('data-testid="template-clone-warning-dialog"'),
    ):
        ui.label(
            f"{count} student(s) have cloned this template. "
            "Changes won't propagate to existing copies."
        ).classes("text-body1")
        with ui.row().classes("justify-end w-full gap-2 mt-4"):
            ui.button(
                "Cancel",
                on_click=dialog.close,
            ).props('flat data-testid="template-clone-warning-cancel-btn"')
            ui.button(
                "Continue",
                on_click=lambda q=qs: ui.navigate.to(f"/annotation?{q}"),
            ).props('color=primary data-testid="template-clone-warning-continue-btn"')
    dialog.open()


async def _handle_delete_workspace(
    workspace_id: UUID,
    *,
    on_success: Callable[[], Any],
) -> None:
    """Show confirmation dialog and delete a workspace."""
    with ui.dialog() as dialog, ui.card().classes("w-96"):
        ui.label("Delete your workspace?").classes("text-lg font-bold")
        ui.label("You can start fresh by cloning again.").classes("text-gray-500")
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancel", on_click=dialog.close).props(
                'flat data-testid="cancel-delete-workspace-btn"'
            )

            async def confirm() -> None:
                user_id = _get_user_id()
                if user_id is None:
                    ui.notify("Not logged in", type="negative")
                    dialog.close()
                    return
                try:
                    await delete_workspace(workspace_id, user_id=user_id)
                except PermissionError:
                    logger.warning("permission_denied", operation="delete_workspace")
                    ui.notify("Permission denied", type="negative")
                    dialog.close()
                    return
                dialog.close()
                ui.notify("Workspace deleted. You can start fresh.", type="positive")
                on_success()

            ui.button("Delete", on_click=confirm).props(
                'color=negative data-testid="confirm-delete-workspace-btn"'
            )
    dialog.open()


def _render_activity_management_controls(
    act: Activity,
    *,
    populated_templates: set[UUID],
    on_edit: Callable[[Activity], Any] | None = None,
    on_delete: Callable[[Activity], Any] | None = None,
) -> None:
    """Render template, edit, settings, and delete buttons for an activity."""
    has_content = act.template_workspace_id in populated_templates
    btn_label = "Edit Template" if has_content else "Create Template"
    btn_icon = "edit" if has_content else "add"
    ui.button(
        btn_label,
        icon=btn_icon,
        on_click=lambda a=act: _handle_edit_template(a.id, a.template_workspace_id),
    ).props(
        f"unelevated color=blue-1 text-color=primary dense"
        f' data-testid="template-btn-{act.id}"'
    )
    if on_edit is not None:
        ui.button(
            "Edit",
            icon="edit",
            on_click=lambda a=act: on_edit(a),
        ).props(
            f"unelevated color=grey-2 text-color=grey-9 dense"
            f' data-testid="edit-activity-btn-{act.id}"'
        )
    ui.button(
        "Activity Settings",
        icon="settings",
        on_click=lambda a=act: open_activity_settings(a),
    ).props(
        "unelevated color=grey-2 text-color=grey-9 dense"
        ' data-testid="activity-settings-btn"'
    )
    if on_delete is not None:
        ui.button(
            "Delete",
            icon="delete",
            on_click=lambda a=act: on_delete(a),
        ).props(
            f'outline color=negative dense data-testid="delete-activity-btn-{act.id}"'
        )


def _render_activity_row(
    act: Activity,
    *,
    can_manage: bool,
    populated_templates: set[UUID],
    user_workspace_map: dict[UUID, Workspace],
    peer_workspaces: list[tuple[str, str, str]] | None = None,
    on_edit: Callable[[Activity], Any] | None = None,
    on_delete: Callable[[Activity], Any] | None = None,
    on_delete_workspace: Callable[[UUID], Any] | None = None,
) -> None:
    """Render a single Activity row with buttons."""
    with (
        ui.row()
        .classes("items-center gap-2")
        .props(f'data-testid="activity-row-{act.id}"')
    ):
        ui.icon("assignment").classes("text-gray-400")
        ui.label(act.title).classes("text-sm font-medium")

        if can_manage:
            _render_activity_management_controls(
                act,
                populated_templates=populated_templates,
                on_edit=on_edit,
                on_delete=on_delete,
            )

        # Push student actions to far-right of the row
        ui.space()

        if act.id in user_workspace_map:
            # User already has a workspace -- show Resume + Delete
            ws = user_workspace_map[act.id]
            qs = urlencode({"workspace_id": str(ws.id)})
            ui.button(
                "Resume",
                icon="play_arrow",
                on_click=lambda q=qs: ui.navigate.to(f"/annotation?{q}"),
            ).props(f'flat color=primary dense data-testid="resume-btn-{act.id}"')
            if on_delete_workspace is not None:
                ui.button(
                    icon="delete",
                    on_click=lambda w=ws: on_delete_workspace(w.id),
                ).props(
                    f"flat round dense size=sm color=negative"
                    f' data-testid="delete-workspace-btn-{ws.id}"'
                )
        else:
            ui.button(
                "Start as Student",
                icon="person",
                on_click=lambda a=act.id: _start_activity_handler(a),
            ).props(
                f'flat color=primary dense data-testid="start-activity-btn-{act.id}"'
            )

    _render_peer_workspaces(peer_workspaces)


def _render_peer_workspaces(
    peer_workspaces: list[tuple[str, str, str]] | None,
) -> None:
    """Render peer workspace links below an activity row."""
    if not peer_workspaces:
        return
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


def _render_week_management_controls(
    week: Any,
    *,
    on_publish_toggle: Callable[[UUID], Any],
    on_edit: Callable[[Any], Any] | None = None,
    on_delete: Callable[[Any], Any] | None = None,
) -> None:
    """Render edit, delete, and publish/unpublish controls for a week."""
    with ui.row().classes("gap-1"):
        if on_edit is not None:
            ui.button(
                "Edit",
                icon="edit",
                on_click=lambda w=week: on_edit(w),
            ).props(
                f"unelevated color=grey-2 text-color=grey-9 dense"
                f' data-testid="edit-week-btn-{week.id}"'
            )
        if on_delete is not None:
            ui.button(
                "Delete",
                icon="delete",
                on_click=lambda w=week: on_delete(w),
            ).props(
                f'outline color=negative dense data-testid="delete-week-btn-{week.id}"'
            )
        _render_publish_toggle(week, on_publish_toggle=on_publish_toggle)


def _render_week_header(
    week: Any,
    *,
    can_view_drafts: bool,
    can_manage: bool,
    on_publish_toggle: Callable[[UUID], Any],
    on_edit: Callable[[Any], Any] | None = None,
    on_delete: Callable[[Any], Any] | None = None,
) -> None:
    """Render week card header with management controls."""
    with ui.row().classes("items-center justify-between w-full"):
        with ui.column().classes("gap-1"):
            ui.label(f"Week {week.week_number}: {week.title}").classes(
                "font-semibold"
            ).props(f'data-testid="week-label-{week.week_number}"')
            if can_view_drafts:
                status = "Published" if week.is_published else "Draft"
                if week.visible_from:
                    date_str = week.visible_from.strftime("%Y-%m-%d")
                    status += f" (visible from {date_str})"
                ui.label(status).classes("text-sm text-gray-500")

        if can_manage:
            _render_week_management_controls(
                week,
                on_publish_toggle=on_publish_toggle,
                on_edit=on_edit,
                on_delete=on_delete,
            )


def _render_publish_toggle(
    week: Any,
    *,
    on_publish_toggle: Callable[[UUID], Any],
) -> None:
    """Render publish/unpublish button for a week."""
    with ui.row().classes("gap-1"):
        if week.is_published:
            ui.button(
                "Unpublish",
                on_click=lambda wid=week.id: on_publish_toggle(wid),
            ).props('outline color=primary dense data-testid="unpublish-week-btn"')
        else:
            ui.button(
                "Publish",
                on_click=lambda wid=week.id: on_publish_toggle(wid),
            ).props('outline color=primary dense data-testid="publish-week-btn"')


async def _render_week_activities(
    week: Any,
    *,
    course_id: str,
    course: Course,
    user_id: UUID,
    can_manage: bool,
    can_view_drafts: bool,
    on_edit_activity: Callable[[Activity], Any] | None = None,
    on_delete_activity: Callable[[Activity], Any] | None = None,
    on_delete_workspace: Callable[[UUID], Any] | None = None,
) -> None:
    """Render the activity list and 'Add Activity' button for a week."""
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
        peer_map = await _build_peer_map(activities, course, user_id, can_view_drafts)
        with ui.column().classes("ml-4 gap-1 mt-2"):
            for act in activities:
                _render_activity_row(
                    act,
                    can_manage=can_manage,
                    populated_templates=populated,
                    user_workspace_map=ws_map,
                    peer_workspaces=peer_map.get(act.id),
                    on_edit=on_edit_activity,
                    on_delete=on_delete_activity,
                    on_delete_workspace=on_delete_workspace,
                )
    elif can_manage:
        ui.label("No activities yet").classes("text-xs text-gray-400 ml-4 mt-1")

    if can_manage:
        ui.button(
            "Add Activity",
            on_click=lambda wid=week.id: ui.navigate.to(
                f"/courses/{course_id}/weeks/{wid}/activities/new"
            ),
        ).props('flat color=primary dense data-testid="add-activity-btn"').classes(
            "ml-4 mt-1"
        )


# -- Tri-state settings UI config --


def _tri_state_options(on_label: str = "On", off_label: str = "Off") -> dict[str, str]:
    """Build a tri-state options dict for activity settings selects."""
    return {"inherit": "Inherit from unit", "on": on_label, "off": off_label}


# (UI label, model attribute name, on_label, off_label)

# (UI label, model attribute name)
_COURSE_DEFAULT_FIELDS: list[tuple[str, str]] = [
    ("Default copy protection", "default_copy_protection"),
    ("Default allow sharing", "default_allow_sharing"),
    ("Anonymous sharing by default", "default_anonymous_sharing"),
    ("Default allow tag creation", "default_allow_tag_creation"),
    ("Default word limit enforcement", "default_word_limit_enforcement"),
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
                logger.warning(
                    "broadcast_client_disconnected",
                    operation="broadcast_weeks_refresh",
                    client_id=client_id,
                )
                _course_clients[course_id].pop(client_id, None)


def _register_course_client(
    cid: UUID,
    client_id: str,
    client: Any,
    refresh: Callable[[], Any],
) -> None:
    """Register a client for broadcast refresh and cleanup on disconnect."""
    if cid not in _course_clients:
        _course_clients[cid] = {}
    _course_clients[cid][client_id] = refresh

    def on_disconnect() -> None:
        if cid in _course_clients:
            _course_clients[cid].pop(client_id, None)
            if not _course_clients[cid]:
                del _course_clients[cid]

    client.on_disconnect(on_disconnect)


async def _handle_enrol_upload(
    upload_event: Any,  # NiceGUI UploadEventArguments; .file is async at runtime
    course: Course,
    force: bool,
) -> None:
    """Handle bulk enrolment XLSX upload.

    Parses the uploaded file, runs bulk enrolment, and notifies the user.
    Called from the upload widget in ``open_course_settings``.
    """
    # NiceGUI UploadEventArguments.file.read() returns coroutine at runtime;
    # ty sees IO[bytes].read() (sync), hence the suppression.
    logger.debug("Upload handler called for course %s", course.code)
    try:
        data: bytes = await upload_event.file.read()  # pyright: ignore[reportAttributeAccessIssue]
    except Exception:
        logger.exception("Failed to read upload")
        ui.notify("Failed to read uploaded file", type="negative", position="top")
        return

    try:
        entries = parse_xlsx(data)
    except EnrolmentParseError as exc:
        logger.warning(
            "enrolment_parse_error", operation="bulk_enrol_upload", errors=exc.errors
        )
        ui.notify(
            "; ".join(exc.errors), type="warning", position="top", close_button="OK"
        )
        return

    try:
        report = await bulk_enrol(entries, course.id, force=force)
    except StudentIdConflictError as exc:
        logger.warning(
            "student_id_conflict", operation="bulk_enrol", conflicts=exc.conflicts
        )
        details = "; ".join(
            f"{email}: existing={old!r}, new={new!r}"
            for email, old, new in exc.conflicts
        )
        ui.notify(
            f"Student ID conflicts: {details}",
            type="negative",
            position="top",
            close_button="OK",
        )
        return
    except Exception:
        logger.exception("Bulk enrolment failed")
        ui.notify(
            "Enrolment failed — check server logs", type="negative", position="top"
        )
        return

    msg = (
        f"Enrolled {report.enrolments_created} of {report.entries_processed} students"
        f" ({report.enrolments_skipped} already enrolled)"
    )
    logger.info("Bulk enrol result: %s", msg)
    ntype = "info" if report.enrolments_created == 0 else "positive"
    ui.notify(msg, type=ntype, position="top", close_button="OK")


async def open_course_settings(course: Course) -> None:
    """Open a dialog to edit course settings.

    Shows boolean switches for each default policy field, driven by
    _COURSE_DEFAULT_FIELDS config.
    """
    with ui.dialog() as dialog, ui.card().classes("w-96"):
        ui.label(f"Unit Settings: {course.name}").classes("text-lg font-bold").props(
            'data-testid="course-settings-title"'
        )

        switches: dict[str, ui.switch] = {}
        for label, attr in _COURSE_DEFAULT_FIELDS:
            switches[attr] = ui.switch(label, value=getattr(course, attr)).props(
                f'data-testid="course-{attr}-switch"'
            )

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancel", on_click=dialog.close).props(
                'flat data-testid="cancel-course-settings-btn"'
            )

            async def save() -> None:
                kwargs = {
                    attr: switches[attr].value for _, attr in _COURSE_DEFAULT_FIELDS
                }
                await update_course(course.id, **kwargs)
                for _, attr in _COURSE_DEFAULT_FIELDS:
                    setattr(course, attr, kwargs[attr])
                dialog.close()
                ui.notify("Unit settings saved", type="positive")

            ui.button("Save", on_click=save).props(
                'color=primary data-testid="save-course-settings-btn"'
            )

    dialog.open()


async def open_activity_settings(activity: Activity) -> None:
    """Open a dialog to edit per-activity settings.

    Shows word count, sharing, and editing settings in grouped sections.
    """
    with ui.dialog() as dialog, ui.card().classes("w-96"):
        ui.label(f"Activity Settings: {activity.title}").classes(
            "text-lg font-bold"
        ).props('data-testid="activity-settings-title"')

        selects: dict[str, ui.select] = {}

        # -- Response Word Count section --
        ui.label("Response Word Count").classes(
            "text-sm font-semibold text-gray-600 mt-2"
        )
        with ui.row().classes("w-full gap-2"):
            word_min_input = (
                ui.number(
                    "Minimum",
                    value=activity.word_minimum,
                    min=1,
                )
                .classes("flex-1")
                .props('data-testid="activity-word-minimum-input"')
            )
            word_limit_input = (
                ui.number(
                    "Limit",
                    value=activity.word_limit,
                    min=1,
                )
                .classes("flex-1")
                .props('data-testid="activity-word-limit-input"')
            )

        sel = (
            ui.select(
                options=_tri_state_options("Hard", "Soft"),
                value=_model_to_ui(activity.word_limit_enforcement),
                label="Enforcement (overrides unit default)",
            )
            .classes("w-full")
            .props('data-testid="activity-word_limit_enforcement-select"')
        )
        add_option_testids(sel, "activity-word_limit_enforcement-opt")
        selects["word_limit_enforcement"] = sel

        # -- Sharing section --
        ui.label("Sharing").classes("text-sm font-semibold text-gray-600 mt-3")
        for label, attr, on_text, off_text in (
            ("Allow sharing", "allow_sharing", "Allowed", "Not allowed"),
        ):
            sel = (
                ui.select(
                    options=_tri_state_options(on_text, off_text),
                    value=_model_to_ui(getattr(activity, attr)),
                    label=f"{label} (overrides unit default)",
                )
                .classes("w-full")
                .props(f'data-testid="activity-{attr}-select"')
            )
            add_option_testids(sel, f"activity-{attr}-opt")
            selects[attr] = sel

        anon_select = (
            ui.select(
                options=_ANONYMOUS_SHARING_OPTIONS,
                value=_model_to_ui(activity.anonymous_sharing),
                label="Anonymity (overrides unit default)",
            )
            .classes("w-full")
            .props('data-testid="activity-anonymous_sharing-select"')
        )

        # -- Editing section --
        ui.label("Editing").classes("text-sm font-semibold text-gray-600 mt-3")
        for label, attr, on_text, off_text in (
            ("Copy protection", "copy_protection", "On", "Off"),
            (
                "Allow tag creation",
                "allow_tag_creation",
                "Allowed",
                "Not allowed",
            ),
        ):
            sel = (
                ui.select(
                    options=_tri_state_options(on_text, off_text),
                    value=_model_to_ui(getattr(activity, attr)),
                    label=f"{label} (overrides unit default)",
                )
                .classes("w-full")
                .props(f'data-testid="activity-{attr}-select"')
            )
            add_option_testids(sel, f"activity-{attr}-opt")
            selects[attr] = sel

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancel", on_click=dialog.close).props(
                'flat data-testid="cancel-activity-settings-btn"'
            )

            async def save() -> None:
                kwargs: dict[str, Any] = {
                    attr: _ui_to_model(sel.value) for attr, sel in selects.items()
                }
                # anonymous_sharing uses a custom options set, not in the loop
                kwargs["anonymous_sharing"] = _ui_to_model(anon_select.value)

                # Word count fields (ui.number may return float)
                word_min_val = word_min_input.value
                word_limit_val = word_limit_input.value
                kwargs["word_minimum"] = (
                    int(word_min_val) if word_min_val is not None else None
                )
                kwargs["word_limit"] = (
                    int(word_limit_val) if word_limit_val is not None else None
                )

                # Client-side cross-field validation
                if (
                    kwargs["word_minimum"] is not None
                    and kwargs["word_limit"] is not None
                    and kwargs["word_minimum"] >= kwargs["word_limit"]
                ):
                    ui.notify(
                        "Word minimum must be less than word limit",
                        type="negative",
                    )
                    return

                try:
                    await update_activity(activity.id, **kwargs)
                except ValueError as e:
                    logger.warning(
                        "activity_update_validation_error", operation="update_activity"
                    )
                    ui.notify(str(e), type="negative")
                    return

                for attr, value in kwargs.items():
                    setattr(activity, attr, value)
                dialog.close()
                ui.notify("Activity settings saved", type="positive")

            ui.button("Save", on_click=save).props(
                'color=primary data-testid="save-activity-settings-btn"'
            )

    dialog.open()


async def open_edit_week(
    week: Week,
    course_id: UUID,  # noqa: ARG001 -- reserved for future week-level validation
    *,
    on_save: Callable[[], Any],
) -> None:
    """Open a dialog to edit week number and title."""
    with ui.dialog() as dialog, ui.card().classes("w-96"):
        ui.label("Edit Week").classes("text-lg font-bold")

        week_number = ui.number(
            "Week Number", value=week.week_number, min=1, max=52
        ).props('data-testid="edit-week-number-input"')
        title = ui.input("Title", value=week.title).props(
            'data-testid="edit-week-title-input"'
        )

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancel", on_click=dialog.close).props(
                'flat data-testid="cancel-edit-week-btn"'
            )

            async def save() -> None:
                await update_week(
                    week.id, title=title.value, week_number=int(week_number.value)
                )
                week.title = title.value
                week.week_number = int(week_number.value)
                dialog.close()
                ui.notify("Week updated", type="positive")
                on_save()

            ui.button("Save", on_click=save).props(
                'color=primary data-testid="save-edit-week-btn"'
            )

    dialog.open()


async def open_edit_activity(
    activity: Activity,
    course_id: UUID,  # noqa: ARG001 -- reserved for future validation
    *,
    on_save: Callable[[], Any],
) -> None:
    """Open a dialog to edit activity title and description."""
    with ui.dialog() as dialog, ui.card().classes("w-96"):
        ui.label("Edit Activity").classes("text-lg font-bold")

        title = ui.input("Title", value=activity.title).props(
            'data-testid="edit-activity-title-input"'
        )
        description = ui.textarea(
            "Description", value=activity.description or ""
        ).props('data-testid="edit-activity-description-input"')

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancel", on_click=dialog.close).props(
                'flat data-testid="cancel-edit-activity-btn"'
            )

            async def save() -> None:
                desc = description.value or None
                await update_activity(activity.id, title=title.value, description=desc)
                activity.title = title.value
                activity.description = desc
                dialog.close()
                ui.notify("Activity updated", type="positive")
                on_save()

            ui.button("Save", on_click=save).props(
                'color=primary data-testid="save-edit-activity-btn"'
            )

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


def _is_db_available() -> bool:
    """Check if database is configured."""
    return bool(get_settings().database.url)


async def _check_auth() -> bool:
    """Check authentication and ban status, redirect if needed."""
    user = _get_current_user()
    if not user:
        ui.navigate.to("/login")
        return False
    user_id = user.get("user_id")
    if user_id:
        from promptgrimoire.db.users import is_user_banned  # noqa: PLC0415

        if await is_user_banned(UUID(user_id)):
            ui.navigate.to("/banned")
            return False
    return True


def _render_course_card(course: Course, enrollment: CourseEnrollment) -> None:
    """Render a single course card in the units list."""
    with (
        ui.card()
        .classes("w-full cursor-pointer hover:bg-gray-50")
        .on("click", lambda c=course: ui.navigate.to(f"/courses/{c.id}"))
        .props(f'data-testid="course-card-{course.id}"')
    ):
        with ui.row().classes("items-center justify-between w-full"):
            with ui.column().classes("gap-1"):
                ui.label(f"{course.code} - {course.name}").classes("font-semibold")
                ui.label(f"Semester: {course.semester}").classes(
                    "text-sm text-gray-500"
                )
            ui.badge(enrollment.role).classes("ml-2")


async def _render_courses_content(user_id: UUID) -> None:
    """Render the enrolled courses list and New Unit button."""
    enrollments = await list_user_enrollments(user_id)
    enrollment_map = {e.course_id: e for e in enrollments}

    is_instructor = is_privileged_user(_get_current_user()) or any(
        e.role in _MANAGER_ROLES for e in enrollments
    )

    courses = await list_courses()
    enrolled_courses = [c for c in courses if c.id in enrollment_map]

    if not enrolled_courses:
        ui.label("You are not enrolled in any units.").classes("text-gray-500")
    else:
        with ui.column().classes("gap-2 w-full max-w-2xl"):
            for course in enrolled_courses:
                _render_course_card(course, enrollment_map[course.id])

    if is_instructor:
        ui.button(
            "New Unit",
            icon="add",
            on_click=lambda: ui.navigate.to("/courses/new"),
        ).props('flat color=primary dense data-testid="new-unit-btn"').classes("mt-4")


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

    with page_layout("Units"):
        ui.add_css(_CSS_FILE)

        with ui.column().classes("mx-auto q-pa-lg courses-content-column"):
            await _render_courses_content(user_id)


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

    code = (
        ui.input("Unit Code", placeholder="e.g., LAWS1100")
        .classes("w-64")
        .props('data-testid="course-code-input"')
    )
    name = (
        ui.input("Unit Name", placeholder="e.g., Contracts")
        .classes("w-64")
        .props('data-testid="course-name-input"')
    )
    semester = (
        ui.input("Semester", placeholder="e.g., 2025-S1")
        .classes("w-64")
        .props('data-testid="course-semester-input"')
    )

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
        ui.button("Create", on_click=submit).props('data-testid="create-course-btn"')
        ui.button("Cancel", on_click=lambda: ui.navigate.to("/courses")).props(
            'flat data-testid="cancel-create-course-btn"'
        )


def _render_add_week_btn(course_id: str) -> None:
    """Render the 'Add Week' list-appender below the weeks list."""
    ui.button(
        "Add Week",
        icon="add",
        on_click=lambda: ui.navigate.to(f"/courses/{course_id}/weeks/new"),
    ).props('flat color=primary dense data-testid="add-week-btn"').classes("mt-2")


def _render_course_action_bar(
    course_id: str,
    course: Course,
    *,
    can_manage: bool,
    can_delete: bool = False,
    on_delete: Callable[[], Any] | None = None,
) -> None:
    """Render the action bar with management buttons."""
    if can_manage or (can_delete and on_delete is not None):
        with ui.row().classes("gap-2 mb-4"):
            if can_manage:
                ui.button(
                    "Manage Enrollments",
                    on_click=lambda: ui.navigate.to(
                        f"/courses/{course_id}/enrollments"
                    ),
                ).props('outline color=primary data-testid="manage-enrollments-btn"')
                ui.button(
                    "Unit Settings",
                    icon="settings",
                    on_click=lambda: open_course_settings(course),
                ).props('outline color=primary data-testid="course-settings-btn"')
            if can_delete and on_delete is not None:
                ui.button(
                    "Delete Unit",
                    icon="delete_forever",
                    on_click=on_delete,
                ).props('outline color=negative data-testid="delete-unit-btn"')


async def _render_students_without_work(cid: UUID, *, can_view_drafts: bool) -> None:
    """Render expandable list of students with no workspaces."""
    if not can_view_drafts:
        return
    no_work = await list_students_without_workspaces(cid)
    if not no_work:
        return
    with (
        ui.expansion(
            f"Students with no work ({len(no_work)})",
            icon="warning",
        )
        .classes("w-full max-w-2xl mt-4")
        .props('data-testid="students-no-work"')
    ):
        with ui.element("ul").classes("ml-4"):
            for name, email in no_work:
                with ui.element("li"):
                    ui.label(f"{name} ({email})")


async def _resolve_course_detail(
    course_id: str,
) -> _CourseDetailContext | None:
    """Validate auth, DB, and enrollment for the course detail page.

    Shows error labels and returns ``None`` on failure.
    """
    if not await _check_auth():
        return None

    if not _is_db_available():
        ui.label("Database not configured").classes("text-red-500")
        return None

    await init_db()

    try:
        cid = UUID(course_id)
    except ValueError:
        logger.warning(
            "invalid_course_id", operation="course_page", course_id=course_id
        )
        ui.label("Invalid unit ID").classes("text-red-500")
        return None

    await ui.context.client.connected()
    client_id = str(id(ui.context.client))

    course = await get_course_by_id(cid)
    user_id = _get_user_id()
    enrollment = (
        await get_enrollment(course_id=cid, user_id=user_id)
        if course and user_id
        else None
    )

    if not course or not user_id or not enrollment:
        _label = (
            "Unit not found"
            if not course
            else (
                "User not found in local database. Please log out and log in again."
                if not user_id
                else "You are not enrolled in this unit"
            )
        )
        ui.label(_label).classes("text-red-500")
        return None

    can_manage = enrollment.role in _MANAGER_ROLES
    staff_roles = await get_staff_roles()
    can_view_drafts = enrollment.role in staff_roles

    return _CourseDetailContext(
        cid=cid,
        course=course,
        user_id=user_id,
        enrollment=enrollment,
        can_manage=can_manage,
        can_view_drafts=can_view_drafts,
        client_id=client_id,
    )


def _make_publish_toggle(
    cid: UUID,
    client_id: str,
    refresh: Callable[[], Any],
) -> Callable[[UUID], Any]:
    """Create a publish/unpublish toggle callback for a course's weeks."""

    async def _toggle(wid: UUID) -> None:
        w = await get_week_by_id(wid)
        if w and w.is_published:
            await unpublish_week(wid)
        else:
            await publish_week(wid)
        refresh()
        _broadcast_weeks_refresh(cid, client_id)

    return _toggle


@ui.page("/courses/{course_id}")
async def course_detail_page(course_id: str) -> None:
    """Course detail page with weeks."""
    ctx = await _resolve_course_detail(course_id)
    if ctx is None:
        return

    cid, course = ctx.cid, ctx.course
    user_id, can_manage = ctx.user_id, ctx.can_manage
    can_view_drafts, client_id = ctx.can_view_drafts, ctx.client_id

    auth_user = _get_current_user()
    can_delete = is_privileged_user(auth_user) or ctx.enrollment.role == "coordinator"

    async def _delete_unit() -> None:
        await _confirm_and_delete(
            entity_label=f"unit: {course.name}",
            delete_fn=delete_course,
            entity_id=cid,
            is_admin=is_privileged_user(auth_user),
            on_success=lambda: ui.navigate.to("/courses"),
        )

    with page_layout(f"{course.code} - {course.name}"):
        ui.add_css(_CSS_FILE)

        with ui.column().classes("mx-auto q-pa-lg courses-content-column"):
            ui.badge(ctx.enrollment.role)
            ui.label(f"Semester: {course.semester}").classes("text-gray-500 mb-4")

            _render_course_action_bar(
                course_id,
                course,
                can_manage=can_manage,
                can_delete=can_delete,
                on_delete=_delete_unit,
            )

            ui.label("Weeks").classes("text-xl font-semibold mb-2")

            @ui.refreshable
            async def weeks_list() -> None:
                """Render the weeks list."""
                weeks = await get_visible_weeks(course_id=cid, user_id=user_id)
                if not weeks:
                    ui.label("No weeks available yet.").classes("text-gray-500")
                    return

                toggle = _make_publish_toggle(cid, client_id, weeks_list.refresh)

                def _on_week_save() -> None:
                    weeks_list.refresh()
                    _broadcast_weeks_refresh(cid, client_id)

                def _on_activity_save() -> None:
                    weeks_list.refresh()
                    _broadcast_weeks_refresh(cid, client_id)

                async def _delete_week_handler(
                    w: Any,
                ) -> None:
                    auth_user = _get_current_user()
                    await _confirm_and_delete(
                        entity_label=(f"Week {w.week_number}: {w.title}"),
                        delete_fn=delete_week,
                        entity_id=w.id,
                        is_admin=is_privileged_user(auth_user),
                        on_success=_on_week_save,
                    )

                async def _delete_activity_handler(
                    a: Any,
                ) -> None:
                    auth_user = _get_current_user()
                    await _confirm_and_delete(
                        entity_label=f"activity: {a.title}",
                        delete_fn=delete_activity,
                        entity_id=a.id,
                        is_admin=is_privileged_user(auth_user),
                        on_success=_on_activity_save,
                    )

                async def _delete_workspace_handler(ws_id: UUID) -> None:
                    await _handle_delete_workspace(ws_id, on_success=_on_activity_save)

                with ui.column().classes("gap-2 w-full"):
                    for week in weeks:
                        with (
                            ui.card()
                            .classes("w-full")
                            .props(f'data-testid="week-card-{week.id}"')
                        ):
                            _render_week_header(
                                week,
                                can_view_drafts=can_view_drafts,
                                can_manage=can_manage,
                                on_publish_toggle=toggle,
                                on_edit=lambda w: open_edit_week(
                                    w, cid, on_save=_on_week_save
                                ),
                                on_delete=_delete_week_handler,
                            )
                            await _render_week_activities(
                                week,
                                course_id=course_id,
                                course=course,
                                user_id=user_id,
                                can_manage=can_manage,
                                can_view_drafts=can_view_drafts,
                                on_edit_activity=lambda a: open_edit_activity(
                                    a, cid, on_save=_on_activity_save
                                ),
                                on_delete_activity=_delete_activity_handler,
                                on_delete_workspace=_delete_workspace_handler,
                            )

            await weeks_list()

            if can_manage:
                _render_add_week_btn(course_id)

            await _render_students_without_work(cid, can_view_drafts=can_view_drafts)

    # Registered after page_layout block so weeks_list.refresh is bound
    _register_course_client(cid, client_id, ui.context.client, weeks_list.refresh)


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
        logger.warning("invalid_course_id", operation="enrol_page", course_id=course_id)
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

    week_number = (
        ui.number("Week Number", value=next_week_num, min=1, max=52)
        .classes("w-32")
        .props('data-testid="week-number-input"')
    )
    title = (
        ui.input("Title", placeholder="e.g., Introduction to Contracts")
        .classes("w-64")
        .props('data-testid="week-title-input"')
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
        ui.button("Create", on_click=submit).props('data-testid="create-week-btn"')
        ui.button(
            "Cancel", on_click=lambda: ui.navigate.to(f"/courses/{course_id}")
        ).props('flat data-testid="cancel-create-week-btn"')


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
        logger.warning("invalid_course_or_week_id", operation="activity_page")
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

    title = (
        ui.input("Title", placeholder="e.g., Annotate Becky Bennett Interview")
        .classes("w-96")
        .props('data-testid="activity-title-input"')
    )
    description = (
        ui.textarea(
            "Description (optional)",
            placeholder="Markdown description of the activity",
        )
        .classes("w-96")
        .props('data-testid="activity-description-input"')
    )

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
        ui.button("Create", on_click=submit).props('data-testid="create-activity-btn"')
        ui.button(
            "Cancel", on_click=lambda: ui.navigate.to(f"/courses/{course_id}")
        ).props('flat data-testid="cancel-create-activity-btn"')


async def _render_add_enrollment_form(
    cid: UUID,
    on_added: Callable[[], Awaitable[None]],
) -> None:
    """Render the add-enrollment form with email input and role select."""
    with ui.card().classes("mb-4 p-4"):
        ui.label("Add Enrollment").classes("font-semibold mb-2")
        ui.label(
            "Enter email address. User will be created if they don't exist yet."
        ).classes("text-sm text-gray-500 mb-2")
        all_roles = list(await get_all_roles())
        with ui.row().classes("gap-2 items-end"):
            new_email = (
                ui.input("Email Address")
                .classes("w-64")
                .props('data-testid="enrollment-email-input"')
            )
            new_role = (
                ui.select(
                    options=all_roles,
                    value="student",
                    label="Role",
                )
                .classes("w-32")
                .props('data-testid="enrollment-role-select"')
            )

            async def add_enrollment() -> None:
                if not new_email.value:
                    ui.notify("Email is required", type="negative")
                    return
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
                    new_email.value = ""
                    await on_added()
                except Exception as e:
                    logger.exception("enroll_failed", operation="add_enrollment")
                    ui.notify(f"Failed to enroll: {e}", type="negative")

            ui.button("Add", on_click=add_enrollment).props(
                'data-testid="add-enrollment-btn"'
            )


@ui.page("/courses/{course_id}/enrollments")
async def manage_enrollments_page(course_id: str) -> None:
    """Manage course enrollments page."""
    ctx = await _resolve_course_detail(course_id)
    if ctx is None:
        return

    if not ctx.can_manage:
        ui.label("Only instructors can manage enrollments").classes("text-red-500")
        return

    cid = ctx.cid

    ui.label(f"Enrollments for {ctx.course.code}").classes("text-2xl font-bold mb-4")

    # -- Enrollment table --
    columns = [
        {
            "name": "display_name",
            "label": "Name",
            "field": "display_name",
            "align": "left",
            "sortable": True,
        },
        {
            "name": "email",
            "label": "Email",
            "field": "email",
            "align": "left",
            "sortable": True,
        },
        {
            "name": "student_id",
            "label": "Student ID",
            "field": "student_id",
            "align": "left",
            "sortable": True,
        },
        {
            "name": "role",
            "label": "Role",
            "field": "role",
            "align": "left",
            "sortable": True,
        },
        {
            "name": "created_at",
            "label": "Enrolled",
            "field": "created_at",
            "align": "left",
            "sortable": True,
        },
        {"name": "action", "label": "Actions", "align": "center"},
    ]

    async def handle_delete(user_id_str: str) -> None:
        await unenroll_user(course_id=cid, user_id=UUID(user_id_str))
        ui.notify("Enrollment removed", type="positive")
        enrollment_table.rows = await list_enrollment_rows(cid)

    initial_rows = await list_enrollment_rows(cid)
    enrollment_table = ui.table(
        columns=columns,
        rows=initial_rows,
        row_key="user_id",
        pagination=25,
    ).props('data-testid="enrollment-table"')

    with enrollment_table.add_slot("body-cell-action"):
        with enrollment_table.cell("action"):
            ui.button(icon="delete").props(
                'flat round dense color=negative data-testid="delete-enrollment-btn"'
            ).on(
                "click",
                js_handler="() => emit(props.row.user_id)",
                handler=lambda e: handle_delete(e.args),
            )

    async def refresh_table() -> None:
        enrollment_table.rows = await list_enrollment_rows(cid)

    await _render_add_enrollment_form(cid, on_added=refresh_table)

    # -- Bulk enrolment upload --
    ui.separator()
    ui.label("Bulk Enrol Students").classes("text-sm font-semibold")

    force_checkbox = ui.checkbox(
        "Override student ID conflicts",
        value=False,
    )
    force_checkbox.props('data-testid="enrol-force-checkbox"')

    upload_widget: ui.upload | None = None

    async def on_upload(e: Any) -> None:
        await _handle_enrol_upload(e, ctx.course, force_checkbox.value)
        if upload_widget is not None:
            upload_widget.reset()
        enrollment_table.rows = await list_enrollment_rows(cid)

    upload_widget = ui.upload(
        label="Upload Moodle Grades XLSX",
        on_upload=on_upload,
        auto_upload=True,
        max_file_size=10 * 1024 * 1024,
    )
    upload_widget.props('accept=".xlsx" data-testid="enrol-upload"').classes("w-full")

    ui.separator()

    ui.button(
        "Back to Unit",
        on_click=lambda: ui.navigate.to(f"/courses/{course_id}"),
    ).props('data-testid="back-to-unit-btn"').classes("mt-4")
