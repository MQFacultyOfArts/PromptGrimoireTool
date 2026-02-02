"""Benchmark test configuration.

Reuses E2E fixtures (app_server, authenticated_page) by loading them via pytest_plugins.
This makes the fixtures available in this test directory.

Note: app_server is in tests/conftest.py (session-scoped)
      authenticated_page is in tests/e2e/conftest.py (pre-authenticated)
"""

from __future__ import annotations

# Load fixtures from e2e conftest
pytest_plugins = ["tests.e2e.conftest"]
