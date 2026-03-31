"""Dev-only endpoints for testing the admission gate.

Gated behind DEV__AUTH_MOCK=true — never available in production.

Endpoints:
    POST /api/dev/admission  — manipulate admission state (set cap, etc.)
    POST /api/dev/block-loop — block the event loop for N ms (triggers AIMD)
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import structlog
from starlette.responses import JSONResponse

if TYPE_CHECKING:
    from starlette.requests import Request

logger = structlog.get_logger()


async def admission_control_handler(request: Request) -> JSONResponse:
    """Manipulate admission state for dev/test.

    Query params:
        cap: Set the admission cap directly (int)
        enabled: Enable/disable the gate (true/false)
        clear: If "true", call clear() to reset all state first

    With no params, returns current state.
    """
    from promptgrimoire.admission import get_admission_state  # noqa: PLC0415

    try:
        state = get_admission_state()
    except RuntimeError:
        logger.warning("dev_admission_not_initialised")
        return JSONResponse({"error": "admission not initialised"}, status_code=503)

    clear_param = request.query_params.get("clear")
    if clear_param and clear_param.lower() in ("true", "1", "yes"):
        state.clear()
        logger.warning("dev_admission_cleared")

    cap_param = request.query_params.get("cap")
    enabled_param = request.query_params.get("enabled")

    if cap_param is not None:
        state.cap = int(cap_param)
        logger.warning("dev_admission_cap_override", cap=state.cap)

    if enabled_param is not None:
        state.enabled = enabled_param.lower() in ("true", "1", "yes")
        logger.warning("dev_admission_enabled_override", enabled=state.enabled)

    return JSONResponse(
        {
            "enabled": state.enabled,
            "cap": state.cap,
            "initial_cap": state.initial_cap,
            "queue_depth": state.queue_depth,
            "ticket_count": state.ticket_count,
        }
    )


async def block_loop_handler(request: Request) -> JSONResponse:
    """Block the event loop for N milliseconds (synchronous sleep).

    This creates real, measurable event-loop lag that
    ``measure_event_loop_lag()`` will pick up. On the next diagnostic
    cycle, the AIMD algorithm will halve the cap.

    Query params:
        ms: Duration to block in milliseconds (default: 200, max: 5000)
        repeat: Number of times to block with 100ms gaps (default: 1, max: 10)

    WARNING: This blocks ALL request processing for the duration.
    """
    ms = min(int(request.query_params.get("ms", "200")), 5000)
    repeat = min(int(request.query_params.get("repeat", "1")), 10)

    import asyncio  # noqa: PLC0415

    logger.warning("dev_block_loop_start", ms=ms, repeat=repeat)

    # Schedule the lag measurement BEFORE blocking — the call_soon
    # callback queues behind the sleep, so it measures how long the
    # loop was actually blocked.
    loop = asyncio.get_running_loop()
    lag_future: asyncio.Future[float] = loop.create_future()
    t0 = loop.time()

    def _resolve_lag() -> None:
        lag_future.set_result((loop.time() - t0) * 1000.0)

    loop.call_soon(_resolve_lag)

    # Now block — the _resolve_lag callback sits in the queue behind this
    for i in range(repeat):
        time.sleep(ms / 1000.0)
        if i < repeat - 1:
            await asyncio.sleep(0.1)

    # Await the lag measurement — it fires as soon as we yield
    lag_ms = await lag_future

    logger.warning("dev_block_loop_done", ms=ms, repeat=repeat, lag_ms=round(lag_ms, 2))

    # Run AIMD cycle with the measured lag
    from promptgrimoire.admission import get_admission_state  # noqa: PLC0415

    try:
        state = get_admission_state()
        from promptgrimoire.auth import client_registry  # noqa: PLC0415

        admitted_count = len(client_registry._registry)
        cap_before = state.cap
        state.update_cap(lag_ms=lag_ms, admitted_count=admitted_count)
        state.admit_batch(admitted_count=admitted_count)
        state.sweep_expired()
        cap_after = state.cap
        logger.warning(
            "dev_block_loop_aimd",
            lag_ms=round(lag_ms, 2),
            admitted_count=admitted_count,
            cap_before=cap_before,
            cap_after=cap_after,
        )
    except RuntimeError:
        cap_before = cap_after = -1

    return JSONResponse(
        {
            "blocked_ms": ms,
            "repeat": repeat,
            "total_ms": ms * repeat + (repeat - 1) * 100,
            "measured_lag_ms": round(lag_ms, 2),
            "cap_before": cap_before,
            "cap_after": cap_after,
        }
    )
