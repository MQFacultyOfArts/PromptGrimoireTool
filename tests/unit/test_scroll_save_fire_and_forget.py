"""Test that scroll save/restore in organise tab is fire-and-forget.

Scroll position is continuously tracked by a JS scroll event listener
on the organise-columns element (attached in organise.py). The rebuild
function only needs to re-render and restore — no save step.

Traceability: Issue #454
"""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock, patch

from promptgrimoire.pages.annotation.tab_bar import (
    _rebuild_organise_with_scroll,
)


class TestScrollSaveFireAndForget:
    """Scroll save/restore uses fire-and-forget JS calls."""

    def test_rebuild_organise_with_scroll_is_not_coroutine(self) -> None:
        assert not inspect.iscoroutinefunction(_rebuild_organise_with_scroll)

    @patch("promptgrimoire.pages.annotation.tab_bar.ui")
    def test_calls_snapshot_listener_and_restore(self, mock_ui: MagicMock) -> None:
        """Three JS calls: snapshot + re-attach listener + restore."""
        render_fn = MagicMock()
        _rebuild_organise_with_scroll(render_fn)

        assert mock_ui.run_javascript.call_count == 3

    @patch("promptgrimoire.pages.annotation.tab_bar.ui")
    def test_snapshot_before_render_restore_after(self, mock_ui: MagicMock) -> None:
        """Snapshot before render, listener+restore after."""
        call_order: list[str] = []
        mock_ui.run_javascript.side_effect = lambda *_a, **_kw: call_order.append("js")
        render_fn = MagicMock(side_effect=lambda: call_order.append("render"))

        _rebuild_organise_with_scroll(render_fn)

        assert call_order == ["js", "render", "js", "js"]

    @patch("promptgrimoire.pages.annotation.tab_bar.ui")
    def test_restore_uses_snapshot_not_live(self, mock_ui: MagicMock) -> None:
        """Restore reads from snapshot (immune to listener zeroing)."""
        captured_js: list[str] = []
        mock_ui.run_javascript.side_effect = lambda js, **_kw: captured_js.append(js)
        render_fn = MagicMock()
        _rebuild_organise_with_scroll(render_fn)

        restore_js = captured_js[2]  # third call is the restore
        assert "Snapshot" in restore_js
        assert "delete" not in restore_js
