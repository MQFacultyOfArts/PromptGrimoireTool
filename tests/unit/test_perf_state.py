"""Tests for durable campaign attempts, validation, and resume."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path


def _schedule(*, levels: tuple[int, ...] = (25,)):
    from promptgrimoire.cli.perf.campaign import (
        ArmDefinition,
        CampaignDefinition,
        resolve_schedule,
    )

    return resolve_schedule(
        CampaignDefinition(
            campaign_id="state-test",
            probe="soak_full_crud",
            target="local",
            parameter_name="sessions",
            levels=levels,
            arms=(ArmDefinition(name="A", source_identity="a" * 40),),
            arm_pattern=("A",),
        )
    )


def _write_pass_result(path: Path) -> None:
    from promptgrimoire.cli.perf.results import (
        ResultIdentity,
        measured_verdict,
        write_result_envelope,
    )
    from promptgrimoire.cli.perf.state import write_json_atomic

    write_result_envelope(
        path,
        verdict=measured_verdict(
            load_failure_count=0,
            fatal_action_failure_count=0,
            degraded_action_count=0,
            collapse_reasons=(),
        ),
        probe_payload={"run_meta": {"probe": "soak_full_crud"}},
        identity=ResultIdentity(
            campaign_id="state-test",
            leg_id=path.parent.parent.name,
            attempt_id=path.parent.name,
        ),
    )
    write_json_atomic(
        path.with_name("validation.json"),
        {
            "schema_version": 1,
            "classification": "pass",
            "failures": [],
            "pytest_exit_code": 0,
        },
    )


def test_raw_probe_json_is_not_a_completed_leg(tmp_path: Path) -> None:
    """Artifact presence without a validated terminal record never resumes."""
    from promptgrimoire.cli.perf.state import CampaignStore

    schedule = _schedule()
    store = CampaignStore(tmp_path)
    store.initialise(schedule)
    attempt = store.begin_attempt(schedule.legs[0])
    _write_pass_result(attempt.path / "probe.json")

    assert store.first_incomplete_leg(schedule) == schedule.legs[0]


def test_terminal_publication_requires_the_executor_validation_record(
    tmp_path: Path,
) -> None:
    """A probe verdict alone cannot bypass target/evidence validation."""
    from promptgrimoire.cli.perf.results import PerfClassification
    from promptgrimoire.cli.perf.state import CampaignStateError, CampaignStore

    schedule = _schedule()
    leg = schedule.legs[0]
    store = CampaignStore(tmp_path)
    store.initialise(schedule)
    attempt = store.begin_attempt(leg)
    _write_pass_result(attempt.path / "probe.json")
    (attempt.path / "validation.json").unlink()

    with pytest.raises(CampaignStateError, match="validation"):
        store.finalise_leg(
            schedule,
            leg,
            attempt,
            classification=PerfClassification.PASS,
            source_identity="a" * 40,
        )


@pytest.mark.parametrize(
    ("target_updates", "server_updates", "expected_error"),
    [
        ({}, {"server_pid": 999}, "pid"),
        (
            {"source_identity": "b" * 40},
            {"server_commit": "bbbbbbb"},
            "target source",
        ),
        ({}, {"server_commit": "bbbbbbb"}, "server commit"),
        ({}, {"server_commit": ""}, "server commit"),
        ({}, {"pool_reason": "wrong_pool_mode"}, "pool reason"),
    ],
    ids=(
        "pid",
        "target-source",
        "server-commit",
        "empty-server-commit",
        "pool-reason",
    ),
)
def test_terminal_publication_rechecks_target_and_server_provenance(
    tmp_path: Path,
    target_updates: dict[str, object],
    server_updates: dict[str, object],
    expected_error: str,
) -> None:
    """A self-consistent verdict cannot cite profiles from another process."""
    from promptgrimoire.cli.perf.results import PerfClassification
    from promptgrimoire.cli.perf.state import (
        CampaignStateError,
        CampaignStore,
        write_json_atomic,
    )

    schedule = _schedule()
    leg = schedule.legs[0]
    store = CampaignStore(tmp_path)
    store.initialise(schedule)
    attempt = store.begin_attempt(leg)
    _write_pass_result(attempt.path / "probe.json")
    write_json_atomic(
        attempt.path / "target-start.json",
        {
            "schema_version": 1,
            "pid": 321,
            "source_identity": "a" * 40,
            "database_query_ok": True,
            "pool_mode_reason": "pool_fidelity",
            **target_updates,
        },
    )
    write_json_atomic(
        attempt.path / "validation.json",
        {
            "schema_version": 1,
            "classification": "pass",
            "failures": [],
            "pytest_exit_code": 0,
            "server_evidence": {
                "profile_count": 1,
                "window_start_covered": True,
                "server_pid": 321,
                "server_commit": "aaaaaaa",
                "pool_reason": "pool_fidelity",
                "paths": ["server.jsonl"],
                **server_updates,
            },
        },
    )

    with pytest.raises(CampaignStateError, match=expected_error):
        store.finalise_leg(
            schedule,
            leg,
            attempt,
            classification=PerfClassification.PASS,
            source_identity="a" * 40,
        )


def test_validated_leg_is_skipped_only_while_manifest_hashes_match(
    tmp_path: Path,
) -> None:
    """Resume reopens evidence and detects post-validation corruption."""
    from promptgrimoire.cli.perf.results import PerfClassification
    from promptgrimoire.cli.perf.state import CampaignStore

    schedule = _schedule()
    leg = schedule.legs[0]
    store = CampaignStore(tmp_path)
    store.initialise(schedule)
    attempt = store.begin_attempt(leg)
    probe_path = attempt.path / "probe.json"
    _write_pass_result(probe_path)

    store.finalise_leg(
        schedule,
        leg,
        attempt,
        classification=PerfClassification.PASS,
        source_identity="a" * 40,
    )

    assert store.first_incomplete_leg(schedule) is None
    probe_path.write_text("{}\n", encoding="utf-8")
    assert store.first_incomplete_leg(schedule) == leg


def test_retry_allocates_a_new_immutable_attempt_directory(tmp_path: Path) -> None:
    """Invalid evidence remains diagnostic history rather than being replaced."""
    from promptgrimoire.cli.perf.state import CampaignStore

    schedule = _schedule()
    leg = schedule.legs[0]
    store = CampaignStore(tmp_path)
    store.initialise(schedule)

    first = store.begin_attempt(leg)
    _write_pass_result(first.path / "probe.json")
    second = store.begin_attempt(leg)

    assert first.attempt_id == "attempt-0001"
    assert second.attempt_id == "attempt-0002"
    assert first.path.is_dir()
    assert (first.path / "probe.json").is_file()
    assert second.path.is_dir()


def test_existing_campaign_rejects_a_changed_definition(tmp_path: Path) -> None:
    """Resume cannot silently regenerate the schedule from new parameters."""
    from promptgrimoire.cli.perf.state import CampaignDefinitionMismatch, CampaignStore

    store = CampaignStore(tmp_path)
    store.initialise(_schedule(levels=(25,)))

    with pytest.raises(CampaignDefinitionMismatch, match=r"campaign\.json"):
        store.initialise(_schedule(levels=(25, 50)))


def test_pause_request_is_durable_without_mutating_the_current_attempt(
    tmp_path: Path,
) -> None:
    """The runner may observe pause only at its between-leg boundary."""
    from promptgrimoire.cli.perf.state import CampaignStore

    schedule = _schedule()
    store = CampaignStore(tmp_path)
    store.initialise(schedule)
    attempt = store.begin_attempt(schedule.legs[0])
    attempt_before = json.loads(
        (attempt.path / "attempt.json").read_text(encoding="utf-8")
    )

    store.request_pause()

    assert store.pause_requested()
    assert (
        json.loads((attempt.path / "attempt.json").read_text(encoding="utf-8"))
        == attempt_before
    )
