"""Unit tests for tag-management callbacks around group creation."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from promptgrimoire.pages.annotation.tags import TagInfo


def _make_state(*, tag_info_list: list[TagInfo]) -> Any:
    """Build the minimal PageState shape needed by group callbacks."""
    from types import SimpleNamespace

    return SimpleNamespace(
        workspace_id=uuid4(),
        crdt_doc=None,
        tag_info_list=tag_info_list,
    )


class TestBuildGroupCallbacks:
    """Group-add callback should avoid duplicate-name regressions."""

    @pytest.mark.asyncio
    async def test_add_group_uses_next_available_default_name(self) -> None:
        """Existing default names should push the next group name forward."""
        from promptgrimoire.pages.annotation.tag_management import (
            _build_group_callbacks,
        )

        state = _make_state(
            tag_info_list=[
                TagInfo(
                    name="Issue",
                    colour="#1f77b4",
                    raw_key="tag-1",
                    group_name="New group",
                ),
                TagInfo(
                    name="Holding",
                    colour="#ff7f0e",
                    raw_key="tag-2",
                    group_name="New group 2",
                ),
            ]
        )
        render_tag_list = AsyncMock()
        create_tag_group = AsyncMock()
        reorder_tag_groups = AsyncMock()

        callbacks = _build_group_callbacks(
            state=state,  # SimpleNamespace stub for PageState
            render_tag_list=render_tag_list,
            create_tag_group=create_tag_group,
            reorder_tag_groups=reorder_tag_groups,
            group_id_list=[],
        )

        await callbacks["add_group"]()

        create_tag_group.assert_awaited_once()
        assert create_tag_group.call_args.kwargs["name"] == "New group 3"

    @pytest.mark.asyncio
    async def test_add_group_duplicate_name_shows_warning(self) -> None:
        """DuplicateNameError should become warning UI, not escape the callback."""
        from promptgrimoire.db.tags import DuplicateNameError
        from promptgrimoire.pages.annotation.tag_management import (
            _build_group_callbacks,
        )

        state = _make_state(tag_info_list=[])
        render_tag_list = AsyncMock()
        create_tag_group = AsyncMock(
            side_effect=DuplicateNameError(
                "A tag group named 'New group' already exists in this workspace"
            )
        )
        reorder_tag_groups = AsyncMock()

        callbacks = _build_group_callbacks(
            state=state,  # SimpleNamespace stub for PageState
            render_tag_list=render_tag_list,
            create_tag_group=create_tag_group,
            reorder_tag_groups=reorder_tag_groups,
            group_id_list=[],
        )

        with (
            patch("promptgrimoire.pages.annotation.tag_management.ui") as mock_ui,
            patch(
                "promptgrimoire.pages.annotation.tag_management.logger"
            ) as mock_logger,
        ):
            await callbacks["add_group"]()

        mock_ui.notify.assert_called_once_with(
            "A tag group named 'New group' already exists",
            type="warning",
        )
        render_tag_list.assert_not_awaited()
        mock_logger.exception.assert_not_called()
