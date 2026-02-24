"""Unit tests for tag toolbar gating behind can_annotate.

Viewers (effective_permission="viewer") must NOT see the tag toolbar.
Users with peer, editor, or owner permissions must see it.

Traceability:
- AC: refactor-workspace-185.AC4.1, refactor-workspace-185.AC4.2
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest

from promptgrimoire.pages.annotation import PageState
from promptgrimoire.pages.annotation.document import _render_document_with_highlights


@pytest.fixture()
def workspace_id() -> UUID:
    return uuid4()


def _make_mock_doc() -> MagicMock:
    """Create a minimal mock WorkspaceDocument."""
    doc = MagicMock()
    doc.id = uuid4()
    doc.content = "<p>Hello</p>"
    doc.source_type = "html"
    return doc


class TestTagToolbarGating:
    """Verify _build_tag_toolbar is only called when state.can_annotate is True."""

    async def test_tag_toolbar_hidden_for_viewer(self, workspace_id: UUID) -> None:
        """Viewer (can_annotate=False) must NOT get the tag toolbar built."""
        state = PageState(
            workspace_id=workspace_id,
            effective_permission="viewer",
        )
        assert state.can_annotate is False

        doc = _make_mock_doc()
        crdt_doc = MagicMock()

        with (
            patch(
                "promptgrimoire.pages.annotation.document._build_tag_toolbar"
            ) as mock_toolbar,
            patch("promptgrimoire.pages.annotation.document.ui"),
            patch(
                "promptgrimoire.pages.annotation.document._build_highlight_pseudo_css",
                return_value="",
            ),
            patch(
                "promptgrimoire.pages.annotation.document._build_highlight_json",
                return_value="{}",
            ),
            patch(
                "promptgrimoire.pages.annotation.document._refresh_annotation_cards",
            ),
            patch(
                "promptgrimoire.pages.annotation.document._render_js",
                return_value="",
            ),
            patch(
                "promptgrimoire.pages.annotation.document.extract_text_from_html",
                return_value=[],
            ),
        ):
            await _render_document_with_highlights(state, doc, crdt_doc)

            mock_toolbar.assert_not_called()

    @pytest.mark.parametrize("permission", ["peer", "editor", "owner"])
    async def test_tag_toolbar_shown_for_annotating_user(
        self, workspace_id: UUID, permission: str
    ) -> None:
        """Users with peer/editor/owner permission must get the tag toolbar."""
        state = PageState(
            workspace_id=workspace_id,
            effective_permission=permission,  # type: ignore[arg-type]  # parametrize yields str, not Literal PermissionLevel
        )
        assert state.can_annotate is True

        doc = _make_mock_doc()
        crdt_doc = MagicMock()

        with (
            patch(
                "promptgrimoire.pages.annotation.document._build_tag_toolbar"
            ) as mock_toolbar,
            patch("promptgrimoire.pages.annotation.document.ui"),
            patch(
                "promptgrimoire.pages.annotation.document._build_highlight_pseudo_css",
                return_value="",
            ),
            patch(
                "promptgrimoire.pages.annotation.document._build_highlight_json",
                return_value="{}",
            ),
            patch(
                "promptgrimoire.pages.annotation.document._refresh_annotation_cards",
            ),
            patch(
                "promptgrimoire.pages.annotation.document._render_js",
                return_value="",
            ),
            patch(
                "promptgrimoire.pages.annotation.document.extract_text_from_html",
                return_value=[],
            ),
        ):
            await _render_document_with_highlights(state, doc, crdt_doc)

            mock_toolbar.assert_called_once()
