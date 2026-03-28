"""H7 discriminating test: concurrent page loads must not cross-contaminate sessions.

Issue: #438 (cross-user session contamination)

Hypothesis H7: Under event loop saturation, NiceGUI's page handler runs in an
asyncio Task (background_tasks.create at page.py:172) that may inherit a stale
request_contextvar from another concurrent request.  app.storage.user then
resolves to the wrong user's storage.

Strategy:
  1. Spin up N independent Playwright instances (separate processes/event loops)
  2. Authenticate each with a distinct mock user
  3. All N navigate to /test/session-identity simultaneously via a barrier
  4. The page handler reads app.storage.user -> auth_user -> email and renders
     it in a data-testid="session-email" element
  5. Each thread captures the displayed email and compares to expected
  6. Any mismatch is contamination

Each thread owns its own Playwright instance, browser, context, and page --
no shared event loop, no SyncBase._sync contention.  The server sees N
genuinely concurrent TCP connections, just like production.

The /test/session-identity page is a real @ui.page (not a FastAPI endpoint),
so it exercises the full middleware -> background_tasks.create -> page handler
code path where the bug manifests.

Run with:
  uv run grimoire e2e run -k "test_h7" --serial
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from uuid import uuid4

import pytest

pytestmark = [pytest.mark.e2e]

# Number of concurrent sessions.  Production incident had ~189 users.
# 20 is enough to create meaningful interleaving in the event loop
# while keeping resource usage reasonable (each is a full browser).
N_SESSIONS = 20
# Rounds of concurrent navigation to increase chance of triggering.
N_ROUNDS = 5


@dataclass
class WorkerResult:
    """Collects results from a single worker thread."""

    expected_email: str = ""
    observations: list[RoundObservation] = field(default_factory=list)


@dataclass
class RoundObservation:
    """What one session saw in a single round."""

    email_before: str | None = None
    email_after: str | None = None
    error: str | None = None


def _run_session(
    app_server: str,
    barrier: threading.Barrier,
    result: WorkerResult,
    n_rounds: int,
) -> None:
    """Run a complete session lifecycle in its own Playwright instance.

    Each thread: launches Playwright -> Chromium -> authenticates -> waits
    at the barrier -> navigates to the identity page -> captures email.
    Repeated for n_rounds.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            context = browser.new_context()
            page = context.new_page()

            # Authenticate
            unique_id = uuid4().hex[:8]
            email = f"h7-{unique_id}@test.example.edu.au"
            result.expected_email = email
            page.goto(
                f"{app_server}/auth/callback?token=mock-token-{email}",
            )
            page.wait_for_url(
                lambda url: "/auth/callback" not in url,
                timeout=15000,
            )

            identity_url = f"{app_server}/test/session-identity"

            for _ in range(n_rounds):
                # All threads wait here, then fire simultaneously.
                barrier.wait(timeout=30)

                obs = RoundObservation()
                try:
                    page.goto(identity_url)
                    loc = page.get_by_test_id("session-email")
                    loc.wait_for(state="attached", timeout=15000)
                    obs.email_before = loc.inner_text()

                    # Also capture "after" email (read after yield points).
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

            # Navigate away before closing
            page.goto("about:blank")
            context.close()
        finally:
            browser.close()


class TestH7SessionContamination:
    """Concurrent page loads must not cross-contaminate sessions."""

    def test_concurrent_session_identity(
        self,
        app_server: str,
    ) -> None:
        """Fire N concurrent page loads from independent browsers.

        Each thread owns its own Playwright instance (separate process).
        A threading.Barrier synchronises navigation so all N hit the
        server at the same moment, maximising event loop contention.
        """
        barrier = threading.Barrier(N_SESSIONS, timeout=60)
        results: list[WorkerResult] = [WorkerResult() for _ in range(N_SESSIONS)]

        threads = [
            threading.Thread(
                target=_run_session,
                args=(app_server, barrier, results[i], N_ROUNDS),
                name=f"h7-session-{i}",
            )
            for i in range(N_SESSIONS)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=120)

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

                # Check initial read
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

                # Check post-yield read (mid-handler contamination)
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
