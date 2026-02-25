"""Integration tests for FTS search infrastructure.

These tests require a running PostgreSQL instance with FTS indexes
applied. Set DEV__TEST_DATABASE_URL.
"""

from __future__ import annotations

import pytest

from promptgrimoire.config import get_settings

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


class TestSearchDirtyOnCRDTSave:
    """Verify save_workspace_crdt_state sets search_dirty."""

    @pytest.mark.asyncio
    async def test_search_dirty_set_on_crdt_save(self) -> None:
        """Saving CRDT state marks workspace as search_dirty.

        After save_workspace_crdt_state(), the workspace's
        search_dirty flag must be True so the extraction worker
        picks it up.
        """
        from promptgrimoire.crdt.annotation_doc import (
            AnnotationDocument,
        )
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_workspace,
            save_workspace_crdt_state,
        )

        # Create workspace and manually clear dirty flag
        workspace = await create_workspace()

        # Build some CRDT bytes
        doc = AnnotationDocument("dirty-test")
        doc.add_highlight(
            start_char=0,
            end_char=5,
            tag="test",
            text="hello",
            author="tester",
        )
        crdt_bytes = doc.get_full_state()

        # Save CRDT state
        result = await save_workspace_crdt_state(workspace.id, crdt_bytes)
        assert result is True

        # Reload and verify search_dirty is True
        reloaded = await get_workspace(workspace.id)
        assert reloaded is not None
        assert reloaded.search_dirty is True
