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
from uuid import uuid4

import pytest

from promptgrimoire.config import get_settings
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

if TYPE_CHECKING:
    from collections.abc import Iterator

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
SOAK_RETRY_TIMEOUT_MS = int(os.environ.get("E2E_SOAK_RETRY_TIMEOUT_MS", "5000"))
SOAK_DIAG_SAMPLE_SECONDS = float(os.environ.get("E2E_SOAK_DIAG_SAMPLE_SECONDS", "10"))

ACTIONS_PER_MIN = OBSERVED_ACTIONS_PER_MIN * SOAK_RATE_MULT
MAX_CONSECUTIVE_ACTION_FAILURES = 3
HIGHLIGHT_ATTEMPTS = 3
SEED_HIGHLIGHTS = 3
# A student must complete at least half its paced budget or the probe
# is not measuring what it claims.
MIN_ACTION_FRACTION = 0.5

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


@dataclass
class ActionResult:
    """One soak action."""

    action: str = ""
    elapsed_ms: int = -1
    retries: int = 0
    error: str | None = None


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


def _do_highlight_create(page: Page, state: StudentState, result: ActionResult) -> None:
    """Create one highlight, re-selecting on silent no-op (as cram)."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    from tests.e2e.highlight_tools import (
        create_highlight_with_tag,
        scroll_to_char,
    )

    needles = state.plan_needles(HIGHLIGHT_ATTEMPTS * 4)
    for attempt in range(HIGHLIGHT_ATTEMPTS):
        # Re-read the actual DOM count so a late-landing previous retry
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
        last = attempt == HIGHLIGHT_ATTEMPTS - 1
        try:
            _wait_card_count(
                page,
                before + 1,
                timeout=SOAK_ACTION_TIMEOUT_MS if last else SOAK_RETRY_TIMEOUT_MS,
            )
        except PlaywrightTimeoutError:
            result.retries += 1
            if last:
                raise
            continue
        state.highlight_count = before + 1
        return


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
    """Drag a card between tag columns on the Organise tab (retag)."""
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

    # Cards drag directly onto the target column's sortable container
    # (the pattern test_tag_sync.py uses); there is no drag handle.
    card = columns.nth(source_idx).locator("[data-testid='organise-card']").first
    card.drag_to(target_col.locator(".nicegui-sortable").first)
    try:
        # Success = the source column lost the card. Where it landed is
        # secondary: any completed drop is a real retag round trip.
        page.wait_for_function(
            "([colIdx, n]) => {"
            "  const cols = document.querySelectorAll('[data-testid=\"tag-column\"]');"
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
            f"drag produced no column change: source_idx={source_idx} "
            f"(had {source_before}), target_idx={target_idx}, "
            f"column counts now {counts}"
        )
        raise RuntimeError(msg) from None
    finally:
        _back_to_source(page)


def _do_respond_type(page: Page, state: StudentState, _result: ActionResult) -> None:
    """Type a sentence into the Respond (Milkdown) editor."""
    page.get_by_test_id("tab-respond").click()
    editor = page.locator("[data-testid='milkdown-editor-container']")
    editor.wait_for(state="visible", timeout=SOAK_ACTION_TIMEOUT_MS)
    editor.locator("[contenteditable]").first.click()
    page.keyboard.type(
        f"Soak analysis point {uuid4().hex[:6]}: the reasoning turns on "
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

    total_retries = sum(a.retries for o in observations for a in o.actions)
    failures = [
        (o.email, a.action, a.error)
        for o in observations
        for a in o.actions
        if a.error is not None
    ]
    print(f"no-op retries:  {total_retries}")
    print(f"action failures: {len(failures)}")
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


def _maybe_write_diag(
    observations: list[SoakObservation],
    diag_samples: list[dict],
) -> None:
    """Optionally persist full evidence for manual analysis."""
    raw_path = os.environ.get("E2E_SOAK_DIAG_PATH")
    if not raw_path:
        return
    payload = {
        "sessions": N_SOAK_SESSIONS,
        "rate_mult": SOAK_RATE_MULT,
        "actions_per_min": ACTIONS_PER_MIN,
        "soak_minutes": SOAK_MINUTES,
        "arrival_spread_s": SOAK_ARRIVAL_SPREAD_S,
        "action_weights": dict(ACTION_WEIGHTS),
        "diag_samples": diag_samples,
        "results": [asdict(o) for o in observations],
    }
    Path(raw_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


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
        _print_summary(observations, diag_samples)
        _maybe_write_diag(observations, diag_samples)

        load_errors = [o.error for o in observations if o.error]
        action_failures = [
            f"{o.email} {a.action}: {a.error}"
            for o in observations
            for a in o.actions
            if a.error is not None
        ]
        if load_errors or action_failures:
            pytest.fail(
                "\n".join(
                    [
                        f"Soak probe boundary hit at n={N_SOAK_SESSIONS}:",
                        *load_errors,
                        *action_failures,
                    ]
                )
            )

        assert all(o.annotation_loaded for o in observations)
        # The probe must not pass by idling: each student must complete
        # at least half of its paced budget.
        min_actions = int(ACTIONS_PER_MIN * SOAK_MINUTES * MIN_ACTION_FRACTION)
        for o in observations:
            ok_actions = sum(1 for a in o.actions if a.error is None)
            assert ok_actions >= min_actions, (
                f"{o.email} completed only {ok_actions} actions "
                f"(minimum {min_actions}) -- pacing or eligibility broke"
            )
