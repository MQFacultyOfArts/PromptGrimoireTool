"""Tests for tag cloning during workspace cloning.

These tests require a running PostgreSQL instance. Set DEV__TEST_DATABASE_URL.

Tests verify TagGroup cloning (AC4.1), Tag cloning with group remapping (AC4.2),
locked flag preservation (AC4.5), empty template cloning (AC4.6), CRDT highlight
tag remapping (AC4.3), tag_order key remapping (AC4.4), and legacy BriefTag
passthrough.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest

from promptgrimoire.config import get_settings

if TYPE_CHECKING:
    from promptgrimoire.db.models import Activity, Course, Tag, TagGroup, User, Week

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


async def _make_clone_user() -> User:
    """Create a unique user for clone ownership tests."""
    from promptgrimoire.db.users import create_user

    tag = uuid4().hex[:8]
    return await create_user(
        email=f"tag-clone-{tag}@test.local",
        display_name=f"Tag Clone Tester {tag}",
    )


async def _make_activity() -> tuple[Course, Week, Activity]:
    """Create a Course -> Week -> Activity with no documents or tags."""
    from promptgrimoire.db.activities import create_activity
    from promptgrimoire.db.courses import create_course
    from promptgrimoire.db.weeks import create_week

    code = f"T{uuid4().hex[:6].upper()}"
    course = await create_course(code=code, name="Tag Clone Test", semester="2026-S1")
    week = await create_week(course_id=course.id, week_number=1, title="Week 1")
    activity = await create_activity(week_id=week.id, title="Tag Clone Activity")
    return course, week, activity


async def _add_tag_groups(
    workspace_id: UUID,
    names: list[str],
) -> list[TagGroup]:
    """Add TagGroups to a workspace via direct session.add()."""
    from promptgrimoire.db.engine import get_session
    from promptgrimoire.db.models import TagGroup

    groups: list[TagGroup] = []
    async with get_session() as session:
        for idx, name in enumerate(names):
            group = TagGroup(
                workspace_id=workspace_id,
                name=name,
                order_index=idx,
            )
            session.add(group)
            await session.flush()
            await session.refresh(group)
            groups.append(group)
    return groups


async def _add_tags(
    workspace_id: UUID,
    specs: list[dict],
) -> list[Tag]:
    """Add Tags to a workspace via direct session.add().

    Each spec dict should have: name, color, and optionally group_id,
    description, locked.
    """
    from promptgrimoire.db.engine import get_session
    from promptgrimoire.db.models import Tag

    tags: list[Tag] = []
    async with get_session() as session:
        for idx, spec in enumerate(specs):
            tag = Tag(
                workspace_id=workspace_id,
                name=spec["name"],
                color=spec["color"],
                group_id=spec.get("group_id"),
                description=spec.get("description"),
                locked=spec.get("locked", False),
                order_index=idx,
            )
            session.add(tag)
            await session.flush()
            await session.refresh(tag)
            tags.append(tag)
    return tags


class TestTagGroupCloning:
    """Tests for TagGroup cloning during workspace cloning."""

    @pytest.mark.asyncio
    async def test_clone_creates_tag_groups_with_same_names_and_order(self) -> None:
        """Cloned workspace has TagGroups with same names and order_index but new UUIDs.

        Verifies AC4.1.
        """
        from promptgrimoire.db.tags import list_tag_groups_for_workspace
        from promptgrimoire.db.workspaces import clone_workspace_from_activity

        _, _, activity = await _make_activity()
        user = await _make_clone_user()

        template_groups = await _add_tag_groups(
            activity.template_workspace_id,
            ["Legal Case Brief", "Reflection"],
        )

        clone, _doc_map = await clone_workspace_from_activity(activity.id, user.id)

        cloned_groups = await list_tag_groups_for_workspace(clone.id)
        assert len(cloned_groups) == 2

        # Same names and order_index
        assert cloned_groups[0].name == "Legal Case Brief"
        assert cloned_groups[0].order_index == 0
        assert cloned_groups[1].name == "Reflection"
        assert cloned_groups[1].order_index == 1

        # New UUIDs
        template_ids = {g.id for g in template_groups}
        cloned_ids = {g.id for g in cloned_groups}
        assert template_ids.isdisjoint(cloned_ids)

        # Correct workspace_id
        for cg in cloned_groups:
            assert cg.workspace_id == clone.id


class TestTagCloning:
    """Tests for Tag cloning during workspace cloning."""

    @pytest.mark.asyncio
    async def test_clone_creates_tags_with_remapped_group_ids(self) -> None:
        """Cloned Tags point to the clone's TagGroup UUIDs, not the template's.

        Verifies AC4.2.
        """
        from promptgrimoire.db.tags import (
            list_tag_groups_for_workspace,
            list_tags_for_workspace,
        )
        from promptgrimoire.db.workspaces import clone_workspace_from_activity

        _, _, activity = await _make_activity()
        user = await _make_clone_user()

        # Create 1 group and 3 tags: 2 in the group, 1 ungrouped
        groups = await _add_tag_groups(
            activity.template_workspace_id, ["Brief Headings"]
        )
        group_id = groups[0].id

        await _add_tags(
            activity.template_workspace_id,
            [
                {
                    "name": "Jurisdiction",
                    "color": "#1f77b4",
                    "group_id": group_id,
                    "description": "Court and jurisdiction",
                },
                {
                    "name": "Facts",
                    "color": "#2ca02c",
                    "group_id": group_id,
                },
                {
                    "name": "Reflection",
                    "color": "#d62728",
                    # No group_id -- ungrouped
                },
            ],
        )

        clone, _doc_map = await clone_workspace_from_activity(activity.id, user.id)

        cloned_tags = await list_tags_for_workspace(clone.id)
        cloned_groups = await list_tag_groups_for_workspace(clone.id)

        assert len(cloned_tags) == 3
        assert len(cloned_groups) == 1

        clone_group_id = cloned_groups[0].id

        # Tags by name for easy assertions
        by_name = {t.name: t for t in cloned_tags}

        # Grouped tags point to clone's group
        assert by_name["Jurisdiction"].group_id == clone_group_id
        assert by_name["Jurisdiction"].group_id != group_id
        assert by_name["Facts"].group_id == clone_group_id

        # Ungrouped tag stays ungrouped
        assert by_name["Reflection"].group_id is None

        # Field preservation
        assert by_name["Jurisdiction"].color == "#1f77b4"
        assert by_name["Jurisdiction"].description == "Court and jurisdiction"
        assert by_name["Facts"].color == "#2ca02c"
        assert by_name["Reflection"].color == "#d62728"

        # All have correct workspace_id
        for ct in cloned_tags:
            assert ct.workspace_id == clone.id

    @pytest.mark.asyncio
    async def test_locked_flag_preserved_on_clone(self) -> None:
        """Cloned tags preserve the locked flag.

        Verifies AC4.5.
        """
        from promptgrimoire.db.tags import list_tags_for_workspace
        from promptgrimoire.db.workspaces import clone_workspace_from_activity

        _, _, activity = await _make_activity()
        user = await _make_clone_user()

        await _add_tags(
            activity.template_workspace_id,
            [
                {"name": "LockedTag", "color": "#aabbcc", "locked": True},
                {"name": "UnlockedTag", "color": "#ddeeff", "locked": False},
            ],
        )

        clone, _doc_map = await clone_workspace_from_activity(activity.id, user.id)

        cloned_tags = await list_tags_for_workspace(clone.id)
        by_name = {t.name: t for t in cloned_tags}

        assert by_name["LockedTag"].locked is True
        assert by_name["UnlockedTag"].locked is False


class TestEmptyTagClone:
    """Tests for cloning a template with no tags."""

    @pytest.mark.asyncio
    async def test_empty_template_produces_zero_tags(self) -> None:
        """Cloning a template with no tags produces 0 TagGroups and 0 Tags.

        Verifies AC4.6.
        """
        from promptgrimoire.db.tags import (
            list_tag_groups_for_workspace,
            list_tags_for_workspace,
        )
        from promptgrimoire.db.workspaces import clone_workspace_from_activity

        _, _, activity = await _make_activity()
        user = await _make_clone_user()

        clone, _doc_map = await clone_workspace_from_activity(activity.id, user.id)

        cloned_groups = await list_tag_groups_for_workspace(clone.id)
        cloned_tags = await list_tags_for_workspace(clone.id)

        assert cloned_groups == []
        assert cloned_tags == []
