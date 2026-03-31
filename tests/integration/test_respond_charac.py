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
    _element_text_content,
    _find_all_by_testid,
    _find_by_testid,
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
    await wait_for_annotation_load(user)

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
    async def test_long_text_rendered_with_css_overflow(
        self, nicegui_user: User
    ) -> None:
        """Long text (>80 chars) rendered with CSS max-height overflow."""
        email = "student-rsp-trunc@test.example.edu.au"
        ws_id, _, _ = await _setup_workspace_with_highlights(email=email)
        await _open_respond_tab(nicegui_user, ws_id, email)

        cards = _find_all_by_testid(nicegui_user, "respond-reference-card")
        found_long_text = False
        found_max_height = False
        for card in cards:
            for desc in [card, *card.descendants()]:
                content = _element_text_content(desc)
                if "CCC" in content:
                    found_long_text = True
                    # Verify CSS overflow is used (in innerHTML)
                    inner = desc.props.get("innerHTML", "")
                    if "max-height" in inner:
                        found_max_height = True
                    break
            if found_long_text:
                break
        assert found_long_text, (
            "Expected highlight text containing 'CCC' in respond reference card"
        )
        assert found_max_height, "Expected max-height CSS for overflow on long text"

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
            for desc in [card, *card.descendants()]:
                content = _element_text_content(desc)
                if "Comment visible in respond tab" in content:
                    found_comment = True
                    break
            if found_comment:
                break
        assert found_comment, "Expected comment text in respond reference card"

    @pytest.mark.asyncio
    async def test_respond_anonymises_author_for_other_viewer(
        self, nicegui_user: User
    ) -> None:
        """Respond tab anonymises author for non-author viewer (AC11.3).

        With anonymous_sharing=True, a viewer who did NOT create the
        highlights must see the adjective-animal pseudonym, not the raw
        author name. This verifies respond.py calls anonymise_author().
        """
        from promptgrimoire.auth.anonymise import _adjective_animal_label
        from promptgrimoire.db.acl import grant_permission
        from promptgrimoire.db.users import find_or_create_user

        author_email = "student-rsp-author@test.example.edu.au"
        viewer_email = "student-rsp-viewer@test.example.edu.au"

        ws_id, _, author_user_id = await _setup_workspace_with_highlights(
            email=author_email, anonymous_sharing=True
        )

        # Create viewer and grant explicit ACL
        viewer_record, _ = await find_or_create_user(
            email=viewer_email,
            display_name=viewer_email.split("@", maxsplit=1)[0],
        )
        await grant_permission(ws_id, viewer_record.id, "viewer")

        # Compute the exact pseudonym that anonymise_author() will produce
        expected_pseudonym = _adjective_animal_label(author_user_id)

        # Open as the viewer (not the author)
        await _open_respond_tab(nicegui_user, ws_id, viewer_email)

        cards = _find_all_by_testid(nicegui_user, "respond-reference-card")
        author_name = author_email.split("@", maxsplit=1)[0]

        # Raw author name must NOT appear (anonymised)
        raw_author_found = False
        # The exact deterministic pseudonym must appear
        pseudonym_found = False
        for card in cards:
            for desc in [card, *card.descendants()]:
                content = _element_text_content(desc)
                if f"by {author_name}" in content:
                    raw_author_found = True
                if f"by {expected_pseudonym}" in content:
                    pseudonym_found = True

        assert not raw_author_found, (
            f"Raw author '{author_name}' must NOT appear when "
            "anonymous_sharing=True and viewing as a different user "
            "(respond.py must call anonymise_author())"
        )
        assert pseudonym_found, (
            f"Expected exact pseudonym 'by {expected_pseudonym}' in respond card "
            f"for viewer '{viewer_email}' with anonymous_sharing=True "
            "(from _adjective_animal_label deterministic contract)"
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
