"""E2E memory probe for #434: unbounded RSS growth investigation.

Exercises the FULL NiceGUI client lifecycle — WebSocket connect, annotation
page render with CRDT doc, minimal interaction, disconnect — and measures
RSS + object counts across N cycles.

Discriminates:
- **Leak**: RSS grows linearly per cycle even after gc.collect()
- **Fragmentation**: RSS stabilises after gc.collect()

Uses the nicegui_user fixture for real in-process client simulation.

See: docs/investigations/2026-03-27-memory-leak-434.md
"""

from __future__ import annotations

import ctypes
import gc
import json
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
import structlog

from promptgrimoire.config import get_settings

if TYPE_CHECKING:
    from nicegui.testing.user import User

logger = structlog.get_logger()

pytestmark = [
    pytest.mark.skipif(
        not get_settings().dev.test_database_url,
        reason="DEV__TEST_DATABASE_URL not configured",
    ),
    pytest.mark.nicegui_ui,
]

# ---------------------------------------------------------------------------
# Measurement helpers
# ---------------------------------------------------------------------------

CYCLES = 10  # Number of connect/disconnect cycles


def _get_rss_bytes() -> int | None:
    """Read current RSS from /proc/self/status (Linux only)."""
    try:
        for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    except OSError:
        pass
    return None


def _malloc_trim() -> bool:
    """Call glibc malloc_trim(0) to release free pages back to OS.

    Returns True if memory was actually released.
    """
    try:
        libc = ctypes.CDLL("libc.so.6")
        return libc.malloc_trim(0) != 0
    except OSError:
        return False


@dataclass
class Snapshot:
    """Memory and object count snapshot at a point in time."""

    cycle: int
    phase: str  # "before_gc", "after_gc", "after_trim"
    rss_bytes: int | None
    client_instances: int
    ws_registry_docs: int
    ws_presence_workspaces: int
    ws_presence_clients: int
    asyncio_tasks: int
    gc_objects: int
    gc_collected: int = 0  # objects collected by gc.collect()


@dataclass
class ProbeResults:
    """Accumulated results from all cycles."""

    snapshots: list[Snapshot] = field(default_factory=list)

    def summary(self) -> str:
        """Format results as a readable table."""
        hdr = (
            "cycle | phase      | rss_MB | clients"
            " | ws_reg | ws_pres | tasks | gc_objs"
            " | gc_collected"
        )
        sep = (
            "------|------------|--------|--------"
            "-|--------|---------|-------|--------"
            "-|-------------"
        )
        lines = [hdr, sep]
        for s in self.snapshots:
            rss_mb = f"{s.rss_bytes / 1048576:.0f}" if s.rss_bytes else "?"
            lines.append(
                f"{s.cycle:>5} | {s.phase:<10}"
                f" | {rss_mb:>6}"
                f" | {s.client_instances:>7}"
                f" | {s.ws_registry_docs:>6}"
                f" | {s.ws_presence_clients:>7}"
                f" | {s.asyncio_tasks:>5}"
                f" | {s.gc_objects:>7}"
                f" | {s.gc_collected:>12}"
            )
        return "\n".join(lines)

    def rss_after_gc(self) -> list[int]:
        """Return RSS values at "after_gc" phase for each cycle."""
        return [
            s.rss_bytes
            for s in self.snapshots
            if s.phase == "after_gc" and s.rss_bytes is not None
        ]

    def rss_after_trim(self) -> list[int]:
        """Return RSS values at "after_trim" phase for each cycle."""
        return [
            s.rss_bytes
            for s in self.snapshots
            if s.phase == "after_trim" and s.rss_bytes is not None
        ]


def _take_snapshot(
    cycle: int,
    phase: str,
    gc_collected: int = 0,
) -> Snapshot:
    """Capture current memory and object state."""
    import asyncio

    from nicegui import Client

    from promptgrimoire.pages.annotation import (
        _workspace_presence,
        _workspace_registry,
    )

    return Snapshot(
        cycle=cycle,
        phase=phase,
        rss_bytes=_get_rss_bytes(),
        client_instances=len(Client.instances),
        ws_registry_docs=len(_workspace_registry._documents),
        ws_presence_workspaces=len(_workspace_presence),
        ws_presence_clients=sum(len(v) for v in _workspace_presence.values()),
        asyncio_tasks=len(asyncio.all_tasks()),
        gc_objects=len(gc.get_objects()),
        gc_collected=gc_collected,
    )


# ---------------------------------------------------------------------------
# DB setup (follows test_page_load_query_count.py pattern)
# ---------------------------------------------------------------------------


HEAVY_FIXTURE = (
    Path(__file__).parent / "fixtures" / "workspace_pabai_190hl_scrubbed.json"
)


async def _rehydrate_heavy_workspace(email: str) -> UUID:
    """Load the heavy production workspace fixture into the test DB.

    The fixture contains a ~426 KB document with 190 highlights, 11 tags,
    and 180 KB CRDT state — representative of a heavily-annotated
    production workspace.

    Inserts the workspace standalone (no course/activity) and grants
    owner ACL to the test user.
    """
    import base64

    from promptgrimoire.db.acl import grant_permission
    from promptgrimoire.db.engine import get_session
    from promptgrimoire.db.models import (
        Tag,
        Workspace,
        WorkspaceDocument,
    )
    from promptgrimoire.db.users import find_or_create_user

    data = json.loads(HEAVY_FIXTURE.read_text(encoding="utf-8"))
    ws_data = data["workspace"]
    docs_data = data.get("documents", [])
    tags_data = data.get("tags", [])

    workspace_id = UUID(ws_data["id"])

    # Decode CRDT binary
    crdt_state = None
    if ws_data.get("crdt_state") and ws_data["crdt_state"].get("base64"):
        crdt_state = base64.b64decode(ws_data["crdt_state"]["base64"])

    async with get_session() as session:
        # Clean any prior run
        from sqlmodel import select

        # Delete existing tags and docs for this workspace
        old_tags = (
            await session.exec(select(Tag).where(Tag.workspace_id == workspace_id))
        ).all()
        for t in old_tags:
            await session.delete(t)

        old_docs = (
            await session.exec(
                select(WorkspaceDocument).where(
                    WorkspaceDocument.workspace_id == workspace_id
                )
            )
        ).all()
        for d in old_docs:
            await session.delete(d)

        existing = (
            await session.exec(select(Workspace).where(Workspace.id == workspace_id))
        ).one_or_none()
        if existing:
            await session.delete(existing)
        await session.flush()

        # Insert workspace
        ws = Workspace(
            id=workspace_id,
            crdt_state=crdt_state,
            title=ws_data.get("title", "Heavy Probe Workspace"),
            activity_id=None,
            course_id=None,
            next_tag_order=ws_data.get("next_tag_order", 0),
            next_group_order=ws_data.get("next_group_order", 0),
        )
        session.add(ws)
        await session.flush()

        # Insert documents
        for doc_data in docs_data:
            doc = WorkspaceDocument(
                id=UUID(doc_data["id"]),
                workspace_id=workspace_id,
                type=doc_data.get("type", "source"),
                content=doc_data.get("content", ""),
                order_index=doc_data.get("order_index", 0),
                title=doc_data.get("title", "Document"),
                source_type=doc_data.get("source_type", "paste"),
            )
            session.add(doc)

        # Insert tags (needed for highlight rendering)
        for tag_data in tags_data:
            tag = Tag(
                id=UUID(tag_data["id"]),
                workspace_id=workspace_id,
                group_id=UUID(tag_data["group_id"])
                if tag_data.get("group_id")
                else None,
                name=tag_data.get("name", "Tag"),
                description=tag_data.get("description", ""),
                color=tag_data.get("color", "#1f77b4"),
                locked=tag_data.get("locked", False),
                order_index=tag_data.get("order_index", 0),
            )
            session.add(tag)

        await session.commit()

    # Grant owner ACL to test user
    user, _ = await find_or_create_user(
        email=email,
        display_name=email.split("@", maxsplit=1)[0],
    )
    await grant_permission(
        workspace_id=workspace_id,
        user_id=user.id,
        permission="owner",
    )

    return workspace_id


# ---------------------------------------------------------------------------
# Probe test
# ---------------------------------------------------------------------------


@contextmanager
def _gc_disabled():
    """Disable automatic GC so we control collection timing."""
    was_enabled = gc.isenabled()
    gc.disable()
    try:
        yield
    finally:
        if was_enabled:
            gc.enable()


class TestMemoryLeakProbe:
    """Connect/disconnect cycle probe measuring RSS and object retention.

    Each cycle:
    1. Open annotation page (full render: CRDT load, element tree, closures)
    2. Navigate away (triggers client disconnect → cleanup chain)
    3. Wait for NiceGUI reconnect_timeout (3s) + deletion
    4. Measure RSS and object counts before/after gc.collect()
    """

    @pytest.mark.asyncio
    async def test_memory_growth_across_cycles(self, nicegui_user: User) -> None:
        """RSS after gc.collect() should stabilise, not grow linearly."""
        import asyncio

        from tests.integration.conftest import _authenticate
        from tests.integration.nicegui_helpers import _should_see_testid

        results = ProbeResults()

        # Unique email per test run to avoid collisions
        run_id = uuid4().hex[:6]
        email = f"mem-probe-{run_id}@test.example.edu.au"

        # Create the workspace once — reuse across cycles
        ws_id = await _rehydrate_heavy_workspace(email)
        await _authenticate(nicegui_user, email=email)

        # Baseline snapshot before any annotation page load
        gc.collect()
        gc.collect()  # Second pass for weak ref callbacks
        _malloc_trim()
        results.snapshots.append(_take_snapshot(0, "baseline"))

        for cycle in range(1, CYCLES + 1):
            # --- CONNECT: Open annotation page (full lifecycle) ---
            await nicegui_user.open(f"/annotation?workspace_id={ws_id}")
            # Wait for the page to fully render (doc-container is the signal)
            await _should_see_testid(nicegui_user, "doc-container")

            # Small pause to let async setup tasks complete
            await asyncio.sleep(0.5)  # noqa: PG001 — no observable condition to wait for

            # --- DISCONNECT: Explicitly delete old clients ---
            # nicegui_user.open() does NOT trigger the real
            # WebSocket disconnect → Client.delete() path.
            # We must call Client.delete() manually to exercise
            # the cleanup chain (_handle_client_delete).
            from nicegui import Client

            current = nicegui_user.client
            current_id = current.id if current else None
            old_clients = [
                c for c in list(Client.instances.values()) if c.id != current_id
            ]
            for c in old_clients:
                c.delete()
            # Let delete handlers (our on_client_delete) run
            await asyncio.sleep(0.5)  # noqa: PG001 — waiting for on_client_delete async chain

            # Navigate away so we start fresh next cycle
            await nicegui_user.open("/login")
            await asyncio.sleep(0.5)  # noqa: PG001 — let page transition settle before measuring

            # --- MEASURE: Before GC ---
            results.snapshots.append(_take_snapshot(cycle, "before_gc"))

            # --- MEASURE: After GC ---
            collected = gc.collect()
            collected += gc.collect()  # Second pass
            results.snapshots.append(
                _take_snapshot(cycle, "after_gc", gc_collected=collected)
            )

            # --- MEASURE: After malloc_trim ---
            _malloc_trim()
            results.snapshots.append(_take_snapshot(cycle, "after_trim"))

        # --- OUTPUT: Log full results ---
        summary = results.summary()
        logger.info("memory_probe_results", summary="\n" + summary)
        print("\n" + summary)

        # Write to file for post-analysis
        out = Path("output/incident/probe_results.txt")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(summary, encoding="utf-8")

        # --- ANALYSIS: Check for linear growth ---
        rss_post_gc = results.rss_after_gc()

        if len(rss_post_gc) >= 4:
            # Compare first quarter average to last quarter average
            quarter = len(rss_post_gc) // 4
            early_avg = sum(rss_post_gc[:quarter]) / quarter
            late_avg = sum(rss_post_gc[-quarter:]) / quarter
            growth_ratio = late_avg / early_avg if early_avg > 0 else 0

            logger.info(
                "memory_probe_analysis",
                early_avg_mb=early_avg / 1048576,
                late_avg_mb=late_avg / 1048576,
                growth_ratio=growth_ratio,
                cycles=CYCLES,
            )

            # Assert: late cycles should not be >20% larger than early cycles
            # after GC. If they are, there's a genuine leak.
            # NOTE: This threshold is deliberately generous for the first probe
            # run. Tighten once we have baseline data.
            early_mb = early_avg / 1048576
            late_mb = late_avg / 1048576
            assert growth_ratio < 1.5, (
                f"RSS after gc.collect() grew "
                f"{growth_ratio:.2f}x between early "
                f"and late cycles "
                f"({early_mb:.0f} MB -> "
                f"{late_mb:.0f} MB). "
                f"Suggests a genuine memory leak.\n"
                f"Full results:\n{summary}"
            )

        # --- ANALYSIS: Check cleanup completeness ---
        final = results.snapshots[-1]
        logger.info(
            "memory_probe_final_state",
            client_instances=final.client_instances,
            ws_registry_docs=final.ws_registry_docs,
            ws_presence_workspaces=final.ws_presence_workspaces,
            ws_presence_clients=final.ws_presence_clients,
        )

        # After all cycles complete and clients disconnect, our tracked
        # objects should be clean. The workspace may remain in registry
        # because we reuse the same workspace (last client hasn't disconnected
        # from the fixture's perspective), so we check presence only.
        # A high ws_presence_clients count would indicate cleanup failure.
        assert final.ws_presence_clients <= 1, (
            f"Expected ≤1 presence client after probe (fixture's own connection), "
            f"got {final.ws_presence_clients}. Cleanup chain may be broken."
        )
