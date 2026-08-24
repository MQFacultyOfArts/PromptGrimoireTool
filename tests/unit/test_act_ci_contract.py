"""Repository contracts for running GitHub workflows through act."""

from pathlib import Path

import yaml


def test_act_runner_matches_ci_contract() -> None:
    """Keep act's image, event, database, and cache behaviour CI-compatible."""
    dockerfile = Path("Dockerfile.act").read_text()
    act_workflow_text = Path(".github/workflows/act-ci.yml").read_text()
    runbook = Path("docs/ci-runners.md").read_text()
    workflows = [
        yaml.safe_load(Path(path).read_text())
        for path in (
            ".github/workflows/ci.yml",
            ".github/workflows/act-ci.yml",
            ".github/workflows/nightly-e2e-slow.yml",
        )
    ]

    assert "postgresql-client" in dockerfile
    assert "psql --version" in dockerfile
    assert "COPY --from=ghcr.io/astral-sh/uv:" in dockerfile
    assert "workflow_dispatch" in workflows[1][True]
    assert "pull_request" not in workflows[1][True]
    assert "browser: [chromium, firefox]" in act_workflow_text
    assert "postgres:17" not in "\n".join(
        Path(path).read_text()
        for path in (
            ".github/workflows/ci.yml",
            ".github/workflows/act-ci.yml",
            ".github/workflows/nightly-e2e-slow.yml",
        )
    )
    assert "cache-local-path" not in act_workflow_text
    assert all(
        flag in runbook
        for flag in ("--env-file", "--secret-file", "--input-file", "--var-file")
    )
    assert "actions/upload-artifact@v4" in act_workflow_text
    assert "actions/upload-artifact@v6" not in act_workflow_text
    assert "actions/upload-artifact@v7" not in act_workflow_text

    service_ports = [
        port
        for workflow in workflows
        for job in workflow["jobs"].values()
        for service in job.get("services", {}).values()
        for port in service.get("ports", [])
    ]
    act_service_ports = [
        port
        for workflow in workflows[1:]
        for job in workflow["jobs"].values()
        for service in job.get("services", {}).values()
        for port in service.get("ports", [])
    ]
    assert all(str(port).startswith("127.0.0.1:") for port in service_ports)
    assert len(act_service_ports) == len(set(act_service_ports))
    assert all(str(port).split(":")[1] != "5432" for port in act_service_ports)


def test_nightly_summary_and_artifacts_are_durable_on_success() -> None:
    """A green nightly publishes exact logs and uses the tested summary renderer."""
    workflow = yaml.safe_load(
        Path(".github/workflows/nightly-e2e-slow.yml").read_text()
    )
    steps = workflow["jobs"]["e2e-slow"]["steps"]
    summary = next(step for step in steps if step.get("name") == "Write job summary")
    upload = next(
        step for step in steps if step.get("name") == "Upload nightly slow artifacts"
    )

    assert summary["if"] == "always()"
    assert summary["run"] == (
        'scripts/nightly-summary.sh "${{ steps.run-tests.outcome }}"'
    )
    assert upload["if"] == "always()"
    assert upload["with"]["if-no-files-found"] == "error"
