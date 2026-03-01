"""Screenshot test for paragraph numbering visual verification.

Parametrised over all conversation fixtures. Identifies novel
formatting contexts (speaker turns, headings, lists, blockquotes,
tables, code blocks, thinking blocks) and takes targeted screenshots.

Run all:   uv run test-e2e tests/e2e/test_para_screenshot.py -xvs
Run one:   uv run test-e2e tests/e2e/test_para_screenshot.py -xvs -k cooking

Screenshots: tests/e2e/screenshots/<prefix>_*.png
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

# All conversation fixtures to test, with short prefix for filenames.
# Excludes 183-clipboard (test artifact) and .gz duplicates of .html files.
_ALL_FIXTURES: list[tuple[str, str]] = [
    ("austlii", "austlii.html"),
    ("chatcraft_prd", "chatcraft_prd.html.gz"),
    ("chinese_wikipedia", "chinese_wikipedia.html"),
    ("claude_cooking", "claude_cooking.html"),
    ("claude_maths", "claude_maths.html"),
    ("google_gemini_debug", "google_gemini_debug.html.gz"),
    ("google_gemini_deep_research", "google_gemini_deep_research.html.gz"),
    ("lawlis_v_r_austlii", "lawlis_v_r_austlii.html"),
    ("openai_biblatex", "openai_biblatex.html.gz"),
    ("openai_dh_dr", "openai_dh_dr.html.gz"),
    ("openai_dprk_denmark", "openai_dprk_denmark.html.gz"),
    ("openai_software_long_dr", "openai_software_long_dr.html.gz"),
    ("openrouter_fizzbuzz", "openrouter_fizzbuzz.html.gz"),
    ("scienceos_loc", "scienceos_loc.html.gz"),
    ("scienceos_philsci", "scienceos_philsci.html.gz"),
    ("translation_japanese", "translation_japanese_sample.html"),
    ("translation_korean", "translation_korean_sample.html"),
    ("translation_spanish", "translation_spanish_sample.html"),
    ("wikisource_quijote", "wikisource_es_don_quijote.html.gz"),
]


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


# JS function that detects all novel formatting contexts in the
# rendered document and returns their positions for screenshotting.
_LANDMARK_JS = """() => {
    const c = document.getElementById('doc-container');
    if (!c) return [];
    const cRect = c.getBoundingClientRect();
    const landmarks = [];

    function yOf(el) {
        return el.getBoundingClientRect().top
            - cRect.top + c.scrollTop;
    }

    // Speaker turn boundaries
    for (const el of c.querySelectorAll('[data-speaker]')) {
        const speaker = el.getAttribute('data-speaker');
        landmarks.push({
            type: 'speaker-' + speaker,
            y: yOf(el),
            text: el.textContent?.substring(0, 40)
        });
    }

    // Headings
    for (const el of c.querySelectorAll('h1,h2,h3,h4,h5,h6')) {
        landmarks.push({
            type: 'heading-' + el.tagName.toLowerCase(),
            y: yOf(el),
            text: el.textContent?.substring(0, 40)
        });
    }

    // Thinking blocks
    for (const el of c.querySelectorAll('[data-thinking]')) {
        landmarks.push({
            type: 'thinking',
            y: yOf(el),
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
                y: yOf(el),
                text: el.textContent?.substring(0, 40)
            });
        }
    }

    // Blockquotes (first only)
    const bq = c.querySelector('blockquote');
    if (bq) {
        landmarks.push({
            type: 'blockquote',
            y: yOf(bq),
            text: bq.textContent?.substring(0, 40)
        });
    }

    // Tables (first only)
    const tbl = c.querySelector('table');
    if (tbl) {
        landmarks.push({
            type: 'table',
            y: yOf(tbl),
            text: tbl.textContent?.substring(0, 40)
        });
    }

    // Code blocks (first <pre> only)
    const pre = c.querySelector('pre');
    if (pre) {
        landmarks.push({
            type: 'code-block',
            y: yOf(pre),
            text: pre.textContent?.substring(0, 40)
        });
    }

    // First and last data-para elements
    const paras = c.querySelectorAll('[data-para]');
    if (paras.length > 0) {
        const first = paras[0];
        landmarks.push({
            type: 'first-para',
            y: yOf(first),
            text: '[' + first.getAttribute('data-para')
                + '] ' + first.textContent?.substring(0, 30)
        });
        const last = paras[paras.length - 1];
        landmarks.push({
            type: 'last-para',
            y: yOf(last),
            text: '[' + last.getAttribute('data-para')
                + '] ' + last.textContent?.substring(0, 30)
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
}"""


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
        page.evaluate(
            f"""(() => {{
                const c = document.getElementById('doc-container');
                if (!c) return;
                const els = c.querySelectorAll(
                    '[data-para],[data-speaker],'
                    + 'h1,h2,h3,h4,h5,h6,ol,ul,'
                    + 'blockquote,table,pre'
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
    @pytest.mark.parametrize(
        ("prefix", "fixture_file"),
        _ALL_FIXTURES,
        ids=[f[0] for f in _ALL_FIXTURES],
    )
    def test_fixture_screenshots(
        self,
        page_with_paste: Page,
        prefix: str,
        fixture_file: str,
    ) -> None:
        """Paste fixture, detect landmarks, take screenshots."""
        page = page_with_paste
        _clean_screenshots(prefix)
        html = _load_fixture(fixture_file)
        _paste_and_render(page, html)

        # Report data-para elements
        para_values = page.evaluate("""
            Array.from(
                document.querySelectorAll('[data-para]')
            ).map(el => ({
                tag: el.tagName,
                para: el.getAttribute('data-para'),
                text: el.textContent?.substring(0, 60)
            }))
        """)
        print(f"\n=== {prefix} ({fixture_file}) ===")
        print(f"data-para elements: {len(para_values)}")
        for p in para_values:
            print(f"  [{p['para']:>3s}] <{p['tag']}>: {p['text']}")

        # Find landmarks and take screenshots
        landmarks: list[dict] = page.evaluate(_LANDMARK_JS)
        print(f"\nFormatting landmarks: {len(landmarks)}")
        for lm in landmarks:
            print(f"  y={lm['y']:>6.0f}  {lm['type']:<20s}  {lm['text']}")

        paths = _screenshot_at_landmarks(page, prefix, landmarks)

        assert len(para_values) > 0, f"No data-para elements in {fixture_file}"
        assert len(paths) > 0, f"No landmarks found in {fixture_file}"
