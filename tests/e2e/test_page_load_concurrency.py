"""Concurrent page load stress test for #377.

Measures annotation page load latency under concurrent browser sessions
to reproduce production "Response not ready after 3.0 seconds" warnings.

Strategy:
  1. Create N workspaces (one per user) — each with content
  2. Navigate each user to their workspace sequentially
  3. Measure wall-clock page load time for each
  4. With N connected clients, the event loop and DB pool are under
     increasing load — later navigations should degrade

Run with:
  uv run grimoire e2e run -k "test_concurrent_page_load" --serial

The --serial flag is important: parallel mode clones the database per test
file.  Serial mode shares a single server + DB.
"""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from promptgrimoire.config import get_settings
from promptgrimoire.docs.helpers import wait_for_text_walker

if TYPE_CHECKING:
    from playwright.sync_api import Browser, Page

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.perf,
    pytest.mark.skipif(
        not get_settings().dev.test_database_url,
        reason="DEV__TEST_DATABASE_URL not configured",
    ),
]

_CONTENT = (
    "The appellant was convicted of multiple offences under the "
    "Crimes Act 1900 (NSW). The primary issue on appeal concerned "
    "the admissibility of evidence obtained during a search of the "
    "appellant's premises. The Crown argued that the evidence was "
    "lawfully obtained pursuant to a valid search warrant issued "
    "under section 3E of the Crimes Act. The defence submitted "
    "that the warrant was defective and that the search was "
    "therefore unlawful. The court considered the procedural "
    "requirements for the issue of search warrants and the "
    "consequences of non-compliance. The court also examined "
    "the discretionary exclusion of improperly obtained evidence "
    "under section 138 of the Evidence Act 1995 (NSW). "
    "In reaching its decision the court applied the balancing "
    "test set out in that provision weighing the desirability "
    "of admitting the evidence against the undesirability of "
    "admitting evidence obtained improperly. "
    "The appeal was ultimately dismissed on all grounds."
)

# Total sessions to create and measure
_N_SESSIONS = 8


def _authenticate(page: Page, app_server: str) -> None:
    """Authenticate a page via mock magic link."""
    unique_id = uuid4().hex[:8]
    email = f"load-test-{unique_id}@test.example.edu.au"
    page.goto(f"{app_server}/auth/callback?token=mock-token-{email}")
    page.wait_for_url(lambda url: "/auth/callback" not in url, timeout=10000)


def _create_workspace_and_add_content(page: Page, app_server: str) -> str:
    """Create a workspace with content, return the workspace URL."""
    page.goto(f"{app_server}/annotation")
    page.get_by_test_id("create-workspace-btn").click()
    page.wait_for_url(re.compile(r"workspace_id="))

    content_input = page.get_by_test_id("content-editor").locator(".q-editor__content")
    content_input.fill(_CONTENT)
    page.get_by_test_id("add-document-btn").click()

    confirm_btn = page.get_by_test_id("confirm-content-type-btn")
    confirm_btn.wait_for(state="visible", timeout=5000)
    confirm_btn.click()

    wait_for_text_walker(page, timeout=15000)
    return page.url


def _print_results(results: list[dict]) -> None:
    """Print timing results table."""
    times = [r["elapsed_ms"] for r in results if r["success"]]
    if times:
        avg = sum(times) / len(times)
        print(
            f"\n  avg={avg:.0f}ms  min={min(times)}ms  max={max(times)}ms  "
            f"succeeded={len(times)}/{len(results)}"
        )
    for r in results:
        status = "OK" if r["success"] else "FAIL"
        detail = f" ({r['error']})" if "error" in r else ""
        print(f"    {r['label']}: {r['elapsed_ms']:5d}ms [{status}]{detail}")


class TestConcurrentPageLoad:
    """Measure annotation page load degradation as connected clients increase."""

    def test_concurrent_page_load(
        self,
        browser: Browser,
        app_server: str,
    ) -> None:
        """Create N workspaces, measure each page reload with growing contention.

        After creating each workspace (which establishes a connected client
        with presence tracking, CRDT subscriptions, and broadcast handlers),
        reload the workspace page and measure load time. As more clients
        connect, the event loop has more work to do per page load (presence
        updates, broadcast hooks), so later reloads should take longer.

        This tests event loop contention, not pool contention (tests use
        NullPool). Production uses QueuePool where pool contention adds
        further latency on top.
        """
        results: list[dict] = []
        contexts = []

        for i in range(_N_SESSIONS):
            context = browser.new_context()
            contexts.append(context)
            page = context.new_page()
            _authenticate(page, app_server)

            # Create workspace (this also loads the annotation page)
            workspace_url = _create_workspace_and_add_content(page, app_server)

            # Now measure a fresh reload of the annotation page
            # This is the measurement: how long does a page load take
            # with i other clients already connected?
            t_start = time.perf_counter()
            page.goto(workspace_url)
            result = {
                "label": f"session_{i} (clients_connected={i})",
                "success": False,
                "elapsed_ms": -1,
            }
            try:
                wait_for_text_walker(page, timeout=15000)
                result["elapsed_ms"] = round((time.perf_counter() - t_start) * 1000)
                result["success"] = True
            except Exception as exc:
                result["elapsed_ms"] = round((time.perf_counter() - t_start) * 1000)
                result["error"] = type(exc).__name__
            results.append(result)

        # Report
        print("\n" + "=" * 70)
        print("PAGE LOAD vs CONNECTED CLIENTS (#377 investigation)")
        print("=" * 70)
        _print_results(results)

        # Check for threshold violations
        over_3s = [r for r in results if r["elapsed_ms"] > 3000]
        if over_3s:
            print(f"\n⚠ {len(over_3s)} sessions exceeded 3000ms threshold")
        else:
            print("\n✓ No sessions exceeded 3000ms threshold")

        # Degradation analysis
        successful = [r for r in results if r["success"]]
        if len(successful) >= 2:
            first = successful[0]["elapsed_ms"]
            last = successful[-1]["elapsed_ms"]
            ratio = last / first if first > 0 else 0
            print(f"\n  First load: {first}ms")
            print(f"  Last load:  {last}ms")
            print(f"  Degradation: {ratio:.1f}x")

        print("=" * 70)

        # Clean up
        for ctx in contexts:
            for p in ctx.pages:
                p.goto("about:blank")
            ctx.close()

        # At least the first session must succeed
        assert results[0]["success"], f"First session failed: {results[0]}"
