"""Performance instrumentation for #377 — browser + server timing.

Loads the rehydrated Pabai workspace (190 highlights, 5,020 text nodes)
and captures:
- Browser console.time output (applyHighlights, positionCards)
- Server-side structlog timing (render_phase, tag_apply_phase, page_phase)

The fixture at tests/e2e/fixtures/pabai_workspace.json is a PII-sanitised
copy of the production workspace (author names and user_ids replaced).

Run with:
    uv run grimoire test run tests/e2e/test_browser_perf_377.py -m perf -v -s
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from playwright.sync_api import ConsoleMessage, expect

from promptgrimoire.config import get_settings
from promptgrimoire.docs.helpers import select_chars
from tests.e2e.card_helpers import (
    PABAI_WORKSPACE_ID,
    ensure_pabai_workspace,
    test_db_conninfo,
)

if TYPE_CHECKING:
    from collections.abc import Generator

    from playwright.sync_api import Browser, Page
_MAX_LOAD_AVG = 10.0  # 1-min load average ceiling for perf tests

# structlog events we want to capture
_SERVER_TIMING_EVENTS = frozenset(
    {
        "render_phase",
        "tag_apply_phase",
        "page_phase",
        "page_load_total",
        "resolve_step",
    }
)


def _check_system_load() -> None:
    """Skip perf tests if system load is too high for reliable numbers."""
    load_1min = os.getloadavg()[0]
    if load_1min > _MAX_LOAD_AVG:
        pytest.skip(
            f"System load too high for perf tests: "
            f"{load_1min:.1f} > {_MAX_LOAD_AVG:.0f}."
        )


pytestmark = [
    pytest.mark.e2e,
    pytest.mark.perf,
    pytest.mark.skipif(
        not get_settings().dev.test_database_url,
        reason="DEV__TEST_DATABASE_URL not configured",
    ),
]


class ServerLogReader:
    """Read structlog JSONL entries from the server's log file.

    Provides checkpoint/read_since semantics so each test action
    gets only the log lines produced during that action.
    """

    def __init__(self, server_log: Path = Path("test-e2e-server.log")) -> None:
        self._server_log = server_log
        self._offset: int = 0
        self._log_file: Path | None = None

    def _find_log_file(self) -> Path | None:
        """Find the structlog JSONL file by parsing test-e2e-server.log.

        The server prints "Log file: <absolute-path>" in a JSONL entry
        during startup. Parse that, falling back to recursive glob.
        """
        # Strategy 1: parse path from server startup log
        if self._server_log.exists():
            for line in self._server_log.read_text().splitlines()[:10]:
                if "Log file:" in line:
                    try:
                        record = json.loads(line)
                        event = record.get("event", "")
                    except json.JSONDecodeError:
                        event = line
                    # Extract path after "Log file: "
                    idx = event.find("Log file: ")
                    if idx >= 0:
                        path = Path(event[idx + len("Log file: ") :].strip())
                        if path.exists():
                            return path

        # Strategy 2: recursive glob from logs/
        candidates = sorted(Path("logs").rglob("promptgrimoire*.jsonl"))
        return candidates[-1] if candidates else None

    def checkpoint(self) -> None:
        """Mark current end of log file — read_since returns only new lines."""
        if self._log_file is None:
            self._log_file = self._find_log_file()
        if self._log_file and self._log_file.exists():
            self._offset = self._log_file.stat().st_size

    def read_since(self, *, settle_seconds: float = 1.0) -> list[dict[str, object]]:
        """Read timing-relevant log entries since last checkpoint.

        Waits briefly for the server to flush buffered log writes.
        """
        time.sleep(settle_seconds)
        if self._log_file is None:
            self._log_file = self._find_log_file()
        if self._log_file is None or not self._log_file.exists():
            return []

        entries: list[dict[str, object]] = []
        with self._log_file.open() as f:
            f.seek(self._offset)
            for raw_line in f:
                stripped = raw_line.strip()
                if not stripped:
                    continue
                try:
                    record = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                event = record.get("event", "")
                if event in _SERVER_TIMING_EVENTS:
                    entries.append(record)
        return entries


def _print_server_timings(entries: list[dict[str, object]], label: str) -> None:
    """Print server-side timing entries in a readable format."""
    print(f"\n=== Server-side timing ({label}) ===")
    for entry in entries:
        event = entry.get("event", "")
        phase = entry.get("phase", entry.get("step", ""))
        elapsed = entry.get("elapsed_ms", "?")
        extras = {
            k: v
            for k, v in entry.items()
            if k
            not in (
                "event",
                "phase",
                "step",
                "elapsed_ms",
                "level",
                "timestamp",
                "pid",
                "branch",
                "commit",
                "user_id",
                "workspace_id",
                "request_path",
            )
            and v is not None
        }
        extra_str = f"  {extras}" if extras else ""
        print(f"  {event}/{phase}: {elapsed}ms{extra_str}")


@pytest.fixture(scope="module")
def pabai_workspace() -> str:
    """Rehydrate the Pabai workspace (idempotent, module-scoped)."""
    return ensure_pabai_workspace()


@pytest.fixture(scope="session")
def server_log() -> ServerLogReader:
    """Provide a reader for the server's structlog JSONL output.

    The NiceGUI E2E server writes structlog JSON to logs/sessions/*.jsonl.
    The exact path is parsed from test-e2e-server.log (printed at startup).
    This reader lets tests checkpoint before an action and read
    only the entries produced during that action.
    """
    reader = ServerLogReader()
    # Wait for the log file to exist (server may take a moment)
    for _ in range(30):
        if reader._find_log_file() is not None:
            break
        time.sleep(0.5)
    return reader


@pytest.fixture
def pabai_page(
    browser: Browser,
    app_server: str,
    pabai_workspace: str,
) -> Generator[Page]:
    """Authenticated page with owner ACL on the Pabai workspace."""
    import psycopg

    context = browser.new_context()
    page = context.new_page()

    # Enable perf instrumentation in JS (gates console.time calls)
    page.add_init_script("window.__perfInstrumented = true;")

    # Authenticate (creates user in DB via mock auth)
    unique_id = uuid4().hex[:8]
    email = f"perf-377-{unique_id}@test.example.edu.au"
    page.goto(f"{app_server}/auth/callback?token=mock-token-{email}")
    page.wait_for_url(lambda url: "/auth/callback" not in url, timeout=10_000)

    # Grant owner ACL via direct SQL
    conninfo = test_db_conninfo()
    with psycopg.connect(conninfo) as conn:
        cur = conn.cursor()
        cur.execute(
            'SELECT id FROM "user" WHERE email = %s',
            (email,),
        )
        row = cur.fetchone()
        assert row is not None, f"Mock auth didn't create user {email}"
        user_id = row[0]
        cur.execute(
            "INSERT INTO acl_entry"
            " (id, workspace_id, user_id, permission, created_at)"
            " VALUES (gen_random_uuid(), %s::uuid, %s, 'owner', now())"
            " ON CONFLICT DO NOTHING",
            (pabai_workspace, user_id),
        )
        conn.commit()

    yield page

    page.goto("about:blank")
    page.close()
    context.close()


_TIMING_RE = re.compile(r"^(.+?):\s+([\d.]+)\s*ms$")


class TestBrowserPerf377:
    """Capture browser-side performance timings for H2b/H2c."""

    @pytest.fixture(autouse=True)
    def _load_guard(self) -> None:
        _check_system_load()

    def test_page_load_timings(
        self, pabai_page: Page, app_server: str, server_log: ServerLogReader
    ) -> None:
        """Load Pabai workspace and capture browser + server timings.

        Browser: console.time results for applyHighlights, positionCards.
        Server: render_phase (ui_html, extract_text, inject_para_attrs),
                page_phase (resolve_context, list_documents, etc.),
                page_load_total.
        """
        page = pabai_page
        timings: dict[str, float] = {}

        def capture_console(msg: ConsoleMessage) -> None:
            text = msg.text
            m = _TIMING_RE.match(text)
            if m:
                label, ms = m.group(1), float(m.group(2))
                timings[label] = ms

        page.on("console", capture_console)

        # Checkpoint server log before page load
        server_log.checkpoint()

        # Clear stale JS state from prior page and force full reload.
        # NiceGUI SPA routing can preserve window globals across
        # page.goto(), so we navigate to about:blank first.
        ws_url = f"{app_server}/annotation?workspace_id={PABAI_WORKSPACE_ID}"
        page.goto("about:blank")
        page.goto(ws_url, wait_until="networkidle")

        # Wait for the workspace content to fully render.
        # __loadComplete is set by the deferred-load branch's
        # background task; on main the doc-container appears
        # synchronously.  Accept either signal.
        page.wait_for_function(
            "() => {"
            "  if (typeof window.__loadComplete !== 'undefined')"
            "    return window.__loadComplete === true;"
            "  return document.querySelector("
            "    '[data-testid=\"doc-container\"]') !== null;"
            "}",
            timeout=60_000,
        )

        # Highlights applied and text nodes populated
        page.wait_for_function(
            "() => document.querySelector("
            "  '[data-testid=\"doc-container\"]')"
            " && window._textNodes"
            " && window._textNodes.length > 0"
            " && window._highlightsReady === true",
            timeout=60_000,
        )

        # Trigger positionCards explicitly — in headless Chromium
        # the rAF chain can stall without a real paint.
        page.evaluate("() => {  if (window._positionCards) window._positionCards();}")

        # Report card state.  charOffsetToRect returns zero-size
        # rects for off-screen text nodes in headless mode (no paint
        # for 425KB documents), so cards may not get positioned.
        # The sidebar ID is per-document: ann-container-{doc_id}.
        card_state = page.evaluate(
            "() => {"
            "  const ac = document.querySelector("
            "    '[id^=\"ann-container-\"]');"
            "  if (!ac) return {cards: 0, positioned: false,"
            "    error: 'no ann-container-* element'};"
            "  const cards = ac.querySelectorAll("
            "    '[data-start-char]');"
            "  const first = cards[0];"
            "  return {"
            "    cards: cards.length,"
            "    positioned: !!(first && first.style.top),"
            "    containerId: ac.id,"
            "  };"
            "}"
        )

        # --- Browser timings ---
        print("\n=== Browser perf (Pabai, page load) ===")
        for label, ms in sorted(timings.items()):
            print(f"  {label}: {ms:.1f}ms")
        print(f"  sidebar cards: {card_state}")

        assert "applyHighlights" in timings, (
            f"applyHighlights timing not captured. Got: {list(timings.keys())}"
        )

        # --- Server timings ---
        server_entries = server_log.read_since()
        _print_server_timings(server_entries, "page load")

        # Verify we got timing data for the key hypotheses
        server_phases = {e.get("phase") or e.get("step") for e in server_entries}
        assert "ui_html" in server_phases, (
            f"H2: ui_html timing not captured. Got: {server_phases}"
        )

    def test_tag_apply_timings(
        self, pabai_page: Page, app_server: str, server_log: ServerLogReader
    ) -> None:
        """Apply a tag and capture browser + server timings.

        Browser: applyHighlights + positionCards cost.
        Server: tag_apply_phase (persist, card rebuild, broadcast, total).
        """
        page = pabai_page
        timings: dict[str, list[float]] = {}

        def capture_console(msg: ConsoleMessage) -> None:
            text = msg.text
            m = _TIMING_RE.match(text)
            if m:
                label, ms = m.group(1), float(m.group(2))
                timings.setdefault(label, []).append(ms)

        page.on("console", capture_console)

        ws_url = f"{app_server}/annotation?workspace_id={PABAI_WORKSPACE_ID}"
        page.goto("about:blank")
        page.goto(ws_url, wait_until="networkidle")
        page.wait_for_function(
            "() => {"
            "  if (typeof window.__loadComplete !== 'undefined')"
            "    return window.__loadComplete === true;"
            "  return document.querySelector("
            "    '[data-testid=\"doc-container\"]') !== null;"
            "}",
            timeout=60_000,
        )
        page.wait_for_function(
            "() => window._highlightsReady === true",
            timeout=60_000,
        )
        # Trigger positionCards explicitly (headless rAF can stall)
        page.evaluate("() => {  if (window._positionCards) window._positionCards();}")

        # Snapshot page-load timings, then clear for interaction
        load_timings = dict(timings)
        timings.clear()

        # Select text and apply a tag
        tag_btns = page.locator('[data-testid^="tag-btn-"]')
        expect(tag_btns.first).to_be_visible(timeout=5000)

        epoch_before = page.evaluate("() => window.__annotationCardsEpoch || 0")

        # Checkpoint server log before tag apply
        server_log.checkpoint()

        select_chars(page, 100, 150)  # noqa: PG003
        highlight_menu = page.locator('[data-testid="highlight-menu"]')
        highlight_menu.wait_for(state="visible", timeout=5000)

        menu_tag_btn = highlight_menu.locator(
            '[data-testid="highlight-menu-tag-btn"]'
        ).first
        menu_tag_btn.click()

        page.wait_for_function(
            f"() => (window.__annotationCardsEpoch || 0) > {epoch_before}",
            timeout=15_000,
        )
        # Trigger positionCards after card rebuild
        page.evaluate("() => {  if (window._positionCards) window._positionCards();}")

        # --- Browser timings ---
        print("\n=== Browser perf (Pabai, tag apply) ===")
        print("--- Page load ---")
        for label, vals in sorted(load_timings.items()):
            if isinstance(vals, list):
                for v in vals:
                    print(f"  {label}: {v:.1f}ms")
            else:
                print(f"  {label}: {vals:.1f}ms")

        print("--- Tag apply ---")
        for label, values in sorted(timings.items()):
            for v in values:
                print(f"  {label}: {v:.1f}ms")

        # --- Server timings ---
        server_entries = server_log.read_since()
        _print_server_timings(server_entries, "tag apply")

        # Verify we got tag-apply pipeline timing
        server_events = {e.get("event") for e in server_entries}
        assert "tag_apply_phase" in server_events, (
            f"H6: tag_apply_phase timing not captured. Got: {server_events}"
        )
