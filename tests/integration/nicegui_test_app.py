"""Minimal NiceGUI app entry point for User-fixture integration tests.

Loaded by ``user_simulation(main_file=...)`` via ``runpy.run_path()``.
When ``NICEGUI_USER_SIMULATION`` is set, ``ui.run()`` configures the
ASGI app with a storage secret and returns immediately -- it does NOT
start a server.  This lets the User harness drive the app in-process.

Environment variables consumed:
- ``DEV__AUTH_MOCK=true``  -- routes auth through MockAuthClient
- ``DATABASE__URL``        -- set by db_schema_guard / test CLI
"""

from __future__ import annotations

import os
from pathlib import Path

from nicegui import app, ui

import promptgrimoire
import promptgrimoire.pages  # registers @ui.page routes

# Enable mock auth -- must be set before the first get_auth_client() call,
# which happens lazily when a page handler runs (not at import time).
os.environ.setdefault("DEV__AUTH_MOCK", "true")

# Serve static assets (mirrors main() in promptgrimoire/__init__.py)
_static_dir = Path(promptgrimoire.__file__).parent / "static"
app.add_static_files("/static", str(_static_dir))

# In user simulation mode ui.run() just sets the storage secret and returns.
ui.run(storage_secret="test-user-fixture-secret")  # nosec B106 -- test-only, not a real secret
