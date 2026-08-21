"""External managed-target execution for one admitted campaign leg."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol
from uuid import uuid4

import structlog

from promptgrimoire.cli._shared import _pre_test_db_cleanup
from promptgrimoire.cli.perf.local import _isolated_environment, _read_probe
from promptgrimoire.cli.perf.models import database_name_from_url
from promptgrimoire.cli.perf.probes import get_probe
from promptgrimoire.cli.perf.results import (
    RESULT_SCHEMA_VERSION,
    PerfClassification,
    reconcile_pytest_exit,
)
from promptgrimoire.cli.perf.runner import AttemptOutcome
from promptgrimoire.cli.perf.server_evidence import (
    ServerEvidenceError,
    ServerEvidenceExpectation,
    ServerEvidenceSummary,
    validate_server_evidence,
)
from promptgrimoire.cli.perf.state import write_json_atomic
from promptgrimoire.cli.testing import PytestEnvironment, _run_pytest

if TYPE_CHECKING:
    from pathlib import Path

    from promptgrimoire.cli._shared import PreparedTestDatabase
    from promptgrimoire.cli.perf.campaign import CampaignSchedule, ResolvedLeg
    from promptgrimoire.cli.perf.state import AttemptPaths, CampaignStore
    from promptgrimoire.cli.perf.targets import ExternalTarget

logger = structlog.get_logger()


class TargetAdapter(Protocol):
    """Operations required from the strict external executable wrapper."""

    def start(
        self,
        request_path: Path,
        *,
        expected_boot_id: str,
        expected_source_identity: str,
        expected_database: str,
        expected_preparation_id: str,
    ) -> ExternalTarget:
        """Start one externally leased target."""
        ...

    def stop(self, handle: str) -> dict[str, Any]:
        """Stop a target and release its live lease."""
        ...

    def collect(
        self,
        handle: str,
        *,
        output_dir: Path,
        probe_path: Path,
    ) -> dict[str, Any]:
        """Collect immutable target evidence after stop."""
        ...


def _parse_run_time(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("probe run window timestamp is missing")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("probe run window timestamp is invalid") from exc


@dataclass(frozen=True, slots=True)
class _ExternalMeasurement:
    target: ExternalTarget
    exit_code: int | None
    measurement_error: Exception | None
    cleanup_failures: tuple[str, ...]
    collection: dict[str, Any] | None


class ExternalLegExecutor:
    """Prepare locally, then own one external target through cleanup."""

    def __init__(
        self,
        schedule: CampaignSchedule,
        store: CampaignStore,
        adapter: TargetAdapter,
    ) -> None:
        self.schedule = schedule
        self.store = store
        self.adapter = adapter
        self.probe = get_probe(schedule.definition.probe)
        if self.probe.parameter_name != schedule.definition.parameter_name:
            raise ValueError(
                f"probe parameter is {self.probe.parameter_name!r}, not "
                f"{schedule.definition.parameter_name!r}"
            )

    def _leg_environment(
        self,
        leg: ResolvedLeg,
        attempt: AttemptPaths,
        direct_url: str,
    ) -> dict[str, str]:
        probe_path = attempt.path / "probe.json"
        return {
            "DEV__BRANCH_DB_SUFFIX": "0",
            "DEV__TEST_DATABASE_URL": direct_url,
            "DATABASE__URL": direct_url,
            self.probe.parameter_env: str(leg.parameter_value),
            self.probe.result_env: str(probe_path.resolve()),
            "E2E_PERF_CAMPAIGN_ID": self.schedule.definition.campaign_id,
            "E2E_PERF_LEG_ID": leg.leg_id,
            "E2E_PERF_ATTEMPT_ID": attempt.attempt_id,
            **dict(leg.overrides),
        }

    def _measure_target(
        self,
        leg: ResolvedLeg,
        attempt: AttemptPaths,
        target: ExternalTarget,
        prepared: PreparedTestDatabase,
    ) -> tuple[int | None, Exception | None]:
        self.store.record_transition(attempt, "measuring")
        try:
            return (
                _run_pytest(
                    title=(
                        f"External performance campaign "
                        f"{self.schedule.definition.campaign_id} — {leg.leg_id}"
                    ),
                    log_path=attempt.path / "pytest.log",
                    default_args=[
                        "-m",
                        "perf",
                        "-v",
                        "-s",
                        "--tb=short",
                        "-o",
                        "addopts=",
                    ],
                    extra_args=[str(self.probe.test_path)],
                    extra_env=PytestEnvironment(
                        variables={
                            "E2E_BASE_URL": target.server_url,
                            "_PROMPTGRIMOIRE_POOL_FIDELITY": "0",
                        },
                        prepared_database=prepared,
                    ),
                ),
                None,
            )
        except Exception as exc:
            logger.exception("external_perf_measurement_failed", leg_id=leg.leg_id)
            return None, exc

    def _cleanup_target(
        self,
        leg: ResolvedLeg,
        attempt: AttemptPaths,
        target: ExternalTarget,
    ) -> tuple[dict[str, Any] | None, tuple[str, ...]]:
        failures: list[str] = []
        collection: dict[str, Any] | None = None
        self.store.record_transition(attempt, "stopping_target")
        try:
            stopped = self.adapter.stop(target.handle)
            write_json_atomic(attempt.path / "target-stop.json", stopped)
        except Exception as exc:
            logger.exception("external_perf_stop_failed", leg_id=leg.leg_id)
            failures.append(f"stop failed: {exc}")
        self.store.record_transition(attempt, "collecting_evidence")
        try:
            target_output = attempt.path / "target"
            target_output.mkdir(parents=True, exist_ok=True)
            collection = self.adapter.collect(
                target.handle,
                output_dir=target_output,
                probe_path=attempt.path / "probe.json",
            )
            write_json_atomic(attempt.path / "target-collect.json", collection)
        except Exception as exc:
            logger.exception("external_perf_collection_failed", leg_id=leg.leg_id)
            failures.append(f"collection failed: {exc}")
        return collection, tuple(failures)

    def _execute(
        self,
        leg: ResolvedLeg,
        attempt: AttemptPaths,
        *,
        direct_url: str,
        boot_id: str,
    ) -> _ExternalMeasurement:
        updates = self._leg_environment(leg, attempt, direct_url)
        with _isolated_environment(updates):
            self.store.record_transition(attempt, "preparing_database")
            prepared = _pre_test_db_cleanup()
            if prepared.database_name is None:
                raise RuntimeError("no performance database was prepared")
            if database_name_from_url(direct_url) != prepared.database_name:
                raise RuntimeError("prepared harness database identity changed")
            request_path = attempt.path / "target-request.json"
            write_json_atomic(
                request_path,
                {
                    "schema_version": 1,
                    "campaign_id": self.schedule.definition.campaign_id,
                    "leg_id": leg.leg_id,
                    "attempt_id": attempt.attempt_id,
                    "boot_id": boot_id,
                    "expected_source_identity": leg.source_identity,
                    "expected_database": prepared.database_name,
                    "preparation_id": prepared.preparation_id,
                    "expected_pool_mode_reason": "pool_fidelity",
                },
            )
            self.store.record_transition(attempt, "starting_target")
            target = self.adapter.start(
                request_path,
                expected_boot_id=boot_id,
                expected_source_identity=leg.source_identity,
                expected_database=prepared.database_name,
                expected_preparation_id=prepared.preparation_id,
            )
            try:
                write_json_atomic(
                    attempt.path / "target-start.json",
                    {
                        "schema_version": 1,
                        "handle": target.handle,
                        "server_url": target.server_url,
                        "boot_id": target.identity.boot_id,
                        "pid": target.identity.pid,
                        "source_identity": target.identity.source_identity,
                        "database_name": target.identity.database_name,
                        "preparation_id": target.identity.preparation_id,
                        "pool_mode_reason": target.identity.pool_mode_reason,
                        "log_identity": target.log_identity,
                    },
                )
                exit_code, measurement_error = self._measure_target(
                    leg, attempt, target, prepared
                )
            finally:
                collection, cleanup_failures = self._cleanup_target(
                    leg, attempt, target
                )
        return _ExternalMeasurement(
            target=target,
            exit_code=exit_code,
            measurement_error=measurement_error,
            cleanup_failures=cleanup_failures,
            collection=collection,
        )

    def _classify(
        self,
        leg: ResolvedLeg,
        attempt: AttemptPaths,
        measurement: _ExternalMeasurement,
    ) -> AttemptOutcome:
        if measurement.measurement_error is not None or measurement.cleanup_failures:
            failures = list(measurement.cleanup_failures)
            if measurement.measurement_error is not None:
                failures.insert(
                    0, f"measurement failed: {measurement.measurement_error}"
                )
            return self._invalid_outcome(
                attempt,
                PerfClassification.INFRASTRUCTURE_FAILURE,
                failures,
                measurement.exit_code,
                leg.source_identity,
            )
        if measurement.collection is None:
            return self._invalid_outcome(
                attempt,
                PerfClassification.INFRASTRUCTURE_FAILURE,
                ["external target lifecycle did not complete"],
                measurement.exit_code,
                leg.source_identity,
            )
        probe_path = attempt.path / "probe.json"
        if not probe_path.is_file():
            classification = (
                PerfClassification.INFRASTRUCTURE_FAILURE
                if measurement.exit_code not in {None, 0}
                else PerfClassification.INVALID_EVIDENCE
            )
            return self._invalid_outcome(
                attempt,
                classification,
                ["measurement produced no probe.json"],
                measurement.exit_code,
                leg.source_identity,
            )

        try:
            measured, server_evidence = self._validate_evidence(
                leg, attempt, measurement
            )
        except (KeyError, ServerEvidenceError, ValueError) as exc:
            logger.warning("external_perf_evidence_invalid", reason=str(exc))
            return self._invalid_outcome(
                attempt,
                PerfClassification.INVALID_EVIDENCE,
                [str(exc)],
                measurement.exit_code,
                leg.source_identity,
            )

        if measurement.exit_code is None:
            return self._invalid_outcome(
                attempt,
                PerfClassification.INFRASTRUCTURE_FAILURE,
                ["measurement has no pytest exit code"],
                measurement.exit_code,
                leg.source_identity,
            )
        classification, process_failures = reconcile_pytest_exit(
            measured,
            measurement.exit_code,
        )
        failures = list(process_failures)
        write_json_atomic(
            attempt.path / "validation.json",
            {
                "schema_version": 1,
                "classification": classification.value,
                "failures": failures,
                "pytest_exit_code": measurement.exit_code,
                "server_evidence": server_evidence.as_payload(),
            },
        )
        return AttemptOutcome(classification, leg.source_identity)

    @staticmethod
    def _validate_evidence(
        leg: ResolvedLeg,
        attempt: AttemptPaths,
        measurement: _ExternalMeasurement,
    ) -> tuple[PerfClassification, ServerEvidenceSummary]:
        collection = measurement.collection
        if collection is None:
            raise ValueError("external collection is missing")
        if collection.get("log_identity") != measurement.target.log_identity:
            raise ValueError("collected log identity differs from started target")
        probe = _read_probe(attempt.path / "probe.json")
        if probe.get("schema_version") != RESULT_SCHEMA_VERSION:
            raise ValueError("unsupported result schema_version")
        verdict = probe.get("verdict")
        if not isinstance(verdict, dict):
            raise ValueError("probe result has no verdict object")
        measured = PerfClassification(str(verdict["classification"]))
        run_meta = probe.get("run_meta")
        if not isinstance(run_meta, dict):
            raise ValueError("probe result has no run_meta object")
        entries = collection.get("files")
        if not isinstance(entries, list):
            raise ValueError("external collection has no ordered files")
        evidence_paths = [
            (attempt.path / "target") / str(entry["path"])
            for entry in entries
            if isinstance(entry, dict)
        ]
        server_evidence = validate_server_evidence(
            evidence_paths,
            expected=ServerEvidenceExpectation(
                window_start=_parse_run_time(run_meta.get("started_utc")),
                window_end=_parse_run_time(run_meta.get("ended_utc")),
                pid=measurement.target.identity.pid,
                source_identity=leg.source_identity,
                pool_reason="pool_fidelity",
            ),
        )
        return measured, server_evidence

    def __call__(self, leg: ResolvedLeg, attempt: AttemptPaths) -> AttemptOutcome:
        """Run one external lifecycle and preserve cleanup failures as infra."""
        direct_url = os.environ.get("E2E_PERF_DIRECT_DATABASE_URL")
        if not direct_url:
            raise RuntimeError("E2E_PERF_DIRECT_DATABASE_URL is required")
        measurement = self._execute(
            leg,
            attempt,
            direct_url=direct_url,
            boot_id=uuid4().hex,
        )
        return self._classify(leg, attempt, measurement)

    @staticmethod
    def _invalid_outcome(
        attempt: AttemptPaths,
        classification: PerfClassification,
        failures: list[str],
        exit_code: int | None,
        source_identity: str,
    ) -> AttemptOutcome:
        write_json_atomic(
            attempt.path / "validation.json",
            {
                "schema_version": 1,
                "classification": classification.value,
                "failures": failures,
                "pytest_exit_code": exit_code,
            },
        )
        return AttemptOutcome(classification, source_identity)
