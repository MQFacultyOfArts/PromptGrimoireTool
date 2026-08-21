"""Perf probe: a thundering herd landing on the heavyweight PABAI workspace.

Where the cram probe (test_assessment_cram_load.py) measures a synchronized
burst of *annotation writes*, and the soak probe measures sustained full
CRUD, this probe measures the shape that historically crashed the server:
N students arriving at once on a heavyweight annotated document, then
churning -- reloading it and re-opening the annotation experience.

The fixture is the PABAI extract (``pabai_workspace_scrubbed.json``: 426 KB
document HTML, ~190 highlights in workspace CRDT state), the same workspace
behind the April 2026 page-load investigation
(docs/investigations/2026-04-23-page-load-failure-modes.md, CLAUDE.md
"Performance failure modes"). Classes A and D are fixed; B (long
transaction holds amplifying pool queueing), C (duplicate registry passes)
and E (per-item O(N) synchronous UI loops during initial render) are known
and unfixed, and every one of them is paid *per page load*. Reloading is
therefore the load, not a detail of it.

Shape:

1. Rehydrate PABAI once, bind it as an Activity template.
2. Pre-clone one workspace per synthetic student via the real
   ``clone_workspace_from_activity`` path, so each student loads their own
   independent workspace carrying its own copy of the ~190 highlights
   (``db/workspaces.py``: CRDT state is replayed into the clone with
   remapped document and tag ids). Per-student clones, not one shared
   workspace: the historical crash was independent loads contending for
   shared server resources, and a shared workspace would instead measure
   broadcast/presence fan-out.
3. All students authenticate, then wait on a barrier and navigate at once
   -- that simultaneous arrival is the herd.
4. Each student then runs ``E2E_HERD_CYCLES`` churn cycles: reload, wait
   for the annotation page to be ready and the sidebar to mount, click
   "Go to highlight" on random cards, visit Organise and Respond, return
   to Source.

Reload churn is **free-running by default**: only the first arrival is
barrier-synchronized, and cycles are separated by jittered think time so
students de-phase. Set ``E2E_HERD_SYNC_RELOADS=true`` to re-form the herd
before every cycle instead (a barrier per cycle, degrading to free-running
if it breaks). Free-running is the default because a warm-cache reload
wave no longer meets the class-A cold-cache precondition, and sustained
overlapping loads at independent phase are what a real class produces once
everyone is in.

Admission is already disabled by the E2E harness
(``cli/e2e/_server_script.py:21`` sets ``ADMISSION__ENABLED=false``), so
this probe never sees the queue and deliberately carries no queue handling.

Ramp externally:

    E2E_HERD_SESSIONS=150 E2E_HERD_DIAG_PATH=perf-data/herd_n150.json \
        uv run grimoire e2e perf tests/e2e/test_thundering_herd.py

Failures are data. The probe records every load and action failure, prints
them, and writes them to the diag JSON; it fails only on systemic collapse
(more than ``max(3, N // 10)`` students affected), so a single wedged
co-located browser cannot masquerade as a server boundary.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import threading
import time
import urllib.request
from contextlib import suppress
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from promptgrimoire.cli.perf.results import (
    MeasuredVerdict,
    measured_verdict,
    should_fail_pytest_for_verdict,
    write_result_envelope,
)
from promptgrimoire.config import get_current_branch, get_settings
from tests.e2e.assessment_fixtures import (
    AssessmentFixture,
    create_template_activity,
    ensure_fixture_workspace,
    provision_clone_for_email,
    restore_template_binding,
)
from tests.e2e.card_helpers import PABAI_FIXTURE_JSON, PABAI_WORKSPACE_ID
from tests.e2e.perf_reporting import (
    build_run_meta,
    collect_server_page_load,
    print_server_page_load,
    utc_now,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from datetime import datetime

    from playwright.sync_api import Page

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.perf,
    # Overrides the global 30s cap: a 150-session herd spends minutes in
    # clone provisioning alone, then several reload cycles per student.
    pytest.mark.timeout(3600),
    pytest.mark.skipif(
        not get_settings().dev.test_database_url,
        reason="DEV__TEST_DATABASE_URL not configured",
    ),
]

# PABAI is not one of the assessment fixtures, but the provisioning
# machinery is fixture-agnostic; its id and path already have a single
# home in card_helpers, so reuse both rather than restating the UUID.
PABAI_FIXTURE = AssessmentFixture(
    name="pabai",
    workspace_id=PABAI_WORKSPACE_ID,
    json_path=PABAI_FIXTURE_JSON,
)

ANNOTATION_CARD = "[data-testid='annotation-card']"


def _bool_env(name: str, *, default: bool = False) -> bool:
    """Read a boolean runner flag from the environment."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


N_HERD_SESSIONS = int(os.environ.get("E2E_HERD_SESSIONS", "25"))
N_HERD_CYCLES = int(os.environ.get("E2E_HERD_CYCLES", "3"))
# Locate ("Go to highlight") clicks per cycle: a read-only card
# interaction that still costs a full client -> server -> client round
# trip, so its latency is a server-responsiveness signal.
N_HERD_LOCATES = int(os.environ.get("E2E_HERD_LOCATES", "2"))
HERD_THINK_MS = int(os.environ.get("E2E_HERD_THINK_MS", "2000"))
HERD_ACTION_TIMEOUT_MS = int(os.environ.get("E2E_HERD_ACTION_TIMEOUT_MS", "30000"))
HERD_LOAD_TIMEOUT_MS = int(os.environ.get("E2E_HERD_LOAD_TIMEOUT_MS", "120000"))
HERD_BARRIER_TIMEOUT_S = float(os.environ.get("E2E_HERD_BARRIER_TIMEOUT_S", "240"))
HERD_DIAG_SAMPLE_SECONDS = float(os.environ.get("E2E_HERD_DIAG_SAMPLE_SECONDS", "5"))
HERD_SYNC_RELOADS = _bool_env("E2E_HERD_SYNC_RELOADS")

# Worst case if every student burns every timeout: one first load plus a
# reload per cycle, and each cycle's locate/organise/respond actions.
# Bounded rather than generous -- the point is to record collapse, not to
# hang until the pytest timeout.
_DEFAULT_WATCH_S = (
    (N_HERD_CYCLES + 1) * HERD_LOAD_TIMEOUT_MS / 1000
    + N_HERD_CYCLES * (N_HERD_LOCATES + 2) * HERD_ACTION_TIMEOUT_MS / 1000
    + 300
)
HERD_WATCH_SECONDS = float(
    os.environ.get("E2E_HERD_WATCH_SECONDS", str(round(_DEFAULT_WATCH_S)))
)

# Failures that are recorded and printed but never fatal, because this
# harness cannot attribute them to the server:
#
# - respond: opening the tab initialises Milkdown, which is browser-CPU
#   heavy. The soak probe measured this directly -- n=25 produced 74
#   respond timeouts against a flat-task, zero-error server
#   (test_soak_full_crud_load.py DEGRADED_NONFATAL_ACTIONS, class G).
# - locate: the only observable for the round trip is the 'hl-throb'
#   registration, which the app deletes 800 ms later. A main thread
#   blocked past that window loses the signal, so a locate timeout means
#   either the round trip never completed or the window was missed. Both
#   are lag evidence; neither is cleanly attributable.
DEGRADED_NONFATAL_ACTIONS = frozenset({"respond", "locate"})

# The locate round trip: the server answers the click by pushing JS that
# scrolls to the highlight and registers 'hl-throb' for 800 ms
# (``pages/annotation/document.py`` ``_on_locate_highlight`` ->
# ``throbHighlight`` in annotation-highlight.js). CSS highlights are not
# DOM nodes, so this readiness wait -- the same channel every probe uses
# for ``window._highlightsReady`` -- is the only signal available.
_THROB_PRESENT_JS = (
    "() => !!(window.CSS && CSS.highlights && CSS.highlights.has('hl-throb'))"
)
_THROB_ABSENT_JS = (
    "() => !(window.CSS && CSS.highlights && CSS.highlights.has('hl-throb'))"
)
# A throb from the previous locate lives 800 ms; clearing it first stops
# the next locate reading a stale registration as its own answer.
_THROB_CLEAR_TIMEOUT_MS = 5000


@dataclass
class ActionResult:
    """One read-only interaction inside a churn cycle."""

    action: str = ""
    elapsed_ms: int = -1
    error: str | None = None
    degraded: bool = False


@dataclass
class CycleResult:
    """One reload-and-reopen churn cycle for one student."""

    cycle: int = 0
    reload_ms: int = -1
    sidebar_ms: int = -1
    cards: int = -1
    actions: list[ActionResult] = field(default_factory=list)
    error: str | None = None


@dataclass
class HerdObservation:
    """Outcome for one synthetic student."""

    email: str = ""
    workspace_id: str = ""
    annotation_loaded: bool = False
    load_elapsed_ms: int = -1
    sidebar_ms: int = -1
    cards: int = -1
    cycles: list[CycleResult] = field(default_factory=list)
    error: str | None = None


def _fetch_json(url: str) -> dict:
    """Fetch JSON from a localhost E2E helper endpoint."""
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read().decode())


def _think(rng: random.Random) -> None:
    """Sleep a jittered think-time so students de-phase between cycles."""
    if HERD_THINK_MS <= 0:
        return
    time.sleep(rng.uniform(0.5, 1.5) * HERD_THINK_MS / 1000)


def _wait_page_ready(page: Page) -> None:
    """Wait for the deferred load and the highlight pass to complete."""
    from promptgrimoire.docs.helpers import wait_for_annotation_ready

    wait_for_annotation_ready(page, timeout=HERD_LOAD_TIMEOUT_MS)
    page.wait_for_function(
        "() => window._highlightsReady === true",
        timeout=HERD_LOAD_TIMEOUT_MS,
    )


def _wait_sidebar_mounted(page: Page) -> int:
    """Wait for the Vue sidebar's mount epoch, then count its cards.

    The sidebar increments ``window.__annotationCardsEpoch`` on mount
    (``immediate: true`` watch, annotationsidebar.js) and on every items
    change, so ``>= 1`` is the mounted-with-items signal. With ~190
    highlights per clone this is the O(N) card render, failure-mode
    class E.
    """
    page.wait_for_function(
        "() => (window.__annotationCardsEpoch || 0) >= 1",
        timeout=HERD_LOAD_TIMEOUT_MS,
    )
    return page.locator(ANNOTATION_CARD).count()


def _back_to_source(page: Page) -> None:
    """Return to the Source 1 tab (every cycle starts and ends there)."""
    page.get_by_test_id("tab-source-1").click()
    page.wait_for_selector(
        "[data-testid='doc-container']", timeout=HERD_ACTION_TIMEOUT_MS
    )


def _do_locate(page: Page, rng: random.Random, n_cards: int) -> None:
    """Click "Go to highlight" on a random card, wait for the throb."""
    page.wait_for_function(_THROB_ABSENT_JS, timeout=_THROB_CLEAR_TIMEOUT_MS)
    card = page.locator(ANNOTATION_CARD).nth(rng.randrange(n_cards))
    card.get_by_test_id("locate-btn").click()
    page.wait_for_function(_THROB_PRESENT_JS, timeout=HERD_ACTION_TIMEOUT_MS)


def _do_organise(page: Page, n_cards: int) -> None:
    """Open the Organise tab, wait for its columns, return to Source."""
    page.get_by_test_id("tab-organise").click()
    page.locator("[data-testid='organise-columns']").wait_for(
        state="visible", timeout=HERD_ACTION_TIMEOUT_MS
    )
    if n_cards > 0:
        # Columns can appear before their cards do; waiting for a card
        # is what makes this a measurement of the per-card render.
        page.locator("[data-testid='organise-card']").first.wait_for(
            state="visible", timeout=HERD_ACTION_TIMEOUT_MS
        )
    _back_to_source(page)


def _do_respond(page: Page) -> None:
    """Open the Respond tab, wait for the editor, return to Source."""
    page.get_by_test_id("tab-respond").click()
    page.locator("[data-testid='milkdown-editor-container']").wait_for(
        state="visible", timeout=HERD_ACTION_TIMEOUT_MS
    )
    _back_to_source(page)


def _record(
    page: Page,
    result: CycleResult,
    action: str,
    run: Callable[[], None],
) -> None:
    """Run one interaction, recording latency and any failure as data."""
    entry = ActionResult(action=action)
    t0 = time.perf_counter()
    try:
        run()
    except Exception as exc:
        entry.error = f"{type(exc).__name__}: {exc}"
        entry.degraded = action.partition("-")[0] in DEGRADED_NONFATAL_ACTIONS
        # Leave the page where the next action expects it; a failure to
        # recover is itself recorded on the next action.
        with suppress(Exception):
            _back_to_source(page)
    finally:
        entry.elapsed_ms = round((time.perf_counter() - t0) * 1000)
        result.actions.append(entry)


def _run_cycle(
    page: Page,
    rng: random.Random,
    observation: HerdObservation,
    cycle_index: int,
    cycle_barrier: threading.Barrier | None,
) -> None:
    """Reload, re-open the annotation experience, record the timings."""
    result = CycleResult(cycle=cycle_index)
    observation.cycles.append(result)

    if cycle_barrier is None:
        _think(rng)
    else:
        # A broken barrier (a student died, or one is slow past the
        # timeout) degrades this cycle to free-running rather than
        # failing every student in it.
        with suppress(threading.BrokenBarrierError):
            cycle_barrier.wait(timeout=HERD_BARRIER_TIMEOUT_S)

    t0 = time.perf_counter()
    try:
        page.reload(wait_until="domcontentloaded", timeout=HERD_LOAD_TIMEOUT_MS)
        _wait_page_ready(page)
        result.reload_ms = round((time.perf_counter() - t0) * 1000)
        result.cards = _wait_sidebar_mounted(page)
        result.sidebar_ms = round((time.perf_counter() - t0) * 1000)
    except Exception as exc:
        result.error = f"{type(exc).__name__}: {exc}"
        return

    for i in range(N_HERD_LOCATES):
        if result.cards <= 0:
            break
        _record(
            page,
            result,
            f"locate-{i}",
            lambda: _do_locate(page, rng, result.cards),
        )
    _record(page, result, "organise", lambda: _do_organise(page, result.cards))
    _record(page, result, "respond", lambda: _do_respond(page))


def _run_herd_session(
    app_server: str,
    observation: HerdObservation,
    seed: int,
    *,
    start_barrier: threading.Barrier,
    loaded_barrier: threading.Barrier,
    cycle_barriers: list[threading.Barrier],
    done_counter: list[int],
    done_lock: threading.Lock,
    release_event: threading.Event,
) -> None:
    """Authenticate, arrive with the herd, then churn."""
    from playwright.sync_api import sync_playwright

    # Deterministic per-student jitter for load shaping, not cryptography.
    rng = random.Random(seed)  # noqa: S311
    workspace_url = f"{app_server}/annotation?workspace_id={observation.workspace_id}"

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            context = browser.new_context()
            page = context.new_page()

            page.goto(
                f"{app_server}/auth/callback?token=mock-token-{observation.email}"
            )
            page.wait_for_url(
                lambda url: "/auth/callback" not in url,
                timeout=15_000,
            )

            try:
                start_barrier.wait(timeout=HERD_BARRIER_TIMEOUT_S)
                t0 = time.perf_counter()
                page.goto(
                    workspace_url,
                    wait_until="domcontentloaded",
                    timeout=HERD_LOAD_TIMEOUT_MS,
                )
                _wait_page_ready(page)
                observation.load_elapsed_ms = round((time.perf_counter() - t0) * 1000)
                observation.annotation_loaded = True
                observation.cards = _wait_sidebar_mounted(page)
                observation.sidebar_ms = round((time.perf_counter() - t0) * 1000)
                # This barrier only marks "the herd has landed" for the
                # diagnostics sample. One student failing aborts it for
                # everyone, so a break here must not convert healthy
                # students into failed ones, nor cost them their churn.
                with suppress(threading.BrokenBarrierError):
                    loaded_barrier.wait(timeout=HERD_BARRIER_TIMEOUT_S)

                for cycle_index in range(N_HERD_CYCLES):
                    _run_cycle(
                        page,
                        rng,
                        observation,
                        cycle_index,
                        cycle_barriers[cycle_index] if cycle_barriers else None,
                    )
            except Exception as exc:
                observation.error = f"{type(exc).__name__}: {exc}"
                # Release everyone still waiting on this student rather
                # than making them burn the full barrier timeout.
                for barrier in (loaded_barrier, *cycle_barriers):
                    with suppress(threading.BrokenBarrierError):
                        barrier.abort()
            finally:
                with done_lock:
                    done_counter[0] += 1
                release_event.wait(timeout=120)
                page.goto("about:blank")
                context.close()
        finally:
            browser.close()


def _percentiles(values: list[int]) -> str:
    """Render p50/p90/max for a latency list."""
    if not values:
        return "n/a"
    ordered = sorted(values)
    p50 = ordered[len(ordered) // 2]
    p90 = ordered[min(len(ordered) - 1, (len(ordered) * 9) // 10)]
    return f"p50={p50}ms p90={p90}ms max={ordered[-1]}ms"


def _all_actions(
    observations: list[HerdObservation],
) -> list[tuple[HerdObservation, CycleResult, ActionResult]]:
    """Flatten every recorded action with its student and cycle."""
    return [
        (observation, cycle, action)
        for observation in observations
        for cycle in observation.cycles
        for action in cycle.actions
    ]


def _print_cycle_table(observations: list[HerdObservation]) -> None:
    """Print reload and sidebar latency per churn cycle."""
    for cycle_index in range(N_HERD_CYCLES):
        cycles = [c for o in observations for c in o.cycles if c.cycle == cycle_index]
        reloads = [c.reload_ms for c in cycles if c.reload_ms >= 0]
        sidebars = [c.sidebar_ms for c in cycles if c.sidebar_ms >= 0]
        errors = sum(1 for c in cycles if c.error)
        print(
            f"cycle {cycle_index}: reload n={len(reloads)} {_percentiles(reloads)}"
            f" | sidebar {_percentiles(sidebars)} | reload failures {errors}"
        )


def _print_summary(
    observations: list[HerdObservation],
    diag_samples: list[dict],
) -> None:
    """Print the latency tables and the diagnostics trajectory."""
    loads = [o.load_elapsed_ms for o in observations if o.load_elapsed_ms >= 0]
    sidebars = [o.sidebar_ms for o in observations if o.sidebar_ms >= 0]
    cards = [o.cards for o in observations if o.cards >= 0]

    mode = "synchronized" if HERD_SYNC_RELOADS else "free-running"
    print(
        f"\n=== Thundering-herd probe (n={N_HERD_SESSIONS}, "
        f"{N_HERD_CYCLES} {mode} cycles, PABAI) ==="
    )
    print(f"first load:     {_percentiles(loads)}")
    print(f"first sidebar:  {_percentiles(sidebars)}")
    print(
        f"cards rendered: min={min(cards) if cards else 'n/a'} "
        f"max={max(cards) if cards else 'n/a'}"
    )
    _print_cycle_table(observations)

    actions = _all_actions(observations)
    for name in ("locate", "organise", "respond"):
        ok = [
            a.elapsed_ms
            for _, _, a in actions
            if a.action.startswith(name) and a.error is None
        ]
        print(f"{name:<10} n={len(ok):<5} {_percentiles(ok)}")

    degraded = [(o.email, a.action) for o, _, a in actions if a.degraded]
    failures = [
        (o.email, a.action, a.error)
        for o, _, a in actions
        if a.error is not None and not a.degraded
    ]
    print(f"degraded (unattributable, nonfatal): {len(degraded)}")
    print(f"action failures (fatal): {len(failures)}")
    for email, action, error in failures[:20]:
        print(f"  {email} {action}: {error}")

    print("--- diagnostics trajectory ---")
    for sample in diag_samples:
        print(
            f"  t={sample['t_s']:.0f}s rss={sample.get('rss_bytes')}"
            f" clients={sample.get('nicegui_clients')}"
            f" tasks={sample.get('asyncio_tasks')}"
            f" pool={sample.get('pool')}"
        )


def _herd_run_meta(started: datetime, ended: datetime) -> dict:
    """Describe this run's configuration for the diag JSON."""
    return build_run_meta(
        probe="thundering_herd",
        env=os.environ,
        started=started,
        ended=ended,
        knobs={
            "sessions": N_HERD_SESSIONS,
            "cycles": N_HERD_CYCLES,
            "locates_per_cycle": N_HERD_LOCATES,
            "sync_reloads": HERD_SYNC_RELOADS,
            "think_ms": HERD_THINK_MS,
            "action_timeout_ms": HERD_ACTION_TIMEOUT_MS,
            "load_timeout_ms": HERD_LOAD_TIMEOUT_MS,
            "barrier_timeout_s": HERD_BARRIER_TIMEOUT_S,
            "watch_seconds": HERD_WATCH_SECONDS,
            "diag_sample_seconds": HERD_DIAG_SAMPLE_SECONDS,
            "fixture": PABAI_FIXTURE.name,
        },
        snapshot_enabled=get_settings().snapshot.enabled,
        branch=get_current_branch(),
    )


def _maybe_write_diag(
    observations: list[HerdObservation],
    diag_samples: list[dict],
    run_meta: dict,
    server_page_load: dict,
    verdict: MeasuredVerdict,
) -> None:
    """Optionally persist one atomic verdict-bearing result envelope."""
    raw_path = os.environ.get("E2E_HERD_DIAG_PATH")
    if not raw_path:
        return
    payload = {
        "run_meta": run_meta,
        "server_page_load": server_page_load,
        "sessions": N_HERD_SESSIONS,
        "cycles": N_HERD_CYCLES,
        "locates_per_cycle": N_HERD_LOCATES,
        "sync_reloads": HERD_SYNC_RELOADS,
        "think_ms": HERD_THINK_MS,
        "diag_samples": diag_samples,
        "results": [asdict(o) for o in observations],
    }
    write_result_envelope(Path(raw_path), verdict=verdict, probe_payload=payload)


def _herd_verdict(observations: list[HerdObservation]) -> MeasuredVerdict:
    """Classify the existing cohort boundary before persisting its evidence."""
    load_failures = sum(
        1
        for observation in observations
        if observation.error or not observation.annotation_loaded
    ) + sum(
        1 for observation in observations for cycle in observation.cycles if cycle.error
    )
    fatal_actions = sum(
        1
        for observation, _cycle, action in _all_actions(observations)
        if action.error is not None and not action.degraded
    )
    degraded_actions = sum(
        1
        for _observation, _cycle, action in _all_actions(observations)
        if action.error is not None and action.degraded
    )
    failed_students = {
        observation.email
        for observation in observations
        if observation.error
        or not observation.annotation_loaded
        or any(cycle.error for cycle in observation.cycles)
        or any(
            action.error and not action.degraded
            for cycle in observation.cycles
            for action in cycle.actions
        )
    }
    max_failed = max(3, N_HERD_SESSIONS // 10)
    collapse_reasons = (
        (
            (
                f"{len(failed_students)} of {N_HERD_SESSIONS} students failed "
                f"the cohort gate {max_failed}"
            ),
        )
        if len(failed_students) > max_failed
        else ()
    )
    return measured_verdict(
        load_failure_count=load_failures,
        fatal_action_failure_count=fatal_actions,
        degraded_action_count=degraded_actions,
        collapse_reasons=collapse_reasons,
    )


def _report_failures_and_gate(
    observations: list[HerdObservation],
    *,
    enforce_gate: bool = True,
) -> None:
    """Print every failure, then assert only against systemic collapse.

    A student counts as failed if their first load never completed, any
    reload cycle failed, or any non-degraded action errored. The gate
    mirrors the cram probe: individual failures are data, and the run
    fails only when the failures spread across the cohort.
    """
    load_errors = [f"{o.email}: {o.error}" for o in observations if o.error]
    cycle_errors = [
        f"{o.email} cycle-{c.cycle}: {c.error}"
        for o in observations
        for c in o.cycles
        if c.error
    ]
    action_failures = [
        f"{o.email} {a.action}: {a.error}"
        for o, _, a in _all_actions(observations)
        if a.error is not None and not a.degraded
    ]
    if load_errors or cycle_errors or action_failures:
        print(f"\nherd failures at n={N_HERD_SESSIONS} (reported, not fatal):")
        for line in (*load_errors, *cycle_errors, *action_failures):
            print(f"  {line}")

    failed_students = {
        o.email
        for o in observations
        if o.error
        or not o.annotation_loaded
        or any(c.error for c in o.cycles)
        or any(a.error and not a.degraded for c in o.cycles for a in c.actions)
    }
    max_failed = max(3, N_HERD_SESSIONS // 10)
    if not enforce_gate:
        return
    assert len(failed_students) <= max_failed, (
        f"Herd collapse: {len(failed_students)} of {N_HERD_SESSIONS} students"
        f" failed (gate {max_failed}): {sorted(failed_students)}"
    )


@pytest.fixture(scope="module")
def pabai_herd_template() -> Iterator[str]:
    """Bind the PABAI fixture as an activity template for the run."""
    ensure_fixture_workspace(PABAI_FIXTURE)
    activity_id, old_template_id = asyncio.run(
        create_template_activity(PABAI_FIXTURE, course_name="Thundering Herd Probe")
    )
    try:
        yield activity_id
    finally:
        asyncio.run(
            restore_template_binding(PABAI_FIXTURE, activity_id, old_template_id)
        )


class TestThunderingHerd:
    """Simultaneous arrival plus reload churn on heavyweight clones."""

    def test_thundering_herd_pabai(
        self,
        app_server: str,
        pabai_herd_template: str,
    ) -> None:
        """Find whether n students arriving at once stay within bounds."""
        run_started = utc_now()
        observations: list[HerdObservation] = []
        for _ in range(N_HERD_SESSIONS):
            email = f"herd-{uuid4().hex[:8]}@test.example.edu.au"
            workspace_id = asyncio.run(
                provision_clone_for_email(pabai_herd_template, email)
            )
            observations.append(HerdObservation(email=email, workspace_id=workspace_id))

        diag_samples: list[dict] = []
        t_origin = time.perf_counter()

        def sample_diag() -> None:
            # A server that has fallen over cannot answer this, and that
            # is precisely the case the probe exists to record: keep the
            # failed sample as evidence rather than aborting the run and
            # losing every other observation with it.
            diag: dict
            try:
                diag = _fetch_json(f"{app_server}/api/test/diagnostics")
            except Exception as exc:
                diag = {"error": f"{type(exc).__name__}: {exc}"}
            diag["t_s"] = time.perf_counter() - t_origin
            diag_samples.append(diag)

        start_barrier = threading.Barrier(
            N_HERD_SESSIONS + 1, timeout=HERD_BARRIER_TIMEOUT_S
        )
        loaded_barrier = threading.Barrier(
            N_HERD_SESSIONS + 1, timeout=HERD_BARRIER_TIMEOUT_S
        )
        # Students only: the harness thread takes no part in the churn.
        cycle_barriers = (
            [
                threading.Barrier(N_HERD_SESSIONS, timeout=HERD_BARRIER_TIMEOUT_S)
                for _ in range(N_HERD_CYCLES)
            ]
            if HERD_SYNC_RELOADS
            else []
        )
        done_counter = [0]
        done_lock = threading.Lock()
        release_event = threading.Event()

        threads = [
            threading.Thread(
                target=_run_herd_session,
                args=(app_server, observation, i),
                kwargs={
                    "start_barrier": start_barrier,
                    "loaded_barrier": loaded_barrier,
                    "cycle_barriers": cycle_barriers,
                    "done_counter": done_counter,
                    "done_lock": done_lock,
                    "release_event": release_event,
                },
                name=f"herd-session-{i}",
            )
            for i, observation in enumerate(observations)
        ]

        for thread in threads:
            thread.start()

        try:
            sample_diag()
            # A broken start barrier means the herd never formed (a
            # browser failed to launch, say). Every student records that
            # as its own load error, so let the run reach its report
            # rather than dying here with no evidence written.
            with suppress(threading.BrokenBarrierError):
                start_barrier.wait(timeout=HERD_BARRIER_TIMEOUT_S)
            with suppress(threading.BrokenBarrierError):
                loaded_barrier.wait(timeout=HERD_BARRIER_TIMEOUT_S)
            # The herd has landed (or broken): this sample is its peak.
            sample_diag()

            watch_deadline = time.perf_counter() + HERD_WATCH_SECONDS
            while time.perf_counter() < watch_deadline:
                with done_lock:
                    if done_counter[0] >= N_HERD_SESSIONS:
                        break
                time.sleep(HERD_DIAG_SAMPLE_SECONDS)
                sample_diag()
        finally:
            release_event.set()
            for thread in threads:
                thread.join(timeout=300)

        sample_diag()
        run_ended = utc_now()
        _print_summary(observations, diag_samples)

        # Browser-observed latency above includes Playwright and the
        # co-located browser's own CPU contention (failure-mode class G);
        # the server's page_load_profile is the production-magnitude
        # number, so both are reported side by side.
        server_page_load = collect_server_page_load(
            window_start=run_started,
            window_end=run_ended,
        )
        print_server_page_load(server_page_load)
        verdict = _herd_verdict(observations)
        _maybe_write_diag(
            observations,
            diag_samples,
            _herd_run_meta(run_started, run_ended),
            server_page_load,
            verdict,
        )

        _report_failures_and_gate(
            observations,
            enforce_gate=should_fail_pytest_for_verdict(verdict.classification),
        )
