"""Unit tests for warp navigation (Phase 6) infrastructure.

Tests verify that the _warp_to_highlight function is importable and has the
correct signature, and that render_organise_tab and render_respond_tab accept
the on_locate callback parameter.

Traceability:
- Design: docs/implementation-plans/2026-02-07-three-tab-ui-98/phase_06.md
- AC: three-tab-ui.AC5.1, AC5.4, AC5.5
"""

from __future__ import annotations

import inspect

from promptgrimoire.pages.annotation.highlights import _warp_to_highlight
from promptgrimoire.pages.annotation.organise import (
    _build_highlight_card,
    render_organise_tab,
)
from promptgrimoire.pages.annotation.respond import (
    _build_reference_card,
    _build_reference_panel,
    render_respond_tab,
)


class TestWarpToHighlightSignature:
    """Verify _warp_to_highlight function exists with correct signature."""

    def test_is_async_function(self) -> None:
        """_warp_to_highlight must be async (uses ui.run_javascript)."""
        assert inspect.iscoroutinefunction(_warp_to_highlight)

    def test_accepts_state_start_end(self) -> None:
        """Signature includes state, start_char, end_char parameters."""
        sig = inspect.signature(_warp_to_highlight)
        param_names = list(sig.parameters.keys())
        assert "state" in param_names
        assert "start_char" in param_names
        assert "end_char" in param_names

    def test_has_three_parameters(self) -> None:
        """Function takes exactly 3 required parameters."""
        sig = inspect.signature(_warp_to_highlight)
        required = [
            p for p in sig.parameters.values() if p.default is inspect.Parameter.empty
        ]
        assert len(required) == 3


class TestOrganiseLocateParameter:
    """Verify render_organise_tab and card builder accept on_locate."""

    def test_render_organise_tab_accepts_on_locate(self) -> None:
        """render_organise_tab has on_locate keyword parameter."""
        sig = inspect.signature(render_organise_tab)
        assert "on_locate" in sig.parameters
        param = sig.parameters["on_locate"]
        assert param.default is None

    def test_build_highlight_card_accepts_on_locate(self) -> None:
        """_build_highlight_card has on_locate parameter."""
        sig = inspect.signature(_build_highlight_card)
        assert "on_locate" in sig.parameters
        param = sig.parameters["on_locate"]
        assert param.default is None


class TestRespondLocateParameter:
    """Verify render_respond_tab and card builder accept on_locate."""

    def test_render_respond_tab_accepts_on_locate(self) -> None:
        """render_respond_tab has on_locate keyword parameter."""
        sig = inspect.signature(render_respond_tab)
        assert "on_locate" in sig.parameters
        param = sig.parameters["on_locate"]
        assert param.default is None

    def test_build_reference_card_accepts_on_locate(self) -> None:
        """_build_reference_card has on_locate parameter."""
        sig = inspect.signature(_build_reference_card)
        assert "on_locate" in sig.parameters
        param = sig.parameters["on_locate"]
        assert param.default is None

    def test_build_reference_panel_accepts_on_locate(self) -> None:
        """_build_reference_panel has on_locate parameter."""
        sig = inspect.signature(_build_reference_panel)
        assert "on_locate" in sig.parameters
        param = sig.parameters["on_locate"]
        assert param.default is None
