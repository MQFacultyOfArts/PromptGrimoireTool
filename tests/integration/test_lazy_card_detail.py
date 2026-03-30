"""Lazy detail section rendering for annotation cards (#457).

Verifies that annotation card detail sections are built lazily (on first
expand) rather than eagerly on initial load, across all rebuild paths.

AC1.1: Detail section not built for collapsed cards on initial load
AC1.2: Detail section built on first expand click
AC1.3: Previously-expanded cards build detail eagerly
AC1.4: Card diff/rebuild handles lazy detail correctly
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import pytest

from promptgrimoire.config import get_settings
from tests.integration.nicegui_helpers import _fire_event_listeners

if TYPE_CHECKING:
    from nicegui.element import Element
    from nicegui.testing.user import User

pytestmark = [
    pytest.mark.skipif(
        not get_settings().dev.test_database_url,
        reason="DEV__TEST_DATABASE_URL not configured",
    ),
    pytest.mark.nicegui_ui,
]


def _make_test_state(
    crdt_doc: Any,
    document_id: UUID,
    container: Any,
) -> Any:
    """Create a minimal PageState with can_annotate=True for lazy detail tests.

    Uses effective_permission="owner" so that can_annotate=True and the
    detail section builds tag-select + comment-input elements we can
    detect.
    """
    from promptgrimoire.pages.annotation import PageState

    state = PageState(
        workspace_id=uuid4(),
        effective_permission="owner",
        user_name="LazyTest",
        user_id="lazy-test-user",
    )
    state.crdt_doc = crdt_doc
    state.document_id = document_id
    state.annotations_container = container
    state.tag_info_list = []
    return state


def _find_detail_children(container: Any, highlight_id: str) -> list[Element]:
    """Find children of the card-detail div for a given highlight.

    Returns child elements of the detail container. An empty list means
    the detail section has NOT been built (lazy — div exists but empty).
    """
    for card_el in container.default_slot.children:
        if card_el.props.get("data-highlight-id") != highlight_id:
            continue
        # Walk card children to find detail div
        for child in card_el.default_slot.children:
            if child.props.get("data-testid") == "card-detail":
                return list(child.default_slot.children)
    return []


def _find_detail_element(container: Any, highlight_id: str) -> Element | None:
    """Find the card-detail div element for a given highlight."""
    for card_el in container.default_slot.children:
        if card_el.props.get("data-highlight-id") != highlight_id:
            continue
        for child in card_el.default_slot.children:
            if child.props.get("data-testid") == "card-detail":
                return child
    return None


class TestLazyDetailSection:
    """Verify lazy detail section build across all rebuild paths."""

    @pytest.mark.asyncio
    async def test_collapsed_cards_have_empty_detail_on_load(
        self, nicegui_user: User
    ) -> None:
        """AC1.1: detail section not built for collapsed cards on initial load."""
        from nicegui import ui

        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.pages.annotation.cards import _refresh_annotation_cards

        await nicegui_user.open("/")

        doc_uuid = uuid4()
        doc_id = str(doc_uuid)
        crdt_doc = AnnotationDocument("test-lazy-ac11")
        hl1 = crdt_doc.add_highlight(10, 20, "tag_a", "Alice", "u1", document_id=doc_id)
        hl2 = crdt_doc.add_highlight(30, 40, "tag_b", "Bob", "u2", document_id=doc_id)

        with nicegui_user:
            container = ui.column()
        state = _make_test_state(crdt_doc, doc_uuid, container)

        # Full build (annotation_cards is None)
        with nicegui_user:
            _refresh_annotation_cards(state)

        assert state.annotation_cards is not None
        assert len(state.annotation_cards) == 2

        # Both detail containers should exist (div with data-testid)
        # but have NO children (lazy — not built yet)
        detail1 = _find_detail_element(container, hl1)
        detail2 = _find_detail_element(container, hl2)
        assert detail1 is not None, "card-detail div must exist for hl1"
        assert detail2 is not None, "card-detail div must exist for hl2"
        assert not detail1.visible, "card-detail should be hidden"
        assert not detail2.visible, "card-detail should be hidden"

        children1 = _find_detail_children(container, hl1)
        children2 = _find_detail_children(container, hl2)
        assert len(children1) == 0, (
            f"AC1.1: collapsed detail should be empty, got {len(children1)}"
        )
        assert len(children2) == 0, (
            f"AC1.1: collapsed detail should be empty, got {len(children2)}"
        )

        # detail_built_cards should be empty
        assert len(state.detail_built_cards) == 0

    @pytest.mark.asyncio
    async def test_first_expand_builds_detail(self, nicegui_user: User) -> None:
        """AC1.2: detail section built on first expand click."""
        from nicegui import ui

        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.pages.annotation.cards import _refresh_annotation_cards

        await nicegui_user.open("/")

        doc_uuid = uuid4()
        doc_id = str(doc_uuid)
        crdt_doc = AnnotationDocument("test-lazy-ac12")
        hl1 = crdt_doc.add_highlight(
            10,
            20,
            "tag_a",
            "Alice",
            "u1",
            document_id=doc_id,
        )
        hl2 = crdt_doc.add_highlight(
            30,
            40,
            "tag_b",
            "Bob",
            "u2",
            document_id=doc_id,
        )

        with nicegui_user:
            container = ui.column()
        state = _make_test_state(crdt_doc, doc_uuid, container)

        with nicegui_user:
            _refresh_annotation_cards(state)

        # Simulate expanding card 1 by clicking its header row
        card1 = state.annotation_cards[hl1]
        header_row = next(
            c for c in card1.default_slot.children if isinstance(c, ui.row)
        )
        _fire_event_listeners(header_row, "click")

        # Card 1 detail should now be populated
        children1 = _find_detail_children(container, hl1)
        assert len(children1) > 0, "AC1.2: expanded card detail should have children"
        assert hl1 in state.detail_built_cards

        # Card 2 detail should still be empty
        children2 = _find_detail_children(container, hl2)
        assert len(children2) == 0, "AC1.2: unexpanded card detail should be empty"
        assert hl2 not in state.detail_built_cards

    @pytest.mark.asyncio
    async def test_pre_expanded_cards_build_detail_eagerly(
        self, nicegui_user: User
    ) -> None:
        """AC1.3: cards in expanded_cards have detail built eagerly."""
        from nicegui import ui

        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.pages.annotation.cards import _refresh_annotation_cards

        await nicegui_user.open("/")

        doc_uuid = uuid4()
        doc_id = str(doc_uuid)
        crdt_doc = AnnotationDocument("test-lazy-ac13")
        hl1 = crdt_doc.add_highlight(10, 20, "tag_a", "Alice", "u1", document_id=doc_id)
        hl2 = crdt_doc.add_highlight(30, 40, "tag_b", "Bob", "u2", document_id=doc_id)

        with nicegui_user:
            container = ui.column()
        state = _make_test_state(crdt_doc, doc_uuid, container)

        # Pre-expand card 1
        state.expanded_cards.add(hl1)

        with nicegui_user:
            _refresh_annotation_cards(state)

        # Card 1: visible + populated
        detail1 = _find_detail_element(container, hl1)
        assert detail1 is not None
        assert detail1.visible, "AC1.3: pre-expanded card-detail should be visible"
        children1 = _find_detail_children(container, hl1)
        assert len(children1) > 0, (
            "AC1.3: pre-expanded card detail should have children"
        )
        assert hl1 in state.detail_built_cards

        # Card 2: hidden + empty
        detail2 = _find_detail_element(container, hl2)
        assert detail2 is not None
        assert not detail2.visible
        children2 = _find_detail_children(container, hl2)
        assert len(children2) == 0, "AC1.3: collapsed card detail should still be empty"

    @pytest.mark.asyncio
    async def test_diff_update_rebuilds_expanded_detail(
        self, nicegui_user: User
    ) -> None:
        """AC1.4: diff-update path rebuilds expanded card with detail."""
        from nicegui import ui

        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.pages.annotation.cards import _refresh_annotation_cards

        await nicegui_user.open("/")

        doc_uuid = uuid4()
        doc_id = str(doc_uuid)
        crdt_doc = AnnotationDocument("test-lazy-ac14-diff")
        hl1 = crdt_doc.add_highlight(10, 20, "tag_a", "Alice", "u1", document_id=doc_id)
        hl2 = crdt_doc.add_highlight(30, 40, "tag_b", "Bob", "u2", document_id=doc_id)

        with nicegui_user:
            container = ui.column()
        state = _make_test_state(crdt_doc, doc_uuid, container)

        # Pre-expand hl1
        state.expanded_cards.add(hl1)

        # Full build
        with nicegui_user:
            _refresh_annotation_cards(state)

        assert hl1 in state.detail_built_cards
        children1_before = _find_detail_children(container, hl1)
        assert len(children1_before) > 0

        # Mutate CRDT: add a comment to hl1 (changes snapshot)
        crdt_doc.add_comment(hl1, "A test comment", "Alice", "u1")

        # Diff path
        with nicegui_user:
            _refresh_annotation_cards(state)

        # hl1 was in expanded_cards, so the rebuilt card should have
        # detail eagerly populated
        assert hl1 in state.detail_built_cards
        detail1 = _find_detail_element(container, hl1)
        assert detail1 is not None
        assert detail1.visible, "Rebuilt expanded card should be visible"
        children1_after = _find_detail_children(container, hl1)
        assert len(children1_after) > 0, (
            "AC1.4: rebuilt expanded card should have detail populated"
        )

        # hl2 should still be lazy
        assert hl2 not in state.detail_built_cards
        children2 = _find_detail_children(container, hl2)
        assert len(children2) == 0

    @pytest.mark.asyncio
    async def test_diff_remove_cleans_up_detail_tracking(
        self, nicegui_user: User
    ) -> None:
        """AC1.4: removing a card cleans up detail_built_cards."""
        from nicegui import ui

        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.pages.annotation.cards import _refresh_annotation_cards

        await nicegui_user.open("/")

        doc_uuid = uuid4()
        doc_id = str(doc_uuid)
        crdt_doc = AnnotationDocument("test-lazy-ac14-rm")
        hl1 = crdt_doc.add_highlight(10, 20, "tag_a", "Alice", "u1", document_id=doc_id)
        crdt_doc.add_highlight(30, 40, "tag_b", "Bob", "u2", document_id=doc_id)

        with nicegui_user:
            container = ui.column()
        state = _make_test_state(crdt_doc, doc_uuid, container)
        state.expanded_cards.add(hl1)

        # Full build
        with nicegui_user:
            _refresh_annotation_cards(state)
        assert hl1 in state.detail_built_cards

        # Remove hl1 from CRDT
        crdt_doc.remove_highlight(hl1)

        # Diff path
        with nicegui_user:
            _refresh_annotation_cards(state)

        assert hl1 not in state.detail_built_cards
        assert hl1 not in state.expanded_cards

    @pytest.mark.asyncio
    async def test_full_rebuild_resets_detail_tracking(
        self, nicegui_user: User
    ) -> None:
        """AC1.4: invalidate_card_cache + refresh resets detail_built_cards."""
        from nicegui import ui

        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.pages.annotation.cards import _refresh_annotation_cards

        await nicegui_user.open("/")

        doc_uuid = uuid4()
        doc_id = str(doc_uuid)
        crdt_doc = AnnotationDocument("test-lazy-ac14-full")
        hl1 = crdt_doc.add_highlight(10, 20, "tag_a", "Alice", "u1", document_id=doc_id)
        hl2 = crdt_doc.add_highlight(30, 40, "tag_b", "Bob", "u2", document_id=doc_id)

        with nicegui_user:
            container = ui.column()
        state = _make_test_state(crdt_doc, doc_uuid, container)
        state.expanded_cards.add(hl1)

        # Full build
        with nicegui_user:
            _refresh_annotation_cards(state)
        assert hl1 in state.detail_built_cards

        # Invalidate + rebuild
        state.invalidate_card_cache()
        assert len(state.detail_built_cards) == 0, (
            "invalidate_card_cache should clear detail_built_cards"
        )

        # Rebuild (full path since annotation_cards is None)
        with nicegui_user:
            _refresh_annotation_cards(state)

        # hl1 is still in expanded_cards, so it should be rebuilt eagerly
        assert hl1 in state.detail_built_cards
        children1 = _find_detail_children(container, hl1)
        assert len(children1) > 0, (
            "AC1.4: after full rebuild, expanded card should have detail"
        )

        # hl2 should remain lazy
        assert hl2 not in state.detail_built_cards
        children2 = _find_detail_children(container, hl2)
        assert len(children2) == 0
