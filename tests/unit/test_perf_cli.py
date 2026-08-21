"""Tests for the public performance campaign CLI."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from typer.testing import CliRunner

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _write_definition(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "campaign_id": "cli-abba",
                "probe": "soak_full_crud",
                "target": "local",
                "parameter_name": "sessions",
                "levels": [25, 50],
                "arms": [
                    {"name": "A", "source_identity": "a" * 40},
                    {"name": "B", "source_identity": "b" * 40},
                ],
                "arm_pattern": ["A", "B", "B", "A"],
                "stop_policy": "complete_schedule",
            }
        ),
        encoding="utf-8",
    )


def test_perf_plan_persists_the_resolved_schedule_before_execution(
    tmp_path: Path,
) -> None:
    """The full ABBA queue is durable before any campaign process runs."""
    from promptgrimoire.cli import app

    definition = tmp_path / "definition.json"
    output = tmp_path / "campaigns"
    _write_definition(definition)

    result = CliRunner().invoke(
        app,
        ["perf", "plan", str(definition), "--output-root", str(output)],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(
        (output / "cli-abba" / "campaign.json").read_text(encoding="utf-8")
    )
    assert [leg["arm"] for leg in payload["legs"]] == [
        "A",
        "B",
        "B",
        "A",
        "A",
        "B",
        "B",
        "A",
    ]


def test_perf_pause_updates_the_same_durable_campaign_state(tmp_path: Path) -> None:
    """Private execution can request a between-leg pause through public state."""
    from promptgrimoire.cli import app

    definition = tmp_path / "definition.json"
    output = tmp_path / "campaigns"
    _write_definition(definition)
    runner = CliRunner()
    planned = runner.invoke(
        app,
        ["perf", "plan", str(definition), "--output-root", str(output)],
    )
    assert planned.exit_code == 0, planned.output

    campaign_dir = output / "cli-abba"
    paused = runner.invoke(app, ["perf", "pause", str(campaign_dir)])

    assert paused.exit_code == 0, paused.output
    state = json.loads((campaign_dir / "state.json").read_text(encoding="utf-8"))
    assert state["pause_requested"] is True


def test_perf_run_reports_process_interruption_with_exit_130(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A cleaned-up SIGTERM remains distinguishable to durable supervision."""
    from promptgrimoire.cli import app

    definition = tmp_path / "definition.json"
    output = tmp_path / "campaigns"
    _write_definition(definition)
    monkeypatch.setattr(
        "promptgrimoire.cli.perf.cli._run_store",
        lambda _store: "interrupted",
    )

    result = CliRunner().invoke(
        app,
        ["perf", "run", str(definition), "--output-root", str(output)],
    )

    assert result.exit_code == 130
    assert "cli-abba: interrupted" in result.output
