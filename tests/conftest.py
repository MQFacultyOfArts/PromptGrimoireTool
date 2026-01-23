"""Shared pytest fixtures for PromptGrimoire tests."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from dotenv import load_dotenv

from promptgrimoire.db import run_alembic_upgrade

load_dotenv()

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from playwright.sync_api import Browser, BrowserContext


TEST_STORAGE_SECRET = "test-secret-for-e2e"


@pytest.fixture(scope="session", autouse=True)
def db_schema_guard() -> Generator[None]:
    """Run migrations once at session start for test database isolation.

    This fixture:
    1. Sets DATABASE_URL from TEST_DATABASE_URL for test isolation
    2. Runs Alembic migrations to ensure schema exists
    3. Does NOT initialize the engine (tests do that as needed)

    Schema verification happens at app startup, not here.
    """
    test_url = os.environ.get("TEST_DATABASE_URL")
    if not test_url:
        pytest.fail(
            "TEST_DATABASE_URL environment variable is required for tests. "
            "Set it to point to a test database (not production!)."
        )

    # Set DATABASE_URL from TEST_DATABASE_URL for test isolation
    os.environ["DATABASE_URL"] = test_url

    # Run migrations (sync - Alembic uses subprocess)
    try:
        run_alembic_upgrade()
    except RuntimeError as e:
        pytest.fail(str(e))

    yield
    # No cleanup needed - UUID-based isolation means data doesn't collide


@pytest.fixture
def mock_stytch_client():
    """Create a mocked Stytch B2BClient for unit tests.

    Patches the B2BClient constructor to return a mock, allowing
    tests to set up expected responses without making real API calls.
    """
    with patch("promptgrimoire.auth.client.B2BClient") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        yield mock_client


def _find_free_port() -> int:
    """Find an available port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


# Script to run NiceGUI server
# Note: We clear PYTEST env vars to prevent NiceGUI from entering test mode
_SERVER_SCRIPT = f"""
import os
import sys

# Clear pytest-related environment variables that NiceGUI checks
for key in list(os.environ.keys()):
    if 'PYTEST' in key or 'NICEGUI' in key:
        del os.environ[key]

# Enable mock auth for E2E tests
os.environ['AUTH_MOCK'] = 'true'
os.environ['STORAGE_SECRET'] = '{TEST_STORAGE_SECRET}'

# Set mock SSO config values so SSO flow can be tested
# Without these, the SSO code returns early before generating a redirect URL
os.environ.setdefault('STYTCH_SSO_CONNECTION_ID', 'test-sso-connection-id')
os.environ.setdefault('STYTCH_PUBLIC_TOKEN', 'test-public-token')

port = int(sys.argv[1])

from nicegui import ui
import promptgrimoire.pages  # noqa: F401 - registers routes

ui.run(port=port, reload=False, show=False, storage_secret='{TEST_STORAGE_SECRET}')
"""


@pytest.fixture(scope="session")
def app_server() -> Generator[str]:
    """Start the NiceGUI app server for E2E tests.

    Returns the base URL of the running server.
    Automatically starts before tests and stops after.

    Note: NiceGUI detects pytest and enters test mode, expecting special
    environment variables. We clear these in the subprocess to run normally.
    """
    port = _find_free_port()
    url = f"http://localhost:{port}"

    # Create clean environment without pytest variables
    clean_env = {
        k: v for k, v in os.environ.items() if "PYTEST" not in k and "NICEGUI" not in k
    }

    # Start server as subprocess with clean environment
    process = subprocess.Popen(
        [sys.executable, "-c", _SERVER_SCRIPT, str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=clean_env,
    )

    # Wait for server to be ready
    max_wait = 15  # seconds
    start_time = time.time()
    while time.time() - start_time < max_wait:
        # Check if process died
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            pytest.fail(
                f"Server process died. Exit code: {process.returncode}\n"
                f"stdout: {stdout.decode()}\n"
                f"stderr: {stderr.decode()}"
            )
        try:
            with socket.create_connection(("localhost", port), timeout=1):
                break
        except OSError:
            time.sleep(0.1)
    else:
        process.terminate()
        pytest.fail(f"Server failed to start within {max_wait} seconds")

    yield url

    # Cleanup
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


@pytest.fixture
def crdt_sync_url(app_server: str) -> str:
    """URL for the CRDT sync demo page."""
    return f"{app_server}/demo/crdt-sync"


@pytest.fixture
def text_selection_url(app_server: str) -> str:
    """URL for the text selection demo page."""
    return f"{app_server}/demo/text-selection"


@pytest.fixture
def live_annotation_url(app_server: str) -> str:
    """URL for the live annotation demo page."""
    return f"{app_server}/demo/live-annotation"


@pytest.fixture
def reset_crdt_state(app_server: str) -> Generator[None]:
    """Reset CRDT state before each test.

    This ensures each E2E test starts with a clean CRDT document state.
    Function-scoped (default) so it runs before every test that uses it.
    """
    import urllib.request

    reset_url = f"{app_server}/api/test/reset-crdt"
    try:
        with urllib.request.urlopen(reset_url, timeout=5) as resp:
            if resp.status != 200:
                pytest.fail(f"Failed to reset CRDT state: {resp.status}")
    except Exception as e:
        pytest.fail(f"Failed to reset CRDT state: {e}")

    yield


@pytest.fixture
def new_context(browser: Browser) -> Generator[Callable[[], BrowserContext]]:
    """Factory fixture for creating new browser contexts.

    Creates isolated browser contexts for multi-user E2E testing.
    All contexts are automatically cleaned up after the test.

    Usage:
        def test_two_users(page: Page, new_context):
            context2 = new_context()
            page2 = context2.new_page()
            # page and page2 are now independent browser sessions
    """
    contexts: list[BrowserContext] = []

    def _new_context() -> BrowserContext:
        ctx = browser.new_context()
        contexts.append(ctx)
        return ctx

    yield _new_context

    # Cleanup all created contexts
    for ctx in contexts:
        ctx.close()


@pytest.fixture
def sample_claude_conversation() -> str:
    """A sample Claude conversation for testing parsers."""
    return (
        "Human: What is the capital of France?\n\n"
        "Assistant: The capital of France is Paris.\n\n"
        "Human: What about Germany?\n\n"
        "Assistant: The capital of Germany is Berlin."
    )


@pytest.fixture
def sample_chatgpt_conversation() -> str:
    """A sample ChatGPT conversation for testing parsers."""
    return (
        "User: What is the capital of France?\n\n"
        "ChatGPT: The capital of France is Paris.\n\n"
        "User: What about Germany?\n\n"
        "ChatGPT: The capital of Germany is Berlin."
    )
