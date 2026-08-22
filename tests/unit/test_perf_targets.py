"""Tests for the bounded exact-argv external target adapter contract."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable


def _patch_local_executor_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    *,
    direct_url: str,
    pooled_url: str,
    source_identity: str,
    prepare_database: Callable[..., object],
    configure_server: Callable[..., object],
    allocate_ports: Callable[..., object],
    start_server: Callable[..., object],
    attest: Callable[..., object],
    run_measurement: Callable[..., object],
    stop_server: Callable[..., object],
) -> None:
    """Install the complete local-target boundary for a coordinator test."""
    monkeypatch.setenv("E2E_PERF_DIRECT_DATABASE_URL", direct_url)
    monkeypatch.setenv("E2E_PERF_DATABASE_URL", pooled_url)
    monkeypatch.setattr(
        "promptgrimoire.cli.perf.local._current_source_identity",
        lambda: source_identity,
    )
    monkeypatch.setattr(
        "promptgrimoire.cli.perf.local._pre_test_db_cleanup",
        prepare_database,
    )
    monkeypatch.setattr(
        "promptgrimoire.cli.perf.local._configure_perf_server",
        configure_server,
    )
    monkeypatch.setattr(
        "promptgrimoire.cli.perf.local._allocate_ports",
        allocate_ports,
    )
    monkeypatch.setattr(
        "promptgrimoire.cli.perf.local._start_e2e_server",
        start_server,
    )
    monkeypatch.setattr(
        "promptgrimoire.cli.perf.local._fetch_attestation",
        attest,
    )
    monkeypatch.setattr(
        "promptgrimoire.cli.perf.local._run_pytest",
        run_measurement,
    )
    monkeypatch.setattr(
        "promptgrimoire.cli.perf.local._stop_e2e_server",
        stop_server,
    )


def _completed(payload: object, *, returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=[],
        returncode=returncode,
        stdout=json.dumps(payload),
        stderr="adapter stderr",
    )


def _start_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "handle": "target-123",
        "server_url": "http://bunyip.invalid:8080",
        "boot_id": "boot-1",
        "pid": 321,
        "source_identity": "a" * 40,
        "database_name": "perf_soak",
        "database_query_ok": True,
        "preparation_id": "prep-1",
        "pool_mode_reason": "pool_fidelity",
        "log_identity": "server-jsonl-123",
        "lease_held": True,
    }


def test_external_adapter_process_does_not_inherit_public_database_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The exact-argv seam cannot accidentally hand direct DB credentials over."""
    from promptgrimoire.cli.perf.targets import _adapter_environment

    public_only = (
        "DATABASE__URL",
        "DEV__TEST_DATABASE_URL",
        "E2E_PERF_DIRECT_DATABASE_URL",
        "E2E_PERF_DATABASE_URL",
        "_CLONE_TEST_SOURCE_URL",
        "_PROMPTGRIMOIRE_DATABASE_PREPARATION_ID",
        "_PROMPTGRIMOIRE_USE_NULL_POOL",
        "_PROMPTGRIMOIRE_POOL_FIDELITY",
    )
    for name in public_only:
        monkeypatch.setenv(name, "postgresql+asyncpg://public-secret")
    monkeypatch.setenv("BUNYIP_PRIVATE_PROFILE", "perf-rig")

    environment = _adapter_environment()

    assert not set(public_only).intersection(environment)
    assert environment["BUNYIP_PRIVATE_PROFILE"] == "perf-rig"


def test_default_adapter_timeout_terminates_the_process_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A transport timeout cannot leave ssh and its remote lease orphaned."""
    from promptgrimoire.cli.perf.targets import _default_run

    class TimedOutProcess:
        pid = 4321
        returncode = -signal.SIGTERM

        def __init__(self) -> None:
            self.communicate_calls: list[float | None] = []

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            self.communicate_calls.append(timeout)
            if len(self.communicate_calls) == 1:
                raise subprocess.TimeoutExpired(["adapter"], timeout or 0)
            return "", ""

    process = TimedOutProcess()

    def popen(argv: list[str], **kwargs: object) -> TimedOutProcess:
        assert argv == ["/private/adapter", "start"]
        assert kwargs["start_new_session"] is True
        return process

    terminated: list[tuple[int, signal.Signals]] = []
    monkeypatch.setattr(subprocess, "Popen", popen)
    monkeypatch.setattr(
        os,
        "killpg",
        lambda pid, sig: terminated.append((pid, sig)),
    )

    with pytest.raises(subprocess.TimeoutExpired):
        _default_run(["/private/adapter", "start"])

    assert process.communicate_calls == [2700, 10]
    assert terminated == [(process.pid, signal.SIGTERM)]


def test_external_start_uses_exact_argv_and_validates_identity(tmp_path: Path) -> None:
    """No shell fragment sits between the public request and private adapter."""
    from promptgrimoire.cli.perf.targets import ExternalTargetAdapter

    calls: list[list[str]] = []

    def run(argv: list[str]) -> subprocess.CompletedProcess:
        calls.append(argv)
        return _completed(_start_payload())

    adapter = ExternalTargetAdapter(Path("/private/perf-target"), run_command=run)
    request = tmp_path / "target-request.json"
    request.write_text("{}\n", encoding="utf-8")

    target = adapter.start(
        request,
        expected_boot_id="boot-1",
        expected_source_identity="a" * 40,
        expected_database="perf_soak",
        expected_preparation_id="prep-1",
    )

    assert calls == [["/private/perf-target", "start", "--request", str(request)]]
    assert target.handle == "target-123"
    assert target.identity.pid == 321
    assert target.server_url == "http://bunyip.invalid:8080"


@pytest.mark.parametrize(
    "payload",
    [
        "not-json",
        {"schema_version": 2},
        _start_payload() | {"boot_id": "stale-boot"},
        _start_payload() | {"source_identity": "b" * 40},
        _start_payload() | {"database_name": "wrong_database"},
        _start_payload() | {"database_query_ok": False},
        _start_payload() | {"pool_mode_reason": "configured_queue_pool"},
        _start_payload() | {"lease_held": False},
    ],
)
def test_external_start_rejects_malformed_or_stale_identity(
    tmp_path: Path,
    payload: object,
) -> None:
    """Every pre-measurement identity failure is infrastructure, not a knee."""
    from promptgrimoire.cli.perf.targets import (
        AdapterProtocolError,
        ExternalTargetAdapter,
    )

    output = payload if isinstance(payload, str) else json.dumps(payload)

    def run(_argv: list[str]) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess([], 0, output, "")

    request = tmp_path / "request.json"
    request.write_text("{}\n", encoding="utf-8")
    adapter = ExternalTargetAdapter(Path("/private/perf-target"), run_command=run)

    with pytest.raises(AdapterProtocolError):
        adapter.start(
            request,
            expected_boot_id="boot-1",
            expected_source_identity="a" * 40,
            expected_database="perf_soak",
            expected_preparation_id="prep-1",
        )


def test_external_stop_requires_observed_exit_and_lease_release() -> None:
    """A stop acknowledgement alone cannot strand the Bunyip flock."""
    from promptgrimoire.cli.perf.targets import (
        AdapterProtocolError,
        ExternalTargetAdapter,
    )

    adapter = ExternalTargetAdapter(
        Path("/private/perf-target"),
        run_command=lambda _argv: _completed(
            {
                "schema_version": 1,
                "handle": "target-123",
                "stopped": True,
                "pid_exit_observed": True,
                "evidence_sealed": True,
                "lease_released": False,
            }
        ),
    )

    with pytest.raises(AdapterProtocolError, match="lease"):
        adapter.stop("target-123")


def test_external_stop_cannot_release_before_sealing_target_evidence() -> None:
    """The remote lease protects log rotation and snapshotting through stop."""
    from promptgrimoire.cli.perf.targets import (
        AdapterProtocolError,
        ExternalTargetAdapter,
    )

    adapter = ExternalTargetAdapter(
        Path("/private/perf-target"),
        run_command=lambda _argv: _completed(
            {
                "schema_version": 1,
                "handle": "target-123",
                "stopped": True,
                "pid_exit_observed": True,
                "evidence_sealed": False,
                "lease_released": True,
            }
        ),
    )

    with pytest.raises(AdapterProtocolError, match="evidence"):
        adapter.stop("target-123")


def test_external_collect_validates_files_hashes_and_window_coverage(
    tmp_path: Path,
) -> None:
    """Complete rotated evidence is positively checked in public attempt scope."""
    from promptgrimoire.cli.perf.targets import ExternalTargetAdapter

    output_dir = tmp_path / "target"
    output_dir.mkdir()
    oldest = output_dir / "server.jsonl.2"
    newest = output_dir / "server.jsonl"
    oldest.write_text('{"event":"startup"}\n', encoding="utf-8")
    newest.write_text('{"event":"page_load_profile"}\n', encoding="utf-8")

    files = [
        {
            "path": path.name,
            "size": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in (oldest, newest)
    ]
    adapter = ExternalTargetAdapter(
        Path("/private/perf-target"),
        run_command=lambda _argv: _completed(
            {
                "schema_version": 1,
                "handle": "target-123",
                "log_identity": "server-jsonl-123",
                "files": files,
                "window_start_covered": True,
            }
        ),
    )

    adapter.collect(
        "target-123",
        output_dir=output_dir,
        probe_path=tmp_path / "probe.json",
    )


def test_external_collect_rejects_lost_window_start(tmp_path: Path) -> None:
    """A surviving log tail cannot stand in for the complete run window."""
    from promptgrimoire.cli.perf.targets import (
        AdapterProtocolError,
        ExternalTargetAdapter,
    )

    adapter = ExternalTargetAdapter(
        Path("/private/perf-target"),
        run_command=lambda _argv: _completed(
            {
                "schema_version": 1,
                "handle": "target-123",
                "files": [],
                "window_start_covered": False,
            }
        ),
    )

    with pytest.raises(AdapterProtocolError, match="window start"):
        adapter.collect(
            "target-123",
            output_dir=tmp_path,
            probe_path=tmp_path / "probe.json",
        )


def test_public_server_evidence_parser_reads_rotations_in_manifest_order(
    tmp_path: Path,
) -> None:
    """Public code, not the private adapter, proves page-load provenance."""
    from promptgrimoire.cli.perf.server_evidence import (
        ServerEvidenceExpectation,
        validate_server_evidence,
    )

    started = datetime(2026, 8, 21, 1, 0, tzinfo=UTC)
    ended = started + timedelta(minutes=15)
    oldest = tmp_path / "server.jsonl.2"
    current = tmp_path / "server.jsonl"
    oldest.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": (started - timedelta(seconds=1)).isoformat(),
                        "event": "db_pool_mode",
                        "pid": 321,
                        "reason": "pool_fidelity",
                    }
                ),
                json.dumps(
                    {
                        "timestamp": (started + timedelta(seconds=2)).isoformat(),
                        "event": "page_load_profile",
                        "pid": 321,
                        "commit": "aaaaaaa",
                        "request_path": "/annotation?workspace_id=1",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    current.write_text(
        json.dumps(
            {
                "timestamp": (ended - timedelta(seconds=1)).isoformat(),
                "event": "page_load_profile",
                "pid": 321,
                "commit": "aaaaaaa",
                "request_path": "/annotation?workspace_id=2",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    summary = validate_server_evidence(
        [oldest, current],
        expected=ServerEvidenceExpectation(
            window_start=started,
            window_end=ended,
            pid=321,
            source_identity="a" * 40,
            pool_reason="pool_fidelity",
        ),
    )

    assert summary.profile_count == 2
    assert summary.window_start_covered is True


def test_public_server_evidence_parser_rejects_a_rotated_away_window_start(
    tmp_path: Path,
) -> None:
    """A positive page-load count cannot hide missing startup evidence."""
    from promptgrimoire.cli.perf.server_evidence import (
        ServerEvidenceError,
        ServerEvidenceExpectation,
        validate_server_evidence,
    )

    started = datetime(2026, 8, 21, 1, 0, tzinfo=UTC)
    log_path = tmp_path / "server.jsonl"
    log_path.write_text(
        json.dumps(
            {
                "timestamp": (started + timedelta(minutes=5)).isoformat(),
                "event": "page_load_profile",
                "pid": 321,
                "commit": "aaaaaaa",
                "request_path": "/annotation",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ServerEvidenceError, match="window start"):
        validate_server_evidence(
            [log_path],
            expected=ServerEvidenceExpectation(
                window_start=started,
                window_end=started + timedelta(minutes=15),
                pid=321,
                source_identity="a" * 40,
                pool_reason="pool_fidelity",
            ),
        )


def test_public_server_evidence_rejects_an_underspecified_commit(
    tmp_path: Path,
) -> None:
    """A one-character prefix cannot prove which source produced a profile."""
    from promptgrimoire.cli.perf.server_evidence import (
        ServerEvidenceError,
        ServerEvidenceExpectation,
        validate_server_evidence,
    )

    started = datetime(2026, 8, 21, 1, 0, tzinfo=UTC)
    log_path = tmp_path / "server.jsonl"
    log_path.write_text(
        "\n".join(
            json.dumps(record)
            for record in (
                {
                    "timestamp": (started - timedelta(seconds=1)).isoformat(),
                    "event": "db_pool_mode",
                    "pid": 321,
                    "reason": "pool_fidelity",
                },
                {
                    "timestamp": (started + timedelta(seconds=1)).isoformat(),
                    "event": "page_load_profile",
                    "pid": 321,
                    "commit": "a",
                    "request_path": "/annotation",
                },
            )
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ServerEvidenceError, match="commit"):
        validate_server_evidence(
            [log_path],
            expected=ServerEvidenceExpectation(
                window_start=started,
                window_end=started + timedelta(seconds=2),
                pid=321,
                source_identity="a" * 40,
                pool_reason="pool_fidelity",
            ),
        )


def test_external_executor_stops_and_collects_after_measurement_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Once start returns a handle, every path observes stop and collection."""
    from promptgrimoire.cli._shared import PreparedTestDatabase
    from promptgrimoire.cli.perf.campaign import (
        ArmDefinition,
        CampaignDefinition,
        resolve_schedule,
    )
    from promptgrimoire.cli.perf.external import ExternalLegExecutor
    from promptgrimoire.cli.perf.models import TargetIdentity
    from promptgrimoire.cli.perf.results import PerfClassification
    from promptgrimoire.cli.perf.state import CampaignStore
    from promptgrimoire.cli.perf.targets import ExternalTarget

    schedule = resolve_schedule(
        CampaignDefinition(
            campaign_id="external-cleanup",
            probe="soak_full_crud",
            target="external",
            parameter_name="sessions",
            levels=(1,),
            arms=(ArmDefinition(name="A", source_identity="a" * 40),),
            arm_pattern=("A",),
        )
    )
    store = CampaignStore(tmp_path / "campaign")
    store.initialise(schedule)
    attempt = store.begin_attempt(schedule.legs[0])
    events: list[str] = []

    class FakeAdapter:
        def start(self, *_args, **_kwargs):
            events.append("start")
            return ExternalTarget(
                handle="target-123",
                server_url="http://bunyip.invalid:8080",
                identity=TargetIdentity(
                    boot_id="boot",
                    pid=321,
                    source_identity="a" * 40,
                    database_name="perf_soak",
                    preparation_id="prep-1",
                    pool_mode_reason="pool_fidelity",
                ),
                log_identity="log-1",
            )

        def stop(self, handle: str):
            events.append("stop")
            assert handle == "target-123"
            return {"schema_version": 1, "stopped": True}

        def collect(self, handle: str, **_kwargs):
            events.append("collect")
            assert handle == "target-123"
            return {"schema_version": 1, "files": []}

    prepared = PreparedTestDatabase.from_urls(
        test_database_url="postgresql+asyncpg://runner@db:5432/perf_soak",
        clone_source_url=("postgresql+asyncpg://runner@db:5432/perf_soak_clone_source"),
        preparation_id="prep-1",
    )
    monkeypatch.setenv(
        "E2E_PERF_DIRECT_DATABASE_URL",
        "postgresql+asyncpg://runner@db:5432/perf_soak",
    )
    monkeypatch.setattr(
        "promptgrimoire.cli.perf.external._pre_test_db_cleanup",
        lambda: prepared,
    )
    monkeypatch.setattr(
        "promptgrimoire.cli.perf.external._run_pytest",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("measurement failed")),
    )

    outcome = ExternalLegExecutor(schedule, store, FakeAdapter())(
        schedule.legs[0], attempt
    )

    assert outcome.classification is PerfClassification.INFRASTRUCTURE_FAILURE
    assert events == ["start", "stop", "collect"]


def test_external_executor_rejects_logs_from_a_different_started_target(
    tmp_path: Path,
) -> None:
    """A collected file set must retain the target's attested log identity."""
    from promptgrimoire.cli.perf.campaign import (
        ArmDefinition,
        CampaignDefinition,
        resolve_schedule,
    )
    from promptgrimoire.cli.perf.external import (
        ExternalLegExecutor,
        _ExternalMeasurement,
    )
    from promptgrimoire.cli.perf.models import TargetIdentity
    from promptgrimoire.cli.perf.results import PerfClassification
    from promptgrimoire.cli.perf.state import CampaignStore
    from promptgrimoire.cli.perf.targets import ExternalTarget, ExternalTargetAdapter

    schedule = resolve_schedule(
        CampaignDefinition(
            campaign_id="external-log-identity",
            probe="soak_full_crud",
            target="external",
            parameter_name="sessions",
            levels=(1,),
            arms=(ArmDefinition(name="A", source_identity="a" * 40),),
            arm_pattern=("A",),
        )
    )
    store = CampaignStore(tmp_path / "campaign")
    store.initialise(schedule)
    attempt = store.begin_attempt(schedule.legs[0])
    (attempt.path / "probe.json").write_text("{}\n", encoding="utf-8")
    target = ExternalTarget(
        handle="target-123",
        server_url="http://bunyip.invalid:8080",
        identity=TargetIdentity(
            boot_id="boot",
            pid=321,
            source_identity="a" * 40,
            database_name="perf_soak",
            preparation_id="prep-1",
            pool_mode_reason="pool_fidelity",
        ),
        log_identity="started-log",
    )

    outcome = ExternalLegExecutor(
        schedule,
        store,
        ExternalTargetAdapter(Path("/unused")),
    )._classify(
        schedule.legs[0],
        attempt,
        _ExternalMeasurement(
            target=target,
            exit_code=0,
            measurement_error=None,
            cleanup_failures=(),
            collection={
                "schema_version": 1,
                "log_identity": "different-log",
                "files": [],
            },
        ),
    )

    assert outcome.classification is PerfClassification.INVALID_EVIDENCE


def test_attested_external_leg_completes_through_the_public_coordinator(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A complete adapter lifecycle yields one revalidatable public pass."""
    from promptgrimoire.cli._shared import PreparedTestDatabase
    from promptgrimoire.cli.perf.campaign import (
        ArmDefinition,
        CampaignDefinition,
        resolve_schedule,
    )
    from promptgrimoire.cli.perf.external import ExternalLegExecutor
    from promptgrimoire.cli.perf.results import (
        ResultIdentity,
        measured_verdict,
        write_result_envelope,
    )
    from promptgrimoire.cli.perf.runner import CampaignRunner
    from promptgrimoire.cli.perf.state import CampaignStore
    from promptgrimoire.cli.perf.targets import ExternalTargetAdapter
    from promptgrimoire.cli.testing import PytestEnvironment

    source_identity = "a" * 40
    schedule = resolve_schedule(
        CampaignDefinition(
            campaign_id="external-pass",
            probe="soak_full_crud",
            target="external",
            parameter_name="sessions",
            levels=(1,),
            arms=(ArmDefinition(name="A", source_identity=source_identity),),
            arm_pattern=("A",),
        )
    )
    store = CampaignStore(tmp_path / "campaign")
    leg = schedule.legs[0]
    attempt_path = store.attempts_path / leg.leg_id / "attempt-0001"
    started = datetime(2026, 8, 21, 1, 0, tzinfo=UTC)
    ended = started + timedelta(seconds=2)
    events: list[str] = []

    prepared = PreparedTestDatabase.from_urls(
        test_database_url="postgresql+asyncpg://runner@db:5432/perf_soak",
        clone_source_url=("postgresql+asyncpg://runner@db:5432/perf_soak_clone_source"),
        preparation_id="prep-1",
    )

    def prepare_database() -> PreparedTestDatabase:
        events.append("prepare")
        return prepared

    def run_adapter(argv: list[str]) -> subprocess.CompletedProcess:
        command = argv[1]
        events.append(command)
        if command == "start":
            request = json.loads(Path(argv[-1]).read_text(encoding="utf-8"))
            return _completed(
                _start_payload()
                | {
                    "boot_id": request["boot_id"],
                    "source_identity": source_identity,
                }
            )
        if command == "stop":
            return _completed(
                {
                    "schema_version": 1,
                    "handle": "target-123",
                    "stopped": True,
                    "pid_exit_observed": True,
                    "evidence_sealed": True,
                    "lease_released": True,
                }
            )
        assert command == "collect"
        output_dir = Path(argv[argv.index("--output-dir") + 1])
        output_dir.mkdir(parents=True, exist_ok=True)
        log_path = output_dir / "server.jsonl"
        log_path.write_text(
            "\n".join(
                json.dumps(record)
                for record in (
                    {
                        "timestamp": (started - timedelta(seconds=1)).isoformat(),
                        "event": "db_pool_mode",
                        "pid": 321,
                        "reason": "pool_fidelity",
                    },
                    {
                        "timestamp": (started + timedelta(seconds=1)).isoformat(),
                        "event": "page_load_profile",
                        "pid": 321,
                        "commit": source_identity[:7],
                        "request_path": "/annotation?workspace_id=1",
                    },
                )
            )
            + "\n",
            encoding="utf-8",
        )
        return _completed(
            {
                "schema_version": 1,
                "handle": "target-123",
                "log_identity": "server-jsonl-123",
                "window_start_covered": True,
                "files": [
                    {
                        "path": log_path.name,
                        "size": log_path.stat().st_size,
                        "sha256": hashlib.sha256(log_path.read_bytes()).hexdigest(),
                    }
                ],
            }
        )

    def run_measurement(**kwargs: object) -> int:
        events.append("measure")
        environment = kwargs["extra_env"]
        assert isinstance(environment, PytestEnvironment)
        assert environment.prepared_database is prepared
        assert environment.variables["E2E_BASE_URL"] == ("http://bunyip.invalid:8080")
        write_result_envelope(
            attempt_path / "probe.json",
            verdict=measured_verdict(
                load_failure_count=0,
                fatal_action_failure_count=0,
                degraded_action_count=0,
                collapse_reasons=(),
            ),
            probe_payload={
                "run_meta": {
                    "probe": "soak_full_crud",
                    "started_utc": started.isoformat(),
                    "ended_utc": ended.isoformat(),
                }
            },
            identity=ResultIdentity(
                campaign_id=schedule.definition.campaign_id,
                leg_id=leg.leg_id,
                attempt_id="attempt-0001",
            ),
        )
        return 0

    monkeypatch.setenv(
        "E2E_PERF_DIRECT_DATABASE_URL",
        "postgresql+asyncpg://runner@db:5432/perf_soak",
    )
    monkeypatch.setattr(
        "promptgrimoire.cli.perf.external._pre_test_db_cleanup",
        prepare_database,
    )
    monkeypatch.setattr(
        "promptgrimoire.cli.perf.external._run_pytest",
        run_measurement,
    )
    adapter = ExternalTargetAdapter(
        Path("/private/perf-target"),
        run_command=run_adapter,
    )
    runner = CampaignRunner(
        store=store,
        execute_leg=ExternalLegExecutor(schedule, store, adapter),
        admission=nullcontext,
        wait_for_idle=lambda: None,
    )

    assert runner.run(schedule) == "complete"
    assert events == ["prepare", "start", "measure", "stop", "collect"]
    assert store.first_incomplete_leg(schedule) is None
    assert store.read_state()["status"] == "complete"


def test_attested_local_leg_prepares_once_and_stops_before_publication(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The local topology crosses the same complete coordinator boundary."""
    from promptgrimoire.cli._shared import PreparedTestDatabase
    from promptgrimoire.cli.perf.campaign import (
        ArmDefinition,
        CampaignDefinition,
        resolve_schedule,
    )
    from promptgrimoire.cli.perf.local import LocalLegExecutor
    from promptgrimoire.cli.perf.results import (
        ResultIdentity,
        measured_verdict,
        write_result_envelope,
    )
    from promptgrimoire.cli.perf.runner import CampaignRunner
    from promptgrimoire.cli.perf.state import CampaignStore
    from promptgrimoire.cli.testing import PytestEnvironment

    source_identity = "a" * 40
    direct_url = "postgresql+asyncpg://runner@db:5432/perf_soak"
    pooled_url = "postgresql+asyncpg://server@db:6432/perf_soak"
    schedule = resolve_schedule(
        CampaignDefinition(
            campaign_id="local-pass",
            probe="soak_full_crud",
            target="local",
            parameter_name="sessions",
            levels=(1,),
            arms=(ArmDefinition(name="A", source_identity=source_identity),),
            arm_pattern=("A",),
        )
    )
    store = CampaignStore(tmp_path / "campaign")
    leg = schedule.legs[0]
    attempt_path = store.attempts_path / leg.leg_id / "attempt-0001"
    started = datetime(2026, 8, 21, 1, 0, tzinfo=UTC)
    ended = started + timedelta(seconds=2)
    server_log = tmp_path / "server.jsonl"
    server_log.write_text(
        "\n".join(
            json.dumps(record)
            for record in (
                {
                    "timestamp": (started - timedelta(seconds=1)).isoformat(),
                    "event": "db_pool_mode",
                    "pid": 321,
                    "reason": "pool_fidelity",
                },
                {
                    "timestamp": (started + timedelta(seconds=1)).isoformat(),
                    "event": "page_load_profile",
                    "pid": 321,
                    "commit": source_identity[:7],
                    "request_path": "/annotation?workspace_id=1",
                },
            )
        )
        + "\n",
        encoding="utf-8",
    )
    prepared = PreparedTestDatabase.from_urls(
        test_database_url=direct_url,
        clone_source_url=("postgresql+asyncpg://runner@db:5432/perf_soak_clone_source"),
        preparation_id="prep-1",
    )
    events: list[str] = []

    class FakeProcess:
        pid = 321
        stopped = False

        def poll(self) -> int | None:
            return 0 if self.stopped else None

    process = FakeProcess()

    def prepare_database() -> PreparedTestDatabase:
        events.append("prepare")
        return prepared

    def start_server(_port: int, *, log_path: Path) -> FakeProcess:
        events.append("start")
        assert (
            os.environ.get("_PROMPTGRIMOIRE_DATABASE_PREPARATION_ID")
            == prepared.preparation_id
        )
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("server started\n", encoding="utf-8")
        return process

    def attest(_url: str) -> dict[str, object]:
        events.append("attest")
        return {
            "boot_id": os.environ["E2E_PERF_BOOT_ID"],
            "pid": process.pid,
            "source_identity": source_identity,
            "database_name": "perf_soak",
            "database_query_ok": True,
            "preparation_id": prepared.preparation_id,
            "pool_mode_reason": "pool_fidelity",
        }

    def run_measurement(**kwargs: object) -> int:
        events.append("measure")
        environment = kwargs["extra_env"]
        assert isinstance(environment, PytestEnvironment)
        assert environment.prepared_database is prepared
        write_result_envelope(
            attempt_path / "probe.json",
            verdict=measured_verdict(
                load_failure_count=0,
                fatal_action_failure_count=0,
                degraded_action_count=0,
                collapse_reasons=(),
            ),
            probe_payload={
                "run_meta": {
                    "probe": "soak_full_crud",
                    "started_utc": started.isoformat(),
                    "ended_utc": ended.isoformat(),
                },
                "server_page_load": {
                    "count": 1,
                    "coverage": {"window_start_covered": True},
                    "server_pid": process.pid,
                    "server_commit": source_identity[:7],
                    "pool_mode": {"reason": "pool_fidelity"},
                    "log_paths": [str(server_log)],
                },
            },
            identity=ResultIdentity(
                campaign_id=schedule.definition.campaign_id,
                leg_id=leg.leg_id,
                attempt_id="attempt-0001",
            ),
        )
        return 0

    def stop_server(target: FakeProcess) -> None:
        events.append("stop")
        assert target is process
        target.stopped = True

    _patch_local_executor_boundaries(
        monkeypatch,
        direct_url=direct_url,
        pooled_url=pooled_url,
        source_identity=source_identity,
        prepare_database=prepare_database,
        configure_server=lambda *, queue_pool: events.append(f"configure:{queue_pool}"),
        allocate_ports=lambda _count: [4321],
        start_server=start_server,
        attest=attest,
        run_measurement=run_measurement,
        stop_server=stop_server,
    )
    runner = CampaignRunner(
        store=store,
        execute_leg=LocalLegExecutor(schedule, store),
        admission=nullcontext,
        wait_for_idle=lambda: None,
    )

    assert runner.run(schedule) == "complete"
    assert events == [
        "prepare",
        "configure:True",
        "start",
        "attest",
        "measure",
        "stop",
    ]
    assert process.stopped
    assert store.first_incomplete_leg(schedule) is None


def test_local_source_identity_rejects_a_dirty_worktree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HEAD cannot attest modified source that the managed server will import."""
    from promptgrimoire.cli.perf import local

    responses = iter(
        (
            subprocess.CompletedProcess([], 0, "a" * 40 + "\n", ""),
            subprocess.CompletedProcess(
                [], 0, " M src/promptgrimoire/example.py\n", ""
            ),
        )
    )
    monkeypatch.setattr(
        local.subprocess, "run", lambda *_args, **_kwargs: next(responses)
    )

    with pytest.raises(local.LocalPerfInfrastructureError, match="uncommitted"):
        local._current_source_identity()


def test_local_executor_rejects_a_summary_without_retained_raw_server_logs(
    tmp_path: Path,
) -> None:
    """Probe-computed provenance cannot replace the immutable source records."""
    from promptgrimoire.cli.perf.campaign import (
        ArmDefinition,
        CampaignDefinition,
        resolve_schedule,
    )
    from promptgrimoire.cli.perf.local import LocalLegExecutor, _LocalMeasurement
    from promptgrimoire.cli.perf.models import TargetIdentity
    from promptgrimoire.cli.perf.results import (
        PerfClassification,
        ResultIdentity,
        measured_verdict,
        write_result_envelope,
    )
    from promptgrimoire.cli.perf.state import CampaignStore

    source_identity = "a" * 40
    schedule = resolve_schedule(
        CampaignDefinition(
            campaign_id="local-missing-raw",
            probe="soak_full_crud",
            target="local",
            parameter_name="sessions",
            levels=(1,),
            arms=(ArmDefinition(name="A", source_identity=source_identity),),
            arm_pattern=("A",),
        )
    )
    store = CampaignStore(tmp_path / "campaign")
    store.initialise(schedule)
    leg = schedule.legs[0]
    attempt = store.begin_attempt(leg)
    started = datetime(2026, 8, 21, 1, 0, tzinfo=UTC)
    write_result_envelope(
        attempt.path / "probe.json",
        verdict=measured_verdict(
            load_failure_count=0,
            fatal_action_failure_count=0,
            degraded_action_count=0,
            collapse_reasons=(),
        ),
        probe_payload={
            "run_meta": {
                "probe": "soak_full_crud",
                "started_utc": started.isoformat(),
                "ended_utc": (started + timedelta(seconds=2)).isoformat(),
            },
            "server_page_load": {
                "count": 1,
                "coverage": {"window_start_covered": True},
                "server_pid": 321,
                "server_commit": source_identity[:7],
                "pool_mode": {"reason": "pool_fidelity"},
                "log_paths": [str(tmp_path / "missing-server.jsonl")],
            },
        },
        identity=ResultIdentity(
            campaign_id=schedule.definition.campaign_id,
            leg_id=leg.leg_id,
            attempt_id=attempt.attempt_id,
        ),
    )

    outcome = LocalLegExecutor(schedule, store)._classify(
        attempt,
        _LocalMeasurement(
            exit_code=0,
            identity=TargetIdentity(
                boot_id="boot",
                pid=321,
                source_identity=source_identity,
                database_name="perf_soak",
                preparation_id="prep-1",
                pool_mode_reason="pool_fidelity",
            ),
            source_identity=source_identity,
        ),
    )

    assert outcome.classification is PerfClassification.INVALID_EVIDENCE
