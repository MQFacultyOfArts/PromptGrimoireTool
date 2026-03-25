#!/usr/bin/env python3
"""Profile annotation page load and interaction latency with Playwright.

Measures both browser Performance API metrics (navigation timing, FCP, LCP)
and application-level readiness (text walker initialisation, card epoch).
Outputs structured JSON for repeatable baseline comparison.

Requires:
  - A running PromptGrimoire server with DEV__AUTH_MOCK=true
  - The target workspace rehydrated into the database
  - Playwright browsers installed (playwright install chromium)

Usage:
    # Page load profiling (5 iterations)
    uv run scripts/profile_workspace.py \\
        --url http://localhost:8080 \\
        --workspace-id 0e5e9b04-de94-4728-a8c9-e625c141fea3

    # With interaction latency measurement
    uv run scripts/profile_workspace.py \\
        --url http://localhost:8080 \\
        --workspace-id 0e5e9b04-de94-4728-a8c9-e625c141fea3 \\
        --interactions

    # More iterations, save to file
    uv run scripts/profile_workspace.py \\
        --url http://localhost:8080 \\
        --workspace-id 0e5e9b04-de94-4728-a8c9-e625c141fea3 \\
        --iterations 10 \\
        --output results.json
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import typer
from playwright.sync_api import Page, sync_playwright

from promptgrimoire.docs.helpers import select_chars

app = typer.Typer(help="Profile annotation page load and interaction latency.")

# JavaScript to inject before navigation that sets up LCP observation.
# LCP is reported asynchronously via PerformanceObserver -- we stash
# entries on window so we can read them after page load stabilises.
_LCP_OBSERVER_SCRIPT = """
window.__lcpEntries = [];
const lcpObs = new PerformanceObserver((list) => {
    for (const entry of list.getEntries()) {
        window.__lcpEntries.push({
            startTime: entry.startTime,
            size: entry.size,
            element: entry.element ? entry.element.tagName : null,
        });
    }
});
lcpObs.observe({ type: 'largest-contentful-paint', buffered: true });
"""

# JavaScript to collect all performance metrics after page load.
_COLLECT_METRICS_JS = """
() => {
    const nav = performance.getEntriesByType('navigation')[0] || {};
    const paints = performance.getEntriesByType('paint');
    const fcp = paints.find(p => p.name === 'first-contentful-paint');
    const fp = paints.find(p => p.name === 'first-paint');
    const lcp = window.__lcpEntries || [];
    const lastLcp = lcp.length > 0 ? lcp[lcp.length - 1] : null;

    return {
        navigation: {
            // Server response time
            responseEnd: nav.responseEnd || null,
            requestStart: nav.requestStart || null,
            serverResponseMs: nav.responseEnd && nav.requestStart
                ? Math.round(nav.responseEnd - nav.requestStart) : null,
            // DOM processing
            domContentLoadedMs: nav.domContentLoadedEventEnd
                ? Math.round(nav.domContentLoadedEventEnd - nav.startTime) : null,
            domInteractiveMs: nav.domInteractive
                ? Math.round(nav.domInteractive - nav.startTime) : null,
            // Full load
            loadEventMs: nav.loadEventEnd
                ? Math.round(nav.loadEventEnd - nav.startTime) : null,
            // Transfer size
            transferSizeBytes: nav.transferSize || null,
            encodedBodySizeBytes: nav.encodedBodySize || null,
            decodedBodySizeBytes: nav.decodedBodySize || null,
        },
        paint: {
            firstPaintMs: fp ? Math.round(fp.startTime) : null,
            firstContentfulPaintMs: fcp ? Math.round(fcp.startTime) : null,
        },
        lcp: lastLcp ? {
            startTimeMs: Math.round(lastLcp.startTime),
            size: lastLcp.size,
            element: lastLcp.element,
        } : null,
        resourceCount: performance.getEntriesByType('resource').length,
    };
}
"""


def _authenticate(
    page: Page,
    server_url: str,
    *,
    email: str = "instructor@uni.edu",
) -> str:
    """Authenticate via mock magic link.

    Defaults to the seed instructor who should already have
    owner ACL on the workspace (via ``rehydrate_workspace.py --owner``).

    Returns the email used.
    """
    page.goto(f"{server_url}/auth/callback?token=mock-token-{email}")
    page.wait_for_url(lambda url: "/auth/callback" not in url, timeout=10_000)
    return email


def _wait_for_text_walker(page: Page, timeout: int = 30_000) -> None:
    """Wait for text walker initialisation (readiness gate)."""
    page.wait_for_function(
        "() => document.getElementById('doc-container')"
        " && window._textNodes && window._textNodes.length > 0",
        timeout=timeout,
    )


def _measure_page_load(
    page: Page,
    workspace_url: str,
    *,
    iteration: int,
) -> dict[str, Any]:
    """Load the workspace page and collect all metrics.

    Returns a dict with timing data for one iteration.
    """
    # Inject LCP observer before navigation
    page.add_init_script(_LCP_OBSERVER_SCRIPT)

    t_start = time.perf_counter()
    page.goto(workspace_url)

    # Wait for DOM content loaded (NiceGUI SSR)
    page.wait_for_load_state("domcontentloaded")
    t_dom = time.perf_counter()

    # Wait for network idle (all resources loaded)
    page.wait_for_load_state("networkidle")
    t_network = time.perf_counter()

    # Wait for application readiness (text walker)
    try:
        _wait_for_text_walker(page, timeout=60_000)
        t_ready = time.perf_counter()
        walker_ready = True
    except Exception:
        t_ready = time.perf_counter()
        walker_ready = False

    # Small delay to let LCP observer fire
    page.wait_for_timeout(500)

    # Collect browser performance metrics
    browser_metrics = page.evaluate(_COLLECT_METRICS_JS)

    # Get document stats from the DOM
    doc_stats = page.evaluate(
        """() => {
            const container = document.getElementById('doc-container');
            return {
                docContainerExists: !!container,
                docContainerHtml: container
                    ? container.innerHTML.length : 0,
                textNodeCount: window._textNodes
                    ? window._textNodes.length : 0,
                highlightCount: container
                    ? container.querySelectorAll(
                        '[data-highlight-id]'
                      ).length : 0,
            };
        }"""
    )

    return {
        "iteration": iteration,
        "walkerReady": walker_ready,
        "timing": {
            "wallClockTotalMs": round((t_ready - t_start) * 1000),
            "wallClockDomMs": round((t_dom - t_start) * 1000),
            "wallClockNetworkMs": round((t_network - t_start) * 1000),
            "wallClockWalkerMs": round((t_ready - t_network) * 1000),
        },
        "browser": browser_metrics,
        "document": doc_stats,
    }


def _measure_interactions(
    page: Page,
    *,
    iteration: int,
) -> dict[str, Any]:
    """Measure tag interaction latency on the loaded page.

    Measures:
      1. Text selection to highlight menu appearance
      2. Tag toolbar button click to card rebuild (epoch advance)

    Returns timing dict for one iteration.
    """
    results: dict[str, Any] = {"iteration": iteration}

    # Ensure we're on the Annotate tab
    manage_btn = page.get_by_test_id("tab-annotate")
    if manage_btn.is_visible():
        manage_btn.click()
        page.wait_for_timeout(200)

    # Find tag toolbar
    tag_toolbar = page.get_by_test_id("tag-toolbar")
    if not tag_toolbar.is_visible(timeout=2000):
        results["error"] = "tag-toolbar not visible"
        return results

    # Count existing tag buttons
    tag_buttons = page.locator('[data-testid^="tag-btn-"]')
    tag_button_count = tag_buttons.count()
    results["tagButtonCount"] = tag_button_count

    # Check text nodes available
    text_nodes_count = page.evaluate(
        "() => window._textNodes ? window._textNodes.length : 0"
    )
    if text_nodes_count < 10:
        results["error"] = "not enough text nodes"
        return results

    # Select text and measure highlight menu appearance
    t0 = time.perf_counter()
    select_chars(page, 100, 150)

    # Diagnostic: check if selection actually exists
    sel_text = page.evaluate("() => window.getSelection().toString().substring(0, 80)")
    results["selectionText"] = sel_text
    results["selectionLength"] = len(sel_text)
    results["selectionBound"] = page.evaluate("() => !!window._annotSelectionBound")

    try:
        # Wait for the highlight-menu container (not just the
        # tag button inside it)
        highlight_menu = page.locator('[data-testid="highlight-menu"]')
        highlight_menu.wait_for(state="visible", timeout=5000)
        t_menu = time.perf_counter()
        results["highlightMenuMs"] = round((t_menu - t0) * 1000)

        # Apply a tag via a button inside the highlight menu
        menu_tag_btns = highlight_menu.locator('[data-testid="highlight-menu-tag-btn"]')
        if menu_tag_btns.count() > 0:
            tag_id = menu_tag_btns.first.get_attribute("data-tag-id")

            epoch_before = page.evaluate("() => window.__annotationCardsEpoch || 0")

            t_tag_start = time.perf_counter()
            menu_tag_btns.first.click()
            page.wait_for_timeout(200)

            # Wait for card rebuild (epoch advance)
            try:
                page.wait_for_function(
                    f"() => (window.__annotationCardsEpoch || 0) > {epoch_before}",
                    timeout=10_000,
                )
                t_tag_end = time.perf_counter()
                results["tagApplyMs"] = round((t_tag_end - t_tag_start) * 1000)
                results["tagApplied"] = tag_id
            except Exception:
                t_tag_end = time.perf_counter()
                results["tagApplyMs"] = round((t_tag_end - t_tag_start) * 1000)
                results["tagApplyTimeout"] = True

    except Exception:
        results["highlightMenuVisible"] = False

    # Clear selection
    page.evaluate("() => window.getSelection().removeAllRanges()")
    page.wait_for_timeout(300)

    return results


def _compute_stats(
    values: list[float | int],
) -> dict[str, float]:
    """Compute summary statistics for a list of values."""
    if not values:
        return {}
    result: dict[str, float] = {
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "mean": round(statistics.mean(values), 1),
        "median": round(statistics.median(values), 1),
    }
    if len(values) >= 2:
        result["stdev"] = round(statistics.stdev(values), 1)
    return result


def _summarise(
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build summary statistics from per-iteration results."""
    summary: dict[str, Any] = {}

    # Wall clock totals
    wall_totals = [
        r["timing"]["wallClockTotalMs"] for r in results if r.get("walkerReady")
    ]
    summary["wallClockTotalMs"] = _compute_stats(wall_totals)

    # Server response
    server_times = [
        r["browser"]["navigation"]["serverResponseMs"]
        for r in results
        if r["browser"]["navigation"]["serverResponseMs"] is not None
    ]
    summary["serverResponseMs"] = _compute_stats(server_times)

    # DOM content loaded
    dom_times = [
        r["browser"]["navigation"]["domContentLoadedMs"]
        for r in results
        if r["browser"]["navigation"]["domContentLoadedMs"] is not None
    ]
    summary["domContentLoadedMs"] = _compute_stats(dom_times)

    # FCP
    fcp_times = [
        r["browser"]["paint"]["firstContentfulPaintMs"]
        for r in results
        if r["browser"]["paint"]["firstContentfulPaintMs"] is not None
    ]
    summary["firstContentfulPaintMs"] = _compute_stats(fcp_times)

    # LCP
    lcp_times = [
        r["browser"]["lcp"]["startTimeMs"]
        for r in results
        if r["browser"].get("lcp") and r["browser"]["lcp"]["startTimeMs"] is not None
    ]
    summary["lcpMs"] = _compute_stats(lcp_times)

    # Transfer size
    sizes = [
        r["browser"]["navigation"]["decodedBodySizeBytes"]
        for r in results
        if r["browser"]["navigation"]["decodedBodySizeBytes"] is not None
    ]
    summary["decodedBodySizeBytes"] = _compute_stats(sizes)

    return summary


def _print_summary(summary: dict[str, Any], label: str = "PAGE LOAD") -> None:
    """Print a human-readable summary table."""
    print(f"\n{'=' * 70}")
    print(f"  {label} PROFILING RESULTS")
    print(f"{'=' * 70}")

    for metric, stats in summary.items():
        if not stats:
            continue
        count = stats.get("count", 0)
        mean = stats.get("mean", 0)
        median = stats.get("median", 0)
        mn = stats.get("min", 0)
        mx = stats.get("max", 0)
        stdev = stats.get("stdev", "-")
        unit = "bytes" if "Bytes" in metric else "ms"
        print(
            f"  {metric:30s}  "
            f"mean={mean:>8.1f}{unit}  "
            f"median={median:>8.1f}{unit}  "
            f"min={mn:>8.1f}  max={mx:>8.1f}  "
            f"stdev={stdev!s:>6s}  n={count}"
        )

    print(f"{'=' * 70}\n")


def _run_single_iteration(
    browser: Any,
    server_url: str,
    workspace_url: str,
    *,
    iteration: int,
    total_iterations: int,
    measure_interactions: bool,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Run a single profiling iteration.

    Returns (load_result, interaction_result | None).
    """
    context = browser.new_context()
    page = context.new_page()

    print(
        f"  Iteration {iteration + 1}/{total_iterations}...",
        end="",
        flush=True,
    )

    _authenticate(page, server_url)
    result = _measure_page_load(page, workspace_url, iteration=iteration)

    total = result["timing"]["wallClockTotalMs"]
    ready = "ready" if result["walkerReady"] else "TIMEOUT"
    print(f" {total}ms [{ready}]", end="")

    interaction = None
    if measure_interactions and result["walkerReady"]:
        interaction = _measure_interactions(page, iteration=iteration)
        if "highlightMenuMs" in interaction:
            print(f" menu={interaction['highlightMenuMs']}ms", end="")
        if "tagApplyMs" in interaction:
            print(f" tag={interaction['tagApplyMs']}ms", end="")

    print()

    page.goto("about:blank")
    page.close()
    context.close()
    return result, interaction


def _run_profiling(
    server_url: str,
    workspace_url: str,
    *,
    iterations: int,
    measure_interactions: bool,
    headed: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Run Playwright profiling iterations.

    Returns (load_results, interaction_results).
    """
    load_results: list[dict[str, Any]] = []
    interaction_results: list[dict[str, Any]] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headed)

        for i in range(iterations):
            result, interaction = _run_single_iteration(
                browser,
                server_url,
                workspace_url,
                iteration=i,
                total_iterations=iterations,
                measure_interactions=measure_interactions,
            )
            load_results.append(result)
            if interaction is not None:
                interaction_results.append(interaction)

        browser.close()

    return load_results, interaction_results


def _emit_results(
    output: dict[str, Any],
    load_results: list[dict[str, Any]],
    output_path: Path | None,
) -> None:
    """Print summary and write JSON output."""
    _print_summary(output["load_summary"], "PAGE LOAD")
    if "interaction_summary" in output:
        _print_summary(output["interaction_summary"], "INTERACTION")

    for r in load_results:
        if r.get("walkerReady"):
            doc = r["document"]
            print("  Document stats (first load):")
            print(f"    HTML size: {doc['docContainerHtml']:,} chars")
            print(f"    Text nodes: {doc['textNodeCount']:,}")
            print(f"    Highlights: {doc['highlightCount']:,}")
            break

    if output_path:
        with output_path.open("w") as f:
            json.dump(output, f, indent=2)
        print(f"\n  Results written to {output_path}")
    else:
        print("\n  JSON results (use --output to save to file):")
        json.dump(output, sys.stderr, indent=2)
        print(file=sys.stderr)


@app.command()
def profile(
    url: str = typer.Option(..., help="Server URL (e.g. http://localhost:8080)"),
    workspace_id: str = typer.Option(..., help="UUID of the workspace to profile"),
    iterations: int = typer.Option(5, help="Number of page load iterations"),
    interactions: bool = typer.Option(
        False, help="Also measure tag interaction latency"
    ),
    output: Path | None = typer.Option(None, help="Write JSON results to file"),
    headed: bool = typer.Option(
        False, help="Run browser in headed mode (visible window)"
    ),
) -> None:
    """Profile annotation page load and interaction latency."""
    workspace_url = f"{url}/annotation?workspace_id={workspace_id}"

    typer.echo(f"Profiling: {workspace_url}")
    typer.echo(f"Iterations: {iterations}")
    typer.echo(f"Interactions: {interactions}")

    load_results, interaction_results = _run_profiling(
        url,
        workspace_url,
        iterations=iterations,
        measure_interactions=interactions,
        headed=headed,
    )

    load_summary = _summarise(load_results)
    result_output: dict[str, Any] = {
        "workspace_id": workspace_id,
        "server_url": url,
        "iterations": iterations,
        "load_results": load_results,
        "load_summary": load_summary,
    }

    if interaction_results:
        menu_times = [
            r["highlightMenuMs"] for r in interaction_results if "highlightMenuMs" in r
        ]
        tag_times = [r["tagApplyMs"] for r in interaction_results if "tagApplyMs" in r]
        result_output["interaction_results"] = interaction_results
        result_output["interaction_summary"] = {
            "highlightMenuMs": _compute_stats(menu_times),
            "tagApplyMs": _compute_stats(tag_times),
        }

    _emit_results(result_output, load_results, output)


if __name__ == "__main__":
    app()
