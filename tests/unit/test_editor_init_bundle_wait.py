"""Test that editor init JS waits for the Milkdown bundle to load.

Regression test for production editor_init_failed errors caused by the
Milkdown bundle <script> not having finished loading when the editor
init IIFE runs.  Under load (10s+ page loads), the bundle fetch races
with the run_javascript call.

The fix: poll for window._createMilkdownEditor in the IIFE instead of
failing immediately.
"""

from __future__ import annotations

import re
from unittest.mock import MagicMock

from promptgrimoire.pages.annotation.respond import _build_editor_init_js


def _make_mock_crdt() -> MagicMock:
    """Create a mock AnnotationDocument with minimal CRDT state."""
    crdt = MagicMock()
    crdt.get_full_state.return_value = b"\x01\x00"  # empty (2 bytes)
    crdt.get_response_draft_markdown.return_value = ""
    crdt.response_draft = ""
    return crdt


class TestBundleWaitLoop:
    """Editor init JS must poll for the Milkdown bundle, not fail instantly."""

    def test_js_contains_retry_loop(self) -> None:
        """The generated JS should retry/poll for _createMilkdownEditor
        rather than checking once and immediately emitting an error."""
        js = _build_editor_init_js(
            editor_id="test-editor",
            fragment_name="response_draft",
            crdt_doc=_make_mock_crdt(),
            workspace_key="ws-key",
            client_id="client-1234",
        )

        # Must contain a waiting/polling mechanism — setTimeout or similar
        assert re.search(r"setTimeout|setInterval", js), (
            "Expected retry/polling loop (setTimeout/setInterval) in editor "
            "init JS, but found immediate check only"
        )

    def test_js_still_fails_after_timeout(self) -> None:
        """After exhausting retries, the JS should still emit editor_ready
        with status error — don't wait forever."""
        js = _build_editor_init_js(
            editor_id="test-editor",
            fragment_name="response_draft",
            crdt_doc=_make_mock_crdt(),
            workspace_key="ws-key",
            client_id="client-1234",
        )

        # Error path must still exist
        assert "editor_ready" in js
        assert "'error'" in js or '"error"' in js

    def test_js_still_creates_editor_on_success(self) -> None:
        """The happy path (bundle loaded) must still call
        _createMilkdownEditor."""
        js = _build_editor_init_js(
            editor_id="test-editor",
            fragment_name="response_draft",
            crdt_doc=_make_mock_crdt(),
            workspace_key="ws-key",
            client_id="client-1234",
        )

        assert "_createMilkdownEditor" in js
        assert "emitEvent('editor_ready', {status: 'ok'})" in js
