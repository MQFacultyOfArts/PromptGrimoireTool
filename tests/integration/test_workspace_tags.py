"""Tests for workspace_tags() DB query.

Verifies that workspace_tags() returns correct TagInfo instances from the
database, including proper field mapping and order_index ordering.

These tests require a running PostgreSQL instance. Set DEV__TEST_DATABASE_URL.
"""

from __future__ import annotations

import pytest

from promptgrimoire.config import get_settings

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


class TestWorkspaceTags:
    """Tests for workspace_tags() returning TagInfo instances."""

    @pytest.mark.asyncio
    async def test_workspace_with_three_tags(self) -> None:
        """workspace_tags() returns 3 TagInfo instances with correct fields."""
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Tag, Workspace
        from promptgrimoire.pages.annotation.tags import TagInfo, workspace_tags

        async with get_session() as session:
            ws = Workspace()
            session.add(ws)
            await session.flush()

            tags_data = [
                ("Jurisdiction", "#1f77b4", 0),
                ("Legal Issues", "#d62728", 1),
                ("Reasons", "#9467bd", 2),
            ]
            created_tags: list[Tag] = []
            for name, color, order_index in tags_data:
                tag = Tag(
                    workspace_id=ws.id,
                    name=name,
                    color=color,
                    order_index=order_index,
                )
                session.add(tag)
                created_tags.append(tag)
            await session.flush()
            # Refresh to get DB-assigned IDs
            for tag in created_tags:
                await session.refresh(tag)

        result = await workspace_tags(ws.id)

        assert len(result) == 3
        for i, (name, color, _order) in enumerate(tags_data):
            assert isinstance(result[i], TagInfo)
            assert result[i].name == name
            assert result[i].colour == color
            assert result[i].raw_key == str(created_tags[i].id)

    @pytest.mark.asyncio
    async def test_workspace_with_no_tags(self) -> None:
        """workspace_tags() returns empty list for workspace with no tags."""
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Workspace
        from promptgrimoire.pages.annotation.tags import workspace_tags

        async with get_session() as session:
            ws = Workspace()
            session.add(ws)
            await session.flush()

        result = await workspace_tags(ws.id)

        assert result == []


class TestWorkspaceTagsOrdering:
    """Tests for workspace_tags() order_index sorting."""

    @pytest.mark.asyncio
    async def test_returns_tags_ordered_by_order_index(self) -> None:
        """Tags inserted out of order are returned sorted by order_index."""
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Tag, Workspace
        from promptgrimoire.pages.annotation.tags import workspace_tags

        async with get_session() as session:
            ws = Workspace()
            session.add(ws)
            await session.flush()

            # Insert in order_index 2, 0, 1 (not sequential)
            tag_c = Tag(
                workspace_id=ws.id,
                name="Third",
                color="#2ca02c",
                order_index=2,
            )
            tag_a = Tag(
                workspace_id=ws.id,
                name="First",
                color="#1f77b4",
                order_index=0,
            )
            tag_b = Tag(
                workspace_id=ws.id,
                name="Second",
                color="#d62728",
                order_index=1,
            )
            session.add_all([tag_c, tag_a, tag_b])
            await session.flush()

        result = await workspace_tags(ws.id)

        assert len(result) == 3
        assert result[0].name == "First"
        assert result[1].name == "Second"
        assert result[2].name == "Third"
