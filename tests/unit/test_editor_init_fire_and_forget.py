"""Test that editor initialisation is a single fire-and-forget JS block.

Verifies eliminate-js-await-454.AC2.1 and AC2.2:
- AC2.1: render_respond_tab() does not contain awaited run_javascript
- AC2.2: The JS block includes full-state sync and markdown seed after
  crepe.create() resolves (bundled, no separate round-trip)

Traceability: Issue #454
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from promptgrimoire.pages.annotation.respond import _build_editor_init_js


def _make_crdt_doc(
    *,
    full_state: bytes = b"",
    markdown: str = "",
    response_draft_str: str = "",
) -> Any:
    """Create a minimal mock CRDT doc."""
    doc = MagicMock()
    doc.get_full_state.return_value = full_state
    doc.get_response_draft_markdown.return_value = markdown
    doc.response_draft = MagicMock(__str__=lambda _: response_draft_str)
    return doc


class TestBuildEditorInitJs:
    """The builder produces a single JS block with all init steps."""

    def test_contains_create_editor_call(self) -> None:
        doc = _make_crdt_doc()
        js = _build_editor_init_js("ed-1", "frag", doc, "ws-1", "client-1")

        assert "_createMilkdownEditor" in js

    def test_contains_editor_ready_event(self) -> None:
        doc = _make_crdt_doc()
        js = _build_editor_init_js("ed-1", "frag", doc, "ws-1", "client-1")

        assert "editor_ready" in js
        assert "'ok'" in js

    def test_contains_error_handling(self) -> None:
        doc = _make_crdt_doc()
        js = _build_editor_init_js("ed-1", "frag", doc, "ws-1", "client-1")

        assert "catch" in js
        assert "'error'" in js

    def test_includes_full_state_sync_when_content_exists(self) -> None:
        """AC2.2: Full-state sync is bundled into the same JS block."""
        doc = _make_crdt_doc(full_state=b"\x01\x02\x03")
        js = _build_editor_init_js("ed-1", "frag", doc, "ws-1", "client-1")

        assert "_applyRemoteUpdate" in js

    def test_excludes_full_state_sync_when_empty(self) -> None:
        # Empty doc is 2 bytes
        doc = _make_crdt_doc(full_state=b"\x01\x00")
        js = _build_editor_init_js("ed-1", "frag", doc, "ws-1", "client-1")

        assert "_applyRemoteUpdate" not in js

    def test_includes_markdown_seed_for_fresh_clone(self) -> None:
        """AC2.2: Markdown seed is bundled into the same JS block."""
        doc = _make_crdt_doc(
            markdown="# Hello",
            response_draft_str="",  # empty XmlFragment = fresh clone
        )
        js = _build_editor_init_js("ed-1", "frag", doc, "ws-1", "client-1")

        assert "_setMilkdownMarkdown" in js
        assert "# Hello" in js

    def test_excludes_markdown_seed_when_fragment_has_content(self) -> None:
        doc = _make_crdt_doc(
            markdown="# Hello",
            response_draft_str="existing content",
        )
        js = _build_editor_init_js("ed-1", "frag", doc, "ws-1", "client-1")

        assert "_setMilkdownMarkdown" not in js

    def test_is_self_executing_iife(self) -> None:
        """The block is an IIFE so it executes immediately."""
        doc = _make_crdt_doc()
        js = _build_editor_init_js("ed-1", "frag", doc, "ws-1", "client-1")

        assert "(async function()" in js
        assert "})();" in js
