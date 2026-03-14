"""NiceGUI integration tests for Respond tab reference card rendering.

Characterisation tests that lock down existing Respond tab (Tab 3)
reference card behaviour before refactoring in Phases 2-6.

Verifies: None (characterisation -- locks down existing behaviour)

Traceability:
- Plan: phase_01.md Task 5 (multi-doc-tabs-186-plan-a)
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
    _find_by_testid,
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
    from promptgrimoire.db.courses import create_course

    uid = uuid4().hex[:8]
    code = f"RSP{uid.upper()}"
    course = await create_course(
        code=code,
        name=f"Respond Test {uid}",
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
    anonymous_sharing: bool | None = None,
) -> tuple[UUID, UUID]:
    from promptgrimoire.db.activities import create_activity, update_activity

    activity = await create_activity(week_id=week_id, title="Respond Test Activity")
    if anonymous_sharing is not None:
        await update_activity(activity.id, anonymous_sharing=anonymous_sharing)
    return activity.id, activity.template_workspace_id


async def _setup_template_tags(
    template_ws_id: UUID,
) -> None:
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
            "<p>Sample document text for testing respond tab with enough content.</p>"
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

    # HL1: short text (<100 chars), with comment
    hl1_id = doc.add_highlight(
        start_char=10,
        end_char=30,
        tag=tag_jurisdiction,
        text="Short highlight for respond",
        author=user_name,
        document_id=str(document_id),
        user_id=user_id,
    )
    doc.add_comment(
        hl1_id,
        user_name,
        "Comment visible in respond tab",
        user_id=user_id,
    )

    # HL2: long text (>100 chars)
    long_text = "C" * 120
    doc.add_highlight(
        start_char=50,
        end_char=170,
        tag=tag_evidence,
        text=long_text,
        author=user_name,
        document_id=str(document_id),
        user_id=user_id,
    )

    await save_workspace_crdt_state(workspace_id, doc.get_full_state())


async def _setup_workspace_with_highlights(
    email: str = "student-rsp@test.example.edu.au",
    anonymous_sharing: bool | None = None,
) -> tuple[UUID, UUID, str]:
    """Full setup returning (workspace_id, doc_id, user_id_str).

    Parameters
    ----------
    email:
        Email address for the student user who creates highlights.
    anonymous_sharing:
        When True, sets anonymous_sharing=True on the Activity so that
        anonymise_author() will return a pseudonym for other viewers.
        None (default) leaves the activity at the course default (False).
    """
    course_id, _ = await _create_course()
    await _enroll(course_id, "coordinator@uni.edu", "coordinator")
    user_id = await _enroll(course_id, email, "student")

    week_id = await _create_week(course_id)
    from promptgrimoire.db.weeks import publish_week

    await publish_week(week_id)

    activity_id, template_ws_id = await _create_activity(
        week_id, anonymous_sharing=anonymous_sharing
    )
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


async def _open_respond_tab(user: User, ws_id: UUID, email: str) -> None:
    """Authenticate, open annotation page, switch to Respond.

    NiceGUI User harness cannot simulate Quasar tab click DOM
    events. Set tab_panels.value programmatically instead.
    """
    from nicegui import ElementFilter, ui

    await _authenticate(user, email=email)
    await user.open(f"/annotation?workspace_id={ws_id}")
    await _should_see_testid(user, "tab-annotate")

    # Find tab_panels and switch to Respond
    with user:
        for el in ElementFilter():
            if isinstance(el, ui.tab_panels):
                el.value = "Respond"
                break

    # Wait until the Respond reference panel is rendered rather than
    # sleeping for a fixed duration -- fixed sleeps are unreliable under
    # parallel xdist execution (PG001).
    await wait_for(
        lambda: _find_by_testid(user, "respond-reference-panel") is not None,
        timeout=5.0,
    )
    # Respond tab renders reference panel
    await _should_see_testid(user, "respond-reference-panel", retries=20)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRespondTabRendering:
    """Characterisation tests for Respond tab reference cards."""

    @pytest.mark.asyncio
    async def test_reference_cards_rendered(self, nicegui_user: User) -> None:
        """Reference cards are rendered for highlights."""
        email = "student-rsp-cards@test.example.edu.au"
        ws_id, _, _ = await _setup_workspace_with_highlights(email=email)
        await _open_respond_tab(nicegui_user, ws_id, email)

        cards = _find_all_by_testid(nicegui_user, "respond-reference-card")
        assert len(cards) == 2, f"Expected 2 reference cards, got {len(cards)}"

    @pytest.mark.asyncio
    async def test_snippet_truncated_at_100_chars(self, nicegui_user: User) -> None:
        """Text >100 chars is truncated with '...' suffix."""
        email = "student-rsp-trunc@test.example.edu.au"
        ws_id, _, _ = await _setup_workspace_with_highlights(email=email)
        await _open_respond_tab(nicegui_user, ws_id, email)

        cards = _find_all_by_testid(nicegui_user, "respond-reference-card")
        found_truncated = False
        for card in cards:
            for desc in card.descendants():
                if not hasattr(desc, "text"):
                    continue
                text_val = str(desc.text)
                if "CCC" in text_val and "..." in text_val:
                    inner = text_val.strip('"')
                    assert inner.endswith("..."), f"Expected '...' suffix: {text_val}"
                    assert len(inner) == 103, f"Expected 103 chars, got {len(inner)}"
                    found_truncated = True
                    break
            if found_truncated:
                break
        assert found_truncated, "Expected truncated text in respond reference card"

    @pytest.mark.asyncio
    async def test_locate_button_present(self, nicegui_user: User) -> None:
        """Each reference card has a locate button."""
        email = "student-rsp-locate@test.example.edu.au"
        ws_id, _, _ = await _setup_workspace_with_highlights(email=email)
        await _open_respond_tab(nicegui_user, ws_id, email)

        locate_btns = _find_all_by_testid(nicegui_user, "respond-locate-btn")
        cards = _find_all_by_testid(nicegui_user, "respond-reference-card")
        assert len(locate_btns) == len(cards), (
            f"Expected {len(cards)} locate buttons, got {len(locate_btns)}"
        )

    @pytest.mark.asyncio
    async def test_comment_text_visible(self, nicegui_user: User) -> None:
        """Comment text is visible on reference cards."""
        email = "student-rsp-comment@test.example.edu.au"
        ws_id, _, _ = await _setup_workspace_with_highlights(email=email)
        await _open_respond_tab(nicegui_user, ws_id, email)

        cards = _find_all_by_testid(nicegui_user, "respond-reference-card")
        found_comment = False
        for card in cards:
            for desc in card.descendants():
                if not hasattr(desc, "text"):
                    continue
                if "Comment visible in respond tab" in str(desc.text):
                    found_comment = True
                    break
            if found_comment:
                break
        assert found_comment, "Expected comment text in respond reference card"

    @pytest.mark.asyncio
    async def test_respond_shows_raw_author_to_viewer(self, nicegui_user: User) -> None:
        """CHARACTERISATION: respond.py displays raw author to a second viewer.

        Known defect in src/promptgrimoire/pages/annotation/respond.py:
        respond.py does NOT call anonymise_author(). The raw author string
        is displayed directly to all viewers, even when anonymous_sharing=True.

        Setup:
        - anonymous_sharing=True is set on the Activity so that a correct call
          to anonymise_author() would return a pseudonym for non-author viewers.
        - A second viewer is granted explicit "viewer" ACL on the workspace.
        - The test opens the workspace as the viewer and asserts the raw author
          name is still shown (broken behaviour -- respond.py skips
          anonymise_author() entirely).

        After Phase 2 adds anonymise_author() to respond.py, the viewer will
        see the adjective-animal pseudonym instead of the raw author name, and
        this assertion will fail -- which is the intended regression signal.
        """
        from promptgrimoire.db.acl import grant_permission
        from promptgrimoire.db.users import find_or_create_user

        author_email = "student-rsp-author@test.example.edu.au"
        viewer_email = "student-rsp-viewer@test.example.edu.au"

        # anonymous_sharing=True: if respond.py called anonymise_author(),
        # the viewer would see a pseudonym. Since it doesn't, the viewer
        # still sees the raw name -- that's the broken behaviour we lock in.
        ws_id, _, _ = await _setup_workspace_with_highlights(
            email=author_email, anonymous_sharing=True
        )

        # Create the viewer user and give them explicit viewer ACL
        viewer_record, _ = await find_or_create_user(
            email=viewer_email,
            display_name=viewer_email.split("@", maxsplit=1)[0],
        )
        await grant_permission(ws_id, viewer_record.id, "viewer")

        # Open as the viewer (not the author)
        await _open_respond_tab(nicegui_user, ws_id, viewer_email)

        cards = _find_all_by_testid(nicegui_user, "respond-reference-card")
        # respond.py currently shows raw author -- anonymise_author() not called
        author_name = author_email.split("@", maxsplit=1)[0]
        found_raw_author = False
        for card in cards:
            for desc in card.descendants():
                if not hasattr(desc, "text"):
                    continue
                if f"by {author_name}" in str(desc.text):
                    found_raw_author = True
                    break
            if found_raw_author:
                break
        assert found_raw_author, (
            f"Expected raw 'by {author_name}' in respond card as seen by "
            f"viewer '{viewer_email}' with anonymous_sharing=True on the Activity "
            "(respond.py skips anonymise_author() -- known bug, Phase 2 will fix)"
        )

    @pytest.mark.asyncio
    async def test_tag_group_expansion_panels(self, nicegui_user: User) -> None:
        """Reference cards are grouped in tag expansion panels."""
        email = "student-rsp-groups@test.example.edu.au"
        ws_id, _, _ = await _setup_workspace_with_highlights(email=email)
        await _open_respond_tab(nicegui_user, ws_id, email)

        groups = _find_all_by_testid(nicegui_user, "respond-tag-group")
        assert len(groups) >= 2, f"Expected at least 2 tag groups, got {len(groups)}"

        group_names = [g.props.get("data-tag-name", "") for g in groups]
        assert "Jurisdiction" in group_names, (
            f"Missing Jurisdiction group: {group_names}"
        )
        assert "Evidence" in group_names, f"Missing Evidence group: {group_names}"
