"""Bulk student enrolment -- imperative shell for XLSX-parsed entries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import uuid4

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from promptgrimoire.db.courses import (
    DuplicateEnrollmentError,
    _enroll_user_with_session,
)
from promptgrimoire.db.engine import get_session
from promptgrimoire.db.models import StudentGroup, StudentGroupMembership, User
from promptgrimoire.db.users import _find_or_create_user_with_session

if TYPE_CHECKING:
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

    from promptgrimoire.enrol.xlsx_parser import EnrolmentEntry

logger = structlog.get_logger()


class StudentIdConflictError(Exception):
    """Raised when a user's existing student_id differs from the import."""

    def __init__(self, conflicts: list[tuple[str, str, str]]) -> None:
        self.conflicts = conflicts  # (email, existing_id, new_id)
        details = "; ".join(
            f"{email}: existing={old!r}, new={new!r}" for email, old, new in conflicts
        )
        super().__init__(f"Student ID conflicts: {details}")


@dataclass(frozen=True, slots=True)
class EnrolmentReport:
    """Summary of a bulk-enrolment run."""

    entries_processed: int
    users_created: int
    users_existing: int
    enrolments_created: int
    enrolments_skipped: int
    groups_created: int
    group_memberships_created: int
    student_ids_overwritten: int
    student_id_warnings: tuple[tuple[str, str, str], ...]


async def bulk_enrol(
    entries: list[EnrolmentEntry],
    course_id: UUID,
    role: str = "student",
    *,
    force: bool = False,
) -> EnrolmentReport:
    """Enrol students atomically from parsed XLSX entries.

    All writes happen inside a single database session. Any failure
    rolls back the entire import -- no partial state is persisted.

    Parameters
    ----------
    entries:
        Parsed enrolment entries from the XLSX parser.
    course_id:
        Target course UUID.
    role:
        Course-level role for all enrolments (default: ``"student"``).
    force:
        When ``True``, overwrite conflicting student IDs instead of
        raising :class:`StudentIdConflictError`.

    Returns
    -------
    EnrolmentReport
        Summary counters for the completed enrolment.

    Raises
    ------
    StudentIdConflictError
        When ``force=False`` and any existing user has a different
        ``student_id`` than the import provides.
    """
    async with get_session() as session:
        return await _bulk_enrol_entries(
            session,
            entries,
            course_id,
            role,
            force,
        )


async def _resolve_users(
    session: AsyncSession,
    entries: list[EnrolmentEntry],
) -> tuple[list[tuple[EnrolmentEntry, User]], int, int, list[tuple[str, str, str]]]:
    """Resolve users and detect student_id conflicts.

    Returns (resolved, users_created, users_existing, conflicts).
    """
    users_created = 0
    users_existing = 0
    conflicts: list[tuple[str, str, str]] = []
    resolved: list[tuple[EnrolmentEntry, User]] = []

    for entry in entries:
        user, created = await _find_or_create_user_with_session(
            session,
            entry.email,
            entry.display_name,
        )
        if created:
            users_created += 1
        else:
            users_existing += 1

        # Set student_id if absent; record conflict if different.
        # Normalise empty string to None — the unique constraint treats
        # '' as a real value, causing conflicts when multiple users lack IDs.
        effective_student_id = entry.student_id or None
        if user.student_id is None or user.student_id == "":
            if effective_student_id is not None:
                user.student_id = effective_student_id
                session.add(user)
                await session.flush()
        elif user.student_id != effective_student_id:
            conflicts.append(
                (entry.email, user.student_id, entry.student_id),
            )

        resolved.append((entry, user))

    return resolved, users_created, users_existing, conflicts


async def _apply_student_id_overwrites(
    session: AsyncSession,
    conflicts: list[tuple[str, str, str]],
) -> int:
    """Force-overwrite conflicting student_ids. Returns count."""
    for email, _old, new_id in conflicts:
        result = await session.execute(
            select(User).where(
                User.email == email.lower(),  # type: ignore[arg-type]  -- SQLAlchemy column expression
            )
        )
        user = result.scalar_one()
        user.student_id = new_id
        session.add(user)
    await session.flush()
    return len(conflicts)


async def _create_enrolments(
    session: AsyncSession,
    resolved: list[tuple[EnrolmentEntry, User]],
    course_id: UUID,
    role: str,
) -> tuple[int, int]:
    """Create course enrolments. Returns (created, skipped)."""
    created = 0
    skipped = 0
    for _entry, user in resolved:
        try:
            await _enroll_user_with_session(
                session,
                course_id,
                user.id,
                role,
            )
            created += 1
        except DuplicateEnrollmentError:
            logger.warning("duplicate_enrollment_skipped", operation="enrol_users")
            skipped += 1
    return created, skipped


async def _create_groups_and_memberships(
    session: AsyncSession,
    resolved: list[tuple[EnrolmentEntry, User]],
    course_id: UUID,
) -> tuple[int, int]:
    """Create student groups and memberships.

    Returns (groups_created, memberships_created).
    """
    groups_created = 0
    memberships_created = 0

    for entry, user in resolved:
        for group_name in entry.groups:
            # Find-or-create group via ON CONFLICT DO NOTHING
            stmt = pg_insert(StudentGroup).values(
                id=uuid4(),
                course_id=course_id,
                name=group_name,
            )
            stmt = stmt.on_conflict_do_nothing(
                constraint="uq_student_group_course_name",
            )
            result = await session.execute(stmt)
            if result.rowcount == 1:  # type: ignore[union-attr]  -- CursorResult has rowcount
                groups_created += 1

            # Query back to get the actual group row
            group_result = await session.execute(
                select(StudentGroup).where(
                    StudentGroup.course_id == course_id,  # type: ignore[arg-type]  -- SQLAlchemy column expression
                    StudentGroup.name == group_name,  # type: ignore[arg-type]  -- SQLAlchemy column expression
                )
            )
            group = group_result.scalar_one()

            # Create membership via ON CONFLICT DO NOTHING
            mem_stmt = pg_insert(StudentGroupMembership).values(
                id=uuid4(),
                student_group_id=group.id,
                user_id=user.id,
            )
            mem_stmt = mem_stmt.on_conflict_do_nothing(
                constraint="uq_student_group_membership_group_user",
            )
            mem_result = await session.execute(mem_stmt)
            if mem_result.rowcount == 1:  # type: ignore[union-attr]  -- CursorResult has rowcount
                memberships_created += 1

    return groups_created, memberships_created


async def _bulk_enrol_entries(
    session: AsyncSession,
    entries: list[EnrolmentEntry],
    course_id: UUID,
    role: str,
    force: bool,
) -> EnrolmentReport:
    """Apply parsed entries inside a caller-owned session."""
    resolved, users_created, users_existing, conflicts = await _resolve_users(
        session, entries
    )

    # Handle student_id conflicts
    student_ids_overwritten = 0
    if conflicts and not force:
        raise StudentIdConflictError(conflicts)
    if conflicts and force:
        student_ids_overwritten = await _apply_student_id_overwrites(session, conflicts)

    enrolments_created, enrolments_skipped = await _create_enrolments(
        session, resolved, course_id, role
    )

    groups_created, group_memberships_created = await _create_groups_and_memberships(
        session,
        resolved,
        course_id,
    )

    return EnrolmentReport(
        entries_processed=len(entries),
        users_created=users_created,
        users_existing=users_existing,
        enrolments_created=enrolments_created,
        enrolments_skipped=enrolments_skipped,
        groups_created=groups_created,
        group_memberships_created=group_memberships_created,
        student_ids_overwritten=student_ids_overwritten,
        student_id_warnings=tuple(conflicts),
    )
