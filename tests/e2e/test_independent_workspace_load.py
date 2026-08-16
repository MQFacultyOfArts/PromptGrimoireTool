"""Perf probe for independent annotation loads on cloned PABAI workspaces.

This targets the user's clarified production shape: many users loading many
different workspaces concurrently, not many users sharing one workspace.

Strategy:
1. Rehydrate the scrubbed PABAI workspace once.
2. Temporarily bind it as an Activity template.
3. Pre-clone one workspace per synthetic user using the real
   ``clone_workspace_from_activity`` path so documents, tags, and CRDT state
   are remapped exactly like production clones.
4. Launch one Playwright instance per user, authenticate, then hit the user's
   own cloned workspace simultaneously.
5. Sample E2E diagnostics while all clients remain connected.

This gives us a discriminating boundary:
- If the system degrades here, the mechanism is in shared resources touched by
  independent page loads.
- If it only degrades in same-workspace tests, the mechanism is broadcast/
  presence fan-out instead.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
import urllib.request
from contextlib import suppress
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest

from promptgrimoire.config import get_settings
from tests.e2e.card_helpers import PABAI_WORKSPACE_ID, ensure_pabai_workspace

if TYPE_CHECKING:
    from collections.abc import Iterator

    from playwright.sync_api import Page, WebSocket

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.perf,
    pytest.mark.skipif(
        not get_settings().dev.test_database_url,
        reason="DEV__TEST_DATABASE_URL not configured",
    ),
]

N_INDEPENDENT_WORKSPACES = int(
    os.environ.get("E2E_INDEPENDENT_WORKSPACES_SESSIONS", "10")
)
AUTH_CLIENT_SETTLE_SECONDS = float(
    os.environ.get("E2E_AUTH_CLIENT_SETTLE_SECONDS", "0")
)


@dataclass
class IndependentWorkspaceObservation:
    """Outcome for one concurrent worker."""

    email: str = ""
    workspace_id: str = ""
    annotation_loaded: bool = False
    domcontentloaded_ms: int = -1
    websocket_ms: int = -1
    websocket_frames: int = 0
    websocket_bytes: int = 0
    largest_websocket_frame_bytes: int = 0
    last_websocket_frame_ms: int = -1
    document_mounted_ms: int = -1
    highlights_ready_ms: int = -1
    elapsed_ms: int = -1
    error: str | None = None


def _fetch_json(url: str) -> dict:
    """Fetch JSON from a localhost E2E helper endpoint."""
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read().decode())


def _wait_for_annotation_ready(page: Page) -> None:
    """Wait until the deferred annotation page has fully rendered."""
    page.wait_for_function(
        "() => {"
        "  if (typeof window.__loadComplete !== 'undefined') {"
        "    return window.__loadComplete === true;"
        "  }"
        "  return document.querySelector("
        "    '[data-testid=\"annotation-ready\"]'"
        "  ) !== null;"
        "}",
        timeout=120_000,
    )


def _measure_annotation_load(
    page: Page,
    url: str,
    observation: IndependentWorkspaceObservation,
) -> None:
    """Load an annotation page and record browser-visible milestones."""
    t0 = time.perf_counter()

    def record_websocket(websocket: WebSocket) -> None:
        if observation.websocket_ms < 0:
            observation.websocket_ms = round((time.perf_counter() - t0) * 1000)

        def record_frame(payload: str | bytes) -> None:
            if observation.annotation_loaded:
                return
            observation.websocket_frames += 1
            frame_bytes = (
                len(payload.encode()) if isinstance(payload, str) else len(payload)
            )
            observation.websocket_bytes += frame_bytes
            observation.largest_websocket_frame_bytes = max(
                observation.largest_websocket_frame_bytes,
                frame_bytes,
            )
            observation.last_websocket_frame_ms = round(
                (time.perf_counter() - t0) * 1000
            )

        websocket.on("framereceived", record_frame)

    page.on("websocket", record_websocket)
    page.goto(url, wait_until="domcontentloaded", timeout=120_000)
    observation.domcontentloaded_ms = round((time.perf_counter() - t0) * 1000)
    page.get_by_test_id("doc-container").wait_for(timeout=120_000)
    observation.document_mounted_ms = round((time.perf_counter() - t0) * 1000)
    page.wait_for_function(
        "() => window._highlightsReady === true",
        timeout=120_000,
    )
    observation.highlights_ready_ms = round((time.perf_counter() - t0) * 1000)
    _wait_for_annotation_ready(page)
    observation.elapsed_ms = round((time.perf_counter() - t0) * 1000)


async def _create_pabai_template_activity() -> tuple[str, str]:
    """Create an Activity whose template workspace is the PABAI fixture."""
    from promptgrimoire.db.activities import create_activity
    from promptgrimoire.db.courses import create_course
    from promptgrimoire.db.engine import get_session
    from promptgrimoire.db.models import Activity, Workspace
    from promptgrimoire.db.weeks import create_week, publish_week

    suffix = uuid4().hex[:8]
    course = await create_course(
        code=f"PB{suffix[:6].upper()}",
        name="PABAI Load Probe",
        semester="2026-S1",
    )
    week = await create_week(course_id=course.id, week_number=1, title="Week 1")
    await publish_week(week.id)
    activity = await create_activity(week_id=week.id, title=f"PABAI Load {suffix}")

    async with get_session() as session:
        db_activity = await session.get(Activity, activity.id)
        assert db_activity is not None
        old_template_id = str(db_activity.template_workspace_id)
        db_activity.template_workspace_id = UUID(PABAI_WORKSPACE_ID)
        session.add(db_activity)

        old_template = await session.get(Workspace, UUID(old_template_id))
        if old_template is not None:
            old_template.activity_id = None
            session.add(old_template)

        pabai = await session.get(Workspace, UUID(PABAI_WORKSPACE_ID))
        assert pabai is not None
        pabai.activity_id = activity.id
        session.add(pabai)

    return str(activity.id), old_template_id


async def _restore_pabai_template_binding(
    activity_id: str,
    old_template_id: str,
) -> None:
    """Restore PABAI to loose-workspace state after the probe."""
    from promptgrimoire.db.engine import get_session
    from promptgrimoire.db.models import Activity, Workspace

    async with get_session() as session:
        activity = await session.get(Activity, UUID(activity_id))
        if activity is not None:
            activity.template_workspace_id = UUID(old_template_id)
            session.add(activity)

        pabai = await session.get(Workspace, UUID(PABAI_WORKSPACE_ID))
        if pabai is not None:
            pabai.activity_id = None
            session.add(pabai)

        old_template = await session.get(Workspace, UUID(old_template_id))
        if old_template is not None:
            old_template.activity_id = UUID(activity_id)
            session.add(old_template)


async def _provision_clone_for_email(activity_id: str, email: str) -> str:
    """Create or reuse a user, then clone the PABAI template for them."""
    from promptgrimoire.db.users import find_or_create_user
    from promptgrimoire.db.workspaces import clone_workspace_from_activity

    user, _ = await find_or_create_user(email, display_name=email.split("@", 1)[0])
    clone, _ = await clone_workspace_from_activity(UUID(activity_id), user.id)
    return str(clone.id)


def _maybe_write_independent_load_diag(
    diag_before: dict,
    diag_during: dict,
    diag_after: dict,
    results: list[IndependentWorkspaceObservation],
) -> None:
    """Optionally persist diagnostics for manual analysis."""
    raw_path = os.environ.get("E2E_INDEPENDENT_WORKSPACES_DIAG_PATH")
    if not raw_path:
        return

    payload = {
        "auth_client_settle_seconds": AUTH_CLIENT_SETTLE_SECONDS,
        "before": diag_before,
        "during": diag_during,
        "after": diag_after,
        "results": [asdict(r) for r in results],
    }
    Path(raw_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _run_independent_workspace_session(
    app_server: str,
    observation: IndependentWorkspaceObservation,
    start_barrier: threading.Barrier,
    loaded_barrier: threading.Barrier,
    release_event: threading.Event,
) -> None:
    """Authenticate and load one cloned workspace in an isolated browser."""
    from playwright.sync_api import sync_playwright

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
            if AUTH_CLIENT_SETTLE_SECONDS:
                page.goto("about:blank")
                time.sleep(AUTH_CLIENT_SETTLE_SECONDS)

            try:
                start_barrier.wait(timeout=240)
                _measure_annotation_load(
                    page,
                    f"{app_server}/annotation?workspace_id={observation.workspace_id}",
                    observation,
                )
                observation.annotation_loaded = True
                loaded_barrier.wait(timeout=240)
                release_event.wait(timeout=120)
            except Exception as exc:
                observation.error = f"{type(exc).__name__}: {exc}"
                with suppress(threading.BrokenBarrierError):
                    loaded_barrier.abort()
            finally:
                page.goto("about:blank")
                context.close()
        finally:
            browser.close()


@pytest.fixture(scope="module")
def pabai_activity_template() -> Iterator[str]:
    """Create a temporary activity that uses PABAI as its template workspace."""
    ensure_pabai_workspace()
    activity_id, old_template_id = asyncio.run(_create_pabai_template_activity())
    try:
        yield activity_id
    finally:
        asyncio.run(_restore_pabai_template_binding(activity_id, old_template_id))


class TestIndependentWorkspaceLoad:
    """Stress many independent cloned workspaces concurrently."""

    def test_concurrent_independent_pabai_loads(
        self,
        app_server: str,
        pabai_activity_template: str,
    ) -> None:
        """Measure diagnostics for concurrent loads on distinct workspaces."""
        observations: list[IndependentWorkspaceObservation] = []
        for _ in range(N_INDEPENDENT_WORKSPACES):
            email = f"iw-{uuid4().hex[:8]}@test.example.edu.au"
            workspace_id = asyncio.run(
                _provision_clone_for_email(pabai_activity_template, email)
            )
            observations.append(
                IndependentWorkspaceObservation(
                    email=email,
                    workspace_id=workspace_id,
                )
            )

        diag_before = _fetch_json(f"{app_server}/api/test/diagnostics")
        start_barrier = threading.Barrier(N_INDEPENDENT_WORKSPACES + 1, timeout=240)
        loaded_barrier = threading.Barrier(N_INDEPENDENT_WORKSPACES + 1, timeout=240)
        release_event = threading.Event()

        threads = [
            threading.Thread(
                target=_run_independent_workspace_session,
                args=(
                    app_server,
                    observation,
                    start_barrier,
                    loaded_barrier,
                    release_event,
                ),
                name=f"independent-workspace-{i}",
            )
            for i, observation in enumerate(observations)
        ]

        for thread in threads:
            thread.start()

        try:
            start_barrier.wait(timeout=240)
            loaded_barrier.wait(timeout=240)
            diag_during = _fetch_json(f"{app_server}/api/test/diagnostics")
        except threading.BrokenBarrierError:
            diag_during = _fetch_json(f"{app_server}/api/test/diagnostics")
        finally:
            release_event.set()
            for thread in threads:
                thread.join(timeout=300)

        diag_after = _fetch_json(f"{app_server}/api/test/diagnostics")
        _maybe_write_independent_load_diag(
            diag_before,
            diag_during,
            diag_after,
            observations,
        )

        errors = [obs.error for obs in observations if obs.error]
        if errors:
            pytest.fail("\n".join(["Independent-workspace worker failed:", *errors]))

        assert all(obs.annotation_loaded for obs in observations)

        assert diag_during["presence_workspaces"] >= N_INDEPENDENT_WORKSPACES
        assert diag_during["presence_total_clients"] >= N_INDEPENDENT_WORKSPACES
