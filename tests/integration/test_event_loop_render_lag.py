"""Card build time during annotation rendering (#457).

Measures per-card and total build time when loading a heavy workspace
(190 highlights). Uses direct timing from the ``card_diff_add``
structured log event, which wraps the actual diff-add loop with
``time.monotonic()``. This is more accurate than event loop lag
sampling, which systematically underreports (showed 15-35ms while
direct timing showed 425-479ms continuous blocking).

The lag sampler is retained as informational-only diagnostic output.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
import structlog
from structlog.testing import capture_logs

from promptgrimoire.config import get_settings

if TYPE_CHECKING:
    from nicegui.testing.user import User

logger = structlog.get_logger()

pytestmark = [
    pytest.mark.skipif(
        not get_settings().dev.test_database_url,
        reason="DEV__TEST_DATABASE_URL not configured",
    ),
    pytest.mark.nicegui_ui,
    pytest.mark.perf,
]

# Per-card build time threshold in milliseconds.
# With lazy detail + HTML header optimisations, each card should build
# in under 0.5ms (just the collapsed header, no detail panel).
_PER_CARD_THRESHOLD_MS = 0.5

# Total build time threshold for 190 cards.
# 190 * 0.5ms = 95ms, rounded up to 100ms.
_TOTAL_THRESHOLD_MS = 100.0


class TestCardBuildTime:
    """Card build time during heavy annotation page render."""

    @pytest.mark.asyncio
    async def test_heavy_render_card_build_time(self, nicegui_user: User) -> None:
        """Loading 190-annotation workspace: per-card < 0.5ms, total < 100ms.

        Strategy:
          1. Rehydrate PABAI workspace (190 highlights, ~180KB CRDT)
          2. Capture structlog events during page load
          3. Extract ``card_diff_add`` event with ``elapsed_ms`` and
             ``added_count`` fields (direct ``time.monotonic()`` timing)
          4. Assert per-card and total thresholds
          5. Run lag sampler as informational diagnostic (no assertion)
        """
        from promptgrimoire.diagnostics import measure_event_loop_lag
        from tests.integration.conftest import _authenticate
        from tests.integration.nicegui_helpers import wait_for_annotation_load
        from tests.integration.test_memory_leak_probe import (
            _rehydrate_heavy_workspace,
        )

        run_id = uuid4().hex[:6]
        email = f"lag-test-{run_id}@test.example.edu.au"

        ws_id = await _rehydrate_heavy_workspace(email)
        await _authenticate(nicegui_user, email=email)

        # Warm up: let any one-time initialisation settle
        await asyncio.sleep(0.1)  # noqa: PG001 — deliberate settle before measurement

        # --- Informational lag sampler (no assertion) ---
        lag_samples: list[float] = []
        stop = asyncio.Event()

        async def _sample_lag() -> None:
            """Continuously measure event loop lag until stopped."""
            while not stop.is_set():
                lag = await measure_event_loop_lag()
                lag_samples.append(lag)
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=0.005)

        sampler = asyncio.create_task(_sample_lag())
        await asyncio.sleep(0.05)  # noqa: PG001 — sampler needs baseline before load

        # --- Load page and capture structlog events ---
        with capture_logs() as cap:
            await nicegui_user.open(f"/annotation?workspace_id={ws_id}")
            await wait_for_annotation_load(nicegui_user)

        # Stop lag sampler
        await asyncio.sleep(0.05)  # noqa: PG001 — trailing callbacks before measurement
        stop.set()
        await sampler

        # --- Extract card_diff_add event ---
        diff_events = [e for e in cap if e.get("event") == "card_diff_add"]
        assert len(diff_events) >= 1, (
            f"Expected at least 1 card_diff_add event, got {len(diff_events)}. "
            f"Captured events: {[e.get('event') for e in cap]}"
        )

        # Use the first (and typically only) card_diff_add event
        diff_event = diff_events[0]
        elapsed_ms: float = diff_event["elapsed_ms"]
        added_count: int = diff_event["added_count"]
        per_card_ms = elapsed_ms / added_count if added_count > 0 else 0.0

        # --- Lag sampler diagnostic (informational only) ---
        peak_lag = max(lag_samples) if lag_samples else 0.0
        avg_lag = sum(lag_samples) / len(lag_samples) if lag_samples else 0.0

        logger.info(
            "render_lag_diagnostic",
            samples=len(lag_samples),
            peak_ms=round(peak_lag, 1),
            avg_ms=round(avg_lag, 1),
            note="informational_only_not_asserted",
        )

        # --- Report ---
        report_lines = [
            f"{'=' * 60}",
            "CARD BUILD TIME DURING 190-HIGHLIGHT RENDER",
            f"{'=' * 60}",
            f"  Cards built:        {added_count}",
            f"  Total time:         {elapsed_ms:.1f}ms",
            f"  Per-card time:      {per_card_ms:.2f}ms",
            f"  Total threshold:    {_TOTAL_THRESHOLD_MS:.0f}ms",
            f"  Per-card threshold: {_PER_CARD_THRESHOLD_MS:.1f}ms",
            f"  Lag sampler peak:   {peak_lag:.1f}ms (informational)",
            f"  Lag sampler avg:    {avg_lag:.1f}ms (informational)",
            f"{'=' * 60}",
        ]
        report = "\n".join(report_lines)
        print(f"\n{report}")

        # Persist results outside artifact dir (survives cleanup)
        from pathlib import Path

        out = Path("output/perf/render_lag.txt")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")

        # --- Assertions on direct timing ---
        assert per_card_ms < _PER_CARD_THRESHOLD_MS, (
            f"Per-card build time {per_card_ms:.2f}ms exceeds threshold "
            f"{_PER_CARD_THRESHOLD_MS}ms ({added_count} cards in {elapsed_ms:.1f}ms). "
            f"Lazy detail and HTML header optimisations should bring this below 0.5ms."
        )
        assert elapsed_ms < _TOTAL_THRESHOLD_MS, (
            f"Total card build time {elapsed_ms:.1f}ms exceeds threshold "
            f"{_TOTAL_THRESHOLD_MS}ms for {added_count} cards. "
            f"Expected < 100ms with lazy detail and HTML header optimisations."
        )
