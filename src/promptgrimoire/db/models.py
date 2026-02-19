"""SQLModel database models for PromptGrimoire.

These models define the core database schema for users, classes, and conversations.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Self
from uuid import UUID, uuid4

import sqlalchemy as sa
from pydantic import model_validator
from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlmodel import Field, SQLModel


class Permission(SQLModel, table=True):
    """Reference table for access permission levels.

    String PK — the name is the identity. Rows seeded by migration.
    Level is UNIQUE to prevent ambiguous "highest wins" resolution.
    """

    name: str = Field(
        sa_column=Column(String(50), primary_key=True, nullable=False),
    )
    level: int = Field(
        sa_column=Column(Integer, nullable=False),
    )

    __table_args__ = (
        UniqueConstraint("level", name="uq_permission_level"),
        CheckConstraint("level BETWEEN 1 AND 100", name="ck_permission_level_range"),
    )


class CourseRoleRef(SQLModel, table=True):
    """Reference table for course roles.

    String PK — the name is the identity. Rows seeded by migration.
    CourseEnrollment.role is a FK to this table.
    ``is_staff`` marks roles that derive instructor-level access
    (week visibility, ACL permission resolution).
    """

    __tablename__ = "course_role"

    name: str = Field(
        sa_column=Column(String(50), primary_key=True, nullable=False),
    )
    level: int = Field(
        sa_column=Column(Integer, nullable=False),
    )
    is_staff: bool = Field(
        default=False,
        sa_column=Column(sa.Boolean, nullable=False, server_default="false"),
    )

    __table_args__ = (
        UniqueConstraint("level", name="uq_course_role_level"),
        CheckConstraint("level BETWEEN 1 AND 100", name="ck_course_role_level_range"),
    )


def _utcnow() -> datetime:
    """Return current UTC time as timezone-aware datetime."""
    return datetime.now(UTC)


def _timestamptz_column() -> Any:
    """Create a TIMESTAMP WITH TIME ZONE column for PostgreSQL."""
    return Column(DateTime(timezone=True), nullable=False)


def _cascade_fk_column(target: str) -> Any:
    """Create a UUID foreign key column with CASCADE DELETE."""
    return Column(Uuid(), ForeignKey(target, ondelete="CASCADE"), nullable=False)


def _set_null_fk_column(target: str) -> Any:
    """Create a UUID foreign key column with SET NULL on delete."""
    return Column(Uuid(), ForeignKey(target, ondelete="SET NULL"), nullable=True)


class User(SQLModel, table=True):
    """User account linked to Stytch authentication.

    Attributes:
        id: Primary key UUID, auto-generated.
        email: Unique email address for the user.
        display_name: Human-readable name shown in UI.
        stytch_member_id: Optional link to Stytch B2B member.
        is_admin: Whether user has org-level admin rights.
        created_at: Timestamp when user was created.
        last_login: Timestamp of last successful login.
    """

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email: str = Field(unique=True, index=True, max_length=255)
    display_name: str = Field(max_length=100)
    stytch_member_id: str | None = Field(default=None, unique=True, index=True)
    is_admin: bool = Field(default=False)
    created_at: datetime = Field(
        default_factory=_utcnow, sa_column=_timestamptz_column()
    )
    last_login: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )


class Course(SQLModel, table=True):
    """A course/unit of study with weeks and enrolled members.

    Courses contain weeks which can be published on a schedule.
    Members are enrolled via CourseEnrollment with course-specific roles.

    Attributes:
        id: Primary key UUID, auto-generated.
        code: Course code (e.g., "LAWS1100").
        name: Course name (e.g., "Contracts").
        semester: Semester identifier (e.g., "2025-S1").
        is_archived: Whether course is archived and read-only.
        default_copy_protection: Course-level default for copy protection
            (inherited by activities with copy_protection=NULL).
        created_at: Timestamp when course was created.
    """

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    code: str = Field(max_length=20, index=True)
    name: str = Field(max_length=200)
    semester: str = Field(max_length=20, index=True)
    is_archived: bool = Field(default=False)
    default_copy_protection: bool = Field(default=False)
    """Course-level default for copy protection.

    Inherited by activities with copy_protection=NULL.
    """
    default_allow_sharing: bool = Field(default=False)
    """Course-level default for workspace sharing.

    Inherited by activities with allow_sharing=NULL.
    """
    default_anonymous_sharing: bool = Field(default=False)
    """Course-level default for anonymous sharing.

    Inherited by activities with anonymous_sharing=NULL.
    """
    default_instructor_permission: str = Field(
        default="editor",
        sa_column=Column(
            String(50),
            ForeignKey("permission.name", ondelete="RESTRICT"),
            nullable=False,
            server_default="editor",
        ),
    )
    """Default permission level for instructors accessing student workspaces.

    Instructors (coordinator/instructor/tutor roles) get this permission
    when accessing workspaces in the course via enrollment-derived access.
    """
    created_at: datetime = Field(
        default_factory=_utcnow, sa_column=_timestamptz_column()
    )


class CourseEnrollment(SQLModel, table=True):
    """Maps a User to a course with a course-level role.

    This provides course-scoped authorization on top of org-level roles.

    Attributes:
        id: Primary key UUID, auto-generated.
        course_id: Foreign key to Course (CASCADE DELETE).
        user_id: Foreign key to User (CASCADE DELETE).
        role: Course-level role (coordinator, instructor, tutor, student).
        created_at: Timestamp when enrollment was created.
    """

    __tablename__ = "course_enrollment"
    __table_args__ = (
        UniqueConstraint(
            "course_id", "user_id", name="uq_course_enrollment_course_user"
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    course_id: UUID = Field(sa_column=_cascade_fk_column("course.id"))
    user_id: UUID = Field(sa_column=_cascade_fk_column("user.id"))
    role: str = Field(
        default="student",
        sa_column=Column(
            String(50),
            ForeignKey("course_role.name", ondelete="RESTRICT"),
            nullable=False,
        ),
    )
    created_at: datetime = Field(
        default_factory=_utcnow, sa_column=_timestamptz_column()
    )


class Week(SQLModel, table=True):
    """A week within a course, with visibility controls for students.

    Instructors see all weeks. Students only see published weeks
    where visible_from has passed.

    Attributes:
        id: Primary key UUID, auto-generated.
        course_id: Foreign key to Course (CASCADE DELETE).
        week_number: Week number within course (1-13 typically).
        title: Week title (e.g., "Introduction to Contract Law").
        is_published: Master switch - False means hidden from students.
        visible_from: Optional auto-publish datetime (UTC).
        created_at: Timestamp when week was created.
    """

    __table_args__ = (
        UniqueConstraint("course_id", "week_number", name="uq_week_course_number"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    course_id: UUID = Field(sa_column=_cascade_fk_column("course.id"))
    week_number: int = Field(ge=1, le=52)
    title: str = Field(max_length=200)
    is_published: bool = Field(default=False)
    visible_from: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    created_at: datetime = Field(
        default_factory=_utcnow, sa_column=_timestamptz_column()
    )


class Activity(SQLModel, table=True):
    """A discrete assignment or exercise within a Week.

    Each Activity has an instructor-managed template workspace that students
    clone when they start work. The template workspace is CASCADE-deleted
    when the Activity is deleted.

    Attributes:
        id: Primary key UUID, auto-generated.
        week_id: Foreign key to Week (CASCADE DELETE).
        template_workspace_id: Foreign key to Workspace (RESTRICT DELETE).
        title: Activity title (e.g., "Annotate Becky Bennett Interview").
        description: Optional markdown description of the activity.
        copy_protection: Tri-state copy protection
            (None=inherit from course, True=on, False=off).
        created_at: Timestamp when activity was created.
        updated_at: Timestamp when activity was last modified.
    """

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    week_id: UUID = Field(sa_column=_cascade_fk_column("week.id"))
    template_workspace_id: UUID = Field(
        sa_column=Column(
            Uuid(),
            ForeignKey("workspace.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        )
    )
    title: str = Field(max_length=200)
    description: str | None = Field(
        default=None, sa_column=Column(sa.Text(), nullable=True)
    )
    copy_protection: bool | None = Field(default=None)
    """Tri-state copy protection.

    None=inherit from course, True=on, False=off.
    """
    allow_sharing: bool | None = Field(default=None)
    """Tri-state sharing control.

    None=inherit from course, True=allowed, False=disallowed.
    """
    anonymous_sharing: bool | None = Field(default=None)
    """Tri-state anonymity control.

    None=inherit from course, True=on, False=off.
    """
    created_at: datetime = Field(
        default_factory=_utcnow, sa_column=_timestamptz_column()
    )
    updated_at: datetime = Field(
        default_factory=_utcnow, sa_column=_timestamptz_column()
    )


class Workspace(SQLModel, table=True):
    """Container for documents and CRDT state. Unit of collaboration.

    Workspaces are isolated silos - each workspace's documents and CRDT state
    are independent. Access control is handled via ACL (Seam D, future).

    A workspace may be optionally placed in either an Activity (student clone)
    or a Course (shared resource), but never both.

    Attributes:
        id: Primary key UUID, auto-generated.
        crdt_state: Serialized pycrdt state bytes for all annotations.
        activity_id: Optional FK to Activity (SET NULL on delete).
        course_id: Optional FK to Course (SET NULL on delete).
        enable_save_as_draft: Whether students can save drafts in this workspace.
        created_at: Timestamp when workspace was created.
        updated_at: Timestamp when workspace was last modified.
    """

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    crdt_state: bytes | None = Field(
        default=None, sa_column=Column(sa.LargeBinary(), nullable=True)
    )
    activity_id: UUID | None = Field(
        default=None, sa_column=_set_null_fk_column("activity.id")
    )
    course_id: UUID | None = Field(
        default=None, sa_column=_set_null_fk_column("course.id")
    )
    enable_save_as_draft: bool = Field(default=False)
    title: str | None = Field(default=None, sa_column=Column(sa.Text(), nullable=True))
    shared_with_class: bool = Field(default=False)
    created_at: datetime = Field(
        default_factory=_utcnow, sa_column=_timestamptz_column()
    )
    updated_at: datetime = Field(
        default_factory=_utcnow, sa_column=_timestamptz_column()
    )

    @model_validator(mode="after")
    def _check_placement_exclusivity(self) -> Self:
        """Ensure activity_id and course_id are mutually exclusive."""
        if self.activity_id is not None and self.course_id is not None:
            msg = "Workspace cannot be placed in both an Activity and a Course"
            raise ValueError(msg)
        return self


class WorkspaceDocument(SQLModel, table=True):
    """A document within a workspace (source text, draft, AI conversation, etc.).

    Attributes:
        id: Primary key UUID, auto-generated.
        workspace_id: Foreign key to Workspace (CASCADE DELETE).
        type: Domain-defined type string ("source", "draft", "ai_conversation").
        content: HTML with character-level spans for annotation.
        source_type: Content type - "html", "rtf", "docx", "pdf", or "text".
        order_index: Display order within workspace.
        title: Optional document title.
        created_at: Timestamp when document was added.
    """

    __tablename__ = "workspace_document"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    workspace_id: UUID = Field(sa_column=_cascade_fk_column("workspace.id"))
    type: str = Field(max_length=50)
    content: str = Field(sa_column=Column(sa.Text(), nullable=False))
    source_type: str = Field(max_length=20)  # "html", "rtf", "docx", "pdf", "text"
    order_index: int = Field(default=0)
    title: str | None = Field(default=None, max_length=500)
    created_at: datetime = Field(
        default_factory=_utcnow, sa_column=_timestamptz_column()
    )


class ACLEntry(SQLModel, table=True):
    """Per-user, per-workspace permission grant.

    One entry per (workspace, user) pair. Permission level can be updated
    via upsert. Cascade-deletes when the Workspace or User is deleted.
    """

    __tablename__ = "acl_entry"
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_acl_entry_workspace_user"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    workspace_id: UUID = Field(sa_column=_cascade_fk_column("workspace.id"))
    user_id: UUID = Field(sa_column=_cascade_fk_column("user.id"))
    permission: str = Field(
        sa_column=Column(
            String(50),
            ForeignKey("permission.name", ondelete="RESTRICT"),
            nullable=False,
        ),
    )
    created_at: datetime = Field(
        default_factory=_utcnow, sa_column=_timestamptz_column()
    )
