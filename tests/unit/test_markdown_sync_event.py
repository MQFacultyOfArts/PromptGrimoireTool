"""Tests for respond_yjs_update event handling — markdown sync via event payload.

Verifies:
- AC3.1: on_yjs_update reads markdown from event args and writes to
  response_draft_markdown via atomic CRDT replace; no run_javascript call.
- AC3.2: on_yjs_update does NOT call _sync_markdown_to_crdt or any
  run_javascript variant.

The handler under test is the inner ``on_yjs_update`` closure registered
by ``_setup_yjs_event_handler``. We extract it by mocking ``ui.on`` and
capturing the callback.
"""

from __future__ import annotations

import base64
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pycrdt
import pytest

from promptgrimoire.crdt.annotation_doc import AnnotationDocument


def _make_crdt_doc() -> AnnotationDocument:
    """Create a minimal AnnotationDocument with a response_draft_markdown field."""
    return AnnotationDocument("test-doc")


def _make_yjs_update() -> str:
    """Generate a valid base64-encoded Yjs update by mutating a peer doc."""
    peer = pycrdt.Doc()
    peer_text = peer.get("response_draft", type=pycrdt.XmlFragment)
    with peer.transaction():
        peer_text.children.append(pycrdt.XmlText("hello"))

    # get_update with empty state vector returns the full document as an update
    empty_state = b"\x00\x00"
    update = peer.get_update(empty_state)
    return base64.b64encode(update).decode("ascii")


def _capture_on_yjs_handler(
    crdt_doc: AnnotationDocument,
    state: MagicMock | None = None,
) -> tuple:
    """Call _setup_yjs_event_handler and capture the registered on_yjs_update callback.

    Returns (handler, mock_ui_on) so the test can invoke the handler directly.
    """
    from promptgrimoire.pages.annotation.respond import _setup_yjs_event_handler

    if state is None:
        state = MagicMock()
        state.word_count_badge = None

    mock_broadcast = MagicMock()

    with patch("promptgrimoire.pages.annotation.respond.ui") as mock_ui:
        _setup_yjs_event_handler(
            crdt_doc=crdt_doc,
            workspace_key="test-ws",
            workspace_id=MagicMock(),
            client_id="test-client-id-1234",
            on_yjs_update_broadcast=mock_broadcast,
            state=state,
        )
        # ui.on("respond_yjs_update", handler) was called
        on_call = mock_ui.on.call_args
        assert on_call is not None, "ui.on was not called"
        event_name, handler = on_call[0]
        assert event_name == "respond_yjs_update"

    return handler, mock_broadcast, mock_ui


class TestOnYjsUpdateMardownSync:
    """AC3.1: markdown from event payload is written to response_draft_markdown."""

    @pytest.mark.asyncio
    async def test_writes_markdown_from_event_to_crdt(self) -> None:
        """When event args contain markdown, it is written to CRDT text field."""
        crdt_doc = _make_crdt_doc()
        b64_update = _make_yjs_update()

        handler, _, _ = _capture_on_yjs_handler(crdt_doc)

        event = SimpleNamespace(
            args={"update": b64_update, "markdown": "# Hello World"}
        )

        with patch("promptgrimoire.pages.annotation.respond.get_persistence_manager"):
            await handler(event)

        # The markdown text should be in the CRDT text field
        assert str(crdt_doc.response_draft_markdown) == "# Hello World"

    @pytest.mark.asyncio
    async def test_writes_empty_markdown_from_event(self) -> None:
        """When event args contain empty markdown, field is cleared."""
        crdt_doc = _make_crdt_doc()

        # Pre-populate with existing content
        text_field = crdt_doc.response_draft_markdown
        with crdt_doc.doc.transaction():
            text_field += "old content"
        assert str(crdt_doc.response_draft_markdown) == "old content"

        b64_update = _make_yjs_update()
        handler, _, _ = _capture_on_yjs_handler(crdt_doc)

        event = SimpleNamespace(args={"update": b64_update, "markdown": ""})

        with patch("promptgrimoire.pages.annotation.respond.get_persistence_manager"):
            await handler(event)

        # Field should be cleared
        assert str(crdt_doc.response_draft_markdown) == ""

    @pytest.mark.asyncio
    async def test_markdown_missing_from_event_defaults_empty(self) -> None:
        """When event args omit markdown key, defaults to empty string."""
        crdt_doc = _make_crdt_doc()
        b64_update = _make_yjs_update()
        handler, _, _ = _capture_on_yjs_handler(crdt_doc)

        event = SimpleNamespace(args={"update": b64_update})

        with patch("promptgrimoire.pages.annotation.respond.get_persistence_manager"):
            await handler(event)

        # No crash, field should be empty
        assert str(crdt_doc.response_draft_markdown) == ""

    @pytest.mark.asyncio
    async def test_markdown_write_precedes_word_count_read(self) -> None:
        """Markdown is written before word count badge reads it."""
        crdt_doc = _make_crdt_doc()
        b64_update = _make_yjs_update()

        state = MagicMock()
        state.word_count_badge = MagicMock()
        state.word_minimum = 10
        state.word_limit = 100

        handler, _, _ = _capture_on_yjs_handler(crdt_doc, state=state)

        event = SimpleNamespace(
            args={"update": b64_update, "markdown": "Five words are right here"}
        )

        with (
            patch("promptgrimoire.pages.annotation.respond.get_persistence_manager"),
            patch(
                "promptgrimoire.pages.annotation.respond.word_count",
                return_value=5,
            ) as mock_wc,
            patch(
                "promptgrimoire.pages.annotation.respond.format_word_count_badge",
            ) as mock_badge,
        ):
            mock_badge.return_value = SimpleNamespace(
                text="5 words", css_classes="text-red"
            )
            await handler(event)

        # word_count was called with the markdown we just wrote
        mock_wc.assert_called_once()
        md_arg = mock_wc.call_args[0][0]
        assert md_arg == "Five words are right here"


class TestOnYjsUpdateNoRunJavascript:
    """AC3.2: on_yjs_update does NOT call run_javascript or _sync_markdown_to_crdt."""

    @pytest.mark.asyncio
    async def test_no_run_javascript_in_handler(self) -> None:
        """The handler must not call ui.run_javascript (no JS round-trip)."""
        crdt_doc = _make_crdt_doc()
        b64_update = _make_yjs_update()
        handler, _, _mock_ui = _capture_on_yjs_handler(crdt_doc)

        event = SimpleNamespace(args={"update": b64_update, "markdown": "test"})

        with (
            patch("promptgrimoire.pages.annotation.respond.get_persistence_manager"),
            patch("promptgrimoire.pages.annotation.respond.ui") as ui_in_handler,
        ):
            await handler(event)
            ui_in_handler.run_javascript.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_sync_markdown_to_crdt_call(self) -> None:
        """The handler must not call _sync_markdown_to_crdt."""
        crdt_doc = _make_crdt_doc()
        b64_update = _make_yjs_update()
        handler, _, _ = _capture_on_yjs_handler(crdt_doc)

        event = SimpleNamespace(args={"update": b64_update, "markdown": "test"})

        with (
            patch("promptgrimoire.pages.annotation.respond.get_persistence_manager"),
            patch(
                "promptgrimoire.pages.annotation.respond._sync_markdown_to_crdt",
            ) as mock_sync,
        ):
            await handler(event)
            mock_sync.assert_not_called()
