"""Tag seeding helpers for annotation E2E tests.

Provides deterministic UUID generation for tag groups and tags,
direct-SQL seeding, and tag locking.
"""

from __future__ import annotations

import os
import uuid

# Legal Case Brief tag seed data
# (mirrors cli.py:_seed_tags_for_activity).
_SEED_GROUP_DEFS: list[tuple[str, str, list[tuple[str, str]]]] = [
    (
        "Case ID",
        "#4a90d9",
        [
            ("Jurisdiction", "#1f77b4"),
            ("Procedural History", "#ff7f0e"),
            ("Decision", "#e377c2"),
            ("Order", "#7f7f7f"),
        ],
    ),
    (
        "Analysis",
        "#d9534f",
        [
            ("Legally Relevant Facts", "#2ca02c"),
            ("Legal Issues", "#d62728"),
            ("Reasons", "#9467bd"),
            ("Court's Reasoning", "#8c564b"),
        ],
    ),
    (
        "Sources",
        "#5cb85c",
        [
            ("Domestic Sources", "#bcbd22"),
            ("Reflection", "#17becf"),
        ],
    ),
]


def seed_tag_id(workspace_id: str, tag_name: str) -> str:
    """Compute the deterministic UUID for a seeded tag.

    Uses the same uuid5 derivation as ``_seed_tags_for_workspace()``,
    so the returned ID matches the ``id`` column in the ``tag`` table
    after seeding.  Useful for constructing ``data-testid`` selectors
    in Playwright tests (e.g. ``f"tag-name-input-{seed_tag_id(ws, 'Jurisdiction')}"``)
    """
    ws_ns = uuid.UUID(workspace_id)
    return str(uuid.uuid5(ws_ns, f"seed-tag-{tag_name}"))


def seed_group_id(workspace_id: str, group_name: str) -> str:
    """Compute the deterministic UUID for a seeded tag group.

    Uses the same uuid5 derivation as ``_seed_tags_for_workspace()``.
    """
    ws_ns = uuid.UUID(workspace_id)
    return str(uuid.uuid5(ws_ns, f"seed-group-{group_name}"))


def _seed_tags_for_workspace(workspace_id: str) -> None:
    """Seed Legal Case Brief tags into a workspace via sync DB connection.

    Inserts 3 tag groups and 10 tags using raw SQL with
    ``ON CONFLICT (id) DO NOTHING`` so the operation is idempotent.

    Deterministic UUIDs are derived from the workspace_id using uuid5
    so re-seeding the same workspace always produces the same rows.

    Follows the sync DB pattern of ``_grant_workspace_access()`` in
    ``conftest.py``.

    Args:
        workspace_id: UUID string of the target workspace.
    """
    from sqlalchemy import create_engine, text

    db_url = os.environ.get("DATABASE__URL", "")
    if not db_url:
        return
    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
    engine = create_engine(sync_url)

    ws_ns = uuid.UUID(workspace_id)

    with engine.begin() as conn:
        for group_idx, (group_name, group_color, tags) in enumerate(_SEED_GROUP_DEFS):
            group_id = uuid.uuid5(ws_ns, f"seed-group-{group_name}")
            conn.execute(
                text(
                    "INSERT INTO tag_group"
                    " (id, workspace_id, name,"
                    " color, order_index, created_at)"
                    " VALUES (:id, CAST(:ws AS uuid),"
                    " :name, :color, :order_index, now())"
                    " ON CONFLICT (id) DO NOTHING"
                ),
                {
                    "id": str(group_id),
                    "ws": workspace_id,
                    "name": group_name,
                    "color": group_color,
                    "order_index": group_idx,
                },
            )

            for tag_idx, (tag_name, tag_color) in enumerate(tags):
                tag_id = uuid.uuid5(ws_ns, f"seed-tag-{tag_name}")
                conn.execute(
                    text(
                        "INSERT INTO tag"
                        " (id, workspace_id, group_id,"
                        " name, color, locked,"
                        " order_index, created_at)"
                        " VALUES"
                        " (:id, CAST(:ws AS uuid),"
                        " CAST(:gid AS uuid),"
                        " :name, :color, :locked,"
                        " :order_index, now())"
                        " ON CONFLICT (id) DO NOTHING"
                    ),
                    {
                        "id": str(tag_id),
                        "ws": workspace_id,
                        "gid": str(group_id),
                        "name": tag_name,
                        "color": tag_color,
                        "locked": False,
                        "order_index": tag_idx,
                    },
                )

        # Update atomic counters so the next create_tag()/create_tag_group()
        # claims the correct order_index (not 0, which would collide).
        total_tags = sum(len(tags) for _, _, tags in _SEED_GROUP_DEFS)
        total_groups = len(_SEED_GROUP_DEFS)
        conn.execute(
            text(
                "UPDATE workspace"
                " SET next_tag_order = :tag_count,"
                "     next_group_order = :group_count"
                " WHERE id = CAST(:ws AS uuid)"
            ),
            {
                "tag_count": total_tags,
                "group_count": total_groups,
                "ws": workspace_id,
            },
        )

    engine.dispose()


def _lock_tag_in_db(workspace_id: str, tag_name: str) -> None:
    """Lock a seeded tag via direct SQL update.

    Uses the deterministic UUID from ``seed_tag_id`` to set
    ``locked = true`` on the tag row.

    Follows the same sync-DB pattern as ``_seed_tags_for_workspace``.

    Args:
        workspace_id: UUID string of the workspace.
        tag_name: Name of the seeded tag to lock.
    """
    from sqlalchemy import create_engine, text

    db_url = os.environ.get("DATABASE__URL", "")
    if not db_url:
        return
    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
    engine = create_engine(sync_url)

    tag_id = seed_tag_id(workspace_id, tag_name)

    with engine.begin() as conn:
        conn.execute(
            text("UPDATE tag SET locked = true WHERE id = CAST(:id AS uuid)"),
            {"id": tag_id},
        )
    engine.dispose()
