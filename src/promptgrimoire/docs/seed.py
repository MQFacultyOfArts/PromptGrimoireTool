"""In-process DB seeding for guide scripts.

Creates users and enrols them in courses using the DB layer directly,
avoiding subprocess CLI calls that connect to a different database when
branch-suffix isolation is active.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import logging

import structlog
from sqlmodel import select

from promptgrimoire.db.courses import DuplicateEnrollmentError, enroll_user
from promptgrimoire.db.engine import get_session, init_db
from promptgrimoire.db.models import Course
from promptgrimoire.db.users import create_user, get_user_by_email

logger = structlog.get_logger()
logging.getLogger(__name__).setLevel(logging.INFO)


async def _ensure_user(email: str, display_name: str) -> None:
    """Create a user if they don't already exist."""
    user = await get_user_by_email(email)
    if user is None:
        await create_user(email, display_name)


async def _ensure_enrolled(email: str, code: str, semester: str) -> None:
    """Enrol user in a course, ignoring duplicates.

    Raises RuntimeError if the course is not found.
    """
    user = await get_user_by_email(email)
    if user is None:
        msg = f"User {email!r} not found — create them first"
        raise RuntimeError(msg)

    async with get_session() as session:
        result = await session.exec(
            select(Course).where(Course.code == code).where(Course.semester == semester)
        )
        course = result.first()

    if course is None:
        msg = f"Course {code} {semester} not found — instructor guide must run first"
        raise RuntimeError(msg)

    with contextlib.suppress(DuplicateEnrollmentError):
        await enroll_user(course.id, user.id, role="student")


async def _seed_user_and_enrol(
    email: str,
    display_name: str,
    code: str,
    semester: str,
) -> None:
    """Create a user and enrol them in a course (idempotent)."""
    logger.debug("[SEED] init_db for %s", email)
    await init_db()
    logger.debug("[SEED] ensuring user %s", email)
    await _ensure_user(email, display_name)
    logger.debug("[SEED] ensuring enrolled %s in %s %s", email, code, semester)
    await _ensure_enrolled(email, code, semester)
    logger.debug("[SEED] done: %s", email)


def _run_in_thread(coro: object) -> None:
    """Run an async coroutine in a new thread with its own event loop.

    The NiceGUI server occupies the main event loop, so ``asyncio.run()``
    raises ``RuntimeError``. Spawning a dedicated thread with a fresh
    loop sidesteps this.
    """
    exc: BaseException | None = None

    def target() -> None:
        nonlocal exc
        try:
            asyncio.run(coro)  # type: ignore[arg-type]
        except BaseException as e:
            exc = e  # Deferred re-raise after thread cleanup (line 94)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(target).result()

    if exc is not None:
        raise exc


def seed_user_and_enrol(
    email: str,
    display_name: str,
    *,
    code: str = "UNIT1234",
    semester: str = "S1 2026",
) -> None:
    """Sync wrapper: create user and enrol in course via DB layer.

    Safe to call from sync Playwright guide scripts even when a NiceGUI
    event loop is already running. Executes async DB operations in a
    separate thread with its own event loop, using the same database
    (same process, same environment).
    """
    _run_in_thread(_seed_user_and_enrol(email, display_name, code, semester))
