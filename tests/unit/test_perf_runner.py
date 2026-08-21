"""Tests for campaign coordination around one atomic leg at a time."""

from __future__ import annotations

import multiprocessing
import os
import signal
from contextlib import contextmanager, nullcontext
from typing import TYPE_CHECKING, Any, Never

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from promptgrimoire.cli.perf.campaign import ResolvedLeg
    from promptgrimoire.cli.perf.state import AttemptPaths


def _sigterm_campaign_worker(root: str, connection: Any) -> None:
    """Run one blocking leg so the parent can exercise the real signal path."""
    from pathlib import Path

    from promptgrimoire.cli.perf.runner import CampaignRunner
    from promptgrimoire.cli.perf.state import CampaignStore

    def block_until_signal(leg: ResolvedLeg, attempt: AttemptPaths) -> Never:
        del leg, attempt
        connection.send("measuring")
        connection.recv()
        raise AssertionError("SIGTERM did not interrupt the campaign leg")

    status = CampaignRunner(
        store=CampaignStore(Path(root)),
        execute_leg=block_until_signal,
        admission=nullcontext,
        wait_for_idle=lambda: None,
    ).run(_schedule())
    connection.send(status)
    connection.close()


def _schedule(*, stop_on_collapse: bool = False):
    from promptgrimoire.cli.perf.campaign import (
        ArmDefinition,
        CampaignDefinition,
        StopPolicy,
        resolve_schedule,
    )

    policy = (
        StopPolicy.STOP_ON_VALID_COLLAPSE
        if stop_on_collapse
        else StopPolicy.COMPLETE_SCHEDULE
    )
    return resolve_schedule(
        CampaignDefinition(
            campaign_id="runner-test",
            probe="soak_full_crud",
            target="local",
            parameter_name="sessions",
            levels=(25, 50),
            arms=(ArmDefinition(name="A", source_identity="a" * 40),),
            arm_pattern=("A",),
            stop_policy=policy,
        )
    )


def _write_result(path: Path, *, collapse: bool = False) -> None:
    from promptgrimoire.cli.perf.results import (
        ResultIdentity,
        measured_verdict,
        write_result_envelope,
    )
    from promptgrimoire.cli.perf.state import write_json_atomic

    classification = "collapse" if collapse else "pass"

    write_result_envelope(
        path,
        verdict=measured_verdict(
            load_failure_count=1 if collapse else 0,
            fatal_action_failure_count=0,
            degraded_action_count=0,
            collapse_reasons=("load boundary",) if collapse else (),
        ),
        probe_payload={"run_meta": {"probe": "soak_full_crud"}},
        identity=ResultIdentity(
            campaign_id="runner-test",
            leg_id=path.parent.parent.name,
            attempt_id=path.parent.name,
        ),
    )
    write_json_atomic(
        path.with_name("validation.json"),
        {
            "schema_version": 1,
            "classification": classification,
            "failures": [],
            "pytest_exit_code": 0,
        },
    )


def test_pause_requested_during_a_leg_takes_effect_after_terminal_cleanup(
    tmp_path: Path,
) -> None:
    """Pause never interrupts a measurement and resume starts at the next leg."""
    from promptgrimoire.cli.perf.results import PerfClassification
    from promptgrimoire.cli.perf.runner import AttemptOutcome, CampaignRunner
    from promptgrimoire.cli.perf.state import CampaignStore

    schedule = _schedule()
    store = CampaignStore(tmp_path)
    executed: list[str] = []

    def execute(leg, attempt):
        executed.append(leg.leg_id)
        _write_result(attempt.path / "probe.json")
        if len(executed) == 1:
            store.request_pause()
        return AttemptOutcome(
            classification=PerfClassification.PASS,
            source_identity=leg.source_identity,
        )

    runner = CampaignRunner(
        store=store,
        execute_leg=execute,
        admission=nullcontext,
        wait_for_idle=lambda: None,
    )

    assert runner.run(schedule) == "paused"
    assert executed == [schedule.legs[0].leg_id]
    assert store.first_incomplete_leg(schedule) == schedule.legs[1]

    store.clear_pause()
    assert runner.run(store.load_schedule()) == "complete"
    assert executed == [leg.leg_id for leg in schedule.legs]


def test_stop_policy_responds_only_to_a_valid_collapse(tmp_path: Path) -> None:
    """An explicit collapse may stop a knee campaign after its evidence validates."""
    from promptgrimoire.cli.perf.results import PerfClassification
    from promptgrimoire.cli.perf.runner import AttemptOutcome, CampaignRunner
    from promptgrimoire.cli.perf.state import CampaignStore

    schedule = _schedule(stop_on_collapse=True)
    store = CampaignStore(tmp_path)
    executed: list[str] = []

    def execute(leg, attempt):
        executed.append(leg.leg_id)
        _write_result(attempt.path / "probe.json", collapse=True)
        return AttemptOutcome(
            classification=PerfClassification.COLLAPSE,
            source_identity=leg.source_identity,
        )

    runner = CampaignRunner(
        store=store,
        execute_leg=execute,
        admission=nullcontext,
        wait_for_idle=lambda: None,
    )

    assert runner.run(schedule) == "stopped_on_collapse"
    assert executed == [schedule.legs[0].leg_id]
    assert store.first_incomplete_leg(schedule) == schedule.legs[1]


def test_idle_host_wait_happens_before_a_campaign_leg_takes_the_slot(
    tmp_path: Path,
) -> None:
    """A load gate cannot strand the shared slot while short work is queued."""
    from promptgrimoire.cli.perf.results import PerfClassification
    from promptgrimoire.cli.perf.runner import AttemptOutcome, CampaignRunner
    from promptgrimoire.cli.perf.state import CampaignStore

    schedule = _schedule(stop_on_collapse=True)
    store = CampaignStore(tmp_path)
    events: list[str] = []

    @contextmanager
    def admission():
        events.append("admitted")
        yield
        events.append("released")

    def execute(leg, attempt):
        events.append("executed")
        _write_result(attempt.path / "probe.json", collapse=True)
        return AttemptOutcome(PerfClassification.COLLAPSE, leg.source_identity)

    runner = CampaignRunner(
        store=store,
        execute_leg=execute,
        admission=admission,
        wait_for_idle=lambda: events.append("idle"),
    )

    assert runner.run(schedule) == "stopped_on_collapse"
    assert events == ["idle", "admitted", "executed", "released"]


def test_result_that_fails_terminal_validation_stops_as_invalid_evidence(
    tmp_path: Path,
) -> None:
    """An executor's optimistic classification cannot publish malformed evidence."""
    from promptgrimoire.cli.perf.results import PerfClassification
    from promptgrimoire.cli.perf.runner import AttemptOutcome, CampaignRunner
    from promptgrimoire.cli.perf.state import CampaignStore

    schedule = _schedule()
    store = CampaignStore(tmp_path)

    def execute(leg, attempt):
        (attempt.path / "probe.json").write_text("{}\n", encoding="utf-8")
        return AttemptOutcome(PerfClassification.PASS, leg.source_identity)

    runner = CampaignRunner(
        store=store,
        execute_leg=execute,
        admission=nullcontext,
        wait_for_idle=lambda: None,
    )

    assert runner.run(schedule) == PerfClassification.INVALID_EVIDENCE
    assert store.read_state()["status"] == PerfClassification.INVALID_EVIDENCE
    assert store.first_incomplete_leg(schedule) == schedule.legs[0]


def test_idle_gate_failure_is_recorded_as_infrastructure_failure(
    tmp_path: Path,
) -> None:
    """Failure before admission still leaves a durable terminal attempt."""
    from promptgrimoire.cli.perf.results import PerfClassification
    from promptgrimoire.cli.perf.runner import CampaignRunner
    from promptgrimoire.cli.perf.state import CampaignStore

    schedule = _schedule()
    store = CampaignStore(tmp_path)

    def fail_idle_gate() -> None:
        raise OSError("cannot read host load")

    def unexpected_execute(leg: object, attempt: object) -> Never:
        raise AssertionError((leg, attempt))

    runner = CampaignRunner(
        store=store,
        execute_leg=unexpected_execute,
        admission=nullcontext,
        wait_for_idle=fail_idle_gate,
    )

    assert runner.run(schedule) == PerfClassification.INFRASTRUCTURE_FAILURE
    assert store.read_state()["status"] == PerfClassification.INFRASTRUCTURE_FAILURE


def test_sigterm_unwinds_the_leg_and_restores_process_signal_handlers(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A termination request leaves an incomplete resumable attempt, not a target."""
    from promptgrimoire.cli.perf.runner import CampaignRunner
    from promptgrimoire.cli.perf.state import CampaignStore

    schedule = _schedule()
    store = CampaignStore(tmp_path)
    originals: dict[signal.Signals, object] = {
        signal.SIGINT: object(),
        signal.SIGTERM: object(),
    }
    installed: dict[signal.Signals, Callable[[int, object], None]] = {}
    calls: list[tuple[signal.Signals, object]] = []

    monkeypatch.setattr(signal, "getsignal", lambda signum: originals[signum])

    def fake_signal(signum: signal.Signals, handler: Any) -> object:
        calls.append((signum, handler))
        if callable(handler):
            installed[signum] = handler
        return originals[signum]

    monkeypatch.setattr(signal, "signal", fake_signal)

    def terminate_during_leg(leg: ResolvedLeg, attempt: AttemptPaths) -> Never:
        del leg, attempt
        handler = installed[signal.SIGTERM]
        handler(signal.SIGTERM, None)
        raise AssertionError("signal handler returned")

    runner = CampaignRunner(
        store=store,
        execute_leg=terminate_during_leg,
        admission=nullcontext,
        wait_for_idle=lambda: None,
    )

    assert runner.run(schedule) == "interrupted"
    assert store.read_state()["status"] == "interrupted"
    assert store.first_incomplete_leg(schedule) == schedule.legs[0]
    assert calls[-2:] == [
        (signal.SIGINT, originals[signal.SIGINT]),
        (signal.SIGTERM, originals[signal.SIGTERM]),
    ]


def test_real_sigterm_leaves_the_campaign_resumable(tmp_path: Path) -> None:
    """The OS signal itself crosses the cleanup and durable-state boundary."""
    from promptgrimoire.cli.perf.state import CampaignStore

    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe()
    process = context.Process(
        target=_sigterm_campaign_worker,
        args=(str(tmp_path), child),
    )
    process.start()
    try:
        assert parent.poll(10)
        assert parent.recv() == "measuring"
        assert process.pid is not None
        os.kill(process.pid, signal.SIGTERM)
        assert parent.poll(10)
        assert parent.recv() == "interrupted"
        process.join(10)
        assert process.exitcode == 0
    finally:
        if process.is_alive():
            process.kill()
            process.join(5)
        parent.close()
        child.close()

    store = CampaignStore(tmp_path)
    schedule = store.load_schedule()
    assert store.read_state()["status"] == "interrupted"
    assert store.first_incomplete_leg(schedule) == schedule.legs[0]
