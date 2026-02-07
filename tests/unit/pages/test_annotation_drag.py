"""Unit tests for drag-and-drop infrastructure module.

Tests verify that create_drag_state() produces independent, per-client
drag state instances that correctly track and clear the currently dragged
highlight ID.

Traceability:
- Design: docs/implementation-plans/2026-02-07-three-tab-ui/phase_04.md Task 1
- AC: three-tab-ui.AC2.3 (partially -- provides the drag mechanics)
"""

from __future__ import annotations

from promptgrimoire.pages.annotation_drag import create_drag_state


class TestCreateDragState:
    """Verify create_drag_state() produces correct per-client drag state."""

    def test_create_drag_state_returns_independent_instances(self) -> None:
        """Two drag states do not share state -- setting one leaves other unaffected."""
        state_a = create_drag_state()
        state_b = create_drag_state()

        state_a.set_dragged("highlight-123")

        assert state_a.get_dragged() == "highlight-123"
        assert state_b.get_dragged() is None

    def test_create_drag_state_tracks_dragged_id(self) -> None:
        """Setting a highlight ID on drag state allows retrieval."""
        state = create_drag_state()

        state.set_dragged("hl-abc-def")

        assert state.get_dragged() == "hl-abc-def"

    def test_create_drag_state_clears_on_drop(self) -> None:
        """Clearing drag state after drop returns None."""
        state = create_drag_state()

        state.set_dragged("hl-to-drop")
        state.clear()

        assert state.get_dragged() is None

    def test_create_drag_state_initial_state_is_none(self) -> None:
        """A fresh drag state has no dragged highlight."""
        state = create_drag_state()

        assert state.get_dragged() is None

    def test_create_drag_state_overwrite(self) -> None:
        """Setting a new dragged ID overwrites the previous one."""
        state = create_drag_state()

        state.set_dragged("first")
        state.set_dragged("second")

        assert state.get_dragged() == "second"

    def test_create_drag_state_tracks_source_tag(self) -> None:
        """Drag state tracks the source tag name for cross-column drops."""
        state = create_drag_state()

        state.set_dragged("hl-123", source_tag="jurisdiction")

        assert state.get_dragged() == "hl-123"
        assert state.get_source_tag() == "jurisdiction"

    def test_create_drag_state_clear_resets_source_tag(self) -> None:
        """Clearing drag state also resets source tag."""
        state = create_drag_state()

        state.set_dragged("hl-123", source_tag="jurisdiction")
        state.clear()

        assert state.get_source_tag() is None
