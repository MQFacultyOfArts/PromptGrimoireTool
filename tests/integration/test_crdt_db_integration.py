"""Integration tests for CRDT <-> Database persistence.

These tests require a running PostgreSQL instance. Set TEST_DATABASE_URL
environment variable to point to a test database.

Example:
    TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/promptgrimoire_test
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

from promptgrimoire.crdt.annotation_doc import (
    AnnotationDocument,
    AnnotationDocumentRegistry,
)
from promptgrimoire.db.annotation_state import get_state_by_case_id, save_state
from promptgrimoire.db.engine import close_db, get_engine, init_db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

# Skip all tests if no test database URL is configured
pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set - skipping database integration tests",
)


@pytest.fixture(scope="function")
async def setup_db() -> AsyncIterator[None]:
    """Initialize test database connection and create tables."""
    from sqlmodel import SQLModel

    test_url = os.environ.get("TEST_DATABASE_URL")
    if not test_url:
        pytest.skip("TEST_DATABASE_URL not set")
        return

    os.environ["DATABASE_URL"] = test_url
    await init_db()

    engine = get_engine()
    assert engine is not None

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    yield

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)

    await close_db()


@pytest.mark.asyncio
@pytest.mark.usefixtures("setup_db")
class TestCRDTDatabaseIntegration:
    """Test CRDT state round-trips through database."""

    async def test_save_empty_document(self) -> None:
        """Empty document state can be saved."""
        doc = AnnotationDocument("test-case-empty")
        state_bytes = doc.get_full_state()

        result = await save_state("test-case-empty", state_bytes, 0)

        assert result is not None
        assert result.case_id == "test-case-empty"
        assert result.crdt_state == state_bytes
        assert result.highlight_count == 0

    async def test_save_and_load_document(self) -> None:
        """Document state can be saved and loaded."""
        doc = AnnotationDocument("test-case-roundtrip")
        state_bytes = doc.get_full_state()

        await save_state("test-case-roundtrip", state_bytes, 0)
        loaded = await get_state_by_case_id("test-case-roundtrip")

        assert loaded is not None
        assert loaded.crdt_state == state_bytes

    async def test_save_document_with_highlights(self) -> None:
        """Document with highlights preserves state through save/load."""
        doc = AnnotationDocument("test-case-highlights")
        doc.add_highlight(0, 10, "jurisdiction", "test text", "TestAuthor")
        doc.add_highlight(15, 25, "legal_issues", "more text", "TestAuthor")
        state_bytes = doc.get_full_state()

        await save_state(
            "test-case-highlights", state_bytes, 2, last_editor="TestAuthor"
        )

        # Create new doc and restore
        doc2 = AnnotationDocument("test-case-highlights")
        loaded = await get_state_by_case_id("test-case-highlights")
        assert loaded is not None
        doc2.apply_update(loaded.crdt_state)

        highlights = doc2.get_all_highlights()
        assert len(highlights) == 2
        assert highlights[0]["tag"] == "jurisdiction"
        assert highlights[1]["tag"] == "legal_issues"

    async def test_save_document_with_comments(self) -> None:
        """Document with comments preserves state through save/load."""
        doc = AnnotationDocument("test-case-comments")
        highlight_id = doc.add_highlight(0, 10, "reasons", "some text", "Author1")
        doc.add_comment(highlight_id, "Author2", "Great point!")
        doc.add_comment(highlight_id, "Author1", "Thanks!")
        state_bytes = doc.get_full_state()

        await save_state("test-case-comments", state_bytes, 1)

        # Create new doc and restore
        doc2 = AnnotationDocument("test-case-comments")
        loaded = await get_state_by_case_id("test-case-comments")
        assert loaded is not None
        doc2.apply_update(loaded.crdt_state)

        highlights = doc2.get_all_highlights()
        assert len(highlights) == 1
        comments = highlights[0].get("comments", [])
        assert len(comments) == 2
        assert comments[0]["text"] == "Great point!"
        assert comments[1]["text"] == "Thanks!"

    async def test_upsert_updates_existing(self) -> None:
        """save_state should update existing record."""
        doc = AnnotationDocument("test-case-upsert")

        # Initial save
        await save_state("test-case-upsert", doc.get_full_state(), 0)

        # Add highlight and save again
        doc.add_highlight(0, 5, "decision", "ruling", "Judge")
        await save_state(
            "test-case-upsert", doc.get_full_state(), 1, last_editor="Judge"
        )

        # Load and verify
        loaded = await get_state_by_case_id("test-case-upsert")
        assert loaded is not None
        assert loaded.highlight_count == 1
        assert loaded.last_editor == "Judge"

    async def test_load_nonexistent_returns_none(self) -> None:
        """Loading nonexistent document returns None."""
        loaded = await get_state_by_case_id("nonexistent-case-xyz")
        assert loaded is None

    async def test_registry_loads_from_db(self) -> None:
        """Registry's get_or_create_with_persistence loads from DB."""
        # Pre-populate database
        doc = AnnotationDocument("test-case-registry")
        doc.add_highlight(5, 15, "reasons", "important ruling", "Prof")
        await save_state("test-case-registry", doc.get_full_state(), 1)

        # New registry should load from DB
        registry = AnnotationDocumentRegistry()
        loaded_doc = await registry.get_or_create_with_persistence("test-case-registry")

        highlights = loaded_doc.get_all_highlights()
        assert len(highlights) == 1
        assert highlights[0]["text"] == "important ruling"

    async def test_registry_creates_new_if_not_in_db(self) -> None:
        """Registry creates new document if not in DB."""
        registry = AnnotationDocumentRegistry()
        loaded_doc = await registry.get_or_create_with_persistence("brand-new-case")

        # Should be empty
        assert len(loaded_doc.get_all_highlights()) == 0

    async def test_registry_returns_cached_document(self) -> None:
        """Registry returns cached document on second call."""
        registry = AnnotationDocumentRegistry()

        doc1 = await registry.get_or_create_with_persistence("cached-test")
        doc1.add_highlight(0, 5, "order", "costs awarded", "Clerk")

        doc2 = await registry.get_or_create_with_persistence("cached-test")

        # Should be the same instance
        assert doc1 is doc2
        assert len(doc2.get_all_highlights()) == 1
