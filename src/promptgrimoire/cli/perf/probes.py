"""Fixed registry of real performance probes supported by campaigns."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ProbeSpec:
    """Typed invocation fields for one repository performance probe."""

    name: str
    test_path: Path
    parameter_name: str
    parameter_env: str
    result_env: str
    campaign_ready: bool


PROBES: dict[str, ProbeSpec] = {
    "soak_full_crud": ProbeSpec(
        name="soak_full_crud",
        test_path=Path("tests/e2e/test_soak_full_crud_load.py"),
        parameter_name="sessions",
        parameter_env="E2E_SOAK_SESSIONS",
        result_env="E2E_SOAK_DIAG_PATH",
        campaign_ready=True,
    ),
    "assessment_cram": ProbeSpec(
        name="assessment_cram",
        test_path=Path("tests/e2e/test_assessment_cram_load.py"),
        parameter_name="sessions",
        parameter_env="E2E_CRAM_SESSIONS",
        result_env="E2E_CRAM_DIAG_PATH",
        campaign_ready=True,
    ),
    "thundering_herd": ProbeSpec(
        name="thundering_herd",
        test_path=Path("tests/e2e/test_thundering_herd.py"),
        parameter_name="sessions",
        parameter_env="E2E_HERD_SESSIONS",
        result_env="E2E_HERD_DIAG_PATH",
        campaign_ready=True,
    ),
}


def get_probe(name: str, *, require_campaign_ready: bool = True) -> ProbeSpec:
    """Resolve one known probe and reject incomplete result migrations."""
    try:
        probe = PROBES[name]
    except KeyError as exc:
        available = ", ".join(sorted(PROBES))
        raise ValueError(
            f"unknown performance probe {name!r}; choose {available}"
        ) from exc
    if require_campaign_ready and not probe.campaign_ready:
        raise ValueError(
            f"performance probe {name!r} has not migrated to result envelopes"
        )
    return probe
