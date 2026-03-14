"""NiceGUI integration tests for Organise tab rendering.

Characterisation tests that lock down existing Organise tab (Tab 2)
card rendering before refactoring in Phases 2-6.

Verifies: None (characterisation -- locks down existing behaviour)

Traceability:
- Plan: phase_01.md Task 4 (multi-doc-tabs-186-plan-a)
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
    _should_see_testid,
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
# DB + CRDT helpers (same pattern as test_annotation_cards_charac)
# ---------------------------------------------------------------------------


async def _create_course() -> tuple[UUID, str]:
    from promptgrimoire.db.courses import create_course

    uid = uuid4().hex[:8]
    code = f"ORG{uid.upper()}"
    course = await create_course(
        code=code,
        name=f"Organise Test {uid}",
        semester="2026-S1",
    )
    return course.id, code


async def _enroll(course_id: UUID, email: str, role: str) -> UUID:
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
    from promptgrimoire.db.activities import create_activity

    activity = await create_activity(week_id=week_id, title="Organise Test Activity")
    return activity.id, activity.template_workspace_id


async def _setup_template_tags(
    template_ws_id: UUID,
) -> None:
    """Create tags on the template workspace (DB + CRDT)."""
    from promptgrimoire.db.tags import create_tag

    await create_tag(template_ws_id, "Jurisdiction", "#1f77b4")
    await create_tag(template_ws_id, "Evidence", "#ff7f0e")


async def _add_template_document(
    workspace_id: UUID,
) -> UUID:
    from promptgrimoire.db.workspace_documents import (
        add_document,
    )

    doc = await add_document(
        workspace_id=workspace_id,
        type="source",
        content=(
            "<p>Sample document text for testing organise tab with enough content.</p>"
        ),
        source_type="paste",
        title="Test Document",
    )
    return doc.id


async def _clone_workspace(
    activity_id: UUID, user_id: UUID
) -> tuple[UUID, dict[UUID, UUID]]:
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
    """Add highlights with various text lengths + comments."""
    from promptgrimoire.crdt.annotation_doc import (
        AnnotationDocumentRegistry,
    )
    from promptgrimoire.db.workspaces import (
        save_workspace_crdt_state,
    )

    registry = AnnotationDocumentRegistry()
    doc = await registry.get_or_create_for_workspace(workspace_id)

    tags = doc.list_tags()
    tag_jurisdiction = None
    tag_evidence = None
    for tid, tdata in tags.items():
        if tdata["name"] == "Jurisdiction":
            tag_jurisdiction = tid
        elif tdata["name"] == "Evidence":
            tag_evidence = tid

    assert tag_jurisdiction is not None
    assert tag_evidence is not None

    # HL1: short text (<100 chars), tag=Jurisdiction, 1 comment
    hl1_id = doc.add_highlight(
        start_char=10,
        end_char=30,
        tag=tag_jurisdiction,
        text="Short highlight text",
        author=user_name,
        document_id=str(document_id),
        user_id=user_id,
    )
    doc.add_comment(
        hl1_id,
        user_name,
        "A test comment on organise card",
        user_id=user_id,
    )

    # HL2: long text (>100 chars), tag=Evidence
    long_text = "B" * 120
    doc.add_highlight(
        start_char=50,
        end_char=170,
        tag=tag_evidence,
        text=long_text,
        author=user_name,
        document_id=str(document_id),
        user_id=user_id,
    )

    # HL3: tag=Evidence (second card in Evidence column)
    doc.add_highlight(
        start_char=200,
        end_char=220,
        tag=tag_evidence,
        text="Another evidence highlight",
        author=user_name,
        document_id=str(document_id),
        user_id=user_id,
    )

    await save_workspace_crdt_state(workspace_id, doc.get_full_state())


async def _setup_workspace_with_highlights(
    email: str = "student-org@test.example.edu.au",
) -> tuple[UUID, UUID, str]:
    """Full setup returning (workspace_id, doc_id, user_id_str)."""
    course_id, _ = await _create_course()
    await _enroll(course_id, "coordinator@uni.edu", "coordinator")
    user_id = await _enroll(course_id, email, "student")

    week_id = await _create_week(course_id)
    from promptgrimoire.db.weeks import publish_week

    await publish_week(week_id)

    activity_id, template_ws_id = await _create_activity(week_id)
    await _setup_template_tags(template_ws_id)
    template_doc_id = await _add_template_document(template_ws_id)

    ws_id, doc_map = await _clone_workspace(activity_id, user_id)
    cloned_doc_id = doc_map.get(template_doc_id, template_doc_id)

    await _add_highlights_to_workspace(
        ws_id,
        cloned_doc_id,
        str(user_id),
        user_name=email.split("@", maxsplit=1)[0],
    )

    return ws_id, cloned_doc_id, str(user_id)


async def _open_organise_tab(user: User, ws_id: UUID, email: str) -> None:
    """Authenticate, open annotation page, switch to Organise.

    NiceGUI User harness cannot simulate Quasar tab click DOM
    events. Set tab_panels.value programmatically instead.
    """
    import asyncio

    from nicegui import ElementFilter, ui

    await _authenticate(user, email=email)
    await user.open(f"/annotation?workspace_id={ws_id}")
    await _should_see_testid(user, "tab-annotate")

    # Find tab_panels and switch to Organise
    with user:
        for el in ElementFilter():
            if isinstance(el, ui.tab_panels):
                el.value = "Organise"
                break

    await asyncio.sleep(0.3)
    await _should_see_testid(user, "organise-columns", retries=20)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestOrganiseTabRendering:
    """Characterisation tests for Organise tab card rendering."""

    @pytest.mark.asyncio
    async def test_organise_cards_rendered(self, nicegui_user: User) -> None:
        """Organise cards are rendered for highlights."""
        email = "student-org-cards@test.example.edu.au"
        ws_id, _, _ = await _setup_workspace_with_highlights(email=email)
        await _open_organise_tab(nicegui_user, ws_id, email)

        cards = _find_all_by_testid(nicegui_user, "organise-card")
        assert len(cards) == 3, f"Expected 3 organise cards, got {len(cards)}"

    @pytest.mark.asyncio
    async def test_snippet_truncated_at_100_chars(self, nicegui_user: User) -> None:
        """Text >100 chars is truncated with '...' suffix."""
        email = "student-org-trunc@test.example.edu.au"
        ws_id, _, _ = await _setup_workspace_with_highlights(email=email)
        await _open_organise_tab(nicegui_user, ws_id, email)

        cards = _find_all_by_testid(nicegui_user, "organise-card")
        # Find the card with long text (120 B's)
        found_truncated = False
        for card in cards:
            for desc in card.descendants():
                if not hasattr(desc, "text"):
                    continue
                text_val = str(desc.text)
                if "BBB" in text_val and "..." in text_val:
                    # Should be 100 B's + "..."
                    inner = text_val.strip('"')
                    assert inner.endswith("..."), (
                        f"Expected '...' suffix, got: {text_val}"
                    )
                    # 100 chars of B + "..."
                    assert len(inner) == 103, (
                        f"Expected 103 chars (100+...), got {len(inner)}"
                    )
                    found_truncated = True
                    break
            if found_truncated:
                break
        assert found_truncated, "Expected truncated text with '...' in organise card"

    @pytest.mark.asyncio
    async def test_short_text_not_truncated(self, nicegui_user: User) -> None:
        """Text <100 chars is shown in full (no '...')."""
        email = "student-org-short@test.example.edu.au"
        ws_id, _, _ = await _setup_workspace_with_highlights(email=email)
        await _open_organise_tab(nicegui_user, ws_id, email)

        cards = _find_all_by_testid(nicegui_user, "organise-card")
        found_short = False
        for card in cards:
            for desc in card.descendants():
                if not hasattr(desc, "text"):
                    continue
                text_val = str(desc.text)
                if "Short highlight text" in text_val:
                    assert "..." not in text_val, (
                        f"Short text should not be truncated: {text_val}"
                    )
                    found_short = True
                    break
            if found_short:
                break
        assert found_short, "Expected to find short highlight text in card"

    @pytest.mark.asyncio
    async def test_locate_button_present(self, nicegui_user: User) -> None:
        """Each organise card has a locate button."""
        email = "student-org-locate@test.example.edu.au"
        ws_id, _, _ = await _setup_workspace_with_highlights(email=email)
        await _open_organise_tab(nicegui_user, ws_id, email)

        cards = _find_all_by_testid(nicegui_user, "organise-card")
        for card in cards:
            found_locate = any(
                desc.props.get("icon") == "my_location"
                for desc in card.descendants()
                if hasattr(desc, "_props")
            )
            assert found_locate, "Organise card missing locate button"

    @pytest.mark.asyncio
    async def test_comment_text_visible(self, nicegui_user: User) -> None:
        """Comment text is visible on organise cards."""
        email = "student-org-comment@test.example.edu.au"
        ws_id, _, _ = await _setup_workspace_with_highlights(email=email)
        await _open_organise_tab(nicegui_user, ws_id, email)

        # Search all cards for the comment text
        cards = _find_all_by_testid(nicegui_user, "organise-card")
        found_comment = False
        for card in cards:
            for desc in card.descendants():
                if not hasattr(desc, "text"):
                    continue
                if "A test comment on organise card" in str(desc.text):
                    found_comment = True
                    break
            if found_comment:
                break
        assert found_comment, "Expected comment text visible on organise card"

    @pytest.mark.asyncio
    async def test_cards_grouped_by_tag(self, nicegui_user: User) -> None:
        """Cards appear in tag columns."""
        email = "student-org-group@test.example.edu.au"
        ws_id, _, _ = await _setup_workspace_with_highlights(email=email)
        await _open_organise_tab(nicegui_user, ws_id, email)

        columns = _find_all_by_testid(nicegui_user, "tag-column")
        assert len(columns) >= 2, f"Expected at least 2 tag columns, got {len(columns)}"

        # Check column names include our tags
        col_names = [c.props.get("data-tag-name", "") for c in columns]
        assert "Jurisdiction" in col_names, f"Missing Jurisdiction column: {col_names}"
        assert "Evidence" in col_names, f"Missing Evidence column: {col_names}"

    @pytest.mark.asyncio
    async def test_author_displayed_with_anonymise(self, nicegui_user: User) -> None:
        """Author display uses anonymise_author (own name shown)."""
        email = "student-org-author@test.example.edu.au"
        ws_id, _, _ = await _setup_workspace_with_highlights(email=email)
        await _open_organise_tab(nicegui_user, ws_id, email)

        cards = _find_all_by_testid(nicegui_user, "organise-card")
        # Since viewing own highlights, author should be real
        user_name = email.split("@", maxsplit=1)[0]
        found_author = False
        for card in cards:
            for desc in card.descendants():
                if not hasattr(desc, "text"):
                    continue
                if f"by {user_name}" in str(desc.text):
                    found_author = True
                    break
            if found_author:
                break
        assert found_author, f"Expected 'by {user_name}' in organise card"
