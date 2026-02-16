"""CRUD operations for Workspace.

Provides async database functions for workspace management.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from sqlmodel import select

from promptgrimoire.db.engine import get_session
from promptgrimoire.db.models import (
    ACLEntry,
    Activity,
    Course,
    CourseEnrollment,
    Week,
    Workspace,
    WorkspaceDocument,
)
from promptgrimoire.db.roles import get_staff_roles

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession


async def get_user_workspace_for_activity(
    activity_id: UUID, user_id: UUID
) -> Workspace | None:
    """Find an existing workspace owned by the user in an activity.

    Looks for a non-template workspace placed in this activity where the user
    has an owner ACL entry. Returns the first match, or None if the user has
    no owned workspace for this activity.

    Filters by permission == "owner" to exclude shared workspaces -- a viewer
    of someone else's workspace should not be treated as having their own
    workspace for this activity (which would suppress the "Start Activity"
    button and show "Resume" instead).
    """
    async with get_session() as session:
        result = await session.exec(
            select(Workspace)
            .join(ACLEntry, ACLEntry.workspace_id == Workspace.id)  # type: ignore[arg-type]  -- SQLAlchemy == returns ColumnElement, not bool
            .where(
                Workspace.activity_id == activity_id,
                ACLEntry.user_id == user_id,
                ACLEntry.permission == "owner",
            )
        )
        return result.first()


async def check_clone_eligibility(activity_id: UUID, user_id: UUID) -> str | None:
    """Check if a user is eligible to clone a workspace from an activity.

    Validates:
    1. Activity exists
    2. User is enrolled in the activity's course
    3. Activity's week is visible to the user (staff bypass)

    Returns:
        None if eligible, or an error message string explaining why not.
    """
    staff_roles = await get_staff_roles()

    async with get_session() as session:
        # 1. Activity must exist
        activity = await session.get(Activity, activity_id)
        if activity is None:
            return "Activity not found"

        # 2. Resolve course via Week
        week = await session.get(Week, activity.week_id)
        if week is None:
            return "Week not found"

        # 3. User must be enrolled in the course
        enrollment_result = await session.exec(
            select(CourseEnrollment).where(
                CourseEnrollment.course_id == week.course_id,
                CourseEnrollment.user_id == user_id,
            )
        )
        enrollment = enrollment_result.one_or_none()
        if enrollment is None:
            return "User is not enrolled in this course"

        # 4. Week must be visible to the user
        # Staff always have access regardless of publish state
        if enrollment.role not in staff_roles:
            # Students need published + visible week
            if not week.is_published:
                return "Week is not published"
            if week.visible_from and week.visible_from > datetime.now(UTC):
                return "Week is not yet visible"

        return None


@dataclass(frozen=True)
class PlacementContext:
    """Full hierarchy context for a workspace's placement."""

    placement_type: Literal["activity", "course", "loose"]
    activity_title: str | None = None
    week_number: int | None = None
    week_title: str | None = None
    course_code: str | None = None
    course_name: str | None = None
    is_template: bool = False
    copy_protection: bool = False
    """Resolved copy protection for this workspace.

    True = protection active.
    """

    @property
    def display_label(self) -> str:
        """Human-readable placement label.

        Shows full hierarchy: "Activity Title in Week N for COURSE_CODE"
        """
        if self.placement_type == "activity":
            return (
                f"{self.activity_title} "
                f"in Week {self.week_number} "
                f"for {self.course_code}"
            )
        if self.placement_type == "course":
            return f"Loose work for {self.course_code}"
        return "Unplaced"


async def get_placement_context(workspace_id: UUID) -> PlacementContext:
    """Resolve the full hierarchy context for a workspace's placement.

    Fetches the workspace and walks the Activity -> Week -> Course chain
    (if placed in an Activity) or just the Course (if placed in a Course)
    within a single session for consistency.

    Args:
        workspace_id: The workspace UUID.

    Returns:
        PlacementContext with all resolved fields. Returns a loose context
        if the workspace is not found or has no placement.
    """
    loose = PlacementContext(placement_type="loose")
    async with get_session() as session:
        workspace = await session.get(Workspace, workspace_id)
        if workspace is None:
            return loose

        # Check if this workspace is a template for any Activity
        template_result = await session.exec(
            select(Activity).where(Activity.template_workspace_id == workspace_id)
        )
        is_template = template_result.first() is not None

        if workspace.activity_id is not None:
            ctx = await _resolve_activity_placement(session, workspace.activity_id)
            if is_template:
                return replace(ctx, is_template=True)
            return ctx

        if workspace.course_id is not None:
            return await _resolve_course_placement(session, workspace.course_id)

        return loose


async def _resolve_activity_placement(
    session: AsyncSession,
    activity_id: UUID,
) -> PlacementContext:
    """Walk Activity -> Week -> Course chain. Falls back to loose on orphan.

    TODO: Replace 3 sequential session.get() calls with a single JOIN query
    if this becomes a performance concern (currently once per page load).
    """
    activity = await session.get(Activity, activity_id)
    if activity is None:
        return PlacementContext(placement_type="loose")
    week = await session.get(Week, activity.week_id)
    if week is None:
        return PlacementContext(placement_type="loose")
    course = await session.get(Course, week.course_id)
    if course is None:
        return PlacementContext(placement_type="loose")

    # Resolve tri-state copy_protection: explicit wins, else course default
    if activity.copy_protection is not None:
        resolved_cp = activity.copy_protection
    else:
        resolved_cp = course.default_copy_protection

    return PlacementContext(
        placement_type="activity",
        activity_title=activity.title,
        week_number=week.week_number,
        week_title=week.title,
        course_code=course.code,
        course_name=course.name,
        copy_protection=resolved_cp,
    )


async def _resolve_course_placement(
    session: AsyncSession,
    course_id: UUID,
) -> PlacementContext:
    """Resolve Course placement. Falls back to loose on orphan."""
    course = await session.get(Course, course_id)
    if course is None:
        return PlacementContext(placement_type="loose")
    return PlacementContext(
        placement_type="course",
        course_code=course.code,
        course_name=course.name,
    )


async def create_workspace() -> Workspace:
    """Create a new workspace.

    Returns:
        The created Workspace with generated ID.
    """
    async with get_session() as session:
        workspace = Workspace()
        session.add(workspace)
        await session.flush()
        await session.refresh(workspace)
        return workspace


async def get_workspace(workspace_id: UUID) -> Workspace | None:
    """Get a workspace by ID.

    Args:
        workspace_id: The workspace UUID.

    Returns:
        The Workspace or None if not found.
    """
    async with get_session() as session:
        return await session.get(Workspace, workspace_id)


async def delete_workspace(workspace_id: UUID) -> None:
    """Delete a workspace and all its documents (CASCADE).

    Args:
        workspace_id: The workspace UUID.
    """
    async with get_session() as session:
        workspace = await session.get(Workspace, workspace_id)
        if workspace:
            await session.delete(workspace)


async def save_workspace_crdt_state(workspace_id: UUID, crdt_state: bytes) -> bool:
    """Save CRDT state to a workspace.

    Args:
        workspace_id: The workspace UUID.
        crdt_state: Serialized pycrdt state bytes.

    Returns:
        True if workspace was found and updated, False otherwise.
    """
    async with get_session() as session:
        workspace = await session.get(Workspace, workspace_id)
        if workspace:
            workspace.crdt_state = crdt_state
            workspace.updated_at = datetime.now(UTC)
            session.add(workspace)
            return True
        return False


async def place_workspace_in_activity(
    workspace_id: UUID,
    activity_id: UUID,
) -> Workspace:
    """Place a workspace in an Activity.

    Sets activity_id and clears course_id (mutual exclusivity).

    Args:
        workspace_id: The workspace UUID.
        activity_id: The activity UUID.

    Returns:
        The updated Workspace.

    Raises:
        ValueError: If workspace or activity not found.
    """
    async with get_session() as session:
        workspace = await session.get(Workspace, workspace_id)
        if not workspace:
            msg = f"Workspace {workspace_id} not found"
            raise ValueError(msg)

        activity = await session.get(Activity, activity_id)
        if not activity:
            msg = f"Activity {activity_id} not found"
            raise ValueError(msg)

        workspace.activity_id = activity_id
        workspace.course_id = None
        workspace.updated_at = datetime.now(UTC)
        session.add(workspace)
        await session.flush()
        await session.refresh(workspace)
        return workspace


async def place_workspace_in_course(
    workspace_id: UUID,
    course_id: UUID,
) -> Workspace:
    """Place a workspace in a Course (loose association).

    Sets course_id and clears activity_id (mutual exclusivity).

    Args:
        workspace_id: The workspace UUID.
        course_id: The course UUID.

    Returns:
        The updated Workspace.

    Raises:
        ValueError: If workspace or course not found.
    """
    async with get_session() as session:
        workspace = await session.get(Workspace, workspace_id)
        if not workspace:
            msg = f"Workspace {workspace_id} not found"
            raise ValueError(msg)

        course = await session.get(Course, course_id)
        if not course:
            msg = f"Course {course_id} not found"
            raise ValueError(msg)

        workspace.course_id = course_id
        workspace.activity_id = None
        workspace.updated_at = datetime.now(UTC)
        session.add(workspace)
        await session.flush()
        await session.refresh(workspace)
        return workspace


async def make_workspace_loose(workspace_id: UUID) -> Workspace:
    """Remove a workspace from any Activity or Course placement.

    Clears both activity_id and course_id.

    Args:
        workspace_id: The workspace UUID.

    Returns:
        The updated Workspace.

    Raises:
        ValueError: If workspace not found.
    """
    async with get_session() as session:
        workspace = await session.get(Workspace, workspace_id)
        if not workspace:
            msg = f"Workspace {workspace_id} not found"
            raise ValueError(msg)

        workspace.activity_id = None
        workspace.course_id = None
        workspace.updated_at = datetime.now(UTC)
        session.add(workspace)
        await session.flush()
        await session.refresh(workspace)
        return workspace


async def list_workspaces_for_activity(
    activity_id: UUID,
) -> list[Workspace]:
    """List all workspaces placed in an Activity.

    Args:
        activity_id: The activity UUID.

    Returns:
        List of Workspaces ordered by created_at.
    """
    async with get_session() as session:
        result = await session.exec(
            select(Workspace)
            .where(Workspace.activity_id == activity_id)
            .order_by(Workspace.created_at)  # type: ignore[arg-type]  # TODO(2026-Q2): Revisit when SQLModel updates type stubs
        )
        return list(result.all())


async def list_loose_workspaces_for_course(
    course_id: UUID,
) -> list[Workspace]:
    """List workspaces associated with a Course but not in an Activity.

    The activity_id == None filter is defense-in-depth. The mutual
    exclusivity constraint guarantees that course_id being set implies
    activity_id is None, but the explicit filter protects against
    constraint violations and makes the query intent clear.

    Args:
        course_id: The course UUID.

    Returns:
        List of loose Workspaces ordered by created_at.
    """
    async with get_session() as session:
        result = await session.exec(
            select(Workspace)
            .where(Workspace.course_id == course_id)
            .where(Workspace.activity_id == None)  # noqa: E711
            .order_by(Workspace.created_at)  # type: ignore[arg-type]  # TODO(2026-Q2): Revisit when SQLModel updates type stubs
        )
        return list(result.all())


def _replay_crdt_state(
    template: Workspace,
    clone: Workspace,
    doc_id_map: dict[UUID, UUID],
) -> None:
    """Replay CRDT state from template into clone with document ID remapping.

    Loads the template's CRDT state into a temporary AnnotationDocument,
    creates a fresh AnnotationDocument for the clone, and replays all
    highlights (with remapped document_id values), comments, and general
    notes. Client metadata is deliberately NOT replayed (AC4.9).

    If template has no crdt_state, the clone gets None (AC4.10).

    Args:
        template: The template Workspace (source of CRDT state).
        clone: The cloned Workspace (destination for replayed state).
        doc_id_map: Mapping of {template_doc_id: cloned_doc_id}.
    """
    from promptgrimoire.crdt.annotation_doc import AnnotationDocument as AnnotDoc

    if template.crdt_state is None:
        return

    # Load template CRDT state
    template_doc = AnnotDoc("template-tmp")
    template_doc.apply_update(template.crdt_state)

    # Fresh document for clone (empty client_meta satisfies AC4.9)
    clone_doc = AnnotDoc("clone-tmp")

    # Replay highlights with remapped document_id
    for hl in template_doc.get_all_highlights():
        # Remap document_id: template doc UUID -> cloned doc UUID
        raw_doc_id = hl.get("document_id")
        if raw_doc_id is not None:
            template_uuid = UUID(raw_doc_id)
            remapped_uuid = doc_id_map.get(template_uuid, template_uuid)
            remapped_doc_id: str | None = str(remapped_uuid)
        else:
            remapped_doc_id = None

        new_hl_id = clone_doc.add_highlight(
            start_char=hl["start_char"],
            end_char=hl["end_char"],
            tag=hl["tag"],
            text=hl["text"],
            author=hl["author"],
            para_ref=hl.get("para_ref", ""),
            document_id=remapped_doc_id,
        )

        # Replay comments for this highlight
        for comment in hl.get("comments", []):
            clone_doc.add_comment(
                highlight_id=new_hl_id,
                author=comment["author"],
                text=comment["text"],
            )

    # Clone general notes
    notes = template_doc.get_general_notes()
    if notes:
        clone_doc.set_general_notes(notes)

    # Serialise and assign to cloned workspace
    clone.crdt_state = clone_doc.get_full_state()


async def clone_workspace_from_activity(
    activity_id: UUID,
    user_id: UUID,
) -> tuple[Workspace, dict[UUID, UUID]]:
    """Clone an Activity's template workspace into a new student workspace.

    Creates a new Workspace within a single transaction, copies all template
    documents (preserving content, type, source_type, title, order_index),
    builds a document ID mapping, and replays CRDT state (highlights,
    comments, general notes) with remapped document IDs. Client metadata
    is NOT cloned -- the fresh workspace starts with empty client state.

    Also creates an ACLEntry granting owner permission to the cloning user.

    Args:
        activity_id: The Activity UUID whose template workspace to clone.
        user_id: The user UUID who will own the cloned workspace.

    Returns:
        Tuple of (new Workspace, mapping of {template_doc_id: cloned_doc_id}).

    Raises:
        ValueError: If Activity or its template workspace is not found.
    """
    async with get_session() as session:
        activity = await session.get(Activity, activity_id)
        if not activity:
            msg = f"Activity {activity_id} not found"
            raise ValueError(msg)

        template = await session.get(Workspace, activity.template_workspace_id)
        if not template:
            msg = f"Template workspace {activity.template_workspace_id} not found"
            raise ValueError(msg)

        # Create new workspace with activity_id and enable_save_as_draft copied
        clone = Workspace(
            activity_id=activity_id,
            enable_save_as_draft=template.enable_save_as_draft,
        )
        session.add(clone)
        await session.flush()

        # Grant owner permission to cloning user
        acl_entry = ACLEntry(
            workspace_id=clone.id,
            user_id=user_id,
            permission="owner",
        )
        session.add(acl_entry)
        await session.flush()

        # Fetch all template documents ordered by order_index
        result = await session.exec(
            select(WorkspaceDocument)
            .where(WorkspaceDocument.workspace_id == template.id)
            .order_by(WorkspaceDocument.order_index)  # type: ignore[arg-type]  # TODO(2026-Q2): Revisit when SQLModel updates type stubs
        )
        template_docs = list(result.all())

        # Clone each document, preserving field values
        doc_id_map: dict[UUID, UUID] = {}
        for tmpl_doc in template_docs:
            cloned_doc = WorkspaceDocument(
                workspace_id=clone.id,
                type=tmpl_doc.type,
                content=tmpl_doc.content,
                source_type=tmpl_doc.source_type,
                title=tmpl_doc.title,
                order_index=tmpl_doc.order_index,
            )
            session.add(cloned_doc)
            await session.flush()
            doc_id_map[tmpl_doc.id] = cloned_doc.id

        # --- CRDT state cloning via API replay ---
        _replay_crdt_state(template, clone, doc_id_map)

        await session.flush()
        await session.refresh(clone)
        return clone, doc_id_map
