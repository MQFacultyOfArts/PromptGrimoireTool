"""Integration tests for the snapshot bundle builder.

build_snapshot_bundle reads the DB and the persisted CRDT state in a
standalone process context (no NiceGUI, no page registry).  These tests
seed a workspace the same way the app does and assert the bundle carries
exactly what the annotation page currently delivers through the NiceGUI
outbox: document HTML, by-tag highlights, sidebar items, tag options,
permissions.

Design: docs/design-notes/2026-08-16-initial-snapshot-delivery.md
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from promptgrimoire.config import get_settings
from promptgrimoire.snapshot import SnapshotClaims

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)

_DOC_HTML = "<p>The quick brown fox jumps over the lazy dog.</p>"


async def _seed_snapshot_workspace() -> tuple[UUID, UUID, UUID, str, str]:
    """Seed workspace + document + tags + persisted CRDT highlights.

    Returns (workspace_id, document_id, other_document_id,
    tag_a_key, tag_b_key).
    """
    from promptgrimoire.crdt.annotation_doc import AnnotationDocument
    from promptgrimoire.db.tags import create_tag
    from promptgrimoire.db.workspace_documents import add_document
    from promptgrimoire.db.workspaces import (
        create_workspace,
        save_workspace_crdt_state,
    )

    ws = await create_workspace()
    doc = await add_document(
        workspace_id=ws.id,
        type="source",
        content=_DOC_HTML,
        source_type="html",
    )
    other_doc = await add_document(
        workspace_id=ws.id,
        type="source",
        content="<p>Another document entirely.</p>",
        source_type="html",
    )
    tag_a = await create_tag(workspace_id=ws.id, name="Issue", color="#1f77b4")
    tag_b = await create_tag(workspace_id=ws.id, name="Ratio", color="#ff7f0e")

    crdt = AnnotationDocument(f"seed-{ws.id}")
    hl_id = crdt.add_highlight(
        start_char=4,
        end_char=9,
        tag=str(tag_a.id),
        text="quick",
        author="Alice Author",
        document_id=str(doc.id),
        user_id="u-alice",
    )
    crdt.add_comment(hl_id, "Bob Peer", "Nice highlight", user_id="u-bob")
    crdt.add_highlight(
        start_char=10,
        end_char=15,
        tag=str(tag_b.id),
        text="brown",
        author="Bob Peer",
        document_id=str(doc.id),
        user_id="u-bob",
    )
    # Highlight on the other document: must not leak into this bundle.
    crdt.add_highlight(
        start_char=0,
        end_char=7,
        tag=str(tag_a.id),
        text="Another",
        author="Alice Author",
        document_id=str(other_doc.id),
        user_id="u-alice",
    )
    assert await save_workspace_crdt_state(ws.id, crdt.get_full_state())
    return ws.id, doc.id, other_doc.id, str(tag_a.id), str(tag_b.id)


def _claims(
    workspace_id: UUID,
    document_id: UUID,
    *,
    can_annotate: bool = True,
) -> SnapshotClaims:
    return SnapshotClaims(
        workspace_id=str(workspace_id),
        document_id=str(document_id),
        user_id="u-alice",
        viewer_is_privileged=False,
        can_annotate=can_annotate,
        anonymous_sharing=False,
    )


class TestBuildSnapshotBundle:
    @pytest.mark.asyncio
    async def test_bundle_carries_document_highlights_items_tags(self) -> None:
        from promptgrimoire.snapshot import build_snapshot_bundle

        ws_id, doc_id, _other, tag_a, tag_b = await _seed_snapshot_workspace()
        bundle = await build_snapshot_bundle(_claims(ws_id, doc_id))
        assert bundle is not None

        # Document HTML: empty paragraph map is a no-op injection.
        assert "quick brown fox" in bundle["document_html"]

        # Highlights: grouped by tag, current document only.
        assert set(bundle["highlights"]) == {tag_a, tag_b}
        assert [h["start_char"] for h in bundle["highlights"][tag_a]] == [4]
        assert [h["start_char"] for h in bundle["highlights"][tag_b]] == [10]

        # Sidebar items: same serialise_items shape the Vue sidebar consumes.
        items = bundle["items"]
        assert len(items) == 2
        by_tag = {i["tag_key"]: i for i in items}
        assert by_tag[tag_a]["tag_display"] == "Issue"
        assert by_tag[tag_a]["color"] == "#1f77b4"
        assert by_tag[tag_a]["text"] == "quick"
        assert by_tag[tag_a]["can_delete"] is True  # own highlight
        assert by_tag[tag_b]["can_delete"] is False  # Bob's highlight
        comments = by_tag[tag_a]["comments"]
        assert [c["text"] for c in comments] == ["Nice highlight"]

        assert bundle["tag_options"] == {tag_a: "Issue", tag_b: "Ratio"}
        assert bundle["permissions"] == {"can_annotate": True}

    @pytest.mark.asyncio
    async def test_viewer_permission_bits_flow_from_claims(self) -> None:
        from promptgrimoire.snapshot import build_snapshot_bundle

        ws_id, doc_id, _other, _a, _b = await _seed_snapshot_workspace()
        bundle = await build_snapshot_bundle(_claims(ws_id, doc_id, can_annotate=False))
        assert bundle is not None
        assert bundle["permissions"] == {"can_annotate": False}
        assert all(i["can_annotate"] is False for i in bundle["items"])

    @pytest.mark.asyncio
    async def test_document_from_other_workspace_rejected(self) -> None:
        from promptgrimoire.db.workspaces import create_workspace
        from promptgrimoire.snapshot import build_snapshot_bundle

        _ws_id, doc_id, _other, _a, _b = await _seed_snapshot_workspace()
        stranger = await create_workspace()
        assert await build_snapshot_bundle(_claims(stranger.id, doc_id)) is None

    @pytest.mark.asyncio
    async def test_missing_workspace_returns_none(self) -> None:
        from promptgrimoire.snapshot import build_snapshot_bundle

        assert await build_snapshot_bundle(_claims(uuid4(), uuid4())) is None
