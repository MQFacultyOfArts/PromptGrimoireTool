"""Benchmark DOM performance using real test fixtures.

Compares word-based (current) vs character-based tokenization using:
- BLNS corpus
- 183-austlii.html (legal document with hard spaces)
- All conversations in tests/fixtures/conversations/

Run BEFORE implementation (word-based baseline):
    uv run pytest tests/benchmark/test_dom_performance.py -v -s --headed

Run AFTER implementation (character-based):
    uv run pytest tests/benchmark/test_dom_performance.py -v -s --headed
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from playwright.sync_api import Page

# Fixture paths
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
BLNS_PATH = FIXTURES_DIR / "blns.txt"
AUSTLII_PATH = FIXTURES_DIR / "183-austlii.html"
CONVERSATIONS_DIR = FIXTURES_DIR / "conversations"


def load_blns() -> str:
    """Load BLNS corpus as plain text."""
    return BLNS_PATH.read_text(encoding="utf-8")


def load_austlii() -> str:
    """Load AustLII document, extract text content."""
    from selectolax.lexbor import LexborHTMLParser

    html = AUSTLII_PATH.read_text(encoding="utf-8")
    tree = LexborHTMLParser(html)
    return tree.body.text(separator="\n") if tree.body else html


def load_conversations() -> list[tuple[str, str]]:
    """Load all conversation fixtures.

    Returns list of (filename, content) tuples.
    Handles HTML files (actual format in fixtures/conversations/).
    """
    from selectolax.lexbor import LexborHTMLParser

    conversations = []
    if CONVERSATIONS_DIR.exists():
        for path in sorted(CONVERSATIONS_DIR.glob("*.html")):
            html = path.read_text(encoding="utf-8")
            tree = LexborHTMLParser(html)
            text = tree.body.text(separator="\n") if tree.body else html
            conversations.append((path.name, text))
    return conversations


def setup_workspace_with_content(page: Page, app_server: str, content: str) -> float:
    """Create workspace and measure time to render spans.

    Returns time in milliseconds from submit to first span visible.
    """
    page.goto(f"{app_server}/annotation")
    page.get_by_role("button", name=re.compile("create", re.IGNORECASE)).click()
    page.wait_for_url(re.compile(r"workspace_id="))

    content_input = page.get_by_placeholder(re.compile("paste|content", re.IGNORECASE))
    content_input.fill(content)

    start = time.perf_counter()
    page.get_by_role("button", name=re.compile("add|submit", re.IGNORECASE)).click()

    # Wait for spans (works for both word-index and char-index)
    page.wait_for_selector("[data-word-index], [data-char-index]", timeout=60000)
    render_time = (time.perf_counter() - start) * 1000

    return render_time


def get_dom_metrics(page: Page) -> dict:
    """Get DOM performance metrics."""
    metrics = page.evaluate(
        """
        () => {
            const wordSpans = document.querySelectorAll('[data-word-index]').length;
            const charSpans = document.querySelectorAll('[data-char-index]').length;
            const totalSpans = wordSpans + charSpans;
            const domNodes = document.getElementsByTagName('*').length;

            // Memory (Chrome only)
            const memory = performance.memory?.usedJSHeapSize || 0;

            return {
                word_spans: wordSpans,
                char_spans: charSpans,
                total_spans: totalSpans,
                dom_nodes: domNodes,
                memory_bytes: memory,
            };
        }
    """
    )
    return metrics


def measure_selection_latency(page: Page) -> float:
    """Measure time to select a range of spans."""
    # Detect which attribute is in use
    char_spans = page.locator("[data-char-index]").count()
    attr = "data-char-index" if char_spans > 0 else "data-word-index"

    first = page.locator(f"[{attr}='0']").first
    tenth = page.locator(f"[{attr}='9']").first

    if first.count() == 0 or tenth.count() == 0:
        return 0.0  # Not enough spans

    first.scroll_into_view_if_needed()

    start = time.perf_counter()
    first.click()
    tenth.click(modifiers=["Shift"])
    latency = (time.perf_counter() - start) * 1000

    return latency


def measure_scroll_performance(page: Page) -> float:
    """Measure scroll time."""
    start = time.perf_counter()
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(100)
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(100)
    return (time.perf_counter() - start) * 1000


@pytest.fixture(scope="module")
def benchmark_results() -> list[dict]:
    """Collect results for summary."""
    return []


def _print_result(r: dict) -> None:
    """Print single result."""
    spans = r.get("char_spans") or r.get("word_spans") or r.get("total_spans", 0)
    print(f"\n{'=' * 60}")
    print(f"BENCHMARK: {r['name']}")
    print(f"  Characters: {r['char_count']:,}")
    print(f"  Lines: {r['line_count']:,}")
    print(f"  Spans: {spans:,}")
    print(f"  DOM nodes: {r['dom_nodes']:,}")
    print(f"  Render time: {r['render_time_ms']:.1f}ms")
    print(f"  Selection latency: {r['selection_latency_ms']:.1f}ms")
    print(f"  Scroll time: {r['scroll_time_ms']:.1f}ms")
    if r.get("memory_bytes"):
        print(f"  Memory: {r['memory_bytes'] / (1024 * 1024):.1f}MB")
    print(f"{'=' * 60}")


class TestFixtureBenchmarks:
    """Benchmark using real test fixtures."""

    @pytest.mark.e2e
    def test_blns_corpus(
        self,
        authenticated_page: Page,
        app_server: str,
        benchmark_results: list[dict],
    ) -> None:
        """Benchmark BLNS corpus (stress test for unicode)."""
        content = load_blns()

        render_time = setup_workspace_with_content(
            authenticated_page, app_server, content
        )
        metrics = get_dom_metrics(authenticated_page)
        selection_latency = measure_selection_latency(authenticated_page)
        scroll_time = measure_scroll_performance(authenticated_page)

        result = {
            "name": "BLNS corpus",
            "char_count": len(content),
            "line_count": content.count("\n"),
            **metrics,
            "render_time_ms": render_time,
            "selection_latency_ms": selection_latency,
            "scroll_time_ms": scroll_time,
        }
        benchmark_results.append(result)

        _print_result(result)

    @pytest.mark.e2e
    def test_austlii_183(
        self,
        authenticated_page: Page,
        app_server: str,
        benchmark_results: list[dict],
    ) -> None:
        """Benchmark AustLII legal document (hard spaces, formal text)."""
        content = load_austlii()

        render_time = setup_workspace_with_content(
            authenticated_page, app_server, content
        )
        metrics = get_dom_metrics(authenticated_page)
        selection_latency = measure_selection_latency(authenticated_page)
        scroll_time = measure_scroll_performance(authenticated_page)

        result = {
            "name": "183-austlii (legal)",
            "char_count": len(content),
            "line_count": content.count("\n"),
            **metrics,
            "render_time_ms": render_time,
            "selection_latency_ms": selection_latency,
            "scroll_time_ms": scroll_time,
        }
        benchmark_results.append(result)

        _print_result(result)

    @pytest.mark.e2e
    @pytest.mark.parametrize(
        ("filename", "content"),
        load_conversations() or [pytest.param("skip", "", marks=pytest.mark.skip)],
        ids=lambda x: x if isinstance(x, str) and x.endswith(".html") else None,
    )
    def test_conversation(
        self,
        authenticated_page: Page,
        app_server: str,
        filename: str,
        content: str,
        benchmark_results: list[dict],
    ) -> None:
        """Benchmark each conversation fixture."""
        if not content.strip():
            pytest.skip(f"Empty content for {filename}")

        render_time = setup_workspace_with_content(
            authenticated_page, app_server, content
        )
        metrics = get_dom_metrics(authenticated_page)
        selection_latency = measure_selection_latency(authenticated_page)
        scroll_time = measure_scroll_performance(authenticated_page)

        result = {
            "name": f"conv: {filename}",
            "char_count": len(content),
            "line_count": content.count("\n"),
            **metrics,
            "render_time_ms": render_time,
            "selection_latency_ms": selection_latency,
            "scroll_time_ms": scroll_time,
        }
        benchmark_results.append(result)

        _print_result(result)

    @pytest.mark.e2e
    def test_print_summary(self, benchmark_results: list[dict]) -> None:
        """Print summary and assessment."""
        if not benchmark_results:
            pytest.skip("No results")

        print("\n" + "=" * 100)
        print("BENCHMARK SUMMARY")
        print("=" * 100)

        # Detect mode
        if benchmark_results[0].get("char_spans", 0) > 0:
            mode = "CHARACTER-BASED"
            span_key = "char_spans"
        else:
            mode = "WORD-BASED"
            span_key = "word_spans"

        print(f"Mode: {mode}")
        print()

        header = (
            f"{'Name':<25} {'Chars':<10} {'Spans':<10} {'DOM':<10} "
            f"{'Render':<12} {'Select':<12} {'Scroll':<10}"
        )
        print(header)
        print("-" * 100)

        for r in benchmark_results:
            spans = r.get(span_key) or r.get("total_spans", 0)
            print(
                f"{r['name']:<25} "
                f"{r['char_count']:<10} "
                f"{spans:<10} "
                f"{r['dom_nodes']:<10} "
                f"{r['render_time_ms']:.0f}ms{'':<7} "
                f"{r['selection_latency_ms']:.0f}ms{'':<7} "
                f"{r['scroll_time_ms']:.0f}ms"
            )

        print("=" * 100)

        # Aggregate stats
        total_chars = sum(r["char_count"] for r in benchmark_results)
        total_spans = sum(
            r.get(span_key) or r.get("total_spans", 0) for r in benchmark_results
        )
        max_render = max(r["render_time_ms"] for r in benchmark_results)
        max_select = max(r["selection_latency_ms"] for r in benchmark_results)
        avg_render = sum(r["render_time_ms"] for r in benchmark_results) / len(
            benchmark_results
        )

        print(f"\nTotal characters processed: {total_chars:,}")
        print(f"Total spans created: {total_spans:,}")
        print(f"Average render time: {avg_render:.0f}ms")
        print(f"Max render time: {max_render:.0f}ms")
        print(f"Max selection latency: {max_select:.0f}ms")

        if benchmark_results[0].get("memory_bytes"):
            max_mem = max(r["memory_bytes"] for r in benchmark_results) / (1024 * 1024)
            print(f"Max memory: {max_mem:.1f}MB")

        print()
        if max_render < 5000 and max_select < 500:
            print("STATUS: ACCEPTABLE")
        else:
            print("STATUS: REVIEW NEEDED")
        print("=" * 100)
