"""Tests for paste handler event payload restructuring.

Verifies:
- AC4.1: handle_add_document_submission receives paste_html, platform_hint,
  and editor_content as direct parameters; no run_javascript calls.
- AC4.2: When paste_html is None/empty, editor_content from event payload
  is used as the document content.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest


class TestNoBrowserCalls:
    """AC4.1: handle_add_document_submission must not call run_javascript."""

    def test_no_run_javascript_in_source(self) -> None:
        """The function body must contain zero ui.run_javascript calls."""
        from promptgrimoire.pages.annotation.paste_handler import (
            handle_add_document_submission,
        )

        source = inspect.getsource(handle_add_document_submission)
        # Parse the AST and check for run_javascript attribute calls,
        # ignoring docstrings and comments.
        tree = ast.parse(textwrap.dedent(source))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "run_javascript":
                msg = (
                    "handle_add_document_submission should not call "
                    "ui.run_javascript; values must arrive via event "
                    "payload parameters"
                )
                pytest.fail(msg)

    def test_signature_has_direct_parameters(self) -> None:
        """The function must accept paste_html, platform_hint, editor_content."""
        from promptgrimoire.pages.annotation.paste_handler import (
            handle_add_document_submission,
        )

        sig = inspect.signature(handle_add_document_submission)
        params = set(sig.parameters.keys())
        assert "paste_html" in params
        assert "platform_hint" in params
        assert "editor_content" in params

    def test_signature_has_no_content_input(self) -> None:
        """The function must NOT accept content_input (Editor element)."""
        from promptgrimoire.pages.annotation.paste_handler import (
            handle_add_document_submission,
        )

        sig = inspect.signature(handle_add_document_submission)
        params = set(sig.parameters.keys())
        assert "content_input" not in params, (
            "content_input parameter should be removed; "
            "editor content arrives via event payload"
        )


class TestEditorContentFallback:
    """AC4.2: When paste_html is None/empty, editor_content is used."""

    @pytest.mark.asyncio
    async def test_uses_editor_content_when_paste_html_is_none(self) -> None:
        """When paste_html is None, editor_content is the document content."""
        from promptgrimoire.pages.annotation.paste_handler import (
            handle_add_document_submission,
        )

        callback = AsyncMock()
        workspace_id = uuid4()

        with (
            patch(
                "promptgrimoire.pages.annotation.paste_handler.show_content_type_dialog",
                new_callable=AsyncMock,
                return_value=("plain_text", False),
            ),
            patch(
                "promptgrimoire.pages.annotation.paste_handler.process_input",
                new_callable=AsyncMock,
                return_value="<p>processed</p>",
            ) as mock_process,
            patch(
                "promptgrimoire.pages.annotation.paste_handler.add_document",
                new_callable=AsyncMock,
            ),
            patch(
                "promptgrimoire.pages.annotation.paste_handler.build_paragraph_map_for_json",
                return_value={"1": "processed"},
            ),
            patch("promptgrimoire.pages.annotation.paste_handler.ui"),
        ):
            await handle_add_document_submission(
                workspace_id=workspace_id,
                paste_html=None,
                platform_hint=None,
                editor_content="typed content here",
                on_document_added=callback,
            )

            # process_input should receive the editor_content, not paste_html
            mock_process.assert_called_once()
            call_kwargs = mock_process.call_args
            assert call_kwargs.kwargs.get("content") == "typed content here" or (
                call_kwargs.args and call_kwargs.args[0] == "typed content here"
            ), "process_input should receive editor_content when paste_html is None"

    @pytest.mark.asyncio
    async def test_uses_editor_content_when_paste_html_is_empty(self) -> None:
        """When paste_html is empty string, editor_content is used."""
        from promptgrimoire.pages.annotation.paste_handler import (
            handle_add_document_submission,
        )

        callback = AsyncMock()
        workspace_id = uuid4()

        with (
            patch(
                "promptgrimoire.pages.annotation.paste_handler.show_content_type_dialog",
                new_callable=AsyncMock,
                return_value=("plain_text", False),
            ),
            patch(
                "promptgrimoire.pages.annotation.paste_handler.process_input",
                new_callable=AsyncMock,
                return_value="<p>processed</p>",
            ) as mock_process,
            patch(
                "promptgrimoire.pages.annotation.paste_handler.add_document",
                new_callable=AsyncMock,
            ),
            patch(
                "promptgrimoire.pages.annotation.paste_handler.build_paragraph_map_for_json",
                return_value={"1": "processed"},
            ),
            patch("promptgrimoire.pages.annotation.paste_handler.ui"),
        ):
            await handle_add_document_submission(
                workspace_id=workspace_id,
                paste_html="",
                platform_hint=None,
                editor_content="fallback content",
                on_document_added=callback,
            )

            mock_process.assert_called_once()
            call_kwargs = mock_process.call_args
            assert call_kwargs.kwargs.get("content") == "fallback content" or (
                call_kwargs.args and call_kwargs.args[0] == "fallback content"
            ), "process_input should receive editor_content when paste_html is empty"

    @pytest.mark.asyncio
    async def test_uses_paste_html_when_present(self) -> None:
        """When paste_html has content, it is used instead of editor_content."""
        from promptgrimoire.pages.annotation.paste_handler import (
            handle_add_document_submission,
        )

        callback = AsyncMock()
        workspace_id = uuid4()

        with (
            patch(
                "promptgrimoire.pages.annotation.paste_handler.process_input",
                new_callable=AsyncMock,
                return_value="<p>processed</p>",
            ) as mock_process,
            patch(
                "promptgrimoire.pages.annotation.paste_handler.add_document",
                new_callable=AsyncMock,
            ),
            patch(
                "promptgrimoire.pages.annotation.paste_handler.detect_paragraph_numbering",
                return_value=(False, {"1": "processed"}),
            ),
            patch("promptgrimoire.pages.annotation.paste_handler.ui"),
        ):
            await handle_add_document_submission(
                workspace_id=workspace_id,
                paste_html="<p>pasted HTML</p>",
                platform_hint="chrome",
                editor_content="editor fallback",
                on_document_added=callback,
            )

            mock_process.assert_called_once()
            call_kwargs = mock_process.call_args
            content_arg = call_kwargs.kwargs.get(
                "content", call_kwargs.args[0] if call_kwargs.args else None
            )
            assert content_arg == "<p>pasted HTML</p>", (
                "process_input should receive paste_html when it has content"
            )
            # Platform hint should be passed through
            platform_arg = call_kwargs.kwargs.get("platform_hint")
            assert platform_arg == "chrome"

    @pytest.mark.asyncio
    async def test_empty_content_shows_warning(self) -> None:
        """When both paste_html and editor_content are empty, show warning."""
        from promptgrimoire.pages.annotation.paste_handler import (
            handle_add_document_submission,
        )

        callback = AsyncMock()
        workspace_id = uuid4()

        with (
            patch(
                "promptgrimoire.pages.annotation.paste_handler.add_document",
                new_callable=AsyncMock,
            ) as mock_add_doc,
            patch("promptgrimoire.pages.annotation.paste_handler.ui") as mock_ui,
        ):
            await handle_add_document_submission(
                workspace_id=workspace_id,
                paste_html=None,
                platform_hint=None,
                editor_content="",
                on_document_added=callback,
            )

            # Should notify warning and NOT add document
            mock_ui.notify.assert_called_once()
            assert "warning" in str(mock_ui.notify.call_args)
            mock_add_doc.assert_not_called()
            callback.assert_not_called()
