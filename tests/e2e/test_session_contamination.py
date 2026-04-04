"""Session contamination reproducer (#438).

Concurrent PABAI page loads must not cross-contaminate.

Issue: #438 (cross-user session contamination)

Under event loop saturation, NiceGUI's page handler runs in an asyncio Task
(background_tasks.create at page.py:172) that may inherit a stale
request_contextvar from another concurrent request.  app.storage.user then
resolves to the wrong user's storage.

Strategy:
  1. Rehydrate the PABAI workspace (190 highlights, 5,020 text nodes, ~150KB)
  2. Spin up N independent Playwright instances (separate processes/event loops)
  3. Authenticate each with a distinct mock user, grant ACL on the shared workspace
  4. All N navigate to the annotation page simultaneously via a barrier
  5. After full page render (text walker ready), navigate to /test/session-identity
  6. Check the rendered email matches the authenticated user
  7. Any mismatch is contamination

The PABAI workspace creates realistic event loop contention: DB queries, CRDT
deserialisation, presence tracking, highlight rendering, and broadcast setup.
This reproduces production conditions far better than a toy endpoint.

Each thread owns its own Playwright instance — no shared event loop.

Run with:
  uv run grimoire e2e run -k "test_session_contamination" --serial
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from uuid import uuid4

import pytest

from promptgrimoire.config import get_settings
from tests.e2e.card_helpers import ensure_pabai_workspace

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.perf,
    pytest.mark.skipif(
        not get_settings().dev.test_database_url,
        reason="DEV__TEST_DATABASE_URL not configured",
    ),
]

# Concurrency parameters.  Production incident had ~189 users.
# 10 is enough to create meaningful event loop contention with
# the PABAI fixture while keeping resource usage manageable.
N_SESSIONS = 10
N_ROUNDS = 3


def _test_db_conninfo() -> str:
    """Build psycopg conninfo from settings (DATABASE__URL or DEV__TEST_DATABASE_URL).

    The E2E parallel runner sets DATABASE__URL per-worker; pydantic-settings
    picks it up automatically.
    """
    from psycopg.conninfo import make_conninfo

    settings = get_settings()
    url = settings.database.url or settings.dev.test_database_url
    if not url:
        msg = "Neither DATABASE__URL nor DEV__TEST_DATABASE_URL configured"
        raise RuntimeError(msg)
    # SQLAlchemy-style URLs use +asyncpg; psycopg needs plain postgresql://
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    return make_conninfo(url)


def _grant_acl(conninfo: str, email: str, workspace_id: str) -> None:
    """Grant owner ACL on workspace to user (by email) via direct SQL."""
    import psycopg

    with psycopg.connect(conninfo) as conn:
        cur = conn.cursor()
        cur.execute(
            'SELECT id FROM "user" WHERE email = %s',
            (email,),
        )
        row = cur.fetchone()
        if row is None:
            msg = f"User not found: {email}"
            raise RuntimeError(msg)
        cur.execute(
            "INSERT INTO acl_entry"
            " (id, workspace_id, user_id, permission, created_at)"
            " VALUES (gen_random_uuid(), %s::uuid, %s, 'owner', now())"
            " ON CONFLICT DO NOTHING",
            (workspace_id, row[0]),
        )
        conn.commit()


@dataclass
class RoundObservation:
    """What one session saw in a single round."""

    email_before: str | None = None
    email_after: str | None = None
    error: str | None = None


@dataclass
class WorkerResult:
    """Collects results from a single worker thread."""

    expected_email: str = ""
    observations: list[RoundObservation] = field(default_factory=list)


def _run_session(
    app_server: str,
    conninfo: str,
    workspace_id: str,
    barrier: threading.Barrier,
    result: WorkerResult,
    n_rounds: int,
) -> None:
    """Run a complete session in its own Playwright instance.

    Each thread: Playwright -> Chromium -> authenticate -> grant ACL ->
    barrier wait -> load annotation page (full PABAI render) ->
    navigate to /test/session-identity -> capture email.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            context = browser.new_context()
            page = context.new_page()

            # Authenticate
            unique_id = uuid4().hex[:8]
            email = f"sc-{unique_id}@test.example.edu.au"
            result.expected_email = email
            page.goto(
                f"{app_server}/auth/callback?token=mock-token-{email}",
            )
            page.wait_for_url(
                lambda url: "/auth/callback" not in url,
                timeout=15000,
            )

            # Grant ACL on the shared PABAI workspace
            _grant_acl(conninfo, email, workspace_id)

            annotation_url = f"{app_server}/annotation?workspace_id={workspace_id}"
            identity_url = f"{app_server}/test/session-identity"

            for _ in range(n_rounds):
                obs = RoundObservation()

                # All threads fire simultaneously.
                barrier.wait(timeout=60)

                try:
                    # Load the PABAI annotation page.  This is the
                    # heavy path: DB, CRDT, presence, highlights.
                    # We don't wait for full render — the server-side
                    # work happens during the HTTP response + background
                    # task.  domcontentloaded is enough to know the
                    # server started processing.
                    page.goto(
                        annotation_url,
                        wait_until="domcontentloaded",
                        timeout=60000,
                    )
                    # Wait for the annotation page to fully render before
                    # checking identity — the interleaving window is during
                    # the heavy annotation load.
                    page.wait_for_load_state("networkidle")  # noqa: PG001

                    # NOW check identity via the lightweight page.
                    # If contextvar was contaminated during the heavy
                    # annotation load, the identity page shows it.
                    page.goto(identity_url)
                    loc = page.get_by_test_id("session-email")
                    loc.wait_for(state="attached", timeout=15000)
                    obs.email_before = loc.inner_text()

                    loc_after = page.get_by_test_id(
                        "session-email-after",
                    )
                    loc_after.wait_for(
                        state="attached",
                        timeout=5000,
                    )
                    obs.email_after = loc_after.inner_text()
                except Exception as exc:
                    obs.error = f"{type(exc).__name__}: {exc}"

                result.observations.append(obs)

            page.goto("about:blank")
            context.close()
        finally:
            browser.close()


class TestSessionContamination:
    """Concurrent PABAI page loads must not cross-contaminate sessions."""

    def test_concurrent_pabai_identity(
        self,
        app_server: str,
    ) -> None:
        """Fire N concurrent annotation page loads with full PABAI content.

        Each thread owns its own Playwright instance.  A barrier
        synchronises navigation so all N hit the server at the same
        moment, loading the 150KB PABAI workspace with 190 highlights.
        After full render, each checks its session identity.
        """
        conninfo = _test_db_conninfo()
        workspace_id = ensure_pabai_workspace()

        barrier = threading.Barrier(N_SESSIONS, timeout=120)
        results: list[WorkerResult] = [WorkerResult() for _ in range(N_SESSIONS)]

        threads = [
            threading.Thread(
                target=_run_session,
                args=(
                    app_server,
                    conninfo,
                    workspace_id,
                    barrier,
                    results[i],
                    N_ROUNDS,
                ),
                name=f"session-contamination-{i}",
            )
            for i in range(N_SESSIONS)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=300)

        # ---- Verification ----
        mismatches: list[dict[str, str]] = []

        for i, res in enumerate(results):
            for round_idx in range(N_ROUNDS):
                if round_idx >= len(res.observations):
                    mismatches.append(
                        {
                            "round": str(round_idx),
                            "session": str(i),
                            "expected": res.expected_email,
                            "observed": "THREAD_INCOMPLETE",
                        }
                    )
                    continue

                obs = res.observations[round_idx]

                if obs.error:
                    mismatches.append(
                        {
                            "round": str(round_idx),
                            "session": str(i),
                            "expected": res.expected_email,
                            "observed": f"ERROR: {obs.error}",
                        }
                    )
                    continue

                if obs.email_before != res.expected_email:
                    mismatches.append(
                        {
                            "round": str(round_idx),
                            "session": str(i),
                            "expected": res.expected_email,
                            "observed": obs.email_before or "<None>",
                            "phase": "before_yield",
                        }
                    )

                if obs.email_after != res.expected_email:
                    mismatches.append(
                        {
                            "round": str(round_idx),
                            "session": str(i),
                            "expected": res.expected_email,
                            "observed": obs.email_after or "<None>",
                            "phase": "after_yield",
                        }
                    )

        # ---- Report ----
        total = N_SESSIONS * N_ROUNDS
        if mismatches:
            lines = [
                f"Session contamination: {len(mismatches)}/{total} "
                f"mismatches across {N_ROUNDS} rounds "
                f"({N_SESSIONS} sessions):",
            ]
            for m in mismatches[:10]:
                phase = m.get("phase", "")
                phase_str = f" [{phase}]" if phase else ""
                lines.append(
                    f"  round={m['round']} session={m['session']}"
                    f"{phase_str}: "
                    f"expected={m['expected']} "
                    f"observed={m['observed']}"
                )
            if len(mismatches) > 10:
                lines.append(
                    f"  ... and {len(mismatches) - 10} more",
                )
            pytest.fail("\n".join(lines))
