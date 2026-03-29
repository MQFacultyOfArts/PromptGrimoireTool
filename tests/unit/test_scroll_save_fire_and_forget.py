"""Test that scroll save/restore in organise tab is fire-and-forget.

Verifies the scroll save no longer blocks the event loop with an await.

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
    def test_calls_run_javascript_without_await(self, mock_ui: MagicMock) -> None:
        """run_javascript is called synchronously (not awaited)."""
        render_fn = MagicMock()
        _rebuild_organise_with_scroll(render_fn)

        # Two fire-and-forget JS calls: save and restore
        assert mock_ui.run_javascript.call_count == 2

    @patch("promptgrimoire.pages.annotation.tab_bar.ui")
    def test_render_fn_called_between_save_and_restore(
        self, mock_ui: MagicMock
    ) -> None:
        """render_fn is called between the save and restore JS calls."""
        call_order: list[str] = []
        mock_ui.run_javascript.side_effect = lambda *_a, **_kw: call_order.append("js")
        render_fn = MagicMock(side_effect=lambda: call_order.append("render"))

        _rebuild_organise_with_scroll(render_fn)

        assert call_order == ["js", "render", "js"]

    @patch("promptgrimoire.pages.annotation.tab_bar.ui")
    def test_restore_does_not_delete_scroll_slot(self, mock_ui: MagicMock) -> None:
        """Restore JS must not delete window._organiseSavedScroll.

        If two rebuilds overlap (rAF from rebuild 1 fires after rebuild 2
        saves), deleting the slot in the first restore destroys rebuild 2's
        saved value. The slot is harmless to leave — the next save always
        overwrites it.
        """
        captured_js: list[str] = []
        mock_ui.run_javascript.side_effect = lambda js, **_kw: captured_js.append(js)
        render_fn = MagicMock()
        _rebuild_organise_with_scroll(render_fn)

        restore_js = captured_js[1]  # second call is the restore
        assert "delete" not in restore_js, (
            "Restore must not delete window._organiseSavedScroll — "
            "overlapping rebuilds would lose the second save"
        )
