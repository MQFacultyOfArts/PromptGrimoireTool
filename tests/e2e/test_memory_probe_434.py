"""E2E memory probe for #434: concurrent client RSS growth.

Exercises the FULL production path -- 10 real Playwright browser contexts
hit the annotation page simultaneously, rendering a heavy workspace
(181 KB CRDT, 190 highlights, 11 tags, 426 KB document). All disconnect,
server-side GC + malloc_trim runs, RSS is measured. Repeated for N cycles.

Two variants:
- **Forced cleanup**: /api/test/cleanup between cycles (scrubbed test harness)
- **Natural cleanup**: no forced cleanup, only WebSocket disconnect + timeout
  (production-like, answers: "does natural cleanup actually free memory?")

Discriminates:
- **Leak**: RSS grows linearly per cycle after gc+trim
- **Fragmentation**: RSS stabilises after gc+trim

Uses the Pabai workspace fixture from test_browser_perf_377.py.
Run with: uv run grimoire e2e perf -k test_memory_probe
"""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from promptgrimoire.config import get_settings

if TYPE_CHECKING:
    from playwright.sync_api import Browser, Page

PABAI_WORKSPACE_ID = "0e5e9b04-de94-4728-a8c9-e625c141fea3"
_WORKSPACE_JSON = Path(__file__).parent / "fixtures" / "pabai_workspace.json"

# Number of connect/disconnect cycles
CYCLES = 5
# Number of concurrent browser clients per cycle
N_CLIENTS = 10

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.perf,
    pytest.mark.skipif(
        not get_settings().dev.test_database_url,
        reason="DEV__TEST_DATABASE_URL not configured",
    ),
]


def _test_db_conninfo() -> str:
    """Build psycopg conninfo for the test database."""
    from urllib.parse import urlparse

    url = get_settings().dev.test_database_url
    if not url:
        msg = "DEV__TEST_DATABASE_URL not configured"
        raise RuntimeError(msg)
    parsed = urlparse(url)
    user = parsed.username or "brian"
    dbname = parsed.path.lstrip("/")
    host = parsed.hostname or "/var/run/postgresql"
    if "host=" in (parsed.query or ""):
        for param in parsed.query.split("&"):
            if param.startswith("host="):
                host = param.split("=", 1)[1]
    return f"user={user} dbname={dbname} host={host}"


def _fetch_json(url: str, *, method: str = "GET") -> dict:
    """Fetch JSON from a URL (test-only localhost)."""
    req = urllib.request.Request(
        url, method=method, data=b"" if method == "POST" else None
    )
    with urllib.request.urlopen(req, timeout=10) as resp:  # test-only localhost URL
        return json.loads(resp.read().decode())


@pytest.fixture(scope="session")
def pabai_workspace() -> str:
    """Ensure the Pabai workspace is rehydrated into the test DB."""
    import psycopg

    if not _WORKSPACE_JSON.exists():
        pytest.skip(f"Workspace JSON not found at {_WORKSPACE_JSON}")

    conninfo = _test_db_conninfo()

    with psycopg.connect(conninfo) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM workspace WHERE id = %s::uuid",
            (PABAI_WORKSPACE_ID,),
        )
        if cur.fetchone() is not None:
            return PABAI_WORKSPACE_ID

    from scripts.rehydrate_workspace import rehydrate

    result = rehydrate(_WORKSPACE_JSON, conninfo)
    assert result["workspace_id"] == PABAI_WORKSPACE_ID
    return PABAI_WORKSPACE_ID


def _authenticate_and_grant(
    page: Page,
    app_server: str,
    workspace_id: str,
    email: str,
) -> None:
    """Authenticate via mock auth and grant owner ACL on the workspace."""
    import psycopg

    page.goto(f"{app_server}/auth/callback?token=mock-token-{email}")
    page.wait_for_url(lambda url: "/auth/callback" not in url, timeout=10_000)

    conninfo = _test_db_conninfo()
    with psycopg.connect(conninfo) as conn:
        cur = conn.cursor()
        cur.execute('SELECT id FROM "user" WHERE email = %s', (email,))
        row = cur.fetchone()
        assert row is not None, f"Mock auth didn't create user {email}"
        cur.execute(
            "INSERT INTO acl_entry"
            " (id, workspace_id, user_id, permission, created_at)"
            " VALUES (gen_random_uuid(), %s::uuid, %s, 'owner', now())"
            " ON CONFLICT DO NOTHING",
            (workspace_id, row[0]),
        )
        conn.commit()


def _format_results(results: list[dict]) -> str:
    """Format probe results as a readable table."""
    hdr = (
        "cycle | phase      | rss_MB | gc_collected"
        " | clients | presence | ws_reg | tasks"
    )
    sep = (
        "------|------------|--------|----------"
        "----|---------|----------|--------|------"
    )
    lines = [hdr, sep]
    for r in results:
        lines.append(
            f"{r['cycle']:>5} | {r['phase']:<10}"
            f" | {r['rss_after_trim_mb']:>6.0f}"
            f" | {r['gc_collected']:>12}"
            f" | {r['clients']:>7}"
            f" | {r['presence_clients']:>8}"
            f" | {r['ws_registry']:>6}"
            f" | {r['tasks']:>5}"
        )
    return "\n".join(lines)


def _run_probe(
    browser: Browser,
    app_server: str,
    ws_id: str,
    *,
    force_cleanup: bool,
) -> tuple[list[dict], str]:
    """Core probe loop: N cycles of connect/disconnect with measurement.

    Args:
        force_cleanup: If True, call /api/test/cleanup between cycles
            (scrubbed test harness). If False, rely only on natural
            WebSocket disconnect + NiceGUI reconnect_timeout (0.5s in
            E2E server) for cleanup (production-like path).

    Returns:
        (results list, formatted summary string)
    """
    results: list[dict] = []

    # Baseline: GC before any clients connect
    gc_data = _fetch_json(f"{app_server}/api/test/gc", method="POST")
    diag_data = _fetch_json(f"{app_server}/api/test/diagnostics")
    results.append(
        {
            "cycle": 0,
            "phase": "baseline",
            "rss_after_trim_mb": (gc_data["rss_after_trim"] or 0) / 1048576,
            "gc_collected": gc_data["gc_collected"],
            "clients": diag_data["nicegui_clients"],
            "presence_clients": diag_data["presence_total_clients"],
            "ws_registry": diag_data["ws_registry"],
            "tasks": diag_data["asyncio_tasks"],
        }
    )

    for cycle in range(1, CYCLES + 1):
        # --- CONNECT: N_CLIENTS browsers open the annotation page ---
        contexts = []
        pages = []
        for i in range(N_CLIENTS):
            ctx = browser.new_context()
            page = ctx.new_page()
            email = f"mem-probe-{uuid4().hex[:6]}-{i}@test.example.edu.au"
            _authenticate_and_grant(page, app_server, ws_id, email)
            contexts.append(ctx)
            pages.append(page)

        # Navigate all to annotation page
        for page in pages:
            page.goto(f"{app_server}/annotation?workspace_id={ws_id}")

        # Wait for all to render
        for page in pages:
            page.wait_for_function(
                "() => document.querySelector("
                "'[data-testid=\"doc-container\"]')"
                " && window._textNodes"
                " && window._textNodes.length > 0",
                timeout=60_000,
            )

        # Snapshot: all clients connected
        diag_connected = _fetch_json(f"{app_server}/api/test/diagnostics")
        results.append(
            {
                "cycle": cycle,
                "phase": "connected",
                "rss_after_trim_mb": (diag_connected["rss_bytes"] or 0) / 1048576,
                "gc_collected": 0,
                "clients": diag_connected["nicegui_clients"],
                "presence_clients": diag_connected["presence_total_clients"],
                "ws_registry": diag_connected["ws_registry"],
                "tasks": diag_connected["asyncio_tasks"],
            }
        )

        # --- DISCONNECT: Close all browser contexts ---
        for page in pages:
            page.goto("about:blank")
        for page in pages:
            page.close()
        for ctx in contexts:
            ctx.close()

        if force_cleanup:
            # Scrubbed: wait for reconnect timeout then force-delete
            time.sleep(3.0)
            _fetch_json(f"{app_server}/api/test/cleanup", method="POST")
            time.sleep(1.0)
        else:
            # Production-like: wait for natural cleanup only.
            # E2E server reconnect_timeout=0.5s, then Client.delete()
            # fires our on_client_delete() chain. Allow 5s total for
            # all 10 clients to complete the chain.
            time.sleep(5.0)

        # GC + malloc_trim
        gc_data = _fetch_json(f"{app_server}/api/test/gc", method="POST")
        diag_data = _fetch_json(f"{app_server}/api/test/diagnostics")

        results.append(
            {
                "cycle": cycle,
                "phase": "after_gc",
                "rss_after_trim_mb": (gc_data["rss_after_trim"] or 0) / 1048576,
                "gc_collected": gc_data["gc_collected"],
                "clients": diag_data["nicegui_clients"],
                "presence_clients": diag_data["presence_total_clients"],
                "ws_registry": diag_data["ws_registry"],
                "tasks": diag_data["asyncio_tasks"],
            }
        )

    summary = _format_results(results)
    return results, summary


class TestMemoryProbe434:
    """Concurrent client memory probe -- 10 browsers x N cycles."""

    def test_concurrent_memory_growth(
        self,
        browser: Browser,
        app_server: str,
        pabai_workspace: str,
    ) -> None:
        """RSS after forced cleanup + gc+trim should stabilise.

        Uses /api/test/cleanup between cycles to force-delete stale
        clients. This is the scrubbed-harness variant — measures the
        lower bound of per-client retention.
        """
        results, summary = _run_probe(
            browser, app_server, pabai_workspace, force_cleanup=True
        )

        print(f"\n=== Forced cleanup ===\n{summary}")

        out = Path("output/incident/e2e_probe_forced.txt")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(summary, encoding="utf-8")

        gc_results = [r for r in results if r["phase"] == "after_gc"]
        if len(gc_results) >= 3:
            early = gc_results[0]["rss_after_trim_mb"]
            late = gc_results[-1]["rss_after_trim_mb"]
            growth = late / early if early > 0 else 0

            print(f"\n  early={early:.0f}MB  late={late:.0f}MB  growth={growth:.3f}x")

            assert growth < 1.5, (
                f"RSS grew {growth:.2f}x with forced cleanup "
                f"({early:.0f}->{late:.0f} MB)\n{summary}"
            )

        final = gc_results[-1] if gc_results else results[-1]
        assert final["presence_clients"] == 0, (
            f"Expected 0 presence clients after forced cleanup, "
            f"got {final['presence_clients']}"
        )

    def test_natural_cleanup_memory_growth(
        self,
        browser: Browser,
        app_server: str,
        pabai_workspace: str,
    ) -> None:
        """RSS after natural cleanup + gc+trim — production-like path.

        No /api/test/cleanup between cycles. Relies only on WebSocket
        disconnect triggering NiceGUI's reconnect_timeout (0.5s in E2E)
        then Client.delete() -> on_client_delete() chain.

        This answers: "does the natural cleanup path actually free
        memory, or does forced cleanup mask retention?"
        """
        results, summary = _run_probe(
            browser, app_server, pabai_workspace, force_cleanup=False
        )

        print(f"\n=== Natural cleanup ===\n{summary}")

        out = Path("output/incident/e2e_probe_natural.txt")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(summary, encoding="utf-8")

        gc_results = [r for r in results if r["phase"] == "after_gc"]
        if len(gc_results) >= 3:
            early = gc_results[0]["rss_after_trim_mb"]
            late = gc_results[-1]["rss_after_trim_mb"]
            growth = late / early if early > 0 else 0

            print(f"\n  early={early:.0f}MB  late={late:.0f}MB  growth={growth:.3f}x")

            # More generous threshold for natural cleanup — we
            # expect higher retention than forced cleanup
            assert growth < 2.0, (
                f"RSS grew {growth:.2f}x with natural cleanup "
                f"({early:.0f}->{late:.0f} MB)\n{summary}"
            )

        # Natural cleanup may leave stragglers if reconnect_timeout
        # hasn't fully expired for all clients. Log but don't fail
        # on non-zero presence — the RSS comparison is what matters.
        final = gc_results[-1] if gc_results else results[-1]
        if final["presence_clients"] > 0:
            print(
                f"\n  NOTE: {final['presence_clients']} presence "
                f"clients remain after natural cleanup "
                f"(cleanup chain may still be in progress)"
            )
