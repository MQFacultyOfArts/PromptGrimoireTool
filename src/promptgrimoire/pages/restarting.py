"""Holding page during server restart.

Two modes controlled by the ``manual`` query parameter:

- **Auto mode** (default, ``manual`` absent): Polls ``/healthz`` every
  2 seconds.  On HTTP 200, waits a random 1-5 s jitter then redirects.
  Used by ``deploy/restart.sh`` operator-initiated deploys.

- **Manual mode** (``manual=1``): Polls ``/healthz`` silently.  When
  the server is ready, shows a "Return to …" button instead of
  auto-redirecting.  Used by memory-threshold restarts to prevent a
  thundering herd of 200+ clients reconnecting simultaneously.

Uses ``@ui.page`` directly (not ``page_route``) so it is accessible
regardless of authentication state — identical pattern to ``/banned``.
"""

from __future__ import annotations

import json
import re

from nicegui import ui

_SAFE_RETURN_RE = re.compile(r"^/([^/].*)?$")


def _js_string(value: str) -> str:
    """Escape a Python string for safe embedding in a ``<script>`` block.

    ``json.dumps`` handles JS string escaping but does not escape the
    ``</`` sequence which terminates ``<script>`` at the HTML parser
    level (HTML5 §8.1.2.6).  The ``<\\/`` replacement is the standard
    fix used by Django's ``escapejs`` for the same reason.
    """
    return json.dumps(value).replace("</", "<\\/")


def _safe_return_url(raw: str) -> str:
    """Accept only same-origin relative paths; reject everything else."""
    if _SAFE_RETURN_RE.match(raw):
        return raw
    return "/"


_TITLE_MAP: dict[str, str] = {
    "/": "Home",
    "/annotation": "Annotation",
    "/courses": "Units",
    "/login": "Login",
}


def _return_title(return_url: str) -> str:
    """Derive a human-readable page title from the return URL path."""
    path = return_url.split("?", maxsplit=1)[0].split("#", maxsplit=1)[0]
    if path in _TITLE_MAP:
        return _TITLE_MAP[path]
    # Strip leading slash and use first segment, title-cased
    segment = path.strip("/").split("/")[0]
    return segment.replace("-", " ").replace("_", " ").title() if segment else "Home"


@ui.page("/restarting")
async def restarting_page() -> None:
    """Display server-updating message with polling.

    In auto mode (default): polls /healthz then redirects with jitter.
    In manual mode (?manual=1): polls /healthz then shows a button.
    """
    raw = ui.context.client.request.query_params.get("return", "/")
    return_url = _safe_return_url(raw)
    manual = ui.context.client.request.query_params.get("manual") == "1"

    # Derive a human-readable title from the return path
    return_title = _return_title(return_url)

    with ui.column().classes("absolute-center items-center"):
        ui.icon("update", size="xl").classes("text-blue-500")
        ui.label("Server updating, please wait...").classes(
            "text-2xl font-bold mt-4"
        ).props('data-testid="restarting-message"')
        ui.label("Waiting for server...").classes("text-lg text-grey-7 mt-2").props(
            'data-testid="restarting-status"'
        )

    if manual:
        # Manual mode: poll silently, show button when ready
        ui.add_body_html(f"""<script>
    (function() {{
        const returnUrl = {_js_string(return_url)};
        const returnTitle = {_js_string(return_title)};
        const pollInterval = 2000;

        async function pollHealthz() {{
            try {{
                const resp = await fetch("/healthz", {{method: "HEAD"}});
                if (resp.ok) {{
                    const statusEl = document.querySelector(
                        '[data-testid="restarting-status"]'
                    );
                    if (statusEl) statusEl.textContent = "Server is ready.";
                    const btnContainer = document.querySelector(
                        '[data-testid="restarting-btn-container"]'
                    );
                    if (btnContainer) {{
                        btnContainer.innerHTML = '';
                        const btn = document.createElement('button');
                        btn.textContent = "Return to " + returnTitle;
                        btn.className = 'q-btn q-btn--flat q-btn--rectangle '
                            + 'text-white bg-blue-500 q-mt-md';
                        btn.style.padding = '12px 32px';
                        btn.style.fontSize = '1.1rem';
                        btn.style.cursor = 'pointer';
                        btn.setAttribute('data-testid', 'restarting-return-btn');
                        btn.onclick = function() {{
                            window.location.href = returnUrl;
                        }};
                        btnContainer.appendChild(btn);
                    }}
                    return;
                }}
            }} catch (e) {{
                // Server not ready yet
            }}
            setTimeout(pollHealthz, pollInterval);
        }}

        setTimeout(pollHealthz, pollInterval);
    }})();
    </script>""")
        # Container for the button (injected by JS when server is ready)
        ui.html(
            '<div data-testid="restarting-btn-container"'
            ' style="text-align:center;margin-top:16px"></div>'
        )
    else:
        # Auto mode: poll and redirect with jitter
        ui.add_body_html(f"""<script>
    (function() {{
        const returnUrl = {_js_string(return_url)};
        const pollInterval = 2000;

        async function pollHealthz() {{
            try {{
                const resp = await fetch("/healthz", {{method: "HEAD"}});
                if (resp.ok) {{
                    const jitter = 1000 + Math.random() * 4000;
                    const sel = '[data-testid="restarting-status"]';
                    const el = document.querySelector(sel);
                    if (el) el.textContent = "Server ready, redirecting...";
                    setTimeout(function() {{
                        window.location.href = returnUrl;
                    }}, jitter);
                    return;
                }}
            }} catch (e) {{
                // Server not ready yet — expected during restart
            }}
            setTimeout(pollHealthz, pollInterval);
        }}

        setTimeout(pollHealthz, pollInterval);
    }})();
    </script>""")
