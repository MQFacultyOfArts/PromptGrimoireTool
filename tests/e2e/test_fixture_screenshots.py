"""E2E test to generate screenshots of all HTML fixtures.

This test renders each HTML fixture through the annotation page pipeline
and captures multiple screenshots at interesting scroll positions (tables,
headings, speaker transitions, etc.) for visual QA review.

Screenshots are saved to output/fixture_screenshots/ for evaluation by
the ralph-loop visual QA process (docs/wip/ralph-fixture-presentation.md).

Each fixture test clears its own stale screenshots (e.g. austlii_*.png) before
regenerating, preventing stale files from previous runs accumulating.

Run with: uv run pytest tests/e2e/test_fixture_screenshots.py -v
Run single fixture: uv run pytest tests/e2e/test_fixture_screenshots.py -v -k austlii

Traceability:
- Issue: #106 HTML input pipeline
- Design: docs/design-plans/2026-02-04-html-input-pipeline-106.md
"""

from __future__ import annotations

import gzip
import re
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

if TYPE_CHECKING:
    from collections.abc import Generator

    from playwright.sync_api import Browser, Page

# Directories
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "conversations"
OUTPUT_DIR = Path(__file__).parent.parent.parent / "output" / "fixture_screenshots"

# Ensure output directory exists
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

FIXTURE_FILES = [
    # Uncompressed HTML files
    ("austlii.html", False),
    ("chinese_wikipedia.html", False),
    ("claude_cooking.html", False),
    ("claude_maths.html", False),
    ("translation_japanese_sample.html", False),
    ("translation_korean_sample.html", False),
    ("translation_spanish_sample.html", False),
    # Gzipped chatbot exports - OpenAI
    ("openai_biblatex.html.gz", True),
    ("openai_dh_dr.html.gz", True),
    ("openai_dprk_denmark.html.gz", True),
    ("openai_software_long_dr.html.gz", True),
    # Gzipped chatbot exports - Google
    ("google_aistudio_image.html.gz", True),
    ("google_aistudio_ux_discussion.html.gz", True),
    ("google_gemini_debug.html.gz", True),
    ("google_gemini_deep_research.html.gz", True),
    # Gzipped chatbot exports - ScienceOS
    ("scienceos_loc.html.gz", True),
    ("scienceos_philsci.html.gz", True),
]

# CSS selectors for interesting elements to screenshot
LANDMARK_SELECTORS = [
    "table",  # Tables
    "pre",  # Code blocks
    "code",  # Inline code (may indicate code-heavy section)
    "ol",  # Ordered lists
    "ul",  # Unordered lists
    "h1",  # Headings
    "h2",
    "h3",
    "blockquote",  # Quotes
]


def _get_landmark_positions(page: Page) -> list[tuple[str, int]]:
    """Find Y positions of landmark elements for screenshot targeting.

    Returns list of (landmark_type, y_position) tuples, sorted by Y.
    """
    landmarks: list[tuple[str, int]] = []

    for selector in LANDMARK_SELECTORS:
        elements = page.locator(f".doc-container {selector}").all()
        for i, el in enumerate(elements[:3]):  # Max 3 per type
            try:
                box = el.bounding_box()
                if box:
                    landmarks.append((f"{selector}{i}", int(box["y"])))
            except Exception:
                continue  # Element may have disappeared

    # Also look for speaker labels
    speaker_labels = page.locator(".doc-container strong").all()
    for i, el in enumerate(speaker_labels[:5]):
        try:
            text = el.text_content() or ""
            if any(
                word in text.lower()
                for word in ["user", "assistant", "human", "ai", "claude"]
            ):
                box = el.bounding_box()
                if box:
                    landmarks.append((f"speaker{i}", int(box["y"])))
        except Exception:
            continue

    # Sort by Y position and deduplicate nearby positions
    landmarks.sort(key=lambda x: x[1])
    return landmarks


def _cluster_positions(
    landmarks: list[tuple[str, int]], viewport_height: int
) -> list[tuple[str, int]]:
    """Cluster nearby landmarks, picking representative positions.

    Returns positions spaced at least viewport_height/2 apart.
    """
    if not landmarks:
        return []

    min_gap = viewport_height // 2
    clusters: list[tuple[str, int]] = []

    for name, y in landmarks:
        if not clusters or (y - clusters[-1][1]) >= min_gap:
            clusters.append((name, y))

    return clusters[:5]  # Cap at 5 screenshots


@pytest.fixture
def fixture_page(browser: Browser, app_server: str) -> Generator[Page]:
    """Authenticated page with clipboard permission for fixture loading."""
    from uuid import uuid4

    context = browser.new_context(
        permissions=["clipboard-read", "clipboard-write"],
        viewport={"width": 1280, "height": 900},
    )
    page = context.new_page()

    # Authenticate
    unique_id = uuid4().hex[:8]
    email = f"fixture-screenshot-{unique_id}@test.example.edu.au"
    page.goto(f"{app_server}/auth/callback?token=mock-token-{email}")
    page.wait_for_url(lambda url: "/auth/callback" not in url, timeout=10000)

    yield page

    page.close()
    context.close()


def _load_fixture_via_paste(page: Page, app_server: str, html_content: str) -> None:
    """Load HTML content into annotation page via paste flow."""
    # Navigate and create workspace
    page.goto(f"{app_server}/annotation")
    page.get_by_role("button", name=re.compile("create", re.IGNORECASE)).click()
    page.wait_for_url(re.compile(r"workspace_id="))

    # Focus editor
    editor = page.locator(".q-editor__content")
    expect(editor).to_be_visible(timeout=5000)
    editor.click()

    # Write HTML to clipboard
    page.evaluate(
        """(html) => {
            const plainText = html.replace(/<[^>]*>/g, '');
            return navigator.clipboard.write([
                new ClipboardItem({
                    'text/html': new Blob([html], { type: 'text/html' }),
                    'text/plain': new Blob([plainText], { type: 'text/plain' })
                })
            ]);
        }""",
        html_content,
    )
    page.wait_for_timeout(100)

    # Paste
    page.keyboard.press("Control+v")
    page.wait_for_timeout(500)

    # Check platform hint before submitting
    platform_hint = page.evaluate("""() => {
        for (const k of Object.keys(window)) {
            if (k.startsWith('_platformHint_'))
                return window[k];
        }
        return null;
    }""")
    print(f"\n  [DEBUG] Platform hint: {platform_hint}")

    # Submit
    page.get_by_role("button", name=re.compile("add", re.IGNORECASE)).click()

    # Wait for document to render
    page.locator("[data-char-index]").first.wait_for(state="attached", timeout=30000)
    page.wait_for_timeout(500)  # Let rendering stabilize

    # Check for data-speaker in rendered DOM
    speaker_count = page.evaluate("""() => {
        return document.querySelectorAll('[data-speaker]').length;
    }""")
    print(f"  [DEBUG] data-speaker elements in DOM: {speaker_count}")


def _capture_fixture_screenshots(
    page: Page, fixture_name: str, viewport_height: int
) -> list[str]:
    """Capture screenshots at multiple scroll positions.

    Returns list of screenshot paths created.
    """
    screenshots: list[str] = []

    # Always capture top of document
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(200)
    path = OUTPUT_DIR / f"{fixture_name}_001_top.png"
    page.screenshot(path=str(path))
    screenshots.append(str(path))

    # Get document container for scroll measurements
    doc_container = page.locator(".doc-container")
    container_box = doc_container.bounding_box()

    if not container_box:
        return screenshots

    # Get total scrollable height
    doc_height = page.evaluate(
        "document.querySelector('.doc-container')?.scrollHeight || 0"
    )

    # Get landmark positions
    landmarks = _get_landmark_positions(page)
    positions = _cluster_positions(landmarks, viewport_height)

    # If no landmarks found but document is tall, add fallback positions
    if not positions and doc_height > viewport_height:
        # Add middle and bottom positions for tall documents without landmarks
        if doc_height > viewport_height * 2:
            positions.append(("middle", doc_height // 2))
        positions.append(("bottom", doc_height - viewport_height))

    # Capture at each position
    for i, (landmark_name, y_pos) in enumerate(positions, start=2):
        # Scroll so landmark is near top of viewport
        scroll_y = max(0, y_pos - 100)
        page.evaluate(f"window.scrollTo(0, {scroll_y})")
        page.wait_for_timeout(200)

        path = OUTPUT_DIR / f"{fixture_name}_{i:03d}_{landmark_name}.png"
        page.screenshot(path=str(path))
        screenshots.append(str(path))

    return screenshots


@pytest.mark.skip(reason="Flaky E2E infrastructure timeout — #120")
class TestFixtureScreenshots:
    """Generate screenshots for all HTML fixtures."""

    @pytest.mark.parametrize("fixture_entry", FIXTURE_FILES)
    def test_capture_fixture_screenshots(
        self,
        fixture_page: Page,
        app_server: str,
        fixture_entry: tuple[str, bool],
    ) -> None:
        """Load fixture and capture screenshots at interesting positions.

        This test always passes - it generates screenshots for visual review.
        """
        fixture_file, is_gzipped = fixture_entry
        fixture_path = FIXTURES_DIR / fixture_file
        if not fixture_path.exists():
            pytest.skip(f"Fixture not found: {fixture_path}")

        if is_gzipped:
            with gzip.open(fixture_path, "rt", encoding="utf-8") as f:
                html_content = f.read()
            fixture_name = fixture_file.replace(".html.gz", "")
        else:
            html_content = fixture_path.read_text(encoding="utf-8")
            fixture_name = fixture_file.replace(".html", "")

        # Clear stale screenshots for THIS fixture before regenerating
        for stale in OUTPUT_DIR.glob(f"{fixture_name}_*.png"):
            stale.unlink(missing_ok=True)

        # Load via paste flow
        _load_fixture_via_paste(fixture_page, app_server, html_content)

        # Capture screenshots
        viewport_height = 900  # From context viewport setting
        screenshots = _capture_fixture_screenshots(
            fixture_page, fixture_name, viewport_height
        )

        # Report what was captured (visible in pytest output)
        print(f"\nCaptured {len(screenshots)} screenshots for {fixture_name}:")
        for path in screenshots:
            print(f"  - {Path(path).name}")
