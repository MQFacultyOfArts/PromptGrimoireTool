"""Tests for _extract_response_markdown in pdf_export module.

Verifies AC3.3: the function is synchronous, reads from the CRDT mirror,
and returns empty string when crdt_doc is None.
"""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock

from promptgrimoire.pages.annotation.pdf_export import _extract_response_markdown


def _make_state(*, crdt_doc: object | None = None) -> MagicMock:
    """Build a minimal PageState mock with the given crdt_doc."""
    state = MagicMock()
    state.crdt_doc = crdt_doc
    return state


class TestExtractResponseMarkdownAC33:
    """AC3.3: _extract_response_markdown is sync and reads from CRDT."""

    def test_is_synchronous(self) -> None:
        """The function must be a plain def, not async def."""
        assert not inspect.iscoroutinefunction(_extract_response_markdown)

    def test_returns_empty_when_crdt_doc_is_none(self) -> None:
        state = _make_state(crdt_doc=None)
        result = _extract_response_markdown(state)
        assert result == ""

    def test_reads_from_crdt_doc(self) -> None:
        mock_doc = MagicMock()
        mock_doc.get_response_draft_markdown.return_value = (
            "# My Response\n\nHello world"
        )
        state = _make_state(crdt_doc=mock_doc)

        result = _extract_response_markdown(state)

        assert result == "# My Response\n\nHello world"
        mock_doc.get_response_draft_markdown.assert_called_once()

    def test_returns_empty_when_crdt_returns_empty(self) -> None:
        mock_doc = MagicMock()
        mock_doc.get_response_draft_markdown.return_value = ""
        state = _make_state(crdt_doc=mock_doc)

        result = _extract_response_markdown(state)

        assert result == ""
