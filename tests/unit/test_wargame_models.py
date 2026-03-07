"""Unit tests for wargame-related SQLModel validation rules."""

from __future__ import annotations

from datetime import time, timedelta
from uuid import uuid4

import pytest

from promptgrimoire.db.models import ACLEntry, Activity, WargameConfig, WargameTeam

_WEEK_ID = uuid4()
_WORKSPACE_ID = uuid4()
_USER_ID = uuid4()
_ACTIVITY_ID = uuid4()
_TEAM_ID = uuid4()


class TestActivityTypeValidation:
    """Verify Activity type/template invariants at model level."""

    def test_activity_rejects_unknown_type(self) -> None:
        """Activity type must stay within the known discriminator domain."""
        with pytest.raises(
            ValueError, match="activity type must be 'annotation' or 'wargame'"
        ):
            Activity.model_validate(
                {
                    "week_id": _WEEK_ID,
                    "title": "Unknown",
                    "type": "unknown",
                    "template_workspace_id": _WORKSPACE_ID,
                }
            )

    def test_annotation_activity_requires_template_workspace(self) -> None:
        """Annotation activity must define template_workspace_id."""
        with pytest.raises(
            ValueError, match="annotation activities require template_workspace_id"
        ):
            Activity.model_validate(
                {
                    "week_id": _WEEK_ID,
                    "title": "Annotation",
                    "type": "annotation",
                }
            )

    def test_wargame_activity_must_not_define_template_workspace(self) -> None:
        """Wargame activity must not define template_workspace_id."""
        with pytest.raises(
            ValueError, match="wargame activities must not set template_workspace_id"
        ):
            Activity.model_validate(
                {
                    "week_id": _WEEK_ID,
                    "template_workspace_id": _WORKSPACE_ID,
                    "title": "Wargame",
                    "type": "wargame",
                }
            )


class TestWargameConfigValidation:
    """Verify timer exclusivity for WargameConfig."""

    def test_accepts_timer_delta_only(self) -> None:
        """timer_delta set and timer_wall_clock unset is valid."""
        config = WargameConfig.model_validate(
            {
                "activity_id": _ACTIVITY_ID,
                "system_prompt": "System prompt",
                "scenario_bootstrap": "Scenario bootstrap",
                "timer_delta": timedelta(minutes=15),
                "timer_wall_clock": None,
            }
        )
        assert config.activity_type == "wargame"
        assert config.timer_delta == timedelta(minutes=15)
        assert config.timer_wall_clock is None

    def test_accepts_timer_wall_clock_only(self) -> None:
        """timer_wall_clock set and timer_delta unset is valid."""
        config = WargameConfig.model_validate(
            {
                "activity_id": _ACTIVITY_ID,
                "system_prompt": "System prompt",
                "scenario_bootstrap": "Scenario bootstrap",
                "timer_delta": None,
                "timer_wall_clock": time(hour=9, minute=30),
            }
        )
        assert config.activity_type == "wargame"
        assert config.timer_delta is None
        assert config.timer_wall_clock == time(hour=9, minute=30)

    def test_accepts_explicit_wargame_activity_type(self) -> None:
        """Explicit wargame discriminator remains valid."""
        config = WargameConfig.model_validate(
            {
                "activity_id": _ACTIVITY_ID,
                "activity_type": "wargame",
                "system_prompt": "System prompt",
                "scenario_bootstrap": "Scenario bootstrap",
                "timer_delta": timedelta(minutes=15),
                "timer_wall_clock": None,
            }
        )
        assert config.activity_type == "wargame"

    def test_rejects_both_timer_fields_unset(self) -> None:
        """Exactly one timer field must be set."""
        with pytest.raises(
            ValueError, match="exactly one of timer_delta or timer_wall_clock"
        ):
            WargameConfig.model_validate(
                {
                    "activity_id": _ACTIVITY_ID,
                    "system_prompt": "System prompt",
                    "scenario_bootstrap": "Scenario bootstrap",
                    "timer_delta": None,
                    "timer_wall_clock": None,
                }
            )

    def test_rejects_both_timer_fields_set(self) -> None:
        """Exactly one timer field must be set."""
        with pytest.raises(
            ValueError, match="exactly one of timer_delta or timer_wall_clock"
        ):
            WargameConfig.model_validate(
                {
                    "activity_id": _ACTIVITY_ID,
                    "system_prompt": "System prompt",
                    "scenario_bootstrap": "Scenario bootstrap",
                    "timer_delta": timedelta(minutes=10),
                    "timer_wall_clock": time(hour=10, minute=0),
                }
            )

    def test_rejects_non_wargame_activity_type(self) -> None:
        """The child discriminator must stay fixed at wargame."""
        with pytest.raises(
            ValueError, match="wargame config activity_type must be 'wargame'"
        ):
            WargameConfig.model_validate(
                {
                    "activity_id": _ACTIVITY_ID,
                    "activity_type": "annotation",
                    "system_prompt": "System prompt",
                    "scenario_bootstrap": "Scenario bootstrap",
                    "timer_delta": timedelta(minutes=10),
                    "timer_wall_clock": None,
                }
            )


class TestWargameTeamValidation:
    """Verify WargameTeam discriminator defaults and validation."""

    def test_defaults_activity_type_to_wargame(self) -> None:
        """WargameTeam should default its child discriminator."""
        team = WargameTeam.model_validate(
            {
                "activity_id": _ACTIVITY_ID,
                "codename": "Alpha",
            }
        )
        assert team.activity_type == "wargame"

    def test_rejects_non_wargame_activity_type(self) -> None:
        """The child discriminator must stay fixed at wargame."""
        with pytest.raises(
            ValueError, match="wargame team activity_type must be 'wargame'"
        ):
            WargameTeam.model_validate(
                {
                    "activity_id": _ACTIVITY_ID,
                    "activity_type": "annotation",
                    "codename": "Alpha",
                }
            )


class TestAclEntryTargetValidation:
    """Verify ACL target exclusivity at model level."""

    def test_workspace_target_is_valid(self) -> None:
        """Workspace ACL entry with team_id omitted is valid."""
        entry = ACLEntry.model_validate(
            {
                "workspace_id": _WORKSPACE_ID,
                "team_id": None,
                "user_id": _USER_ID,
                "permission": "viewer",
            }
        )
        assert entry.workspace_id == _WORKSPACE_ID
        assert entry.team_id is None

    def test_team_target_is_valid(self) -> None:
        """Team ACL entry with workspace_id omitted is valid."""
        entry = ACLEntry.model_validate(
            {
                "workspace_id": None,
                "team_id": _TEAM_ID,
                "user_id": _USER_ID,
                "permission": "viewer",
            }
        )
        assert entry.workspace_id is None
        assert entry.team_id == _TEAM_ID

    def test_rejects_both_workspace_and_team_targets(self) -> None:
        """Exactly one target FK must be set."""
        with pytest.raises(ValueError, match="exactly one of workspace_id or team_id"):
            ACLEntry.model_validate(
                {
                    "workspace_id": _WORKSPACE_ID,
                    "team_id": _TEAM_ID,
                    "user_id": _USER_ID,
                    "permission": "viewer",
                }
            )

    def test_rejects_missing_workspace_and_team_targets(self) -> None:
        """Exactly one target FK must be set."""
        with pytest.raises(ValueError, match="exactly one of workspace_id or team_id"):
            ACLEntry.model_validate(
                {
                    "workspace_id": None,
                    "team_id": None,
                    "user_id": _USER_ID,
                    "permission": "viewer",
                }
            )
