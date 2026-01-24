"""E2E test configuration.

Auto-applies the 'e2e' marker to all tests in this directory.
Skip with: pytest -m "not e2e"
"""

import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Add e2e marker to all tests in this directory."""
    for item in items:
        if "/e2e/" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)
