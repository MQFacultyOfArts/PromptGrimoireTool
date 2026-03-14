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
