"""Cached role queries.

Loads role classification data from the ``course_role`` reference table
once, then serves it from memory for the process lifetime.
"""

from __future__ import annotations

from sqlmodel import select

from promptgrimoire.db.engine import get_session
from promptgrimoire.db.models import CourseRoleRef

_staff_roles_cache: frozenset[str] | None = None
_all_roles_cache: tuple[str, ...] | None = None


def _reset_staff_roles_cache() -> None:
    """Clear the cached staff roles (for test isolation)."""
    global _staff_roles_cache  # noqa: PLW0603
    _staff_roles_cache = None


def _reset_all_roles_cache() -> None:
    """Clear the cached all-roles list (for test isolation)."""
    global _all_roles_cache  # noqa: PLW0603
    _all_roles_cache = None


async def get_all_roles() -> tuple[str, ...]:
    """Return all course role names ordered by level (ascending).

    Loaded from the database on first call, then cached for the
    process lifetime.  Reference data is seeded by migration and
    does not change at runtime.
    """
    global _all_roles_cache  # noqa: PLW0603
    if _all_roles_cache is None:
        async with get_session() as session:
            result = await session.exec(
                select(CourseRoleRef.name).order_by(CourseRoleRef.level)  # type: ignore[arg-type]  -- SQLAlchemy column expr vs int stub mismatch
            )
            _all_roles_cache = tuple(result.all())
    return _all_roles_cache


async def get_staff_roles() -> frozenset[str]:
    """Return the set of course role names where ``is_staff=True``.

    Loaded from the database on first call, then cached for the
    process lifetime.  Reference data is seeded by migration and
    does not change at runtime.
    """
    global _staff_roles_cache  # noqa: PLW0603
    if _staff_roles_cache is None:
        async with get_session() as session:
            result = await session.exec(
                select(CourseRoleRef.name).where(
                    CourseRoleRef.is_staff == True  # noqa: E712
                )
            )
            _staff_roles_cache = frozenset(result.all())
    return _staff_roles_cache
