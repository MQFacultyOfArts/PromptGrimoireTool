# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "nicegui>=3.6.1",
#   "pytest",
#   "pytest-playwright",
# ]
# ///
"""Automated Playwright test for NiceGUI char-span preservation.

Launches repro.py in a thread (matching NiceGUI's own test pattern),
injects char spans via JS, clicks the toggle button,
and verifies the styled spans survive the server-side update.
Captures before/after screenshots to output/repro_screenshots/.

Requires repro.py in the same directory.
Requires: playwright install chromium  (one-time browser setup)

Usage (standalone):
    uv run test_repro.py                                              # latest
    uv run --with nicegui==3.6.1 test_repro.py                       # baseline
    uv run --with nicegui==3.7.1 test_repro.py                       # regression
    uv run --with 'nicegui @ git+https://...@branch' test_repro.py   # PR branch
"""

from __future__ import annotations

import os
import re
import runpy
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import FloatRect

if TYPE_CHECKING:
    from playwright.sync_api import Page

SCREENSHOT_DIR = Path(__file__).parent / "output" / "repro_screenshots"
WORKTREE = Path(__file__).parent


def _wait_for_server(url: str, timeout: float = 15) -> None:
    """Poll until the server responds or timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return
        except Exception:
            time.sleep(0.5)
    msg = f"Server at {url} did not start within {timeout}s"
    raise TimeoutError(msg)


@pytest.fixture(scope="module")
def repro_server():
    """Start repro.py in a thread (NiceGUI's own test pattern)."""
    os.environ["NICEGUI_SCREEN_TEST_PORT"] = "8090"
    thread = threading.Thread(
        target=lambda: runpy.run_path(str(WORKTREE / "repro.py"), run_name="__main__"),
        daemon=True,
    )
    thread.start()
    _wait_for_server("http://localhost:8090/")
    yield thread
    # Server shuts down when the daemon thread is collected


def _version_slug(version_text: str) -> str:
    """Turn 'NiceGUI 3.6.1' into a filename-safe slug."""
    return re.sub(r"[^a-zA-Z0-9._-]", "_", version_text).strip("_")


def test_char_spans_survive_server_update(
    repro_server: threading.Thread,  # noqa: ARG001
    page: Page,
) -> None:
    """After JS injects char spans, a server-side toggle must not destroy them."""
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    page.goto("http://localhost:8090/")

    # Wait for the JS injection to complete
    page.wait_for_selector('[data-char-index="0"]', timeout=10_000)

    # Read the version label from the page for screenshot naming
    version_el = page.locator(".text-h5").first
    version_text = version_el.inner_text()
    slug = _version_slug(version_text)

    # Count styled spans before clicking
    before = page.locator("#target span[data-char-index]").count()
    assert before > 0, "JS injection didn't create any char spans"

    # Clip to just the content area (version label through button)
    clip = FloatRect(x=0, y=0, width=1280, height=280)

    # Screenshot: before click
    page.screenshot(
        path=str(SCREENSHOT_DIR / f"{slug}_1_before_click.png"),
        clip=clip,
    )

    # Click the toggle button (triggers server-side update)
    page.get_by_role("button", name="Toggle").click()
    page.wait_for_timeout(1000)

    # Screenshot: after click
    page.screenshot(
        path=str(SCREENSHOT_DIR / f"{slug}_2_after_click.png"),
        clip=clip,
    )

    # Count styled spans after clicking
    after = page.locator("#target span[data-char-index]").count()

    print(f"\n{'=' * 60}")
    print(f"Version: {version_text}")
    print(f"Char spans before click: {before}")
    print(f"Char spans after click:  {after}")

    # The critical assertion: spans must survive
    if after == before:
        # Also check styling preserved
        first_span = page.locator('[data-char-index="0"]')
        bg = first_span.evaluate("el => getComputedStyle(el).backgroundColor")
        print(f"Background colour: {bg}")
        print("RESULT: PASS")
        print(f"{'=' * 60}")
    else:
        print("RESULT: FAIL -- spans destroyed")
        print(f"{'=' * 60}")
        pytest.fail(
            f"Server update destroyed char spans: {before} before, {after} after"
        )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s"]))
