"""Repository contract for the isolated pre-PR workflow."""

import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

WORKFLOW_PATH = Path(".github/workflows/pre-pr-ci.yml")
SMOKE_WORKFLOW_PATH = Path(".github/workflows/pre-pr-runner-smoke.yml")
REQUEST_ID = "prepr-0123456789abcdef0123456789abcdef"
REQUESTED_SHA = "0123456789abcdef0123456789abcdef01234567"
DNS_ADDRESS = "203.0.113.7"


def _workflow() -> dict[str | bool, Any]:
    return yaml.safe_load(WORKFLOW_PATH.read_text())


def _smoke_workflow() -> dict[str | bool, Any]:
    return yaml.safe_load(SMOKE_WORKFLOW_PATH.read_text())


def _attestation_script_and_path() -> tuple[str, Path]:
    workflow = _smoke_workflow()
    smoke_steps = workflow["jobs"]["smoke"]["steps"]
    attest = next(step for step in smoke_steps if step.get("name") == "Attest runner")
    upload = next(
        step
        for step in smoke_steps
        if step.get("name") == "Upload runner smoke evidence"
    )
    return attest["run"], Path(upload["with"]["path"])


def _write_executable(path: Path, body: str) -> None:
    path.write_text(f"#!/usr/bin/env bash\n{body}")
    path.chmod(0o755)


def _run_attestation(
    tmp_path: Path,
    *,
    getent_exit: int = 0,
    curl_exit: int = 0,
    runner_name: str = REQUEST_ID,
) -> tuple[subprocess.CompletedProcess[str], Path, dict[str, str]]:
    assert shutil.which("jq") is not None, "jq is required on PATH for this test"

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    getent_body = (
        f"printf '%s\\n' '{DNS_ADDRESS} STREAM github.com'\nexit 0\n"
        if getent_exit == 0
        else f"exit {getent_exit}\n"
    )
    _write_executable(fake_bin / "getent", getent_body)
    _write_executable(fake_bin / "curl", f"exit {curl_exit}\n")

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}{os.pathsep}{env['PATH']}",
            "REQUESTED_SHA": REQUESTED_SHA,
            "REQUEST_ID": REQUEST_ID,
            "RUNNER_NAME": runner_name,
            "RUNNER_OS": "Linux",
            "RUNNER_ARCH": "X64",
        }
    )
    script, relative_artifact_path = _attestation_script_and_path()
    result = subprocess.run(
        ["bash", "-c", script],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return result, tmp_path / relative_artifact_path, env


def _read_attestation(path: Path) -> dict[str, Any]:
    assert path.exists(), f"attestation was not written at {path}"
    return json.loads(path.read_text())


def _assert_identity(attestation: dict[str, Any], env: dict[str, str]) -> None:
    assert {
        "request_id": attestation["request_id"],
        "requested_sha": attestation["requested_sha"],
        "runner_name": attestation["runner_name"],
        "runner_os": attestation["runner_os"],
        "runner_arch": attestation["runner_arch"],
    } == {
        "request_id": env["REQUEST_ID"],
        "requested_sha": env["REQUESTED_SHA"],
        "runner_name": env["RUNNER_NAME"],
        "runner_os": env["RUNNER_OS"],
        "runner_arch": env["RUNNER_ARCH"],
    }


def _assert_iso_8601_utc(value: Any) -> None:
    assert isinstance(value, str)
    assert value.endswith("Z")
    assert datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo == UTC


def test_pre_pr_workflow_has_only_a_trusted_manual_entrypoint() -> None:
    """The private runner must never be selected by ordinary push or PR events."""
    workflow = _workflow()
    triggers = workflow[True]
    dispatch = triggers["workflow_dispatch"]

    assert set(triggers) == {"workflow_dispatch"}
    assert dispatch["inputs"]["sha"] == {
        "description": "Exact pushed commit SHA to test",
        "required": True,
        "type": "string",
    }
    assert dispatch["inputs"]["request_id"] == {
        "description": "Unpredictable one-run runner label",
        "required": True,
        "type": "string",
    }
    assert workflow["permissions"] == {}
    assert workflow["concurrency"] == {
        "group": "pre-pr-isolated",
        "cancel-in-progress": False,
    }


def test_pre_pr_runner_is_one_job_uniquely_addressed_and_credential_minimal() -> None:
    """Only the approved request can match the disposable repository runner."""
    workflow = _workflow()
    jobs = workflow["jobs"]
    prepare = jobs["prepare"]
    isolated = jobs["isolated-ci"]
    finalize = jobs["finalize"]

    assert prepare["runs-on"] == "ubuntu-latest"
    assert prepare["permissions"] == {"contents": "read", "statuses": "write"}
    assert isolated["needs"] == "prepare"
    assert isolated["runs-on"] == [
        "self-hosted",
        "Linux",
        "X64",
        "pre-pr-isolated",
        "${{ inputs.request_id }}",
    ]
    assert isolated["permissions"] == {"contents": "read"}
    assert "secrets" not in isolated
    assert finalize["runs-on"] == "ubuntu-latest"
    assert finalize["permissions"] == {"contents": "read", "statuses": "write"}
    assert finalize["needs"] == ["prepare", "isolated-ci"]
    assert finalize["if"] == ("${{ always() && needs.prepare.result == 'success' }}")


def test_pre_pr_workflow_validates_and_runs_the_exact_sha() -> None:
    """Hosted jobs stamp the same SHA whose tree the isolated job executes."""
    workflow_text = WORKFLOW_PATH.read_text()
    workflow = _workflow()
    jobs = workflow["jobs"]
    prepare_steps = jobs["prepare"]["steps"]
    isolated_steps = jobs["isolated-ci"]["steps"]
    finalize_steps = jobs["finalize"]["steps"]

    assert any(
        "scripts/pre-pr-status.sh validate-request" in step.get("run", "")
        and "github.event.repository.default_branch" in step.get("run", "")
        for step in prepare_steps
    )
    assert any(
        step.get("run") == "scripts/pre-pr-status.sh set pending"
        for step in prepare_steps
    )
    checkout = next(
        step for step in isolated_steps if step.get("uses") == "actions/checkout@v6.0.2"
    )
    assert checkout["with"] == {
        "ref": "${{ inputs.sha }}",
        "persist-credentials": False,
    }
    assert any(
        step.get("name") == "Verify exact checkout"
        and "git rev-parse HEAD" in step.get("run", "")
        for step in isolated_steps
    )
    finalize_run = next(
        step["run"]
        for step in finalize_steps
        if step.get("name") == "Stamp the exact commit with the terminal result"
    )
    assert 'scripts/pre-pr-status.sh set "$FINAL_STATE"' in finalize_run
    assert all(
        mapping in finalize_run
        for mapping in (
            "success) FINAL_STATE=success",
            "failure) FINAL_STATE=failure",
            "cancelled|skipped) FINAL_STATE=error",
        )
    )
    assert "uv run ruff check ." in workflow_text
    assert "uv run ruff format --check ." in workflow_text
    assert "uv run ty check" in workflow_text
    assert "uv run grimoire e2e slow" in workflow_text
    assert "uv run grimoire e2e run --browser firefox" in workflow_text


def test_ordinary_pr_ci_remains_github_hosted() -> None:
    """Adding the isolated manual route must not move pull requests onto it."""
    workflow = yaml.safe_load(Path(".github/workflows/ci.yml").read_text())

    assert "pull_request" in workflow[True]
    assert all(job["runs-on"] == "ubuntu-latest" for job in workflow["jobs"].values())


def test_runner_smoke_has_only_a_trusted_manual_entrypoint() -> None:
    """The smoke route must be manually addressed to one unpredictable runner."""
    workflow = _smoke_workflow()
    triggers = workflow[True]

    assert set(triggers) == {"workflow_dispatch"}
    assert set(triggers["workflow_dispatch"]["inputs"]) == {"sha", "request_id"}
    assert workflow["permissions"] == {}
    assert workflow["concurrency"] == {
        "group": "pre-pr-runner-smoke-${{ inputs.request_id }}",
        "cancel-in-progress": False,
    }


def test_runner_smoke_executes_no_repository_code() -> None:
    """The first JIT job proves pickup and egress without checking out a tree."""
    workflow = _smoke_workflow()
    jobs = workflow["jobs"]
    prepare = jobs["prepare"]
    smoke = jobs["smoke"]

    assert set(jobs) == {"prepare", "smoke"}
    assert prepare["runs-on"] == "ubuntu-latest"
    assert prepare["permissions"] == {"contents": "read"}
    assert smoke["needs"] == "prepare"
    assert smoke["runs-on"] == [
        "self-hosted",
        "Linux",
        "X64",
        "pre-pr-isolated",
        "${{ inputs.request_id }}",
    ]
    assert smoke["permissions"] == {}
    assert smoke["timeout-minutes"] == 15
    assert "services" not in smoke
    assert "secrets" not in smoke
    assert all(
        not str(step.get("uses", "")).startswith("actions/checkout@")
        for job in jobs.values()
        for step in job["steps"]
    )


def test_runner_smoke_keeps_hosted_validation_and_always_uploads() -> None:
    """GitHub-only validation and unconditional evidence upload stay structural."""
    workflow = _smoke_workflow()
    prepare_run = workflow["jobs"]["prepare"]["steps"][0]["run"]
    smoke_steps = workflow["jobs"]["smoke"]["steps"]
    upload = next(
        step
        for step in smoke_steps
        if step.get("name") == "Upload runner smoke evidence"
    )

    assert "gh api" in prepare_run
    assert "commits/$REQUESTED_SHA" in prepare_run
    assert upload["if"] == "always()"


def test_runner_smoke_attestation_succeeds_with_working_probes(tmp_path: Path) -> None:
    """Successful probes produce a complete, positively validated attestation."""
    result, artifact_path, env = _run_attestation(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    attestation = _read_attestation(artifact_path)
    _assert_identity(attestation, env)
    assert attestation["schema_version"] == 1
    assert attestation["dns_ok"] is True
    assert attestation["github_https_ok"] is True
    assert attestation["dns_address"] == DNS_ADDRESS
    _assert_iso_8601_utc(attestation["started_utc"])
    _assert_iso_8601_utc(attestation["ended_utc"])


def test_runner_smoke_attestation_survives_https_failure(tmp_path: Path) -> None:
    """A failed GitHub HTTPS probe leaves its observed attestation behind."""
    result, artifact_path, env = _run_attestation(tmp_path, curl_exit=22)

    assert result.returncode != 0
    attestation = _read_attestation(artifact_path)
    _assert_identity(attestation, env)
    assert attestation["dns_ok"] is True
    assert attestation["github_https_ok"] is False


def test_runner_smoke_attestation_survives_dns_failure(tmp_path: Path) -> None:
    """A failed DNS probe leaves an attestation with an empty address behind."""
    result, artifact_path, _env = _run_attestation(tmp_path, getent_exit=2)

    assert result.returncode != 0
    attestation = _read_attestation(artifact_path)
    assert attestation["dns_ok"] is False
    assert attestation["dns_address"] == ""


def test_runner_smoke_attestation_survives_identity_mismatch(tmp_path: Path) -> None:
    """A mismatched runner name is recorded before the assertion fails."""
    actual_runner_name = "prepr-11111111111111111111111111111111"
    result, artifact_path, _env = _run_attestation(
        tmp_path,
        runner_name=actual_runner_name,
    )

    assert result.returncode != 0
    attestation = _read_attestation(artifact_path)
    assert attestation["runner_name"] == actual_runner_name
