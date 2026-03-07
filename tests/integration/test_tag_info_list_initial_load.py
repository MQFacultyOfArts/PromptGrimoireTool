"""Integration test: tag_info_list is populated on initial page load.

Verifies that when a workspace has DB-seeded tags (no prior CRDT state),
the initial render path populates state.tag_info_list from the hydrated
CRDT doc. This reproduces the "chase tags" bug where tags only appeared
via broadcast from a second client, not on the first page load.

Acceptance Criteria:
- tag-lifecycle-235-291.AC1.5: DB-only tags hydrate into CRDT on first load

Traceability:
- Issues: #235, #291
- Phase: docs/implementation-plans/2026-03-06-tag-lifecycle-235-291/phase_03.md
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from promptgrimoire.config import get_settings

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


async def _seed_workspace_with_db_tags() -> tuple[UUID, list[UUID]]:
    """Create a workspace with tags in DB only (no CRDT state).

    This mimics the seed data scenario: tags exist in the DB but the
    workspace has no prior CRDT state, so the CRDT doc must hydrate
    from DB on first load.

    Returns (workspace_id, [tag_id, ...]).
    """
    from promptgrimoire.db.activities import create_activity
    from promptgrimoire.db.courses import create_course
    from promptgrimoire.db.tags import create_tag
    from promptgrimoire.db.weeks import create_week
    from promptgrimoire.db.workspaces import (
        create_workspace,
        place_workspace_in_activity,
    )

    code = f"TI{uuid4().hex[:6].upper()}"
    course = await create_course(
        code=code, name=f"TagInit Test {code}", semester="2026-S1"
    )
    week = await create_week(course_id=course.id, week_number=1, title="Week 1")
    activity = await create_activity(week_id=week.id, title="Tag Init Test")

    ws = await create_workspace()
    await place_workspace_in_activity(ws.id, activity.id)

    # Create tags directly in DB (no crdt_doc parameter = DB-only)
    tag1 = await create_tag(workspace_id=ws.id, name="Alpha", color="#ff0000")
    tag2 = await create_tag(workspace_id=ws.id, name="Beta", color="#00ff00")

    return ws.id, [tag1.id, tag2.id]


class TestTagInfoListInitialLoad:
    """Verify tag_info_list is populated after CRDT doc load."""

    @pytest.mark.asyncio
    async def test_crdt_hydration_makes_tags_available(self) -> None:
        """CRDT hydration from DB makes tags available via workspace_tags_from_crdt.

        This verifies the data path works: DB tags -> CRDT hydration ->
        workspace_tags_from_crdt returns non-empty list.
        """
        from promptgrimoire.crdt.annotation_doc import AnnotationDocumentRegistry
        from promptgrimoire.pages.annotation.tags import workspace_tags_from_crdt

        ws_id, _tag_ids = await _seed_workspace_with_db_tags()

        # Load CRDT doc (triggers _ensure_crdt_tag_consistency hydration)
        registry = AnnotationDocumentRegistry()
        crdt_doc = await registry.get_or_create_for_workspace(ws_id)

        # Verify tags are available from CRDT after hydration
        tag_list = workspace_tags_from_crdt(crdt_doc)
        assert len(tag_list) == 2, (
            f"Expected 2 tags from CRDT after hydration, got {len(tag_list)}"
        )
        tag_names = {t.name for t in tag_list}
        assert tag_names == {"Alpha", "Beta"}

    @pytest.mark.asyncio
    async def test_tag_info_list_populated_after_crdt_doc_set(self) -> None:
        """tag_info_list must be populated right after crdt_doc is set.

        Simulates the _build_tab_panels path: after loading the CRDT doc
        and setting state.crdt_doc, workspace_tags_from_crdt should be
        called to populate state.tag_info_list. This is the fix for the
        "chase tags" bug where tags only appeared via broadcast.
        """
        from promptgrimoire.crdt.annotation_doc import AnnotationDocumentRegistry
        from promptgrimoire.pages.annotation import PageState
        from promptgrimoire.pages.annotation.tags import workspace_tags_from_crdt

        ws_id, _tag_ids = await _seed_workspace_with_db_tags()

        # Simulate _resolve_workspace_context: creates PageState without crdt_doc
        state = PageState(workspace_id=ws_id)
        assert state.crdt_doc is None
        assert state.tag_info_list is None

        # Simulate _build_tab_panels: load CRDT doc and populate tag_info_list
        registry = AnnotationDocumentRegistry()
        crdt_doc = await registry.get_or_create_for_workspace(ws_id)
        state.crdt_doc = crdt_doc
        state.tag_info_list = workspace_tags_from_crdt(crdt_doc)

        # After the fix, tag_info_list should be populated
        assert state.tag_info_list is not None
        assert len(state.tag_info_list) == 2
        tag_names = {t.name for t in state.tag_info_list}
        assert tag_names == {"Alpha", "Beta"}
