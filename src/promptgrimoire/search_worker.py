"""Background worker for extracting searchable text from dirty workspaces.

Polls for workspaces with search_dirty=True, deserialises their CRDT
state, extracts text via extract_searchable_text(), and writes the
result to workspace.search_text.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text

from promptgrimoire.db.crdt_extraction import extract_searchable_text
from promptgrimoire.db.engine import get_session

logger = logging.getLogger(__name__)


async def process_dirty_workspaces(batch_size: int = 500) -> int:
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
        # Fetch dirty workspaces.  FOR UPDATE SKIP LOCKED prevents two workers
        # from selecting the same batch simultaneously.  The lock is released
        # when this session commits (before processing begins), so concurrent
        # workers starting later may still pick up the same rows.  The CAS
        # guard on the UPDATE (AND search_dirty = true) is the actual
        # correctness mechanism — it prevents two workers from both clearing
        # the flag.  Double extraction is possible but harmless (idempotent).
        result = await session.execute(
            text(
                "SELECT w.id, w.crdt_state, "
                "  COALESCE(w.title, '') AS ws_title, "
                "  COALESCE(a.title, '') AS activity_title "
                "FROM workspace w "
                "LEFT JOIN activity a ON a.id = w.activity_id "
                "WHERE w.search_dirty = true "
                "LIMIT :batch_size "
                "FOR UPDATE OF w SKIP LOCKED"
            ),
            {"batch_size": batch_size},
        )
        rows = result.fetchall()

    # Batch-fetch tags for all workspaces (fixes N+1 query per workspace)
    ws_ids = [row[0] for row in rows]
    tag_map: dict[str, dict[str, str]] = {str(ws_id): {} for ws_id in ws_ids}
    if ws_ids:
        async with get_session() as session:
            tag_result = await session.execute(
                text(
                    "SELECT workspace_id, id, name FROM tag "
                    "WHERE workspace_id = ANY(:ws_ids)"
                ),
                {"ws_ids": ws_ids},
            )
            for tag_row in tag_result.fetchall():
                tag_map[str(tag_row[0])][str(tag_row[1])] = tag_row[2]

    for workspace_id, crdt_state, ws_title, activity_title in rows:
        try:
            tag_names = tag_map.get(str(workspace_id), {})

            # Extract CRDT content and prepend titles so search_text
            # contains everything needed for FTS (matching the GIN index
            # on to_tsvector('english', COALESCE(search_text, ''))).
            crdt_bytes: bytes | None = (
                bytes(crdt_state) if crdt_state is not None else None
            )
            crdt_text = extract_searchable_text(crdt_bytes, tag_names)
            title_prefix = f"{ws_title} {activity_title}".strip()
            extracted_text = (
                f"{title_prefix}\n{crdt_text}" if title_prefix else crdt_text
            )

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


async def start_search_worker(
    interval_seconds: float = 30.0,
    batch_size: int = 500,
) -> None:
    """Start the background search extraction worker.

    Runs process_dirty_workspaces() in a loop.  When a batch is full
    (processed == batch_size), loops immediately to drain the queue.
    Only sleeps when a batch comes back short (queue drained).

    Parameters
    ----------
    interval_seconds : float
        Sleep duration between polling cycles when queue is drained.
    batch_size : int
        Maximum workspaces per batch.
    """
    logger.info("Search extraction worker started (interval=%.1fs)", interval_seconds)
    while True:
        try:
            processed = await process_dirty_workspaces(batch_size=batch_size)
            if processed >= batch_size:
                # Batch was full — likely more work waiting.  Loop immediately.
                continue
        except Exception:
            logger.exception("Search extraction worker iteration failed")
        await asyncio.sleep(interval_seconds)
