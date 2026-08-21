"""Deterministic performance campaign definitions and resolved schedules."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

CAMPAIGN_SCHEMA_VERSION = 1
_ID_CHARACTERS = re.compile(r"[^a-zA-Z0-9_.-]+")
_FULL_GIT_IDENTITY = re.compile(r"[0-9a-f]{40}")


def _is_safe_path_component(value: str) -> bool:
    """Return whether one persisted identifier is a non-traversing component."""
    return bool(value) and value not in {".", ".."} and not _ID_CHARACTERS.search(value)


class StopPolicy(StrEnum):
    """When a campaign may stop before exhausting its resolved schedule."""

    COMPLETE_SCHEDULE = "complete_schedule"
    STOP_ON_VALID_COLLAPSE = "stop_on_valid_collapse"


@dataclass(frozen=True, slots=True)
class ArmDefinition:
    """One named comparative arm and its pinned source identity."""

    name: str
    source_identity: str
    overrides: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        """Require the immutable full commit attested by managed targets."""
        if not _FULL_GIT_IDENTITY.fullmatch(self.source_identity):
            raise ValueError("source_identity must be a full 40-character git commit")

    def as_payload(self) -> dict[str, object]:
        """Return a stable JSON representation."""
        return {
            "name": self.name,
            "source_identity": self.source_identity,
            "overrides": dict(self.overrides),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> ArmDefinition:
        """Restore an arm from a persisted campaign definition."""
        overrides = payload.get("overrides", {})
        if not isinstance(overrides, dict):
            raise ValueError("arm overrides must be an object")
        return cls(
            name=str(payload["name"]),
            source_identity=str(payload["source_identity"]),
            overrides=tuple(
                sorted((str(key), str(value)) for key, value in overrides.items())
            ),
        )


@dataclass(frozen=True, slots=True)
class ExplicitLeg:
    """One deliberately ordered non-cartesian campaign leg."""

    parameter_value: int
    arm: str
    overrides: tuple[tuple[str, str], ...] = ()

    def as_payload(self) -> dict[str, object]:
        """Return a stable JSON representation."""
        return {
            "parameter_value": self.parameter_value,
            "arm": self.arm,
            "overrides": dict(self.overrides),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> ExplicitLeg:
        """Restore one explicit leg declaration."""
        overrides = payload.get("overrides", {})
        if not isinstance(overrides, dict):
            raise ValueError("explicit leg overrides must be an object")
        return cls(
            parameter_value=int(payload["parameter_value"]),
            arm=str(payload["arm"]),
            overrides=tuple(
                sorted((str(key), str(value)) for key, value in overrides.items())
            ),
        )


@dataclass(frozen=True, slots=True)
class CampaignDefinition:
    """Human-declared campaign intent before deterministic expansion."""

    campaign_id: str
    probe: str
    target: str
    parameter_name: str
    arms: tuple[ArmDefinition, ...]
    levels: tuple[int, ...] = ()
    arm_pattern: tuple[str, ...] = ()
    repetitions: int = 1
    explicit_legs: tuple[ExplicitLeg, ...] = ()
    stop_policy: StopPolicy = StopPolicy.COMPLETE_SCHEDULE

    def __post_init__(self) -> None:
        """Reject definitions whose intended order is ambiguous."""
        _validate_campaign_identifiers(self)
        _validate_campaign_schedule(self)
        _validate_campaign_arms(self)

    def as_payload(self) -> dict[str, object]:
        """Return a stable JSON representation of declared intent."""
        return {
            "campaign_id": self.campaign_id,
            "probe": self.probe,
            "target": self.target,
            "parameter_name": self.parameter_name,
            "levels": list(self.levels),
            "arms": [arm.as_payload() for arm in self.arms],
            "arm_pattern": list(self.arm_pattern),
            "repetitions": self.repetitions,
            "explicit_legs": [leg.as_payload() for leg in self.explicit_legs],
            "stop_policy": self.stop_policy.value,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> CampaignDefinition:
        """Restore declared intent from a persisted schedule."""
        return cls(
            campaign_id=str(payload["campaign_id"]),
            probe=str(payload["probe"]),
            target=str(payload["target"]),
            parameter_name=str(payload["parameter_name"]),
            levels=tuple(int(value) for value in payload.get("levels", [])),
            arms=tuple(ArmDefinition.from_payload(arm) for arm in payload["arms"]),
            arm_pattern=tuple(str(name) for name in payload.get("arm_pattern", [])),
            repetitions=int(payload.get("repetitions", 1)),
            explicit_legs=tuple(
                ExplicitLeg.from_payload(leg)
                for leg in payload.get("explicit_legs", [])
            ),
            stop_policy=StopPolicy(
                payload.get("stop_policy", StopPolicy.COMPLETE_SCHEDULE.value)
            ),
        )


def _validate_campaign_identifiers(definition: CampaignDefinition) -> None:
    """Reject missing or unsafe persisted campaign identifiers."""
    if not _is_safe_path_component(definition.campaign_id):
        raise ValueError(
            "campaign_id must contain only letters, numbers, ._- characters"
        )
    if not definition.probe or not definition.target or not definition.parameter_name:
        raise ValueError("probe, target, and parameter_name are required")
    if not _is_safe_path_component(definition.parameter_name):
        raise ValueError(
            "parameter_name must contain only letters, numbers, ._- characters"
        )


def _validate_campaign_schedule(definition: CampaignDefinition) -> None:
    """Reject ambiguous sweep and explicit-leg combinations."""
    if definition.repetitions < 1:
        raise ValueError("repetitions must be positive")
    if bool(definition.explicit_legs) == bool(definition.levels):
        raise ValueError("declare either levels or explicit_legs")
    if definition.explicit_legs and (
        definition.arm_pattern or definition.repetitions != 1
    ):
        raise ValueError(
            "explicit_legs cannot be combined with arm_pattern or repetitions"
        )


def _validate_campaign_arms(definition: CampaignDefinition) -> None:
    """Reject missing, duplicate, unknown, or non-positive scheduled arms."""
    arm_names = [arm.name for arm in definition.arms]
    if not arm_names or len(set(arm_names)) != len(arm_names):
        raise ValueError("arm names must be present and unique")
    selected_arms = (
        [leg.arm for leg in definition.explicit_legs]
        if definition.explicit_legs
        else list(definition.arm_pattern)
    )
    if not selected_arms:
        raise ValueError("arm_pattern is required for a level sweep")
    unknown = sorted(set(selected_arms).difference(arm_names))
    if unknown:
        raise ValueError(f"unknown campaign arm(s): {', '.join(unknown)}")
    values = (
        [leg.parameter_value for leg in definition.explicit_legs]
        if definition.explicit_legs
        else list(definition.levels)
    )
    if any(value < 1 for value in values):
        raise ValueError("campaign parameter values must be positive")


@dataclass(frozen=True, slots=True)
class ResolvedLeg:
    """One immutable measurement unit in exact execution order."""

    index: int
    leg_id: str
    parameter_name: str
    parameter_value: int
    arm: str
    repetition: int
    pattern_position: int
    source_identity: str
    overrides: tuple[tuple[str, str], ...]

    def as_payload(self) -> dict[str, object]:
        """Return a stable JSON representation."""
        return {
            "index": self.index,
            "leg_id": self.leg_id,
            "parameter_name": self.parameter_name,
            "parameter_value": self.parameter_value,
            "arm": self.arm,
            "repetition": self.repetition,
            "pattern_position": self.pattern_position,
            "source_identity": self.source_identity,
            "overrides": dict(self.overrides),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> ResolvedLeg:
        """Restore one already-resolved campaign leg."""
        overrides = payload.get("overrides", {})
        if not isinstance(overrides, dict):
            raise ValueError("resolved leg overrides must be an object")
        return cls(
            index=int(payload["index"]),
            leg_id=str(payload["leg_id"]),
            parameter_name=str(payload["parameter_name"]),
            parameter_value=int(payload["parameter_value"]),
            arm=str(payload["arm"]),
            repetition=int(payload["repetition"]),
            pattern_position=int(payload["pattern_position"]),
            source_identity=str(payload["source_identity"]),
            overrides=tuple(
                sorted((str(key), str(value)) for key, value in overrides.items())
            ),
        )


@dataclass(frozen=True, slots=True)
class CampaignSchedule:
    """Persisted definition and exact ordered legs used by resume."""

    definition: CampaignDefinition
    legs: tuple[ResolvedLeg, ...]
    schema_version: int = CAMPAIGN_SCHEMA_VERSION

    def as_payload(self) -> dict[str, object]:
        """Return the complete immutable campaign file payload."""
        return {
            "schema_version": self.schema_version,
            "definition": self.definition.as_payload(),
            "legs": [leg.as_payload() for leg in self.legs],
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> CampaignSchedule:
        """Restore a schedule without expanding current defaults."""
        version = int(payload["schema_version"])
        if version != CAMPAIGN_SCHEMA_VERSION:
            raise ValueError(f"unsupported campaign schema version: {version}")
        return cls(
            schema_version=version,
            definition=CampaignDefinition.from_payload(payload["definition"]),
            legs=tuple(ResolvedLeg.from_payload(leg) for leg in payload["legs"]),
        )


def _merged_overrides(
    arm: ArmDefinition,
    leg_overrides: tuple[tuple[str, str], ...],
) -> tuple[tuple[str, str], ...]:
    merged = dict(arm.overrides)
    merged.update(leg_overrides)
    return tuple(sorted(merged.items()))


def resolve_schedule(definition: CampaignDefinition) -> CampaignSchedule:
    """Expand declared intent into deterministic immutable campaign legs."""
    arms = {arm.name: arm for arm in definition.arms}
    resolved: list[ResolvedLeg] = []

    def append_leg(
        *,
        parameter_value: int,
        arm_name: str,
        repetition: int,
        pattern_position: int,
        overrides: tuple[tuple[str, str], ...] = (),
    ) -> None:
        arm = arms[arm_name]
        index = len(resolved) + 1
        safe_arm = _ID_CHARACTERS.sub("-", arm_name).strip("-") or "arm"
        leg_id = (
            f"leg-{index:04d}-{definition.parameter_name}-{parameter_value}-"
            f"{safe_arm}-r{repetition:02d}-p{pattern_position:02d}"
        )
        resolved.append(
            ResolvedLeg(
                index=index,
                leg_id=leg_id,
                parameter_name=definition.parameter_name,
                parameter_value=parameter_value,
                arm=arm_name,
                repetition=repetition,
                pattern_position=pattern_position,
                source_identity=arm.source_identity,
                overrides=_merged_overrides(arm, overrides),
            )
        )

    if definition.explicit_legs:
        for position, leg in enumerate(definition.explicit_legs, start=1):
            append_leg(
                parameter_value=leg.parameter_value,
                arm_name=leg.arm,
                repetition=1,
                pattern_position=position,
                overrides=leg.overrides,
            )
    else:
        for parameter_value in definition.levels:
            for repetition in range(1, definition.repetitions + 1):
                for position, arm_name in enumerate(definition.arm_pattern, start=1):
                    append_leg(
                        parameter_value=parameter_value,
                        arm_name=arm_name,
                        repetition=repetition,
                        pattern_position=position,
                    )

    return CampaignSchedule(definition=definition, legs=tuple(resolved))
