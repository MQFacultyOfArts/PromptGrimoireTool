#!/usr/bin/env python3
"""Smoke test for the wargame turn cycle engine.

Exercises the full round trip against a real database with real AI calls
(not TestModel). Creates ephemeral test data and cleans up afterwards.

Reads LLM__API_KEY from .env (via pydantic-settings) and bridges it to
ANTHROPIC_API_KEY for PydanticAI agents.

Requires:
    - DATABASE__URL in .env (or env var)
    - LLM__API_KEY in .env (or ANTHROPIC_API_KEY in env)
    - scripts/smoke_data/system_prompt.md (gitignored — copy from .example)
    - scripts/smoke_data/scenario_bootstrap.md (gitignored — copy from .example)

Usage:
    uv run scripts/smoke_turn_cycle.py
    uv run scripts/smoke_turn_cycle.py --rounds 1   # bootstrap + publish only
    uv run scripts/smoke_turn_cycle.py --keep        # don't delete test data
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import os
import sys
import textwrap
import time
import traceback
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pycrdt
import sqlalchemy as sa
from sqlmodel import select

# Imported here to satisfy PLC0415 (top-level import)
from promptgrimoire.config import get_settings as _get_settings
from promptgrimoire.db.courses import create_course
from promptgrimoire.db.engine import get_session
from promptgrimoire.db.models import (
    Activity,
    Course,
    WargameConfig,
    WargameMessage,
    WargameTeam,
    Week,
)
from promptgrimoire.db.wargames import (
    create_teams,
    list_teams,
    on_deadline_fired,
    publish_all,
    start_game,
)
from promptgrimoire.db.weeks import create_week
from promptgrimoire.wargame.agents import summary_agent, turn_agent

SMOKE_DATA = Path(__file__).parent / "smoke_data"
SMOKE_LOG = Path(__file__).parent / "smoke_data" / "smoke.log"
DIVIDER = "=" * 72
SUBDIV = "-" * 72


def _setup_logging() -> None:
    """Configure logging to file + console (INFO to console, DEBUG to file)."""
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # File handler — verbose, captures everything including SQLAlchemy/PydanticAI
    fh = logging.FileHandler(SMOKE_LOG, mode="w")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
    root.addHandler(fh)

    # Console handler — progress messages + API call visibility
    ch = logging.StreamHandler(sys.stderr)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("  %(message)s"))

    # Allow promptgrimoire, httpx, and anthropic through the console filter
    allowed_prefixes = ("promptgrimoire", "httpx", "anthropic")

    class _PrefixFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            return record.name.startswith(allowed_prefixes)

    ch.addFilter(_PrefixFilter())
    root.addHandler(ch)

    # Ensure httpx/anthropic loggers emit at INFO level
    for name in ("httpx", "anthropic"):
        logging.getLogger(name).setLevel(logging.INFO)

    print(f"  Logging to: {SMOKE_LOG}")


def _preflight() -> bool:
    """Run pre-flight checks. Returns True if all pass, False otherwise."""
    ok = True
    settings = _get_settings()

    # 1. Bridge LLM__API_KEY → ANTHROPIC_API_KEY for PydanticAI
    if not os.environ.get("ANTHROPIC_API_KEY"):
        api_key = settings.llm.api_key.get_secret_value()
        if api_key:
            os.environ["ANTHROPIC_API_KEY"] = api_key
            print("  [ok] ANTHROPIC_API_KEY bridged from LLM__API_KEY")
        else:
            print(
                "  [FAIL] No API key: set LLM__API_KEY in .env"
                " or ANTHROPIC_API_KEY in env"
            )
            ok = False
    else:
        print("  [ok] ANTHROPIC_API_KEY already set")

    # 2. Check DATABASE__URL
    if not settings.database.url:
        print("  [FAIL] No DATABASE__URL configured")
        ok = False
    else:
        print("  [ok] DATABASE__URL configured")

    # 3. Check prompt files exist
    for name in ("system_prompt.md", "scenario_bootstrap.md"):
        path = SMOKE_DATA / name
        if not path.exists():
            print(f"  [FAIL] Missing: {path}")
            print(f"         Copy {name}.example to {name} and fill in your content")
            ok = False
        else:
            print(f"  [ok] {name} found")

    return ok


def _check_team_health(teams: list, stage: str) -> bool:
    """Check if any teams are in error state. Returns True if all healthy."""
    errored = [t for t in teams if t.round_state == "error"]
    if errored:
        print(f"\n  [FAIL] {len(errored)} team(s) in error state after {stage}:")
        for t in errored:
            print(f"    - {t.codename} (round={t.current_round})")
        return False
    return True


def _read_prompt_file(name: str) -> str:
    """Read a prompt file from smoke_data/, with helpful error on missing."""
    path = SMOKE_DATA / name
    example = SMOKE_DATA / f"{name}.example"
    if not path.exists():
        print(f"\nMissing: {path}")
        print(f"Copy {example.name} to {name} and fill in your content.\n")
        sys.exit(1)
    return path.read_text().strip()


def _print_section(title: str, content: str, *, indent: int = 4) -> None:
    """Print a labelled section with indented content."""
    print(f"\n{SUBDIV}")
    print(f"  {title}")
    print(SUBDIV)
    for line in content.splitlines():
        print(f"{' ' * indent}{line}")
    print()


async def _setup_test_data(
    system_prompt: str,
    scenario_bootstrap: str,
    summary_system_prompt: str | None,
    *,
    num_teams: int = 1,
) -> tuple[Activity, list]:
    """Create ephemeral course/week/activity/config/teams for smoke testing."""
    slug = uuid4().hex[:6].upper()
    course = await create_course(
        code=f"SMOKE{slug}",
        name=f"Smoke Test {slug}",
        semester="2026-S1",
    )
    week = await create_week(course_id=course.id, week_number=1, title="Week 1")

    async with get_session() as session:
        activity = Activity(
            week_id=week.id,
            type="wargame",
            title=f"Smoke Turn Cycle {slug}",
        )
        session.add(activity)
        await session.flush()
        await session.refresh(activity)

        config = WargameConfig(
            activity_id=activity.id,
            system_prompt=system_prompt,
            scenario_bootstrap=scenario_bootstrap,
            summary_system_prompt=summary_system_prompt,  # type: ignore[arg-type]  -- str | None, field defaults to ""
            timer_delta=timedelta(hours=24),
        )
        session.add(config)
        await session.flush()
        # config committed but not needed after this

    await create_teams(activity.id, num_teams)
    teams = await list_teams(activity.id)
    return activity, teams


async def _cleanup(activity_id) -> None:
    """Delete all smoke test data (best-effort)."""
    async with get_session() as session:
        activity = await session.get(Activity, activity_id)
        if not activity:
            return
        week_id = activity.week_id

        week = await session.get(Week, week_id)
        course_id = week.course_id if week else None

        # Delete in FK order
        await session.exec(
            sa.delete(WargameMessage).where(
                WargameMessage.team_id.in_(  # type: ignore[union-attr]  -- Column .in_()
                    sa.select(WargameTeam.id).where(  # type: ignore[arg-type]  -- SQLAlchemy column expression
                        WargameTeam.activity_id == activity_id
                    )
                )
            )
        )
        await session.exec(
            sa.delete(WargameTeam).where(WargameTeam.activity_id == activity_id)  # type: ignore[arg-type]  -- SQLAlchemy column expression
        )
        await session.exec(
            sa.delete(WargameConfig).where(WargameConfig.activity_id == activity_id)  # type: ignore[arg-type]  -- SQLAlchemy column expression
        )
        await session.exec(sa.delete(Activity).where(Activity.id == activity_id))  # type: ignore[arg-type]  -- SQLAlchemy column expression
        if week_id:
            await session.exec(sa.delete(Week).where(Week.id == week_id))  # type: ignore[arg-type]  -- SQLAlchemy column expression
        if course_id:
            await session.exec(sa.delete(Course).where(Course.id == course_id))  # type: ignore[arg-type]  -- SQLAlchemy column expression


async def _get_team_messages(team_id) -> list[WargameMessage]:
    """Fetch all messages for a team, ordered by sequence."""
    async with get_session() as session:
        result = await session.exec(
            select(WargameMessage)
            .where(WargameMessage.team_id == team_id)
            .order_by(WargameMessage.sequence_no)  # type: ignore[arg-type]  -- SQLAlchemy column expression
        )
        return list(result.all())


async def _print_team_state(teams, *, show_messages: bool = True) -> None:
    """Print current state of all teams."""
    for team in teams:
        print(f"\n  Team: {team.codename} (id={team.id!s:.8}...)")
        print(f"    round={team.current_round}  state={team.round_state}")
        print(f"    deadline={team.current_deadline}")
        print(f"    move_buffer={'set' if team.move_buffer_crdt else 'None'}")

        if team.game_state_text:
            _print_section(
                f"Game State (GM-only) — {team.codename}",
                team.game_state_text,
            )

        if team.student_summary_text:
            _print_section(
                f"Student Briefing — {team.codename}",
                team.student_summary_text,
            )

        if show_messages:
            messages = await _get_team_messages(team.id)
            for msg in messages:
                role_tag = "USER" if msg.role == "user" else "ASST"
                content_preview = textwrap.shorten(msg.content, width=120)
                print(f"    [{role_tag} seq={msg.sequence_no}] {content_preview}")


async def _simulate_moves(teams) -> None:
    """Write CRDT move buffers with distinct content per team."""
    for i, team in enumerate(teams):
        doc = pycrdt.Doc()
        text = doc.get("t", type=pycrdt.Text)
        move = f"Team {team.codename} submits move {i + 1}: Deploy to sector {i + 1}."
        text += move

        async with get_session() as session:
            db_team = (
                await session.exec(select(WargameTeam).where(WargameTeam.id == team.id))
            ).one()
            db_team.move_buffer_crdt = doc.get_update()
            session.add(db_team)

        print(f"  Wrote move for {team.codename}: {move}")


async def _run_round(activity_id, round_num: int, teams: list) -> list:
    """Execute one round: simulate moves, deadline fire, publish."""
    print(f"\n{DIVIDER}")
    print(f"  ROUND {round_num}: Simulate player moves")
    print(DIVIDER)

    await _simulate_moves(teams)

    print(f"\n{DIVIDER}")
    print(f"  ROUND {round_num}: on_deadline_fired() — lock + preprocess")
    print("  (Calling turn_agent per team — waiting for API response...)")
    print(DIVIDER)

    t0 = time.monotonic()
    await on_deadline_fired(activity_id)
    elapsed = time.monotonic() - t0
    print(f"\n  on_deadline_fired() completed in {elapsed:.1f}s")

    teams = await list_teams(activity_id)
    await _print_team_state(teams)

    print(f"\n{DIVIDER}")
    print(f"  ROUND {round_num}: publish_all() — generate briefings")
    print("  (Calling summary_agent per team — waiting for API response...)")
    print(DIVIDER)

    t0 = time.monotonic()
    await publish_all(activity_id)
    elapsed = time.monotonic() - t0
    print(f"\n  publish_all() completed in {elapsed:.1f}s")

    teams = await list_teams(activity_id)
    await _print_team_state(teams)
    return teams


async def _run_bootstrap(activity_id) -> list | None:
    """Run round 1: start_game + publish. Returns teams or None on failure."""
    print(f"\n{DIVIDER}")
    print("  ROUND 1: start_game() — bootstrap with real AI")
    print("  (Calling turn_agent per team — waiting for API response...)")
    print(DIVIDER)

    t0 = time.monotonic()
    await start_game(activity_id)
    elapsed = time.monotonic() - t0
    print(f"\n  start_game() completed in {elapsed:.1f}s")

    teams = await list_teams(activity_id)
    await _print_team_state(teams)
    if not _check_team_health(teams, "start_game"):
        return None

    print(f"\n{DIVIDER}")
    print("  ROUND 1: publish_all() — generate student briefings")
    print("  (Calling summary_agent per team — waiting for API response...)")
    print(DIVIDER)

    t0 = time.monotonic()
    await publish_all(activity_id)
    elapsed = time.monotonic() - t0
    print(f"\n  publish_all() completed in {elapsed:.1f}s")

    teams = await list_teams(activity_id)
    await _print_team_state(teams)
    if not _check_team_health(teams, "publish_all (round 1)"):
        return None
    return teams


async def _run_all_rounds(activity_id, num_rounds: int) -> bool:
    """Bootstrap + play rounds. Returns True if all rounds pass."""
    teams = await _run_bootstrap(activity_id)
    if teams is None:
        return False

    for r in range(2, num_rounds + 1):
        teams = await _run_round(activity_id, r, teams)
        if not _check_team_health(teams, f"round {r}"):
            return False

    return True


async def run(
    num_rounds: int = 2,
    *,
    keep: bool = False,
    model: str | None = None,
    num_teams: int = 1,
) -> None:
    """Execute the smoke test."""
    model_label = model or "default (anthropic:claude-sonnet-4-6)"
    print(DIVIDER)
    print("  WARGAME TURN CYCLE SMOKE TEST")
    print(
        f"  Rounds: {num_rounds}  |  Teams: {num_teams}"
        f"  |  Keep data: {keep}  |  Model: {model_label}"
    )
    print(DIVIDER)

    _setup_logging()

    print("\n[preflight]")
    if not _preflight():
        print(f"\n{DIVIDER}")
        print("  SMOKE TEST ABORTED — pre-flight checks failed")
        print(DIVIDER)
        sys.exit(1)

    system_prompt = _read_prompt_file("system_prompt.md")
    scenario_bootstrap = _read_prompt_file("scenario_bootstrap.md")
    summary_path = SMOKE_DATA / "summary_system_prompt.md"
    summary_system_prompt = (
        summary_path.read_text().strip() if summary_path.exists() else None
    )

    print("\n[setup] Creating ephemeral test data...")
    activity, teams = await _setup_test_data(
        system_prompt, scenario_bootstrap, summary_system_prompt, num_teams=num_teams
    )
    print(f"  Activity: {activity.id}")
    print(f"  Teams: {', '.join(t.codename for t in teams)}")

    passed = False
    turn_ctx = turn_agent.override(model=model) if model else contextlib.nullcontext()
    summary_ctx = (
        summary_agent.override(model=model) if model else contextlib.nullcontext()
    )

    try:
        with turn_ctx, summary_ctx:
            passed = await _run_all_rounds(activity.id, num_rounds)
    except Exception:
        print(f"\n{DIVIDER}")
        print("  SMOKE TEST FAILED — exception")
        print(DIVIDER)
        traceback.print_exc()
    finally:
        status = "PASSED" if passed else "FAILED"
        print(f"\n{DIVIDER}")
        print(f"  SMOKE TEST {status}")
        print(DIVIDER)

        if keep:
            print(f"\n  Data kept. Activity ID: {activity.id}")
        else:
            print("\n  Cleaning up test data...")
            await _cleanup(activity.id)
            print("  Done.")

    sys.exit(0 if passed else 1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test the wargame turn cycle")
    parser.add_argument(
        "--rounds",
        type=int,
        default=2,
        help="Number of rounds to play (default: 2)",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Keep test data in DB after completion",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Override LLM model (e.g. anthropic:claude-haiku-4-5)",
    )
    parser.add_argument(
        "--teams",
        type=int,
        default=1,
        help="Number of teams to create (default: 1)",
    )
    args = parser.parse_args()
    asyncio.run(
        run(
            num_rounds=args.rounds,
            keep=args.keep,
            model=args.model,
            num_teams=args.teams,
        )
    )


if __name__ == "__main__":
    main()
