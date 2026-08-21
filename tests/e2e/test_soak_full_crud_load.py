"""Perf probe: sustained "doing all the things" students (crunched soak).

Where the cram probe (test_assessment_cram_load.py) is a synchronized
burst of highlight+comment batches, this probe models the calibrated
worst case agreed 2026-08-18: every student behaves like the fastest
real student observed in the 2026-08-17 LAWS8001 tutorial, times a
scaling knob, doing full CRUD across all three tabs.

Calibration (prod CRDT extract, 42 active students, ~30 min exercise):
median 0.65 actions/min sustained per student, p90 1.25, fastest 2.15.
``E2E_SOAK_RATE_MULT`` (default 5) multiplies the observed median, so
the default soak student works at 3.25 actions/min -- faster than the
fastest real student -- for ``E2E_SOAK_MINUTES`` (default 15).

Each student runs a weighted action mix (weights below), seeded by a
few forced highlight creations:

- create highlight (10 case-brief tags), add comment,
- delete own highlight / comment,
- create a new tag via the toolbar dialog (absent from the tutorial),
- drag a card between tag columns on the Organise tab,
- type into the Respond (Milkdown) editor,
- browse tabs (read-only revisit).

Students alternate between the Narayan and Savage fixtures (two
distinct activity templates), and arrivals are spread over
``E2E_SOAK_ARRIVAL_SPREAD_S`` rather than synchronized.

Ramp externally in steps of 25:

    E2E_SOAK_SESSIONS=25 uv run grimoire e2e perf \
        tests/e2e/test_soak_full_crud_load.py

Any load or action failure fails the probe -- the printed latency
table and diagnostics samples are the boundary evidence. A student
finishing with implausibly few actions also fails (the probe must not
pass by doing nothing).
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
from uuid import UUID, uuid4

import pytest

from promptgrimoire.cli.perf.results import (
    MeasuredVerdict,
    PerfClassification,
    measured_verdict,
    should_fail_pytest_for_verdict,
    write_result_envelope,
)
from promptgrimoire.config import get_current_branch, get_settings
from tests.e2e.assessment_fixtures import (
    CASE_BRIEF_TAG_COUNT,
    NARAYAN_FIXTURE,
    SAVAGE_FIXTURE,
    AssessmentFixture,
    create_template_activity,
    ensure_fixture_workspace,
    fixture_document_words,
    provision_clone_for_email,
    restore_template_binding,
)
from tests.e2e.perf_reporting import (
    build_run_meta,
    collect_server_page_load,
    print_server_page_load,
    utc_now,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
    from datetime import datetime

    from playwright.sync_api import Page

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.perf,
    pytest.mark.timeout(3600),
    pytest.mark.skipif(
        not get_settings().dev.test_database_url,
        reason="DEV__TEST_DATABASE_URL not configured",
    ),
]

N_SOAK_SESSIONS = int(os.environ.get("E2E_SOAK_SESSIONS", "25"))
# Observed median sustained rate, 2026-08-17 LAWS8001 calibration.
OBSERVED_ACTIONS_PER_MIN = 0.65
SOAK_RATE_MULT = float(os.environ.get("E2E_SOAK_RATE_MULT", "5"))
SOAK_MINUTES = float(os.environ.get("E2E_SOAK_MINUTES", "15"))
SOAK_ARRIVAL_SPREAD_S = float(os.environ.get("E2E_SOAK_ARRIVAL_SPREAD_S", "300"))
SOAK_ACTION_TIMEOUT_MS = int(os.environ.get("E2E_SOAK_ACTION_TIMEOUT_MS", "30000"))
SOAK_DIAG_SAMPLE_SECONDS = float(os.environ.get("E2E_SOAK_DIAG_SAMPLE_SECONDS", "10"))

ACTIONS_PER_MIN = OBSERVED_ACTIONS_PER_MIN * SOAK_RATE_MULT
MAX_CONSECUTIVE_ACTION_FAILURES = 3
SEED_HIGHLIGHTS = 3
# Wedge-guard floor: a student under a quarter of its paced budget is
# a silently-stopped browser, not a slow one.  Throughput attainment
# (reported per run) is the actual how-much-got-done measurement; at
# 20x rate legitimate students sit near 45-55% attainment because 30s
# timeouts eat real time, so the guard must sit well below that.
MIN_ACTION_FRACTION = 0.25
# Server-attributable failures are a boundary only when systemic:
# this share of students affected (floor 3, so small-n runs keep a
# meaningful gate), or this fraction of all actions.  Absolute-3 read
# a calm n=100 run (6 students, one isolated timeout each, 0.14% of
# actions) as a boundary; scaling with n keeps the gate about spread,
# not run size.
SOAK_MAX_FATAL_STUDENTS = max(3, N_SOAK_SESSIONS // 10)
SOAK_MAX_FATAL_FRACTION = 0.01

# Weighted "doing all the things" mix. An ineligible pick (e.g. delete
# with nothing to delete) substitutes highlight_create.
# E2E_SOAK_WEIGHTS='{"comment_delete": 0.3}' partially overrides.
_DEFAULT_WEIGHTS: dict[str, float] = {
    "highlight_create": 0.40,
    "respond_type": 0.20,
    "comment_add": 0.12,
    "organise_drag": 0.10,
    "highlight_delete": 0.06,
    "tag_create": 0.05,
    "tab_browse": 0.05,
    "comment_delete": 0.02,
}
_weight_overrides: dict[str, float] = json.loads(
    os.environ.get("E2E_SOAK_WEIGHTS", "{}")
)
if unknown := set(_weight_overrides) - set(_DEFAULT_WEIGHTS):
    msg = f"E2E_SOAK_WEIGHTS names unknown actions: {sorted(unknown)}"
    raise RuntimeError(msg)
ACTION_WEIGHTS: list[tuple[str, float]] = list(
    (_DEFAULT_WEIGHTS | _weight_overrides).items()
)

ANNOTATION_CARD = "[data-testid='annotation-card']"


# Action types whose failures are browser-side degradation, not server
# boundary evidence (failure-mode class G, co-located harness):
# - respond_type: Milkdown init is browser-CPU-heavy; n=25 had 74
#   timeouts against a flat-task, zero-error server.
# - organise_drag: SortableJS drops bounce ~1% when a rebuild lands
#   mid-drag; a real student re-drags (retried, then degraded).
# These are counted and reported, never fatal. If the server itself
# stalls, the fatal action types (creates, comments, tags) catch it.
DEGRADED_NONFATAL_ACTIONS = frozenset({"respond_type", "organise_drag"})


@dataclass
class ActionResult:
    """One soak action."""

    action: str = ""
    elapsed_ms: int = -1
    error: str | None = None
    degraded: bool = False
    # Unique text marker typed by this action (respond_type only),
    # recorded BEFORE typing so the post-run DB audit can classify
    # every attempt: found-in-CRDT vs never-landed.
    marker: str | None = None


@dataclass
class SoakObservation:
    """Outcome for one synthetic student."""

    email: str = ""
    workspace_id: str = ""
    fixture: str = ""
    arrival_offset_s: float = 0.0
    annotation_loaded: bool = False
    load_elapsed_ms: int = -1
    pass_elapsed_ms: int = -1
    actions: list[ActionResult] = field(default_factory=list)
    error: str | None = None


@dataclass(frozen=True, slots=True)
class SoakGate:
    """Derived soak boundary and its complete supporting failures."""

    load_errors: tuple[str, ...]
    fatal_students: frozenset[str]
    action_failures: tuple[str, ...]
    total_actions: int
    systemic: bool
    verdict: MeasuredVerdict


def _soak_gate(observations: list[SoakObservation]) -> SoakGate:
    """Classify one soak cohort after every student has finished."""
    load_errors = tuple(o.error for o in observations if o.error is not None)
    fatal_students = frozenset(
        observation.email
        for observation in observations
        for action in observation.actions
        if action.error is not None and not action.degraded
    )
    action_failures = tuple(
        f"{observation.email} {action.action}: {action.error}"
        for observation in observations
        for action in observation.actions
        if action.error is not None and not action.degraded
    )
    total_actions = sum(len(observation.actions) for observation in observations)
    systemic = len(fatal_students) >= SOAK_MAX_FATAL_STUDENTS or len(
        action_failures
    ) > max(1, int(total_actions * SOAK_MAX_FATAL_FRACTION))
    unloaded_students = [
        observation.email
        for observation in observations
        if not observation.annotation_loaded
    ]
    wedge_failures = _wedge_failures(observations)
    degraded_actions = sum(
        1
        for observation in observations
        for action in observation.actions
        if action.error is not None and action.degraded
    )
    collapse_reasons: list[str] = []
    if load_errors:
        collapse_reasons.append(f"{len(load_errors)} session load failure(s)")
    if action_failures and systemic:
        collapse_reasons.append(f"{len(action_failures)} systemic action failure(s)")
    if unloaded_students:
        collapse_reasons.append(
            f"{len(unloaded_students)} annotation load boundary failure(s)"
        )
    if wedge_failures:
        collapse_reasons.append(f"{len(wedge_failures)} browser wedge(s)")
    verdict = measured_verdict(
        load_failure_count=len(load_errors),
        fatal_action_failure_count=len(action_failures),
        degraded_action_count=degraded_actions,
        collapse_reasons=tuple(collapse_reasons),
    )
    return SoakGate(
        load_errors=load_errors,
        fatal_students=fatal_students,
        action_failures=action_failures,
        total_actions=total_actions,
        systemic=systemic,
        verdict=verdict,
    )


class StudentState:
    """Mutable per-student bookkeeping for eligibility and waits."""

    def __init__(self, words: list[str], rng: random.Random) -> None:
        self.rng = rng
        self.words = words
        self.highlight_count = 0
        # Cards are sorted by start_char, so per-card indices rot as
        # highlights are created; track only the live comment count and
        # hunt the DOM when deleting.
        self.comments_alive = 0
        self.tags_created = 0

    def plan_needles(self, count: int) -> list[str]:
        """Pick word-span needles spread through the document text."""
        needles: list[str] = []
        for _ in range(count):
            span = self.rng.randint(8, 25)
            first = self.rng.randint(1, len(self.words) - span - 1)
            needles.append(" ".join(self.words[first : first + span]))
        return needles


def _fetch_json(url: str) -> dict:
    """Fetch JSON from a localhost E2E helper endpoint."""
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read().decode())


def _resolve_next_range(page: Page, needles: list[str]) -> tuple[int, int]:
    """Resolve the next findable needle to walker char offsets."""
    from tests.e2e.highlight_tools import find_text_range

    while needles:
        with suppress(ValueError):
            return find_text_range(page, needles.pop(0))
    msg = "needle pool exhausted"
    raise RuntimeError(msg)


def _back_to_source(page: Page) -> None:
    """Return to the Source 1 tab (all actions start and end there)."""
    page.get_by_test_id("tab-source-1").click()
    page.wait_for_selector(
        "[data-testid='doc-container']", timeout=SOAK_ACTION_TIMEOUT_MS
    )


def _card_count(page: Page) -> int:
    """Current annotation-card count (the per-highlight sidebar signal).

    ``wait_for_css_highlight_count`` is unsuitable here: CSS.highlights
    keys are per TAG (``hl-{tag}``), so with random tag picks the count
    stops moving on the second highlight of any tag. The cram probe
    dodged this by cycling exactly 10 tags for 10 highlights.
    """
    return page.locator(ANNOTATION_CARD).count()


def _wait_card_count(page: Page, expected: int, *, timeout: int) -> None:
    """Wait until the sidebar renders exactly *expected* cards.

    The card renders during the sidebar rebuild, so this doubles as the
    rebuild-complete signal (no separate epoch wait needed).
    """
    page.wait_for_function(
        "([sel, n]) => document.querySelectorAll(sel).length === n",
        arg=[ANNOTATION_CARD, expected],
        timeout=timeout,
    )


def _do_highlight_create(
    page: Page, state: StudentState, _result: ActionResult
) -> None:
    """Create one highlight: single attempt, failure recorded as-is.

    No retry-on-no-op: a silent no-op or a slow round trip IS the
    measurement. The failure rate per step is the deliverable.
    """
    from tests.e2e.highlight_tools import (
        create_highlight_with_tag,
        scroll_to_char,
    )

    # The needle pool only absorbs fixture-parsing misses (walker
    # whitespace collapsing) -- not system retries.
    needles = state.plan_needles(8)
    # Re-read the actual DOM count so a late-landing earlier action
    # cannot skew the expectation (self-healing baseline).
    before = _card_count(page)
    start, end = _resolve_next_range(page, needles)
    scroll_to_char(page, start)
    create_highlight_with_tag(
        page,
        start,
        end,
        state.rng.randrange(CASE_BRIEF_TAG_COUNT),
    )
    _wait_card_count(page, before + 1, timeout=SOAK_ACTION_TIMEOUT_MS)
    state.highlight_count = before + 1


def _do_comment_add(page: Page, state: StudentState, _result: ActionResult) -> None:
    """Comment on a random own card (epoch wait inside the helper)."""
    from tests.e2e.card_helpers import add_comment_to_highlight

    idx = state.rng.randrange(_card_count(page))
    add_comment_to_highlight(
        page,
        f"Soak note {uuid4().hex[:6]}",
        card_index=idx,
    )
    state.comments_alive += 1


def _do_highlight_delete(
    page: Page, state: StudentState, _result: ActionResult
) -> None:
    """Delete a random own highlight from the sidebar."""
    before = _card_count(page)
    idx = state.rng.randrange(before)
    card = page.locator(ANNOTATION_CARD).nth(idx)
    # The deleted card may carry comments; resync the live count from
    # its hidden per-card comment-count span (absent until first expand
    # builds the detail section -- treat absent as unknown-but-possible).
    comment_count_span = card.locator("[data-testid='comment-count']")
    lost_comments = 0
    if comment_count_span.count() > 0:
        with suppress(ValueError):
            lost_comments = int(comment_count_span.inner_text())
    card.get_by_test_id("delete-highlight-btn").click()
    _wait_card_count(page, before - 1, timeout=SOAK_ACTION_TIMEOUT_MS)
    state.highlight_count = before - 1
    state.comments_alive = max(0, state.comments_alive - lost_comments)


def _do_comment_delete(page: Page, state: StudentState, _result: ActionResult) -> None:
    """Delete one comment, hunting cards for a deletable one.

    Card indices shift as highlights are created (sorted by
    start_char), so the comment's location is discovered by expanding
    cards from a random start rather than tracked by index.
    """
    from tests.e2e.card_helpers import expand_card

    n_cards = _card_count(page)
    start = state.rng.randrange(n_cards)
    for offset in range(n_cards):
        idx = (start + offset) % n_cards
        expand_card(page, idx)
        card = page.locator(ANNOTATION_CARD).nth(idx)
        delete_btns = card.locator("[data-testid='comment-delete']")
        if delete_btns.count() == 0:
            continue
        old_epoch = page.evaluate("() => window.__annotationCardsEpoch || 0")
        delete_btns.first.click()
        page.wait_for_function(
            "(oldEpoch) => (window.__annotationCardsEpoch || 0) > oldEpoch",
            arg=old_epoch,
            timeout=SOAK_ACTION_TIMEOUT_MS,
        )
        state.comments_alive -= 1
        return
    msg = f"{state.comments_alive} comments tracked alive but none found in DOM"
    raise RuntimeError(msg)


def _do_tag_create(page: Page, state: StudentState, _result: ActionResult) -> None:
    """Create a new tag via the toolbar quick-create dialog."""
    tag_name = f"Soak {uuid4().hex[:4]}"
    page.get_by_test_id("tag-create-btn").click()
    dialog = page.get_by_test_id("tag-quick-create-dialog")
    dialog.wait_for(state="visible", timeout=SOAK_ACTION_TIMEOUT_MS)
    page.get_by_test_id("tag-quick-create-name-input").fill(tag_name)
    page.get_by_test_id("quick-create-save-btn").click()
    toolbar = page.get_by_test_id("tag-toolbar")
    button = toolbar.locator('[data-testid^="tag-btn-"]').filter(has_text=tag_name)
    button.wait_for(state="visible", timeout=SOAK_ACTION_TIMEOUT_MS)
    state.tags_created += 1


def _do_organise_drag(page: Page, state: StudentState, _result: ActionResult) -> None:
    """Drag a card between tag columns: single attempt, no retry.

    A bounced drop (rebuild landing mid-drag) is recorded as a failure
    -- the bounce rate per step is part of the measurement.
    """
    page.get_by_test_id("tab-organise").click()
    columns = page.locator("[data-testid='tag-column']")
    columns.first.wait_for(state="visible", timeout=SOAK_ACTION_TIMEOUT_MS)
    n_columns = columns.count()

    source_idx = None
    for i in range(n_columns):
        if columns.nth(i).locator("[data-testid='organise-card']").count() > 0:
            source_idx = i
            break
    if source_idx is None:
        msg = "no organise column holds a card"
        raise RuntimeError(msg)

    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    # Adjacent target only: SortableJS misses drops on far columns that
    # need horizontal scrolling mid-drag (mechanics run 3 evidence);
    # test_tag_sync.py's passing drag is likewise between neighbours.
    neighbours = [i for i in (source_idx - 1, source_idx + 1) if 0 <= i < n_columns]
    target_idx = state.rng.choice(neighbours)
    target_col = columns.nth(target_idx)
    target_col.scroll_into_view_if_needed()
    source_before = (
        columns.nth(source_idx).locator("[data-testid='organise-card']").count()
    )

    try:
        # Cards drag directly onto the target column's sortable
        # container (the pattern test_tag_sync.py uses); no handle.
        card = columns.nth(source_idx).locator("[data-testid='organise-card']").first
        card.drag_to(target_col.locator(".nicegui-sortable").first)
        try:
            # Success = the source column lost the card. Where it
            # landed is secondary: any completed drop is a real
            # retag round trip.
            page.wait_for_function(
                "([colIdx, n]) => {"
                "  const cols = document.querySelectorAll("
                "    '[data-testid=\"tag-column\"]');"
                "  if (!cols[colIdx]) return false;"
                "  return cols[colIdx].querySelectorAll("
                "    '[data-testid=\"organise-card\"]').length < n;"
                "}",
                arg=[source_idx, source_before],
                timeout=SOAK_ACTION_TIMEOUT_MS,
            )
        except PlaywrightTimeoutError:
            counts = [
                columns.nth(i).locator("[data-testid='organise-card']").count()
                for i in range(n_columns)
            ]
            msg = (
                f"drag produced no column change: "
                f"source_idx={source_idx} (had {source_before}), "
                f"target_idx={target_idx}, column counts now {counts}"
            )
            raise RuntimeError(msg) from None
    finally:
        _back_to_source(page)


def _do_respond_type(page: Page, state: StudentState, result: ActionResult) -> None:
    """Type a uniquely-markered sentence into the Respond (Milkdown) editor.

    The marker is recorded before any page interaction: a tab or editor
    click that times out raises before a keystroke is sent, so the
    post-run audit reads a missing marker as never-typed rather than as
    typed-then-lost.
    """
    marker = uuid4().hex[:6]
    result.marker = marker
    page.get_by_test_id("tab-respond").click()
    editor = page.locator("[data-testid='milkdown-editor-container']")
    editor.wait_for(state="visible", timeout=SOAK_ACTION_TIMEOUT_MS)
    editor.locator("[contenteditable]").first.click()
    # Once the draft has content the centre-click lands the caret
    # mid-text, splicing the new sentence into an old one: that garbles
    # the draft and cuts markers in half, so the post-run audit reads
    # landed text as lost. Appending at the end is also what a student
    # actually does.
    page.keyboard.press("Control+End")
    page.keyboard.type(
        f"Soak analysis point {marker}: the reasoning turns on "
        f"the {state.rng.choice(['duty', 'breach', 'causation', 'damages'])} limb. "
    )
    _back_to_source(page)


def _do_tab_browse(page: Page, _state: StudentState, _result: ActionResult) -> None:
    """Read-only revisit: Organise then back to Source."""
    page.get_by_test_id("tab-organise").click()
    page.locator("[data-testid='organise-columns']").wait_for(
        state="visible", timeout=SOAK_ACTION_TIMEOUT_MS
    )
    _back_to_source(page)


ACTION_IMPLS = {
    "highlight_create": _do_highlight_create,
    "comment_add": _do_comment_add,
    "highlight_delete": _do_highlight_delete,
    "comment_delete": _do_comment_delete,
    "tag_create": _do_tag_create,
    "organise_drag": _do_organise_drag,
    "respond_type": _do_respond_type,
    "tab_browse": _do_tab_browse,
}


def _eligible(action: str, state: StudentState) -> bool:
    """Whether the picked action can run against current student state."""
    if action == "comment_add":
        return state.highlight_count >= 1
    if action == "highlight_delete":
        # Keep at least one highlight so later picks stay eligible.
        return state.highlight_count >= 2
    if action == "comment_delete":
        return state.comments_alive >= 1
    if action == "organise_drag":
        return state.highlight_count >= 1
    return True


def _pick_action(state: StudentState, action_index: int) -> str:
    """Pick the next action: forced seed highlights, then weighted mix."""
    if action_index < SEED_HIGHLIGHTS:
        return "highlight_create"
    names = [name for name, _ in ACTION_WEIGHTS]
    weights = [w for _, w in ACTION_WEIGHTS]
    action = state.rng.choices(names, weights=weights, k=1)[0]
    if not _eligible(action, state):
        return "highlight_create"
    return action


def _run_soak_pass(
    page: Page,
    state: StudentState,
    observation: SoakObservation,
) -> None:
    """Run the paced full-CRUD action loop until the soak deadline."""
    pass_start = time.perf_counter()
    deadline = pass_start + SOAK_MINUTES * 60
    mean_delay_s = 60.0 / ACTIONS_PER_MIN
    consecutive_failures = 0
    action_index = 0

    while time.perf_counter() < deadline:
        action = _pick_action(state, action_index)
        result = ActionResult(action=f"{action}-{action_index}")
        t0 = time.perf_counter()
        try:
            ACTION_IMPLS[action](page, state, result)
            consecutive_failures = 0
        except Exception as exc:
            result.error = f"{type(exc).__name__}: {exc}"
            # A select_chars whiff is harness-attributed (#562): it must not
            # bill the app or trip the systemic gate. Error text stays in the
            # diag JSON so analysis buckets whiffs separately from class G.
            if action in DEGRADED_NONFATAL_ACTIONS or "Harness bug (#562)" in str(exc):
                result.degraded = True
            else:
                consecutive_failures += 1
            with suppress(Exception):
                _back_to_source(page)
        finally:
            result.elapsed_ms = round((time.perf_counter() - t0) * 1000)
            observation.actions.append(result)
        action_index += 1

        if consecutive_failures >= MAX_CONSECUTIVE_ACTION_FAILURES:
            break
        time.sleep(state.rng.uniform(0.5, 1.5) * mean_delay_s)

    observation.pass_elapsed_ms = round((time.perf_counter() - pass_start) * 1000)


def _run_soak_session(
    app_server: str,
    observation: SoakObservation,
    fixture: AssessmentFixture,
    seed: int,
    *,
    ready_barrier: threading.Barrier,
    done_counter: list[int],
    done_lock: threading.Lock,
) -> None:
    """Authenticate, arrive on schedule, load the clone, run the soak."""
    from playwright.sync_api import sync_playwright

    from promptgrimoire.docs.helpers import wait_for_annotation_ready

    # Deterministic per-student jitter for load shaping, not cryptography.
    rng = random.Random(seed)  # noqa: S311
    words = fixture_document_words(fixture)
    state = StudentState(words, rng)

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
                ready_barrier.wait(timeout=240)
                time.sleep(observation.arrival_offset_s)
                t0 = time.perf_counter()
                page.goto(
                    f"{app_server}/annotation?workspace_id={observation.workspace_id}",
                    wait_until="domcontentloaded",
                    timeout=120_000,
                )
                wait_for_annotation_ready(page, timeout=120_000)
                page.wait_for_function(
                    "() => window._highlightsReady === true",
                    timeout=120_000,
                )
                observation.load_elapsed_ms = round((time.perf_counter() - t0) * 1000)
                observation.annotation_loaded = True

                _run_soak_pass(page, state, observation)
            except Exception as exc:
                observation.error = f"{type(exc).__name__}: {exc}"
            finally:
                page.goto("about:blank")
                context.close()
        finally:
            browser.close()
            with done_lock:
                done_counter[0] += 1


def _percentiles(values: list[int]) -> str:
    """Render p50/p90/max for a latency list."""
    if not values:
        return "n/a"
    ordered = sorted(values)
    p50 = ordered[len(ordered) // 2]
    p90 = ordered[min(len(ordered) - 1, (len(ordered) * 9) // 10)]
    return f"p50={p50}ms p90={p90}ms max={ordered[-1]}ms"


def _print_summary(
    observations: list[SoakObservation],
    diag_samples: list[dict],
) -> None:
    """Print per-action-type latency table and diagnostics trajectory."""
    loads = [o.load_elapsed_ms for o in observations if o.load_elapsed_ms >= 0]
    print(
        f"\n=== Full-CRUD soak probe (n={N_SOAK_SESSIONS}, "
        f"rate={ACTIONS_PER_MIN:.2f}/min = {SOAK_RATE_MULT}x observed, "
        f"{SOAK_MINUTES:.0f} min, arrival spread {SOAK_ARRIVAL_SPREAD_S:.0f}s) ==="
    )
    print(f"page load:      {_percentiles(loads)}")

    for action_name, _ in ACTION_WEIGHTS:
        ok = [
            a.elapsed_ms
            for o in observations
            for a in o.actions
            if a.action.startswith(action_name) and a.error is None
        ]
        print(f"{action_name:<17} n={len(ok):<5} {_percentiles(ok)}")

    degraded = [
        (o.email, a.action) for o in observations for a in o.actions if a.degraded
    ]
    failures = [
        (o.email, a.action, a.error)
        for o in observations
        for a in o.actions
        if a.error is not None and not a.degraded
    ]
    print(f"degraded (browser-side, nonfatal): {len(degraded)}")
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


async def _audit_respond_markers(observations: list[SoakObservation]) -> dict:
    """Classify every typed respond marker against persisted CRDT state.

    Reads each student's workspace back from the database and looks for
    the markers its ``respond_type`` actions recorded. Four buckets:

    - ``ok_landed``: the action succeeded and its marker is in the draft.
    - ``ok_lost``: the action succeeded and its marker is ABSENT -- typed
      text that never reached the database, the loss this audit exists
      to catch.
    - ``degraded_landed``: the action was degraded but the text landed
      anyway (the harness lost track, the user's work survived).
    - ``degraded_never_typed``: degraded with no marker -- the editor
      never opened, so nothing was ever typed. The expected shape of a
      Milkdown-init timeout.

    ``no_crdt_state`` holds markers that could not be classified because
    the workspace is missing or has never persisted CRDT state; counting
    them separately keeps a read failure from masquerading as loss.

    The substring check assumes every sentence was appended at the end of
    the draft (the ``Control+End`` in :func:`_do_respond_type`). A run
    recorded before that append landed splices sentences into each other,
    cutting markers in half, so its losses must be read as unclassifiable
    rather than as evidence of dropped text.
    """
    from promptgrimoire.crdt.annotation_doc import AnnotationDocument
    from promptgrimoire.db.workspaces import get_workspace

    counts = {
        "ok_landed": 0,
        "ok_lost": 0,
        "degraded_landed": 0,
        "degraded_never_typed": 0,
        "no_crdt_state": 0,
    }
    lost: list[dict[str, str]] = []

    for observation in observations:
        if not any(a.marker for a in observation.actions):
            continue
        workspace = await get_workspace(UUID(observation.workspace_id))
        crdt_state = workspace.crdt_state if workspace else None
        text = ""
        if crdt_state is not None:
            doc = AnnotationDocument("audit-tmp")
            doc.apply_update(crdt_state)
            text = doc.get_response_draft_markdown() or ""

        for action in observation.actions:
            marker = action.marker
            if marker is None:
                continue
            if crdt_state is None:
                counts["no_crdt_state"] += 1
                continue
            landed = marker in text
            # respond_type is in DEGRADED_NONFATAL_ACTIONS, so any error
            # on one of these actions is already flagged degraded.
            if action.error is None:
                counts["ok_landed" if landed else "ok_lost"] += 1
                if not landed:
                    lost.append(
                        {
                            "email": observation.email,
                            "action": action.action,
                            "marker": marker,
                        }
                    )
            else:
                counts["degraded_landed" if landed else "degraded_never_typed"] += 1

    return {"counts": counts, "ok_lost": lost}


def _run_respond_audit(observations: list[SoakObservation]) -> dict:
    """Wait out the persistence debounce, then audit the markers.

    The CRDT persistence manager debounces DB writes by 5 s
    (``crdt/persistence.py``, ``debounce_seconds``), so the last
    sentence a student typed may still be in flight when the browsers
    close; 15 s is 3x margin.

    An audit-infrastructure failure (DB unreachable, extraction crash)
    is recorded rather than raised -- the soak evidence must survive a
    bug in the audit.
    """
    time.sleep(15)
    try:
        return asyncio.run(_audit_respond_markers(observations))
    except Exception as exc:
        print(f"respond audit failed: {exc!r}")
        return {"audit_error": repr(exc)}


def _print_respond_audit(audit: dict) -> None:
    """Print the respond-marker audit verdict, losses one per line."""
    if "audit_error" in audit:
        print(f"respond audit: UNAVAILABLE ({audit['audit_error']})")
        return
    counts = audit["counts"]
    print("--- respond marker audit (post-run CRDT read) ---")
    print(
        f"  ok_landed={counts['ok_landed']} ok_lost={counts['ok_lost']} "
        f"degraded_landed={counts['degraded_landed']} "
        f"degraded_never_typed={counts['degraded_never_typed']} "
        f"no_crdt_state={counts['no_crdt_state']}"
    )
    for entry in audit["ok_lost"]:
        print(
            f"  !! TYPED TEXT LOST: {entry['email']} {entry['action']} "
            f"marker={entry['marker']}"
        )


def _soak_run_meta(started: datetime, ended: datetime) -> dict:
    """Describe this run's configuration for the diag JSON.

    Provenance used to rest on the output filename, so a run JSON could
    not say which snapshot flag or pool mode produced it.
    """
    return build_run_meta(
        probe="soak_full_crud",
        env=os.environ,
        started=started,
        ended=ended,
        knobs={
            "sessions": N_SOAK_SESSIONS,
            "rate_mult": SOAK_RATE_MULT,
            "actions_per_min": ACTIONS_PER_MIN,
            "soak_minutes": SOAK_MINUTES,
            "arrival_spread_s": SOAK_ARRIVAL_SPREAD_S,
            "action_timeout_ms": SOAK_ACTION_TIMEOUT_MS,
            "diag_sample_seconds": SOAK_DIAG_SAMPLE_SECONDS,
        },
        snapshot_enabled=get_settings().snapshot.enabled,
        branch=get_current_branch(),
    )


def _maybe_write_diag(
    observations: list[SoakObservation],
    diag_samples: list[dict],
    respond_audit: dict,
    run_meta: dict,
    server_page_load: dict,
    *,
    verdict: MeasuredVerdict,
) -> None:
    """Optionally persist one atomic verdict-bearing result envelope."""
    raw_path = os.environ.get("E2E_SOAK_DIAG_PATH")
    if not raw_path:
        return
    payload = {
        "run_meta": run_meta,
        "server_page_load": server_page_load,
        "sessions": N_SOAK_SESSIONS,
        "rate_mult": SOAK_RATE_MULT,
        "actions_per_min": ACTIONS_PER_MIN,
        "soak_minutes": SOAK_MINUTES,
        "arrival_spread_s": SOAK_ARRIVAL_SPREAD_S,
        "action_weights": dict(ACTION_WEIGHTS),
        "diag_samples": diag_samples,
        "respond_audit": respond_audit,
        "results": [asdict(o) for o in observations],
    }
    write_result_envelope(Path(raw_path), verdict=verdict, probe_payload=payload)


def _report_run(
    observations: list[SoakObservation],
    diag_samples: list[dict],
    run_started: datetime,
    run_ended: datetime,
    verdict: MeasuredVerdict,
) -> None:
    """Print every view of the run, then persist the full evidence.

    Browser-observed latency includes Playwright and the co-located
    browser's own CPU contention (failure-mode class G), so the server's
    own ``page_load_profile`` is reported beside it as the
    production-magnitude number.
    """
    _print_summary(observations, diag_samples)
    server_page_load = collect_server_page_load(
        window_start=run_started,
        window_end=run_ended,
    )
    print_server_page_load(server_page_load)

    respond_audit = _run_respond_audit(observations)
    # Gating the probe on ok_lost is deliberately deferred until a real
    # run confirms 15 s clears the persistence debounce; until then a
    # nonzero ok_lost is a finding to read, not a failure.
    _print_respond_audit(respond_audit)
    _maybe_write_diag(
        observations,
        diag_samples,
        respond_audit,
        _soak_run_meta(run_started, run_ended),
        server_page_load,
        verdict=verdict,
    )


def _wedge_failures(observations: list[SoakObservation]) -> list[str]:
    """Return browsers that failed the positive minimum-work boundary."""
    budget = ACTIONS_PER_MIN * SOAK_MINUTES
    min_actions = int(budget * MIN_ACTION_FRACTION)
    return [
        (
            f"{observation.email} completed only {attempted} actions "
            f"(wedge floor {min_actions}) -- browser wedged or pacing broke"
        )
        for observation in observations
        if (
            attempted := sum(
                1
                for action in observation.actions
                if action.error is None or action.degraded
            )
        )
        < min_actions
    ]


def _report_attainment_and_guard_wedge(
    observations: list[SoakObservation],
) -> None:
    """Report throughput attainment; assert only against wedged browsers.

    Attainment IS the measurement: how much each student got done
    versus the paced intent.  Time eaten by 30 s timeouts is genuinely
    lost student time, so it rightly drags attainment down -- report
    it, never mask it.  The assert is only a wedge-guard (a browser
    that silently stopped recording anything), so its floor sits far
    under any slow-but-alive student.
    """
    budget = ACTIONS_PER_MIN * SOAK_MINUTES
    per_student = [
        sum(1 for a in o.actions if a.error is None or a.degraded) for o in observations
    ]
    attainments = sorted(attempted / budget for attempted in per_student)
    print(
        f"throughput attainment vs paced budget ({budget:.0f}): "
        f"min={attainments[0]:.0%} "
        f"p50={attainments[len(attainments) // 2]:.0%} "
        f"max={attainments[-1]:.0%}"
    )
    min_actions = int(budget * MIN_ACTION_FRACTION)
    for o, attempted in zip(observations, per_student, strict=True):
        assert attempted >= min_actions, (
            f"{o.email} completed only {attempted} actions "
            f"(wedge floor {min_actions}) -- browser wedged or pacing broke"
        )


@pytest.fixture(scope="module")
def soak_activity_templates() -> Iterator[dict[str, str]]:
    """Bind BOTH fixtures as activity templates; restore afterwards."""
    bindings: dict[str, tuple[AssessmentFixture, str, str]] = {}
    for fixture in (NARAYAN_FIXTURE, SAVAGE_FIXTURE):
        ensure_fixture_workspace(fixture)
        activity_id, old_template_id = asyncio.run(
            create_template_activity(fixture, course_name=f"Soak Probe {fixture.name}")
        )
        bindings[fixture.name] = (fixture, activity_id, old_template_id)
    try:
        yield {name: binding[1] for name, binding in bindings.items()}
    finally:
        for fixture, activity_id, old_template_id in bindings.values():
            asyncio.run(restore_template_binding(fixture, activity_id, old_template_id))


class TestSoakFullCrudLoad:
    """Sustained full-CRUD load: calibrated worst-case students."""

    def test_soak_full_crud(
        self,
        app_server: str,
        soak_activity_templates: dict[str, str],
    ) -> None:
        """Find whether n crunched-soak students stay within bounds."""
        run_started = utc_now()
        fixtures = [NARAYAN_FIXTURE, SAVAGE_FIXTURE]
        observations: list[SoakObservation] = []
        for i in range(N_SOAK_SESSIONS):
            fixture = fixtures[i % len(fixtures)]
            email = f"soak-{uuid4().hex[:8]}@test.example.edu.au"
            workspace_id = asyncio.run(
                provision_clone_for_email(soak_activity_templates[fixture.name], email)
            )
            observations.append(
                SoakObservation(
                    email=email,
                    workspace_id=workspace_id,
                    fixture=fixture.name,
                    arrival_offset_s=(
                        (i / max(1, N_SOAK_SESSIONS - 1)) * SOAK_ARRIVAL_SPREAD_S
                    ),
                )
            )

        diag_samples: list[dict] = []
        t_origin = time.perf_counter()

        def sample_diag() -> None:
            diag = _fetch_json(f"{app_server}/api/test/diagnostics")
            diag["t_s"] = time.perf_counter() - t_origin
            diag_samples.append(diag)

        ready_barrier = threading.Barrier(N_SOAK_SESSIONS + 1, timeout=240)
        done_counter = [0]
        done_lock = threading.Lock()

        threads = [
            threading.Thread(
                target=_run_soak_session,
                args=(app_server, observation, fixtures[i % len(fixtures)], i),
                kwargs={
                    "ready_barrier": ready_barrier,
                    "done_counter": done_counter,
                    "done_lock": done_lock,
                },
                name=f"soak-session-{i}",
            )
            for i, observation in enumerate(observations)
        ]

        for thread in threads:
            thread.start()

        try:
            sample_diag()
            ready_barrier.wait(timeout=240)
            watch_deadline = (
                time.perf_counter() + SOAK_ARRIVAL_SPREAD_S + SOAK_MINUTES * 60 + 600
            )
            while time.perf_counter() < watch_deadline:
                with done_lock:
                    if done_counter[0] >= N_SOAK_SESSIONS:
                        break
                time.sleep(SOAK_DIAG_SAMPLE_SECONDS)
                sample_diag()
        finally:
            for thread in threads:
                thread.join(timeout=300)

        sample_diag()
        run_ended = utc_now()

        gate = _soak_gate(observations)
        _report_run(
            observations,
            diag_samples,
            run_started,
            run_ended,
            gate.verdict,
        )
        if gate.verdict.classification is PerfClassification.COLLAPSE:
            if should_fail_pytest_for_verdict(gate.verdict.classification):
                pytest.fail(
                    "\n".join(
                        [
                            f"Soak probe boundary hit at n={N_SOAK_SESSIONS}:",
                            *gate.load_errors,
                            *gate.action_failures,
                        ]
                    )
                )
            return
        if gate.action_failures:
            print(
                "isolated tail failures (non-systemic, "
                f"{len(gate.action_failures)}/{gate.total_actions} actions, "
                f"{len(gate.fatal_students)} student(s)):"
            )
            for line in gate.action_failures:
                print(f"  {line}")

        assert all(o.annotation_loaded for o in observations)
        _report_attainment_and_guard_wedge(observations)
