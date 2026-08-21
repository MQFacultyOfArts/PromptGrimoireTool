"""Tests for deterministic performance campaign schedules."""

from __future__ import annotations

import pytest

_SHA_A = "a" * 40
_SHA_B = "b" * 40


def test_abba_schedule_expands_at_each_parameter_level() -> None:
    """Every N receives the declared comparative order before moving on."""
    from promptgrimoire.cli.perf.campaign import (
        ArmDefinition,
        CampaignDefinition,
        resolve_schedule,
    )

    definition = CampaignDefinition(
        campaign_id="pool-abba",
        probe="soak_full_crud",
        target="local",
        parameter_name="sessions",
        levels=(25, 50),
        arms=(
            ArmDefinition(name="A", source_identity=_SHA_A),
            ArmDefinition(name="B", source_identity=_SHA_B),
        ),
        arm_pattern=("A", "B", "B", "A"),
    )

    schedule = resolve_schedule(definition)

    assert [(leg.parameter_value, leg.arm) for leg in schedule.legs] == [
        (25, "A"),
        (25, "B"),
        (25, "B"),
        (25, "A"),
        (50, "A"),
        (50, "B"),
        (50, "B"),
        (50, "A"),
    ]
    assert [leg.source_identity for leg in schedule.legs] == [
        _SHA_A,
        _SHA_B,
        _SHA_B,
        _SHA_A,
        _SHA_A,
        _SHA_B,
        _SHA_B,
        _SHA_A,
    ]
    assert len({leg.leg_id for leg in schedule.legs}) == 8


def test_repetitions_have_stable_unique_leg_ids() -> None:
    """Repeating a schedule never reuses or randomly changes leg identity."""
    from promptgrimoire.cli.perf.campaign import (
        ArmDefinition,
        CampaignDefinition,
        resolve_schedule,
    )

    definition = CampaignDefinition(
        campaign_id="repeat",
        probe="soak_full_crud",
        target="local",
        parameter_name="sessions",
        levels=(25,),
        arms=(ArmDefinition(name="baseline", source_identity=_SHA_A),),
        arm_pattern=("baseline",),
        repetitions=3,
    )

    first = resolve_schedule(definition)
    second = resolve_schedule(definition)

    assert [leg.repetition for leg in first.legs] == [1, 2, 3]
    assert [leg.leg_id for leg in first.legs] == [leg.leg_id for leg in second.legs]
    assert len({leg.leg_id for leg in first.legs}) == 3


def test_explicit_schedule_preserves_irregular_intent() -> None:
    """Intentional non-cartesian legs remain in their declared order."""
    from promptgrimoire.cli.perf.campaign import (
        ArmDefinition,
        CampaignDefinition,
        ExplicitLeg,
        resolve_schedule,
    )

    definition = CampaignDefinition(
        campaign_id="irregular",
        probe="soak_full_crud",
        target="local",
        parameter_name="sessions",
        arms=(
            ArmDefinition(name="A", source_identity=_SHA_A),
            ArmDefinition(name="B", source_identity=_SHA_B),
        ),
        explicit_legs=(
            ExplicitLeg(parameter_value=10, arm="B"),
            ExplicitLeg(parameter_value=75, arm="A"),
            ExplicitLeg(parameter_value=25, arm="B"),
        ),
    )

    schedule = resolve_schedule(definition)

    assert [(leg.parameter_value, leg.arm) for leg in schedule.legs] == [
        (10, "B"),
        (75, "A"),
        (25, "B"),
    ]


def test_schedule_round_trip_does_not_regenerate_current_defaults() -> None:
    """The persisted resolved order is sufficient for exact resume."""
    from promptgrimoire.cli.perf.campaign import (
        ArmDefinition,
        CampaignDefinition,
        CampaignSchedule,
        resolve_schedule,
    )

    definition = CampaignDefinition(
        campaign_id="round-trip",
        probe="soak_full_crud",
        target="local",
        parameter_name="sessions",
        levels=(25, 50),
        arms=(ArmDefinition(name="A", source_identity=_SHA_A),),
        arm_pattern=("A",),
    )
    schedule = resolve_schedule(definition)

    restored = CampaignSchedule.from_payload(schedule.as_payload())

    assert restored == schedule


def test_campaign_summary_groups_arms_without_erasing_run_order() -> None:
    """ABBA reporting retains each leg and within-arm outcome spread."""
    from promptgrimoire.cli.perf.campaign import (
        ArmDefinition,
        CampaignDefinition,
        resolve_schedule,
    )
    from promptgrimoire.cli.perf.summary import summarise_campaign

    schedule = resolve_schedule(
        CampaignDefinition(
            campaign_id="summary-abba",
            probe="soak_full_crud",
            target="local",
            parameter_name="sessions",
            levels=(25,),
            arms=(
                ArmDefinition(name="A", source_identity=_SHA_A),
                ArmDefinition(name="B", source_identity=_SHA_B),
            ),
            arm_pattern=("A", "B", "B", "A"),
        )
    )
    records = {
        leg.leg_id: {
            "attempt_id": f"attempt-{leg.index:04d}",
            "classification": ("pass_with_degradation" if leg.index == 3 else "pass"),
        }
        for leg in schedule.legs
    }

    summary = summarise_campaign(schedule, records)

    assert [leg["arm"] for leg in summary["legs"]] == ["A", "B", "B", "A"]
    assert summary["groups"] == [
        {
            "parameter_value": 25,
            "arm": "A",
            "outcomes": ["pass", "pass"],
            "attempt_ids": ["attempt-0001", "attempt-0004"],
        },
        {
            "parameter_value": 25,
            "arm": "B",
            "outcomes": ["pass", "pass_with_degradation"],
            "attempt_ids": ["attempt-0002", "attempt-0003"],
        },
    ]


@pytest.mark.parametrize(
    ("campaign_id", "parameter_name"),
    [
        (".", "sessions"),
        ("..", "sessions"),
        ("safe", "../../../escaped"),
    ],
)
def test_campaign_paths_reject_dot_segments_and_separators(
    campaign_id: str,
    parameter_name: str,
) -> None:
    """User-controlled schedule fields cannot escape the campaign root."""
    from promptgrimoire.cli.perf.campaign import ArmDefinition, CampaignDefinition

    with pytest.raises(ValueError, match=r"campaign_id|parameter_name"):
        CampaignDefinition(
            campaign_id=campaign_id,
            probe="soak_full_crud",
            target="local",
            parameter_name=parameter_name,
            levels=(1,),
            arms=(ArmDefinition(name="A", source_identity=_SHA_A),),
            arm_pattern=("A",),
        )


@pytest.mark.parametrize(
    ("arm_pattern", "repetitions"),
    [
        (("A",), 1),
        ((), 2),
    ],
)
def test_explicit_leg_schedule_rejects_silently_ignored_sweep_fields(
    arm_pattern: tuple[str, ...],
    repetitions: int,
) -> None:
    """Irregular intent cannot contain knobs that resolution would ignore."""
    from promptgrimoire.cli.perf.campaign import (
        ArmDefinition,
        CampaignDefinition,
        ExplicitLeg,
    )

    with pytest.raises(ValueError, match="explicit_legs"):
        CampaignDefinition(
            campaign_id="explicit",
            probe="soak_full_crud",
            target="local",
            parameter_name="sessions",
            arms=(ArmDefinition(name="A", source_identity=_SHA_A),),
            arm_pattern=arm_pattern,
            repetitions=repetitions,
            explicit_legs=(ExplicitLeg(parameter_value=1, arm="A"),),
        )


@pytest.mark.parametrize("source_identity", ["", "main", "abcdef0", "g" * 40])
def test_campaign_arms_require_a_full_immutable_git_identity(
    source_identity: str,
) -> None:
    """A moving ref or abbreviated commit cannot define a comparative arm."""
    from promptgrimoire.cli.perf.campaign import ArmDefinition

    with pytest.raises(ValueError, match="source_identity"):
        ArmDefinition(name="A", source_identity=source_identity)
