"""SQLModel database models for PromptGrimoire.

These models define the core database schema for users, classes, and conversations.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, ForeignKey, UniqueConstraint, Uuid
from sqlmodel import Field, SQLModel


class CourseRole(StrEnum):
    """Role within a specific course enrollment.

    These are course-scoped roles, separate from Stytch org-level roles.
    """

    coordinator = "coordinator"  # Course owner, full control
    instructor = "instructor"  # Can manage content, see all student work
    tutor = "tutor"  # Can see assigned tutorial groups
    student = "student"  # Can access published content only


def _utcnow() -> datetime:
    """Return current UTC time as timezone-aware datetime."""
    return datetime.now(UTC)


def _timestamptz_column() -> Any:
    """Create a TIMESTAMP WITH TIME ZONE column for PostgreSQL."""
    return Column(DateTime(timezone=True), nullable=False)


def _cascade_fk_column(target: str) -> Any:
    """Create a UUID foreign key column with CASCADE DELETE."""
    return Column(Uuid(), ForeignKey(target, ondelete="CASCADE"), nullable=False)


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


class Class(SQLModel, table=True):
    """A class instance for student enrollment.

    Classes are enrollment containers that can be linked to courses.
    Students join via invite codes.

    Attributes:
        id: Primary key UUID, auto-generated.
        name: Display name for the class.
        owner_id: Foreign key to the instructor/owner User (CASCADE DELETE).
        invite_code: Unique code students use to join.
        created_at: Timestamp when class was created.
    """

    __tablename__ = "class"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(max_length=200)
    owner_id: UUID = Field(sa_column=_cascade_fk_column("user.id"))
    invite_code: str = Field(unique=True, max_length=20)
    created_at: datetime = Field(
        default_factory=_utcnow, sa_column=_timestamptz_column()
    )


class Conversation(SQLModel, table=True):
    """A conversation submitted by a user for annotation.

    Stores the raw conversation text and optional CRDT state for
    real-time collaborative annotation.

    Attributes:
        id: Primary key UUID, auto-generated.
        class_id: Foreign key to the Class (CASCADE DELETE).
        owner_id: Foreign key to the User (CASCADE DELETE).
        raw_text: Full conversation text.
        crdt_state: Serialized pycrdt state for collaborative editing.
        created_at: Timestamp when conversation was created.
    """

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    class_id: UUID = Field(sa_column=_cascade_fk_column("class.id"))
    owner_id: UUID = Field(sa_column=_cascade_fk_column("user.id"))
    raw_text: str
    crdt_state: bytes | None = None
    created_at: datetime = Field(
        default_factory=_utcnow, sa_column=_timestamptz_column()
    )


class AnnotationDocumentState(SQLModel, table=True):
    """Persisted CRDT state for annotation documents.

    Stores the full pycrdt document state for recovery after server restart.
    Each case_id has at most one state record.

    Attributes:
        id: Primary key UUID, auto-generated.
        case_id: Unique identifier for the document (e.g., "demo-case-183").
        crdt_state: Serialized pycrdt state bytes.
        highlight_count: Cached count of highlights (denormalized for quick display).
        last_editor: Display name of last user to edit.
        created_at: Timestamp when document was first persisted.
        updated_at: Timestamp when document was last persisted.
    """

    __tablename__ = "annotation_document_state"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    case_id: str = Field(unique=True, index=True, max_length=255)
    crdt_state: bytes
    highlight_count: int = Field(default=0)
    last_editor: str | None = Field(default=None, max_length=100)
    created_at: datetime = Field(
        default_factory=_utcnow, sa_column=_timestamptz_column()
    )
    updated_at: datetime = Field(
        default_factory=_utcnow, sa_column=_timestamptz_column()
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
        created_at: Timestamp when course was created.
    """

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    code: str = Field(max_length=20, index=True)
    name: str = Field(max_length=200)
    semester: str = Field(max_length=20, index=True)
    is_archived: bool = Field(default=False)
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
    role: CourseRole = Field(default=CourseRole.student)
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
