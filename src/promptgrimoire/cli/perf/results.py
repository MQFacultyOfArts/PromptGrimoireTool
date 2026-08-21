"""Versioned verdicts and atomic result-envelope persistence."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

RESULT_SCHEMA_VERSION = 1


class PerfClassification(StrEnum):
    """Terminal meanings understood by the public performance harness."""

    PASS = "pass"  # noqa: S105 -- measurement verdict, not a password
    PASS_WITH_DEGRADATION = "pass_with_degradation"  # noqa: S105
    COLLAPSE = "collapse"
    INFRASTRUCTURE_FAILURE = "infrastructure_failure"
    INVALID_EVIDENCE = "invalid_evidence"


@dataclass(frozen=True, slots=True)
class MeasurementCounts:
    """Error counts retained independently of the probe verdict."""

    load_failures: int
    fatal_action_failures: int
    degraded_actions: int


@dataclass(frozen=True, slots=True)
class MeasuredVerdict:
    """A probe-owned verdict for a completed measurement window."""

    classification: PerfClassification
    reasons: tuple[str, ...]
    counts: MeasurementCounts

    def as_payload(self) -> dict[str, object]:
        """Return the stable JSON representation of this verdict."""
        return {
            "classification": self.classification.value,
            "reasons": list(self.reasons),
            "counts": asdict(self.counts),
        }


@dataclass(frozen=True, slots=True)
class ResultIdentity:
    """Campaign coordinates embedded by a campaign-run pytest process."""

    campaign_id: str | None = None
    leg_id: str | None = None
    attempt_id: str | None = None

    @classmethod
    def from_environment(cls) -> ResultIdentity:
        """Read the public campaign coordinates inherited by a probe."""
        return cls(
            campaign_id=os.environ.get("E2E_PERF_CAMPAIGN_ID"),
            leg_id=os.environ.get("E2E_PERF_LEG_ID"),
            attempt_id=os.environ.get("E2E_PERF_ATTEMPT_ID"),
        )

    def as_payload(self) -> dict[str, object]:
        """Return campaign identity, rejecting a partially configured run."""
        campaign = self.is_campaign()
        return {
            "mode": "campaign" if campaign else "standalone",
            "campaign_id": self.campaign_id,
            "leg_id": self.leg_id,
            "attempt_id": self.attempt_id,
        }

    def is_campaign(self) -> bool:
        """Return whether all campaign coordinates are present and coherent."""
        values = (self.campaign_id, self.leg_id, self.attempt_id)
        if any(values) and not all(values):
            raise ValueError("campaign result identity is only partially configured")
        return all(values)


def should_fail_pytest_for_verdict(
    classification: PerfClassification,
    *,
    identity: ResultIdentity | None = None,
) -> bool:
    """Keep standalone collapse gates red while campaigns classify envelopes."""
    execution = identity or ResultIdentity.from_environment()
    return classification is PerfClassification.COLLAPSE and not execution.is_campaign()


def reconcile_pytest_exit(
    measured: PerfClassification,
    exit_code: int,
) -> tuple[PerfClassification, tuple[str, ...]]:
    """Reject any failed pytest process after a completed measurement."""
    if exit_code != 0:
        return (
            PerfClassification.INFRASTRUCTURE_FAILURE,
            (f"completed measurement returned pytest exit {exit_code}",),
        )
    return measured, ()


def measured_verdict(
    *,
    load_failure_count: int,
    fatal_action_failure_count: int,
    degraded_action_count: int,
    collapse_reasons: tuple[str, ...],
) -> MeasuredVerdict:
    """Build a measured verdict without consulting pytest's exit status."""
    counts = MeasurementCounts(
        load_failures=load_failure_count,
        fatal_action_failures=fatal_action_failure_count,
        degraded_actions=degraded_action_count,
    )
    if any(value < 0 for value in asdict(counts).values()):
        raise ValueError("measurement counts cannot be negative")

    if collapse_reasons:
        classification = PerfClassification.COLLAPSE
    elif any(asdict(counts).values()):
        classification = PerfClassification.PASS_WITH_DEGRADATION
    else:
        classification = PerfClassification.PASS
    return MeasuredVerdict(
        classification=classification,
        reasons=collapse_reasons,
        counts=counts,
    )


def write_result_envelope(
    path: Path,
    *,
    verdict: MeasuredVerdict,
    probe_payload: Mapping[str, object],
    identity: ResultIdentity | None = None,
) -> None:
    """Atomically write one versioned measurement result beside its target."""
    reserved = {"schema_version", "execution", "verdict"}.intersection(probe_payload)
    if reserved:
        names = ", ".join(sorted(reserved))
        raise ValueError(f"probe payload uses reserved result fields: {names}")

    payload = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "execution": (identity or ResultIdentity.from_environment()).as_payload(),
        "verdict": verdict.as_payload(),
        **probe_payload,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(payload, temporary, indent=2, sort_keys=True)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path.replace(path)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise
