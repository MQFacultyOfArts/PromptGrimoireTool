"""Raw Starlette handlers for the admission queue.

These bypass NiceGUI entirely — zero client overhead for queued users.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from starlette.responses import HTMLResponse, JSONResponse

if TYPE_CHECKING:
    from starlette.requests import Request


async def queue_status_handler(
    request: Request,
) -> JSONResponse:
    """Return queue position / admission status for a token.

    AC4.3, AC4.4.
    """
    from promptgrimoire.admission import (  # noqa: PLC0415
        get_admission_state,
    )

    token = request.query_params.get("t", "")
    state = get_admission_state()
    status = state.get_queue_status(token)
    return JSONResponse(status)


async def queue_page_handler(
    request: Request,
) -> HTMLResponse:
    """Serve the queue waiting page as raw HTML.

    Vanilla JS polling, no NiceGUI client overhead.
    AC4.1, AC4.2, AC4.5, AC4.6.
    """
    token = request.query_params.get("t", "")
    raw_return = request.query_params.get("return", "/")

    # Open-redirect guard: return URL must be a relative path
    # starting with /. Rejects javascript:, data:,
    # protocol-relative (//), and absolute URLs.
    return_url = (
        raw_return
        if raw_return.startswith("/") and not raw_return.startswith("//")
        else "/"
    )

    # Safe JS embedding (prevent XSS via </script> injection)
    safe_token = json.dumps(token).replace("</", "<\\/")
    safe_return = json.dumps(return_url).replace("</", "<\\/")

    html = _build_queue_html(safe_token, safe_return)
    return HTMLResponse(html)


def _build_queue_html(safe_token: str, safe_return: str) -> str:
    """Build the queue page HTML with embedded JS polling."""
    # Line length inside the JS template is intentional —
    # this is inline JavaScript, not Python.
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Queue - PromptGrimoire</title>
    <style>
        body {{ font-family: system-ui, sans-serif; display: flex;
               justify-content: center; align-items: center;
               min-height: 100vh; margin: 0; background: #f5f5f5; }}
        main {{ text-align: center; max-width: 400px; padding: 2rem; }}
        h1 {{ font-size: 1.5rem; margin-bottom: 1rem; }}
        #position {{ font-size: 1.2rem; margin: 1rem 0; }}
        #expired {{ display: none; }}
        a {{ color: #1976d2; }}
    </style>
</head>
<body>
    <main>
        <h1>Server is busy</h1>
        <p id="position">Loading queue position...</p>
        <p>Users are admitted in batches. This page updates automatically.</p>
        <div id="expired">
            <p>Your place in the queue has expired.</p>
            <p><a id="rejoin" href="/">Rejoin the queue</a></p>
        </div>
        <noscript><p>JavaScript is required for the queue page.</p></noscript>
    </main>
    <script>
    (function() {{
        var token = {safe_token};
        var returnUrl = {safe_return};
        var posEl = document.getElementById("position");
        var expEl = document.getElementById("expired");
        var rejoinEl = document.getElementById("rejoin");
        rejoinEl.href = returnUrl;
        async function poll() {{
            try {{
                var r = await fetch(
                    "/api/queue/status?t=" + encodeURIComponent(token)
                );
                if (r.ok) {{
                    var d = await r.json();
                    if (d.admitted) {{
                        window.location.href = returnUrl;
                        return;
                    }}
                    if (d.expired) {{
                        posEl.style.display = "none";
                        expEl.style.display = "block";
                        return;
                    }}
                    posEl.textContent = "You are position "
                        + d.position + " of "
                        + d.total + " in the queue.";
                }}
            }} catch (e) {{
                /* server may be restarting */
            }}
            setTimeout(poll, 5000);
        }}
        setTimeout(poll, 1000);
    }})();
    </script>
</body>
</html>"""
