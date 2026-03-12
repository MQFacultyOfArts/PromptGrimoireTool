"""SQLModel database models for PromptGrimoire.

These models define the core database schema for users, classes, and conversations.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
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
from sqlalchemy.dialects.postgresql import JSONB
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
    can_edit: bool = Field(
        default=False,
        sa_column=Column(sa.Boolean, nullable=False, server_default="false"),
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
    default_allow_tag_creation: bool = Field(default=True)
    """Course-level default for tag creation.

    Inherited by activities with allow_tag_creation=NULL.
    """
    default_word_limit_enforcement: bool = Field(default=False)
    """Course-level default for word limit enforcement.

    Inherited by activities with word_limit_enforcement=NULL.
    False=soft (warn only), True=hard (block submit).
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
        type: Activity type discriminator ("annotation" or "wargame").
        template_workspace_id: Foreign key to Workspace (RESTRICT DELETE).
            Required for annotation activities; NULL for wargame activities.
        title: Activity title (e.g., "Annotate Becky Bennett Interview").
        description: Optional markdown description of the activity.
        copy_protection: Tri-state copy protection
            (None=inherit from course, True=on, False=off).
        created_at: Timestamp when activity was created.
        updated_at: Timestamp when activity was last modified.
    """

    __table_args__ = (
        UniqueConstraint("id", "type", name="uq_activity_id_type"),
        CheckConstraint(
            "type IN ('annotation', 'wargame')",
            name="ck_activity_type_known",
        ),
        CheckConstraint(
            "type != 'annotation' OR template_workspace_id IS NOT NULL",
            name="ck_activity_annotation_requires_template",
        ),
        CheckConstraint(
            "type != 'wargame' OR template_workspace_id IS NULL",
            name="ck_activity_wargame_no_template",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    week_id: UUID = Field(sa_column=_cascade_fk_column("week.id"))
    type: str = Field(
        default="annotation",
        sa_column=Column(String(50), nullable=False, server_default="annotation"),
    )
    # Compatibility shim: keep the historical UUID annotation during the schema
    # seam so annotation-era callers do not need a broad UUID | None update yet.
    template_workspace_id: UUID = Field(
        default=None,
        sa_column=Column(
            Uuid(),
            ForeignKey("workspace.id", ondelete="RESTRICT"),
            nullable=True,
            unique=True,
        ),
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
    allow_tag_creation: bool | None = Field(default=None)
    """Tri-state tag creation control.

    None=inherit from course, True=allowed, False=disallowed.
    """
    word_minimum: int | None = Field(default=None)
    """Minimum word count for submissions.

    None=no minimum enforced.
    """
    word_limit: int | None = Field(default=None)
    """Maximum word count for submissions.

    None=no limit enforced.
    """
    word_limit_enforcement: bool | None = Field(default=None)
    """Tri-state word limit enforcement.

    None=inherit from course, True=hard (block submit), False=soft (warn only).
    """
    created_at: datetime = Field(
        default_factory=_utcnow, sa_column=_timestamptz_column()
    )
    updated_at: datetime = Field(
        default_factory=_utcnow, sa_column=_timestamptz_column()
    )

    @model_validator(mode="after")
    def _check_type_template_requirements(self) -> Self:
        """Ensure Activity type and template workspace invariants hold."""
        if self.type not in {"annotation", "wargame"}:
            msg = "activity type must be 'annotation' or 'wargame'"
            raise ValueError(msg)
        if self.type == "annotation" and self.template_workspace_id is None:
            msg = "annotation activities require template_workspace_id"
            raise ValueError(msg)
        if self.type == "wargame" and self.template_workspace_id is not None:
            msg = "wargame activities must not set template_workspace_id"
            raise ValueError(msg)
        return self


class WargameConfig(SQLModel, table=True):
    """Wargame configuration extension for Activity.

    PK-as-FK one-to-one table for wargame-specific configuration fields.
    Exactly one timer mode must be configured: relative delta or wall-clock.
    """

    __tablename__ = "wargame_config"
    __table_args__ = (
        CheckConstraint(
            "activity_type = 'wargame'",
            name="ck_wargame_config_activity_type",
        ),
        sa.ForeignKeyConstraint(
            ["activity_id", "activity_type"],
            ["activity.id", "activity.type"],
            name="fk_wargame_config_activity_wargame",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "num_nonnulls(timer_delta, timer_wall_clock) = 1",
            name="ck_wargame_config_timer_exactly_one",
        ),
    )

    activity_id: UUID = Field(
        sa_column=Column(
            Uuid(),
            nullable=False,
            primary_key=True,
        )
    )
    activity_type: str = Field(
        default="wargame",
        sa_column=Column(String(50), nullable=False, server_default="wargame"),
    )
    system_prompt: str = Field(sa_column=Column(sa.Text(), nullable=False))
    scenario_bootstrap: str = Field(sa_column=Column(sa.Text(), nullable=False))
    timer_delta: timedelta | None = Field(
        default=None, sa_column=Column(sa.Interval(), nullable=True)
    )
    timer_wall_clock: time | None = Field(
        default=None, sa_column=Column(sa.Time(), nullable=True)
    )
    summary_system_prompt: str = Field(
        default="",
        sa_column=Column(sa.Text(), nullable=False, server_default=""),
    )

    @model_validator(mode="after")
    def _check_activity_type(self) -> Self:
        """Ensure the child discriminator remains fixed at wargame."""
        if self.activity_type != "wargame":
            msg = "wargame config activity_type must be 'wargame'"
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _check_timer_exclusivity(self) -> Self:
        """Ensure exactly one timer field is configured."""
        has_delta = self.timer_delta is not None
        has_wall_clock = self.timer_wall_clock is not None
        if has_delta == has_wall_clock:
            msg = "exactly one of timer_delta or timer_wall_clock must be set"
            raise ValueError(msg)
        return self


class WargameTeam(SQLModel, table=True):
    """Team resource within a wargame activity."""

    __tablename__ = "wargame_team"
    __table_args__ = (
        CheckConstraint(
            "activity_type = 'wargame'",
            name="ck_wargame_team_activity_type",
        ),
        sa.ForeignKeyConstraint(
            ["activity_id", "activity_type"],
            ["activity.id", "activity.type"],
            name="fk_wargame_team_activity_wargame",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "activity_id",
            "codename",
            name="uq_wargame_team_activity_codename",
        ),
        sa.Index("ix_wargame_team_activity_id", "activity_id"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    activity_id: UUID = Field(
        sa_column=Column(
            Uuid(),
            nullable=False,
        )
    )
    activity_type: str = Field(
        default="wargame",
        sa_column=Column(String(50), nullable=False, server_default="wargame"),
    )
    codename: str = Field(max_length=100)
    current_round: int = Field(default=0)
    round_state: str = Field(default="drafting", max_length=50)
    current_deadline: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    game_state_text: str | None = Field(
        default=None, sa_column=Column(sa.Text(), nullable=True)
    )
    student_summary_text: str | None = Field(
        default=None, sa_column=Column(sa.Text(), nullable=True)
    )
    move_buffer_crdt: bytes | None = Field(
        default=None, sa_column=Column(sa.LargeBinary(), nullable=True)
    )
    notes_crdt: bytes | None = Field(
        default=None, sa_column=Column(sa.LargeBinary(), nullable=True)
    )
    created_at: datetime = Field(
        default_factory=_utcnow, sa_column=_timestamptz_column()
    )

    @model_validator(mode="after")
    def _check_activity_type(self) -> Self:
        """Ensure the child discriminator remains fixed at wargame."""
        if self.activity_type != "wargame":
            msg = "wargame team activity_type must be 'wargame'"
            raise ValueError(msg)
        return self


class WargameMessage(SQLModel, table=True):
    """Canonical per-team message log for wargame turns.

    Message order is defined only by ``sequence_no``. ``created_at`` and
    ``edited_at`` are audit fields and must not be used to derive order.
    Earlier-turn edits or regenerations update rows in place.
    """

    __tablename__ = "wargame_message"
    __table_args__ = (
        UniqueConstraint(
            "team_id",
            "sequence_no",
            name="uq_wargame_message_team_sequence",
        ),
        sa.Index("ix_wargame_message_team_id", "team_id"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    team_id: UUID = Field(sa_column=_cascade_fk_column("wargame_team.id"))
    sequence_no: int = Field()
    role: str = Field(max_length=50)
    content: str = Field(sa_column=Column(sa.Text(), nullable=False))
    thinking: str | None = Field(
        default=None, sa_column=Column(sa.Text(), nullable=True)
    )
    metadata_json: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column("metadata", JSONB, nullable=True),
    )
    edited_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    created_at: datetime = Field(
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
    next_tag_order: int = Field(default=0)
    next_group_order: int = Field(default=0)
    enable_save_as_draft: bool = Field(default=False)
    title: str | None = Field(default=None, sa_column=Column(sa.Text(), nullable=True))
    shared_with_class: bool = Field(default=False)
    search_text: str | None = Field(
        default=None, sa_column=Column(sa.Text(), nullable=True)
    )
    # server_default="true" (string) matches the existing pattern in this file
    # (see CourseRoleRef.is_staff above which uses server_default="false").
    # The migration uses sa.text("true") which is equivalent at the DB level.
    search_dirty: bool = Field(
        default=True,
        sa_column=Column(sa.Boolean(), nullable=False, server_default="true"),
    )
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
        auto_number_paragraphs: True = auto-number mode (default), False = source-number
            mode (AustLII documents with ``<li value>`` attributes).
        paragraph_map: Maps char-offset (string key) to paragraph number. Empty dict
            is the safe default for documents without a computed map.
        source_document_id: Nullable FK to the template document this was
            cloned from. NULL for user-uploaded documents or when the
            source is deleted (ON DELETE SET NULL).
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
    auto_number_paragraphs: bool = Field(
        default=True,
        sa_column=Column(sa.Boolean(), nullable=False, server_default="true"),
    )
    paragraph_map: dict[str, int] = Field(
        default_factory=dict,
        sa_column=Column(sa.JSON(), nullable=False, server_default="{}"),
    )
    source_document_id: UUID | None = Field(
        default=None,
        sa_column=_set_null_fk_column("workspace_document.id"),
    )


class TagGroup(SQLModel, table=True):
    """Visual container for grouping tags within a workspace.

    TagGroups organise related tags (e.g. "Legal Case Brief" headings).
    CASCADE-deleted when the parent Workspace is deleted.

    Attributes:
        id: Primary key UUID, auto-generated.
        workspace_id: Foreign key to Workspace (CASCADE DELETE).
        name: Group display name.
        order_index: Display order within workspace.
        created_at: Timestamp when group was created.
    """

    __tablename__ = "tag_group"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_tag_group_workspace_name"),
        CheckConstraint(
            "color IS NULL OR color ~ '^#[0-9a-fA-F]{6}$'",
            name="ck_tag_group_color_hex",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    workspace_id: UUID = Field(sa_column=_cascade_fk_column("workspace.id"))
    name: str = Field(max_length=100)
    color: str | None = Field(default=None, max_length=7)
    order_index: int = Field(default=0)
    created_at: datetime = Field(
        default_factory=_utcnow, sa_column=_timestamptz_column()
    )


class Tag(SQLModel, table=True):
    """Per-workspace annotation tag.

    Tags belong to a workspace and optionally to a TagGroup.
    CASCADE-deleted when the parent Workspace is deleted.
    If the parent TagGroup is deleted, group_id is set to NULL.

    Attributes:
        id: Primary key UUID, auto-generated.
        workspace_id: Foreign key to Workspace (CASCADE DELETE).
        group_id: Optional FK to TagGroup (SET NULL on delete).
        name: Tag display name.
        description: Optional longer description of the tag's purpose.
        color: Hex colour string (e.g. "#1f77b4").
        locked: Whether students can modify this tag.
        order_index: Display order within group or workspace.
        created_at: Timestamp when tag was created.
    """

    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_tag_workspace_name"),
        CheckConstraint("color ~ '^#[0-9a-fA-F]{6}$'", name="ck_tag_color_hex"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    workspace_id: UUID = Field(sa_column=_cascade_fk_column("workspace.id"))
    group_id: UUID | None = Field(
        default=None, sa_column=_set_null_fk_column("tag_group.id")
    )
    name: str = Field(max_length=100)
    description: str | None = Field(
        default=None, sa_column=Column(sa.Text(), nullable=True)
    )
    color: str = Field(max_length=7)
    locked: bool = Field(default=False)
    order_index: int = Field(default=0)
    created_at: datetime = Field(
        default_factory=_utcnow, sa_column=_timestamptz_column()
    )


class ACLEntry(SQLModel, table=True):
    """Per-user permission grant for either a workspace or a wargame team.

    Exactly one target FK (workspace_id or team_id) must be set.
    """

    __tablename__ = "acl_entry"
    __table_args__ = (
        CheckConstraint(
            "num_nonnulls(workspace_id, team_id) = 1",
            name="ck_acl_entry_exactly_one_target",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    workspace_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            Uuid(),
            ForeignKey("workspace.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    team_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            Uuid(),
            ForeignKey("wargame_team.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
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

    @model_validator(mode="after")
    def _check_exactly_one_target(self) -> Self:
        """Ensure ACL entry targets exactly one resource type."""
        has_workspace_target = self.workspace_id is not None
        has_team_target = self.team_id is not None
        if has_workspace_target == has_team_target:
            msg = "exactly one of workspace_id or team_id must be set"
            raise ValueError(msg)
        return self
