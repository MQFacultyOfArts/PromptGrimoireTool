"""Shared typed values for performance-run lifecycle boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy.engine import make_url

if TYPE_CHECKING:
    from collections.abc import Mapping


class DatabaseIdentityMismatch(ValueError):
    """Raised when direct, pooled, and expected database names diverge."""


class TargetAttestationError(ValueError):
    """Raised when a measured target cannot prove its expected identity."""


@dataclass(frozen=True, slots=True)
class TargetIdentity:
    """Positive identity returned by a fresh database-usable target."""

    boot_id: str
    pid: int
    source_identity: str
    database_name: str
    preparation_id: str
    pool_mode_reason: str


@dataclass(frozen=True, slots=True)
class TargetExpectation:
    """Identity values the coordinator fixes before target start."""

    boot_id: str
    source_identity: str
    database_name: str
    preparation_id: str
    pool_mode_reason: str


def database_name_from_url(url: str) -> str:
    """Parse and return a database name without comparing URL text."""
    database = make_url(url).database
    if not database:
        raise DatabaseIdentityMismatch("database URL has no database name")
    return database


def verify_database_identity(
    *,
    direct_url: str,
    pooled_url: str,
    expected_database: str,
) -> str:
    """Require direct and pooled transports to name the expected database."""
    direct_database = database_name_from_url(direct_url)
    pooled_database = database_name_from_url(pooled_url)
    mismatches: list[str] = []
    if direct_database != expected_database:
        mismatches.append(f"direct database {direct_database!r}")
    if pooled_database != expected_database:
        mismatches.append(f"pooled database {pooled_database!r}")
    if mismatches:
        detail = ", ".join(mismatches)
        raise DatabaseIdentityMismatch(
            f"Database identity mismatch: expected {expected_database!r}; {detail}"
        )
    return expected_database


def validate_target_attestation(
    payload: Mapping[str, object],
    *,
    expected: TargetExpectation,
) -> TargetIdentity:
    """Validate a target's fresh-process, source, pool, and DB proof."""
    if payload.get("database_query_ok") is not True:
        raise TargetAttestationError("target database query did not succeed")

    raw_pid = payload.get("pid")
    if isinstance(raw_pid, bool) or not isinstance(raw_pid, (int, str)):
        raise TargetAttestationError("target pid is missing or invalid")
    try:
        pid = int(raw_pid)
    except ValueError as exc:
        raise TargetAttestationError("target pid is missing or invalid") from exc
    if pid < 1:
        raise TargetAttestationError("target pid is missing or invalid")

    observed = {
        "boot_id": str(payload.get("boot_id", "")),
        "source_identity": str(payload.get("source_identity", "")),
        "database_name": str(payload.get("database_name", "")),
        "preparation_id": str(payload.get("preparation_id", "")),
        "pool_mode_reason": str(payload.get("pool_mode_reason", "")),
    }
    expected_values = {
        "boot_id": expected.boot_id,
        "source_identity": expected.source_identity,
        "database_name": expected.database_name,
        "preparation_id": expected.preparation_id,
        "pool_mode_reason": expected.pool_mode_reason,
    }
    mismatches = [
        f"{name} observed={observed[name]!r} expected={value!r}"
        for name, value in expected_values.items()
        if observed[name] != value
    ]
    if mismatches:
        raise TargetAttestationError(
            "target attestation mismatch: " + "; ".join(mismatches)
        )
    return TargetIdentity(pid=pid, **observed)
