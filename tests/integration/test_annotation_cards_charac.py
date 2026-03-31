"""NiceGUI integration tests for Annotate tab card rendering.

Characterisation tests that lock down existing annotation card behaviour
before refactoring in Phases 2-6. Tests exercise the card rendering
pipeline: CRDT highlights -> cards.py -> DOM.

Verifies: None (characterisation -- locks down existing behaviour)

Traceability:
- Plan: phase_01.md Task 3 (multi-doc-tabs-186-plan-a)
- Protects: AC11 (Card Consistency), AC12 (Diff-Based Updates)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import pytest

from promptgrimoire.config import get_settings
from tests.integration.conftest import _authenticate
from tests.integration.nicegui_helpers import (
    _find_all_by_testid,
    _find_html_testid_texts,
    _fire_event_listeners,
    _should_see_testid,
    wait_for,
    wait_for_annotation_load,
)

if TYPE_CHECKING:
    from nicegui.testing.user import User

pytestmark = [
    pytest.mark.skipif(
        not get_settings().dev.test_database_url,
        reason="DEV__TEST_DATABASE_URL not configured",
    ),
    pytest.mark.nicegui_ui,
]


# ---------------------------------------------------------------------------
# DB + CRDT helpers
# ---------------------------------------------------------------------------


async def _create_course() -> tuple[UUID, str]:
    """Create a course with a unique code."""
    from promptgrimoire.db.courses import create_course

    uid = uuid4().hex[:8]
    code = f"ANN{uid.upper()}"
    course = await create_course(
        code=code,
        name=f"Annotation Card Test {uid}",
        semester="2026-S1",
    )
    return course.id, code


async def _enroll(course_id: UUID, email: str, role: str) -> UUID:
    """Ensure user exists and enroll. Returns user_id."""
    from promptgrimoire.db.courses import enroll_user
    from promptgrimoire.db.users import find_or_create_user

    user_record, _ = await find_or_create_user(
        email=email,
        display_name=email.split("@", maxsplit=1)[0],
    )
    await enroll_user(
        course_id=course_id,
        user_id=user_record.id,
        role=role,
    )
    return user_record.id


async def _create_week(course_id: UUID) -> UUID:
    from promptgrimoire.db.weeks import create_week

    week = await create_week(
        course_id=course_id,
        week_number=1,
        title="Test Week",
    )
    return week.id


async def _create_activity(
    week_id: UUID,
) -> tuple[UUID, UUID]:
    """Returns (activity_id, template_workspace_id)."""
    from promptgrimoire.db.activities import create_activity

    activity = await create_activity(week_id=week_id, title="Card Test Activity")
    return activity.id, activity.template_workspace_id


async def _setup_template_tags(
    template_ws_id: UUID,
) -> tuple[str, str]:
    """Create tags on the template workspace (DB + CRDT).

    Returns (tag_1_id_str, tag_2_id_str) for use in highlights.
    """
    from promptgrimoire.db.tags import create_tag

    tag1 = await create_tag(template_ws_id, "Jurisdiction", "#1f77b4")
    tag2 = await create_tag(template_ws_id, "Evidence", "#ff7f0e")
    return str(tag1.id), str(tag2.id)


async def _add_template_document(
    workspace_id: UUID,
) -> UUID:
    """Add a source document to the template workspace."""
    from promptgrimoire.db.workspace_documents import (
        add_document,
    )

    doc = await add_document(
        workspace_id=workspace_id,
        type="source",
        content=(
            "<p>Sample document text for testing "
            "annotation cards with enough content.</p>"
        ),
        source_type="paste",
        title="Test Document",
    )
    return doc.id


async def _clone_workspace(
    activity_id: UUID, user_id: UUID
) -> tuple[UUID, dict[UUID, UUID]]:
    """Clone template workspace for student.

    Returns (workspace_id, doc_id_map).
    """
    from promptgrimoire.db.workspaces import (
        clone_workspace_from_activity,
    )

    ws, doc_map = await clone_workspace_from_activity(activity_id, user_id)
    return ws.id, doc_map


async def _add_highlights_to_workspace(
    workspace_id: UUID,
    document_id: UUID,
    user_id: str,
    user_name: str = "Test User",
) -> None:
    """Add test highlights to workspace CRDT and persist.

    Creates:
    - HL1: start_char=10, short text, tag=Jurisdiction, 1 comment
    - HL2: start_char=50, long text (>80 chars), tag=Evidence
    - HL3: start_char=30, medium text, tag=Jurisdiction
    """
    from promptgrimoire.crdt.annotation_doc import (
        AnnotationDocumentRegistry,
    )
    from promptgrimoire.db.workspaces import (
        save_workspace_crdt_state,
    )

    # Load existing CRDT state (has tags from clone)
    registry = AnnotationDocumentRegistry()
    doc = await registry.get_or_create_for_workspace(workspace_id)

    # Find the cloned tag IDs by matching names
    tags = doc.list_tags()
    cloned_tag_1 = None
    cloned_tag_2 = None
    for tid, tdata in tags.items():
        if tdata["name"] == "Jurisdiction":
            cloned_tag_1 = tid
        elif tdata["name"] == "Evidence":
            cloned_tag_2 = tid

    assert cloned_tag_1 is not None, "Jurisdiction tag not found in cloned CRDT"
    assert cloned_tag_2 is not None, "Evidence tag not found in cloned CRDT"

    # HL1: short text, with comment
    hl1_id = doc.add_highlight(
        start_char=10,
        end_char=20,
        tag=cloned_tag_1,
        text="short text",
        author=user_name,
        document_id=str(document_id),
        user_id=user_id,
    )
    doc.add_comment(hl1_id, user_name, "First comment", user_id=user_id)

    # HL2: long text (>80 chars), no comments
    long_text = "A" * 120
    doc.add_highlight(
        start_char=50,
        end_char=170,
        tag=cloned_tag_2,
        text=long_text,
        author=user_name,
        document_id=str(document_id),
        user_id=user_id,
    )

    # HL3: middle position
    doc.add_highlight(
        start_char=30,
        end_char=42,
        tag=cloned_tag_1,
        text="middle text",
        author=user_name,
        document_id=str(document_id),
        user_id=user_id,
    )

    await save_workspace_crdt_state(workspace_id, doc.get_full_state())


async def _setup_workspace_with_highlights(
    email: str = "student@test.example.edu.au",
) -> tuple[UUID, UUID, str]:
    """Full setup: course > activity > tags > clone > highlights.

    Returns (workspace_id, document_id, user_id_str).
    """
    course_id, _ = await _create_course()
    await _enroll(course_id, "coordinator@uni.edu", "coordinator")
    user_id = await _enroll(course_id, email, "student")

    week_id = await _create_week(course_id)
    from promptgrimoire.db.weeks import publish_week

    await publish_week(week_id)

    activity_id, template_ws_id = await _create_activity(week_id)

    # Create tags and document on template BEFORE cloning
    _tag_1_id, _tag_2_id = await _setup_template_tags(template_ws_id)
    template_doc_id = await _add_template_document(template_ws_id)

    # Clone inherits tags + document
    ws_id, doc_map = await _clone_workspace(activity_id, user_id)

    # Map template doc ID to cloned doc ID
    cloned_doc_id = doc_map.get(template_doc_id, template_doc_id)

    # Add highlights using cloned tag IDs
    await _add_highlights_to_workspace(
        ws_id,
        cloned_doc_id,
        str(user_id),
        user_name=email.split("@", maxsplit=1)[0],
    )

    return ws_id, cloned_doc_id, str(user_id)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAnnotateCardRendering:
    """Characterisation tests for Annotate tab card rendering."""

    @pytest.mark.asyncio
    async def test_cards_rendered_for_highlights(self, nicegui_user: User) -> None:
        """Each highlight produces an annotation-card element."""
        email = "student@test.example.edu.au"
        ws_id, _, _ = await _setup_workspace_with_highlights(email=email)

        await _authenticate(nicegui_user, email=email)
        await nicegui_user.open(f"/annotation?workspace_id={ws_id}")
        await wait_for_annotation_load(nicegui_user)
        await _should_see_testid(nicegui_user, "annotation-card")

        cards = _find_all_by_testid(nicegui_user, "annotation-card")
        assert len(cards) == 3, f"Expected 3 annotation cards, got {len(cards)}"

    @pytest.mark.asyncio
    async def test_cards_ordered_by_start_char(self, nicegui_user: User) -> None:
        """Cards are ordered by start_char (ascending)."""
        email = "student-order@test.example.edu.au"
        ws_id, _, _ = await _setup_workspace_with_highlights(email=email)

        await _authenticate(nicegui_user, email=email)
        await nicegui_user.open(f"/annotation?workspace_id={ws_id}")
        await wait_for_annotation_load(nicegui_user)
        await _should_see_testid(nicegui_user, "annotation-card")

        cards = _find_all_by_testid(nicegui_user, "annotation-card")
        start_chars = [int(float(c.props.get("data-start-char", "0"))) for c in cards]
        assert start_chars == sorted(start_chars), (
            f"Cards not sorted by start_char: {start_chars}"
        )
        # First card should be start_char=10
        assert start_chars[0] == 10

    @pytest.mark.asyncio
    async def test_expandable_text_truncated(self, nicegui_user: User) -> None:
        """Long highlight text (>80 chars) is truncated."""
        email = "student-expand@test.example.edu.au"
        ws_id, _, _ = await _setup_workspace_with_highlights(email=email)

        await _authenticate(nicegui_user, email=email)
        await nicegui_user.open(f"/annotation?workspace_id={ws_id}")
        await wait_for_annotation_load(nicegui_user)
        await _should_see_testid(nicegui_user, "annotation-card")

        # Find the card with the long text (start_char=50)
        cards = _find_all_by_testid(nicegui_user, "annotation-card")
        long_card = next(
            c for c in cards if int(float(c.props.get("data-start-char", "0"))) == 50
        )

        # Expand the card by clicking the header row
        from nicegui import ui

        header = next(child for child in long_card if isinstance(child, ui.row))
        _fire_event_listeners(header, "click")

        # Wait until a descendant with truncated text is visible.
        # Pin the exact 80-char boundary from cards.py _build_expandable_text:
        # full_text[:80] + "..." wrapped in quotes gives 85 chars total.
        expected_truncated = '"' + "A" * 80 + '..."'

        def _has_truncated_text() -> bool:
            for desc in long_card.descendants():
                if not hasattr(desc, "text"):
                    continue
                text_val = str(getattr(desc, "text", ""))
                if text_val == expected_truncated:
                    return True
            return False

        await wait_for(_has_truncated_text, timeout=2.0)
        assert _has_truncated_text(), (
            f"Expected exact truncated text at 80-char boundary: {expected_truncated!r}"
        )

    @pytest.mark.asyncio
    async def test_comment_count_badge(self, nicegui_user: User) -> None:
        """Comment count badge visible when comments exist."""
        email = "student-badge@test.example.edu.au"
        ws_id, _, _ = await _setup_workspace_with_highlights(email=email)

        await _authenticate(nicegui_user, email=email)
        await nicegui_user.open(f"/annotation?workspace_id={ws_id}")
        await wait_for_annotation_load(nicegui_user)
        await _should_see_testid(nicegui_user, "annotation-card")

        # Comment count is inside ui.html() raw HTML (Phase 2, #457)
        badge_texts = _find_html_testid_texts(nicegui_user, "comment-count")
        # HL1 has 1 comment => badge "1"
        assert len(badge_texts) >= 1, "Expected at least 1 comment count badge"
        assert "1" in badge_texts, f"Expected badge '1', got {badge_texts}"

    @pytest.mark.asyncio
    async def test_locate_button_present(self, nicegui_user: User) -> None:
        """Each card has a locate button (icon=my_location)."""
        email = "student-locate@test.example.edu.au"
        ws_id, _, _ = await _setup_workspace_with_highlights(email=email)

        await _authenticate(nicegui_user, email=email)
        await nicegui_user.open(f"/annotation?workspace_id={ws_id}")
        await wait_for_annotation_load(nicegui_user)
        await _should_see_testid(nicegui_user, "annotation-card")

        cards = _find_all_by_testid(nicegui_user, "annotation-card")
        for card in cards:
            found_locate = any(
                desc.props.get("icon") == "my_location"
                for desc in card.descendants()
                if hasattr(desc, "_props")
            )
            assert found_locate, (
                f"Card start_char="
                f"{card.props.get('data-start-char')} "
                "missing locate button"
            )

    @pytest.mark.asyncio
    async def test_expand_button_present(self, nicegui_user: User) -> None:
        """Each card has an expand/collapse chevron button."""
        email = "student-chevron@test.example.edu.au"
        ws_id, _, _ = await _setup_workspace_with_highlights(email=email)

        await _authenticate(nicegui_user, email=email)
        await nicegui_user.open(f"/annotation?workspace_id={ws_id}")
        await wait_for_annotation_load(nicegui_user)
        await _should_see_testid(nicegui_user, "annotation-card")

        expand_btns = _find_all_by_testid(nicegui_user, "card-expand-btn")
        cards = _find_all_by_testid(nicegui_user, "annotation-card")
        assert len(expand_btns) == len(cards), (
            f"Expected {len(cards)} expand buttons, got {len(expand_btns)}"
        )

    @pytest.mark.asyncio
    async def test_detail_hidden_by_default(self, nicegui_user: User) -> None:
        """Card detail section is hidden (collapsed) by default."""
        email = "student-detail@test.example.edu.au"
        ws_id, _, _ = await _setup_workspace_with_highlights(email=email)

        await _authenticate(nicegui_user, email=email)
        await nicegui_user.open(f"/annotation?workspace_id={ws_id}")
        await wait_for_annotation_load(nicegui_user)
        await _should_see_testid(nicegui_user, "annotation-card")

        # card-detail elements exist but are not visible
        from nicegui import ElementFilter

        with nicegui_user:
            detail_elements = [
                el
                for el in ElementFilter()
                if el.props.get("data-testid") == "card-detail"
            ]
        assert len(detail_elements) == 3, (
            f"Expected 3 card-detail elements, got {len(detail_elements)}"
        )
        for el in detail_elements:
            assert not el.visible, "card-detail should be hidden by default"

    # NOTE: cards_epoch characterisation was removed after Codex audit
    # round 2 identified it as fragile (closure extraction from
    # _build_annotation_card internals, flaky under xdist). The NiceGUI
    # User harness has no real browser, so window.__annotationCardsEpoch
    # (the public contract) is untestable at this layer. Phase 5 E2E
    # tests will cover the epoch mechanism via Playwright's
    # wait_for_function("() => window.__annotationCardsEpoch >= N").


# ---------------------------------------------------------------------------
# Diff-based card update tests (AC12)
#
# These tests exercise _diff_annotation_cards() directly by calling
# _refresh_annotation_cards() twice: first with annotation_cards=None
# (full build), then after CRDT mutation (diff path).  This verifies
# the diff algorithm itself, not just the full-build rendering.
# ---------------------------------------------------------------------------


def _make_diff_test_state(
    crdt_doc: Any,
    document_id: UUID,
    container: Any,
) -> Any:
    """Create a minimal PageState for diff-path testing.

    Uses ``effective_permission="viewer"`` so ``can_annotate=False``,
    avoiding the tag ``ui.select`` which requires valid tag options.
    The diff algorithm doesn't depend on annotation capability.
    """
    from promptgrimoire.pages.annotation import PageState

    state = PageState(
        workspace_id=uuid4(),
        effective_permission="viewer",
        user_name="DiffTest",
        user_id="diff-test-user",
    )
    state.crdt_doc = crdt_doc
    state.document_id = document_id
    state.annotations_container = container
    state.tag_info_list = []
    return state


def _card_start_chars(state: Any) -> list[int]:
    """Extract start_char values from annotation_cards in container order.

    Reads the ``data-start-char`` prop from each card in the
    container's slot children (preserves DOM insertion order).
    """
    assert state.annotations_container is not None
    result = []
    for child in state.annotations_container.default_slot.children:
        sc = child.props.get("data-start-char")
        if sc is not None:
            result.append(int(float(sc)))
    return result


class TestDiffBasedCardUpdates:
    """Tests that exercise the _diff_annotation_cards diff path directly.

    Each test:
    1. Creates a CRDT doc with initial highlights
    2. Calls _refresh_annotation_cards (full build — annotation_cards=None)
    3. Mutates the CRDT
    4. Calls _refresh_annotation_cards again (diff path — annotation_cards populated)
    5. Asserts on the result

    Traceability:
    - AC12.1: Adding a highlight inserts one card via diff
    - AC12.2: Removing a highlight deletes one card via diff
    - AC12.3: Multiple cards inserted at correct positions via diff
    """

    @pytest.mark.asyncio
    async def test_diff_add_inserts_one_card(self, nicegui_user: User) -> None:
        """AC12.1: diff path adds one card when CRDT gains a highlight."""
        from nicegui import ui

        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.pages.annotation.cards import _refresh_annotation_cards

        await nicegui_user.open("/")

        doc_uuid = uuid4()
        doc_id = str(doc_uuid)
        crdt_doc = AnnotationDocument("test-diff-add")
        crdt_doc.add_highlight(10, 20, "t", "first", "u", document_id=doc_id)
        crdt_doc.add_highlight(50, 60, "t", "second", "u", document_id=doc_id)

        with nicegui_user:
            container = ui.column()
        state = _make_diff_test_state(crdt_doc, doc_uuid, container)

        # Full build
        with nicegui_user:
            _refresh_annotation_cards(state)
        assert state.annotation_cards is not None
        assert len(state.annotation_cards) == 2

        # Mutate CRDT: add a third highlight
        crdt_doc.add_highlight(30, 40, "t", "third", "u", document_id=doc_id)

        # Diff path
        with nicegui_user:
            _refresh_annotation_cards(state)
        assert len(state.annotation_cards) == 3

    @pytest.mark.asyncio
    async def test_diff_remove_deletes_one_card(self, nicegui_user: User) -> None:
        """AC12.2: diff path removes card when CRDT loses a highlight."""
        from nicegui import ui

        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.pages.annotation.cards import _refresh_annotation_cards

        await nicegui_user.open("/")

        doc_uuid = uuid4()
        doc_id = str(doc_uuid)
        crdt_doc = AnnotationDocument("test-diff-rm")
        hl1 = crdt_doc.add_highlight(10, 20, "t", "first", "u", document_id=doc_id)
        crdt_doc.add_highlight(30, 40, "t", "second", "u", document_id=doc_id)
        crdt_doc.add_highlight(50, 60, "t", "third", "u", document_id=doc_id)

        with nicegui_user:
            container = ui.column()
        state = _make_diff_test_state(crdt_doc, doc_uuid, container)

        # Full build
        with nicegui_user:
            _refresh_annotation_cards(state)
        assert len(state.annotation_cards) == 3

        # Mutate CRDT: remove the first highlight
        crdt_doc.remove_highlight(hl1)

        # Diff path
        with nicegui_user:
            _refresh_annotation_cards(state)
        assert len(state.annotation_cards) == 2
        assert hl1 not in state.annotation_cards
        assert _card_start_chars(state) == [30, 50]

    @pytest.mark.asyncio
    async def test_diff_multi_add_correct_order(self, nicegui_user: User) -> None:
        """AC12.3: multiple cards added via diff land in start_char order."""
        from nicegui import ui

        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.pages.annotation.cards import _refresh_annotation_cards

        await nicegui_user.open("/")

        doc_uuid = uuid4()
        doc_id = str(doc_uuid)
        crdt_doc = AnnotationDocument("test-diff-order")
        crdt_doc.add_highlight(10, 20, "t", "first", "u", document_id=doc_id)
        crdt_doc.add_highlight(50, 60, "t", "last", "u", document_id=doc_id)

        with nicegui_user:
            container = ui.column()
        state = _make_diff_test_state(crdt_doc, doc_uuid, container)

        # Full build: 2 cards at [10, 50]
        with nicegui_user:
            _refresh_annotation_cards(state)
        assert _card_start_chars(state) == [10, 50]

        # Mutate CRDT: add two highlights between existing ones
        crdt_doc.add_highlight(25, 30, "t", "mid1", "u", document_id=doc_id)
        crdt_doc.add_highlight(35, 40, "t", "mid2", "u", document_id=doc_id)

        # Diff path: should insert both in correct positions
        with nicegui_user:
            _refresh_annotation_cards(state)
        assert len(state.annotation_cards) == 4
        assert _card_start_chars(state) == [10, 25, 35, 50]

    @pytest.mark.asyncio
    async def test_diff_tag_change_rebuilds_card(self, nicegui_user: User) -> None:
        """AC12.4: tag change on one highlight rebuilds only that card."""
        from nicegui import ui

        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.pages.annotation.cards import _refresh_annotation_cards

        await nicegui_user.open("/")

        doc_uuid = uuid4()
        doc_id = str(doc_uuid)
        crdt_doc = AnnotationDocument("test-diff-tag")
        hl1 = crdt_doc.add_highlight(10, 20, "old_tag", "text", "u", document_id=doc_id)
        hl2 = crdt_doc.add_highlight(
            50, 60, "old_tag", "text2", "u", document_id=doc_id
        )

        with nicegui_user:
            container = ui.column()
        state = _make_diff_test_state(crdt_doc, doc_uuid, container)

        # Full build
        with nicegui_user:
            _refresh_annotation_cards(state)
        card1_before = state.annotation_cards[hl1]
        card2_before = state.annotation_cards[hl2]

        # Change tag on hl1 only
        crdt_doc.update_highlight_tag(hl1, "new_tag")

        # Diff path
        with nicegui_user:
            _refresh_annotation_cards(state)

        # hl1's card should be a NEW object (rebuilt)
        assert state.annotation_cards[hl1] is not card1_before
        # hl2's card should be the SAME object (untouched)
        assert state.annotation_cards[hl2] is card2_before

    @pytest.mark.asyncio
    async def test_diff_preserves_expanded_state(self, nicegui_user: User) -> None:
        """AC12.4: expansion state survives diff-based card rebuild."""
        from nicegui import ui

        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.pages.annotation.cards import _refresh_annotation_cards

        await nicegui_user.open("/")

        doc_uuid = uuid4()
        doc_id = str(doc_uuid)
        crdt_doc = AnnotationDocument("test-diff-expand")
        hl1 = crdt_doc.add_highlight(10, 20, "t", "text", "u", document_id=doc_id)

        with nicegui_user:
            container = ui.column()
        state = _make_diff_test_state(crdt_doc, doc_uuid, container)

        # Full build
        with nicegui_user:
            _refresh_annotation_cards(state)

        # Mark hl1 as expanded
        state.expanded_cards.add(hl1)

        # Mutate: add a new highlight (triggers diff)
        crdt_doc.add_highlight(50, 60, "t", "new", "u", document_id=doc_id)

        with nicegui_user:
            _refresh_annotation_cards(state)

        # hl1 should still be in expanded_cards
        assert hl1 in state.expanded_cards

    @pytest.mark.asyncio
    async def test_invalidate_card_cache_forces_full_rebuild(
        self, nicegui_user: User
    ) -> None:
        """invalidate_card_cache forces full rebuild on next refresh."""
        from nicegui import ui

        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.pages.annotation.cards import _refresh_annotation_cards

        await nicegui_user.open("/")

        doc_uuid = uuid4()
        doc_id = str(doc_uuid)
        crdt_doc = AnnotationDocument("test-invalidate")
        hl1 = crdt_doc.add_highlight(10, 20, "t", "text", "u", document_id=doc_id)

        with nicegui_user:
            container = ui.column()
        state = _make_diff_test_state(crdt_doc, doc_uuid, container)

        # Full build
        with nicegui_user:
            _refresh_annotation_cards(state)
        card_before = state.annotation_cards[hl1]

        # Invalidate cache (simulates tag metadata change)
        state.invalidate_card_cache()
        assert state.annotation_cards is None

        # Next refresh does full build — card is a NEW object
        with nicegui_user:
            _refresh_annotation_cards(state)
        assert state.annotation_cards is not None
        assert state.annotation_cards[hl1] is not card_before


# ---------------------------------------------------------------------------
# Guard: refresh_annotations targets correct container after tab switch
# ---------------------------------------------------------------------------


class TestRefreshAfterTabSwitch:
    """Guard test: refresh_annotations must target the restored container.

    If someone refactors the refresh_annotations closure to capture
    the container at creation time instead of reading
    state.annotations_container dynamically, this test will fail.
    """

    @pytest.mark.asyncio
    async def test_refresh_targets_restored_container(self, nicegui_user: User) -> None:
        """After save(A)/restore(B), refresh builds cards in B's container."""
        from nicegui import ui

        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.pages.annotation.cards import _refresh_annotation_cards
        from promptgrimoire.pages.annotation.tab_bar import (
            _restore_source_tab_state,
            _save_source_tab_state,
        )
        from promptgrimoire.pages.annotation.tab_state import DocumentTabState

        await nicegui_user.open("/")

        doc_a = uuid4()
        doc_b = uuid4()
        crdt = AnnotationDocument("test-tab-switch")
        crdt.add_highlight(10, 20, "t", "a1", "u", document_id=str(doc_a))
        crdt.add_highlight(50, 60, "t", "b1", "u", document_id=str(doc_b))
        crdt.add_highlight(70, 80, "t", "b2", "u", document_id=str(doc_b))

        with nicegui_user:
            container_a = ui.column()
            container_b = ui.column()

        state = _make_diff_test_state(crdt, doc_a, container_a)

        tab_a = DocumentTabState(document_id=doc_a, tab=None, panel=None)
        tab_b = DocumentTabState(document_id=doc_b, tab=None, panel=None)
        tab_a.cards_container = container_a
        tab_b.cards_container = container_b
        state.document_tabs = {doc_a: tab_a, doc_b: tab_b}

        # Build doc A (1 highlight)
        with nicegui_user:
            _refresh_annotation_cards(state)
        assert len(state.annotation_cards) == 1
        tab_a.rendered = True
        _save_source_tab_state(state, tab_a)

        # Switch to doc B
        _restore_source_tab_state(state, tab_b)
        assert state.annotations_container is container_b

        # Set up refresh_annotations as document.py does
        def refresh_annotations() -> None:
            _refresh_annotation_cards(state)

        state.refresh_annotations = refresh_annotations

        # Build doc B (2 highlights)
        with nicegui_user:
            state.refresh_annotations()
        assert len(state.annotation_cards) == 2

        # Save B, restore A
        tab_b.rendered = True
        _save_source_tab_state(state, tab_b)
        _restore_source_tab_state(state, tab_a)

        # Refresh — must target A's container and show 1 card
        with nicegui_user:
            state.refresh_annotations()
        assert len(state.annotation_cards) == 1


# ---------------------------------------------------------------------------
# Unit tests for _snapshot_highlight (pure function)
# ---------------------------------------------------------------------------


# NOTE: TestSnapshotHighlight (pure-function unit tests for _snapshot_highlight)
# moved to tests/unit/test_snapshot_highlight.py to prevent import-poisoning of
# the NiceGUI user_simulation fixture.  See that file's docstring for details.


# ---------------------------------------------------------------------------
# Integration tests for tag/comment change detection (AC12.4)
# ---------------------------------------------------------------------------


class TestDiffChangedHighlights:
    """Characterisation tests: card rendering reflects CRDT mutations.

    NOTE: These tests mutate CRDT state before page navigation, so they
    exercise the full-build path only.  The actual diff path is tested
    in ``TestDiffBasedCardUpdates`` above.

    Traceability:
    - AC12.4 (full-build rendering): tag/comment changes visible in
      rendered cards
    """

    @pytest.mark.asyncio
    async def test_tag_change_reflected_in_card_colour(
        self, nicegui_user: User
    ) -> None:
        """AC12.4: Changing a highlight tag renders with the new tag colour."""
        email = "student-tag-change@test.example.edu.au"
        ws_id, doc_id, _user_id = await _setup_workspace_with_highlights(email=email)

        # Mutate HL1 (start_char=10) tag from Jurisdiction to Evidence before nav
        from promptgrimoire.crdt.annotation_doc import AnnotationDocumentRegistry
        from promptgrimoire.db.workspaces import save_workspace_crdt_state

        registry = AnnotationDocumentRegistry()
        crdt_doc = await registry.get_or_create_for_workspace(ws_id)
        highlights = crdt_doc.get_highlights_for_document(str(doc_id))
        hl1 = next(h for h in highlights if h.get("start_char") == 10)

        # Find Evidence tag ID
        tags = crdt_doc.list_tags()
        evidence_tag_id = next(
            tid for tid, tdata in tags.items() if tdata["name"] == "Evidence"
        )

        crdt_doc.update_highlight_tag(hl1["id"], evidence_tag_id)
        await save_workspace_crdt_state(ws_id, crdt_doc.get_full_state())

        await _authenticate(nicegui_user, email=email)
        await nicegui_user.open(f"/annotation?workspace_id={ws_id}")
        await wait_for_annotation_load(nicegui_user)
        await _should_see_testid(nicegui_user, "annotation-card")

        # The card at start_char=10 should now have Evidence colour (#ff7f0e)
        cards = _find_all_by_testid(nicegui_user, "annotation-card")
        hl1_card = next(
            c for c in cards if int(float(c.props.get("data-start-char", "0"))) == 10
        )
        style = hl1_card._style.get("border-left", "")
        assert "#ff7f0e" in style, (
            f"Expected Evidence colour #ff7f0e in border-left, got: {style}"
        )

    @pytest.mark.asyncio
    async def test_comment_addition_reflected_in_badge(
        self, nicegui_user: User
    ) -> None:
        """AC12.4: Adding a comment updates the badge count on that card."""
        email = "student-comment-add@test.example.edu.au"
        ws_id, doc_id, user_id = await _setup_workspace_with_highlights(email=email)

        # Add a second comment to HL1 (start_char=10, already has 1 comment)
        from promptgrimoire.crdt.annotation_doc import AnnotationDocumentRegistry
        from promptgrimoire.db.workspaces import save_workspace_crdt_state

        registry = AnnotationDocumentRegistry()
        crdt_doc = await registry.get_or_create_for_workspace(ws_id)
        highlights = crdt_doc.get_highlights_for_document(str(doc_id))
        hl1 = next(h for h in highlights if h.get("start_char") == 10)

        crdt_doc.add_comment(
            hl1["id"], "student-comment-add", "Second comment", user_id=user_id
        )
        await save_workspace_crdt_state(ws_id, crdt_doc.get_full_state())

        await _authenticate(nicegui_user, email=email)
        await nicegui_user.open(f"/annotation?workspace_id={ws_id}")
        await wait_for_annotation_load(nicegui_user)
        await _should_see_testid(nicegui_user, "annotation-card")

        # The badge on HL1 card should show "2" (inside ui.html, Phase 2 #457)
        badge_texts = _find_html_testid_texts(nicegui_user, "comment-count")
        assert "2" in badge_texts, (
            f"Expected badge '2' after adding comment, got {badge_texts}"
        )

    @pytest.mark.asyncio
    async def test_other_cards_unaffected_by_tag_change(
        self, nicegui_user: User
    ) -> None:
        """AC12.4: Changing tag on one card does not affect other cards."""
        email = "student-unaffected@test.example.edu.au"
        ws_id, doc_id, _user_id = await _setup_workspace_with_highlights(email=email)

        # Change HL1 (start_char=10) tag, leave HL2 (start_char=50) and HL3 alone
        from promptgrimoire.crdt.annotation_doc import AnnotationDocumentRegistry
        from promptgrimoire.db.workspaces import save_workspace_crdt_state

        registry = AnnotationDocumentRegistry()
        crdt_doc = await registry.get_or_create_for_workspace(ws_id)
        highlights = crdt_doc.get_highlights_for_document(str(doc_id))
        hl1 = next(h for h in highlights if h.get("start_char") == 10)

        tags = crdt_doc.list_tags()
        evidence_tag_id = next(
            tid for tid, tdata in tags.items() if tdata["name"] == "Evidence"
        )
        crdt_doc.update_highlight_tag(hl1["id"], evidence_tag_id)
        await save_workspace_crdt_state(ws_id, crdt_doc.get_full_state())

        await _authenticate(nicegui_user, email=email)
        await nicegui_user.open(f"/annotation?workspace_id={ws_id}")
        await wait_for_annotation_load(nicegui_user)
        await _should_see_testid(nicegui_user, "annotation-card")

        # HL2 (start_char=50) should still have Evidence colour
        # HL3 (start_char=30) should still have Jurisdiction colour (#1f77b4)
        cards = _find_all_by_testid(nicegui_user, "annotation-card")
        assert len(cards) == 3, f"Expected 3 cards unchanged, got {len(cards)}"

        hl3_card = next(
            c for c in cards if int(float(c.props.get("data-start-char", "0"))) == 30
        )
        hl3_style = hl3_card._style.get("border-left", "")
        assert "#1f77b4" in hl3_style, (
            f"Expected Jurisdiction colour #1f77b4 on HL3, got: {hl3_style}"
        )


# ---------------------------------------------------------------------------
# Rapid CRDT update tests (AC12.5)
# ---------------------------------------------------------------------------


class TestRapidCRDTUpdates:
    """Characterisation tests: rapid CRDT mutations render correctly.

    NOTE: These tests mutate CRDT state before page navigation, so they
    exercise the full-build path only.  They verify that the final CRDT
    state produces correct rendered output regardless of how many
    intermediate mutations occurred.

    Traceability:
    - AC12.5 (full-build rendering): rapid successive CRDT updates
      produce correct final card state with no duplicates
    """

    @pytest.mark.asyncio
    async def test_rapid_successive_adds_produce_correct_state(
        self, nicegui_user: User
    ) -> None:
        """AC12.5: Adding 3 highlights rapidly produces 6 total cards."""
        email = "student-rapid-add@test.example.edu.au"
        ws_id, doc_id, user_id = await _setup_workspace_with_highlights(email=email)

        from promptgrimoire.crdt.annotation_doc import AnnotationDocumentRegistry
        from promptgrimoire.db.workspaces import save_workspace_crdt_state

        registry = AnnotationDocumentRegistry()
        crdt_doc = await registry.get_or_create_for_workspace(ws_id)
        tags = crdt_doc.list_tags()
        tag_id = next(iter(tags))

        # Add 3 highlights rapidly -- no await between sync operations
        crdt_doc.add_highlight(
            start_char=5,
            end_char=9,
            tag=tag_id,
            text="rapid1",
            author="rapid",
            document_id=str(doc_id),
            user_id=user_id,
        )
        crdt_doc.add_highlight(
            start_char=22,
            end_char=27,
            tag=tag_id,
            text="rapid2",
            author="rapid",
            document_id=str(doc_id),
            user_id=user_id,
        )
        crdt_doc.add_highlight(
            start_char=45,
            end_char=48,
            tag=tag_id,
            text="rapid3",
            author="rapid",
            document_id=str(doc_id),
            user_id=user_id,
        )
        await save_workspace_crdt_state(ws_id, crdt_doc.get_full_state())

        await _authenticate(nicegui_user, email=email)
        await nicegui_user.open(f"/annotation?workspace_id={ws_id}")
        await wait_for_annotation_load(nicegui_user)
        await _should_see_testid(nicegui_user, "annotation-card")

        cards = _find_all_by_testid(nicegui_user, "annotation-card")
        assert len(cards) == 6, (
            f"Expected 6 cards (3 original + 3 rapid adds), got {len(cards)}"
        )

        start_chars = sorted(
            int(float(c.props.get("data-start-char", "0"))) for c in cards
        )
        # All 6 unique start_chars present, no duplicates
        assert start_chars == [5, 10, 22, 30, 45, 50], (
            f"Expected start_chars [5,10,22,30,45,50], got {start_chars}"
        )

    @pytest.mark.asyncio
    async def test_rapid_add_then_immediate_remove(self, nicegui_user: User) -> None:
        """AC12.5: Add then immediately remove leaves original count."""
        email = "student-rapid-rm@test.example.edu.au"
        ws_id, doc_id, user_id = await _setup_workspace_with_highlights(email=email)

        from promptgrimoire.crdt.annotation_doc import AnnotationDocumentRegistry
        from promptgrimoire.db.workspaces import save_workspace_crdt_state

        registry = AnnotationDocumentRegistry()
        crdt_doc = await registry.get_or_create_for_workspace(ws_id)
        tags = crdt_doc.list_tags()
        tag_id = next(iter(tags))

        # Add then immediately remove -- both sync, no yield
        ephemeral_id = crdt_doc.add_highlight(
            start_char=5,
            end_char=9,
            tag=tag_id,
            text="ephemeral",
            author="rapid",
            document_id=str(doc_id),
            user_id=user_id,
        )
        crdt_doc.remove_highlight(ephemeral_id)
        await save_workspace_crdt_state(ws_id, crdt_doc.get_full_state())

        await _authenticate(nicegui_user, email=email)
        await nicegui_user.open(f"/annotation?workspace_id={ws_id}")
        await wait_for_annotation_load(nicegui_user)
        await _should_see_testid(nicegui_user, "annotation-card")

        cards = _find_all_by_testid(nicegui_user, "annotation-card")
        assert len(cards) == 3, (
            f"Expected 3 cards (add+remove should cancel out), got {len(cards)}"
        )

        start_chars = sorted(
            int(float(c.props.get("data-start-char", "0"))) for c in cards
        )
        assert start_chars == [10, 30, 50], (
            f"Expected original start_chars [10, 30, 50], got {start_chars}"
        )

    @pytest.mark.asyncio
    async def test_rapid_tag_changes_reflect_final_value(
        self, nicegui_user: User
    ) -> None:
        """AC12.5: Rapidly changing a tag 3 times renders the final tag value."""
        email = "student-rapid-tag@test.example.edu.au"
        ws_id, doc_id, _user_id = await _setup_workspace_with_highlights(email=email)

        from promptgrimoire.crdt.annotation_doc import AnnotationDocumentRegistry
        from promptgrimoire.db.workspaces import save_workspace_crdt_state

        registry = AnnotationDocumentRegistry()
        crdt_doc = await registry.get_or_create_for_workspace(ws_id)
        highlights = crdt_doc.get_highlights_for_document(str(doc_id))
        hl1 = next(h for h in highlights if h.get("start_char") == 10)

        tags = crdt_doc.list_tags()
        jurisdiction_tag = next(
            tid for tid, tdata in tags.items() if tdata["name"] == "Jurisdiction"
        )
        evidence_tag = next(
            tid for tid, tdata in tags.items() if tdata["name"] == "Evidence"
        )

        # HL1 starts as Jurisdiction. Rapidly toggle 3 times:
        # Jurisdiction -> Evidence -> Jurisdiction -> Evidence (final)
        crdt_doc.update_highlight_tag(hl1["id"], evidence_tag)
        crdt_doc.update_highlight_tag(hl1["id"], jurisdiction_tag)
        crdt_doc.update_highlight_tag(hl1["id"], evidence_tag)
        await save_workspace_crdt_state(ws_id, crdt_doc.get_full_state())

        await _authenticate(nicegui_user, email=email)
        await nicegui_user.open(f"/annotation?workspace_id={ws_id}")
        await wait_for_annotation_load(nicegui_user)
        await _should_see_testid(nicegui_user, "annotation-card")

        cards = _find_all_by_testid(nicegui_user, "annotation-card")
        assert len(cards) == 3, f"Expected 3 cards unchanged, got {len(cards)}"

        hl1_card = next(
            c for c in cards if int(float(c.props.get("data-start-char", "0"))) == 10
        )
        style = hl1_card._style.get("border-left", "")
        assert "#ff7f0e" in style, (
            f"Expected final Evidence colour #ff7f0e in border-left, got: {style}"
        )
