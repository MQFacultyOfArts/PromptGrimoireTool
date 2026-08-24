"""Repository contract for the isolated pre-PR workflow."""

from pathlib import Path
from typing import Any

import yaml

WORKFLOW_PATH = Path(".github/workflows/pre-pr-ci.yml")


def _workflow() -> dict[str | bool, Any]:
    return yaml.safe_load(WORKFLOW_PATH.read_text())


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
