"""Cached role queries.

Loads role classification data from the ``course_role`` reference table
once, then serves it from memory for the process lifetime.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlmodel import select

from promptgrimoire.db.engine import get_session
from promptgrimoire.db.models import CourseRoleRef

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

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


async def get_all_roles(*, session: AsyncSession | None = None) -> tuple[str, ...]:
    """Return all course role names ordered by level (ascending).

    Loaded from the database on first call, then cached for the
    process lifetime.  Reference data is seeded by migration and
    does not change at runtime.

    When an ``AsyncSession`` is supplied, the cold-load query reuses the
    caller's existing transaction instead of opening a nested session.
    Callers already inside an ``async with get_session()`` block MUST
    pass ``session=session`` to avoid a pool deadlock under saturation.
    """
    global _all_roles_cache  # noqa: PLW0603
    if _all_roles_cache is None:
        if session is None:
            async with get_session() as db_session:
                result = await db_session.exec(
                    select(CourseRoleRef.name).order_by("level")
                )
                _all_roles_cache = tuple(result.all())
        else:
            result = await session.exec(select(CourseRoleRef.name).order_by("level"))
            _all_roles_cache = tuple(result.all())
    return _all_roles_cache


async def warm_role_caches() -> None:
    """Populate role caches before accepting traffic.

    Call during application startup, after ``init_db()``, so every page
    load from then on sees a warm cache and never triggers the cold-load
    path. This closes the last remaining precondition for the cold-cache
    nested-session deadlock under saturated-pool load.

    Both cache fills share a single outer session so startup issues one
    checkout rather than two. Once both caches are warm, the function
    returns before opening a session.
    """
    if _staff_roles_cache is not None and _all_roles_cache is not None:
        return

    async with get_session() as session:
        await get_staff_roles(session=session)
        await get_all_roles(session=session)


async def get_staff_roles(*, session: AsyncSession | None = None) -> frozenset[str]:
    """Return the set of course role names where ``is_staff=True``.

    Loaded from the database on first call, then cached for the
    process lifetime.  Reference data is seeded by migration and
    does not change at runtime.

    When an ``AsyncSession`` is supplied, the cold-load query reuses the
    caller's existing transaction instead of opening a nested session.
    Callers already inside an ``async with get_session()`` block MUST
    pass ``session=session`` to avoid a pool deadlock under saturation.
    """
    global _staff_roles_cache  # noqa: PLW0603
    if _staff_roles_cache is None:
        if session is None:
            async with get_session() as db_session:
                result = await db_session.exec(
                    select(CourseRoleRef.name).where(
                        CourseRoleRef.is_staff == True  # noqa: E712
                    )
                )
                _staff_roles_cache = frozenset(result.all())
        else:
            result = await session.exec(
                select(CourseRoleRef.name).where(
                    CourseRoleRef.is_staff == True  # noqa: E712
                )
            )
            _staff_roles_cache = frozenset(result.all())
    return _staff_roles_cache
