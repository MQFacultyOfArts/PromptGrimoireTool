"""Tests that load-test CRDT state stores valid Tag UUIDs, not tag names.

Regression test for a bug where ``build_crdt_state`` stored tag name strings
(e.g. "Jurisdiction") in highlight ``tag`` fields instead of Tag UUID strings.
The annotation UI resolves tag display info via ``tag_options`` which maps
``str(tag.id)`` -> ``tag.name``, so name strings silently fail to resolve.

These tests require a running PostgreSQL instance. Set DEV__TEST_DATABASE_URL.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest
from sqlmodel import select

from promptgrimoire.config import get_settings

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


@dataclass
class CrdtFixture:
    """Shared state produced by _build_crdt_fixture."""

    workspace_id: uuid.UUID
    tag_ids: list[str]
    highlights: list[dict[str, object]]


async def _build_crdt_fixture() -> CrdtFixture:
    """Create a workspace with tags, a document, and CRDT highlights.

    Shared setup for all tests in this module — eliminates the repeated
    workspace-create / seed-tags / add-document / build-CRDT / apply-update
    sequence.
    """
    from promptgrimoire.cli_loadtest import (
        DOCUMENT_PARAGRAPHS,
        _seed_tags_for_template,
        build_crdt_state,
    )
    from promptgrimoire.crdt.annotation_doc import AnnotationDocument
    from promptgrimoire.db.workspace_documents import add_document
    from promptgrimoire.db.workspaces import create_workspace

    workspace = await create_workspace()
    tag_ids = await _seed_tags_for_template(workspace.id)

    content = "".join(DOCUMENT_PARAGRAPHS[:3])
    doc = await add_document(
        workspace_id=workspace.id,
        type="ai_conversation",
        content=content,
        source_type="html",
        title="Test Document",
    )

    crdt_bytes = build_crdt_state(
        document_id=str(doc.id),
        tag_ids=tag_ids,
        student_name="test-student",
        content_length=len(content),
    )

    ann_doc = AnnotationDocument(doc_id=str(doc.id))
    ann_doc.apply_update(crdt_bytes)
    highlights = ann_doc.get_all_highlights()

    assert len(highlights) >= 2, "Expected at least 2 highlights from build_crdt_state"

    return CrdtFixture(
        workspace_id=workspace.id,
        tag_ids=tag_ids,
        highlights=highlights,
    )


class TestLoadtestCrdtTagValidity:
    """Verify that build_crdt_state produces highlights with valid Tag UUIDs."""

    @pytest.mark.asyncio
    async def test_highlight_tags_are_valid_uuids(self) -> None:
        """Every highlight tag value must be a parseable UUID string."""
        fixture = await _build_crdt_fixture()

        for hl in fixture.highlights:
            tag_value = str(hl["tag"])
            # Must parse as a valid UUID — will raise ValueError if not
            parsed = uuid.UUID(tag_value)
            assert str(parsed) == tag_value, (
                f"Tag value round-trip mismatch: {tag_value!r} != {str(parsed)!r}"
            )

    @pytest.mark.asyncio
    async def test_highlight_tag_uuids_are_from_seed(self) -> None:
        """Every highlight tag UUID must be one returned by _seed_tags_for_template."""
        fixture = await _build_crdt_fixture()

        tag_id_set = set(fixture.tag_ids)
        for hl in fixture.highlights:
            tag_value = hl["tag"]
            assert tag_value in tag_id_set, (
                f"Highlight tag {tag_value!r} is not in seeded tag_ids. "
                f"This may indicate tag names are being stored instead of UUIDs."
            )

    @pytest.mark.asyncio
    async def test_highlight_tag_uuids_exist_in_database(self) -> None:
        """Highlight tag UUIDs must correspond to actual Tag rows in the DB."""
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Tag

        fixture = await _build_crdt_fixture()

        async with get_session() as session:
            result = await session.exec(
                select(Tag).where(Tag.workspace_id == fixture.workspace_id)
            )
            db_tag_ids = {str(t.id) for t in result.all()}

        highlight_tag_ids = {hl["tag"] for hl in fixture.highlights}
        assert highlight_tag_ids <= db_tag_ids, (
            f"Highlight tag UUIDs not found in DB: {highlight_tag_ids - db_tag_ids}. "
            f"DB has: {db_tag_ids}"
        )
