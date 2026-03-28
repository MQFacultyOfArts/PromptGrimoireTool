"""E2E memory probe for #434: concurrent client RSS growth.

Exercises the FULL production path -- 10 real Playwright browser contexts
hit the annotation page simultaneously, rendering a heavy workspace
(181 KB CRDT, 190 highlights, 11 tags, 426 KB document). All disconnect,
server-side GC + malloc_trim runs, RSS is measured. Repeated for N cycles.

Five variants:
- **Forced cleanup**: /api/test/cleanup between cycles (scrubbed test harness)
- **Natural cleanup**: no forced cleanup, only WebSocket disconnect + timeout
  (production-like, answers: "does natural cleanup actually free memory?")
- **Cleanup gap isolation** (3 variants): natural cleanup + ONE targeted
  action (clients_only / eio_only / events_only). Identifies which
  /api/test/cleanup action reclaims the ~5 MB/cycle natural-vs-forced gap.

Discriminates:
- **Leak**: RSS grows linearly per cycle after gc+trim
- **Fragmentation**: RSS stabilises after gc+trim

Uses the Pabai workspace fixture from test_browser_perf_377.py.
Run with: uv run grimoire e2e perf -k test_memory_probe
"""

from __future__ import annotations

import json
import os
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

# System load threshold: perf tests skip if 1-minute load average exceeds
# 2x the number of CPUs. High load contaminates RSS measurements by
# delaying cleanup handlers and inflating the natural-vs-forced gap.
_MAX_LOAD_FACTOR = 2.0

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.perf,
    pytest.mark.skipif(
        not get_settings().dev.test_database_url,
        reason="DEV__TEST_DATABASE_URL not configured",
    ),
]


def _check_system_load() -> None:
    """Skip perf tests if system load is too high for valid measurements.

    Override threshold with PERF_MAX_LOAD env var for manual runs
    (e.g. PERF_MAX_LOAD=999 to bypass).
    """
    load_1min = os.getloadavg()[0]
    override = os.environ.get("PERF_MAX_LOAD")
    if override:
        threshold = float(override)
    else:
        cpus = os.cpu_count() or 1
        threshold = cpus * _MAX_LOAD_FACTOR
    if load_1min > threshold:
        pytest.skip(
            f"System load too high for perf tests: {load_1min:.1f} "
            f"(threshold: {threshold:.0f} = {cpus} CPUs x {_MAX_LOAD_FACTOR}). "
            f"RSS measurements would be contaminated by cleanup handler delays."
        )


@pytest.fixture(autouse=True)
def _load_gate() -> None:
    """Auto-applied fixture: skip all tests in this module if load is high."""
    _check_system_load()


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
    cleanup_mode: str = "none",
) -> tuple[list[dict], str]:
    """Core probe loop: N cycles of connect/disconnect with measurement.

    Args:
        force_cleanup: If True, call /api/test/cleanup between cycles
            (scrubbed test harness). If False, rely only on natural
            WebSocket disconnect + NiceGUI reconnect_timeout (0.5s in
            E2E server) for cleanup (production-like path).
        cleanup_mode: Which cleanup action(s) to run via the cleanup
            endpoint. Values: "none" (default — no targeted action),
            "all", "clients_only", "eio_only", "events_only".
            When force_cleanup is True, "none" is promoted to "all".
            When force_cleanup is False, non-"none" values run a
            targeted cleanup action after the natural wait period.

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

        # Resolve effective cleanup mode: force_cleanup promotes "none"→"all"
        effective_mode = cleanup_mode
        if force_cleanup and cleanup_mode == "none":
            effective_mode = "all"

        cleanup_resp: dict | None = None
        if force_cleanup:
            # Scrubbed: wait for reconnect timeout then force-delete
            time.sleep(3.0)
            cleanup_url = f"{app_server}/api/test/cleanup?mode={effective_mode}"
            cleanup_resp = _fetch_json(cleanup_url, method="POST")
            time.sleep(1.0)
        else:
            # Production-like: wait for natural cleanup only.
            # E2E server reconnect_timeout=0.5s, then Client.delete()
            # fires our on_client_delete() chain. Allow 5s total for
            # all 10 clients to complete the chain.
            time.sleep(5.0)

            # Snapshot AFTER natural wait, BEFORE targeted action.
            # This proves natural cleanup completed independently —
            # without it, the targeted action could mask incomplete
            # natural cleanup, weakening the causal read.
            if effective_mode != "none":
                diag_pre = _fetch_json(f"{app_server}/api/test/diagnostics")
                results.append(
                    {
                        "cycle": cycle,
                        "phase": "after_natural",
                        "rss_after_trim_mb": ((diag_pre["rss_bytes"] or 0) / 1048576),
                        "gc_collected": 0,
                        "clients": diag_pre["nicegui_clients"],
                        "presence_clients": (diag_pre["presence_total_clients"]),
                        "ws_registry": diag_pre["ws_registry"],
                        "tasks": diag_pre["asyncio_tasks"],
                    }
                )

                cleanup_url = f"{app_server}/api/test/cleanup?mode={effective_mode}"
                cleanup_resp = _fetch_json(cleanup_url, method="POST")
                time.sleep(0.5)

        # GC + malloc_trim
        gc_data = _fetch_json(f"{app_server}/api/test/gc", method="POST")
        diag_data = _fetch_json(f"{app_server}/api/test/diagnostics")

        result_entry: dict = {
            "cycle": cycle,
            "phase": "after_gc",
            "rss_after_trim_mb": (gc_data["rss_after_trim"] or 0) / 1048576,
            "gc_collected": gc_data["gc_collected"],
            "clients": diag_data["nicegui_clients"],
            "presence_clients": diag_data["presence_total_clients"],
            "ws_registry": diag_data["ws_registry"],
            "tasks": diag_data["asyncio_tasks"],
        }
        if cleanup_resp is not None:
            result_entry["cleanup_resp"] = cleanup_resp
        results.append(result_entry)

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


def _assert_isolation_invariants(
    results: list[dict],
    mode_name: str,
    positive_control_key: str,
) -> None:
    """Common assertions for cleanup gap isolation variants.

    1. Natural cleanup completed BEFORE the targeted action ran
       (presence == 0 on after_natural snapshots).
    2. Everything clean after the full sequence (presence == 0 on
       after_gc snapshots).
    3. Positive control: the targeted action actually matched
       something (cleanup_resp[key] > 0 on at least one cycle).
    """
    # Check natural cleanup completed before targeted action
    natural_snaps = [r for r in results if r["phase"] == "after_natural"]
    for snap in natural_snaps:
        assert snap["presence_clients"] == 0, (
            f"[{mode_name}] Natural cleanup incomplete before targeted "
            f"action: presence={snap['presence_clients']} on cycle "
            f"{snap['cycle']}. The 5s wait was insufficient — results "
            f"are contaminated."
        )

    # Check final state
    gc_results = [r for r in results if r["phase"] == "after_gc"]
    if gc_results:
        final = gc_results[-1]
        assert final["presence_clients"] == 0, (
            f"[{mode_name}] Presence not zero after full cleanup: "
            f"{final['presence_clients']}"
        )

    # Positive control: targeted action matched something
    cleanup_resps = [r["cleanup_resp"] for r in gc_results if "cleanup_resp" in r]
    if cleanup_resps:
        total = sum(r.get(positive_control_key, 0) for r in cleanup_resps)
        print(f"\n  [{mode_name}] {positive_control_key}: {total} total")
        assert total > 0, (
            f"[{mode_name}] Targeted action matched zero targets "
            f"({positive_control_key}=0 across all cycles). The mode "
            f"may not be exercising its intended cleanup path — results "
            f"are ambiguous."
        )


class TestCleanupGapIsolation:
    """Isolate which /api/test/cleanup action reclaims the ~5 MB/cycle gap.

    Each variant: natural cleanup (5s wait) + ONE targeted cleanup action
    + GC. Comparing per-cycle RSS growth across variants identifies which
    action(s) account for the difference between natural (~6 MB/cycle)
    and forced (~1 MB/cycle) cleanup.

    Run with: uv run grimoire e2e perf -k test_cleanup_gap
    """

    def test_cleanup_gap_clients_only(
        self,
        browser: Browser,
        app_server: str,
        pabai_workspace: str,
    ) -> None:
        """Natural cleanup + force-delete remaining NiceGUI clients.

        Tests whether stale Client instances (missed by natural timeout)
        account for the gap. If per-cycle growth drops to ~1 MB, client
        deletion is the key reclamation action.
        """
        results, summary = _run_probe(
            browser,
            app_server,
            pabai_workspace,
            force_cleanup=False,
            cleanup_mode="clients_only",
        )

        print(f"\n=== Cleanup gap: clients_only ===\n{summary}")

        out = Path("output/incident/e2e_probe_clients_only.txt")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(summary, encoding="utf-8")

        _assert_isolation_invariants(results, "clients_only", "deleted")

    def test_cleanup_gap_eio_only(
        self,
        browser: Browser,
        app_server: str,
        pabai_workspace: str,
    ) -> None:
        """Natural cleanup + disconnect orphan engine.io sessions.

        Tests whether stale engine.io WebSocket sessions (surviving after
        NiceGUI client deletion) account for the gap. These hold
        per-connection request objects and event handler registries.
        """
        results, summary = _run_probe(
            browser,
            app_server,
            pabai_workspace,
            force_cleanup=False,
            cleanup_mode="eio_only",
        )

        print(f"\n=== Cleanup gap: eio_only ===\n{summary}")

        out = Path("output/incident/e2e_probe_eio_only.txt")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(summary, encoding="utf-8")

        _assert_isolation_invariants(results, "eio_only", "eio_closed")

    def test_cleanup_gap_events_only(
        self,
        browser: Browser,
        app_server: str,
        pabai_workspace: str,
    ) -> None:
        """Natural cleanup + cancel orphan Event.wait tasks.

        Tests whether leaked Event.wait tasks (from NiceGUI's page
        handler not cancelling _waiting_for_connection.wait()) account
        for the gap. Each task retains its closure scope.
        """
        results, summary = _run_probe(
            browser,
            app_server,
            pabai_workspace,
            force_cleanup=False,
            cleanup_mode="events_only",
        )

        print(f"\n=== Cleanup gap: events_only ===\n{summary}")

        out = Path("output/incident/e2e_probe_events_only.txt")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(summary, encoding="utf-8")

        _assert_isolation_invariants(results, "events_only", "orphan_wait")
