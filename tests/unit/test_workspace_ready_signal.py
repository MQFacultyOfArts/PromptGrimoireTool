"""Tests for the deferred annotation workspace readiness boundary."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest


def test_title_update_and_ready_signal_are_one_ordered_browser_operation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Readiness cannot precede the title mutation observers depend upon."""
    from promptgrimoire.pages.annotation import workspace

    scripts: list[str] = []
    monkeypatch.setattr(workspace.ui, "run_javascript", scripts.append)

    workspace._update_page_title("Deferred Load Test Workspace")

    assert len(scripts) == 1
    script = scripts[0]
    assert script.index("document.title") < script.index("window.__loadComplete = true")
