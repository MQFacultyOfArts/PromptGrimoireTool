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
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from playwright.sync_api import ConsoleMessage, expect

from promptgrimoire.config import get_settings
from promptgrimoire.docs.helpers import select_chars

if TYPE_CHECKING:
    from collections.abc import Generator

    from playwright.sync_api import Browser, Page

PABAI_WORKSPACE_ID = "0e5e9b04-de94-4728-a8c9-e625c141fea3"
_WORKSPACE_JSON = Path(__file__).parent / "fixtures" / "pabai_workspace.json"

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


@pytest.fixture(scope="session")
def pabai_workspace() -> str:
    """Ensure the Pabai workspace is rehydrated into the test DB.

    Session-scoped: runs once, rehydrates from JSON extraction if
    the workspace is missing. Skips if the JSON file doesn't exist.

    Returns the workspace ID.
    """
    import psycopg

    if not _WORKSPACE_JSON.exists():
        pytest.skip(
            f"Workspace JSON not found at {_WORKSPACE_JSON}. "
            "Extract from prod or dev DB first."
        )

    conninfo = _test_db_conninfo()

    # Check if already present
    with psycopg.connect(conninfo) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM workspace WHERE id = %s::uuid",
            (PABAI_WORKSPACE_ID,),
        )
        if cur.fetchone() is not None:
            return PABAI_WORKSPACE_ID

    # Rehydrate
    from scripts.rehydrate_workspace import rehydrate

    result = rehydrate(_WORKSPACE_JSON, conninfo)
    assert result["workspace_id"] == PABAI_WORKSPACE_ID
    return PABAI_WORKSPACE_ID


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
    conninfo = _test_db_conninfo()
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

        ws_url = f"{app_server}/annotation?workspace_id={PABAI_WORKSPACE_ID}"
        page.goto(ws_url)

        page.wait_for_function(
            "() => document.querySelector('[data-testid=\"doc-container\"]')"
            " && window._textNodes && window._textNodes.length > 0"
            " && window._highlightsReady === true",
            timeout=60_000,
        )

        # Wait for positionCards to set style.top on sidebar cards
        page.wait_for_function(
            "() => {"
            "  const sb = '#annotations-container';"
            "  const c = document.querySelector("
            "    sb + ' [data-start-char]');"
            "  return c && c.style.top !== '';"
            "}",
            timeout=10_000,
        )

        # --- Browser timings ---
        print("\n=== Browser perf (Pabai, page load) ===")
        for label, ms in sorted(timings.items()):
            print(f"  {label}: {ms:.1f}ms")

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
        page.goto(ws_url)
        page.wait_for_function(
            "() => window._highlightsReady === true",
            timeout=60_000,
        )
        # Wait for positionCards to complete (cards get style.top)
        page.wait_for_function(
            "() => {"
            "  const sb = '#annotations-container';"
            "  const c = document.querySelector("
            "    sb + ' [data-start-char]');"
            "  return c && c.style.top !== '';"
            "}",
            timeout=10_000,
        )

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
        # Wait for positionCards to reposition after card rebuild
        page.wait_for_function(
            "() => {"
            "  const sb = '#annotations-container';"
            "  const c = document.querySelector("
            "    sb + ' [data-start-char]');"
            "  return c && c.style.top !== '';"
            "}",
            timeout=10_000,
        )

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
