"""Strict exact-argv command seam for externally managed perf targets."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlsplit

from promptgrimoire.cli.perf.models import (
    TargetAttestationError,
    TargetExpectation,
    TargetIdentity,
    validate_target_attestation,
)

if TYPE_CHECKING:
    from collections.abc import Callable

ADAPTER_SCHEMA_VERSION = 1
_SECRET_KEY_PARTS = ("password", "secret", "token", "credential", "database_url")
_PUBLIC_HARNESS_ENV_KEYS = frozenset(
    {
        "DATABASE__URL",
        "DEV__TEST_DATABASE_URL",
        "E2E_PERF_DIRECT_DATABASE_URL",
        "E2E_PERF_DATABASE_URL",
        "_CLONE_TEST_SOURCE_URL",
        "_PROMPTGRIMOIRE_DATABASE_PREPARATION_ID",
        "_PROMPTGRIMOIRE_USE_NULL_POOL",
        "_PROMPTGRIMOIRE_POOL_FIDELITY",
    }
)


class AdapterProtocolError(RuntimeError):
    """Raised when the external executable violates its public protocol."""


@dataclass(frozen=True, slots=True)
class ExternalTarget:
    """One fresh external target owned through an opaque adapter handle."""

    handle: str
    server_url: str
    identity: TargetIdentity
    log_identity: str


def _adapter_environment() -> dict[str, str]:
    """Keep private adapter config while withholding public DB credentials."""
    return {
        name: value
        for name, value in os.environ.items()
        if name not in _PUBLIC_HARNESS_ENV_KEYS
    }


def _default_run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
        env=_adapter_environment(),
    )


def _contains_secret(value: object, *, key: str = "") -> bool:
    lowered_key = key.lower()
    if any(part in lowered_key for part in _SECRET_KEY_PARTS):
        return True
    if isinstance(value, str):
        lowered = value.lower()
        return "postgresql://" in lowered or "postgresql+" in lowered
    if isinstance(value, dict):
        return any(
            _contains_secret(child, key=str(child_key))
            for child_key, child in value.items()
        )
    if isinstance(value, list):
        return any(_contains_secret(child) for child in value)
    return False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_evidence_entry(entry: object, *, output_root: Path) -> None:
    """Validate one manifest entry against its collected file."""
    if not isinstance(entry, dict):
        raise AdapterProtocolError("external evidence entry is not an object")
    try:
        relative_path = Path(str(entry["path"]))
        expected_size = int(entry["size"])
        expected_hash = str(entry["sha256"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AdapterProtocolError("external evidence entry is incomplete") from exc
    artifact = (output_root / relative_path).resolve()
    if (
        relative_path.is_absolute()
        or not artifact.is_relative_to(output_root)
        or artifact.is_symlink()
        or not artifact.is_file()
    ):
        raise AdapterProtocolError("external evidence path escapes output_dir")
    if artifact.stat().st_size != expected_size:
        raise AdapterProtocolError("external evidence size mismatch")
    if _sha256(artifact) != expected_hash:
        raise AdapterProtocolError("external evidence hash mismatch")


class ExternalTargetAdapter:
    """Invoke one private executable without importing or interpreting it."""

    def __init__(
        self,
        executable: Path,
        *,
        run_command: Callable[
            [list[str]], subprocess.CompletedProcess[str]
        ] = _default_run,
    ) -> None:
        self.executable = executable
        self.run_command = run_command

    def _invoke(self, *args: str) -> dict[str, Any]:
        argv = [str(self.executable), *args]
        try:
            result = self.run_command(argv)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AdapterProtocolError(
                "external target command did not complete"
            ) from exc
        if result.returncode != 0:
            raise AdapterProtocolError(
                f"external target command exited {result.returncode}"
            )
        try:
            payload = json.loads(result.stdout)
        except (TypeError, json.JSONDecodeError) as exc:
            raise AdapterProtocolError(
                "external target stdout is not one JSON value"
            ) from exc
        if not isinstance(payload, dict):
            raise AdapterProtocolError("external target stdout must be a JSON object")
        if payload.get("schema_version") != ADAPTER_SCHEMA_VERSION:
            raise AdapterProtocolError("external target schema_version is unsupported")
        if _contains_secret(payload):
            raise AdapterProtocolError(
                "external target response contains a secret-bearing field"
            )
        return payload

    def start(
        self,
        request_path: Path,
        *,
        expected_boot_id: str,
        expected_source_identity: str,
        expected_database: str,
        expected_preparation_id: str,
    ) -> ExternalTarget:
        """Start and validate one fresh, leased, database-usable target."""
        payload = self._invoke("start", "--request", str(request_path))
        if payload.get("lease_held") is not True:
            raise AdapterProtocolError(
                "external target did not prove its lease is held"
            )
        handle = payload.get("handle")
        log_identity = payload.get("log_identity")
        server_url = payload.get("server_url")
        if not all(
            isinstance(value, str) and value
            for value in (handle, log_identity, server_url)
        ):
            raise AdapterProtocolError(
                "external target handle, server_url, and log_identity are required"
            )
        handle = cast("str", handle)
        log_identity = cast("str", log_identity)
        server_url = cast("str", server_url)
        parsed_url = urlsplit(server_url)
        if (
            parsed_url.scheme not in {"http", "https"}
            or not parsed_url.hostname
            or parsed_url.username
            or parsed_url.password
            or parsed_url.query
            or parsed_url.fragment
        ):
            raise AdapterProtocolError(
                "external target server_url is not a safe HTTP origin"
            )
        try:
            identity = validate_target_attestation(
                payload,
                expected=TargetExpectation(
                    boot_id=expected_boot_id,
                    source_identity=expected_source_identity,
                    database_name=expected_database,
                    preparation_id=expected_preparation_id,
                    pool_mode_reason="pool_fidelity",
                ),
            )
        except TargetAttestationError as exc:
            raise AdapterProtocolError(str(exc)) from exc
        return ExternalTarget(
            handle=handle,
            server_url=server_url,
            identity=identity,
            log_identity=log_identity,
        )

    def stop(self, handle: str) -> dict[str, Any]:
        """Require observed process exit and release of the private live lease."""
        payload = self._invoke("stop", "--handle", handle)
        if payload.get("handle") != handle:
            raise AdapterProtocolError("external stop handle mismatch")
        if (
            payload.get("stopped") is not True
            or payload.get("pid_exit_observed") is not True
        ):
            raise AdapterProtocolError("external target process exit was not observed")
        if payload.get("evidence_sealed") is not True:
            raise AdapterProtocolError(
                "external target evidence was not sealed before lease release"
            )
        if payload.get("lease_released") is not True:
            raise AdapterProtocolError("external target lease release was not observed")
        return payload

    def collect(
        self,
        handle: str,
        *,
        output_dir: Path,
        probe_path: Path,
    ) -> dict[str, Any]:
        """Collect and positively validate complete time-windowed target evidence."""
        payload = self._invoke(
            "collect",
            "--handle",
            handle,
            "--output-dir",
            str(output_dir),
            "--probe-result",
            str(probe_path),
        )
        if payload.get("handle") != handle:
            raise AdapterProtocolError("external collect handle mismatch")
        if payload.get("window_start_covered") is not True:
            raise AdapterProtocolError("external logs do not cover the window start")
        if not isinstance(payload.get("log_identity"), str) or not payload.get(
            "log_identity"
        ):
            raise AdapterProtocolError("external collection has no log identity")
        files = payload.get("files")
        if not isinstance(files, list) or not files:
            raise AdapterProtocolError("external collection returned no evidence files")
        output_root = output_dir.resolve()
        for entry in files:
            _validate_evidence_entry(entry, output_root=output_root)
        return payload
