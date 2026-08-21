"""Campaign coordination with one scoped resource admission per leg."""

from __future__ import annotations

import signal
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

import structlog

from promptgrimoire.cli._shared import (
    _campaign_test_run_slot,
    _wait_for_idle_test_host,
)
from promptgrimoire.cli.perf.campaign import StopPolicy
from promptgrimoire.cli.perf.results import PerfClassification
from promptgrimoire.cli.perf.state import CampaignStateError

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from contextlib import AbstractContextManager
    from types import FrameType

    from promptgrimoire.cli.perf.campaign import CampaignSchedule, ResolvedLeg
    from promptgrimoire.cli.perf.state import AttemptPaths, CampaignStore

logger = structlog.get_logger()

_CAMPAIGN_SIGNALS = (signal.SIGINT, signal.SIGTERM)


@contextmanager
def _campaign_signal_handlers() -> Iterator[None]:
    """Turn process interruption into ordinary campaign cleanup unwinding."""
    if threading.current_thread() is not threading.main_thread():
        yield
        return

    previous = {signum: signal.getsignal(signum) for signum in _CAMPAIGN_SIGNALS}

    def interrupt(_signum: int, _frame: FrameType | None) -> None:
        raise KeyboardInterrupt

    for signum in _CAMPAIGN_SIGNALS:
        signal.signal(signum, interrupt)
    try:
        yield
    finally:
        for signum in _CAMPAIGN_SIGNALS:
            signal.signal(signum, previous[signum])


@dataclass(frozen=True, slots=True)
class AttemptOutcome:
    """The classification and observed source returned by one leg executor."""

    classification: PerfClassification
    source_identity: str


class LegExecutor(Protocol):
    """Run, clean up, and retain evidence for one admitted campaign leg."""

    def __call__(
        self,
        leg: ResolvedLeg,
        attempt: AttemptPaths,
    ) -> AttemptOutcome:
        """Execute one atomic leg and return its evidence-backed outcome."""
        ...


class CampaignRunner:
    """Advance a persisted campaign without holding resources between legs."""

    def __init__(
        self,
        *,
        store: CampaignStore,
        execute_leg: LegExecutor,
        admission: Callable[[], AbstractContextManager[None]] = (
            _campaign_test_run_slot
        ),
        wait_for_idle: Callable[[], None] = _wait_for_idle_test_host,
    ) -> None:
        self.store = store
        self.execute_leg = execute_leg
        self.admission = admission
        self.wait_for_idle = wait_for_idle

    def run(self, schedule: CampaignSchedule) -> str:
        """Run until complete, paused, collapsed by policy, or invalid."""
        with _campaign_signal_handlers():
            try:
                status = self._advance(schedule)
            except KeyboardInterrupt:
                logger.warning("perf_campaign_interrupted")
                status = "interrupted"
            self.store.set_status(status)
        return status

    def _advance(self, schedule: CampaignSchedule) -> str:
        """Advance the schedule while signal handling owns the outer lifetime."""
        self.store.initialise(schedule)
        if self.store.pause_requested():
            return "paused"
        status: str | None = None
        while (
            status is None
            and (leg := self.store.first_incomplete_leg(schedule)) is not None
        ):
            status = self._run_leg(schedule, leg)
        return status or "complete"

    def _run_leg(
        self,
        schedule: CampaignSchedule,
        leg: ResolvedLeg,
    ) -> str | None:
        """Advance one leg and return only a campaign-stopping status."""
        attempt = self.store.begin_attempt(leg)
        outcome: AttemptOutcome | None = None
        status: str | None = None
        try:
            self.store.record_transition(attempt, "waiting_for_idle_host")
            self.wait_for_idle()
            self.store.record_transition(attempt, "waiting_for_admission")
            with self.admission():
                self.store.record_transition(attempt, "admitted")
                outcome = self.execute_leg(leg, attempt)
        except KeyboardInterrupt:
            logger.warning(
                "perf_campaign_leg_interrupted",
                leg_id=leg.leg_id,
                attempt_id=attempt.attempt_id,
            )
            self.store.record_transition(
                attempt,
                "terminal",
                detail="interrupted",
            )
            status = "interrupted"
        except Exception as exc:
            logger.exception(
                "perf_campaign_leg_execution_failed",
                leg_id=leg.leg_id,
                attempt_id=attempt.attempt_id,
            )
            self.store.record_transition(
                attempt,
                "terminal",
                detail=f"infrastructure_failure: {exc}",
            )
            status = PerfClassification.INFRASTRUCTURE_FAILURE.value

        measured = {
            PerfClassification.PASS,
            PerfClassification.PASS_WITH_DEGRADATION,
            PerfClassification.COLLAPSE,
        }
        if (
            status is None
            and outcome is not None
            and outcome.classification not in measured
        ):
            self.store.record_transition(
                attempt,
                "terminal",
                detail=outcome.classification.value,
            )
            status = outcome.classification.value

        if status is None and outcome is not None:
            try:
                self.store.finalise_leg(
                    schedule,
                    leg,
                    attempt,
                    classification=outcome.classification,
                    source_identity=outcome.source_identity,
                )
            except CampaignStateError as exc:
                logger.warning(
                    "perf_campaign_terminal_evidence_invalid",
                    leg_id=leg.leg_id,
                    attempt_id=attempt.attempt_id,
                    reason=str(exc),
                )
                self.store.record_transition(
                    attempt,
                    "terminal",
                    detail=f"invalid_evidence: {exc}",
                )
                status = PerfClassification.INVALID_EVIDENCE.value
            except Exception as exc:
                logger.exception(
                    "perf_campaign_terminal_publication_failed",
                    leg_id=leg.leg_id,
                    attempt_id=attempt.attempt_id,
                )
                self.store.record_transition(
                    attempt,
                    "terminal",
                    detail=f"infrastructure_failure: {exc}",
                )
                status = PerfClassification.INFRASTRUCTURE_FAILURE.value

        if status is None and self.store.pause_requested():
            status = "paused"
        if (
            status is None
            and outcome is not None
            and outcome.classification is PerfClassification.COLLAPSE
            and schedule.definition.stop_policy is StopPolicy.STOP_ON_VALID_COLLAPSE
        ):
            status = "stopped_on_collapse"
        return status
