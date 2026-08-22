"""Atomic durable state and evidence validation for performance campaigns."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from promptgrimoire.cli.perf.campaign import CampaignSchedule, ResolvedLeg
from promptgrimoire.cli.perf.results import (
    RESULT_SCHEMA_VERSION,
    PerfClassification,
)

logger = structlog.get_logger()
STATE_SCHEMA_VERSION = 1
_MINIMUM_GIT_IDENTITY_LENGTH = 7
_MEASURED_CLASSIFICATIONS = frozenset(
    {
        PerfClassification.PASS,
        PerfClassification.PASS_WITH_DEGRADATION,
        PerfClassification.COLLAPSE,
    }
)


class CampaignStateError(ValueError):
    """Base class for invalid or inconsistent durable campaign state."""


class CampaignDefinitionMismatch(CampaignStateError):
    """Raised when an existing campaign ID is reused with changed intent."""


@dataclass(frozen=True, slots=True)
class AttemptPaths:
    """Immutable identity and root for one campaign-leg attempt."""

    leg_id: str
    attempt_id: str
    path: Path


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    """Durably replace a JSON object through a sibling temporary file."""
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
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def _read_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CampaignStateError(f"cannot read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise CampaignStateError(f"{path} must contain a JSON object")
    return payload


def _validate_executor_record(
    attempt_path: Path,
    classification: PerfClassification,
    *,
    source_identity: str,
) -> None:
    """Require the executor's evidence decision before terminal publication."""
    validation = _read_object(attempt_path / "validation.json")
    if validation.get("schema_version") != STATE_SCHEMA_VERSION:
        raise CampaignStateError("validation record schema version is unsupported")
    if validation.get("classification") != classification.value:
        raise CampaignStateError("validation record classification mismatch")
    if validation.get("failures") != []:
        raise CampaignStateError("validation record contains evidence failures")
    if validation.get("pytest_exit_code") != 0:
        raise CampaignStateError("validation record has no successful pytest exit")
    server_evidence = validation.get("server_evidence")
    if server_evidence is None:
        return
    if not isinstance(server_evidence, dict):
        raise CampaignStateError("validation server evidence is not an object")
    target = _read_object(attempt_path / "target-start.json")
    if target.get("source_identity") != source_identity:
        raise CampaignStateError("target source identity mismatch")
    if server_evidence.get("server_pid") != target.get("pid"):
        raise CampaignStateError("server pid differs from the attested target")
    server_commit = server_evidence.get("server_commit")
    if (
        not isinstance(server_commit, str)
        or len(server_commit) < _MINIMUM_GIT_IDENTITY_LENGTH
        or not source_identity.startswith(server_commit)
    ):
        raise CampaignStateError("server commit differs from the attested target")
    if server_evidence.get("pool_reason") != target.get("pool_mode_reason"):
        raise CampaignStateError("server pool reason differs from the attested target")


class CampaignStore:
    """Own one campaign's immutable schedule, attempts, and resume records."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.campaign_path = root / "campaign.json"
        self.state_path = root / "state.json"
        self.legs_path = root / "legs"
        self.attempts_path = root / "attempts"

    def initialise(self, schedule: CampaignSchedule) -> None:
        """Persist a new schedule or verify an exact existing definition."""
        expected = schedule.as_payload()
        if self.campaign_path.exists():
            existing = _read_object(self.campaign_path)
            if existing != expected:
                raise CampaignDefinitionMismatch(
                    f"{self.campaign_path} differs from the requested schedule"
                )
        else:
            write_json_atomic(self.campaign_path, expected)

        self.legs_path.mkdir(parents=True, exist_ok=True)
        self.attempts_path.mkdir(parents=True, exist_ok=True)
        if not self.state_path.exists():
            write_json_atomic(
                self.state_path,
                {
                    "schema_version": STATE_SCHEMA_VERSION,
                    "campaign_id": schedule.definition.campaign_id,
                    "status": "ready",
                    "pause_requested": False,
                    "current_leg_id": None,
                    "current_attempt_id": None,
                    "updated_utc": _utc_now(),
                },
            )

    def load_schedule(self) -> CampaignSchedule:
        """Load the immutable resolved schedule without regeneration."""
        return CampaignSchedule.from_payload(_read_object(self.campaign_path))

    def read_state(self) -> dict[str, Any]:
        """Return the current atomic coordinator state for status reporting."""
        return _read_object(self.state_path)

    def begin_attempt(self, leg: ResolvedLeg) -> AttemptPaths:
        """Allocate a never-reused directory and mark it as the current attempt."""
        leg_root = self.attempts_path / leg.leg_id
        leg_root.mkdir(parents=True, exist_ok=True)
        existing_numbers = [
            int(path.name.removeprefix("attempt-"))
            for path in leg_root.iterdir()
            if path.is_dir()
            and path.name.startswith("attempt-")
            and path.name.removeprefix("attempt-").isdigit()
        ]
        attempt_id = f"attempt-{max(existing_numbers, default=0) + 1:04d}"
        attempt_path = leg_root / attempt_id
        attempt_path.mkdir()
        attempt = AttemptPaths(
            leg_id=leg.leg_id,
            attempt_id=attempt_id,
            path=attempt_path,
        )
        write_json_atomic(
            attempt_path / "attempt.json",
            {
                "schema_version": STATE_SCHEMA_VERSION,
                "leg_id": leg.leg_id,
                "attempt_id": attempt_id,
                "transitions": [{"state": "created", "at_utc": _utc_now()}],
            },
        )
        self._update_state(
            status="running",
            current_leg_id=leg.leg_id,
            current_attempt_id=attempt_id,
        )
        return attempt

    def record_transition(
        self,
        attempt: AttemptPaths,
        state: str,
        *,
        detail: str | None = None,
    ) -> None:
        """Append an atomic lifecycle transition to one immutable attempt."""
        path = attempt.path / "attempt.json"
        payload = _read_object(path)
        transitions = payload.get("transitions")
        if not isinstance(transitions, list):
            raise CampaignStateError(f"{path} has invalid transitions")
        transition: dict[str, object] = {"state": state, "at_utc": _utc_now()}
        if detail is not None:
            transition["detail"] = detail
        transitions.append(transition)
        write_json_atomic(path, payload)

    def finalise_leg(
        self,
        schedule: CampaignSchedule,
        leg: ResolvedLeg,
        attempt: AttemptPaths,
        *,
        classification: PerfClassification,
        source_identity: str,
    ) -> None:
        """Validate a measured result, hash evidence, and publish its leg record."""
        if leg not in schedule.legs or attempt.leg_id != leg.leg_id:
            raise CampaignStateError("attempt does not belong to the resolved leg")
        if source_identity != leg.source_identity:
            raise CampaignStateError(
                f"source identity {source_identity!r} does not match "
                f"{leg.source_identity!r}"
            )
        if classification not in _MEASURED_CLASSIFICATIONS:
            raise CampaignStateError(
                "only a measured pass, degraded pass, or collapse can complete a leg"
            )

        probe_path = attempt.path / "probe.json"
        probe = _read_object(probe_path)
        if probe.get("schema_version") != RESULT_SCHEMA_VERSION:
            raise CampaignStateError(
                "probe result schema version is missing or unsupported"
            )
        verdict = probe.get("verdict")
        if not isinstance(verdict, dict):
            raise CampaignStateError("probe result has no verdict object")
        if verdict.get("classification") != classification.value:
            raise CampaignStateError(
                "probe verdict differs from terminal classification"
            )
        execution = probe.get("execution")
        expected_execution = {
            "mode": "campaign",
            "campaign_id": schedule.definition.campaign_id,
            "leg_id": leg.leg_id,
            "attempt_id": attempt.attempt_id,
        }
        if execution != expected_execution:
            raise CampaignStateError("probe result campaign identity mismatch")
        run_meta = probe.get("run_meta")
        if not isinstance(run_meta, dict):
            raise CampaignStateError("probe result has no run_meta object")
        if run_meta.get("probe") != schedule.definition.probe:
            raise CampaignStateError("probe result does not match the campaign probe")
        _validate_executor_record(
            attempt.path,
            classification,
            source_identity=source_identity,
        )

        self.record_transition(attempt, "terminal", detail=classification.value)
        entries: list[dict[str, object]] = []
        for artifact in sorted(attempt.path.rglob("*")):
            if artifact.is_file() and artifact.name != "manifest.json":
                entries.append(
                    {
                        "path": str(artifact.relative_to(attempt.path)),
                        "size": artifact.stat().st_size,
                        "sha256": _sha256(artifact),
                    }
                )
        manifest_path = attempt.path / "manifest.json"
        write_json_atomic(
            manifest_path,
            {
                "schema_version": STATE_SCHEMA_VERSION,
                "leg_id": leg.leg_id,
                "attempt_id": attempt.attempt_id,
                "artifacts": entries,
            },
        )
        write_json_atomic(
            self.legs_path / f"{leg.leg_id}.json",
            {
                "schema_version": STATE_SCHEMA_VERSION,
                "leg_id": leg.leg_id,
                "attempt_id": attempt.attempt_id,
                "classification": classification.value,
                "source_identity": source_identity,
                "manifest_sha256": _sha256(manifest_path),
            },
        )
        self._update_state(
            status="ready",
            current_leg_id=None,
            current_attempt_id=None,
        )

    def _validated_record_context(
        self,
        leg: ResolvedLeg,
    ) -> tuple[dict[str, Any], PerfClassification, str, Path]:
        record = _read_object(self.legs_path / f"{leg.leg_id}.json")
        if record.get("leg_id") != leg.leg_id:
            raise CampaignStateError("leg record identity mismatch")
        if record.get("source_identity") != leg.source_identity:
            raise CampaignStateError("leg record source identity mismatch")
        classification = PerfClassification(str(record["classification"]))
        if classification not in _MEASURED_CLASSIFICATIONS:
            raise CampaignStateError("leg record is not a measured classification")
        attempt_id = str(record["attempt_id"])
        return (
            record,
            classification,
            attempt_id,
            self.attempts_path / leg.leg_id / attempt_id,
        )

    @staticmethod
    def _validate_manifest(attempt_path: Path, record: dict[str, Any]) -> None:
        manifest_path = attempt_path / "manifest.json"
        if _sha256(manifest_path) != record.get("manifest_sha256"):
            raise CampaignStateError("manifest hash mismatch")
        artifacts = _read_object(manifest_path).get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            raise CampaignStateError("manifest has no artifacts")
        attempt_root = attempt_path.resolve()
        for entry in artifacts:
            if not isinstance(entry, dict):
                raise CampaignStateError("manifest artifact entry is invalid")
            artifact = (attempt_path / str(entry["path"])).resolve()
            if not artifact.is_relative_to(attempt_root) or artifact.is_symlink():
                raise CampaignStateError("manifest artifact escapes attempt directory")
            if artifact.stat().st_size != int(entry["size"]):
                raise CampaignStateError(f"artifact size mismatch: {artifact}")
            if _sha256(artifact) != entry.get("sha256"):
                raise CampaignStateError(f"artifact hash mismatch: {artifact}")

    @staticmethod
    def _validate_probe_record(
        schedule: CampaignSchedule,
        leg: ResolvedLeg,
        attempt_id: str,
        attempt_path: Path,
        classification: PerfClassification,
    ) -> None:
        probe = _read_object(attempt_path / "probe.json")
        execution = probe.get("execution")
        expected_execution = {
            "mode": "campaign",
            "campaign_id": schedule.definition.campaign_id,
            "leg_id": leg.leg_id,
            "attempt_id": attempt_id,
        }
        if execution != expected_execution:
            raise CampaignStateError("probe campaign identity no longer matches")
        verdict = probe.get("verdict")
        if not isinstance(verdict, dict):
            raise CampaignStateError("probe result has no verdict")
        if verdict.get("classification") != classification.value:
            raise CampaignStateError("probe classification no longer matches")
        run_meta = probe.get("run_meta")
        if not isinstance(run_meta, dict) or run_meta.get("probe") != (
            schedule.definition.probe
        ):
            raise CampaignStateError("probe identity no longer matches")
        _validate_executor_record(
            attempt_path,
            classification,
            source_identity=leg.source_identity,
        )

    def _is_leg_valid(self, schedule: CampaignSchedule, leg: ResolvedLeg) -> bool:
        try:
            record, classification, attempt_id, attempt_path = (
                self._validated_record_context(leg)
            )
            self._validate_manifest(attempt_path, record)
            self._validate_probe_record(
                schedule,
                leg,
                attempt_id,
                attempt_path,
                classification,
            )
        except (CampaignStateError, KeyError, OSError, ValueError) as exc:
            logger.warning(
                "perf_campaign_leg_invalid",
                leg_id=leg.leg_id,
                reason=str(exc),
            )
            return False
        return True

    def first_incomplete_leg(self, schedule: CampaignSchedule) -> ResolvedLeg | None:
        """Return the first leg lacking revalidated terminal evidence."""
        for leg in schedule.legs:
            if not self._is_leg_valid(schedule, leg):
                return leg
        return None

    def validated_leg_records(
        self,
        schedule: CampaignSchedule,
    ) -> dict[str, dict[str, Any]]:
        """Return only terminal records whose manifests still revalidate."""
        return {
            leg.leg_id: _read_object(self.legs_path / f"{leg.leg_id}.json")
            for leg in schedule.legs
            if self._is_leg_valid(schedule, leg)
        }

    def request_pause(self) -> None:
        """Persist a request that the coordinator observes between legs."""
        self._update_state(pause_requested=True)

    def clear_pause(self) -> None:
        """Clear a durable pause request before resuming."""
        self._update_state(pause_requested=False, status="ready")

    def pause_requested(self) -> bool:
        """Read the durable between-leg pause flag."""
        return bool(_read_object(self.state_path).get("pause_requested"))

    def set_status(self, status: str) -> None:
        """Persist a coordinator status without changing evidence records."""
        self._update_state(status=status)

    def _update_state(self, **changes: object) -> None:
        state = _read_object(self.state_path)
        state.update(changes)
        state["updated_utc"] = _utc_now()
        write_json_atomic(self.state_path, state)
