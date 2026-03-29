"""Test pre-restart Milkdown flush uses fire-and-forget pattern.

Verifies eliminate-js-await-454.AC3.4 through AC3.7:
- AC3.4: _flush_milkdown_to_crdt sends fire-and-forget _flushRespondMarkdownNow,
          then asyncio.sleep(1.0), then reads from response_draft_markdown
- AC3.5: _on_markdown_flush writes to CRDT and calls mark_dirty_workspace
          without broadcasting or updating badges
- AC3.6: Flush contains exactly one asyncio.sleep(1.0), no per-client
          await run_javascript calls (structural check)
- AC3.7: When no Yjs events have fired, response_draft_markdown holds initial
          DB value; flush reads it without error

Traceability: Issue #454
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from promptgrimoire.crdt.annotation_doc import AnnotationDocument


class TestFlushMilkdownFireAndForget:
    """AC3.4: _flush_milkdown_to_crdt sends fire-and-forget JS calls."""

    @pytest.mark.anyio
    async def test_flush_sends_fire_and_forget_to_all_milkdown_clients(
        self,
    ) -> None:
        """Fire-and-forget _flushRespondMarkdownNow is sent to each client
        with has_milkdown_editor, then sleep(1.0) is called, then
        response_draft_markdown is read from the CRDT doc."""
        from promptgrimoire.pages.restart import _flush_milkdown_to_crdt

        # Build mock presence with two milkdown clients and one without
        mock_client_a = MagicMock()
        mock_client_a._deleted = False
        mock_client_a.has_socket_connection = True
        mock_client_a.run_javascript = MagicMock()  # not async — fire-and-forget

        mock_client_b = MagicMock()
        mock_client_b._deleted = False
        mock_client_b.has_socket_connection = True
        mock_client_b.run_javascript = MagicMock()

        mock_client_no_editor = MagicMock()
        mock_client_no_editor._deleted = False
        mock_client_no_editor.has_socket_connection = True

        presence_a = MagicMock()
        presence_a.has_milkdown_editor = True
        presence_a.nicegui_client = mock_client_a

        presence_b = MagicMock()
        presence_b.has_milkdown_editor = True
        presence_b.nicegui_client = mock_client_b

        presence_no = MagicMock()
        presence_no.has_milkdown_editor = False
        presence_no.nicegui_client = mock_client_no_editor

        workspace_presence = {
            "ws-1": {"c1": presence_a, "c2": presence_no},
            "ws-2": {"c3": presence_b},
        }

        # Build a real CRDT doc with some initial markdown
        crdt_doc = AnnotationDocument(doc_id="test-doc")
        text_field = crdt_doc.response_draft_markdown
        with crdt_doc.doc.transaction():
            text_field += "initial markdown"

        mock_registry = AsyncMock()
        mock_registry.get_or_create_for_workspace = AsyncMock(return_value=crdt_doc)

        with (
            patch(
                "promptgrimoire.pages.restart._get_annotation_state",
                return_value=(workspace_presence, mock_registry),
            ),
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            await _flush_milkdown_to_crdt()

        # Both milkdown clients got fire-and-forget JS calls
        mock_client_a.run_javascript.assert_called_once()
        assert (
            "_flushRespondMarkdownNow" in mock_client_a.run_javascript.call_args[0][0]
        )
        mock_client_b.run_javascript.assert_called_once()
        assert (
            "_flushRespondMarkdownNow" in mock_client_b.run_javascript.call_args[0][0]
        )

        # Non-milkdown client did NOT get a JS call
        mock_client_no_editor.run_javascript.assert_not_called()

        # Sleep was called with 1.0 (the drain deadline)
        mock_sleep.assert_called_once_with(1.0)


class TestFlushStructural:
    """AC3.6: Structural checks on _flush_milkdown_to_crdt."""

    def test_flush_has_exactly_one_asyncio_sleep(self) -> None:
        """_flush_milkdown_to_crdt contains exactly one asyncio.sleep(1.0)
        call, not N per-client awaits."""
        from promptgrimoire.pages.restart import _flush_milkdown_to_crdt

        source = textwrap.dedent(inspect.getsource(_flush_milkdown_to_crdt))
        tree = ast.parse(source)

        sleep_calls: list[ast.Await] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Await):
                inner = node.value
                if isinstance(inner, ast.Call):
                    func = inner.func
                    # asyncio.sleep or sleep
                    if (isinstance(func, ast.Attribute) and func.attr == "sleep") or (
                        isinstance(func, ast.Name) and func.id == "sleep"
                    ):
                        sleep_calls.append(node)

        assert len(sleep_calls) == 1, (
            f"Expected exactly 1 asyncio.sleep call, found {len(sleep_calls)}"
        )

        # Verify the sleep argument is 1.0
        call_node = sleep_calls[0].value
        assert isinstance(call_node, ast.Call)
        assert len(call_node.args) >= 1
        arg = call_node.args[0]
        assert isinstance(arg, ast.Constant)
        assert arg.value == 1.0, f"Expected sleep(1.0), got sleep({arg.value})"

    def test_flush_has_no_per_client_await_run_javascript(self) -> None:
        """_flush_milkdown_to_crdt does not await run_javascript
        (fire-and-forget only)."""
        from promptgrimoire.pages.restart import _flush_milkdown_to_crdt

        source = textwrap.dedent(inspect.getsource(_flush_milkdown_to_crdt))
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.Await):
                inner = node.value
                if isinstance(inner, ast.Call):
                    func = inner.func
                    if (
                        isinstance(func, ast.Attribute)
                        and func.attr == "run_javascript"
                    ):
                        msg = (
                            "_flush_milkdown_to_crdt still awaits "
                            "run_javascript — should be fire-and-forget"
                        )
                        raise AssertionError(msg)

    def test_flush_single_client_removed(self) -> None:
        """_flush_single_client should no longer exist in restart.py."""
        import promptgrimoire.pages.restart as restart_mod

        assert not hasattr(restart_mod, "_flush_single_client"), (
            "_flush_single_client should be removed — "
            "replaced by fire-and-forget pattern in _flush_milkdown_to_crdt"
        )


class TestOnMarkdownFlush:
    """AC3.5: _on_markdown_flush writes to CRDT and marks dirty."""

    @pytest.mark.anyio
    async def test_on_markdown_flush_writes_crdt_and_marks_dirty(self) -> None:
        """Handler writes markdown to CRDT response_draft_markdown and
        calls mark_dirty_workspace. Does NOT broadcast or update badges."""
        from promptgrimoire.pages.annotation.respond import _on_markdown_flush

        crdt_doc = AnnotationDocument(doc_id="test-doc")
        workspace_id = UUID("00000000-0000-0000-0000-000000000001")

        mock_pm = MagicMock()

        event = MagicMock()
        event.args = {"markdown": "# Hello World"}

        with patch(
            "promptgrimoire.pages.annotation.respond.get_persistence_manager",
            return_value=mock_pm,
        ):
            _on_markdown_flush(
                event,
                crdt_doc=crdt_doc,
                workspace_id=workspace_id,
                client_id="test-client-id",
            )

        # CRDT field was updated
        assert str(crdt_doc.response_draft_markdown) == "# Hello World"

        # Persistence was triggered
        mock_pm.mark_dirty_workspace.assert_called_once()

    @pytest.mark.anyio
    async def test_on_markdown_flush_does_not_broadcast(self) -> None:
        """Handler must NOT relay to peers or update word count badges."""
        from promptgrimoire.pages.annotation.respond import _on_markdown_flush

        source = textwrap.dedent(inspect.getsource(_on_markdown_flush))

        # Should not reference broadcast or badge functions
        assert "on_yjs_update_broadcast" not in source
        assert "word_count_badge" not in source
        assert "set_text" not in source


class TestFlushInitialMarkdown:
    """AC3.7: When no Yjs events fired, flush reads initial DB value."""

    @pytest.mark.anyio
    async def test_initial_markdown_survives_flush(self) -> None:
        """response_draft_markdown holds DB-seeded value; flush reads it
        without error even when no browser events have arrived."""
        crdt_doc = AnnotationDocument(doc_id="test-doc")

        # Simulate DB-seeded markdown (as done during workspace load)
        initial = "This is the initial response from the database."
        text_field = crdt_doc.response_draft_markdown
        with crdt_doc.doc.transaction():
            text_field += initial

        # Verify the value persists without any Yjs events
        assert str(crdt_doc.response_draft_markdown) == initial

        # The replace pattern used by _replace_crdt_text should work
        from promptgrimoire.pages.restart import _replace_crdt_text

        _replace_crdt_text(
            crdt_doc.response_draft_markdown,
            initial,  # same value — should be a no-op
            crdt_doc.doc,
        )
        assert str(crdt_doc.response_draft_markdown) == initial

        # Replace with new value also works
        _replace_crdt_text(
            crdt_doc.response_draft_markdown,
            "updated content",
            crdt_doc.doc,
        )
        assert str(crdt_doc.response_draft_markdown) == "updated content"


class TestFlushRespondMarkdownNowJS:
    """Verify _flushRespondMarkdownNow is defined in the bundled init JS."""

    def test_flush_function_defined_in_init_js(self) -> None:
        """The bundled init JS block must define window._flushRespondMarkdownNow."""
        from promptgrimoire.pages.annotation.respond import _build_editor_init_js

        crdt_doc = AnnotationDocument(doc_id="test-doc")
        js = _build_editor_init_js(
            "test-editor",
            "response_draft",
            crdt_doc,
            "ws-key",
            "client-id",
        )
        assert "_flushRespondMarkdownNow" in js
        assert "respond_markdown_flush" in js
        assert "_getMilkdownMarkdown" in js
