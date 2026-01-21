"""SQLModel database models for PromptGrimoire.

These models define the core database schema for users, classes, and conversations.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Uuid
from sqlmodel import Field, SQLModel


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
        created_at: Timestamp when user was created.
    """

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email: str = Field(unique=True, index=True, max_length=255)
    display_name: str = Field(max_length=100)
    stytch_member_id: str | None = Field(default=None, unique=True, index=True)
    created_at: datetime = Field(
        default_factory=_utcnow, sa_column=_timestamptz_column()
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
