"""Background worker for firing expired wargame deadlines.

Polls for WargameTeam rows with current_deadline in the past and
round_state='drafting', then fires on_deadline_fired() for each
affected activity. Follows the same polling-loop pattern as
search_worker.py.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import text

from promptgrimoire.db.engine import get_session

logger = logging.getLogger(__name__)


async def check_expired_deadlines() -> int:
    """Check for and fire expired wargame deadlines.

    Queries for distinct activity IDs where any team has
    current_deadline <= now() and round_state = 'drafting'.
    Fires on_deadline_fired() for each.

    Returns
    -------
    int
        Number of activities processed.
    """
    # Import here to avoid circular imports (on_deadline_fired is in db/wargames.py
    # which imports from wargame/ which may transitively touch models)
    from promptgrimoire.db.wargames import (
        on_deadline_fired,
    )

    async with get_session() as session:
        result = await session.execute(
            text(
                "SELECT DISTINCT activity_id "
                "FROM wargame_team "
                "WHERE current_deadline <= :now "
                "AND round_state = 'drafting'"
            ),
            {"now": datetime.now(UTC)},
        )
        activity_ids = [row[0] for row in result.fetchall()]

    processed = 0
    for activity_id in activity_ids:
        try:
            await on_deadline_fired(activity_id)
            processed += 1
            logger.info("Deadline fired for activity %s", activity_id)
        except Exception:
            logger.exception("Failed to process deadline for activity %s", activity_id)

    return processed


async def _next_deadline_seconds() -> float | None:
    """Return seconds until the nearest future deadline, or None."""
    async with get_session() as session:
        result = await session.execute(
            text(
                "SELECT MIN(current_deadline) "
                "FROM wargame_team "
                "WHERE current_deadline IS NOT NULL "
                "AND round_state = 'drafting'"
            ),
        )
        nearest = result.scalar_one_or_none()

    if nearest is None:
        return None
    delta = (nearest - datetime.now(UTC)).total_seconds()
    return max(delta, 0.0)


async def start_deadline_worker(
    max_interval: float = 30.0,
) -> None:
    """Start the background deadline polling worker.

    Runs check_expired_deadlines() in a loop. Sleep duration adapts:
    if a deadline is imminent (within max_interval), sleeps until 1
    second after that deadline. Otherwise sleeps for max_interval.

    Parameters
    ----------
    max_interval : float
        Maximum sleep duration between polling cycles.
    """
    logger.info("Deadline worker started (max_interval=%.1fs)", max_interval)
    while True:
        try:
            await check_expired_deadlines()
        except Exception:
            logger.exception("Deadline worker iteration failed")

        # Adaptive sleep: if a deadline is coming soon, wake up for it
        try:
            next_in = await _next_deadline_seconds()
        except Exception:
            next_in = None

        if next_in is not None and next_in < max_interval:
            sleep_for = next_in + 1.0  # wake 1 second after deadline
        else:
            sleep_for = max_interval

        await asyncio.sleep(sleep_for)
