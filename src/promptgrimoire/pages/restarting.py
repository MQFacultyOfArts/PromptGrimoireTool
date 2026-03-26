"""Holding page during server restart.

Polls ``/healthz`` every 2 seconds. On HTTP 200, waits a random 1-5 second
jitter (thundering herd prevention) then redirects to the ``return`` query
parameter, defaulting to ``/``.

Uses ``@ui.page`` directly (not ``page_route``) so it is accessible
regardless of authentication state — identical pattern to ``/banned``.
"""

from __future__ import annotations

import json

from nicegui import ui


def _js_string(value: str) -> str:
    """Escape a Python string for safe embedding in a JS string literal."""
    return json.dumps(value)


@ui.page("/restarting")
async def restarting_page() -> None:
    """Display server-updating message with auto-redirect polling."""
    return_url = ui.context.client.request.query_params.get("return", "/")

    with ui.column().classes("absolute-center items-center"):
        ui.icon("update", size="xl").classes("text-blue-500")
        ui.label("Server updating, please wait...").classes(
            "text-2xl font-bold mt-4"
        ).props('data-testid="restarting-message"')
        ui.label("Waiting for server...").classes("text-lg text-grey-7 mt-2").props(
            'data-testid="restarting-status"'
        )

    # Inline JS: poll /healthz, jitter redirect
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

        // Start polling after a brief initial delay (server just went down)
        setTimeout(pollHealthz, pollInterval);
    }})();
    </script>""")
