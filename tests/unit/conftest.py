"""Shared fixtures for unit tests."""

from __future__ import annotations

from uuid import UUID

import pytest

from promptgrimoire.db.models import User

# Standard UUIDs for test references
SAMPLE_USER_ID = UUID("12345678-1234-5678-1234-567812345678")
SAMPLE_OWNER_ID = UUID("87654321-4321-8765-4321-876543218765")


@pytest.fixture
def make_user():
    """Factory for User instances."""

    def _make(
        email: str = "test@example.com", display_name: str = "Test User", **kwargs
    ):
        return User(email=email, display_name=display_name, **kwargs)

    return _make


@pytest.fixture
def make_workspace():
    """Factory for Workspace instances (not persisted)."""
    from uuid import uuid4

    from promptgrimoire.db.models import Workspace

    def _make(created_by: UUID | None = None, **kwargs):
        return Workspace(
            created_by=created_by or uuid4(),
            **kwargs,
        )

    return _make


@pytest.fixture
def make_workspace_document():
    """Factory for WorkspaceDocument instances (not persisted)."""
    from uuid import uuid4

    from promptgrimoire.db.models import WorkspaceDocument

    def _make(
        workspace_id: UUID | None = None,
        type: str = "source",
        content: str = "",
        raw_content: str = "",
        order_index: int = 0,
        title: str | None = None,
        **kwargs,
    ):
        return WorkspaceDocument(
            workspace_id=workspace_id or uuid4(),
            type=type,
            content=content,
            raw_content=raw_content,
            order_index=order_index,
            title=title,
            **kwargs,
        )

    return _make
