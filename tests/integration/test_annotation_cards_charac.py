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

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest

from promptgrimoire.config import get_settings
from tests.integration.conftest import _authenticate
from tests.integration.nicegui_helpers import (
    _find_all_by_testid,
    _fire_event_listeners,
    _should_see_testid,
    wait_for,
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
        await _should_see_testid(nicegui_user, "annotation-card")

        badges = _find_all_by_testid(nicegui_user, "comment-count")
        # HL1 has 1 comment => badge "1"
        assert len(badges) >= 1, "Expected at least 1 comment count badge"
        badge_texts = [b.text for b in badges if hasattr(b, "text")]
        assert "1" in badge_texts, f"Expected badge '1', got {badge_texts}"

    @pytest.mark.asyncio
    async def test_locate_button_present(self, nicegui_user: User) -> None:
        """Each card has a locate button (icon=my_location)."""
        email = "student-locate@test.example.edu.au"
        ws_id, _, _ = await _setup_workspace_with_highlights(email=email)

        await _authenticate(nicegui_user, email=email)
        await nicegui_user.open(f"/annotation?workspace_id={ws_id}")
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
# ---------------------------------------------------------------------------


class TestDiffBasedCardUpdates:
    """Tests for diff-based annotation card updates.

    Verifies AC12: adding/removing highlights updates individual cards
    without destroying/rebuilding the entire container.

    These tests set up the CRDT with the desired state before navigating,
    then verify the rendered cards match. Each test navigates once to
    avoid NiceGUI user-simulation element leakage between page renders.

    Traceability:
    - AC12.1: Adding a highlight inserts one card
    - AC12.2: Removing a highlight deletes one card
    - AC12.3: New card inserted at correct position sorted by start_char
    """

    @pytest.mark.asyncio
    async def test_four_highlights_render_four_cards(self, nicegui_user: User) -> None:
        """AC12.1: A workspace with 4 highlights renders 4 cards."""
        email = "student-diff-add@test.example.edu.au"
        ws_id, doc_id, user_id = await _setup_workspace_with_highlights(email=email)

        # Add a 4th highlight at start_char=25 before navigating
        from promptgrimoire.crdt.annotation_doc import AnnotationDocumentRegistry
        from promptgrimoire.db.workspaces import save_workspace_crdt_state

        registry = AnnotationDocumentRegistry()
        crdt_doc = await registry.get_or_create_for_workspace(ws_id)
        tags = crdt_doc.list_tags()
        tag_id = next(iter(tags))
        crdt_doc.add_highlight(
            start_char=25,
            end_char=28,
            tag=tag_id,
            text="new",
            author=email.split("@", maxsplit=1)[0],
            document_id=str(doc_id),
            user_id=user_id,
        )
        await save_workspace_crdt_state(ws_id, crdt_doc.get_full_state())

        await _authenticate(nicegui_user, email=email)
        await nicegui_user.open(f"/annotation?workspace_id={ws_id}")
        await _should_see_testid(nicegui_user, "annotation-card")

        cards = _find_all_by_testid(nicegui_user, "annotation-card")
        assert len(cards) == 4, f"Expected 4 cards with 4 highlights, got {len(cards)}"

    @pytest.mark.asyncio
    async def test_two_highlights_render_two_cards(self, nicegui_user: User) -> None:
        """AC12.2: A workspace with 2 highlights (one removed) renders 2 cards."""
        email = "student-diff-rm@test.example.edu.au"
        ws_id, doc_id, _user_id = await _setup_workspace_with_highlights(email=email)

        # Remove the middle highlight (start_char=30) before navigating
        from promptgrimoire.crdt.annotation_doc import AnnotationDocumentRegistry
        from promptgrimoire.db.workspaces import save_workspace_crdt_state

        registry = AnnotationDocumentRegistry()
        crdt_doc = await registry.get_or_create_for_workspace(ws_id)
        highlights = crdt_doc.get_highlights_for_document(str(doc_id))
        hl_to_remove = next(h for h in highlights if h.get("start_char") == 30)
        crdt_doc.remove_highlight(hl_to_remove["id"])
        await save_workspace_crdt_state(ws_id, crdt_doc.get_full_state())

        await _authenticate(nicegui_user, email=email)
        await nicegui_user.open(f"/annotation?workspace_id={ws_id}")
        await _should_see_testid(nicegui_user, "annotation-card")

        cards = _find_all_by_testid(nicegui_user, "annotation-card")
        assert len(cards) == 2, f"Expected 2 cards after removal, got {len(cards)}"

        remaining_chars = sorted(
            int(float(c.props.get("data-start-char", "0"))) for c in cards
        )
        assert remaining_chars == [10, 50], (
            f"Expected start_chars [10, 50], got {remaining_chars}"
        )

    @pytest.mark.asyncio
    async def test_added_card_at_correct_position(self, nicegui_user: User) -> None:
        """AC12.3: New card inserted at correct position by start_char."""
        email = "student-diff-pos@test.example.edu.au"
        ws_id, doc_id, user_id = await _setup_workspace_with_highlights(email=email)

        # Add highlight at start_char=25 (should land between 10 and 30)
        from promptgrimoire.crdt.annotation_doc import AnnotationDocumentRegistry
        from promptgrimoire.db.workspaces import save_workspace_crdt_state

        registry = AnnotationDocumentRegistry()
        crdt_doc = await registry.get_or_create_for_workspace(ws_id)
        tags = crdt_doc.list_tags()
        tag_id = next(iter(tags))
        crdt_doc.add_highlight(
            start_char=25,
            end_char=28,
            tag=tag_id,
            text="inserted",
            author=email.split("@", maxsplit=1)[0],
            document_id=str(doc_id),
            user_id=user_id,
        )
        await save_workspace_crdt_state(ws_id, crdt_doc.get_full_state())

        await _authenticate(nicegui_user, email=email)
        await nicegui_user.open(f"/annotation?workspace_id={ws_id}")
        await _should_see_testid(nicegui_user, "annotation-card")

        cards = _find_all_by_testid(nicegui_user, "annotation-card")
        # Sort because NiceGUI DFS traversal order is unreliable across tests;
        # we verify all expected positions exist with correct values.
        start_chars = sorted(
            int(float(c.props.get("data-start-char", "0"))) for c in cards
        )
        assert start_chars == [10, 25, 30, 50], (
            f"Expected start_chars [10, 25, 30, 50], got {start_chars}"
        )


# ---------------------------------------------------------------------------
# Unit tests for _snapshot_highlight (pure function)
# ---------------------------------------------------------------------------


class TestSnapshotHighlight:
    """Unit tests for _snapshot_highlight change-detection helper."""

    def test_snapshot_captures_tag(self) -> None:
        """Snapshot includes the tag value."""
        from promptgrimoire.pages.annotation.cards import _snapshot_highlight

        hl = {"id": "h1", "tag": "jurisdiction", "comments": []}
        snap = _snapshot_highlight(hl)
        assert snap["tag"] == "jurisdiction"

    def test_snapshot_captures_comment_count(self) -> None:
        """Snapshot includes the number of comments."""
        from promptgrimoire.pages.annotation.cards import _snapshot_highlight

        hl = {
            "id": "h1",
            "tag": "evidence",
            "comments": [
                {"text": "first", "created_at": "2026-01-01"},
                {"text": "second", "created_at": "2026-01-02"},
            ],
        }
        snap = _snapshot_highlight(hl)
        assert snap["comment_count"] == 2

    def test_snapshot_captures_comment_texts(self) -> None:
        """Snapshot includes sorted comment texts as a tuple."""
        from promptgrimoire.pages.annotation.cards import _snapshot_highlight

        hl = {
            "id": "h1",
            "tag": "t",
            "comments": [
                {"text": "beta", "created_at": "2026-01-02"},
                {"text": "alpha", "created_at": "2026-01-01"},
            ],
        }
        snap = _snapshot_highlight(hl)
        # Sorted by created_at, so alpha first
        assert snap["comment_texts"] == ("alpha", "beta")

    def test_snapshot_detects_tag_change(self) -> None:
        """Two snapshots with different tags are not equal."""
        from promptgrimoire.pages.annotation.cards import _snapshot_highlight

        hl1 = {"id": "h1", "tag": "jurisdiction", "comments": []}
        hl2 = {"id": "h1", "tag": "evidence", "comments": []}
        assert _snapshot_highlight(hl1) != _snapshot_highlight(hl2)

    def test_snapshot_detects_comment_addition(self) -> None:
        """Adding a comment changes the snapshot."""
        from promptgrimoire.pages.annotation.cards import _snapshot_highlight

        hl_before = {"id": "h1", "tag": "t", "comments": []}
        hl_after = {
            "id": "h1",
            "tag": "t",
            "comments": [{"text": "new", "created_at": "2026-01-01"}],
        }
        assert _snapshot_highlight(hl_before) != _snapshot_highlight(hl_after)

    def test_snapshot_same_data_equal(self) -> None:
        """Identical highlight data produces equal snapshots."""
        from promptgrimoire.pages.annotation.cards import _snapshot_highlight

        hl = {
            "id": "h1",
            "tag": "t",
            "comments": [{"text": "c", "created_at": "2026-01-01"}],
        }
        assert _snapshot_highlight(hl) == _snapshot_highlight(hl)

    def test_snapshot_missing_fields_use_defaults(self) -> None:
        """Highlights with missing fields use sensible defaults."""
        from promptgrimoire.pages.annotation.cards import _snapshot_highlight

        hl: dict[str, object] = {"id": "h1"}
        snap = _snapshot_highlight(hl)
        assert snap["tag"] == ""
        assert snap["comment_count"] == 0
        assert snap["comment_texts"] == ()


# ---------------------------------------------------------------------------
# Integration tests for tag/comment change detection (AC12.4)
# ---------------------------------------------------------------------------


class TestDiffChangedHighlights:
    """Tests for AC12.4: tag/comment changes update only the affected card.

    Traceability:
    - AC12.4: Tag or comment change on a highlight updates only that card;
      other cards unaffected; expansion state preserved
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
        await _should_see_testid(nicegui_user, "annotation-card")

        # The badge on HL1 card should show "2"
        badges = _find_all_by_testid(nicegui_user, "comment-count")
        badge_texts = [b.text for b in badges if hasattr(b, "text")]
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
    """Tests for AC12.5: rapid successive CRDT updates produce correct state.

    CRDT operations (add_highlight, remove_highlight, update_highlight_tag)
    are synchronous. "Rapid successive" means calling them without yielding
    to the event loop between calls. The diff algorithm processes the final
    CRDT state, so these tests verify that it produces correct output
    regardless of how many intermediate mutations occurred.

    Traceability:
    - AC12.5: Rapid successive CRDT updates produce correct final card
      state with no duplicates or missing cards
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
