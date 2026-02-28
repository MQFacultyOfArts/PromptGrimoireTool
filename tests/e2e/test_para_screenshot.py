"""Screenshot test for paragraph numbering visual verification.

Identifies novel formatting contexts (speaker turns, headings,
lists, thinking blocks) and takes targeted screenshots at each.

Run: uv run test-e2e tests/e2e/test_para_screenshot.py -xvs
Screenshots: tests/e2e/screenshots/cooking_*.png
"""

from __future__ import annotations

import gzip
import re
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator

    from playwright.sync_api import Browser, Page

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "conversations"
SCREENSHOT_DIR = Path(__file__).parent / "screenshots"
SCREENSHOT_DIR.mkdir(exist_ok=True)


def _load_fixture(name: str) -> str:
    path = FIXTURES_DIR / name
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return f.read()
    return path.read_text(encoding="utf-8")


@pytest.fixture
def page_with_paste(browser: Browser, app_server: str) -> Generator[Page]:
    context = browser.new_context(
        permissions=["clipboard-read", "clipboard-write"],
    )
    page = context.new_page()
    page.set_viewport_size({"width": 1280, "height": 900})

    unique_id = uuid4().hex[:8]
    email = f"para-ss-{unique_id}@test.example.edu.au"
    page.goto(f"{app_server}/auth/callback?token=mock-token-{email}")
    page.wait_for_url(
        lambda url: "/auth/callback" not in url,
        timeout=10000,
    )

    page.goto(f"{app_server}/annotation")
    page.get_by_role("button", name=re.compile("create", re.IGNORECASE)).click()
    page.wait_for_url(re.compile(r"workspace_id="))

    yield page

    page.close()
    context.close()


def _paste_and_render(page: Page, html: str) -> None:
    """Paste HTML content and wait for document to render."""
    editor = page.get_by_test_id("content-editor").locator(".q-editor__content")
    editor.click()

    page.evaluate(
        """(html) => {
            const plain = html.replace(/<[^>]*>/g, '');
            return navigator.clipboard.write([
                new ClipboardItem({
                    'text/html': new Blob(
                        [html], { type: 'text/html' }
                    ),
                    'text/plain': new Blob(
                        [plain], { type: 'text/plain' }
                    )
                })
            ]);
        }""",
        html,
    )
    page.wait_for_timeout(100)
    page.keyboard.press("Control+v")
    page.wait_for_timeout(500)

    page.get_by_role("button", name=re.compile("add", re.IGNORECASE)).click()

    page.wait_for_function(
        "() => window._textNodes && window._textNodes.length > 0",
        timeout=15000,
    )
    page.wait_for_timeout(500)


def _find_formatting_landmarks(page: Page) -> list[dict]:
    """Find positions of novel formatting contexts.

    Returns list of {type, y, text} sorted by y position,
    deduplicated so nearby items (within 300px) are merged.
    """
    return page.evaluate("""() => {
        const c = document.getElementById('doc-container');
        if (!c) return [];
        const cRect = c.getBoundingClientRect();
        const landmarks = [];

        // Speaker turn boundaries
        for (const el of c.querySelectorAll(
            '[data-speaker]'
        )) {
            const r = el.getBoundingClientRect();
            const speaker = el.getAttribute('data-speaker');
            const text = el.textContent?.substring(0, 40);
            landmarks.push({
                type: 'speaker-' + speaker,
                y: r.top - cRect.top + c.scrollTop,
                text: text
            });
        }

        // Headings
        for (const el of c.querySelectorAll(
            'h1,h2,h3,h4,h5,h6'
        )) {
            landmarks.push({
                type: 'heading-' + el.tagName.toLowerCase(),
                y: el.getBoundingClientRect().top
                    - cRect.top + c.scrollTop,
                text: el.textContent?.substring(0, 40)
            });
        }

        // Thinking blocks
        for (const el of c.querySelectorAll(
            '[data-thinking]'
        )) {
            landmarks.push({
                type: 'thinking',
                y: el.getBoundingClientRect().top
                    - cRect.top + c.scrollTop,
                text: el.textContent?.substring(0, 40)
            });
        }

        // Lists (first of each type)
        const seenListTypes = new Set();
        for (const el of c.querySelectorAll('ol, ul')) {
            const tag = el.tagName.toLowerCase();
            if (!seenListTypes.has(tag)) {
                seenListTypes.add(tag);
                landmarks.push({
                    type: 'list-' + tag,
                    y: el.getBoundingClientRect().top
                        - cRect.top + c.scrollTop,
                    text: el.textContent?.substring(0, 40)
                });
            }
        }

        // First and last data-para elements
        const paras = c.querySelectorAll('[data-para]');
        if (paras.length > 0) {
            const first = paras[0];
            landmarks.push({
                type: 'first-para',
                y: first.getBoundingClientRect().top
                    - cRect.top + c.scrollTop,
                text: '[' + first.getAttribute('data-para')
                    + '] ' + first.textContent
                        ?.substring(0, 30)
            });
            const last = paras[paras.length - 1];
            landmarks.push({
                type: 'last-para',
                y: last.getBoundingClientRect().top
                    - cRect.top + c.scrollTop,
                text: '[' + last.getAttribute('data-para')
                    + '] ' + last.textContent
                        ?.substring(0, 30)
            });
        }

        // Sort by y, deduplicate within 300px
        landmarks.sort((a, b) => a.y - b.y);
        const deduped = [];
        let lastY = -999;
        for (const lm of landmarks) {
            if (lm.y - lastY > 300) {
                deduped.push(lm);
                lastY = lm.y;
            }
        }
        return deduped;
    }""")


def _clean_screenshots(prefix: str) -> None:
    """Remove screenshots from a previous run of this prefix."""
    for old in SCREENSHOT_DIR.glob(f"{prefix}_*.png"):
        old.unlink()


def _screenshot_at_landmarks(
    page: Page, prefix: str, landmarks: list[dict]
) -> list[str]:
    """Scroll to each landmark and take a screenshot."""
    paths = []

    for i, lm in enumerate(landmarks):
        # scrollIntoView on nearest element to the landmark
        page.evaluate(
            f"""(() => {{
                const c = document.getElementById(
                    'doc-container'
                );
                if (!c) return;
                const els = c.querySelectorAll(
                    '[data-para],[data-speaker],'
                    + 'h1,h2,h3,h4,h5,h6,ol,ul'
                );
                let best = null;
                let bestDist = Infinity;
                const targetY = {lm["y"]};
                for (const el of els) {{
                    const r = el.getBoundingClientRect();
                    const elY = r.top
                        - c.getBoundingClientRect().top
                        + c.scrollTop;
                    const dist = Math.abs(elY - targetY);
                    if (dist < bestDist) {{
                        bestDist = dist;
                        best = el;
                    }}
                }}
                if (best) {{
                    best.scrollIntoView({{
                        block: 'start',
                        behavior: 'instant'
                    }});
                }}
            }})()"""
        )
        page.wait_for_timeout(300)

        label = lm["type"].replace(" ", "_")
        path = str(SCREENSHOT_DIR / f"{prefix}_{i:02d}_{label}.png")
        page.screenshot(path=path)
        paths.append(path)

    return paths


@pytest.mark.e2e
class TestParagraphScreenshots:
    def test_claude_cooking_fixture(self, page_with_paste: Page) -> None:
        """Full cooking conversation — inspect paragraph
        numbers at every novel formatting context."""
        page = page_with_paste
        _clean_screenshots("cooking")
        html = _load_fixture("claude_cooking.html")
        _paste_and_render(page, html)

        # Report all data-para elements
        para_values = page.evaluate("""
            Array.from(
                document.querySelectorAll('[data-para]')
            ).map(el => ({
                tag: el.tagName,
                para: el.getAttribute('data-para'),
                text: el.textContent?.substring(0, 60)
            }))
        """)
        print(f"\ndata-para elements: {len(para_values)}")
        for p in para_values:
            print(f"  [{p['para']:>3s}] <{p['tag']}>: {p['text']}")

        # Find landmarks and take targeted screenshots
        landmarks = _find_formatting_landmarks(page)
        print(f"\nFormatting landmarks: {len(landmarks)}")
        for lm in landmarks:
            print(f"  y={lm['y']:>6.0f}  {lm['type']:<20s}  {lm['text']}")

        paths = _screenshot_at_landmarks(page, "cooking", landmarks)

        assert len(para_values) > 0
        assert len(paths) > 0
