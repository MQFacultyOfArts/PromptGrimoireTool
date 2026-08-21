"""Local managed-target execution for one admitted campaign leg."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import structlog

from promptgrimoire.cli._shared import _pre_test_db_cleanup
from promptgrimoire.cli.e2e import (
    _allocate_ports,
    _configure_perf_server,
    _start_e2e_server,
    _stop_e2e_server,
)
from promptgrimoire.cli.perf.models import (
    TargetExpectation,
    validate_target_attestation,
    verify_database_identity,
)
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
    validate_server_evidence,
)
from promptgrimoire.cli.perf.state import write_json_atomic
from promptgrimoire.cli.testing import PytestEnvironment, _run_pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

    from promptgrimoire.cli.perf.campaign import CampaignSchedule, ResolvedLeg
    from promptgrimoire.cli.perf.models import TargetIdentity
    from promptgrimoire.cli.perf.state import AttemptPaths, CampaignStore

logger = structlog.get_logger()


class LocalPerfInfrastructureError(RuntimeError):
    """Raised when local setup cannot produce a valid measurement target."""


@dataclass(frozen=True, slots=True)
class _LocalMeasurement:
    exit_code: int
    identity: TargetIdentity
    source_identity: str


@contextmanager
def _isolated_environment(updates: dict[str, str]) -> Iterator[None]:
    """Apply one leg's environment and restore the coordinator afterwards."""
    from promptgrimoire.config import get_settings  # noqa: PLC0415

    original = dict(os.environ)
    os.environ.update(updates)
    get_settings.cache_clear()
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(original)
        get_settings.cache_clear()


def _current_source_identity() -> str:
    """Return the full commit only when it describes the imported source."""
    try:
        identity = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        worktree = subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise LocalPerfInfrastructureError(
            "cannot resolve local source identity"
        ) from exc
    if worktree.stdout.strip():
        raise LocalPerfInfrastructureError(
            "local performance source has uncommitted or untracked files"
        )
    return identity.stdout.strip()


def _fetch_attestation(url: str, *, timeout_s: float = 15.0) -> dict[str, Any]:
    """Wait for the managed endpoint to return a JSON attestation object."""
    endpoint = url.rstrip("/") + "/api/test/diagnostics"
    deadline = time.monotonic() + timeout_s
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(endpoint, timeout=2) as response:  # noqa: S310
                payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, dict):
                raise LocalPerfInfrastructureError(
                    "target diagnostics did not return a JSON object"
                )
            return payload
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(0.1)
    raise LocalPerfInfrastructureError(
        f"target attestation unavailable at {endpoint}: {last_error}"
    )


def _read_probe(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"probe result is unreadable: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("probe result must be a JSON object")
    return payload


def _copy_server_evidence(attempt: AttemptPaths, probe: dict[str, Any]) -> list[Path]:
    """Copy every server log named by the result into immutable attempt scope."""
    server_page_load = probe.get("server_page_load")
    if not isinstance(server_page_load, dict):
        return []
    log_paths = server_page_load.get("log_paths")
    if not isinstance(log_paths, list):
        return []
    destination = attempt.path / "target" / "server-jsonl"
    destination.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    for raw_path in log_paths:
        if not isinstance(raw_path, str):
            continue
        source = Path(raw_path)
        if source.is_file():
            copied_path = destination / source.name
            shutil.copy2(source, copied_path)
            copied.append(copied_path)
    return copied


def _parse_run_time(value: object) -> datetime:
    """Parse one timezone-aware probe measurement boundary."""
    if not isinstance(value, str):
        raise ValueError("probe run window timestamp is missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("probe run window timestamp is invalid") from exc
    if parsed.tzinfo is None:
        raise ValueError("probe run window timestamp has no timezone")
    return parsed.astimezone(UTC)


def _validate_probe_evidence(
    probe: dict[str, Any],
    *,
    expected_source_identity: str,
    expected_pid: int,
) -> list[str]:
    """Return provenance gaps that prevent the result from completing a leg."""
    failures: list[str] = []
    if probe.get("schema_version") != RESULT_SCHEMA_VERSION:
        failures.append("unsupported or missing result schema_version")
    server_page_load = probe.get("server_page_load")
    if not isinstance(server_page_load, dict):
        return [*failures, "missing server_page_load evidence"]
    if server_page_load.get("count", 0) < 1:
        failures.append("server_page_load count is not positive")
    coverage = server_page_load.get("coverage")
    if (
        not isinstance(coverage, dict)
        or coverage.get("window_start_covered") is not True
    ):
        failures.append("server log does not cover the measurement window start")
    if server_page_load.get("server_pid") != expected_pid:
        failures.append("server page-load PID differs from the attested target")
    observed_commit = server_page_load.get("server_commit")
    if not isinstance(observed_commit, str) or not expected_source_identity.startswith(
        observed_commit
    ):
        failures.append("server page-load commit differs from the expected source")
    pool_mode = server_page_load.get("pool_mode")
    if not isinstance(pool_mode, dict) or pool_mode.get("reason") != "pool_fidelity":
        failures.append("server page-load pool reason is not pool_fidelity")
    return failures


class LocalLegExecutor:
    """Prepare, start, attest, measure, stop, and retain one local leg."""

    def __init__(self, schedule: CampaignSchedule, store: CampaignStore) -> None:
        self.schedule = schedule
        self.store = store
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
        *,
        direct_url: str,
        boot_id: str,
        server_stdout: Path,
    ) -> dict[str, str]:
        return {
            "DEV__BRANCH_DB_SUFFIX": "0",
            "DEV__TEST_DATABASE_URL": direct_url,
            "DATABASE__URL": direct_url,
            "E2E_PERF_BOOT_ID": boot_id,
            "E2E_SERVER_STDOUT_LOG": str(server_stdout.resolve()),
            self.probe.parameter_env: str(leg.parameter_value),
            self.probe.result_env: str((attempt.path / "probe.json").resolve()),
            "E2E_PERF_CAMPAIGN_ID": self.schedule.definition.campaign_id,
            "E2E_PERF_LEG_ID": leg.leg_id,
            "E2E_PERF_ATTEMPT_ID": attempt.attempt_id,
            **dict(leg.overrides),
        }

    def _measure(
        self,
        leg: ResolvedLeg,
        attempt: AttemptPaths,
        *,
        source_identity: str,
        direct_url: str,
        pooled_url: str,
    ) -> _LocalMeasurement:
        boot_id = uuid4().hex
        server_stdout = attempt.path / "target" / "server-stdout.log"
        updates = self._leg_environment(
            leg,
            attempt,
            direct_url=direct_url,
            boot_id=boot_id,
            server_stdout=server_stdout,
        )
        with _isolated_environment(updates):
            self.store.record_transition(attempt, "preparing_database")
            prepared = _pre_test_db_cleanup()
            if prepared.test_database_url is None or prepared.database_name is None:
                raise LocalPerfInfrastructureError(
                    "no performance database was prepared"
                )
            verify_database_identity(
                direct_url=prepared.test_database_url,
                pooled_url=pooled_url,
                expected_database=prepared.database_name,
            )
            self.store.record_transition(attempt, "starting_target")
            _configure_perf_server(queue_pool=True)
            port = _allocate_ports(1)[0]
            url = f"http://localhost:{port}"
            process = None
            try:
                try:
                    process = _start_e2e_server(port, log_path=server_stdout)
                except SystemExit as exc:
                    raise LocalPerfInfrastructureError(
                        "managed performance server did not start"
                    ) from exc
                self.store.record_transition(attempt, "attesting_target")
                attestation = _fetch_attestation(url)
                identity = validate_target_attestation(
                    attestation,
                    expected=TargetExpectation(
                        boot_id=boot_id,
                        source_identity=source_identity,
                        database_name=prepared.database_name,
                        preparation_id=prepared.preparation_id,
                        pool_mode_reason="pool_fidelity",
                    ),
                )
                write_json_atomic(
                    attempt.path / "target-start.json",
                    {"schema_version": 1, **attestation},
                )
                self.store.record_transition(attempt, "measuring")
                os.environ["E2E_BASE_URL"] = url
                exit_code = _run_pytest(
                    title=(
                        f"Performance campaign {self.schedule.definition.campaign_id} "
                        f"— {leg.leg_id}"
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
                        variables={"_PROMPTGRIMOIRE_POOL_FIDELITY": "0"},
                        prepared_database=prepared,
                    ),
                )
            finally:
                self.store.record_transition(attempt, "stopping_target")
                if process is not None:
                    _stop_e2e_server(process)
                write_json_atomic(
                    attempt.path / "target-stop.json",
                    {
                        "schema_version": 1,
                        "stopped": process is not None and process.poll() is not None,
                    },
                )
        return _LocalMeasurement(
            exit_code=exit_code,
            identity=identity,
            source_identity=source_identity,
        )

    def _classify(
        self,
        attempt: AttemptPaths,
        measurement: _LocalMeasurement,
    ) -> AttemptOutcome:
        probe_path = attempt.path / "probe.json"
        if not probe_path.is_file():
            classification = (
                PerfClassification.INFRASTRUCTURE_FAILURE
                if measurement.exit_code != 0
                else PerfClassification.INVALID_EVIDENCE
            )
            write_json_atomic(
                attempt.path / "validation.json",
                {
                    "schema_version": 1,
                    "classification": classification.value,
                    "failures": ["measurement produced no probe.json"],
                    "pytest_exit_code": measurement.exit_code,
                },
            )
            return AttemptOutcome(classification, measurement.source_identity)

        try:
            probe = _read_probe(probe_path)
            verdict = probe.get("verdict")
            if not isinstance(verdict, dict):
                raise ValueError("probe result has no verdict object")
            measured_classification = PerfClassification(str(verdict["classification"]))
        except (KeyError, ValueError) as exc:
            logger.warning("perf_probe_result_invalid", reason=str(exc))
            write_json_atomic(
                attempt.path / "validation.json",
                {
                    "schema_version": 1,
                    "classification": PerfClassification.INVALID_EVIDENCE.value,
                    "failures": [str(exc)],
                    "pytest_exit_code": measurement.exit_code,
                },
            )
            return AttemptOutcome(
                PerfClassification.INVALID_EVIDENCE,
                measurement.source_identity,
            )

        self.store.record_transition(attempt, "collecting_evidence")
        copied_logs = _copy_server_evidence(attempt, probe)
        failures = _validate_probe_evidence(
            probe,
            expected_source_identity=measurement.source_identity,
            expected_pid=measurement.identity.pid,
        )
        server_evidence = None
        try:
            run_meta = probe.get("run_meta")
            if not isinstance(run_meta, dict):
                raise ValueError("probe result has no run_meta object")
            server_evidence = validate_server_evidence(
                copied_logs,
                expected=ServerEvidenceExpectation(
                    window_start=_parse_run_time(run_meta.get("started_utc")),
                    window_end=_parse_run_time(run_meta.get("ended_utc")),
                    pid=measurement.identity.pid,
                    source_identity=measurement.source_identity,
                    pool_reason="pool_fidelity",
                ),
            )
        except (ServerEvidenceError, ValueError) as exc:
            logger.warning("local_perf_server_evidence_invalid", reason=str(exc))
            failures.append(str(exc))
        process_classification, process_failures = reconcile_pytest_exit(
            measured_classification,
            measurement.exit_code,
        )
        failures.extend(process_failures)
        if process_failures:
            classification = process_classification
        elif failures:
            classification = PerfClassification.INVALID_EVIDENCE
        else:
            classification = measured_classification
        validation: dict[str, object] = {
            "schema_version": 1,
            "classification": classification.value,
            "failures": failures,
            "pytest_exit_code": measurement.exit_code,
        }
        if server_evidence is not None:
            validation["server_evidence"] = server_evidence.as_payload()
        write_json_atomic(attempt.path / "validation.json", validation)
        return AttemptOutcome(classification, measurement.source_identity)

    def __call__(self, leg: ResolvedLeg, attempt: AttemptPaths) -> AttemptOutcome:
        """Execute one complete local lifecycle and classify its evidence."""
        source_identity = _current_source_identity()
        if source_identity != leg.source_identity:
            raise LocalPerfInfrastructureError(
                f"local source {source_identity!r} does not match arm "
                f"{leg.source_identity!r}"
            )
        direct_url = os.environ.get("E2E_PERF_DIRECT_DATABASE_URL")
        pooled_url = os.environ.get("E2E_PERF_DATABASE_URL")
        if not direct_url or not pooled_url:
            raise LocalPerfInfrastructureError(
                "E2E_PERF_DIRECT_DATABASE_URL and E2E_PERF_DATABASE_URL are required"
            )
        measurement = self._measure(
            leg,
            attempt,
            source_identity=source_identity,
            direct_url=direct_url,
            pooled_url=pooled_url,
        )
        return self._classify(attempt, measurement)
