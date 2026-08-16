"""Remote annotation updates preserve live toolbar interactions."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

if TYPE_CHECKING:
    from promptgrimoire.crdt.annotation_doc import AnnotationDocument
    from promptgrimoire.pages.annotation import PageState


_TAG_ID = "00000000-0000-0000-0000-000000000001"


def _state_with_tag() -> tuple[PageState, AnnotationDocument, AsyncMock, MagicMock]:
    """Build real CRDT and page state at the remote-update boundary."""
    from promptgrimoire.crdt.annotation_doc import AnnotationDocument
    from promptgrimoire.pages.annotation import PageState
    from promptgrimoire.pages.annotation.tags import workspace_tags_from_crdt

    doc = AnnotationDocument("remote-toolbar-test")
    doc.set_tag(_TAG_ID, "Issue", "#1f77b4", order_index=0)
    state = PageState(
        workspace_id=uuid4(),
        crdt_doc=doc,
        tag_info_list=workspace_tags_from_crdt(doc),
    )
    refresh_toolbar = AsyncMock()
    refresh_annotations = MagicMock()
    state.refresh_toolbar = refresh_toolbar
    state.refresh_annotations = refresh_annotations
    return state, doc, refresh_toolbar, refresh_annotations


@pytest.fixture
def quiet_remote_ui(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate the toolbar decision from unrelated NiceGUI rendering."""
    monkeypatch.setattr(
        "promptgrimoire.pages.annotation.broadcast._update_highlight_css",
        lambda _state: None,
    )
    monkeypatch.setattr(
        "promptgrimoire.pages.annotation.broadcast._update_user_count",
        lambda _state: None,
    )


@pytest.mark.asyncio
async def test_highlight_only_update_preserves_live_toolbar(
    quiet_remote_ui: None,  # noqa: ARG001 - fixture side effects
) -> None:
    """A new highlight refreshes cards without replacing tag buttons."""
    from promptgrimoire.pages.annotation.broadcast import _handle_remote_update

    state, doc, refresh_toolbar, refresh_annotations = _state_with_tag()
    doc.add_highlight(0, 5, _TAG_ID, "Issue", "Student")

    await _handle_remote_update(state)

    refresh_toolbar.assert_not_awaited()
    refresh_annotations.assert_called_once_with(trigger="crdt_broadcast")


@pytest.mark.asyncio
async def test_tag_metadata_update_rebuilds_toolbar(
    quiet_remote_ui: None,  # noqa: ARG001 - fixture side effects
) -> None:
    """A renamed tag still replaces the toolbar so metadata stays current."""
    from promptgrimoire.pages.annotation.broadcast import _handle_remote_update

    state, doc, refresh_toolbar, refresh_annotations = _state_with_tag()
    doc.set_tag(_TAG_ID, "Renamed issue", "#1f77b4", order_index=0)

    await _handle_remote_update(state)

    refresh_toolbar.assert_awaited_once_with()
    refresh_annotations.assert_called_once_with(trigger="crdt_broadcast")
