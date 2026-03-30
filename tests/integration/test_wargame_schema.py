"""Integration tests for wargame schema migrations and constraints."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from promptgrimoire.config import get_settings
from promptgrimoire.db.models import (
    ACLEntry,
    Activity,
    WargameConfig,
    WargameMessage,
    WargameTeam,
    Week,
)

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


async def _make_week(suffix: str) -> Week:
    """Create a unique course/week for integration tests."""
    from promptgrimoire.db.courses import create_course
    from promptgrimoire.db.weeks import create_week

    code = f"WG{uuid4().hex[:6].upper()}"
    course = await create_course(
        code=code, name=f"Wargame {suffix}", semester="2026-S1"
    )
    return await create_week(course_id=course.id, week_number=1, title="Week 1")


async def _make_wargame_activity(week_id: UUID, *, title: str = "Wargame") -> Activity:
    """Create and persist a wargame Activity row."""
    from promptgrimoire.db.engine import get_session

    async with get_session() as session:
        activity = Activity(
            week_id=week_id,
            type="wargame",
            title=title,
        )
        session.add(activity)
        await session.flush()
        await session.refresh(activity)
        return activity


class TestActivityTypeDiscriminator:
    """Validate Activity type and template constraints."""

    @pytest.mark.asyncio
    async def test_insert_without_type_uses_annotation_default(self) -> None:
        """Insert path without type proves the branch-local legacy/default contract."""
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.workspaces import create_workspace

        week = await _make_week("activity-legacy-default")
        template = await create_workspace()
        activity_id = uuid4()
        now = datetime.now(UTC)

        async with get_session() as session:
            await session.execute(
                sa.text(
                    """
                    INSERT INTO activity (
                        id,
                        week_id,
                        template_workspace_id,
                        title,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        :id,
                        :week_id,
                        :template_workspace_id,
                        :title,
                        :created_at,
                        :updated_at
                    )
                    """
                ),
                {
                    "id": activity_id,
                    "week_id": week.id,
                    "template_workspace_id": template.id,
                    "title": "Legacy annotation",
                    "created_at": now,
                    "updated_at": now,
                },
            )

        from promptgrimoire.db.activities import get_activity

        activity = await get_activity(activity_id)
        assert activity is not None
        assert activity.type == "annotation"
        assert activity.template_workspace_id == template.id

    @pytest.mark.asyncio
    async def test_rejects_unknown_activity_type(self) -> None:
        """Unknown discriminator values must be rejected at the database boundary."""
        from promptgrimoire.db.engine import get_session

        week = await _make_week("activity-unknown-type")
        with pytest.raises(IntegrityError, match="ck_activity_type_known"):
            async with get_session() as session:
                await session.execute(
                    sa.text(
                        """
                        INSERT INTO activity (
                            id,
                            week_id,
                            type,
                            title,
                            created_at,
                            updated_at
                        )
                        VALUES (
                            :id,
                            :week_id,
                            :type,
                            :title,
                            :created_at,
                            :updated_at
                        )
                        """
                    ),
                    {
                        "id": uuid4(),
                        "week_id": week.id,
                        "type": "unknown",
                        "title": "Unknown activity",
                        "created_at": datetime.now(UTC),
                        "updated_at": datetime.now(UTC),
                    },
                )

    @pytest.mark.asyncio
    async def test_create_activity_defaults_to_annotation_type(self) -> None:
        """create_activity should persist type='annotation' for existing path."""
        from promptgrimoire.db.activities import create_activity

        week = await _make_week("activity-default")
        activity = await create_activity(week_id=week.id, title="Annotation")
        assert activity.type == "annotation"
        assert activity.template_workspace_id is not None

    @pytest.mark.asyncio
    async def test_accepts_wargame_activity_without_template_workspace(self) -> None:
        """A wargame activity with no template workspace is valid."""
        week = await _make_week("activity-wargame")
        activity = await _make_wargame_activity(week.id, title="Wargame Activity")
        assert activity.type == "wargame"
        assert activity.template_workspace_id is None

    @pytest.mark.asyncio
    async def test_rejects_annotation_activity_without_template_workspace(self) -> None:
        """Annotation activities must define template_workspace_id."""
        from promptgrimoire.db.engine import get_session

        week = await _make_week("activity-bad-annotation")
        with pytest.raises(
            IntegrityError, match="ck_activity_annotation_requires_template"
        ):
            async with get_session() as session:
                activity = Activity(
                    week_id=week.id,
                    type="annotation",
                    title="Invalid annotation",
                )
                session.add(activity)
                await session.flush()

    @pytest.mark.asyncio
    async def test_rejects_wargame_activity_with_template_workspace(self) -> None:
        """Wargame activities must not define template_workspace_id."""
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.workspaces import create_workspace

        week = await _make_week("activity-bad-wargame")
        template = await create_workspace()
        with pytest.raises(IntegrityError, match="ck_activity_wargame_no_template"):
            async with get_session() as session:
                activity = Activity(
                    week_id=week.id,
                    template_workspace_id=template.id,
                    type="wargame",
                    title="Invalid wargame",
                )
                session.add(activity)
                await session.flush()


class TestWargameConfigTable:
    """Validate WargameConfig timer constraints."""

    @pytest.mark.asyncio
    async def test_accepts_timer_delta_only(self) -> None:
        """timer_delta set and timer_wall_clock NULL is valid."""
        from promptgrimoire.db.engine import get_session

        week = await _make_week("config-delta")
        activity = await _make_wargame_activity(week.id)
        async with get_session() as session:
            config = WargameConfig(
                activity_id=activity.id,
                system_prompt="System prompt",
                scenario_bootstrap="Scenario text",
                timer_delta=timedelta(minutes=30),
                timer_wall_clock=None,
            )
            session.add(config)
            await session.flush()
            await session.refresh(config)
            assert config.activity_type == "wargame"
            assert config.timer_delta == timedelta(minutes=30)
            assert config.timer_wall_clock is None

    @pytest.mark.asyncio
    async def test_accepts_timer_wall_clock_only(self) -> None:
        """timer_wall_clock set and timer_delta NULL is valid."""
        from promptgrimoire.db.engine import get_session

        week = await _make_week("config-wall-clock")
        activity = await _make_wargame_activity(week.id)
        async with get_session() as session:
            config = WargameConfig(
                activity_id=activity.id,
                system_prompt="System prompt",
                scenario_bootstrap="Scenario text",
                timer_delta=None,
                timer_wall_clock=time(hour=9, minute=0),
            )
            session.add(config)
            await session.flush()
            await session.refresh(config)
            assert config.activity_type == "wargame"
            assert config.timer_delta is None
            assert config.timer_wall_clock == time(hour=9, minute=0)

    @pytest.mark.asyncio
    async def test_rejects_both_timer_fields_null(self) -> None:
        """Both timer fields NULL violates exclusivity check."""
        from promptgrimoire.db.engine import get_session

        week = await _make_week("config-both-null")
        activity = await _make_wargame_activity(week.id)
        with pytest.raises(IntegrityError, match="ck_wargame_config_timer_exactly_one"):
            async with get_session() as session:
                config = WargameConfig(
                    activity_id=activity.id,
                    system_prompt="System prompt",
                    scenario_bootstrap="Scenario text",
                    timer_delta=None,
                    timer_wall_clock=None,
                )
                session.add(config)
                await session.flush()

    @pytest.mark.asyncio
    async def test_rejects_config_for_annotation_activity(self) -> None:
        """Config rows must not attach to annotation activities."""
        from promptgrimoire.db.activities import create_activity
        from promptgrimoire.db.engine import get_session

        week = await _make_week("config-annotation-parent")
        annotation_activity = await create_activity(week_id=week.id, title="Annotation")
        with pytest.raises(IntegrityError, match="fk_wargame_config_activity_wargame"):
            async with get_session() as session:
                config = WargameConfig(
                    activity_id=annotation_activity.id,
                    activity_type="wargame",
                    system_prompt="System prompt",
                    scenario_bootstrap="Scenario text",
                    timer_delta=timedelta(minutes=10),
                    timer_wall_clock=None,
                )
                session.add(config)
                await session.flush()

    @pytest.mark.asyncio
    async def test_rejects_non_wargame_child_discriminator(self) -> None:
        """The child-side discriminator CHECK should reject annotation values."""
        from promptgrimoire.db.engine import get_session

        week = await _make_week("config-child-discriminator")
        activity = await _make_wargame_activity(week.id)
        with pytest.raises(IntegrityError, match="ck_wargame_config_activity_type"):
            async with get_session() as session:
                config = WargameConfig(
                    activity_id=activity.id,
                    activity_type="annotation",
                    system_prompt="System prompt",
                    scenario_bootstrap="Scenario text",
                    timer_delta=timedelta(minutes=10),
                    timer_wall_clock=None,
                )
                session.add(config)
                await session.flush()

    @pytest.mark.asyncio
    async def test_deleting_activity_cascades_to_config(self) -> None:
        """Deleting the parent wargame activity should cascade-delete config."""
        from promptgrimoire.db.engine import get_session

        week = await _make_week("config-cascade")
        activity = await _make_wargame_activity(week.id)
        async with get_session() as session:
            config = WargameConfig(
                activity_id=activity.id,
                activity_type="wargame",
                system_prompt="System prompt",
                scenario_bootstrap="Scenario text",
                timer_delta=timedelta(minutes=15),
                timer_wall_clock=None,
            )
            session.add(config)
            await session.flush()

        async with get_session() as session:
            activity_row = await session.get(Activity, activity.id)
            assert activity_row is not None
            await session.delete(activity_row)

        async with get_session() as session:
            deleted_config = await session.get(WargameConfig, activity.id)
            assert deleted_config is None

    @pytest.mark.asyncio
    async def test_rejects_both_timer_fields_set(self) -> None:
        """Setting both timer fields violates exclusivity check."""
        from promptgrimoire.db.engine import get_session

        week = await _make_week("config-both-set")
        activity = await _make_wargame_activity(week.id)
        with pytest.raises(IntegrityError, match="ck_wargame_config_timer_exactly_one"):
            async with get_session() as session:
                config = WargameConfig(
                    activity_id=activity.id,
                    system_prompt="System prompt",
                    scenario_bootstrap="Scenario text",
                    timer_delta=timedelta(minutes=10),
                    timer_wall_clock=time(hour=10, minute=0),
                )
                session.add(config)
                await session.flush()


class TestWargameTeamTable:
    """Validate WargameTeam constraints and cascade behavior."""

    @pytest.mark.asyncio
    async def test_defaults_and_unique_codename_within_activity(self) -> None:
        """Team defaults apply and codename uniqueness is enforced per activity."""
        from promptgrimoire.db.engine import get_session

        week = await _make_week("team-defaults")
        activity = await _make_wargame_activity(week.id)
        async with get_session() as session:
            alpha = WargameTeam(activity_id=activity.id, codename="Alpha")
            bravo = WargameTeam(activity_id=activity.id, codename="Bravo")
            session.add(alpha)
            session.add(bravo)
            await session.flush()
            await session.refresh(alpha)
            assert alpha.activity_type == "wargame"
            assert alpha.current_round == 0
            assert alpha.round_state == "drafting"
            assert alpha.current_deadline is None
            assert alpha.game_state_text is None
            assert alpha.student_summary_text is None

        with pytest.raises(IntegrityError, match="uq_wargame_team_activity_codename"):
            async with get_session() as session:
                duplicate = WargameTeam(activity_id=activity.id, codename="Alpha")
                session.add(duplicate)
                await session.flush()

    @pytest.mark.asyncio
    async def test_rejects_team_for_annotation_activity(self) -> None:
        """Annotation activities must not own wargame teams."""
        from promptgrimoire.db.activities import create_activity
        from promptgrimoire.db.engine import get_session

        week = await _make_week("team-annotation-parent")
        annotation_activity = await create_activity(week_id=week.id, title="Annotation")
        with pytest.raises(IntegrityError, match="fk_wargame_team_activity_wargame"):
            async with get_session() as session:
                team = WargameTeam(activity_id=annotation_activity.id, codename="Alpha")
                session.add(team)
                await session.flush()

    @pytest.mark.asyncio
    async def test_deleting_activity_cascades_to_teams(self) -> None:
        """Deleting activity should cascade-delete child teams."""
        from promptgrimoire.db.engine import get_session

        week = await _make_week("team-cascade")
        activity = await _make_wargame_activity(week.id)
        async with get_session() as session:
            team = WargameTeam(activity_id=activity.id, codename="Cascade")
            session.add(team)
            await session.flush()
            team_id = team.id

        async with get_session() as session:
            activity_row = await session.get(Activity, activity.id)
            assert activity_row is not None
            await session.delete(activity_row)

        async with get_session() as session:
            deleted_team = await session.get(WargameTeam, team_id)
            assert deleted_team is None


class TestWargameMessageTable:
    """Validate WargameMessage constraints and cascade behavior."""

    @pytest.mark.asyncio
    async def test_orders_messages_by_sequence_number_not_timestamps(self) -> None:
        """Canonical message order must come from sequence_no, not timestamps."""
        from sqlmodel import select

        from promptgrimoire.db.engine import get_session

        week = await _make_week("message-ordering")
        activity = await _make_wargame_activity(week.id)
        base_time = datetime.now(UTC)

        async with get_session() as session:
            team = WargameTeam(activity_id=activity.id, codename="Order")
            session.add(team)
            await session.flush()
            team_id = team.id

            session.add(
                WargameMessage(
                    team_id=team_id,
                    sequence_no=2,
                    role="assistant",
                    content="second",
                    created_at=base_time - timedelta(minutes=5),
                )
            )
            session.add(
                WargameMessage(
                    team_id=team_id,
                    sequence_no=1,
                    role="user",
                    content="first",
                    created_at=base_time + timedelta(minutes=5),
                )
            )
            session.add(
                WargameMessage(
                    team_id=team_id,
                    sequence_no=3,
                    role="system",
                    content="third",
                    created_at=base_time,
                )
            )
            await session.flush()

        async with get_session() as session:
            result = await session.exec(
                select(WargameMessage)
                .where(WargameMessage.team_id == team_id)
                .order_by(WargameMessage.sequence_no)  # type: ignore[arg-type]  -- SQLModel order_by() stubs don't accept Column expressions
            )
            messages = list(result.all())

        assert [message.sequence_no for message in messages] == [1, 2, 3]
        assert [message.content for message in messages] == ["first", "second", "third"]
        assert messages[0].created_at > messages[1].created_at

    @pytest.mark.asyncio
    async def test_roles_and_unique_sequence_per_team(self) -> None:
        """Messages accept multiple roles; duplicate sequence_no is rejected."""
        from promptgrimoire.db.engine import get_session

        week = await _make_week("message-unique")
        activity = await _make_wargame_activity(week.id)
        # Single session: PG checks unique constraints within a transaction,
        # no commit required.  The previous two-session pattern was racy under
        # xdist — the second session's flush could execute before the first
        # session's commit was visible.
        async with get_session() as session:
            team = WargameTeam(activity_id=activity.id, codename="Delta")
            session.add(team)
            await session.flush()
            team_id = team.id

            session.add(
                WargameMessage(
                    team_id=team_id,
                    sequence_no=1,
                    role="user",
                    content="move",
                )
            )
            session.add(
                WargameMessage(
                    team_id=team_id,
                    sequence_no=2,
                    role="assistant",
                    content="result",
                )
            )
            session.add(
                WargameMessage(
                    team_id=team_id,
                    sequence_no=3,
                    role="system",
                    content="reminder",
                )
            )
            await session.flush()

            # Duplicate within the same transaction — savepoint (begin_nested)
            # so the IntegrityError rolls back only the savepoint, not the
            # outer session.
            with pytest.raises(
                IntegrityError, match="uq_wargame_message_team_sequence"
            ):
                async with session.begin_nested():
                    session.add(
                        WargameMessage(
                            team_id=team_id,
                            sequence_no=2,
                            role="assistant",
                            content="duplicate",
                        )
                    )
                    await session.flush()

    @pytest.mark.asyncio
    async def test_updates_earlier_message_in_place_without_reordering(self) -> None:
        """Edits keep payload fields and preserve canonical sequence order."""
        from sqlmodel import select

        from promptgrimoire.db.engine import get_session

        week = await _make_week("message-regeneration")
        activity = await _make_wargame_activity(week.id)

        async with get_session() as session:
            team = WargameTeam(activity_id=activity.id, codename="Revision")
            session.add(team)
            await session.flush()
            team_id = team.id

            original = WargameMessage(
                team_id=team_id,
                sequence_no=1,
                role="assistant",
                content="draft",
            )
            follow_up = WargameMessage(
                team_id=team_id,
                sequence_no=2,
                role="user",
                content="response",
            )
            session.add(original)
            session.add(follow_up)
            await session.flush()
            original_id = original.id

        async with get_session() as session:
            message = await session.get(WargameMessage, original_id)
            assert message is not None
            assert message.thinking is None
            assert message.edited_at is None

            edited_at = datetime.now(UTC)
            message.content = "final"
            message.thinking = "chain"
            message.metadata_json = {"regenerated": True}
            message.edited_at = edited_at
            session.add(message)
            await session.flush()

        async with get_session() as session:
            result = await session.exec(
                select(WargameMessage)
                .where(WargameMessage.team_id == team_id)
                .order_by(WargameMessage.sequence_no)  # type: ignore[arg-type]  -- SQLModel order_by() stubs don't accept Column expressions
            )
            messages = list(result.all())

        assert [message.sequence_no for message in messages] == [1, 2]
        assert messages[0].id == original_id
        assert messages[0].content == "final"
        assert messages[0].thinking == "chain"
        assert messages[0].metadata_json == {"regenerated": True}
        assert messages[0].edited_at is not None
        assert messages[1].content == "response"

    @pytest.mark.asyncio
    async def test_deleting_team_cascades_to_messages(self) -> None:
        """Deleting team should cascade-delete child messages."""
        from promptgrimoire.db.engine import get_session

        week = await _make_week("message-cascade")
        activity = await _make_wargame_activity(week.id)
        async with get_session() as session:
            team = WargameTeam(activity_id=activity.id, codename="Echo")
            session.add(team)
            await session.flush()
            team_id = team.id

            message = WargameMessage(
                team_id=team_id,
                sequence_no=1,
                role="user",
                content="hello",
            )
            session.add(message)
            await session.flush()
            message_id = message.id

        async with get_session() as session:
            team_row = await session.get(WargameTeam, team_id)
            assert team_row is not None
            await session.delete(team_row)

        async with get_session() as session:
            deleted_message = await session.get(WargameMessage, message_id)
            assert deleted_message is None


class TestAclEntryTeamExtension:
    """Validate ACL target exclusivity and partial unique indexes."""

    @pytest.mark.asyncio
    async def test_workspace_target_entry_remains_valid(self) -> None:
        """Existing workspace-target ACL entry shape still works."""
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace

        user = await create_user(
            email=f"wg-acl-ws-{uuid4().hex[:8]}@test.local",
            display_name="WS ACL User",
        )
        workspace = await create_workspace()
        async with get_session() as session:
            entry = ACLEntry(
                workspace_id=workspace.id,
                team_id=None,
                user_id=user.id,
                permission="viewer",
            )
            session.add(entry)
            await session.flush()
            await session.refresh(entry)
            assert entry.workspace_id == workspace.id
            assert entry.team_id is None

    @pytest.mark.asyncio
    async def test_team_target_entry_is_valid(self) -> None:
        """New team-target ACL entry shape is accepted."""
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.users import create_user

        week = await _make_week("acl-team")
        activity = await _make_wargame_activity(week.id)
        user = await create_user(
            email=f"wg-acl-team-{uuid4().hex[:8]}@test.local",
            display_name="Team ACL User",
        )

        async with get_session() as session:
            team = WargameTeam(activity_id=activity.id, codename="Foxtrot")
            session.add(team)
            await session.flush()

            entry = ACLEntry(
                workspace_id=None,
                team_id=team.id,
                user_id=user.id,
                permission="viewer",
            )
            session.add(entry)
            await session.flush()
            await session.refresh(entry)
            assert entry.workspace_id is None
            assert entry.team_id == team.id

    @pytest.mark.asyncio
    async def test_rejects_acl_entry_with_both_targets_set(self) -> None:
        """Exactly one ACL target FK must be set."""
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace

        week = await _make_week("acl-both")
        activity = await _make_wargame_activity(week.id)
        user = await create_user(
            email=f"wg-acl-both-{uuid4().hex[:8]}@test.local",
            display_name="Both ACL User",
        )
        workspace = await create_workspace()

        with pytest.raises(IntegrityError, match="ck_acl_entry_exactly_one_target"):
            async with get_session() as session:
                team = WargameTeam(activity_id=activity.id, codename="Golf")
                session.add(team)
                await session.flush()
                entry = ACLEntry(
                    workspace_id=workspace.id,
                    team_id=team.id,
                    user_id=user.id,
                    permission="viewer",
                )
                session.add(entry)
                await session.flush()

    @pytest.mark.asyncio
    async def test_rejects_acl_entry_with_no_target_set(self) -> None:
        """Exactly one ACL target FK must be set."""
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.users import create_user

        user = await create_user(
            email=f"wg-acl-none-{uuid4().hex[:8]}@test.local",
            display_name="None ACL User",
        )
        with pytest.raises(IntegrityError, match="ck_acl_entry_exactly_one_target"):
            async with get_session() as session:
                entry = ACLEntry(
                    workspace_id=None,
                    team_id=None,
                    user_id=user.id,
                    permission="viewer",
                )
                session.add(entry)
                await session.flush()

    @pytest.mark.asyncio
    async def test_workspace_target_uniqueness_preserved(self) -> None:
        """Duplicate workspace-target (workspace_id, user_id) is rejected."""
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace

        user = await create_user(
            email=f"wg-acl-dup-ws-{uuid4().hex[:8]}@test.local",
            display_name="Dup WS ACL User",
        )
        workspace = await create_workspace()

        async with get_session() as session:
            entry = ACLEntry(
                workspace_id=workspace.id,
                team_id=None,
                user_id=user.id,
                permission="viewer",
            )
            session.add(entry)
            await session.flush()

        with pytest.raises(IntegrityError, match="uq_acl_entry_workspace_user"):
            async with get_session() as session:
                duplicate = ACLEntry(
                    workspace_id=workspace.id,
                    team_id=None,
                    user_id=user.id,
                    permission="editor",
                )
                session.add(duplicate)
                await session.flush()

    @pytest.mark.asyncio
    async def test_team_target_uniqueness_enforced(self) -> None:
        """Duplicate team-target (team_id, user_id) is rejected."""
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.users import create_user

        week = await _make_week("acl-dup-team")
        activity = await _make_wargame_activity(week.id)
        user = await create_user(
            email=f"wg-acl-dup-team-{uuid4().hex[:8]}@test.local",
            display_name="Dup Team ACL User",
        )

        async with get_session() as session:
            team = WargameTeam(activity_id=activity.id, codename="Hotel")
            session.add(team)
            await session.flush()
            team_id = team.id

            first = ACLEntry(
                workspace_id=None,
                team_id=team_id,
                user_id=user.id,
                permission="viewer",
            )
            session.add(first)
            await session.flush()

        with pytest.raises(IntegrityError, match="uq_acl_entry_team_user"):
            async with get_session() as session:
                duplicate = ACLEntry(
                    workspace_id=None,
                    team_id=team_id,
                    user_id=user.id,
                    permission="editor",
                )
                session.add(duplicate)
                await session.flush()

    @pytest.mark.asyncio
    async def test_deleting_team_cascades_team_acl_entries(self) -> None:
        """Team-target ACL rows cascade-delete with their team."""
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.users import create_user

        week = await _make_week("acl-team-cascade")
        activity = await _make_wargame_activity(week.id)
        user = await create_user(
            email=f"wg-acl-cascade-{uuid4().hex[:8]}@test.local",
            display_name="Cascade Team ACL User",
        )

        async with get_session() as session:
            team = WargameTeam(activity_id=activity.id, codename="India")
            session.add(team)
            await session.flush()
            team_id = team.id

            entry = ACLEntry(
                workspace_id=None,
                team_id=team.id,
                user_id=user.id,
                permission="viewer",
            )
            session.add(entry)
            await session.flush()
            entry_id = entry.id

        async with get_session() as session:
            team_row = await session.get(WargameTeam, team_id)
            assert team_row is not None
            await session.delete(team_row)

        async with get_session() as session:
            remaining = await session.get(ACLEntry, entry_id)
            assert remaining is None

    @pytest.mark.asyncio
    async def test_list_entries_for_user_returns_workspace_and_team_targets(
        self,
    ) -> None:
        """list_entries_for_user should include both workspace and team ACL rows."""
        from promptgrimoire.db.acl import list_entries_for_user
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace

        week = await _make_week("acl-list-user")
        activity = await _make_wargame_activity(week.id)
        user = await create_user(
            email=f"wg-acl-list-user-{uuid4().hex[:8]}@test.local",
            display_name="List User ACL User",
        )
        workspace = await create_workspace()

        async with get_session() as session:
            team = WargameTeam(activity_id=activity.id, codename="Juliet")
            session.add(team)
            await session.flush()

            session.add(
                ACLEntry(
                    workspace_id=workspace.id,
                    team_id=None,
                    user_id=user.id,
                    permission="viewer",
                )
            )
            session.add(
                ACLEntry(
                    workspace_id=None,
                    team_id=team.id,
                    user_id=user.id,
                    permission="viewer",
                )
            )
            await session.flush()

        entries = await list_entries_for_user(user.id)
        assert len(entries) == 2
        workspace_targets = [
            entry for entry in entries if entry.workspace_id is not None
        ]
        team_targets = [entry for entry in entries if entry.team_id is not None]
        assert len(workspace_targets) == 1
        assert len(team_targets) == 1

    @pytest.mark.asyncio
    async def test_workspace_owner_subquery_ignores_team_entries(self) -> None:
        """Team ACL rows with NULL workspace_id must not break peer listing filters."""
        from promptgrimoire.db.acl import list_peer_workspaces
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace

        week = await _make_week("acl-null-subquery")
        activity = await _make_wargame_activity(week.id)
        user = await create_user(
            email=f"wg-acl-null-subquery-{uuid4().hex[:8]}@test.local",
            display_name="Null Subquery ACL User",
        )

        async with get_session() as session:
            team = WargameTeam(activity_id=activity.id, codename="Kilo")
            session.add(team)
            await session.flush()

            # Team ACL target intentionally has workspace_id NULL.
            session.add(
                ACLEntry(
                    workspace_id=None,
                    team_id=team.id,
                    user_id=user.id,
                    permission="owner",
                )
            )

            # Peer workspace candidate row.
            shared_workspace = await create_workspace()
            shared_workspace.activity_id = activity.id
            shared_workspace.shared_with_class = True
            session.add(shared_workspace)
            await session.flush()

        # Should not error and should still return rows rather than being
        # poisoned by NULL in the owned_subq.
        rows = await list_peer_workspaces(activity.id, user.id)
        assert isinstance(rows, list)
        assert len(rows) == 1
        assert rows[0].activity_id == activity.id

    @pytest.mark.asyncio
    async def test_workspace_owner_lookup_with_names_ignores_team_entries(self) -> None:
        """Owner-name peer listing must ignore team ACL rows with NULL workspace_id."""
        from promptgrimoire.db.acl import list_peer_workspaces_with_owners
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace

        week = await _make_week("acl-null-owner-subquery")
        activity = await _make_wargame_activity(week.id)
        requester = await create_user(
            email=f"wg-acl-null-owner-{uuid4().hex[:8]}@test.local",
            display_name="Null Owner Requester",
        )
        owner = await create_user(
            email=f"wg-acl-peer-owner-{uuid4().hex[:8]}@test.local",
            display_name="Peer Owner",
        )

        async with get_session() as session:
            team = WargameTeam(activity_id=activity.id, codename="Lima")
            session.add(team)
            await session.flush()

            session.add(
                ACLEntry(
                    workspace_id=None,
                    team_id=team.id,
                    user_id=requester.id,
                    permission="owner",
                )
            )

            shared_workspace = await create_workspace()
            shared_workspace.activity_id = activity.id
            shared_workspace.shared_with_class = True
            session.add(shared_workspace)
            await session.flush()

            session.add(
                ACLEntry(
                    workspace_id=shared_workspace.id,
                    team_id=None,
                    user_id=owner.id,
                    permission="owner",
                )
            )
            await session.flush()

        rows = await list_peer_workspaces_with_owners(activity.id, requester.id)
        assert len(rows) == 1
        workspace, display_name, owner_id = rows[0]
        assert workspace.activity_id == activity.id
        assert display_name == "Peer Owner"
        assert owner_id == owner.id
