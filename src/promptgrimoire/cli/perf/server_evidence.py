"""Public validation of collected structured server logs."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


class ServerEvidenceError(ValueError):
    """Raised when collected logs cannot prove the measurement provenance."""


_ABBREVIATED_GIT_IDENTITY = re.compile(r"[0-9a-f]{7,40}")


@dataclass(frozen=True, slots=True)
class ServerEvidenceSummary:
    """Positive facts established from raw collected JSONL lines."""

    profile_count: int
    window_start_covered: bool
    server_pid: int
    server_commit: str
    pool_reason: str
    paths: tuple[str, ...]

    def as_payload(self) -> dict[str, object]:
        """Return a JSON-ready validation summary."""
        return {
            "profile_count": self.profile_count,
            "window_start_covered": self.window_start_covered,
            "server_pid": self.server_pid,
            "server_commit": self.server_commit,
            "pool_reason": self.pool_reason,
            "paths": list(self.paths),
        }


@dataclass(frozen=True, slots=True)
class ServerEvidenceExpectation:
    """Run-window and target facts fixed before validating collected logs."""

    window_start: datetime
    window_end: datetime
    pid: int
    source_identity: str
    pool_reason: str


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ServerEvidenceError("server log record has no timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ServerEvidenceError("server log timestamp is invalid") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _record_pid(record: dict[str, object], *, event: str) -> int:
    raw_pid = record.get("pid")
    if isinstance(raw_pid, bool) or not isinstance(raw_pid, (int, str)):
        raise ServerEvidenceError(f"{event} record has no pid")
    try:
        return int(raw_pid)
    except ValueError as exc:
        raise ServerEvidenceError(f"{event} record has no pid") from exc


def _read_records(paths: list[Path]) -> Iterator[tuple[dict[str, object], datetime]]:
    for path in paths:
        with path.open(encoding="utf-8") as source:
            for line_number, raw_line in enumerate(source, start=1):
                if not raw_line.strip():
                    continue
                try:
                    record = json.loads(raw_line)
                except json.JSONDecodeError as exc:
                    raise ServerEvidenceError(
                        f"server log is malformed at {path}:{line_number}"
                    ) from exc
                if not isinstance(record, dict):
                    raise ServerEvidenceError(
                        f"server log record is not an object at {path}:{line_number}"
                    )
                yield record, _parse_timestamp(record.get("timestamp"))


@dataclass(slots=True)
class _EvidenceScan:
    earliest: datetime | None = None
    profile_count: int = 0
    observed_pids: set[int] = field(default_factory=set)
    observed_commits: set[str] = field(default_factory=set)
    pool_reasons: dict[int, str] = field(default_factory=dict)

    def consume(
        self,
        record: dict[str, object],
        timestamp: datetime,
        expected: ServerEvidenceExpectation,
    ) -> None:
        if self.earliest is None or timestamp < self.earliest:
            self.earliest = timestamp
        event = record.get("event")
        if event == "db_pool_mode" and timestamp <= expected.window_end:
            reason = record.get("reason")
            if isinstance(reason, str):
                self.pool_reasons[_record_pid(record, event="pool-mode")] = reason
            return
        if event != "page_load_profile":
            return
        if not expected.window_start <= timestamp <= expected.window_end:
            return
        request_path = record.get("request_path")
        if isinstance(request_path, str) and not request_path.startswith("/annotation"):
            return
        commit = record.get("commit")
        if not isinstance(commit, str) or not _ABBREVIATED_GIT_IDENTITY.fullmatch(
            commit
        ):
            raise ServerEvidenceError(
                "page-load profile commit is missing or underspecified"
            )
        self.observed_pids.add(_record_pid(record, event="page-load profile"))
        self.observed_commits.add(commit)
        self.profile_count += 1

    def validated_summary(
        self,
        paths: list[Path],
        expected: ServerEvidenceExpectation,
    ) -> ServerEvidenceSummary:
        if self.earliest is None or self.earliest > expected.window_start:
            raise ServerEvidenceError("server logs do not cover the window start")
        if self.profile_count < 1:
            raise ServerEvidenceError(
                "server logs contain no in-window page-load profiles"
            )
        if self.observed_pids != {expected.pid}:
            raise ServerEvidenceError(
                f"server log pids {sorted(self.observed_pids)} differ from "
                f"{expected.pid}"
            )
        if len(self.observed_commits) != 1:
            raise ServerEvidenceError("server logs contain mixed source commits")
        observed_commit = next(iter(self.observed_commits))
        if not expected.source_identity.startswith(observed_commit):
            raise ServerEvidenceError("server log commit differs from expected source")
        pool_reason = self.pool_reasons.get(expected.pid)
        if pool_reason != expected.pool_reason:
            raise ServerEvidenceError(
                f"server pool reason {pool_reason!r} differs from "
                f"{expected.pool_reason!r}"
            )
        return ServerEvidenceSummary(
            profile_count=self.profile_count,
            window_start_covered=True,
            server_pid=expected.pid,
            server_commit=observed_commit,
            pool_reason=pool_reason,
            paths=tuple(str(path) for path in paths),
        )


def validate_server_evidence(
    paths: list[Path],
    *,
    expected: ServerEvidenceExpectation,
) -> ServerEvidenceSummary:
    """Validate ordered rotations against the run window and target identity."""
    if not paths or any(not path.is_file() for path in paths):
        raise ServerEvidenceError("server evidence files are missing")
    scan = _EvidenceScan()
    for record, timestamp in _read_records(paths):
        scan.consume(record, timestamp, expected)
    return scan.validated_summary(paths, expected)
