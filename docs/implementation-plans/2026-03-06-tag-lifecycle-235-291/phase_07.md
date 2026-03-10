# Tag Lifecycle Refactor — Phase 7: Migration/Verification Script

**Goal:** Backfill CRDT `tags`/`tag_groups` Maps for all existing workspaces and verify DB–CRDT consistency.

**Architecture:** CLI sub-command `grimoire migrate backfill-tags` iterates all workspaces with tags, loads each workspace's CRDT state, populates Maps from DB tag/group rows using Phase 1's `hydrate_tags_from_db()`, and saves back. Defaults to verify-only mode (report discrepancies); `--fix` flag performs actual writes. Idempotent — safe to re-run after any phase.

**Tech Stack:** Typer (existing CLI framework), SQLModel (existing queries), pycrdt via AnnotationDocument methods from Phase 1

**Scope:** 8 phases from original design (phase 7 of 8)

**Codebase verified:** 2026-03-06

---

## Acceptance Criteria Coverage

This phase is **infrastructure** — it does not directly test acceptance criteria. The migration enables AC1.5 (hydration on workspace load) by pre-populating CRDT state for existing workspaces, ensuring the consistency check in Phase 3 starts from a clean baseline.

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Create `cli/migrate.py` scaffolding and register sub-app

**Verifies:** None (infrastructure)

**Files:**
- Create: `src/promptgrimoire/cli/migrate.py`
- Modify: `src/promptgrimoire/cli/__init__.py:1-18` (register migrate_app)

**Implementation:**

Create `cli/migrate.py` following the pattern in `cli/seed.py`:

```python
"""Tag migration and CRDT backfill commands."""

from __future__ import annotations

import asyncio
import sys

import typer
from rich.console import Console

console = Console()

migrate_app = typer.Typer(help="Migration and CRDT backfill tools.")


@migrate_app.command("backfill-tags")
def backfill_tags(
    fix: bool = typer.Option(False, help="Apply changes. Without this flag, only reports."),
    workspace_id: str | None = typer.Option(None, help="Process a single workspace by UUID."),
) -> None:
    """Backfill CRDT tags/tag_groups Maps from DB for all workspaces.

    By default runs in verify-only mode — reports which workspaces need
    hydration without modifying data. Use --fix to apply changes.
    """
    from promptgrimoire.config import get_settings

    if not get_settings().database.url:
        console.print("[red]Error:[/] DATABASE__URL not set")
        sys.exit(1)

    asyncio.run(_backfill_tags(fix=fix, single_workspace_id=workspace_id))
```

Register in `cli/__init__.py` — add import and `app.add_typer(migrate_app, name="migrate")`.

**Verification:**
Run: `uv run grimoire migrate backfill-tags --help`
Expected: Help text with `--fix` and `--workspace-id` options

**Commit:** `feat: add grimoire migrate CLI sub-app with backfill-tags command`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Implement `_backfill_tags()` async function

**Verifies:** None (infrastructure — verified operationally)

**Files:**
- Modify: `src/promptgrimoire/cli/migrate.py` (add `_backfill_tags` function)

**Implementation:**

Add the core async function that iterates workspaces and backfills CRDT state:

```python
async def _backfill_tags(
    fix: bool,
    single_workspace_id: str | None = None,
) -> None:
    from uuid import UUID

    from sqlmodel import select

    from promptgrimoire.crdt.annotation_doc import AnnotationDocument
    from promptgrimoire.db.engine import get_session, init_db
    from promptgrimoire.db.models import Tag, TagGroup, Workspace
    from promptgrimoire.db.tags import (
        list_tag_groups_for_workspace,
        list_tags_for_workspace,
    )
    from promptgrimoire.db.workspaces import save_workspace_crdt_state

    await init_db()

    # Find workspaces with tags
    async with get_session() as session:
        query = select(Workspace.id).where(
            Workspace.id.in_(select(Tag.workspace_id).distinct())
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

    needs_hydration = 0
    has_drift = 0
    already_ok = 0

    for ws_id in workspace_ids:
        # Load existing CRDT state
        async with get_session() as session:
            workspace = await session.get(Workspace, ws_id)
            if not workspace:
                continue

        doc = AnnotationDocument(str(ws_id))
        if workspace.crdt_state:
            doc.apply_update(workspace.crdt_state)

        # Check current CRDT tag state
        crdt_tags = doc.list_tags()
        crdt_groups = doc.list_tag_groups()

        # Load DB state
        db_tags = await list_tags_for_workspace(ws_id)
        db_groups = await list_tag_groups_for_workspace(ws_id)

        if not crdt_tags and not crdt_groups and (db_tags or db_groups):
            # Empty CRDT, DB has data — needs full hydration
            needs_hydration += 1
            console.print(f"  [yellow]HYDRATE[/] {ws_id}: "
                         f"{len(db_tags)} tags, {len(db_groups)} groups")
            if fix:
                doc.hydrate_tags_from_db(db_tags, db_groups)
                await save_workspace_crdt_state(ws_id, doc.get_full_state())
                console.print(f"    [green]Fixed[/]")
        elif crdt_tags or crdt_groups:
            # Both have data — check for drift
            crdt_tag_ids = {t_id for t_id in crdt_tags}
            db_tag_ids = {str(t.id) for t in db_tags}
            missing_in_crdt = db_tag_ids - crdt_tag_ids
            extra_in_crdt = crdt_tag_ids - db_tag_ids

            if missing_in_crdt or extra_in_crdt:
                has_drift += 1
                if missing_in_crdt:
                    console.print(f"  [yellow]DRIFT[/] {ws_id}: "
                                 f"{len(missing_in_crdt)} tags in DB missing from CRDT")
                if extra_in_crdt:
                    console.print(f"  [yellow]DRIFT[/] {ws_id}: "
                                 f"{len(extra_in_crdt)} tags in CRDT not in DB")
                if fix:
                    # Re-hydrate from DB (full replacement)
                    doc.hydrate_tags_from_db(db_tags, db_groups)
                    await save_workspace_crdt_state(ws_id, doc.get_full_state())
                    console.print(f"    [green]Fixed[/]")
            else:
                already_ok += 1
        else:
            already_ok += 1

    console.print(f"\n[bold]Summary:[/]")
    console.print(f"  OK: {already_ok}")
    console.print(f"  Needs hydration: {needs_hydration}")
    console.print(f"  Has drift: {has_drift}")
    if not fix and (needs_hydration or has_drift):
        console.print(f"\n[yellow]Run with --fix to apply changes.[/]")
```

Note: `doc.list_tags()`, `doc.list_tag_groups()`, `doc.hydrate_tags_from_db()`, `doc.get_full_state()`, and `doc.apply_update()` are from Phase 1. The script depends on Phase 1 being implemented first. `save_workspace_crdt_state()` is confirmed at `db/workspaces.py:389-407`.

**Complexity budget:** The pseudocode above shows the logical flow as a single function. For complexity compliance, split at the `for ws_id in workspace_ids:` boundary: extract the per-workspace logic into `_check_and_fix_workspace(ws_id, fix, doc)` and keep `_backfill_tags()` as the outer loop driver. Both must stay ≤15.

**Verification:**
Run: `uv run grimoire migrate backfill-tags` (against a seeded dev DB)
Expected: Reports workspace status without modifying data

Run: `uv run grimoire migrate backfill-tags --fix`
Expected: Hydrates CRDT maps, reports changes made

Run: `uv run grimoire migrate backfill-tags --fix` (second time)
Expected: Reports all workspaces as OK (idempotent)

Run: `uv run complexipy src/promptgrimoire/cli/migrate.py --max-complexity-allowed 15`
Expected: No violations

**Commit:** `feat: implement backfill-tags migration with verify/fix modes`

<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_3 -->
### Task 3: Integration test for backfill idempotency

**Verifies:** None (infrastructure verification)

**Files:**
- Test: `tests/integration/test_migrate_backfill.py`

**Implementation:**

Integration tests that verify the backfill logic:

1. **Empty CRDT hydration:** Create a workspace with tags in DB but no `crdt_state`. Run `_backfill_tags(fix=True)`. Verify CRDT maps are populated with correct tag/group data.

2. **Idempotency:** Run `_backfill_tags(fix=True)` twice on the same workspace. Verify second run reports no changes needed. Compare logical equality (same tags/groups with same values via `list_tags()` / `list_tag_groups()`) rather than byte-identical CRDT state — pycrdt serialisation is not guaranteed deterministic.

3. **Drift detection:** Create a workspace, backfill once, then add a tag to DB without updating CRDT. Run `_backfill_tags(fix=False)` — verify drift is reported. Run with `fix=True` — verify CRDT is updated.

4. **Single workspace filter:** Create two workspaces with tags. Run `_backfill_tags(fix=True, single_workspace_id=str(ws1.id))`. Verify only ws1 is processed.

5. **No tags:** Create workspace with no tags. Run `_backfill_tags(fix=True)`. Verify it's skipped (not in the workspace list).

**Verification:**
Run: `uv run pytest tests/integration/test_migrate_backfill.py -v`
Expected: All tests pass

**Commit:** `test: add integration tests for backfill-tags migration`

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Full regression verification

**Verifies:** None (regression verification)

**Files:**
- No modifications — verification only

**Verification:**
Run: `uv run grimoire test all`
Expected: All tests pass

Run: `uv run grimoire migrate backfill-tags --help`
Expected: Help text displays correctly

**Commit:** No commit needed — verification only

<!-- END_TASK_4 -->
