"""Background worker for extracting searchable text from dirty workspaces.

Polls for workspaces with search_dirty=True, deserialises their CRDT
state, extracts text via extract_searchable_text(), and writes the
result to workspace.search_text.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text

from promptgrimoire.db.engine import get_session
from promptgrimoire.db.search import extract_searchable_text

logger = logging.getLogger(__name__)


async def process_dirty_workspaces(batch_size: int = 50) -> int:
    """Process workspaces with search_dirty=True.

    For each dirty workspace:
    1. Loads tags to build a UUID-to-name mapping.
    2. Calls extract_searchable_text() with the CRDT state.
    3. Writes extracted text to search_text and clears search_dirty.

    Args:
        batch_size: Maximum number of workspaces to process per call.

    Returns:
        Count of workspaces processed.
    """
    processed = 0

    async with get_session() as session:
        # Fetch dirty workspaces.  FOR UPDATE SKIP LOCKED prevents concurrent
        # workers from double-processing the same rows.
        result = await session.execute(
            text(
                "SELECT id, crdt_state FROM workspace "
                "WHERE search_dirty = true "
                "LIMIT :batch_size "
                "FOR UPDATE SKIP LOCKED"
            ),
            {"batch_size": batch_size},
        )
        rows = result.fetchall()

    for row in rows:
        workspace_id = row[0]
        crdt_state = row[1]

        try:
            # Build tag_names mapping for this workspace
            tag_names: dict[str, str] = {}
            async with get_session() as session:
                tag_result = await session.execute(
                    text("SELECT id, name FROM tag WHERE workspace_id = :ws_id"),
                    {"ws_id": str(workspace_id)},
                )
                for tag_row in tag_result.fetchall():
                    tag_names[str(tag_row[0])] = tag_row[1]

            # Extract searchable text
            crdt_bytes: bytes | None = bytes(crdt_state) if crdt_state else None
            extracted_text = extract_searchable_text(crdt_bytes, tag_names)

            # Update workspace.  The CAS guard (AND search_dirty = true) ensures
            # that if a concurrent CRDT save set search_dirty = true between the
            # read and this write, the flag is NOT cleared here -- the worker
            # will re-process the workspace on the next poll cycle.
            async with get_session() as session:
                await session.execute(
                    text(
                        "UPDATE workspace "
                        "SET search_text = :search_text, search_dirty = false "
                        "WHERE id = :ws_id AND search_dirty = true"
                    ),
                    {"search_text": extracted_text, "ws_id": str(workspace_id)},
                )

            processed += 1

        except Exception:
            logger.exception(
                "Failed to process workspace %s for search extraction",
                workspace_id,
            )

    if processed > 0:
        logger.info("Processed %d dirty workspaces for search extraction", processed)

    return processed


async def start_search_worker(interval_seconds: float = 30.0) -> None:
    """Start the background search extraction worker.

    Runs process_dirty_workspaces() in a loop with the given interval
    between iterations. Catches and logs exceptions per iteration
    to prevent the loop from crashing.

    Args:
        interval_seconds: Sleep duration between polling cycles.
    """
    logger.info("Search extraction worker started (interval=%.1fs)", interval_seconds)
    while True:
        try:
            await process_dirty_workspaces()
        except Exception:
            logger.exception("Search extraction worker iteration failed")
        await asyncio.sleep(interval_seconds)
