# Character-Based Tokenization Implementation Plan

**Goal:** Replace word-based tokenization with character-based tokenization in the UI, verify performance acceptable

**Architecture:** Each character (including whitespace) gets its own `<span>` with `data-char-index` attribute. Newlines create paragraph breaks but don't get indices. Function returns tuple of (html, char_list).

**Tech Stack:** Python stdlib (html.escape), Playwright for benchmarks, pytest

**Scope:** Phase 1 of 6 from design plan

**Codebase verified:** 2026-02-02

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->

<!-- START_TASK_1 -->
### Task 1: Write failing tests for `_process_text_to_char_spans()`

**Files:**
- Create: `tests/unit/test_char_tokenization.py`

**Step 1: Write the failing tests**

```python
"""Unit tests for character-based tokenization."""

import pytest

from promptgrimoire.pages.annotation import _process_text_to_char_spans


class TestProcessTextToCharSpans:
    """Tests for _process_text_to_char_spans function."""

    def test_empty_string_returns_empty(self) -> None:
        """Empty input returns empty string."""
        result, chars = _process_text_to_char_spans("")
        assert result == ""
        assert chars == []

    def test_single_word_ascii(self) -> None:
        """Single ASCII word creates spans for each character."""
        result, chars = _process_text_to_char_spans("Hello")
        assert chars == ["H", "e", "l", "l", "o"]
        assert 'data-char-index="0"' in result
        assert 'data-char-index="4"' in result
        assert ">H<" in result
        assert ">o<" in result

    def test_whitespace_gets_index(self) -> None:
        """Spaces are indexed as characters."""
        result, chars = _process_text_to_char_spans("a b")
        assert chars == ["a", " ", "b"]
        assert 'data-char-index="0"' in result  # 'a'
        assert 'data-char-index="1"' in result  # ' '
        assert 'data-char-index="2"' in result  # 'b'

    def test_multiple_spaces_preserved(self) -> None:
        """Multiple consecutive spaces each get their own index."""
        result, chars = _process_text_to_char_spans("a  b")
        assert chars == ["a", " ", " ", "b"]
        assert len(chars) == 4

    def test_cjk_characters_split_individually(self) -> None:
        """CJK characters are each a separate unit."""
        result, chars = _process_text_to_char_spans("你好")
        assert chars == ["你", "好"]
        assert 'data-char-index="0"' in result
        assert 'data-char-index="1"' in result
        assert ">你<" in result
        assert ">好<" in result

    def test_mixed_cjk_and_ascii(self) -> None:
        """Mixed CJK and ASCII text tokenizes correctly."""
        result, chars = _process_text_to_char_spans("Hello你好")
        assert chars == ["H", "e", "l", "l", "o", "你", "好"]
        assert len(chars) == 7

    def test_newline_creates_paragraph_break(self) -> None:
        """Newlines create paragraph breaks, chars continue indexing."""
        result, chars = _process_text_to_char_spans("ab\ncd")
        assert chars == ["a", "b", "c", "d"]  # Newline not indexed
        assert "</p>" in result
        assert 'data-para="0"' in result
        assert 'data-para="1"' in result

    def test_empty_line_preserved(self) -> None:
        """Empty lines create paragraphs with nbsp."""
        result, chars = _process_text_to_char_spans("a\n\nb")
        assert "&nbsp;" in result
        assert 'data-para="1"' in result  # Empty line

    def test_html_special_chars_escaped(self) -> None:
        """HTML special characters are escaped."""
        result, chars = _process_text_to_char_spans("<>&")
        assert chars == ["<", ">", "&"]
        assert "&lt;" in result
        assert "&gt;" in result
        assert "&amp;" in result

    def test_non_breaking_space_indexed(self) -> None:
        """Non-breaking space (U+00A0) gets its own index."""
        result, chars = _process_text_to_char_spans("a\u00a0b")
        assert chars == ["a", "\u00a0", "b"]
        assert len(chars) == 3

    def test_class_is_char_not_word(self) -> None:
        """Spans have class='char' not 'word'."""
        result, chars = _process_text_to_char_spans("a")
        assert 'class="char"' in result
        assert 'class="word"' not in result
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/test_char_tokenization.py -v
```

**Expected:** Tests fail with `ImportError: cannot import name '_process_text_to_char_spans'`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Implement `_process_text_to_char_spans()`

**Files:**
- Modify: `src/promptgrimoire/pages/annotation.py` (add after line 238)

**Step 1: Add the new function**

Insert after the existing `_process_text_to_word_spans()` function (after line 238):

```python
def _process_text_to_char_spans(text: str) -> tuple[str, list[str]]:
    """Convert plain text to HTML with character-level spans.

    Each character (including whitespace) gets a span with data-char-index
    attribute for annotation targeting. Newlines create paragraph breaks
    but do not get indices.

    Args:
        text: Plain text to process.

    Returns:
        Tuple of (html_string, char_list) where char_list contains
        all indexed characters in order.
    """
    lines = text.split("\n")
    html_parts: list[str] = []
    chars: list[str] = []
    char_index = 0

    for line_num, line in enumerate(lines):
        if line:  # Non-empty line
            line_spans: list[str] = []
            for char in line:
                escaped = html.escape(char)
                span = (
                    f'<span class="char" data-char-index="{char_index}">'
                    f"{escaped}</span>"
                )
                line_spans.append(span)
                chars.append(char)
                char_index += 1
            html_parts.append(f'<p data-para="{line_num}">{"".join(line_spans)}</p>')
        else:  # Empty line
            html_parts.append(f'<p data-para="{line_num}">&nbsp;</p>')

    return "\n".join(html_parts), chars
```

**Step 2: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_char_tokenization.py -v
```

**Expected:** All tests pass

**Step 3: Commit**

```bash
git add src/promptgrimoire/pages/annotation.py tests/unit/test_char_tokenization.py
git commit -m "$(cat <<'EOF'
feat(annotation): add character-based tokenization function

Add _process_text_to_char_spans() alongside existing word-based function.
- Each character (including whitespace) gets its own index
- CJK text splits by character, not word
- Non-breaking spaces preserved
- Returns tuple of (html, char_list) for state.document_chars

Part of Issue #101: CJK unicode support

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_2 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->

<!-- START_TASK_3 -->
### Task 3: Write Playwright benchmark using real fixtures

**Files:**
- Create: `tests/benchmark/__init__.py`
- Create: `tests/benchmark/conftest.py`
- Create: `tests/benchmark/test_dom_performance.py`

**Step 1: Create benchmark directory structure**

```bash
mkdir -p tests/benchmark
touch tests/benchmark/__init__.py
```

**Step 2: Create conftest.py**

Create `tests/benchmark/conftest.py`:

```python
"""Benchmark test configuration - reuses E2E fixtures."""

# Import E2E fixtures (app_server, fresh_page) by re-exporting from e2e conftest
# This makes the fixtures available in this test directory
from tests.e2e.conftest import app_server, fresh_page  # noqa: F401

# Alternative approach if the above doesn't work:
# pytest_plugins = ["tests.e2e.conftest"]
```

**Note:** Verify the fixture imports work by running a simple test. If imports fail, fall back to the `pytest_plugins` approach.

**Step 3: Create the benchmark test file**

Create `tests/benchmark/test_dom_performance.py`:

```python
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

import json
import re
import time
from pathlib import Path

import pytest
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
    try:
        from bs4 import BeautifulSoup

        html = AUSTLII_PATH.read_text(encoding="utf-8")
        soup = BeautifulSoup(html, "html.parser")
        return soup.get_text(separator="\n")
    except ImportError:
        # Fallback: strip HTML tags with regex
        html = AUSTLII_PATH.read_text(encoding="utf-8")
        text = re.sub(r"<[^>]+>", "", html)
        return text


def load_conversations() -> list[tuple[str, str]]:
    """Load all conversation fixtures.

    Returns list of (filename, content) tuples.
    """
    conversations = []
    if CONVERSATIONS_DIR.exists():
        for path in sorted(CONVERSATIONS_DIR.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            # Extract text from conversation turns
            if isinstance(data, list):
                text = "\n\n".join(
                    turn.get("content", "") for turn in data if isinstance(turn, dict)
                )
            elif isinstance(data, dict) and "messages" in data:
                text = "\n\n".join(
                    msg.get("content", "") for msg in data["messages"]
                )
            else:
                text = str(data)
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

    if char_spans > 0:
        attr = "data-char-index"
    else:
        attr = "data-word-index"

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
    print(f"\n{'='*60}")
    print(f"BENCHMARK: {r['name']}")
    print(f"  Characters: {r['char_count']:,}")
    print(f"  Lines: {r['line_count']:,}")
    print(f"  Spans: {spans:,}")
    print(f"  DOM nodes: {r['dom_nodes']:,}")
    print(f"  Render time: {r['render_time_ms']:.1f}ms")
    print(f"  Selection latency: {r['selection_latency_ms']:.1f}ms")
    print(f"  Scroll time: {r['scroll_time_ms']:.1f}ms")
    if r.get("memory_bytes"):
        print(f"  Memory: {r['memory_bytes'] / (1024*1024):.1f}MB")
    print(f"{'='*60}")


class TestFixtureBenchmarks:
    """Benchmark using real test fixtures."""

    @pytest.mark.e2e
    def test_blns_corpus(
        self,
        fresh_page: Page,
        app_server: str,
        benchmark_results: list[dict],
    ) -> None:
        """Benchmark BLNS corpus (stress test for unicode)."""
        content = load_blns()

        render_time = setup_workspace_with_content(fresh_page, app_server, content)
        metrics = get_dom_metrics(fresh_page)
        selection_latency = measure_selection_latency(fresh_page)
        scroll_time = measure_scroll_performance(fresh_page)

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
        fresh_page: Page,
        app_server: str,
        benchmark_results: list[dict],
    ) -> None:
        """Benchmark AustLII legal document (hard spaces, formal text)."""
        content = load_austlii()

        render_time = setup_workspace_with_content(fresh_page, app_server, content)
        metrics = get_dom_metrics(fresh_page)
        selection_latency = measure_selection_latency(fresh_page)
        scroll_time = measure_scroll_performance(fresh_page)

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
        ids=lambda x: x if isinstance(x, str) and x.endswith(".json") else None,
    )
    def test_conversation(
        self,
        fresh_page: Page,
        app_server: str,
        filename: str,
        content: str,
        benchmark_results: list[dict],
    ) -> None:
        """Benchmark each conversation fixture."""
        if not content.strip():
            pytest.skip(f"Empty content for {filename}")

        render_time = setup_workspace_with_content(fresh_page, app_server, content)
        metrics = get_dom_metrics(fresh_page)
        selection_latency = measure_selection_latency(fresh_page)
        scroll_time = measure_scroll_performance(fresh_page)

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
```

**Step 4: Run BEFORE implementation (word-based baseline)**

```bash
uv run pytest tests/benchmark/test_dom_performance.py -v -s --headed 2>&1 | tee benchmark_word_based.txt
```

**Expected:** Baseline measurements for BLNS, 183-austlii, and all conversations using word-based tokenization.

**Step 5: Commit**

```bash
git add tests/benchmark/
git commit -m "$(cat <<'EOF'
test(benchmark): add Playwright DOM benchmark using real fixtures

Benchmarks actual browser performance on:
- BLNS corpus (unicode stress test)
- 183-austlii.html (legal document with hard spaces)
- All conversations in tests/fixtures/conversations/

Measures: render time, span count, DOM nodes, selection latency, scroll

Designed for before/after comparison of word vs character tokenization.

Part of Issue #101: CJK unicode support

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Add parameterized BLNS tests for tokenization

**Files:**
- Modify: `tests/unit/test_char_tokenization.py`

**Step 1: Add parameterized tests using BLNS fixtures**

Add these imports at the top of `tests/unit/test_char_tokenization.py`:

```python
from tests.conftest import CJK_TEST_CHARS
```

Add this new test class at the end of the file:

```python
class TestCharTokenizationBLNS:
    """Tests using BLNS corpus for edge cases."""

    @pytest.mark.parametrize("char", CJK_TEST_CHARS[:20])  # Sample of CJK chars
    def test_cjk_char_from_blns(self, char: str) -> None:
        """Each CJK character from BLNS is tokenized individually."""
        result, chars = _process_text_to_char_spans(char)
        assert len(chars) == 1
        assert chars[0] == char
        assert 'data-char-index="0"' in result

    def test_rtl_arabic_tokenizes(self) -> None:
        """Arabic RTL text tokenizes character by character."""
        arabic = "مرحبا"
        result, chars = _process_text_to_char_spans(arabic)
        assert len(chars) == 5
        assert all(c in chars for c in arabic)

    def test_rtl_hebrew_tokenizes(self) -> None:
        """Hebrew RTL text tokenizes character by character."""
        hebrew = "שלום"
        result, chars = _process_text_to_char_spans(hebrew)
        assert len(chars) == 4

    def test_emoji_split_by_codepoint(self) -> None:
        """Emoji are split by Unicode code point (acceptable for MVP)."""
        result, chars = _process_text_to_char_spans("😀")
        assert len(chars) == 1

    def test_ideographic_space_indexed(self) -> None:
        """Ideographic space (U+3000) is indexed."""
        result, chars = _process_text_to_char_spans("a\u3000b")
        assert chars == ["a", "\u3000", "b"]

    def test_zero_width_joiner_indexed(self) -> None:
        """Zero-width joiner (U+200D) is indexed as a character."""
        result, chars = _process_text_to_char_spans("a\u200db")
        assert chars == ["a", "\u200d", "b"]

    def test_control_chars_indexed(self) -> None:
        """Control characters are indexed but may render invisibly."""
        result, chars = _process_text_to_char_spans("a\tb")
        assert chars == ["a", "\t", "b"]
```

**Step 2: Run the extended tests**

```bash
uv run pytest tests/unit/test_char_tokenization.py -v
```

**Expected:** All tests pass

**Step 3: Commit**

```bash
git add tests/unit/test_char_tokenization.py
git commit -m "$(cat <<'EOF'
test(tokenization): add BLNS parameterized tests for character tokenization

Tests cover:
- CJK characters from BLNS corpus
- RTL text (Arabic, Hebrew)
- Emoji (single codepoint)
- Ideographic space (U+3000)
- Zero-width joiner
- Control characters (tab)

Part of Issue #101: CJK unicode support

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_4 -->

<!-- END_SUBCOMPONENT_B -->

---

## Phase 1 UAT Steps

1. [ ] Run all Phase 1 unit tests: `uv run pytest tests/unit/test_char_tokenization.py -v`
2. [ ] Run word-based benchmark (baseline): `uv run pytest tests/benchmark/test_dom_performance.py -v -s --headed 2>&1 | tee benchmark_word_based.txt`
3. [ ] Verify benchmark completes and shows "WORD-BASED" mode
4. [ ] Review span counts and render times for each fixture
5. [ ] Assess: Is current word-based performance acceptable?

## Evidence Required

- [ ] All unit tests passing
- [ ] Benchmark baseline output saved to `benchmark_word_based.txt`
- [ ] Benchmark shows STATUS: ACCEPTABLE (or document concerns)
