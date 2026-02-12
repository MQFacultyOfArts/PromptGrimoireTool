"""Shared pytest fixtures for PromptGrimoire tests."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections.abc import Generator
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from promptgrimoire.db import run_alembic_upgrade
from promptgrimoire.export.pdf import get_latexmk_path

load_dotenv()


def pytest_configure(config: pytest.Config) -> None:
    """Database cleanup is handled by CLI commands (test-all, test-debug).

    The CLI runs Alembic migrations and TRUNCATE in a single process before
    pytest starts, avoiding xdist worker deadlocks. See cli.py._pre_test_db_cleanup().

    When running pytest directly (not via CLI), ensure the database is
    already migrated and clean, or use the db_schema_guard fixture.
    """


# Canary UUID for database rebuild detection
# If this row disappears during a test run, the database was rebuilt
_DB_CANARY_ID = uuid4()

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Generator

    from playwright.sync_api import Browser, BrowserContext


# =============================================================================
# LaTeX/PDF Testing Utilities
# =============================================================================


def _has_latexmk() -> bool:
    """Check if latexmk is available via TinyTeX."""
    try:
        get_latexmk_path()
        return True
    except FileNotFoundError:
        return False


# Decorator that FAILS (not skips) when latexmk is missing
# Use pytest -m "not latex" to exclude these tests
def requires_latexmk(func_or_class):
    """Decorator that fails tests if latexmk is not installed.

    Unlike skipif, this makes missing dependencies visible as failures.
    To exclude LaTeX tests entirely: pytest -m "not latex"
    """
    import functools
    import inspect

    if isinstance(func_or_class, type):
        # Class decorator
        for name, method in list(vars(func_or_class).items()):
            if name.startswith("test_") and callable(method):
                setattr(func_or_class, name, requires_latexmk(method))
        return pytest.mark.latex(func_or_class)
    elif inspect.iscoroutinefunction(func_or_class):
        # Async function decorator
        @functools.wraps(func_or_class)
        async def async_wrapper(*args, **kwargs):
            if not _has_latexmk():
                pytest.fail(
                    "latexmk not installed. Run: uv run python scripts/setup_latex.py\n"
                    "To skip LaTeX tests: pytest -m 'not latex'"
                )
            return await func_or_class(*args, **kwargs)

        return pytest.mark.latex(async_wrapper)
    else:
        # Sync function decorator
        @functools.wraps(func_or_class)
        def wrapper(*args, **kwargs):
            if not _has_latexmk():
                pytest.fail(
                    "latexmk not installed. Run: uv run python scripts/setup_latex.py\n"
                    "To skip LaTeX tests: pytest -m 'not latex'"
                )
            return func_or_class(*args, **kwargs)

        return pytest.mark.latex(wrapper)


# =============================================================================
# Fixture File Loading (supports .html and .html.gz)
# =============================================================================

CONVERSATIONS_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "conversations"


def load_conversation_fixture(name: str) -> str:
    """Load a conversation fixture, supporting both .html and .html.gz.

    Args:
        name: Fixture name with or without extension (e.g., "claude_cooking" or
              "claude_cooking.html")

    Returns:
        HTML content as string.
    """
    import gzip

    # Normalize: strip extension if provided
    base_name = name.removesuffix(".html.gz").removesuffix(".html")

    # Try gzipped first (preferred for storage)
    gz_path = CONVERSATIONS_FIXTURES_DIR / f"{base_name}.html.gz"
    if gz_path.exists():
        with gzip.open(gz_path, "rt", encoding="utf-8") as f:
            return f.read()

    # Fall back to plain HTML
    html_path = CONVERSATIONS_FIXTURES_DIR / f"{base_name}.html"
    if html_path.exists():
        return html_path.read_text()

    msg = f"Fixture not found: {base_name} (tried .html.gz and .html)"
    raise FileNotFoundError(msg)


TEST_STORAGE_SECRET = "test-secret-for-e2e"


@pytest.fixture(scope="session")
def db_schema_guard() -> Generator[None]:
    """Set up database schema once at session start.

    This fixture:
    1. Sets DATABASE_URL from TEST_DATABASE_URL for test isolation
    2. Runs Alembic migrations to ensure schema exists

    The database engine is initialized lazily on first use within each
    test's event loop context. Tests use UUID-based isolation so they
    don't interfere with each other.

    Note: Not autouse - only tests that need the DB should depend on this
    (typically via their db_engine fixture).
    """
    test_url = os.environ.get("TEST_DATABASE_URL")
    if not test_url:
        pytest.fail(
            "TEST_DATABASE_URL environment variable is required for tests. "
            "Set it to point to a test database (not production!)."
        )
        return  # Unreachable, but helps type checker

    # Set DATABASE_URL from TEST_DATABASE_URL for test isolation
    os.environ["DATABASE_URL"] = test_url

    # Run migrations (sync - Alembic uses subprocess)
    try:
        run_alembic_upgrade()
    except RuntimeError as e:
        pytest.fail(str(e))

    yield


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def db_canary(db_schema_guard: None) -> AsyncIterator[str]:  # noqa: ARG001
    """Insert canary row at session start. If DB rebuilds, canary disappears.

    This fixture:
    1. Creates a fresh NullPool engine
    2. Inserts a User with known UUID and email
    3. Returns the canary email for verification

    The canary check in db_session verifies ~1ms PK lookup.
    """
    from promptgrimoire.db import User

    canary_email = f"canary-{_DB_CANARY_ID}@test.local"

    engine = create_async_engine(
        os.environ["DATABASE_URL"],
        poolclass=NullPool,
        connect_args={"timeout": 10, "command_timeout": 30},
    )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        canary_user = User(email=canary_email, display_name="DB Canary")
        session.add(canary_user)
        await session.commit()

    await engine.dispose()
    yield canary_email

    # Cleanup: remove canary row after session ends
    from sqlmodel import delete

    cleanup_engine = create_async_engine(
        os.environ["DATABASE_URL"],
        poolclass=NullPool,
        connect_args={"timeout": 10, "command_timeout": 30},
    )
    cleanup_factory = async_sessionmaker(
        cleanup_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with cleanup_factory() as session:
        # ty doesn't understand SQLModel column comparison returns expression, not bool
        await session.execute(delete(User).where(User.email == canary_email))  # type: ignore[arg-type]
        await session.commit()

    await cleanup_engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_canary: str) -> AsyncIterator[AsyncSession]:
    """Database session with NullPool - safe for xdist parallelism.

    Each test gets a fresh TCP connection to PostgreSQL.
    Connection closes when test ends. No pooling, no event loop binding.

    Verifies canary row exists - fails fast if database was rebuilt.
    Canary check uses email lookup (indexed column, ~1ms).
    Note: Email lookup is safer than UUID because User.id is auto-generated.
    """
    from sqlmodel import select

    from promptgrimoire.db import User

    engine = create_async_engine(
        os.environ["DATABASE_URL"],
        poolclass=NullPool,
        connect_args={"timeout": 10, "command_timeout": 30},
    )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        # Verify canary exists - fails if DB was rebuilt
        result = await session.execute(select(User).where(User.email == db_canary))
        canary = result.scalar_one_or_none()
        if canary is None:
            pytest.fail(
                f"DATABASE WAS REBUILT - canary row missing (email: {db_canary})"
            )

        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def mock_stytch_client():
    """Create a mocked Stytch B2BClient for unit tests.

    Patches the B2BClient constructor to return a mock, allowing
    tests to set up expected responses without making real API calls.

    Made async to ensure proper event loop handling with pytest-asyncio.
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
from pathlib import Path

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

from nicegui import app, ui
import promptgrimoire.pages  # noqa: F401 - registers routes

# Serve static JS/CSS assets (mirrors main() in promptgrimoire/__init__.py)
import promptgrimoire
_static_dir = Path(promptgrimoire.__file__).parent / "static"
app.add_static_files("/static", str(_static_dir))

ui.run(port=port, reload=False, show=False, storage_secret='{TEST_STORAGE_SECRET}')
"""


@pytest.fixture(scope="session")
def app_server() -> Generator[str]:
    """Provide the base URL of the NiceGUI app server for E2E tests.

    If ``E2E_BASE_URL`` is set (by the ``test-e2e`` CLI command), yields that
    URL directly — all xdist workers share the single external server.

    Otherwise, starts a NiceGUI server in a subprocess on a random port
    (one per session, which means one per xdist worker — wasteful but
    backwards-compatible for direct ``pytest -m e2e`` invocations).
    """
    external_url = os.environ.get("E2E_BASE_URL")
    if external_url:
        yield external_url
        return

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
