"""Shared fixtures for incident analysis tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _no_beszel_auto_fetch():
    """Prevent ingest from hitting a live Beszel hub during tests.

    ``_try_beszel_fetch`` probes localhost:8090 and, if reachable,
    makes real HTTP requests to fetch metrics.  This must never run
    in tests — it pollutes the test database with extra sources and
    depends on an SSH tunnel that may or may not be open.
    """
    with patch("scripts.incident.ingest._try_beszel_fetch"):
        yield
