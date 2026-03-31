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

    With no params, returns current state.
    """
    from promptgrimoire.admission import get_admission_state  # noqa: PLC0415

    try:
        state = get_admission_state()
    except RuntimeError:
        logger.warning("dev_admission_not_initialised")
        return JSONResponse({"error": "admission not initialised"}, status_code=503)

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

    logger.warning("dev_block_loop_start", ms=ms, repeat=repeat)

    for i in range(repeat):
        time.sleep(ms / 1000.0)
        if i < repeat - 1:
            # Brief yield between blocks so the loop can process one tick
            import asyncio  # noqa: PLC0415

            await asyncio.sleep(0.1)

    logger.warning("dev_block_loop_done", ms=ms, repeat=repeat)

    return JSONResponse(
        {
            "blocked_ms": ms,
            "repeat": repeat,
            "total_ms": ms * repeat + (repeat - 1) * 100,
        }
    )
