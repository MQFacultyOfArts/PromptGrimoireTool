"""Descriptive campaign summaries that preserve exact comparative order."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

    from promptgrimoire.cli.perf.campaign import CampaignSchedule


def summarise_campaign(
    schedule: CampaignSchedule,
    records: Mapping[str, Mapping[str, object]],
) -> dict[str, Any]:
    """Group outcomes by N and arm while retaining every ordered leg."""
    legs: list[dict[str, object]] = []
    grouped: dict[tuple[int, str], dict[str, object]] = {}
    for leg in schedule.legs:
        record = records.get(leg.leg_id, {})
        classification = str(record.get("classification", "incomplete"))
        attempt_id = record.get("attempt_id")
        legs.append(
            {
                "index": leg.index,
                "leg_id": leg.leg_id,
                "parameter_value": leg.parameter_value,
                "arm": leg.arm,
                "repetition": leg.repetition,
                "classification": classification,
                "attempt_id": attempt_id,
            }
        )
        key = (leg.parameter_value, leg.arm)
        group = grouped.setdefault(
            key,
            {
                "parameter_value": leg.parameter_value,
                "arm": leg.arm,
                "outcomes": [],
                "attempt_ids": [],
            },
        )
        outcomes = group["outcomes"]
        attempt_ids = group["attempt_ids"]
        if not isinstance(outcomes, list) or not isinstance(attempt_ids, list):
            raise ValueError("campaign summary group was internally corrupted")
        outcomes.append(classification)
        attempt_ids.append(attempt_id)
    return {
        "schema_version": 1,
        "campaign_id": schedule.definition.campaign_id,
        "probe": schedule.definition.probe,
        "parameter_name": schedule.definition.parameter_name,
        "legs": legs,
        "groups": list(grouped.values()),
    }
