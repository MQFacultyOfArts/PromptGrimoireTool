"""Raw Starlette handlers for the admission queue and idle paused page.

These bypass NiceGUI entirely — zero client overhead for queued users.
"""

from __future__ import annotations

import json
import re
from html import escape
from typing import TYPE_CHECKING

from starlette.responses import HTMLResponse, JSONResponse

if TYPE_CHECKING:
    from starlette.requests import Request

_SAFE_RETURN_RE = re.compile(r"^/([^/].*)?$")


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


async def paused_page_handler(
    request: Request,
) -> HTMLResponse:
    """Serve the idle-paused landing page as raw HTML.

    No NiceGUI client created. AC3.1, AC3.4, AC3.5, AC3.6.
    """
    raw_return = request.query_params.get("return", "/")
    return_url = raw_return if _SAFE_RETURN_RE.match(raw_return) else "/"
    return HTMLResponse(_build_paused_html(return_url))


def _build_paused_html(return_url: str) -> str:
    """Build the paused page HTML with Resume button."""
    safe_href = escape(return_url, quote=True)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Session Paused - PromptGrimoire</title>
    <style>
        body {{ font-family: system-ui, sans-serif; display: flex;
               justify-content: center; align-items: center;
               min-height: 100vh; margin: 0; background: #f5f5f5; }}
        main {{ text-align: center; max-width: 400px; padding: 2rem; }}
        h1 {{ font-size: 1.5rem; margin-bottom: 1rem; }}
        .resume {{ display: inline-block; margin-top: 1.5rem;
                   padding: 0.75rem 2rem; background: #1976d2;
                   color: white; text-decoration: none;
                   border-radius: 4px; font-size: 1rem; }}
        .resume:hover {{ background: #1565c0; }}
    </style>
</head>
<body>
    <main>
        <h1>Session paused</h1>
        <p>Your session was paused due to inactivity.</p>
        <p>Your saved work is preserved.</p>
        <a class="resume" href="{safe_href}">Resume</a>
    </main>
</body>
</html>"""


async def welcome_page_handler(
    request: Request,  # noqa: ARG001 — Starlette handler signature
) -> HTMLResponse:
    """Serve the pre-auth landing page as raw HTML.

    Lightweight bookmark target — no NiceGUI client created. AC7.1, AC7.2.
    """
    from promptgrimoire.config import get_settings  # noqa: PLC0415

    tagline = escape(get_settings().app.tagline, quote=True)
    return HTMLResponse(_build_welcome_html(tagline))


def _build_welcome_html(tagline: str) -> str:
    """Build the welcome landing page HTML with Login button."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Welcome - PromptGrimoire</title>
    <style>
        body {{ font-family: system-ui, sans-serif; display: flex;
               justify-content: center; align-items: center;
               min-height: 100vh; margin: 0; background: #f5f5f5; }}
        main {{ text-align: center; max-width: 400px; padding: 2rem; }}
        h1 {{ font-size: 1.5rem; margin-bottom: 1rem; }}
        .login {{ display: inline-block; margin-top: 1.5rem;
                 padding: 0.75rem 2rem; background: #1976d2;
                 color: white; text-decoration: none;
                 border-radius: 4px; font-size: 1rem; }}
        .login:hover {{ background: #1565c0; }}
    </style>
</head>
<body>
    <main>
        <h1>PromptGrimoire</h1>
        <p>{tagline}</p>
        <a class="login" href="/login?return=/">Login</a>
    </main>
</body>
</html>"""
