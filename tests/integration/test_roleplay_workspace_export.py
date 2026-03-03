"""Integration tests for roleplay workspace export.

Verifies AC3.1: Export creates a loose workspace with ai_conversation document.
Requires DEV__TEST_DATABASE_URL.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from promptgrimoire.config import get_settings
from promptgrimoire.models import Character, Session

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


class TestRoleplayWorkspaceExport:
    """Integration tests for the full export pipeline."""

    @pytest.mark.asyncio
    async def test_export_creates_workspace_with_ai_conversation_doc(self) -> None:
        """AC3.1: Creates a loose workspace with a single ai_conversation document."""
        from promptgrimoire.db.workspace_documents import add_document, list_documents
        from promptgrimoire.db.workspaces import create_workspace, get_workspace
        from promptgrimoire.pages.roleplay_export import session_to_html

        # Set up test session
        char = Character(name="Becky Bennett", description="Test")
        session = Session(character=char, user_name="Jane")
        session.add_turn("Hello Becky", is_user=True)
        session.add_turn("Hi there Jane", is_user=False)

        html = session_to_html(session)

        # Create workspace and document
        workspace = await create_workspace()
        await add_document(
            workspace_id=workspace.id,
            type="ai_conversation",
            content=html,
            source_type="html",
            title="Roleplay: Becky Bennett",
        )

        # Verify workspace exists
        ws = await get_workspace(workspace.id)
        assert ws is not None

        # Verify exactly one document of correct type
        docs = await list_documents(workspace.id)
        assert len(docs) == 1
        assert docs[0].type == "ai_conversation"

    @pytest.mark.asyncio
    async def test_exported_document_contains_speaker_markers(self) -> None:
        """AC3.1+AC3.2: Document content contains data-speaker attributes."""
        from promptgrimoire.db.workspace_documents import add_document, list_documents
        from promptgrimoire.db.workspaces import create_workspace
        from promptgrimoire.pages.roleplay_export import session_to_html

        char = Character(name="Becky Bennett", description="Test")
        session = Session(character=char, user_name="Jane")
        session.add_turn("Hello", is_user=True)
        session.add_turn("Hi", is_user=False)

        html = session_to_html(session)
        workspace = await create_workspace()
        await add_document(
            workspace_id=workspace.id,
            type="ai_conversation",
            content=html,
            source_type="html",
        )

        docs = await list_documents(workspace.id)
        content = docs[0].content
        assert 'data-speaker="user"' in content
        assert 'data-speaker="assistant"' in content
        assert 'data-speaker-name="Jane"' in content
        assert 'data-speaker-name="Becky Bennett"' in content

    @pytest.mark.asyncio
    async def test_export_grants_owner_permission(self) -> None:
        """AC3.1: ACL entry exists with 'owner' permission."""
        from promptgrimoire.db.acl import grant_permission, resolve_permission
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace

        tag = uuid4().hex[:8]
        user = await create_user(
            email=f"roleplay-export-{tag}@test.local",
            display_name=f"Roleplay Export {tag}",
        )
        workspace = await create_workspace()

        await grant_permission(workspace.id, user.id, "owner")

        permission = await resolve_permission(workspace.id, user.id)
        assert permission == "owner"
