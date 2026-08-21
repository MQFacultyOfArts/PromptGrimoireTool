"""Tests for performance-run identity and result contracts."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path


def test_prepared_database_context_carries_identity_into_the_harness() -> None:
    """Preparation provenance is explicit and inherited by pytest workers."""
    from promptgrimoire.cli._shared import PreparedTestDatabase

    prepared = PreparedTestDatabase.from_urls(
        test_database_url="postgresql+asyncpg://runner@db:5432/perf_soak",
        clone_source_url=("postgresql+asyncpg://runner@db:5432/perf_soak_clone_source"),
        preparation_id="prep-123",
    )

    assert prepared.database_name == "perf_soak"
    assert prepared.preparation_id == "prep-123"
    assert prepared.harness_env() == {
        "DATABASE__URL": "postgresql+asyncpg://runner@db:5432/perf_soak",
        "_PROMPTGRIMOIRE_USE_NULL_POOL": "1",
        "_CLONE_TEST_SOURCE_URL": (
            "postgresql+asyncpg://runner@db:5432/perf_soak_clone_source"
        ),
        "_PROMPTGRIMOIRE_DATABASE_PREPARATION_ID": "prep-123",
    }


def test_database_identity_accepts_direct_and_pooled_urls_for_same_database() -> None:
    """Transport and credentials may differ without changing DB identity."""
    from promptgrimoire.cli.perf.models import verify_database_identity

    assert (
        verify_database_identity(
            direct_url="postgresql+asyncpg://runner@db:5432/perf_soak",
            pooled_url="postgresql+asyncpg://server@db:6432/perf_soak?ssl=disable",
            expected_database="perf_soak",
        )
        == "perf_soak"
    )


def test_database_identity_rejects_a_different_pooled_database() -> None:
    """A reachable server on the wrong database is invalid infrastructure."""
    from promptgrimoire.cli.perf.models import (
        DatabaseIdentityMismatch,
        verify_database_identity,
    )

    with pytest.raises(DatabaseIdentityMismatch, match=r"pooled.*other_database"):
        verify_database_identity(
            direct_url="postgresql+asyncpg://runner@db:5432/perf_soak",
            pooled_url="postgresql+asyncpg://server@db:6432/other_database",
            expected_database="perf_soak",
        )


def test_target_attestation_requires_fresh_boot_database_query_and_source() -> None:
    """A health response alone cannot attest the process being measured."""
    from promptgrimoire.cli.perf.models import (
        TargetExpectation,
        validate_target_attestation,
    )

    identity = validate_target_attestation(
        {
            "boot_id": "boot-1",
            "pid": 321,
            "source_identity": "a" * 40,
            "database_name": "perf_soak",
            "database_query_ok": True,
            "preparation_id": "prep-1",
            "pool_mode_reason": "pool_fidelity",
        },
        expected=TargetExpectation(
            boot_id="boot-1",
            source_identity="a" * 40,
            database_name="perf_soak",
            preparation_id="prep-1",
            pool_mode_reason="pool_fidelity",
        ),
    )

    assert identity.pid == 321
    assert identity.database_name == "perf_soak"


def test_target_attestation_rejects_a_failed_database_query() -> None:
    """A live HTTP process with an unusable DB is infrastructure failure."""
    from promptgrimoire.cli.perf.models import (
        TargetAttestationError,
        TargetExpectation,
        validate_target_attestation,
    )

    with pytest.raises(TargetAttestationError, match="database query"):
        validate_target_attestation(
            {
                "boot_id": "boot-1",
                "pid": 321,
                "source_identity": "a" * 40,
                "database_name": "perf_soak",
                "database_query_ok": False,
                "preparation_id": "prep-1",
                "pool_mode_reason": "pool_fidelity",
            },
            expected=TargetExpectation(
                boot_id="boot-1",
                source_identity="a" * 40,
                database_name="perf_soak",
                preparation_id="prep-1",
                pool_mode_reason="pool_fidelity",
            ),
        )


@pytest.mark.parametrize(
    ("fatal_actions", "degraded_actions", "expected"),
    [
        (0, 0, "pass"),
        (1, 0, "pass_with_degradation"),
        (0, 3, "pass_with_degradation"),
    ],
)
def test_measured_verdict_never_describes_nonzero_errors_as_clean(
    fatal_actions: int,
    degraded_actions: int,
    expected: str,
) -> None:
    """Any tolerated action error remains visible in the verdict."""
    from promptgrimoire.cli.perf.results import measured_verdict

    verdict = measured_verdict(
        load_failure_count=0,
        fatal_action_failure_count=fatal_actions,
        degraded_action_count=degraded_actions,
        collapse_reasons=(),
    )

    assert verdict.classification.value == expected


def test_measured_verdict_records_a_systemic_collapse() -> None:
    """An explicit probe boundary, not pytest's exit code, identifies collapse."""
    from promptgrimoire.cli.perf.results import measured_verdict

    verdict = measured_verdict(
        load_failure_count=12,
        fatal_action_failure_count=40,
        degraded_action_count=2,
        collapse_reasons=("12 sessions failed to load", "systemic action failures"),
    )

    assert verdict.classification.value == "collapse"
    assert verdict.reasons == (
        "12 sessions failed to load",
        "systemic action failures",
    )


def test_result_envelope_is_versioned_atomic_and_preserves_probe_payload(
    tmp_path: Path,
) -> None:
    """A completed measurement has one parseable verdict-bearing artifact."""
    from promptgrimoire.cli.perf.results import measured_verdict, write_result_envelope

    path = tmp_path / "probe.json"
    verdict = measured_verdict(
        load_failure_count=0,
        fatal_action_failure_count=0,
        degraded_action_count=4,
        collapse_reasons=(),
    )

    write_result_envelope(
        path,
        verdict=verdict,
        probe_payload={"sessions": 25, "results": [{"email": "a@example.test"}]},
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["verdict"]["classification"] == "pass_with_degradation"
    assert payload["verdict"]["counts"]["degraded_actions"] == 4
    assert payload["sessions"] == 25
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize(
    "measured",
    ["pass", "pass_with_degradation", "collapse"],
)
def test_completed_measurement_requires_a_successful_pytest_process(
    measured: str,
) -> None:
    """A teardown/config failure cannot borrow a probe's measured verdict."""
    from promptgrimoire.cli.perf.results import (
        PerfClassification,
        reconcile_pytest_exit,
    )

    classification = PerfClassification(measured)

    assert reconcile_pytest_exit(classification, 0) == (classification, ())
    assert reconcile_pytest_exit(classification, 1) == (
        PerfClassification.INFRASTRUCTURE_FAILURE,
        ("completed measurement returned pytest exit 1",),
    )


def test_collapse_fails_standalone_pytest_but_not_a_campaign_process() -> None:
    """Campaigns classify envelopes; standalone probe runs retain red gates."""
    from promptgrimoire.cli.perf.results import (
        PerfClassification,
        ResultIdentity,
        should_fail_pytest_for_verdict,
    )

    standalone = ResultIdentity()
    campaign = ResultIdentity(
        campaign_id="campaign",
        leg_id="leg-1",
        attempt_id="attempt-1",
    )

    assert should_fail_pytest_for_verdict(
        PerfClassification.COLLAPSE,
        identity=standalone,
    )
    assert not should_fail_pytest_for_verdict(
        PerfClassification.COLLAPSE,
        identity=campaign,
    )
    assert not should_fail_pytest_for_verdict(
        PerfClassification.PASS,
        identity=standalone,
    )
