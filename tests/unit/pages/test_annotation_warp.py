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
from uuid import UUID, uuid4

from promptgrimoire.pages.annotation.highlights import (
    _resolve_warp_target_doc_id,
    _warp_to_highlight,
)
from promptgrimoire.pages.annotation.organise import (
    _build_highlight_card_html,
    render_organise_tab,
)
from promptgrimoire.pages.annotation.respond import (
    _build_reference_card_html,
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


class TestResolveWarpTargetDocId:
    """Pure logic extracted from _warp_to_highlight's tab-resolution branch."""

    def test_no_document_id_returns_first_tab(self) -> None:
        """With no document_id hint, the first tab in the mapping wins."""
        first = uuid4()
        document_tabs = {first: object(), uuid4(): object()}
        assert _resolve_warp_target_doc_id(None, document_tabs) == str(first)

    def test_valid_known_document_id_is_used_verbatim(self) -> None:
        """A document_id that matches a known tab is returned unchanged."""
        known = uuid4()
        document_tabs = {known: object(), uuid4(): object()}
        assert _resolve_warp_target_doc_id(str(known), document_tabs) == str(known)

    def test_valid_but_unknown_document_id_falls_back_to_first_tab(self) -> None:
        """A well-formed UUID absent from document_tabs falls back to the first tab."""
        first = uuid4()
        document_tabs = {first: object()}
        assert _resolve_warp_target_doc_id(str(uuid4()), document_tabs) == str(first)

    def test_malformed_document_id_falls_back_to_first_tab(self) -> None:
        """A non-UUID document_id string falls back to the first tab."""
        first = uuid4()
        document_tabs = {first: object()}
        assert _resolve_warp_target_doc_id("not-a-uuid", document_tabs) == str(first)

    def test_empty_string_document_id_falls_back_to_first_tab(self) -> None:
        """An empty document_id is falsy, so it falls back like None."""
        first = uuid4()
        document_tabs = {first: object()}
        assert _resolve_warp_target_doc_id("", document_tabs) == str(first)

    def test_return_type_is_str(self) -> None:
        """The resolved id is always a str, even though keys are UUID."""
        first = uuid4()
        result = _resolve_warp_target_doc_id(None, {first: object()})
        assert isinstance(result, str)
        assert UUID(result) == first


class TestOrganiseLocateParameter:
    """Verify render_organise_tab and card builder accept on_locate."""

    def test_render_organise_tab_accepts_on_locate(self) -> None:
        """render_organise_tab has on_locate keyword parameter."""
        sig = inspect.signature(render_organise_tab)
        assert "on_locate" in sig.parameters
        param = sig.parameters["on_locate"]
        assert param.default is None

    def test_build_highlight_card_html_accepts_on_locate(self) -> None:
        """_build_highlight_card_html has on_locate parameter."""
        sig = inspect.signature(_build_highlight_card_html)
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

    def test_build_reference_card_html_accepts_on_locate(self) -> None:
        """_build_reference_card_html has on_locate parameter."""
        sig = inspect.signature(_build_reference_card_html)
        assert "on_locate" in sig.parameters
        param = sig.parameters["on_locate"]
        assert param.default is None

    def test_build_reference_panel_accepts_on_locate(self) -> None:
        """_build_reference_panel has on_locate parameter."""
        sig = inspect.signature(_build_reference_panel)
        assert "on_locate" in sig.parameters
        param = sig.parameters["on_locate"]
        assert param.default is None
