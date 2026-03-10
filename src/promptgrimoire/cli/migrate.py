"""Tag migration and CRDT backfill commands."""

from __future__ import annotations

import asyncio
import sys
from typing import TYPE_CHECKING, Any

import typer
from rich.console import Console

if TYPE_CHECKING:
    from uuid import UUID

    from promptgrimoire.db.models import Workspace

console = Console()

migrate_app = typer.Typer(help="Migration and CRDT backfill tools.")


@migrate_app.command("backfill-tags")
def backfill_tags(
    fix: bool = typer.Option(
        False, help="Apply changes. Without this flag, only reports."
    ),
    workspace_id: str | None = typer.Option(
        None, help="Process a single workspace by UUID."
    ),
) -> None:
    """Backfill CRDT tags/tag_groups Maps from DB for all workspaces.

    By default runs in verify-only mode -- reports which workspaces need
    hydration without modifying data. Use --fix to apply changes.
    """
    from promptgrimoire.config import get_settings

    if not get_settings().database.url:
        console.print("[red]Error:[/] DATABASE__URL not set")
        sys.exit(1)

    asyncio.run(_backfill_tags(fix=fix, single_workspace_id=workspace_id))


def _tags_to_dicts(
    db_tags: list[Any],
    db_groups: list[Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Convert SQLModel Tag/TagGroup objects to dicts for CRDT hydration.

    The CRDT layer uses British ``"colour"``; the DB model uses
    American ``"color"`` -- this function handles the mapping.
    """
    tag_dicts = [
        {
            "id": t.id,
            "name": t.name,
            "colour": t.color,
            "group_id": t.group_id,
            "description": t.description,
            "order_index": t.order_index,
            "highlights": [],
        }
        for t in db_tags
    ]
    group_dicts = [
        {
            "id": g.id,
            "name": g.name,
            "colour": g.color,
            "order_index": g.order_index,
        }
        for g in db_groups
    ]
    return tag_dicts, group_dicts


def _detect_drift(
    crdt_tags: dict[str, Any],
    db_tags: list[Any],
    ws_id: UUID,
) -> bool:
    """Report tag-set drift between CRDT and DB.

    Returns ``True`` if any mismatch is found.
    """
    crdt_tag_ids = set(crdt_tags)
    db_tag_ids = {str(t.id) for t in db_tags}
    missing_in_crdt = db_tag_ids - crdt_tag_ids
    extra_in_crdt = crdt_tag_ids - db_tag_ids

    if not missing_in_crdt and not extra_in_crdt:
        return False

    if missing_in_crdt:
        console.print(
            f"  [yellow]DRIFT[/] {ws_id}: "
            f"{len(missing_in_crdt)} tags in DB missing from CRDT"
        )
    if extra_in_crdt:
        console.print(
            f"  [yellow]DRIFT[/] {ws_id}: {len(extra_in_crdt)} tags in CRDT not in DB"
        )
    return True


async def _check_and_fix_workspace(
    ws_id: UUID,
    workspace: Workspace,
    fix: bool,
) -> str:
    """Check a single workspace and optionally fix CRDT state.

    Returns: ``"ok"``, ``"hydrated"``, or ``"drift"``.
    """
    from promptgrimoire.crdt.annotation_doc import AnnotationDocument
    from promptgrimoire.db.tags import (
        list_tag_groups_for_workspace,
        list_tags_for_workspace,
    )
    from promptgrimoire.db.workspaces import save_workspace_crdt_state

    doc = AnnotationDocument(str(ws_id))
    if workspace.crdt_state:
        doc.apply_update(workspace.crdt_state)

    crdt_tags = doc.list_tags()
    crdt_groups = doc.list_tag_groups()

    db_tags = await list_tags_for_workspace(ws_id)
    db_groups = await list_tag_groups_for_workspace(ws_id)
    tag_dicts, group_dicts = _tags_to_dicts(db_tags, db_groups)

    # Case 1: CRDT is empty but DB has data -- needs hydration.
    if not crdt_tags and not crdt_groups and (db_tags or db_groups):
        console.print(
            f"  [yellow]HYDRATE[/] {ws_id}: "
            f"{len(db_tags)} tags, {len(db_groups)} groups"
        )
        if fix:
            doc.hydrate_tags_from_db(tag_dicts, group_dicts)
            await save_workspace_crdt_state(ws_id, doc.get_full_state())
            console.print("    [green]Fixed[/]")
        return "hydrated"

    # Case 2: CRDT has data -- check for drift against DB.
    if (crdt_tags or crdt_groups) and _detect_drift(crdt_tags, db_tags, ws_id):
        if fix:
            doc.hydrate_tags_from_db(tag_dicts, group_dicts)
            await save_workspace_crdt_state(ws_id, doc.get_full_state())
            console.print("    [green]Fixed[/]")
        return "drift"

    return "ok"


async def _backfill_tags(
    fix: bool,
    single_workspace_id: str | None = None,
) -> None:
    """Scan workspaces with tags and backfill CRDT state from DB."""
    from uuid import UUID

    from sqlmodel import select

    from promptgrimoire.db.engine import get_session, init_db
    from promptgrimoire.db.models import Tag, Workspace

    await init_db()

    async with get_session() as session:
        query = select(Workspace.id).where(
            Workspace.id.in_(select(Tag.workspace_id).distinct())  # type: ignore[union-attr]  -- Column has .in_()
        )
        if single_workspace_id:
            query = query.where(Workspace.id == UUID(single_workspace_id))
        result = await session.exec(query)
        workspace_ids = list(result.all())

    if not workspace_ids:
        console.print("[yellow]No workspaces with tags found.[/]")
        return

    mode = "[green]FIX" if fix else "[yellow]VERIFY-ONLY"
    console.print(f"Mode: {mode}[/] — {len(workspace_ids)} workspace(s) to process\n")

    counts: dict[str, int] = {"ok": 0, "hydrated": 0, "drift": 0}

    for ws_id in workspace_ids:
        async with get_session() as session:
            workspace = await session.get(Workspace, ws_id)
            if not workspace:
                continue

        result_status = await _check_and_fix_workspace(ws_id, workspace, fix)
        counts[result_status] += 1

    console.print("\n[bold]Summary:[/]")
    console.print(f"  OK: {counts['ok']}")
    console.print(f"  Needs hydration: {counts['hydrated']}")
    console.print(f"  Has drift: {counts['drift']}")
    if not fix and (counts["hydrated"] or counts["drift"]):
        console.print("\n[yellow]Run with --fix to apply changes.[/]")
