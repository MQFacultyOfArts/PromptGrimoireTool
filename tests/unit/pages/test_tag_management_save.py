"""Unit tests for tag_management_save with model-dict based inputs.

Verifies that _save_single_tag and _save_single_group read values from
plain model dicts (bind_value targets) instead of NiceGUI element .value
properties.

Traceability:
- Design: phase_04.md Task 1-2 (tag-lifecycle-235-291)
- AC: tag-lifecycle-235-291.AC4.1 (colour persistence)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest


@pytest.fixture
def tag_model() -> dict:
    """A model dict as produced by bind_value in _render_tag_row."""
    return {
        "name": "Evidence",
        "color": "#1f77b4",
        "description": "Test desc",
        "group_id": str(uuid4()),
        "orig_name": "Evidence",
        "orig_color": "#1f77b4",
        "orig_desc": "Test desc",
        "orig_group": None,
    }


@pytest.fixture
def group_model() -> dict:
    """A model dict as produced by bind_value in _render_group_header."""
    return {
        "name": "Legal",
        "color": "#ff7f0e",
        "orig_name": "Legal",
        "orig_color": "#ff7f0e",
    }


class TestSaveSingleTagModelDict:
    """_save_single_tag reads from model dicts, not element refs."""

    @pytest.mark.asyncio
    async def test_no_changes_skips_save(self, tag_model: dict) -> None:
        """When model matches originals, no DB call is made."""
        from promptgrimoire.pages.annotation.tag_management_save import (
            _save_single_tag,
        )

        tag_id = uuid4()
        # Make orig match current (no changes)
        tag_model["orig_group"] = tag_model["group_id"]
        update_tag = AsyncMock()
        result = await _save_single_tag(tag_id, {tag_id: tag_model}, update_tag)
        assert result is True
        update_tag.assert_not_called()

    @pytest.mark.asyncio
    async def test_changed_name_triggers_save(self, tag_model: dict) -> None:
        """When model name differs from orig, update_tag is called."""
        from promptgrimoire.pages.annotation.tag_management_save import (
            _save_single_tag,
        )

        tag_id = uuid4()
        tag_model["name"] = "New Name"
        update_tag = AsyncMock()
        result = await _save_single_tag(tag_id, {tag_id: tag_model}, update_tag)
        assert result is True
        update_tag.assert_called_once()
        call_kwargs = update_tag.call_args
        assert call_kwargs[1]["name"] == "New Name"

    @pytest.mark.asyncio
    async def test_changed_color_triggers_save(self, tag_model: dict) -> None:
        """When model colour differs from orig, update_tag is called."""
        from promptgrimoire.pages.annotation.tag_management_save import (
            _save_single_tag,
        )

        tag_id = uuid4()
        tag_model["color"] = "#ff0000"
        update_tag = AsyncMock()
        result = await _save_single_tag(tag_id, {tag_id: tag_model}, update_tag)
        assert result is True
        update_tag.assert_called_once()
        assert update_tag.call_args[1]["color"] == "#ff0000"

    @pytest.mark.asyncio
    async def test_originals_updated_after_save(self, tag_model: dict) -> None:
        """After successful save, orig values are updated to match current."""
        from promptgrimoire.pages.annotation.tag_management_save import (
            _save_single_tag,
        )

        tag_id = uuid4()
        tag_model["name"] = "Updated"
        tag_model["color"] = "#00ff00"
        update_tag = AsyncMock()
        await _save_single_tag(tag_id, {tag_id: tag_model}, update_tag)
        assert tag_model["orig_name"] == "Updated"
        assert tag_model["orig_color"] == "#00ff00"


class TestSaveSingleGroupModelDict:
    """_save_single_group reads from model dicts, not element refs."""

    @pytest.mark.asyncio
    async def test_no_changes_skips_save(self, group_model: dict) -> None:
        """When model matches originals, no DB call is made."""
        from promptgrimoire.pages.annotation.tag_management_save import (
            _save_single_group,
        )

        gid = uuid4()
        update_group = AsyncMock()
        result = await _save_single_group(gid, {gid: group_model}, update_group)
        assert result is True
        update_group.assert_not_called()

    @pytest.mark.asyncio
    async def test_changed_name_triggers_save(self, group_model: dict) -> None:
        """When model name differs from orig, update is called."""
        from promptgrimoire.pages.annotation.tag_management_save import (
            _save_single_group,
        )

        gid = uuid4()
        group_model["name"] = "New Group"
        update_group = AsyncMock()
        result = await _save_single_group(gid, {gid: group_model}, update_group)
        assert result is True
        update_group.assert_called_once()

    @pytest.mark.asyncio
    async def test_originals_updated_after_save(self, group_model: dict) -> None:
        """After successful save, orig values are updated."""
        from promptgrimoire.pages.annotation.tag_management_save import (
            _save_single_group,
        )

        gid = uuid4()
        group_model["name"] = "Renamed"
        group_model["color"] = "#aabbcc"
        update_group = AsyncMock()
        await _save_single_group(gid, {gid: group_model}, update_group)
        assert group_model["orig_name"] == "Renamed"
        assert group_model["orig_color"] == "#aabbcc"


class TestCreateTagOrNotify:
    """_create_tag_or_notify maps domain duplicate errors to warning UI."""

    @pytest.mark.asyncio
    async def test_duplicate_name_shows_warning_not_generic_failure(self) -> None:
        """DuplicateNameError should show warning UI and avoid exception logging."""
        from types import SimpleNamespace

        from promptgrimoire.db.tags import DuplicateNameError
        from promptgrimoire.pages.annotation.tag_management_save import (
            _create_tag_or_notify,
        )

        state = SimpleNamespace(workspace_id=uuid4(), crdt_doc=None)
        create_tag = AsyncMock(
            side_effect=DuplicateNameError(
                "A tag named 'Evidence' already exists in this workspace"
            )
        )

        with (
            patch("promptgrimoire.pages.annotation.tag_management_save.ui") as mock_ui,
            patch(
                "promptgrimoire.pages.annotation.tag_management_save.logger"
            ) as mock_logger,
        ):
            result = await _create_tag_or_notify(
                create_tag,
                state,  # type: ignore[arg-type]  # SimpleNamespace stub for PageState
                "Evidence",
                "#1f77b4",
                None,
            )

        assert result is None
        mock_ui.notify.assert_called_once_with(
            "A tag named 'Evidence' already exists",
            type="warning",
        )
        mock_logger.exception.assert_not_called()
