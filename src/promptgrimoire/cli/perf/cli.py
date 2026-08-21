"""Public commands for planning and operating performance campaigns."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import typer

from promptgrimoire.cli._shared import console
from promptgrimoire.cli.perf.campaign import CampaignDefinition, resolve_schedule
from promptgrimoire.cli.perf.external import ExternalLegExecutor
from promptgrimoire.cli.perf.local import LocalLegExecutor
from promptgrimoire.cli.perf.probes import get_probe
from promptgrimoire.cli.perf.runner import CampaignRunner
from promptgrimoire.cli.perf.state import CampaignStore
from promptgrimoire.cli.perf.summary import summarise_campaign
from promptgrimoire.cli.perf.targets import ExternalTargetAdapter

perf_app = typer.Typer(help="Plan, run, pause, resume, and inspect perf campaigns.")


def _read_definition(path: Path) -> CampaignDefinition:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise typer.BadParameter(f"cannot read campaign definition: {exc}") from exc
    if not isinstance(payload, dict):
        raise typer.BadParameter("campaign definition must be a JSON object")
    try:
        definition = CampaignDefinition.from_payload(payload)
        get_probe(definition.probe)
    except (KeyError, TypeError, ValueError) as exc:
        raise typer.BadParameter(f"invalid campaign definition: {exc}") from exc
    if definition.target not in {"local", "external"}:
        raise typer.BadParameter("campaign target must be 'local' or 'external'")
    return definition


def _campaign_store(output_root: Path, campaign_id: str) -> CampaignStore:
    return CampaignStore(output_root / campaign_id)


def _run_store(store: CampaignStore) -> str:
    schedule = store.load_schedule()
    if schedule.definition.target == "local":
        executor = LocalLegExecutor(schedule, store)
    else:
        executable = os.environ.get("E2E_PERF_TARGET_ADAPTER")
        if not executable:
            raise typer.BadParameter(
                "E2E_PERF_TARGET_ADAPTER is required for an external campaign"
            )
        adapter = ExternalTargetAdapter(Path(executable))
        executor = ExternalLegExecutor(schedule, store, adapter)
    return CampaignRunner(store=store, execute_leg=executor).run(schedule)


def _exit_for_terminal_status(status: str) -> None:
    """Map non-success campaign states to stable process exit statuses."""
    if status == "interrupted":
        raise typer.Exit(code=130)
    if status in {"infrastructure_failure", "invalid_evidence"}:
        raise typer.Exit(code=1)


@perf_app.command("plan")
def plan_campaign(
    definition: Path = typer.Argument(..., exists=True, dir_okay=False),  # noqa: B008
    output_root: Path = typer.Option(  # noqa: B008
        Path("output/perf-campaigns"),
        "--output-root",
        help="Directory containing one durable subdirectory per campaign.",
    ),
) -> None:
    """Resolve and persist the complete schedule without running a leg."""
    resolved = resolve_schedule(_read_definition(definition))
    store = _campaign_store(output_root, resolved.definition.campaign_id)
    store.initialise(resolved)
    console.print(f"[green]Planned {len(resolved.legs)} legs:[/] {store.campaign_path}")


@perf_app.command("run")
def run_campaign(
    definition: Path = typer.Argument(..., exists=True, dir_okay=False),  # noqa: B008
    output_root: Path = typer.Option(  # noqa: B008
        Path("output/perf-campaigns"),
        "--output-root",
    ),
) -> None:
    """Persist a definition, then run its remaining legs on its target."""
    resolved = resolve_schedule(_read_definition(definition))
    store = _campaign_store(output_root, resolved.definition.campaign_id)
    store.initialise(resolved)
    status = _run_store(store)
    console.print(f"Campaign {resolved.definition.campaign_id}: {status}")
    _exit_for_terminal_status(status)


@perf_app.command("resume")
def resume_campaign(
    campaign_dir: Path = typer.Argument(..., file_okay=False),  # noqa: B008
) -> None:
    """Clear a requested pause and resume the persisted resolved schedule."""
    store = CampaignStore(campaign_dir)
    store.load_schedule()
    store.clear_pause()
    status = _run_store(store)
    console.print(f"Campaign {campaign_dir.name}: {status}")
    _exit_for_terminal_status(status)


@perf_app.command("pause")
def pause_campaign(
    campaign_dir: Path = typer.Argument(..., file_okay=False),  # noqa: B008
) -> None:
    """Request a pause after the current atomic leg finishes and cleans up."""
    store = CampaignStore(campaign_dir)
    store.load_schedule()
    store.request_pause()
    console.print(f"Pause requested: {campaign_dir}")


@perf_app.command("status")
def campaign_status(
    campaign_dir: Path = typer.Argument(..., file_okay=False),  # noqa: B008
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Report durable state and the first leg lacking valid evidence."""
    store = CampaignStore(campaign_dir)
    schedule = store.load_schedule()
    state = store.read_state()
    incomplete = store.first_incomplete_leg(schedule)
    payload: dict[str, Any] = {
        "campaign_id": schedule.definition.campaign_id,
        "status": state.get("status"),
        "pause_requested": state.get("pause_requested"),
        "total_legs": len(schedule.legs),
        "first_incomplete_leg": incomplete.leg_id if incomplete is not None else None,
        "campaign_path": str(store.campaign_path),
    }
    if json_output:
        console.print_json(data=payload)
    else:
        console.print(
            f"{payload['campaign_id']}: {payload['status']}; "
            f"first incomplete={payload['first_incomplete_leg']}; "
            f"pause={payload['pause_requested']}"
        )


@perf_app.command("summary")
def campaign_summary(
    campaign_dir: Path = typer.Argument(..., file_okay=False),  # noqa: B008
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Report exact leg order and descriptive outcomes grouped by N and arm."""
    store = CampaignStore(campaign_dir)
    schedule = store.load_schedule()
    payload = summarise_campaign(schedule, store.validated_leg_records(schedule))
    if json_output:
        console.print_json(data=payload)
        return
    console.print(f"Campaign {payload['campaign_id']} ({payload['probe']})")
    for leg in payload["legs"]:
        console.print(
            f"  {leg['index']:>3} n={leg['parameter_value']} "
            f"arm={leg['arm']} {leg['classification']}"
        )
