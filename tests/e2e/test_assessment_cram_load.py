"""Perf probe: concurrent students doing the case-brief assessment.

Models the 11pm-night-before scenario for the Practice-Based Task
(Narayan v R): N students each load their own clone of the assessment
template, then work through a case-brief annotation pass concurrently --
highlights tagged against the ten case-brief tags (Citation, Court,
Procedural History, Facts, Issues, Reasons, Ratio, Obiter, Decision,
Order), with comments on a subset.

Strategy (extends test_independent_workspace_load.py with interactivity):
1. Rehydrate the Narayan assessment template once.
2. Temporarily bind it as an Activity template.
3. Pre-clone one workspace per synthetic student via the real
   ``clone_workspace_from_activity`` path.
4. Launch one Playwright instance per student, authenticate, load the
   clone, then run the annotation pass with think-time jitter.
5. Sample ``/api/test/diagnostics`` every few seconds during the pass.

Ramp externally in steps of 25:

    E2E_CRAM_SESSIONS=25 uv run grimoire e2e perf \
        tests/e2e/test_assessment_cram_load.py

The probe fails when any student cannot load, or any annotation action
times out or errors -- that failure, with the printed latency table and
diagnostics samples, is the boundary evidence. Comment posting uses the
shared ``add_comment_to_highlight`` helper, whose 10-second epoch wait
doubles as the acceptable-latency bound for a comment round trip.
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

from promptgrimoire.config import get_settings

if TYPE_CHECKING:
    from collections.abc import Iterator

    from playwright.sync_api import Page

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.perf,
    # Overrides the global 30s cap: a 100-session wave spends minutes in
    # clone provisioning, barriers, and the annotation pass.
    pytest.mark.timeout(1800),
    pytest.mark.skipif(
        not get_settings().dev.test_database_url,
        reason="DEV__TEST_DATABASE_URL not configured",
    ),
]

NARAYAN_WORKSPACE_ID = "c7cf540f-53df-407e-b043-cc6f6e30cf5b"
NARAYAN_FIXTURE_JSON = (
    Path(__file__).parent.parent / "fixtures" / "narayan_workspace.json"
)
CASE_BRIEF_TAG_COUNT = 10

N_CRAM_SESSIONS = int(os.environ.get("E2E_CRAM_SESSIONS", "25"))
N_CRAM_HIGHLIGHTS = int(os.environ.get("E2E_CRAM_HIGHLIGHTS", "10"))
N_CRAM_COMMENTS = int(os.environ.get("E2E_CRAM_COMMENTS", "3"))
CRAM_THINK_MS = int(os.environ.get("E2E_CRAM_THINK_MS", "2000"))
CRAM_ACTION_TIMEOUT_MS = int(os.environ.get("E2E_CRAM_ACTION_TIMEOUT_MS", "30000"))
CRAM_RETRY_TIMEOUT_MS = int(os.environ.get("E2E_CRAM_RETRY_TIMEOUT_MS", "5000"))
CRAM_DIAG_SAMPLE_SECONDS = float(os.environ.get("E2E_CRAM_DIAG_SAMPLE_SECONDS", "5"))
MAX_CONSECUTIVE_ACTION_FAILURES = 3
# Re-select-and-click attempts per highlight, mirroring a student whose
# tag click silently no-ops (selection_made/tag-click socket race).
HIGHLIGHT_ATTEMPTS = 3


@dataclass
class ActionResult:
    """One annotation action (highlight creation or comment post)."""

    action: str = ""
    elapsed_ms: int = -1
    retries: int = 0
    error: str | None = None


@dataclass
class CramObservation:
    """Outcome for one synthetic student."""

    email: str = ""
    workspace_id: str = ""
    annotation_loaded: bool = False
    load_elapsed_ms: int = -1
    pass_elapsed_ms: int = -1
    actions: list[ActionResult] = field(default_factory=list)
    error: str | None = None


def _fetch_json(url: str) -> dict:
    """Fetch JSON from a localhost E2E helper endpoint."""
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read().decode())


def _ensure_narayan_workspace() -> str:
    """Rehydrate the Narayan assessment template into the test DB.

    The rehydrate script deletes then re-inserts, so calling this
    unconditionally is safe. Returns the workspace ID.
    """
    if not NARAYAN_FIXTURE_JSON.exists():
        pytest.skip(
            f"Workspace JSON not found at {NARAYAN_FIXTURE_JSON}. "
            "Extract from prod with scripts/extract_workspace.py first."
        )

    from scripts.rehydrate_workspace import rehydrate

    db_url = get_settings().database.url
    if not db_url:
        msg = "DATABASE__URL not configured"
        raise RuntimeError(msg)
    result = rehydrate(NARAYAN_FIXTURE_JSON, db_url)
    assert result["workspace_id"] == NARAYAN_WORKSPACE_ID
    return NARAYAN_WORKSPACE_ID


async def _create_narayan_template_activity() -> tuple[str, str]:
    """Create an Activity whose template workspace is the Narayan fixture."""
    from promptgrimoire.db.activities import create_activity
    from promptgrimoire.db.courses import create_course
    from promptgrimoire.db.engine import get_session
    from promptgrimoire.db.models import Activity, Workspace
    from promptgrimoire.db.weeks import create_week, publish_week

    suffix = uuid4().hex[:8]
    course = await create_course(
        code=f"CR{suffix[:6].upper()}",
        name="Assessment Cram Probe",
        semester="2026-S2",
    )
    week = await create_week(course_id=course.id, week_number=5, title="Week 5")
    await publish_week(week.id)
    activity = await create_activity(week_id=week.id, title=f"Cram Load {suffix}")

    async with get_session() as session:
        db_activity = await session.get(Activity, activity.id)
        assert db_activity is not None
        old_template_id = str(db_activity.template_workspace_id)
        db_activity.template_workspace_id = UUID(NARAYAN_WORKSPACE_ID)
        session.add(db_activity)

        old_template = await session.get(Workspace, UUID(old_template_id))
        if old_template is not None:
            old_template.activity_id = None
            session.add(old_template)

        narayan = await session.get(Workspace, UUID(NARAYAN_WORKSPACE_ID))
        assert narayan is not None
        narayan.activity_id = activity.id
        session.add(narayan)

    return str(activity.id), old_template_id


async def _restore_narayan_template_binding(
    activity_id: str,
    old_template_id: str,
) -> None:
    """Restore the Narayan fixture to loose-workspace state after the probe."""
    from promptgrimoire.db.engine import get_session
    from promptgrimoire.db.models import Activity, Workspace

    async with get_session() as session:
        activity = await session.get(Activity, UUID(activity_id))
        if activity is not None:
            activity.template_workspace_id = UUID(old_template_id)
            session.add(activity)

        narayan = await session.get(Workspace, UUID(NARAYAN_WORKSPACE_ID))
        if narayan is not None:
            narayan.activity_id = None
            session.add(narayan)

        old_template = await session.get(Workspace, UUID(old_template_id))
        if old_template is not None:
            old_template.activity_id = UUID(activity_id)
            session.add(old_template)


async def _provision_clone_for_email(activity_id: str, email: str) -> str:
    """Create or reuse a user, then clone the assessment template for them."""
    from promptgrimoire.db.users import find_or_create_user
    from promptgrimoire.db.workspaces import clone_workspace_from_activity

    user, _ = await find_or_create_user(email, display_name=email.split("@", 1)[0])
    clone, _ = await clone_workspace_from_activity(UUID(activity_id), user.id)
    return str(clone.id)


def _fixture_document_words() -> list[str]:
    """Extract the assessment document's words from the fixture JSON.

    The browser's text walker collapses whitespace, so a needle built
    from single-space-joined words matches what ``find_text_range``
    searches. Reading the fixture (rather than the browser) keeps the
    probe file free of page.evaluate.
    """
    from selectolax.lexbor import LexborHTMLParser

    data = json.loads(NARAYAN_FIXTURE_JSON.read_text(encoding="utf-8"))
    html = data["documents"][0]["content"]
    words = LexborHTMLParser(html).text(separator=" ").split()
    min_words_needed = 200
    if len(words) < min_words_needed:
        msg = f"fixture document too short ({len(words)} words)"
        raise RuntimeError(msg)
    return words


def _plan_highlight_needles(
    words: list[str],
    rng: random.Random,
    count: int,
) -> list[str]:
    """Pick word-span needles spread through the document text.

    Each needle is resolved to walker char offsets in-browser via
    ``find_text_range``; a needle the browser cannot find is skipped
    there and replaced by the next candidate.
    """
    needles: list[str] = []
    for _ in range(count):
        span = rng.randint(8, 25)
        first = rng.randint(1, len(words) - span - 1)
        needles.append(" ".join(words[first : first + span]))
    return needles


def _resolve_next_range(
    page: Page,
    needles: list[str],
) -> tuple[int, int]:
    """Resolve the next findable needle to walker char offsets.

    Consumes needles from the front, discarding unfindable ones (walker
    whitespace collapsing makes a few percent of fixture-derived needles
    unmatchable). Raises when the pool is exhausted.
    """
    from tests.e2e.highlight_tools import find_text_range

    while needles:
        with suppress(ValueError):
            return find_text_range(page, needles.pop(0))
    msg = "needle pool exhausted (retries and unfindable needles)"
    raise RuntimeError(msg)


def _create_highlight_with_retry(
    page: Page,
    needles: list[str],
    highlight_index: int,
    highlights_created: int,
    result: ActionResult,
) -> None:
    """Create one highlight, re-selecting on silent no-op.

    The selection_made/tag-click socket race (highlights.py "No selection"
    early return) makes a tag click a silent no-op under event-loop lag. A
    real student re-selects and clicks again; do the same and count it —
    the retry rate is itself a lag signal.
    """
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    from tests.e2e.highlight_tools import (
        create_highlight_with_tag,
        scroll_to_char,
        wait_for_css_highlight_count,
    )

    for attempt in range(HIGHLIGHT_ATTEMPTS):
        start, end = _resolve_next_range(page, needles)
        scroll_to_char(page, start)
        create_highlight_with_tag(
            page, start, end, highlight_index % CASE_BRIEF_TAG_COUNT
        )
        # Short wait per attempt (successes land in well under a second);
        # full timeout on the last attempt so a genuinely slow round trip
        # at high n is measured rather than misclassified as a no-op.
        last = attempt == HIGHLIGHT_ATTEMPTS - 1
        try:
            wait_for_css_highlight_count(
                page,
                highlights_created + 1,
                timeout=CRAM_ACTION_TIMEOUT_MS if last else CRAM_RETRY_TIMEOUT_MS,
            )
            return
        except PlaywrightTimeoutError:
            result.retries += 1
            if last:
                raise


def _think(rng: random.Random) -> None:
    """Sleep a jittered think-time between annotation actions."""
    if CRAM_THINK_MS <= 0:
        return
    time.sleep(rng.uniform(0.5, 1.5) * CRAM_THINK_MS / 1000)


def _run_annotation_pass(
    page: Page,
    rng: random.Random,
    observation: CramObservation,
) -> None:
    """Perform the case-brief annotation pass, recording per-action timing.

    Each student annotates only their own clone, so after the k-th
    successful highlight the CSS highlight count is deterministically k;
    ``wait_for_css_highlight_count`` is therefore the round-trip signal
    (server save + CRDT broadcast + client CSS update).

    Consecutive failures beyond MAX_CONSECUTIVE_ACTION_FAILURES abort the
    pass (the remaining actions would only repeat the same evidence).
    """
    from tests.e2e.card_helpers import add_comment_to_highlight

    pass_start = time.perf_counter()
    words = _fixture_document_words()
    # Extra candidates cover needles the walker's whitespace collapsing
    # renders unfindable (e.g. words joined across a <br>).
    # 4x pool: retries and unfindable needles both consume candidates.
    needles = _plan_highlight_needles(words, rng, N_CRAM_HIGHLIGHTS * 4)

    consecutive_failures = 0
    highlights_created = 0

    for i in range(N_CRAM_HIGHLIGHTS):
        result = ActionResult(action=f"highlight-{i}")
        t0 = time.perf_counter()
        try:
            _create_highlight_with_retry(page, needles, i, highlights_created, result)
            # Wait for the sidebar rebuild too: starting the next selection
            # before the k-th rebuild lands lets the rebuild destroy the
            # in-flight selection (documented rebuild/interaction race).
            # Own workspace, single writer: after k highlights the epoch is
            # deterministically >= k+1 (1 for mount, +1 per items change).
            page.wait_for_function(
                "(k) => (window.__annotationCardsEpoch || 0) >= k",
                arg=highlights_created + 2,
                timeout=CRAM_ACTION_TIMEOUT_MS,
            )
            highlights_created += 1
            consecutive_failures = 0
        except Exception as exc:
            result.error = f"{type(exc).__name__}: {exc}"
            consecutive_failures += 1
        finally:
            result.elapsed_ms = round((time.perf_counter() - t0) * 1000)
            observation.actions.append(result)

        if consecutive_failures >= MAX_CONSECUTIVE_ACTION_FAILURES:
            break
        _think(rng)

    n_comments = min(N_CRAM_COMMENTS, highlights_created)
    for j in range(n_comments):
        if consecutive_failures >= MAX_CONSECUTIVE_ACTION_FAILURES:
            break
        result = ActionResult(action=f"comment-{j}")
        t0 = time.perf_counter()
        try:
            add_comment_to_highlight(
                page,
                f"Cram note {j + 1}: element noted ({uuid4().hex[:6]})",
                card_index=j,
            )
            consecutive_failures = 0
        except Exception as exc:
            result.error = f"{type(exc).__name__}: {exc}"
            consecutive_failures += 1
        finally:
            result.elapsed_ms = round((time.perf_counter() - t0) * 1000)
            observation.actions.append(result)
        _think(rng)

    observation.pass_elapsed_ms = round((time.perf_counter() - pass_start) * 1000)


def _run_cram_session(
    app_server: str,
    observation: CramObservation,
    seed: int,
    start_barrier: threading.Barrier,
    loaded_barrier: threading.Barrier,
    done_counter: list[int],
    done_lock: threading.Lock,
    release_event: threading.Event,
) -> None:
    """Authenticate, load one clone, then run the annotation pass."""
    from playwright.sync_api import sync_playwright

    from promptgrimoire.docs.helpers import wait_for_annotation_ready

    # Deterministic per-student jitter for load shaping, not cryptography.
    rng = random.Random(seed)  # noqa: S311
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
                start_barrier.wait(timeout=240)
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
                loaded_barrier.wait(timeout=240)

                _run_annotation_pass(page, rng, observation)
            except Exception as exc:
                observation.error = f"{type(exc).__name__}: {exc}"
                with suppress(threading.BrokenBarrierError):
                    loaded_barrier.abort()
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


def _print_summary(
    observations: list[CramObservation],
    diag_samples: list[dict],
) -> None:
    """Print the latency table and diagnostics trajectory."""
    loads = [o.load_elapsed_ms for o in observations if o.load_elapsed_ms >= 0]
    highlight_ok = [
        a.elapsed_ms
        for o in observations
        for a in o.actions
        if a.action.startswith("highlight") and a.error is None
    ]
    comment_ok = [
        a.elapsed_ms
        for o in observations
        for a in o.actions
        if a.action.startswith("comment") and a.error is None
    ]
    failures = [
        (o.email, a.action, a.error)
        for o in observations
        for a in o.actions
        if a.error is not None
    ]

    total_retries = sum(a.retries for o in observations for a in o.actions)

    print(f"\n=== Assessment cram probe (n={N_CRAM_SESSIONS}) ===")
    print(f"page load:      {_percentiles(loads)}")
    print(f"highlight ok:   {len(highlight_ok)}  {_percentiles(highlight_ok)}")
    print(f"comment ok:     {len(comment_ok)}  {_percentiles(comment_ok)}")
    print(f"no-op retries:  {total_retries}  (selection/tag-click race rate)")
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
    observations: list[CramObservation],
    diag_samples: list[dict],
) -> None:
    """Optionally persist full evidence for manual analysis."""
    raw_path = os.environ.get("E2E_CRAM_DIAG_PATH")
    if not raw_path:
        return
    payload = {
        "sessions": N_CRAM_SESSIONS,
        "highlights_per_student": N_CRAM_HIGHLIGHTS,
        "comments_per_student": N_CRAM_COMMENTS,
        "think_ms": CRAM_THINK_MS,
        "diag_samples": diag_samples,
        "results": [asdict(o) for o in observations],
    }
    Path(raw_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


@pytest.fixture(scope="module")
def narayan_activity_template() -> Iterator[str]:
    """Create a temporary activity using the Narayan fixture as template."""
    _ensure_narayan_workspace()
    activity_id, old_template_id = asyncio.run(_create_narayan_template_activity())
    try:
        yield activity_id
    finally:
        asyncio.run(_restore_narayan_template_binding(activity_id, old_template_id))


class TestAssessmentCramLoad:
    """Concurrent case-brief annotation passes on independent clones."""

    def test_concurrent_assessment_cram(
        self,
        app_server: str,
        narayan_activity_template: str,
    ) -> None:
        """Find whether n concurrent working students stay within bounds."""
        observations: list[CramObservation] = []
        for _ in range(N_CRAM_SESSIONS):
            email = f"cram-{uuid4().hex[:8]}@test.example.edu.au"
            workspace_id = asyncio.run(
                _provision_clone_for_email(narayan_activity_template, email)
            )
            observations.append(CramObservation(email=email, workspace_id=workspace_id))

        diag_samples: list[dict] = []
        t_origin = time.perf_counter()

        def sample_diag() -> None:
            diag = _fetch_json(f"{app_server}/api/test/diagnostics")
            diag["t_s"] = time.perf_counter() - t_origin
            diag_samples.append(diag)

        start_barrier = threading.Barrier(N_CRAM_SESSIONS + 1, timeout=240)
        loaded_barrier = threading.Barrier(N_CRAM_SESSIONS + 1, timeout=240)
        done_counter = [0]
        done_lock = threading.Lock()
        release_event = threading.Event()

        threads = [
            threading.Thread(
                target=_run_cram_session,
                args=(
                    app_server,
                    observation,
                    i,
                    start_barrier,
                    loaded_barrier,
                    done_counter,
                    done_lock,
                    release_event,
                ),
                name=f"cram-session-{i}",
            )
            for i, observation in enumerate(observations)
        ]

        for thread in threads:
            thread.start()

        try:
            sample_diag()
            start_barrier.wait(timeout=240)
            with suppress(threading.BrokenBarrierError):
                loaded_barrier.wait(timeout=240)
            sample_diag()

            interaction_deadline = time.perf_counter() + 600
            while time.perf_counter() < interaction_deadline:
                with done_lock:
                    if done_counter[0] >= N_CRAM_SESSIONS:
                        break
                time.sleep(CRAM_DIAG_SAMPLE_SECONDS)
                sample_diag()
        finally:
            release_event.set()
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
                        f"Cram probe boundary hit at n={N_CRAM_SESSIONS}:",
                        *load_errors,
                        *action_failures,
                    ]
                )
            )

        assert all(o.annotation_loaded for o in observations)
        expected_actions = N_CRAM_HIGHLIGHTS + N_CRAM_COMMENTS
        total_ok = sum(1 for o in observations for a in o.actions if a.error is None)
        assert total_ok == N_CRAM_SESSIONS * expected_actions
